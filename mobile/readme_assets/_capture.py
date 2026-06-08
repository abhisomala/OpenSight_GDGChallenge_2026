"""
Render opensight_anim.html (the Flutter Android client loop) to MP4 + GIF,
fully on this machine. Mobile sibling of ../../readme_assets/_capture.py — same
method (Playwright record + imageio-ffmpeg two-pass GIF), adapted to this HTML.

Re-runnable: edit the HTML, then run this again.

    .venv/Scripts/python.exe mobile/readme_assets/_capture.py

Differences from the desktop capture:
  - This HTML has no `.scene`/`.appwin`/`startLoop()`. The croppable target is
    the phone `.card` (440x920), centered on a slightly-darker page; the scene
    is the card plus a small margin so the bezel edge crops cleanly.
  - The loop is a seamless `requestAnimationFrame` modulo of `T.END` (first
    frame == last frame). After fonts settle we call the page's startLoop() to
    reset it to frame 0 (idle), then record one full loop and extract the
    trailing loop with -sseof, so the GIF opens on the clean idle frame.
  - GIF is sized for a tall portrait phone (narrower than the desktop card).
"""
import re
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
HTML = HERE / "opensight_anim.html"
MP4 = HERE / "opensight_mobile_demo.mp4"
GIF = HERE / "opensight_mobile_demo.gif"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

MARGIN = 20           # dark page margin around the card, for a clean crop
GIF_FPS = 16          # GIF frame rate (drop to trim size)
GIF_WIDTH = 400       # GIF width in px, portrait phone (height auto, kept even)
GIF_MAX_MB = 6.0      # if the GIF is bigger, re-encode leaner


def _wh(css: str, selector: str):
    """Pull width/height (px) for a `.selector{ ... width:Wpx; height:Hpx ... }` rule."""
    block = re.search(re.escape(selector) + r"\{(.*?)\}", css, re.S).group(1)
    w = int(re.search(r"width:(\d+)px", block).group(1))
    h = int(re.search(r"height:(\d+)px", block).group(1))
    return w, h


def parse_html():
    css = HTML.read_text(encoding="utf-8")
    card_w, card_h = _wh(css, ".card")
    # Seamless loop length is the END mark of the `const T = {...}` timeline.
    t_block = re.search(r"const T\s*=\s*\{(.*?)\}", css, re.S).group(1)
    loop_ms = int(re.search(r"END:\s*(\d+)", t_block).group(1))
    return card_w, card_h, loop_ms


def record(scene_w, scene_h, loop_ms) -> Path:
    """Record one full seamless loop; return the path to the .webm video."""
    tmp = Path(tempfile.mkdtemp(prefix="opensight_mobile_vid_"))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": scene_w, "height": scene_h},
            record_video_dir=str(tmp),
            record_video_size={"width": scene_w, "height": scene_h},
            device_scale_factor=1,
        )
        page = ctx.new_page()
        page.goto(HTML.resolve().as_uri())
        page.evaluate("() => document.fonts.ready")
        page.wait_for_timeout(1200)               # settle; fonts on-brand
        page.evaluate("() => window.startLoop && window.startLoop()")  # reset to idle frame 0
        page.wait_for_timeout(loop_ms + 200)      # exactly one clean loop (+ tail)
        video_path = Path(page.video.path())
        ctx.close()                               # finalizes the .webm
        browser.close()
    return video_path


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def encode_mp4(video, crop, loop_s):
    cw, ch, cx, cy = crop
    run([FFMPEG, "-y", "-sseof", f"-{loop_s:.3f}", "-i", str(video), "-an",
         "-vf", f"crop={cw}:{ch}:{cx}:{cy}", "-c:v", "libx264", "-preset", "veryslow",
         "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(MP4)])


def encode_gif(video, crop, loop_s, fps, width, colors=160):
    cw, ch, cx, cy = crop
    with tempfile.TemporaryDirectory() as td:
        palette = Path(td) / "palette.png"
        vf = f"crop={cw}:{ch}:{cx}:{cy},fps={fps},scale={width}:-2:flags=lanczos"
        run([FFMPEG, "-y", "-sseof", f"-{loop_s:.3f}", "-i", str(video),
             "-vf", f"{vf},palettegen=max_colors={colors}:stats_mode=diff", str(palette)])
        run([FFMPEG, "-y", "-sseof", f"-{loop_s:.3f}", "-i", str(video), "-i", str(palette),
             "-lavfi", f"{vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle",
             "-loop", "0", str(GIF)])


def main():
    card_w, card_h, loop_ms = parse_html()
    scene_w, scene_h = card_w + 2 * MARGIN, card_h + 2 * MARGIN
    loop_s = loop_ms / 1000.0
    crop = (card_w, card_h, MARGIN, MARGIN)
    print(f"scene {scene_w}x{scene_h} | card {card_w}x{card_h} | loop {loop_s:.1f}s")

    video = record(scene_w, scene_h, loop_ms)
    print(f"recorded {video}")

    encode_mp4(video, crop, loop_s)
    print(f"wrote {MP4}  ({MP4.stat().st_size/1e6:.2f} MB)")

    # GIF: encode, then trim leaner if it overshoots the size target
    fps, width, colors = GIF_FPS, GIF_WIDTH, 160
    encode_gif(video, crop, loop_s, fps, width, colors)
    size_mb = GIF.stat().st_size / 1e6
    if size_mb > GIF_MAX_MB:
        print(f"gif {size_mb:.2f} MB > {GIF_MAX_MB} MB — re-encoding leaner")
        fps, width, colors = 13, 340, 128
        encode_gif(video, crop, loop_s, fps, width, colors)
        size_mb = GIF.stat().st_size / 1e6
    print(f"wrote {GIF}  ({size_mb:.2f} MB, {fps}fps, {width}px wide)")

    print("\nDONE")
    print(f"  MP4: {MP4}")
    print(f"  GIF: {GIF}  ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
