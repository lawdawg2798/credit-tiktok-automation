"""
generate_script.py

Picks a random script structure + topic (weighted so recently-used
combos are less likely to repeat), then calls an LLM to write the
actual script text. Outputs a JSON file per video into content/pending/.

Run:  python scripts/generate_script.py --count 7
"""
import argparse
import json
import os
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
import anthropic  # pip install anthropic

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "variation.yaml"
PENDING_DIR = ROOT / "content" / "pending"
HISTORY_PATH = ROOT / "config" / "recent_history.json"

STRUCTURE_PROMPTS = {
    "hook": "A 1-2 sentence hook with a specific shocking number or claim.",
    "setup": "2-3 sentences establishing who the person is and their situation.",
    "mistake": "2-4 sentences on the specific decision/mistake, with concrete numbers.",
    "fix": "3-5 sentences on exactly what they did to fix it, step by step.",
    "result": "1-2 sentences on the outcome, with a number and timeframe.",
    "result_teaser": "1 sentence teasing the end result before explaining how.",
    "flashback_setup": "2-3 sentences setting the scene before the result.",
    "lesson": "1-2 sentence clear takeaway.",
    "three_things_learned": "Three short numbered lessons, punchy, 1 sentence each.",
    "advice": "1-2 sentences of direct, concrete advice.",
    "one_line_story_proof": "One sentence of real-feeling anecdotal proof.",
    "cta": "One short soft call-to-action line (follow / comment), no hard sell.",
}


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_history():
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text())
    return {"recent_topics": [], "recent_structures": [], "recent_voices": []}


def save_history(history):
    # keep last 10 of each so we avoid immediate repeats without exhausting the pool
    for k in history:
        history[k] = history[k][-10:]
    HISTORY_PATH.write_text(json.dumps(history, indent=2))


def weighted_choice(options, recent, key=lambda x: x):
    """Down-weight recently used options instead of hard-excluding them."""
    weights = [0.2 if key(o) in recent else 1.0 for o in options]
    return random.choices(options, weights=weights, k=1)[0]


def build_prompt(topic, structure):
    beats = "\n".join(
        f"- {beat.upper()}: {STRUCTURE_PROMPTS[beat]}" for beat in structure["order"]
    )
    return f"""Write a short-form vertical video script about: {topic.replace('_', ' ')}.

This is a real-feeling first-person credit story (can be a composite/illustrative
scenario — do not claim it is a specific real named person). Follow this exact
beat order and label each beat clearly on its own line as "BEAT_NAME: text":

{beats}

Rules:
- Total spoken script should read aloud in 55-95 seconds (roughly 140-220 words).
- Concrete numbers only (scores, dollar amounts, months/years) — no vague claims.
- No guaranteed outcomes ("guaranteed to raise your score") — describe what
  happened, don't promise results to the viewer.
- Conversational spoken tone, short sentences, no hashtags in the script itself.
"""


def call_llm(prompt):
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in resp.content if block.type == "text")


def parse_beats(raw_text, structure):
    beats = {}
    current_key = None
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        matched = False
        for beat in structure["order"]:
            prefix = f"{beat.upper()}:"
            if line.upper().startswith(prefix):
                current_key = beat
                beats[current_key] = line[len(prefix):].strip()
                matched = True
                break
        if not matched and current_key:
            beats[current_key] += " " + line
    return beats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=7)
    args = parser.parse_args()

    config = load_config()
    history = load_history()
    PENDING_DIR.mkdir(parents=True, exist_ok=True)

    for i in range(args.count):
        topic = weighted_choice(config["topics"], history["recent_topics"])
        structure = weighted_choice(
            config["script_structures"], history["recent_structures"], key=lambda s: s["id"]
        )
        voice = weighted_choice(
            config["voice_profiles"], history["recent_voices"], key=lambda v: v["name"]
        )
        caption_style = random.choice(config["caption_styles"])
        background = random.choice(config["background_pools"])
        music = random.choice(config["music_pools"])
        target_len = random.choice(config["video_length_targets_seconds"])

        prompt = build_prompt(topic, structure)
        raw_text = call_llm(prompt)
        beats = parse_beats(raw_text, structure)

        video_id = str(uuid.uuid4())[:8]
        record = {
            "video_id": video_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "topic": topic,
            "structure_id": structure["id"],
            "beats": beats,
            "voice_profile": voice["name"],
            "caption_style": caption_style["id"],
            "background_category": background["category"],
            "music_category": music["category"],
            "target_length_seconds": target_len,
            "status": "script_ready",
        }

        out_path = PENDING_DIR / f"{video_id}.json"
        out_path.write_text(json.dumps(record, indent=2))
        print(f"[{i+1}/{args.count}] wrote {out_path.name} (topic={topic}, structure={structure['id']})")

        history["recent_topics"].append(topic)
        history["recent_structures"].append(structure["id"])
        history["recent_voices"].append(voice["name"])

    save_history(history)


if __name__ == "__main__":
    main()
