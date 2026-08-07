"""
assemble.py

Assembles the final vertical video LOCALLY with ffmpeg -- no Creatomate,
no per-video cost beyond what you already pay ElevenLabs for the voice.

Captions are written as a proper .ass subtitle file (not .srt + force_style)
so font size, color, and centering are set natively and reliably. Word
timing comes from ElevenLabs' real per-character alignment when available
(zero drift), falling back to a character-weighted estimate otherwise.

Run:  python assemble.py
"""
import json
import os
import subprocess
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
    # marginv=300 on a 1280px frame puts captions ~23% up from the bottom --
    # clear of TikTok/Reels' own UI (username, caption, music ticker), which
    # typically covers the bottom ~10-12% when a video is actually posted.
    "bold_yellow_bottom": {"color": "&H0000D4FF", "alignment": 2, "marginv": 300},
    "clean_white_center": {"color": "&H00FFFFFF", "alignment": 5, "marginv": 0},
    "outline_center_top": {"color": "&H00FFFFFF", "alignment": 8, "marginv": 140},
}

# Accent color for emphasized words (bright red-orange), used across all
# caption styles so key words visually pop regardless of the base style.
EMPHASIS_COLOR = "&H00303BFF"   # ASS format &HAABBGGRR -> RGB approx (255,59,48)
EMPHASIS_FONT_BUMP = 8          # emphasized words render slightly larger

# Words/patterns that should be visually emphasized when they appear in a
# caption -- names of dramatic beats, betrayal/conflict language, etc.
# Numbers are always emphasized too (handled separately, not in this set).
EMPHASIS_KEYWORDS = {
    "cheating", "cheated", "affair", "cheater",
    "fired", "quit", "quitting",
    "lied", "liar", "lying",
    "divorce", "divorced", "engaged", "wedding", "pregnant",
    "secret", "secretly", "betrayed", "betrayal",
    "stole", "stealing", "stolen", "scam", "scammed",
    "arrested", "caught", "exposed", "confronted",
    "threatened", "blackmail", "revenge",
    "evicted", "kicked", "banned",
    "died", "death", "killed",
    "police", "lawyer", "court", "sued",
}


def is_emphasis_word(word):
    """True if this word should render in the accent color/larger size."""
    stripped = "".join(ch for ch in word if ch.isalnum())
    if not stripped:
        return False
    if stripped.isdigit():
        return True
    return stripped.lower() in EMPHASIS_KEYWORDS

FONT_SIZE = 30
MIN_WORD_DUR = 0.22


def words_from_alignment(alignment):
    chars = alignment["characters"]
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]

    words = []
    cur_word = ""
    cur_start = None
    prev_end = None
    for ch, s, e in zip(chars, starts, ends):
        if ch.strip() == "":
            if cur_word:
                words.append((cur_word, cur_start, prev_end))
                cur_word = ""
                cur_start = None
            continue
        if cur_start is None:
            cur_start = s
        cur_word += ch
        prev_end = e
    if cur_word:
        words.append((cur_word, cur_start, prev_end))
    return words


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


def fmt_ass_ts(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def word_timings(all_words, total_dur):
    weights = [max(len(w), 3) for w in all_words]
    total_weight = sum(weights)
    raw = [total_dur * (w / total_weight) for w in weights]
    durs = [max(d, MIN_WORD_DUR) for d in raw]
    scale = total_dur / sum(durs)
    return [d * scale for d in durs]


def build_ass(record, total_dur, ass_path, alignment=None):
    style = CAPTION_STYLES[record["caption_style"]]
    emphasis_size = FONT_SIZE + EMPHASIS_FONT_BUMP

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{FONT_SIZE},{style['color']},&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,{style['alignment']},20,20,{style['marginv']},1
Style: Emphasis,DejaVu Sans,{emphasis_size},{EMPHASIS_COLOR},&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,{style['alignment']},20,20,{style['marginv']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]

    def dialogue_line(word, start, end):
        style_name = "Emphasis" if is_emphasis_word(word) else "Default"
        return f"Dialogue: 0,{fmt_ass_ts(start)},{fmt_ass_ts(end)},{style_name},,0,0,0,,{word.upper()}"

    if alignment:
        for word, start, end in words_from_alignment(alignment):
            lines.append(dialogue_line(word, start, end))
    else:
        full_text = " ".join(
            str(b).strip() for b in record["beats"].values() if str(b).strip()
        )
        all_words = full_text.split()
        if all_words:
            durs = word_timings(all_words, total_dur)
            t = 0.0
            for word, d in zip(all_words, durs):
                start, end = t, t + d
                t = end
                lines.append(dialogue_line(word, start, end))

    ass_path.write_text("\n".join(lines))


def assemble_video(background_path, audio_path, ass_path, out_path, dur):
    scale_crop = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT}"
    )
    subs_filter = f"ass={ass_path}"

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
            audio_path = PENDING_DIR / f"{record['video_id']}_voiceover.mp3"
            ass_path = PENDING_DIR / f"{record['video_id']}_captions.ass"
            out_path = PENDING_DIR / f"{record['video_id']}_final.mp4"

            dur = audio_duration(audio_path)

            alignment = None
            alignment_file = record.get("alignment_path")
            if alignment_file and Path(alignment_file).exists():
                alignment = json.loads(Path(alignment_file).read_text())
            else:
                local_alignment = PENDING_DIR / f"{record['video_id']}_alignment.json"
                if local_alignment.exists():
                    alignment = json.loads(local_alignment.read_text())

            build_ass(record, dur, ass_path, alignment=alignment)
            assemble_video(background_path, audio_path, ass_path, out_path, dur)

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
