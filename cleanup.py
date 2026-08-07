"""
cleanup.py

Moves every finished video (status 'video_ready' or 'render_error') and all
its associated files out of content_pending/ into content_posted/, so
content_pending/ only ever contains fresh, not-yet-finished work.

This is safe: it never deletes anything, just archives. Run it any time
content_pending/ gets cluttered.

Run:  python cleanup.py
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PENDING_DIR = ROOT / "content_pending"
POSTED_DIR = ROOT / "content_posted"

# statuses considered "done" and safe to archive out of pending
DONE_STATUSES = {"video_ready", "render_error", "posted"}


def main():
    if not PENDING_DIR.exists():
        print("No content_pending/ folder; nothing to clean.")
        return

    POSTED_DIR.mkdir(exist_ok=True)

    moved_records = 0
    moved_files = 0

    for json_path in sorted(PENDING_DIR.glob("*.json")):
        try:
            record = json.loads(json_path.read_text())
        except json.JSONDecodeError:
            print(f"Skipping unreadable {json_path.name}")
            continue

        if record.get("status") not in DONE_STATUSES:
            continue  # leave fresh/in-progress work alone

        vid = record.get("video_id") or json_path.stem

        # move every file that starts with this video id
        for f in PENDING_DIR.glob(f"{vid}*"):
            dest = POSTED_DIR / f.name
            shutil.move(str(f), str(dest))
            moved_files += 1
        moved_records += 1
        print(f"archived {vid} (status={record.get('status')})")

    if moved_records == 0:
        print("Nothing to archive — content_pending/ is already clean.")
    else:
        print(f"\nDone: archived {moved_records} records ({moved_files} files) "
              f"into content_posted/.")
        print("content_pending/ now holds only fresh/in-progress videos.")


if __name__ == "__main__":
    main()
