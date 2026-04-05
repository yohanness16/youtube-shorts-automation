# YouTube Shorts Automation — Reddit Stories

Fully autonomous Python pipeline that generates viral Reddit Stories Shorts with background gameplay, emotional voiceovers, dynamic subtitles, and background music — plus automated channel growth tools for search, subscribe, comment, and SEO.

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
1. **Sub-to-Sub Strategy** — Subscribe to 10 Reddit story channels daily (YouTube API limit)
   - Search by niche-specific queries (e.g. "Am I The Asshole reddit")
   - Deduplication — never subscribe to the same channel twice
   - Subscribe to small channels with 100-5K subs (they sub back fastest)
2. **Comment Engagement** — Auto-post contextual comments on similar-niche Shorts
   - Daily limit: 20 comments across subscribed channels
   - Uses natural, non-spammy templates with subreddit references
3. **Cross-Promotion** — Comment on other creators' videos linking to our content
   - Up to 30 cross-promo comments per day
   - Links back to our most relevant video for the niche
4. **SEO Tag Optimization** — Bulk update all video tags for discoverability
   - 15-21 niche-specific tags per video
   - Auto-detected from video description (r/subreddit matching)
   - Tags include: subreddit name, reddit keywords, voiceover, shorts, viral
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
| `channel_manager.py` | Channel scheduling + growth orchestration |
| `cli.py` | Interactive CLI entry point (mode 6 = growth) |
| `growth_promoter.py` | YouTube API — search, subscribe, comment |
| `tag_and_comment.py` | SEO tag pools + cross-promotion comments |
| `update_video_data.py` | Bulk video metadata/tag updater |
| `get_youtube_token.py` | OAuth token generation helper |
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
- YouTube OAuth credentials (for upload and growth actions)

## Channel Growth

Automated growth runs from CLI mode 6:

```bash
python cli.py
# Select mode 6
```

Or run directly:

```bash
python growth_promoter.py              # run growth for all niches
python update_video_data.py            # update tags on all videos
python get_youtube_token.py            # get new OAuth refresh token
```

Growth workflow per niche:
1. **Search** — finds channels in your subreddit's niche via YouTube API
2. **Subscribe** — subscribes to new channels (10/day limit)
3. **Comment** — comments on recent Shorts from subscribed channels (20/day limit)
4. **SEO** — updates video tags with subreddit-specific keywords
5. **Cross-promo** — comments on other niches' videos linking to our content
