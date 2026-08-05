"""
post_to_tiktok.py

Picks the single oldest 'video_ready' record, posts it via TikTok's
Content Posting API (official, requires an approved app + OAuth token —
see README), flags it as AI-generated per TikTok's disclosure requirement,
and moves the record to content/posted/.

Intended to run once per scheduled slot (see .github/workflows/daily-post.yml).

Run:  python scripts/post_to_tiktok.py
"""
import json
import os
import random
import shutil
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
PENDING_DIR = ROOT / "content" / "pending"
POSTED_DIR = ROOT / "content" / "posted"

TIKTOK_ACCESS_TOKEN = os.environ["TIKTOK_ACCESS_TOKEN"]
POST_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"

HASHTAG_POOLS = {
    "medical_debt_collections": ["#creditrepair", "#medicaldebt", "#personalfinance"],
    "authorized_user_strategy": ["#creditscore", "#creditbuilding", "#financetips"],
    # extend per topic; falls back to a generic pool below if missing
}
GENERIC_HASHTAGS = ["#creditscore", "#moneytok", "#financetips", "#creditrepair"]

CTA_LINES = [
    "Follow for more real credit stories.",
    "What would you have done differently? Comment below.",
    "Save this for when you need it.",
]


def oldest_ready_record():
    ready = []
    for path in PENDING_DIR.glob("*.json"):
        record = json.loads(path.read_text())
        if record["status"] == "video_ready":
            ready.append((path, record))
    if not ready:
        return None, None
    ready.sort(key=lambda pr: pr[1]["created_at"])
    return ready[0]


def build_caption(record):
    hashtags = HASHTAG_POOLS.get(record["topic"], GENERIC_HASHTAGS)
    cta = random.choice(CTA_LINES)
    topic_readable = record["topic"].replace("_", " ")
    return f"{cta} {' '.join(hashtags)} #{topic_readable.replace(' ', '')}"


def post_video(record):
    caption = build_caption(record)
    headers = {
        "Authorization": f"Bearer {TIKTOK_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    # Simplified request body — TikTok's actual Content Posting API expects
    # a two-step init/upload flow (init returns an upload URL, then you PUT
    # the video bytes to it). See README for the full flow + docs link.
    init_payload = {
        "post_info": {
            "title": caption,
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "brand_content_toggle": False,
            "brand_organic_toggle": False,
            "is_aigc": True,  # mandatory AI-disclosure flag
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": os.path.getsize(record["final_video_path"]),
        },
    }
    resp = requests.post(POST_URL, headers=headers, json=init_payload, timeout=30)
    resp.raise_for_status()
    init_data = resp.json()

    upload_url = init_data["data"]["upload_url"]
    with open(record["final_video_path"], "rb") as f:
        video_bytes = f.read()
    put_resp = requests.put(
        upload_url,
        headers={"Content-Type": "video/mp4"},
        data=video_bytes,
        timeout=120,
    )
    put_resp.raise_for_status()
    return init_data["data"]["publish_id"]


def main():
    path, record = oldest_ready_record()
    if record is None:
        print("No videos ready to post.")
        return

    publish_id = post_video(record)
    record["status"] = "posted"
    record["publish_id"] = publish_id

    POSTED_DIR.mkdir(parents=True, exist_ok=True)
    dest = POSTED_DIR / path.name
    path.write_text(json.dumps(record, indent=2))
    shutil.move(str(path), str(dest))

    # also move the media files so pending/ doesn't accumulate
    for suffix in ("_voiceover.mp3", "_final.mp4"):
        src = PENDING_DIR / f"{record['video_id']}{suffix}"
        if src.exists():
            shutil.move(str(src), str(POSTED_DIR / src.name))

    print(f"Posted video_id={record['video_id']} publish_id={publish_id}")


if __name__ == "__main__":
    main()
