"""
tts.py

Reads each pending script JSON, joins the beats into one narration string,
and calls ElevenLabs using the voice profile already assigned to that video
(assigned back in generate_script.py so voice rotation stays consistent
with the history tracker).

Run:  python scripts/tts.py
"""
import json
import os
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "variation.yaml"
PENDING_DIR = ROOT / "content" / "pending"

ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def voice_by_name(config, name):
    for v in config["voice_profiles"]:
        if v["name"] == name:
            return v
    raise ValueError(f"voice profile {name} not found in config")


def narration_text(record):
    order = None
    # structure order isn't stored directly on the record, so just join
    # beats in insertion order (Python dicts preserve this) — good enough
    # since parse_beats already wrote them in script order.
    return " ".join(record["beats"].values())


def synthesize(text, voice):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice['provider_id']}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "voice_settings": {
            "stability": voice["stability"],
            "similarity_boost": 0.75,
            "style": voice["style"],
        },
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.content


def main():
    config = load_config()
    for path in PENDING_DIR.glob("*.json"):
        record = json.loads(path.read_text())
        if record["status"] != "script_ready":
            continue

        voice = voice_by_name(config, record["voice_profile"])
        text = narration_text(record)
        audio_bytes = synthesize(text, voice)

        audio_path = PENDING_DIR / f"{record['video_id']}_voiceover.mp3"
        audio_path.write_bytes(audio_bytes)

        record["status"] = "voiceover_ready"
        record["audio_path"] = str(audio_path)
        path.write_text(json.dumps(record, indent=2))
        print(f"voiceover ready: {audio_path.name}")


if __name__ == "__main__":
    main()
