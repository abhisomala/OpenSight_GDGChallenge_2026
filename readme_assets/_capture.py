"""
Render opensight_desktop_anim.html to MP4 + GIF, fully on this machine.

Re-runnable: edit the HTML, then run this again.

    .venv/Scripts/python.exe readme_assets/_capture.py

Pipeline:
  1. Parse the card size (.appwin) + scene size (.scene) + the LOOP total
     straight from the HTML so this stays in sync with any tweaks.
  2. Playwright Chromium records ONE full loop with recordVideo (smoothest),
     after document.fonts.ready + ~1s so the first frame is on-brand. The loop
     is restarted via the page's own startLoop() so the recorded tail is exactly
     one clean loop (idle -> ... -> idle, first frame == last frame).
  3. Encode with the ffmpeg bundled by imageio-ffmpeg (no system install):
       - opensight_demo.mp4  (H.264, yuv420p, cropped tight to the card)
       - opensight_demo.gif  (two-pass palettegen/paletteuse, ~16fps, lean)
     The last LOOP seconds are extracted (-sseof) so the preamble is dropped.
"""
import re
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
HTML = HERE / "opensight_desktop_anim.html"
MP4 = HERE / "opensight_demo.mp4"
GIF = HERE / "opensight_demo.gif"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

GIF_FPS = 16          # GIF frame rate (drop to trim size)
GIF_WIDTH = 820       # GIF width in px (height auto, kept even)
GIF_MAX_MB = 6.0      # if the GIF is bigger, re-encode leaner


def _wh(css: str, selector: str):
    """Pull width/height (px) for a `.selector{ ... width:Wpx; height:Hpx ... }` rule."""
    block = re.search(re.escape(selector) + r"\{(.*?)\}", css, re.S).group(1)
    w = int(re.search(r"width:(\d+)px", block).group(1))
    h = int(re.search(r"height:(\d+)px", block).group(1))
    return w, h


def parse_html():
    css = HTML.read_text(encoding="utf-8")
    scene_w, scene_h = _wh(css, ".scene")
    card_w, card_h = _wh(css, ".appwin")
    loop_block = re.search(r"const LOOP\s*=\s*\{(.*?)\}", css, re.S).group(1)
    loop_ms = sum(int(n) for n in re.findall(r":\s*(\d+)", loop_block))
    return scene_w, scene_h, card_w, card_h, loop_ms


def record(scene_w, scene_h, loop_ms) -> Path:
    """Record one full loop; return the path to the .webm video."""
    tmp = Path(tempfile.mkdtemp(prefix="opensight_vid_"))
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
        page.wait_for_timeout(1000)               # settle on a fully-rendered idle frame
        page.evaluate("() => startLoop()")        # restart loop at frame 0 (idle)
        page.wait_for_timeout(loop_ms + 150)      # exactly one loop (+ tiny tail)
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
    scene_w, scene_h, card_w, card_h, loop_ms = parse_html()
    loop_s = loop_ms / 1000.0
    crop = (card_w, card_h, (scene_w - card_w) // 2, (scene_h - card_h) // 2)
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
        fps, width, colors = 13, 720, 128
        encode_gif(video, crop, loop_s, fps, width, colors)
        size_mb = GIF.stat().st_size / 1e6
    print(f"wrote {GIF}  ({size_mb:.2f} MB, {fps}fps, {width}px wide)")

    print("\nDONE")
    print(f"  MP4: {MP4}")
    print(f"  GIF: {GIF}  ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
