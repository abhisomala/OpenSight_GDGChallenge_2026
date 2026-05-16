import asyncio
import os
import queue
import threading
import time

import sounddevice as sd

_WAKE_PHRASES = [
    "opensight",
    "open sight",
    "open site",
    "open sign",
    "open signs",
    "opsin",
    "open size",
    "open cited",
    "open sighed",
]

_WAKE_COOLDOWN = 2.0
_last_wake_time: float = 0.0


def _is_wake_word(transcript: str) -> bool:
    t = transcript.lower().strip()
    return any(phrase in t for phrase in _WAKE_PHRASES)


def _should_fire_wake() -> bool:
    """Check the wake word cooldown. Returns True if enough time has passed.

    Previously accepted an unused on_wake_cb parameter — removed.
    """
    global _last_wake_time
    now = time.monotonic()
    if now - _last_wake_time < _WAKE_COOLDOWN:
        return False
    _last_wake_time = now
    return True


def init_microphone(state):
    try:
        default_input_device = sd.default.device[0]
        info = sd.query_devices(default_input_device, "input")
        state.sample_rate = int(info["default_samplerate"])
    except Exception:
        print("[mic] Default input device error, falling back to library default")


def run_wake_word_loop(state, on_wake_cb):
    t = threading.Thread(
        target=lambda: asyncio.run(_wake_word_loop(state, on_wake_cb)),
        daemon=True,
    )
    t.start()


async def _wake_word_loop(state, on_wake_cb):
    try:
        websockets = __import__("websockets")
    except Exception:
        return

    while not state.shutdown_event.is_set():
        try:
            await _wake_word_listen(state, on_wake_cb, websockets)
        except Exception:
            print("[wake] error")
        if state.shutdown_event.is_set():
            break
        await asyncio.sleep(2)


async def _wake_word_listen(state, on_wake_cb, websockets):
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        return

    url = (
        "wss://api.deepgram.com/v1/listen"
        "?model=nova-2&language=en-US&smart_format=true"
        "&interim_results=true&endpointing=300"
        "&encoding=linear16&channels=1"
        f"&sample_rate={state.sample_rate}"
    )
    headers = {"Authorization": f"Token {api_key}"}

    try:
        async with websockets.connect(url, additional_headers=headers, ping_interval=None) as ws:
            ws_alive = True
            audio_queue: queue.Queue[bytes | None] = queue.Queue(maxsize=50)

            async def send_audio():
                while ws_alive and not state.shutdown_event.is_set():
                    frame = await asyncio.to_thread(audio_queue.get)
                    if frame is None:
                        return
                    await ws.send(frame)

            def audio_cb(indata, frames, t, status):
                if not ws_alive or state.shutdown_event.is_set():
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
                dtype="int16", channels=1, callback=audio_cb,
            )
            stream.start()
            sender = asyncio.create_task(send_audio())

            try:
                while not state.shutdown_event.is_set():
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
                            if transcript.strip() and _is_wake_word(transcript):
                                # _should_fire_wake() — on_wake_cb param removed (was unused)
                                if _should_fire_wake():
                                    try:
                                        import browser_manager
                                        browser_manager.focus_opensight()
                                    except Exception:
                                        pass
                                    on_wake_cb()
                    except asyncio.TimeoutError:
                        continue
                    except Exception:
                        print("[wake] recv error")
                        break
            finally:
                ws_alive = False
                try:
                    audio_queue.put_nowait(None)
                except queue.Full:
                    pass
                sender.cancel()
                stream.stop()
                stream.close()

    except Exception:
        print("[wake] connection error")


def run_deepgram_loop(state, session_token: int, redraw_cb, on_final_cb, on_interim_cb):
    asyncio.run(_deepgram_retry(state, session_token, redraw_cb, on_final_cb, on_interim_cb))


async def _deepgram_retry(state, session_token, redraw_cb, on_final_cb, on_interim_cb):
    try:
        websockets = __import__("websockets")
    except Exception:
        return

    retries = 0
    max_retries = 5
    while not state.stop_event.is_set() and session_token == state.session_token:
        try:
            await _deepgram_listen(state, session_token, on_final_cb, on_interim_cb, websockets)
        except Exception:
            print("[deepgram] error")
        if state.stop_event.is_set() or session_token != state.session_token:
            break
        retries += 1
        if retries > max_retries:
            break
        wait = min(2 ** retries, 30)
        await asyncio.sleep(wait)


async def _deepgram_listen(state, session_token, on_final_cb, on_interim_cb, websockets):
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        return

    url = (
        "wss://api.deepgram.com/v1/listen"
        "?model=nova-2&language=en-US&smart_format=true"
        "&interim_results=true&endpointing=2500"
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
                if status:
                    return
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
                                    if not _is_wake_word(transcript):
                                        on_final_cb(transcript)
                                else:
                                    on_interim_cb(f"... {transcript}")
                    except asyncio.TimeoutError:
                        continue
                    except Exception:
                        print("[deepgram] recv error")
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

    except Exception:
        print("[deepgram] connection error")


def voice_worker(state):
    while not state.shutdown_event.is_set():
        phrase = state.voice_queue.get()
        if phrase is None:
            break
        try:
            state.is_speaking = True
            speak_text(state, phrase)
        except Exception:
            print("[tts] error")
        finally:
            state.is_speaking = False
            # Increased from 0.5s to 1.2s — ElevenLabs streams audio and the
            # previous 0.5s window sometimes opened the mic while the speaker
            # was still active, causing Deepgram to transcribe the TTS output.
            state.suppress_until = time.monotonic() + 1.2


def speak_text(state, text: str):
    import platform
    import subprocess
    import tempfile
    import os

    tts_creds = os.getenv("GOOGLE_TTS_CREDENTIALS")

    if tts_creds and os.path.exists(tts_creds):
        try:
            from google.cloud import texttospeech
            import pygame

            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tts_creds
            client = texttospeech.TextToSpeechClient()

            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(
                language_code="en-US",
                name=os.getenv("GOOGLE_TTS_VOICE", "en-US-Journey-F"),
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3
            )

            response = client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config,
            )

            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(response.audio_content)
                tmp_path = f.name

            pygame.mixer.init()
            pygame.mixer.music.load(tmp_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)
            pygame.mixer.quit()
            os.unlink(tmp_path)
            return

        except Exception as e:
            print(f"[tts] Google TTS error: {e}, falling back")

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