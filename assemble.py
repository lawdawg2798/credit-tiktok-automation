"""
assemble.py

Assembles the final vertical video LOCALLY with ffmpeg -- no Creatomate,
no per-video cost beyond what you already pay ElevenLabs for the voice.

Run:  python assemble.py
"""
import json
import os
import random
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PENDING_DIR = ROOT / "content_pending"
BACKGROUNDS_DIR = ROOT / "assets_backgrounds"

WIDTH, HEIGHT = 720, 1280

BACKGROUND_FILES = {
    "bold_yellow_bottom": "bold_yellow_bottom_bg.mp4",
    "clean_white_center": "clean_white_center_bg.mp4",
    "outline_center_top": "outline_center_top_bg.mp4",
}

CAPTION_STYLES = {
    "bold_yellow_bottom": {"color": "&H0000D4FF", "alignment": 2, "marginv": 90},
    "clean_white_center": {"color": "&H00FFFFFF", "alignment": 5, "marginv": 0},
    "outline_center_top": {"color": "&H00FFFFFF", "alignment": 8, "marginv": 90},
}


def narration_text(record):
    return " ".join(str(v).strip() for v in record["beats"].values() if str(v).strip())


def pick_background(caption_style):
    filename = BACKGROUND_FILES.get(caption_style)
    if not filename:
        raise KeyError(f"No background mapped for caption_style '{caption_style}'")
    path = BACKGROUNDS_DIR / filename
    if not path.exists():
        candidates = [
            c for c in BACKGROUNDS_DIR.glob("*")
            if c.is_file() and not c.name.startswith(".")
        ]
        if not candidates:
            raise FileNotFoundError(
                f"No background found for '{caption_style}' and no fallback "
                f"clips exist in {BACKGROUNDS_DIR}."
            )
        print(f"Warning: '{filename}' not found, using fallback {candidates[0].name}")
        return candidates[0]
    return path


def audio_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def fmt_ts(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(record, total_dur, srt_path):
    beats = [b for b in record["beats"].values() if str(b).strip()]
    words = [max(1, len(str(b).split())) for b in beats]
    total_words = sum(words)
    lines = []
    t = 0.0
    for i, (beat_text, w) in enumerate(zip(beats, words), start=1):
        dur = total_dur * (w / total_words)
        start, end = t, t + dur
        t = end
        lines.append(str(i))
        lines.append(f"{fmt_ts(start)} --> {fmt_ts(end)}")
        lines.append("\n".join(textwrap.wrap(str(beat_text), width=28)))
        lines.append("")
    srt_path.write_text("\n".join(lines))


def assemble_video(record, background_path, audio_path, srt_path, out_path):
    style = CAPTION_STYLES[record["caption_style"]]
    dur = audio_duration(audio_path)

    ass_style = (
        "FontName=DejaVu Sans,"
        "FontSize=16,"
        f"PrimaryColour={style['color']},"
        "Bold=1,"
        f"Alignment={style['alignment']},"
        f"MarginV={style['marginv']},"
        "Outline=2,"
        "BorderStyle=1"
    )
    subs_filter = f"subtitles={srt_path}:force_style='{ass_style}'"

    scale_crop = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT}"
    )

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(background_path),
            "-i", str(audio_path),
            "-vf", f"{scale_crop},{subs_filter}",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-t", str(dur),
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def main():
    if not PENDING_DIR.exists():
        print(f"No pending directory yet ({PENDING_DIR}); nothing to assemble.")
        return

    found_any = False
    for path in sorted(PENDING_DIR.glob("*.json")):
        record = json.loads(path.read_text())
        if record.get("status") != "voiceover_ready":
            continue
        found_any = True

        print(f"Assembling {record['video_id']} (style={record['caption_style']})")
        try:
            background_path = pick_background(record["caption_style"])
            audio_path = Path(record["audio_path"])
            srt_path = PENDING_DIR / f"{record['video_id']}_captions.srt"
            out_path = PENDING_DIR / f"{record['video_id']}_final.mp4"

            dur = audio_duration(audio_path)
            build_srt(record, dur, srt_path)
            assemble_video(record, background_path, audio_path, srt_path, out_path)

            record["status"] = "video_ready"
            record["final_video_path"] = str(out_path)
            path.write_text(json.dumps(record, indent=2))
            print(f"  video ready: {out_path.name} ({out_path.stat().st_size} bytes)")
        except subprocess.CalledProcessError as e:
            print(f"  ERROR (ffmpeg) on {record.get('video_id')}: {e.stderr[-500:]}")
            record["status"] = "render_error"
            record["error"] = e.stderr[-500:]
            path.write_text(json.dumps(record, indent=2))
        except Exception as e:
            print(f"  ERROR on {record.get('video_id')}: {e}")
            record["status"] = "render_error"
            record["error"] = str(e)
            path.write_text(json.dumps(record, indent=2))

    if not found_any:
        print("No pending records with status voiceover_ready found.")


if __name__ == "__main__":
    main()
