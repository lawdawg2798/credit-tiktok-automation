"""
assemble.py
Renders the final vertical video via Creatomate's API.

Creatomate's Voiceover layer generates audio FROM TEXT (via the project's
ElevenLabs integration), so we send the script text -- not an audio file.
The Captions layer auto-transcribes from that voiceover, so we don't set
caption text manually. The Background layer needs a PUBLIC URL, which we
build from the (public) GitHub repo's raw file host.

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

GITHUB_USER = "lawdawg2798"
GITHUB_REPO = "credit-tiktok-automation"
GITHUB_BRANCH = "main"


def load_templates():
    return json.loads(TEMPLATES_PATH.read_text())


def pick_background_clip(background_category):
    """Return a PUBLIC raw.githubusercontent.com URL for a matching clip."""
    candidates = list(BACKGROUNDS_DIR.glob(f"*{background_category}*"))
    if not candidates:
        candidates = list(BACKGROUNDS_DIR.glob("*"))
        # ignore any stray non-video junk like .gitkeep
        candidates = [c for c in candidates if c.is_file() and not c.name.startswith(".")]
        if not candidates:
            raise FileNotFoundError(
                f"No background clips found in {BACKGROUNDS_DIR}. Add source files first."
            )
        print(f"Warning: no backgrounds matching '{background_category}'. Using a random fallback.")

    chosen = random.choice(candidates)
    public_url = (
        f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/"
        f"{GITHUB_BRANCH}/assets_backgrounds/{chosen.name}"
    )
    print(f"  background -> {public_url}")
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
        },
    }
    resp = requests.post(CREATOMATE_URL, headers=headers, json=payload, timeout=30)
    if resp.status_code >= 400:
        # surface Creatomate's actual error body instead of a bare HTTPError
        raise RuntimeError(f"Creatomate render request failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    return data[0] if isinstance(data, list) else data


def poll_render(render_id, headers, timeout_s=300, interval_s=5):
    url = f"{CREATOMATE_URL}/{render_id}"
    waited = 0
    while waited < timeout_s:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")
        if status == "succeeded":
            return data["url"]
        if status == "failed":
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

    found_any = False
    for path in PENDING_DIR.glob("*.json"):
        record = json.loads(path.read_text())
        if record.get("status") not in ("script_ready", "voiceover_ready"):
            continue
        found_any = True

        print(f"Rendering {record['video_id']} (template={record['caption_style']})")
        submitted = submit_render(record, templates, headers)
        render_id = submitted["id"]
        video_url = poll_render(render_id, headers)

        local_path = PENDING_DIR / f"{record['video_id']}_final.mp4"
        video_bytes = requests.get(video_url, timeout=120).content
        local_path.write_bytes(video_bytes)

        record["status"] = "video_ready"
        record["final_video_path"] = str(local_path)
        path.write_text(json.dumps(record, indent=2))
        print(f"  video ready: {local_path.name}")

    if not found_any:
        print("No pending records with status script_ready/voiceover_ready found.")


if __name__ == "__main__":
    main()
