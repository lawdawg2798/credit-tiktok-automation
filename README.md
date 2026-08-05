# Credit Story TikTok Automation (flat layout)

All Python scripts and config live in the repo root. Two content folders
(`content_pending/` and `content_posted/`) and an `assets_backgrounds/`
folder are created/used at runtime.

## Pipeline

```
generate_script.py   -> content_pending/<id>.json        (status: script_ready)
tts.py                -> + <id>_voiceover.mp3             (status: voiceover_ready)
assemble.py           -> + <id>_final.mp4                 (status: video_ready)
post_to_tiktok.py     -> moves to content_posted/          (status: posted)
```

Run manually, in order:
```
python generate_script.py --count 7
python tts.py
python assemble.py
python post_to_tiktok.py
```

## Environment variables / GitHub secrets

- `ANTHROPIC_API_KEY`   - script generation
- `ELEVENLABS_API_KEY`  - voiceover
- `CREATOMATE_API_KEY`  - video assembly
- `TIKTOK_ACCESS_TOKEN` - posting (only once TikTok approves the app)

## Background footage

Put your own/licensed clips in `assets_backgrounds/`, with the category name
somewhere in each filename so `assemble.py` can match it, e.g.:
`soft_ambient_b_roll_1.mp4`, `original_photos_slideshow_2.jpg`,
`subtle_motion_graphics_3.mp4`.

## Config

- `variation.yaml` - the rotation pools (topics, voices, caption styles, etc.)
- `creatomate_templates.json` - maps caption style -> Creatomate template ID

## Note on automation vs. manual

Everything through `assemble.py` works with just the three content-generation
API keys. `post_to_tiktok.py` only works once TikTok approves production
access. Until then you can run the first three steps and post the finished
MP4s in `content_pending/` manually.
