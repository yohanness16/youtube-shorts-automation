# YouTube Shorts Automation

Fully autonomous Python pipeline that researches, scripts, generates, edits, and uploads YouTube Shorts — running 24/7 on its own.

## What It Does

1. **Researches topics** in your niche using an LLM (Qwen, DeepSeek, OpenRouter, or any OpenAI-compatible API)
2. **Generates a script** — coherent 12-segment narrative with voiceover text and visual prompts for each clip
3. **Creates voiceover** via ElevenLabs or OpenAI TTS (per-segment, so subtitles are accurately timed)
4. **Generates 12 AI video clips** via your chosen video API (Luma, Runway, Pika) — or uses mock mode for testing
5. **Assembles everything** with ffmpeg: joins clips, overlays voiceover, adds styled subtitles, mixes background music
6. **Uploads to YouTube** via the YouTube Data API v3

Runs in an infinite loop — generate a video, sleep, repeat.

## Quick Start

```bash
# 1. Set up environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Add your API keys
cp .env.example .env
nano .env  # fill in your keys

# 3. Verify ffmpeg is installed
which ffmpeg  # required

# 4. Run once (manual test)
python main.py
```

## Configuration

Copy `.env.example` to `.env` and fill in the values:

```ini
# === Script LLM (Qwen, DeepSeek, OpenRouter, etc.) ===
SCRIPT_PROVIDER=qwen
SCRIPT_API_KEY=your-key
SCRIPT_MODEL=qwen-plus
SCRIPT_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# === Voiceover ===
VOICE_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=your-key
ELEVENLABS_VOICE_ID=EXAVITQu4vr4xnSDxMaL

# === Video Generation ===
VIDEO_PROVIDER=mock          # mock | luma | runway | pika
VIDEO_API_KEY=your-key       # not needed for mock

# === YouTube ===
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
YOUTUBE_REFRESH_TOKEN=...
YOUTUBE_PRIVACY_STATUS=private  # review before going public

# === Settings ===
NICHE=history-facts
CLIPS_PER_VIDEO=12
POLL_INTERVAL_SECONDS=600  # time between runs
```

## Architecture

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────────┐
│ Idea         │────>│ Script          │────>│ Audio (TTS)      │
│ Generator    │     │ Generator       │     │ Generator        │
└──────────────┘     └─────────────────┘     └──────┬───────────┘
                                                     │
┌──────────────┐     ┌─────────────────┐     ┌──────▼───────────┐
│ YouTube      │<────│ Video Editor    │<────│ Video Clip       │
│ Uploader     │     │ (ffmpeg)        │     │ Generator        │
└──────────────┘     └─────────────────┘     └──────────────────┘
                           │
                     ┌─────▼────────┐
                     │ Subtitles    │
                     │ Generator    │
                     └──────────────┘
```

| File | Purpose |
|------|---------|
| `main.py` | Orchestrator — runs the full pipeline in a loop |
| `config.py` | Settings, API key loading, validation |
| `idea_generator.py` | Researches trending topics via LLM |
| `script_generator.py` | Generates 12-segment script + visual prompts |
| `audio_generator.py` | ElevenLabs or OpenAI TTS voiceover |
| `video_generator.py` | AI video generation (Mock/Luma/Runway/Pika) |
| `subtitles.py` | SRT → ASS generation from per-segment timing |
| `editor.py` | ffmpeg assembly: clips + audio + subtitles + music |
| `music_generator.py` | Synth background music via ffmpeg |
| `youtube_uploader.py` | YouTube Data API v3 upload |
| `utils.py` | Logging, retry decorator, ffmpeg helpers |

## Requirements

- **Python 3.10+**
- **ffmpeg** (system binary) — [install guide](https://ffmpeg.org/download.html)
- API keys for your chosen providers

## Running

```bash
# Continuous loop (Ctrl+C to stop gracefully)
source .venv/bin/activate
python main.py

# YouTube OAuth setup (one time)
python scripts/get_youtube_token.py
```

## Directory Structure

```
output/          # Current build workspace
  clips/         # Generated clip files
  audio/         # Voiceover segments + full mix
  subs/          # Subtitle files
  draft.mp4      # Assembled video
cache/           # Cached ideas, pipeline state
completed/       # Archived successful runs
failed/          # Failed runs with error logs
logs/            # Pipeline log files
```

## Adding a Real Video Provider

The code ships with **MockProvider** (colored frames) for zero-cost testing. To use a real AI video API:

1. Pick a provider and get an API key
2. Update `.env`:
   ```ini
   VIDEO_PROVIDER=luma
   VIDEO_API_KEY=your-key
   VIDEO_BASE_URL=https://api.lumalabs.ai/dream-machine/v1
   ```
3. If the provider isn't the built-in `luma`, add a new class in `video_generator.py` implementing the `VideoProvider.generate_clip()` interface.
