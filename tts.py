"""
tts.py

Calls ElevenLabs' with-timestamps endpoint directly. This returns the
voiceover audio AND exact per-character timing, so captions can be built
from real speech timing instead of an estimate (which drifts on longer
scripts). No Creatomate involved.

Run:  python tts.py
"""
import base64
import json
import os
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "variation.yaml"
PENDING_DIR = ROOT / "content_pending"

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
    return " ".join(str(v).strip() for v in record["beats"].values() if str(v).strip())


def synthesize_with_timestamps(text, voice):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice['provider_id']}/with-timestamps"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": voice["stability"],
            "similarity_boost": 0.75,
            "style": voice["style"],
        },
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(f"ElevenLabs TTS failed ({resp.status_code}): {resp.text}")
    return resp.json()


def main():
    config = load_config()
    if not PENDING_DIR.exists():
        print(f"No pending directory yet ({PENDING_DIR}); nothing to voice.")
        return

    for path in sorted(PENDING_DIR.glob("*.json")):
        record = json.loads(path.read_text())
        if record.get("status") != "script_ready":
            continue

        voice = voice_by_name(config, record["voice_profile"])
        text = narration_text(record)
        print(f"Synthesizing {record['video_id']} with voice={voice['name']}...")

        result = synthesize_with_timestamps(text, voice)

        audio_bytes = base64.b64decode(result["audio_base64"])
        audio_path = PENDING_DIR / f"{record['video_id']}_voiceover.mp3"
        audio_path.write_bytes(audio_bytes)

        alignment = result.get("alignment") or result.get("normalized_alignment")
        alignment_path = PENDING_DIR / f"{record['video_id']}_alignment.json"
        alignment_path.write_text(json.dumps(alignment))

        record["status"] = "voiceover_ready"
        record["audio_path"] = str(audio_path)
        record["alignment_path"] = str(alignment_path)
        path.write_text(json.dumps(record, indent=2))
        print(f"  voiceover ready: {audio_path.name} ({len(audio_bytes)} bytes, with timestamps)")


if __name__ == "__main__":
    main()
