# Credit Story TikTok Automation

End-to-end pipeline: script → voiceover → assembly → scheduled posting,
built around **variation pools** so consecutive videos don't share an
identical structure, voice, background, or caption style.

## Pipeline

```
generate_script.py   -> content/pending/<id>.json           (status: script_ready)
tts.py                -> + <id>_voiceover.mp3                (status: voiceover_ready)
assemble.py           -> + <id>_final.mp4                    (status: video_ready)
post_to_tiktok.py     -> moves to content/posted/             (status: posted)
```

Runs as two GitHub Actions workflows:
- **weekly-batch.yml** — Sundays, generates a week's worth of scripts → voiceovers → videos.
- **daily-post.yml** — daily, posts the oldest ready video.

## One-time setup

1. **TikTok Content Posting API access** — apply for developer access and
   OAuth your account: https://developers.tiktok.com/doc/content-posting-api-get-started
   Store the resulting access token as the `TIKTOK_ACCESS_TOKEN` repo secret.
   (Tokens expire — you'll need a refresh step eventually; not included here.)

2. **Anthropic API key** — for script generation. Repo secret: `ANTHROPIC_API_KEY`.

3. **ElevenLabs API key** — for voiceover. Repo secret: `ELEVENLABS_API_KEY`.
   Fill in real voice IDs in `config/variation.yaml` under `voice_profiles`.

4. **Creatomate account + templates** — build one template per entry in
   `caption_styles` (3 by default) in Creatomate's visual editor, each with
   a Background layer, Voiceover audio layer, and an auto-caption layer tied
   to the audio. Put the resulting template IDs in
   `config/creatomate_templates.json`:
   ```json
   {
     "bold_yellow_bottom": "tpl_xxx",
     "clean_white_center": "tpl_yyy",
     "outline_center_top": "tpl_zzz"
   }
   ```
   Repo secret: `CREATOMATE_API_KEY`.

5. **Background footage** — populate `assets/backgrounds/<category>/` with
   your own or licensed source clips/photos, matching the `clips_dir`
   categories in `variation.yaml`. Avoid generic borrowed gameplay-loop
   footage — see note below.

6. Video/audio files are binary and will grow the repo fast — set up
   [Git LFS](https://git-lfs.com/) for `content/` and `assets/`, or swap
   the workflows to push finished files to S3/Drive instead of committing
   them, if you want this to scale past a few weeks.

## Why "variation" instead of one fixed template

Manual review is the actual lever, but if you're running this closer to
hands-off, spreading risk across the pipeline helps:

- 4 script structures × 15 topics × 3 voices × 3 caption styles × 3
  background categories × 4 length targets = thousands of distinct
  combinations before anything repeats exactly.
- Recently-used topics/structures/voices are down-weighted (not
  excluded) each generation run, so rotation happens naturally.
- `is_aigc: True` in the post payload sends TikTok's mandatory AI
  disclosure flag on every post — leaving this off risks the account's
  standing beyond just that video, per TikTok's 2026 enforcement.

None of this guarantees Creator Rewards eligibility — TikTok's
originality check evaluates the final video regardless of how it was
produced, and heavily templated AI content is explicitly what it targets.
The next real step (see "splicing in originality") is adding a manual or
semi-manual layer that a script alone can't fake: your own b-roll, a
real personalization pass per video, or a distinctive visual signature
that's actually yours.
