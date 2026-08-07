"""
cleanup.py

Moves every finished video (status 'video_ready', 'render_error', or
'posted') and all its associated files out of content_pending/ into
content_posted/, so content_pending/ only ever contains fresh work.

Safe: it never deletes anything, only archives (moves).

Run:  python cleanup.py
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PENDING_DIR = ROOT / "content_pending"
POSTED_DIR = ROOT / "content_posted"

DONE_STATUSES = {"video_ready", "render_error", "posted"}


def main():
    if not PENDING_DIR.exists():
        print("No content_pending/ folder; nothing to clean.")
        return

    POSTED_DIR.mkdir(exist_ok=True)

    record_files = [
        p for p in sorted(PENDING_DIR.glob("*.json"))
        if "_" not in p.stem
    ]

    moved_records = 0
    moved_files = 0

    for json_path in record_files:
        if not json_path.exists():
            continue
        try:
            record = json.loads(json_path.read_text())
        except json.JSONDecodeError:
            print(f"Skipping unreadable {json_path.name}")
            continue

        if record.get("status") not in DONE_STATUSES:
            continue

        vid = record.get("video_id") or json_path.stem

        files = list(PENDING_DIR.glob(f"{vid}*"))
        for f in files:
            if not f.exists():
                continue
            dest = POSTED_DIR / f.name
            try:
                shutil.move(str(f), str(dest))
                moved_files += 1
            except FileNotFoundError:
                pass
        moved_records += 1
        print(f"archived {vid} (status={record.get('status')})")

    if moved_records == 0:
        print("Nothing to archive -- content_pending/ is already clean.")
    else:
        print(f"\nDone: archived {moved_records} records ({moved_files} files) "
              f"into content_posted/.")
        print("content_pending/ now holds only fresh/in-progress videos.")


if __name__ == "__main__":
    main()
