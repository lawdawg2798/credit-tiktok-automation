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
    # Openers / hooks -- must drop straight into the stakes, zero backstory.
    "hook": "The single most dramatic line or core question of the story, 1-2 sentences. Start mid-stakes (e.g. 'I found out my roommate had been reading my texts for a year') -- NEVER 'so this happened when...' or any throat-clearing. This is the line that stops someone scrolling.",
    "ending_teaser": "1 sentence teasing the wildest outcome, phrased so it raises a question the story then answers.",
    "result_teaser": "1 sentence teasing the payoff as a question or cliffhanger, not a flat statement.",
    # Setup / context -- kept minimal, info is revealed gradually, not dumped.
    "setup": "1-2 SHORT sentences establishing who's involved. Bare minimum context -- do not explain everything up front.",
    "backstory": "1-2 short sentences of just-enough context. Hold back a detail for later if it helps the twist land.",
    "normal_life": "1-2 short sentences showing things seemed fine -- plant a small detail that matters later.",
    "flashback_setup": "1-2 short sentences setting the scene, withholding the outcome.",
    # Rising action -- reveal new info steadily, plant a question early.
    "incident": "2-3 short, punchy sentences on the specific thing that kicked it off. End this beat on a detail that raises a new question.",
    "first_red_flag": "1-2 short sentences on the first sign something was wrong -- understated, let the viewer feel it before it's spelled out.",
    "the_wrong": "1-2 short sentences on how someone got wronged/crossed a line. Concrete detail, no summarizing.",
    "the_plan": "1-2 short sentences on the plan that formed -- tease it without giving away how it plays out.",
    # Escalation / turns
    "escalation": "2-3 short sentences where it gets worse or takes a turn. One new piece of information at a time.",
    "the_reveal": "1-2 sentences delivering the twist directly -- no hedging, let it land hard.",
    "the_execution": "2-3 short, vivid sentences on how the payback/plan went down. Specific sensory detail over summary.",
    # Payoff / resolution -- must include the actual payoff AND an engagement hook.
    "payoff": "2-3 sentences delivering the satisfying or shocking result, ending on the sharpest possible detail.",
    "the_satisfaction": "1-2 sentences on the satisfying aftermath, then 1 sentence that turns to the audience (a direct question, a tease of what happened next, or an open question about what they'd have done).",
    "resolution": "1-2 sentences wrapping up how it ended, then 1 sentence turning to the audience the same way.",
    "aftermath": "1-2 sentences on what happened after, then 1 sentence turning to the audience the same way.",
    # Close
    "cta": "One short line that is BOTH a natural call-to-action and an engagement hook -- a direct question to the viewer ('what would you have done?'), a comment prompt, or a 'part 2 in the comments if you want it' tease. Never a flat 'follow for more' with nothing else.",
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
style TikTok/Reels. The story theme is: {theme}.

Write it as a gripping, first-person dramatic story in the voice of an
ordinary person retelling something that happened to them. It should feel
like a real Reddit post being read aloud -- specific, vivid, emotionally
charged. Invent a plausible, self-contained story (it is fictional/
illustrative -- do not use real named public figures or claim it is a
specific real person).

RETENTION RULES (these matter more than anything else):
- Open with the single most dramatic line or the core question of the story.
  Do NOT start with backstory or setup ("So this happened when I was...").
  Drop straight into the stakes.
- Reveal new information gradually, a piece at a time, across the beats --
  never front-load all the context in the first few lines. This is what
  keeps someone watching instead of scrolling away.
- Plant a question or unresolved detail early that only gets answered near
  the end -- a genuine curiosity gap, not just suspense-for-its-own-sake.
- The ending must land BOTH a real payoff (the twist/revenge/result actually
  resolves) AND an engagement hook -- a direct question to the viewer, or a
  tease that pulls them toward commenting or wanting a part 2. Never end on
  a flat, closed statement with nothing for the viewer to react to.

Follow this exact beat order and label each beat clearly on its own line as
"BEAT_NAME: text":

{beats}

Writing style rules:
- SHORT, PUNCHY sentences. One idea per sentence. Avoid long compound
  sentences joined with "and"/"but" -- they're harder to follow with sound
  off and harder to caption cleanly.
- Punctuate deliberately. Use periods, commas, and em-dashes on purpose --
  punctuation controls the pacing of the AI voice reading this aloud, so
  place it where a natural pause should land, especially right before a
  twist or reveal.
- Cut anything that doesn't add new information or tension. If a sentence
  could be deleted without losing meaning, delete it.
- Use concrete, specific details (names for side characters are fine, places,
  amounts, timeframes) so it feels real, not generic.
- Keep it PG-13: dramatic and intense is great, but no graphic gore, explicit
  sexual content, or slurs.
- Conversational spoken tone. No hashtags or emojis in the script text itself.

Length: total spoken script should run 60-120 seconds of narration at a
natural pace of roughly 150-180 words per minute -- that's approximately
150 to 330 words depending on how much the story needs, but err toward the
tighter end unless the plot genuinely needs the room. Under 45 seconds feels
rushed; if the story is rich enough to need more than 2 minutes, tighten it
rather than let it run long.
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
