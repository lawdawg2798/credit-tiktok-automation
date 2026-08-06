"""
assemble.py
Combines background footage + an ElevenLabs-generated voiceover + captions
into the final vertical video via Creatomate's API.

IMPORTANT: Creatomate's Voiceover layer is configured (per-template, via the
project's ElevenLabs integration) to generate audio FROM TEXT. So this script
sends the script text as the Voiceover source, not an audio file. Creatomate
calls ElevenLabs on its own servers -- no file hosting needed for audio.

Background clips must be at a PUBLIC URL Creatomate can fetch. Since your
footage lives in this GitHub repo, we build the raw.githubusercontent.com
URL for whichever file matches the requested category.

Run:  python assemble.py
"""
import json
import os
import random
import time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
PENDING_DIR = ROOT / "content_pending"
TEMPLATES_PATH = ROOT / "creatomate_templates.json"
BACKGROUNDS_DIR = ROOT / "assets_backgrounds"

CREATOMATE_API_KEY = os.environ["CREATOMATE_API_KEY"]
CREATOMATE_URL = "https://api.creatomate.com/v1/renders"

# --- fill these in once, to match your actual GitHub repo ---
GITHUB_USER = "lawdawg2798"
GITHUB_REPO = "credit-tiktok-automation"
GITHUB_BRANCH = "main"
# ---------------------------------------------------------------


def load_templates():
    return json.loads(TEMPLATES_PATH.read_text())


def pick_background_clip(background_category):
    """
    Returns a PUBLIC raw.githubusercontent.com URL for a clip whose filename
    contains background_category, falling back to any available clip.
    """
    candidates = list(BACKGROUNDS_DIR.glob(f"*{background_category}*"))
    if not candidates:
        candidates = list(BACKGROUNDS_DIR.glob("*"))
        if not candidates:
            raise FileNotFoundError(
                f"No background clips found for category '{background_category}' "
                f"in {BACKGROUNDS_DIR}. Add source files there first."
            )
        print(f"Warning: no backgrounds matching '{background_category}'. Using a random fallback.")

    chosen = random.choice(candidates)
    filename = chosen.name
    public_url = (
        f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/"
        f"{GITHUB_BRANCH}/assets_backgrounds/{filename}"
    )
    return public_url


def narration_text(record):
    return " ".join(record["beats"].values())


def submit_render(record, templates, headers):
    template_id = templates[record["caption_style"]]
    background_url = pick_background_clip(record["background_category"])
    script_text = narration_text(record)

    payload = {
        "template_id": template_id,
        "modifications": {
            "Voiceover.source": script_text,
            "Background.source": background_url,
            "Captions.text": script_text,
        },
    }
    resp = requests.post(CREATOMATE_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data[0] if isinstance(data, list) else data


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
    headers = {
        "Authorization": f"Bearer {CREATOMATE_API_KEY}",
        "Content-Type": "application/json",
    }

    for path in PENDING_DIR.glob("*.json"):
        record = json.loads(path.read_text())
        if record["status"] not in ("script_ready", "voiceover_ready"):
            continue

        submitted = submit_render(record, templates, headers)
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
