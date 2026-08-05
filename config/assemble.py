"""
assemble.py

Combines background footage + voiceover + captions into the final vertical
video via Creatomate's API. You'll need one Creatomate template per
caption_style (build these once in their editor — this script just swaps
the dynamic layer contents per video).

Requires config/creatomate_templates.json mapping caption_style id ->
Creatomate template_id, e.g.:
{
  "bold_yellow_bottom": "tpl_xxx",
  "clean_white_center": "tpl_yyy",
  "outline_center_top": "tpl_zzz"
}

Run:  python scripts/assemble.py
"""
import json
import os
import random
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
PENDING_DIR = ROOT / "content" / "pending"
TEMPLATES_PATH = ROOT / "config" / "creatomate_templates.json"

CREATOMATE_API_KEY = os.environ["CREATOMATE_API_KEY"]
CREATOMATE_URL = "https://api.creatomate.com/v1/renders"


def load_templates():
    return json.loads(TEMPLATES_PATH.read_text())


def pick_background_clip(background_category):
    clips_dir = ROOT / "assets" / "backgrounds"
    # In practice: point this at wherever your original/licensed b-roll lives.
    # Picking randomly *within* the assigned category keeps the category
    # consistent with what generate_script.py chose, while still varying
    # the exact clip used.
    candidates = list((clips_dir).glob(f"**/*{background_category}*"))
    if not candidates:
        raise FileNotFoundError(
            f"No background clips found for category '{background_category}' "
            f"in {clips_dir}. Add source files there first."
        )
    return str(random.choice(candidates))


def submit_render(record, templates):
    template_id = templates[record["caption_style"]]
    background_clip = pick_background_clip(record["background_category"])

    payload = {
        "template_id": template_id,
        "modifications": {
            "Voiceover.source": record["audio_path"],
            "Background.source": background_clip,
            "Caption-Text": " ".join(record["beats"].values()),
            # Creatomate's auto-transcription/caption layer picks up timing
            # from the Voiceover audio track automatically if configured
            # that way in the template.
        },
    }
    headers = {
        "Authorization": f"Bearer {CREATOMATE_API_KEY}",
        "Content-Type": "application/json",
    }
    resp = requests.post(CREATOMATE_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def poll_render(render_id, headers, timeout_s=300, interval_s=5):
    url = f"{CREATOMATE_URL}/{render_id}"
    waited = 0
    while waited < timeout_s:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data["status"] == "succeeded":
            return data["url"]
        if data["status"] == "failed":
            raise RuntimeError(f"Render {render_id} failed: {data}")
        time.sleep(interval_s)
        waited += interval_s
    raise TimeoutError(f"Render {render_id} did not finish in {timeout_s}s")


def main():
    templates = load_templates()
    headers = {"Authorization": f"Bearer {CREATOMATE_API_KEY}"}

    for path in PENDING_DIR.glob("*.json"):
        record = json.loads(path.read_text())
        if record["status"] != "voiceover_ready":
            continue

        submitted = submit_render(record, templates)
        video_url = poll_render(submitted["id"], headers)

        local_path = PENDING_DIR / f"{record['video_id']}_final.mp4"
        video_bytes = requests.get(video_url, timeout=60).content
        local_path.write_bytes(video_bytes)

        record["status"] = "video_ready"
        record["final_video_path"] = str(local_path)
        path.write_text(json.dumps(record, indent=2))
        print(f"video ready: {local_path.name}")


if __name__ == "__main__":
    main()
