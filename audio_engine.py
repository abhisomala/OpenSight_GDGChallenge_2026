import asyncio
import os
import queue
import threading
import time

import sounddevice as sd


def init_microphone(state):
    try:
        default_input_device = sd.default.device[0]
        info = sd.query_devices(default_input_device, "input")
        print(f"[mic] Using default input device {default_input_device}: {info['name']} @ {int(info['default_samplerate'])}Hz")
        state.sample_rate = int(info["default_samplerate"])
    except Exception as e:
        print(f"[mic] Default input device error: {e}, falling back to library default")


def run_deepgram_loop(state, session_token: int, redraw_cb, on_final_cb, on_interim_cb, on_wake_cb=None):
    asyncio.run(_deepgram_retry(state, session_token, redraw_cb, on_final_cb, on_interim_cb, on_wake_cb))


async def _deepgram_retry(state, session_token, redraw_cb, on_final_cb, on_interim_cb, on_wake_cb=None):
    try:
        websockets = __import__("websockets")
    except Exception:
        return

    retries = 0
    max_retries = 5
    while not state.stop_event.is_set() and session_token == state.session_token:
        try:
            await _deepgram_listen(state, session_token, on_final_cb, on_interim_cb, websockets, on_wake_cb)
        except Exception as e:
            print(f"[deepgram] error: {e}")
        if state.stop_event.is_set() or session_token != state.session_token:
            break
        retries += 1
        if retries > max_retries:
            break
        wait = min(2 ** retries, 30)
        print(f"[deepgram] retrying in {wait}s (attempt {retries}/{max_retries})")
        await asyncio.sleep(wait)


async def _deepgram_listen(state, session_token, on_final_cb, on_interim_cb, websockets, on_wake_cb=None):
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        return

    url = (
        "wss://api.deepgram.com/v1/listen"
        "?model=nova-2&language=en-US&smart_format=true"
        "&interim_results=true&endpointing=1200"
        "&encoding=linear16&channels=1"
        f"&sample_rate={state.sample_rate}"
    )
    headers = {"Authorization": f"Token {api_key}"}

    try:
        async with websockets.connect(url, additional_headers=headers, ping_interval=None) as ws:
            ws_alive = True
            audio_queue: queue.Queue[bytes | None] = queue.Queue(maxsize=50)

            async def send_audio_frames():
                while ws_alive and not state.stop_event.is_set() and session_token == state.session_token:
                    frame = await asyncio.to_thread(audio_queue.get)
                    if frame is None:
                        return
                    await ws.send(frame)

            def audio_callback(indata, frames, t, status):
                if not ws_alive or state.stop_event.is_set():
                    return
                if session_token != state.session_token:
                    return
                if state.is_speaking:
                    return
                if time.monotonic() < state.suppress_until:
                    return
                frame = bytes(indata)
                try:
                    audio_queue.put_nowait(frame)
                except queue.Full:
                    try:
                        audio_queue.get_nowait()
                        audio_queue.put_nowait(frame)
                    except (queue.Empty, queue.Full):
                        pass

            stream = sd.InputStream(
                samplerate=state.sample_rate, blocksize=4800,
                dtype="int16", channels=1, callback=audio_callback,
            )
            stream.start()
            sender_task = asyncio.create_task(send_audio_frames())

            try:
                while not state.stop_event.is_set() and session_token == state.session_token:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        import json
                        data = json.loads(msg)
                        if data.get("type") == "Results":
                            transcript = (
                                data.get("channel", {})
                                    .get("alternatives", [{}])[0]
                                    .get("transcript", "")
                            )
                            is_final = bool(data.get("is_final") or data.get("speech_final"))
                            if transcript and transcript.strip():
                                if is_final:
                                    transcript_lower = transcript.lower().strip()
                                    if on_wake_cb and any(phrase in transcript_lower for phrase in [
                                        "hey opensight", "opensight", "hey open sight",
                                        "open site", "hey open site",
                                    ]):
                                        on_wake_cb()
                                    else:
                                        on_final_cb(transcript)
                                else:
                                    on_interim_cb(f"... {transcript}")
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        print(f"[deepgram] recv error: {e}")
                        break
            finally:
                ws_alive = False
                try:
                    audio_queue.put_nowait(None)
                except queue.Full:
                    pass
                sender_task.cancel()
                stream.stop()
                stream.close()

    except Exception as e:
        print(f"[deepgram] connection error: {e}")


def voice_worker(state):
    while not state.shutdown_event.is_set():
        phrase = state.voice_queue.get()
        if phrase is None:
            break
        try:
            state.is_speaking = True
            speak_text(state, phrase)
        except Exception as e:
            print(f"[tts] error: {e}")
        finally:
            state.is_speaking = False
            state.suppress_until = time.monotonic() + 0.5


def speak_text(state, text: str):
    import platform
    import subprocess

    api_key = os.getenv("ELEVENLABS_API_KEY")

    if api_key:
        try:
            from elevenlabs.client import ElevenLabs
            from elevenlabs import stream as el_stream

            el_client = ElevenLabs(api_key=api_key)
            audio = el_client.text_to_speech.convert(
                voice_id="onwK4e9ZLuTAKqWW03F9",
                text=text,
                model_id="eleven_turbo_v2",
            )
            el_stream(audio)
            return
        except Exception as e:
            print(f"[tts] ElevenLabs error: {e}, falling back")

    system_name = platform.system()
    if system_name == "Darwin":
        subprocess.run(["say", "-v", "Ava", "-r", "175", text], check=False)
    elif system_name == "Windows":
        safe = text.replace("'", "''")
        cmd = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Speak('{safe}')"
        )
        subprocess.run(["powershell", "-Command", cmd], check=False)
    else:
        subprocess.run(["espeak", text], check=False)