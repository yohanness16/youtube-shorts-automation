# YouTube Shorts Automation — Reddit Stories

Fully autonomous Python pipeline that generates viral Reddit Stories Shorts with background gameplay, emotional voiceovers, dynamic subtitles, and background music.

## Channel Growth Plan: 0 → 1K Subs in 7 Days

### Strategy: Quality + Volume + Engagement

**Week 1: Launch Phase**

#### Daily Production Target
- **3 Shorts/day** (morning 8am, afternoon 2pm, evening 8pm EST)
- 21 Shorts total for the week
- Each Short: 50-58 seconds, high-retention storytelling

#### Content Mix
| Day | Primary Subreddit | Secondary | Goal |
|-----|-------------------|-----------|------|
| 1-2 | AmItheAsshole | confessions | Hook with drama/identity |
| 3-4 | pettyrevenge | MaliciousCompliance | Satisfying payoffs |
| 5 | tifu | trueoffmychest | Relatable humor |
| 6-7 | prorevenge | confessions | Strong finish |

#### Growth Tactics Implemented
1. **Sub-to-Sub Strategy** — Subscribe to 50 Reddit story channels daily in 15-minute bursts
   - Channels with 100-5K subs (they sub back fastest)
   - Like their 2 most recent videos
   - Leave genuine comments (not "sub4sub")
2. **Comment Engagement** — Auto-post engaging question on every Short
   - Pin the comment to drive reply rate
   - Reply to EVERY comment within 1 hour
3. **Cross-Promotion** — Post Shorts to r/YouTube_STARTUP for feedback
4. **Optimized Metadata** — Subreddit-specific tags + trending hashtags in description
5. **Consistent Branding** — Same voice styles, subtitle format, music mood

#### Realistic Projections
| Metric | Target |
|--------|--------|
| Videos in Week 1 | 21 |
| Avg Views/Video | 500-2,000 (new channel) |
| Total Views | 10K-40K |
| Sub Conversion | 2-5% |
| Sub Goal | 1,000 |

### How to Run

```bash
# Generate and upload one Short
python generate_short.py

# Generate one Short (no upload — saves to file)
python generate_short.py  # upload happens if credentials configured
```

## What Each Short Does

1. **Picks the best story** — scrapes 9 subreddits, picks highest upvoted
2. **Builds script** — LLM adapts story into 12 timed segments
3. **Generates voiceover** — Edge TTS with emotional subreddit-matched voice
4. **Selects background video** — from your `bg_Video/` folder
5. **Selects background music** — mood-matched from your `bgMusic/` folder (audible at 20% mix level)
6. **Cuts clips** — 12 segments cut from background video
7. **Generates subtitles** — 64px centered, animated pop-in effect
8. **Assembles** — ffmpeg combines video + voice + music + subtitles
9. **Uploads** — YouTube with subreddit-specific tags + SEO description

## File Reference

| File | Purpose |
|------|---------|
| `generate_short.py` | Single Short generator + uploader |
| `reddit_stories.py` | Reddit scraper + AI story generation |
| `background_video.py` | Background video from local folder |
| `subtitles.py` | SRT → ASS (centered, animated, 64px) |
| `editor.py` | ffmpeg assembly (bg music at 20% volume) |
| `youtube_uploader.py` | Upload with tags + engaging comment |
| `config.py` | Settings from `.env` |

## Configuration

```ini
REDDIT_NICHES=AmItheAsshole,confessions,trueoffmychest,tifu,MaliciousCompliance,pettyrevenge,prorevenge,LetsNotMeet,nosleep
BACKGROUND_VIDEO_SOURCE=local
BACKGROUND_VIDEO_FOLDER=./bg_Video
YOUTUBE_PRIVACY_STATUS=public
```

## Requirements

- **Python 3.10+**
- **ffmpeg** (system binary)
- **yt-dlp** (for download fallback)
- **Edge TTS** (free voiceover, no API key)
- OpenRouter API key (for LLM scripts)
- YouTube OAuth credentials (for upload)
