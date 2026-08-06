"""
assemble.py
Renders the final vertical video via Creatomate's API.

Backgrounds are now BAKED INTO each Creatomate template, so this script does
NOT send a background at all. Each template already contains:
  - its own background video (uploaded directly in Creatomate)
  - a Voiceover layer set to ElevenLabs generation (generates audio FROM TEXT)
  - a Captions layer that auto-transcribes from that voiceover

So the ONLY thing we send is the script text for the voiceover. No file
hosting, no URLs, no GitHub dependency. Far fewer failure points.

Run:  python assemble.py
"""
import json
import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
PENDING_DIR = ROOT / "content_pending"
TEMPLATES_PATH = ROOT / "creatomate_templates.json"

CREATOMATE_API_KEY = os.environ["CREATOMATE_API_KEY"]
CREATOMATE_URL = "https://api.creatomate.com/v1/renders"


def load_templates():
    if not TEMPLATES_PATH.exists():
        raise FileNotFoundError(f"Missing {TEMPLATES_PATH}")
    return json.loads(TEMPLATES_PATH.read_text())


def narration_text(record):
    beats = record.get("beats", {})
    text = " ".join(str(v).strip() for v in beats.values() if str(v).strip())
    if not text:
        raise ValueError(f"Record {record.get('video_id')} has no usable script text.")
    return text


def submit_render(record, templates, headers):
    caption_style = record.get("caption_style")
    if caption_style not in templates:
        raise KeyError(
            f"caption_style '{caption_style}' not found in creatomate_templates.json "
            f"(available: {list(templates.keys())})"
        )
    template_id = templates[caption_style]
    script_text = narration_text(record)

    payload = {
        "template_id": template_id,
        "modifications": {
            "Voiceover.source": script_text,
        },
    }

    print(f"  template_id={template_id}")
    print(f"  voiceover text ({len(script_text)} chars): {script_text[:80]}...")

    resp = requests.post(CREATOMATE_URL, headers=headers, json=payload, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Creatomate render request failed ({resp.status_code}): {resp.text}"
        )
    data = resp.json()
    item = data[0] if isinstance(data, list) else data
    if "id" not in item:
        raise RuntimeError(f"Unexpected Creatomate response (no id): {item}")
    return item


def poll_render(render_id, headers, timeout_s=600, interval_s=5):
    url = f"{CREATOMATE_URL}/{render_id}"
    waited = 0
    while waited < timeout_s:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")
        if status == "succeeded":
            if not data.get("url"):
                raise RuntimeError(f"Render succeeded but no url returned: {data}")
            return data["url"]
        if status in ("failed", "error"):
            raise RuntimeError(f"Render {render_id} failed: {data}")
        time.sleep(interval_s)
        waited += interval_s
    raise TimeoutError(f"Render {render_id} did not finish in {timeout_s}s")


def main():
    templates = load_templates()
    headers = {
        "Authorization": f"Bearer {CREATOMATE_API_KEY}",
        "Content-Type": "application/json",
    }

    if not PENDING_DIR.exists():
        print(f"No pending directory yet ({PENDING_DIR}); nothing to render.")
        return

    found_any = False
    for path in sorted(PENDING_DIR.glob("*.json")):
        try:
            record = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            print(f"Skipping unreadable {path.name}: {e}")
            continue

        if record.get("status") not in ("script_ready", "voiceover_ready"):
            continue
        found_any = True

        print(f"Rendering {record.get('video_id')} (style={record.get('caption_style')})")
        try:
            submitted = submit_render(record, templates, headers)
            video_url = poll_render(submitted["id"], headers)

            local_path = PENDING_DIR / f"{record['video_id']}_final.mp4"
            video_bytes = requests.get(video_url, timeout=180).content
            local_path.write_bytes(video_bytes)

            record["status"] = "video_ready"
            record["final_video_path"] = str(local_path)
            path.write_text(json.dumps(record, indent=2))
            print(f"  video ready: {local_path.name} ({len(video_bytes)} bytes)")
        except Exception as e:
            print(f"  ERROR on {record.get('video_id')}: {e}")
            record["status"] = "render_error"
            record["error"] = str(e)
            path.write_text(json.dumps(record, indent=2))
            continue

    if not found_any:
        print("No pending records with status script_ready/voiceover_ready found.")


if __name__ == "__main__":
    main()
