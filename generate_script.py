"""
generate_script.py

Picks a random script structure + topic (weighted so recently-used
combos are less likely to repeat), then calls an LLM to write the
actual script text. Outputs a JSON file per video into a local
'content_pending' folder (all files live in one flat directory).

Run:  python generate_script.py --count 7
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

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "variation.yaml"
PENDING_DIR = ROOT / "content_pending"
HISTORY_PATH = ROOT / "recent_history.json"

STRUCTURE_PROMPTS = {
    # Openers / hooks
    "hook": "A punchy 1-2 sentence hook that drops the audience into the drama and makes them NEED to hear what happens. No slow warmup.",
    "ending_teaser": "1 sentence teasing the wild outcome up front, before explaining how it happened.",
    "result_teaser": "1 sentence teasing the payoff before the story.",
    # Setup / context
    "setup": "2-3 sentences establishing who's involved and the situation, fast.",
    "backstory": "2-3 sentences of just-enough context to understand the conflict.",
    "normal_life": "2 sentences showing how things seemed normal/fine at first.",
    "flashback_setup": "2-3 sentences setting the scene before the payoff.",
    # Rising action
    "incident": "2-4 sentences on the specific thing that kicked it all off.",
    "first_red_flag": "2-3 sentences on the first sign something was wrong.",
    "the_wrong": "2-3 sentences on how someone got wronged/crossed a line.",
    "the_plan": "2-3 sentences on the plan that formed in response.",
    # Escalation / turns
    "escalation": "2-4 sentences where it gets worse, more tense, or takes a turn.",
    "the_reveal": "2-3 sentences delivering the big twist or reveal.",
    "the_execution": "2-4 sentences on how the plan/payback went down, with vivid detail.",
    # Payoff / resolution
    "payoff": "2-3 sentences delivering the satisfying or shocking result.",
    "the_satisfaction": "2-3 sentences on the satisfying aftermath and how it felt.",
    "resolution": "2-3 sentences wrapping up how it ended.",
    "aftermath": "2-3 sentences on what happened after the dust settled.",
    # Close
    "cta": "One short natural call-to-action (follow for more stories / comment what you'd do). No hard sell.",
}


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_history():
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text())
    return {"recent_topics": [], "recent_structures": [], "recent_voices": []}


def save_history(history):
    for k in history:
        history[k] = history[k][-10:]
    HISTORY_PATH.write_text(json.dumps(history, indent=2))


def weighted_choice(options, recent, key=lambda x: x):
    weights = [0.2 if key(o) in recent else 1.0 for o in options]
    return random.choices(options, weights=weights, k=1)[0]


def build_prompt(topic, structure):
    beats = "\n".join(
        f"- {beat.upper()}: {STRUCTURE_PROMPTS[beat]}" for beat in structure["order"]
    )
    theme = topic.replace('_', ' ')
    return f"""Write a short-form vertical video script for a faceless "Reddit stories"
style TikTok. The story theme is: {theme}.

Write it as a gripping, first-person dramatic story in the voice of an
ordinary person retelling something that happened to them. It should feel
like a real Reddit post being read aloud -- specific, vivid, emotionally
charged, with a clear hook and a satisfying or shocking payoff. Invent a
plausible, self-contained story (it is fictional/illustrative -- do not use
real named public figures or claim it is a specific real person).

Follow this exact beat order and label each beat clearly on its own line as
"BEAT_NAME: text":

{beats}

Rules:
- Total spoken script should read aloud in 55-95 seconds (roughly 150-230 words).
- Open with a hook that creates instant curiosity -- no slow throat-clearing.
- Use concrete, specific details (names for side characters are fine, places,
  amounts, timeframes) so it feels real, not generic.
- Build tension and pay it off. The ending should land -- satisfying revenge,
  a shocking twist, or a gut-punch, depending on the theme.
- Keep it PG-13: dramatic and intense is great, but no graphic gore, explicit
  sexual content, or slurs.
- Conversational spoken tone, short punchy sentences, no hashtags or emojis in
  the script text itself.
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
