"""Tag and comment growth tool — improve video SEO and cross-promote in comments."""

import logging
import time
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import humanize

logger = logging.getLogger("growth.tag_comment")

# SEO tag pools by niche
TAG_POOL = {
    "AmItheAsshole": [
        "reddit stories", "AITA", "Am I The Asshole", "reddit AITA stories",
        "reddit relationship drama", "storytime", "reddit storytime",
        "reddit shorts", "AITA reddit", "reddit drama",
        "reddit stories compilation", "AITA storytime",
        "reddit voiceover", "reddit animated", "reddit shorts compilation",
        "viral reddit stories", "reddit relationship advice",
        "shorts", "reddit shorts viral", "storytime reddit",
    ],
    "confessions": [
        "reddit confessions", "confession stories", "reddit confession shorts",
        "true confessions", "storytime", "reddit storytime", "reddit shorts",
        "reddit voiceover", "confession reddit", "reddit secrets",
        "short viral stories", "reddit shorts viral", "confession storytime",
        "reddit voiceover compilation", "storytime reddit",
    ],
    "trueoffmychest": [
        "reddit off my chest", "reddit venting", "reddit emotional stories",
        "true off my chest", "storytime", "reddit shorts", "reddit voiceover",
        "reddit emotional storytime", "reddit drama", "reddit shorts viral",
        "reddit voiceover compilation", "storytime reddit",
    ],
    "tifu": [
        "TIFU", "reddit TIFU stories", "TIFU reddit", "reddit fail stories",
        "funny reddit stories", "storytime", "reddit shorts", "reddit voiceover",
        "TIFU storytime", "reddit humor", "reddit funny shorts",
        "reddit shorts viral", "reddit voiceover compilation", "storytime reddit",
    ],
    "MaliciousCompliance": [
        "malicious compliance", "reddit malicious compliance", "revenge story",
        "workplace revenge", "malicious compliance reddit", "storytime",
        "reddit shorts", "reddit voiceover", "workplace stories",
        "reddit compliance stories", "technicality revenge",
        "malicious compliance storytime", "reddit shorts viral",
        "reddit voiceover compilation", "storytime reddit",
    ],
    "pettyrevenge": [
        "petty revenge", "petty revenge reddit", "revenge story", "reddit revenge",
        "petty revenge storytime", "storytime", "reddit shorts", "reddit voiceover",
        "satisfying revenge reddit", "reddit drama", "petty revenge compilation",
        "reddit shorts viral", "reddit voiceover compilation", "storytime reddit",
    ],
    "prorevenge": [
        "reddit pro revenge", "epic revenge stories", "pro revenge reddit",
        "revenge story", "reddit revenge shorts", "storytime", "reddit shorts",
        "reddit voiceover", "pro revenge storytime", "karma revenge",
        "reddit shorts viral", "reddit voiceover compilation", "storytime reddit",
        "reddit dramatic", "epic revenge compilation",
    ],
    "LetsNotMeet": [
        "reddit scary stories", "reddit horror stories", "lets not meet reddit",
        "creepy encounter stories", "scary storytime", "reddit shorts",
        "reddit voiceover", "true scary stories", "reddit horror shorts",
        "creepy reddit stories", "reddit shorts viral",
        "reddit voiceover compilation", "storytime reddit",
        "true crime reddit", "reddit creepy encounter",
    ],
    "EntitledParents": [
        "reddit entitled parents", "entitled parents reddit", "reddit drama",
        "karen stories", "entitled mom stories", "storytime", "reddit shorts",
        "reddit voiceover", "entitled people reddit", "reddit entitled drama",
        "reddit shorts viral", "reddit voiceover compilation", "storytime reddit",
    ],
    "nosleep": [
        "reddit nosleep", "nosleep stories", "horror storytime",
        "scary reddit stories", "reddit horror shorts", "reddit shorts",
        "reddit voiceover", "creepypasta reddit", "horror voiceover",
        "reddit horror stories", "reddit scary shorts", "nosleep reddit",
        "reddit shorts viral", "reddit voiceover compilation", "storytime reddit",
    ],
    "generic": [
        "reddit stories", "reddit storytime", "reddit shorts", "reddit voiceover",
        "storytime", "reddit drama", "reddit shorts compilation",
        "reddit stories compilation", "reddit voiceover compilation",
        "reddit voiceover story", "viral reddit stories",
        "shorts", "reddit shorts viral", "reddit animated stories",
        "reddit narration", "storytime reddit", "reddit voice acting",
        "reddit top stories", "reddit best stories", "reddit trending",
    ],
}

# Comment templates with video link placeholders
PROMO_COMMENTS = [
    "I do voiceovers of r/{subreddit} stories — this one got me! Check this out: https://youtube.com/watch?v={video_id}",
    "Love r/{subreddit} content! I narrate these on my channel: https://youtube.com/watch?v={video_id}",
    "As a r/{subreddit} voiceover creator, this is one of my favorites: https://youtube.com/watch?v={video_id}",
    "r/{subreddit} hits different with a voiceover! My take: https://youtube.com/watch?v={video_id}",
    "I make r/{subreddit} shorts — this one's wild: https://youtube.com/watch?v={video_id}",
]

DAILY_CROSS_PROMO_LIMIT = 30  # comments per day with our video link


@dataclass
class PromoLog:
    commented_on: list[dict] = field(default_factory=list)


def _load_promo_log(cache_dir: Path = None) -> PromoLog:
    base = cache_dir or Path("cache")
    log_file = base / "promo_log.json"
    if log_file.exists():
        try:
            with open(log_file) as f:
                return PromoLog(**json.load(f))
        except Exception:
            pass
    return PromoLog()


def _save_promo_log(log: PromoLog, cache_dir: Path = None):
    base = cache_dir or Path("cache")
    base.mkdir(parents=True, exist_ok=True)
    with open(base / "promo_log.json", "w") as f:
        json.dump({"commented_on": log.commented_on}, f, indent=2)


def get_our_videos(settings, max_results: int = 10) -> list[dict]:
    """Get our channel's video IDs and titles."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    yt_conf = settings.youtube
    creds = Credentials(
        token=None,
        refresh_token=yt_conf.refresh_token,
        client_id=yt_conf.client_id,
        client_secret=yt_conf.client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube"],
    )
    yt = build("youtube", "v3", credentials=creds)

    ch = yt.channels().list(part="snippet", mine=True).execute()
    if not ch.get("items"):
        return []

    channel_id = ch["items"][0]["id"]
    resp = yt.search().list(
        part="snippet",
        channelId=channel_id,
        type="video",
        order="date",
        maxResults=max_results,
    ).execute()

    return [
        {"video_id": item["id"]["videoId"], "title": item["snippet"]["title"]}
        for item in resp.get("items", [])
    ]


def update_video_tags(settings, video_id: str, subreddit: str) -> bool:
    """Update a video's tags to maximize SEO reach."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    yt_conf = settings.youtube
    creds = Credentials(
        token=None,
        refresh_token=yt_conf.refresh_token,
        client_id=yt_conf.client_id,
        client_secret=yt_conf.client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube"],
    )
    yt = build("youtube", "v3", credentials=creds)

    # Get current metadata
    resp = yt.videos().list(part="snippet", id=video_id).execute()
    if not resp.get("items"):
        logger.warning(f"Video {video_id} not found")
        return False

    snippet = resp["items"][0]["snippet"]

    # Build new tags: niche-specific + generic + subreddit-specific
    niche_tags = TAG_POOL.get(subreddit, TAG_POOL["generic"])
    generic_tags = TAG_POOL["generic"]
    all_tags = niche_tags + generic_tags

    # Extract unique words from title for additional tags
    title_words = [w.lower().strip(".,!?") for w in snippet["title"].split()]
    title_tags = [f"reddit {w}" for w in title_words if len(w) > 3][:3]

    # Combine and dedupe, limit to 500 chars (YouTube limit is 500 chars total)
    final_tags = list(dict.fromkeys(title_tags + all_tags))
    while len(",".join(final_tags)) > 480 and final_tags:
        final_tags.pop()

    logger.info(f"Updating tags for {video_id}: {final_tags}")

    # Update with full snippet + new tags
    snippet["tags"] = final_tags
    snippet.pop("thumbnails", None)  # can't update thumbnails via API

    try:
        yt.videos().update(
            part="snippet",
            body={
                "id": video_id,
                "snippet": snippet,
            },
        ).execute()
        logger.info(f"Tags updated for {video_id}")
        return True
    except Exception as e:
        logger.warning(f"Tag update failed for {video_id}: {e}")
        return False


def post_cross_promo_comment(
    settings, target_video_id: str, our_video_id: str, subreddit: str
) -> bool:
    """Post a comment on someone else's video promoting our video."""
    from growth_promoter import leave_promotion_comment

    yt, creds = _get_youtube_client_for_comments(settings)
    if not yt:
        return False

    try:
        channels_resp = yt.channels().list(part="snippet", mine=True).execute()
        own_channel_id = channels_resp["items"][0]["id"] if channels_resp.get("items") else ""
        if own_channel_id:
            videos_resp = yt.videos().list(part="snippet", id=target_video_id).execute()
            if videos_resp.get("items"):
                video_channel = videos_resp["items"][0]["snippet"]["channelId"]
                if video_channel == own_channel_id:
                    logger.info("Skipping — this is our own video")
                    return False
    except Exception:
        pass

    template = random.choice(PROMO_COMMENTS)
    comment = template.format(subreddit=subreddit, video_id=our_video_id)
    logger.info(f"Posting cross-promo comment on {target_video_id}: '{comment[:60]}...'")

    try:
        yt.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": target_video_id,
                    "topLevelComment": {
                        "snippet": {"textOriginal": comment},
                    },
                },
            },
        ).execute()
        logger.info(f"Cross-promo comment posted on {target_video_id}")
        return True
    except Exception as e:
        logger.warning(f"Cross-promo comment failed on {target_video_id}: {e}")
        return False


def _get_youtube_client_for_comments(settings):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    yt_conf = settings.youtube
    if not yt_conf.refresh_token:
        return None, None

    creds = Credentials(
        token=None,
        refresh_token=yt_conf.refresh_token,
        client_id=yt_conf.client_id,
        client_secret=yt_conf.client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
    )
    yt = build("youtube", "v3", credentials=creds)
    return yt, creds


def run_tag_update(settings, video_subreddit_map: dict) -> list:
    """Update tags on all our videos.

    Args:
        video_subreddit_map: dict of video_id -> subreddit e.g. {"abc123": "pettyrevenge"}
    """
    results = {}
    for vid, sub in video_subreddit_map.items():
        success = update_video_tags(settings, vid, sub)
        results[vid] = "updated" if success else "failed"
        time.sleep(2)
    return results


def run_cross_promotion(settings, subreddit: str, our_video_id: str) -> dict:
    """Cross-promote our video on other channels in the same niche."""
    from growth_promoter import search_similar_channels, get_recent_shorts

    summary = {"subreddit": subreddit, "our_video": our_video_id, "posted": 0, "ignored": 0}

    channels = search_similar_channels(settings, subreddit, max_results=10)
    for ch in channels:
        if summary["posted"] >= DAILY_CROSS_PROMO_LIMIT:
            break

        shorts = get_recent_shorts(settings, ch["channel_id"], max_results=3)
        for short in shorts:
            if summary["posted"] >= DAILY_CROSS_PROMO_LIMIT:
                break

            success = post_cross_promo_comment(
                settings, short["video_id"], our_video_id, sub
            )
            if success:
                summary["posted"] += 1
            else:
                summary["ignored"] += 1

            time.sleep(3)
    return summary


import json

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    from config import Settings
    settings = Settings.from_env()

    our_videos = get_our_videos(settings)
    print(f"\nOur videos ({len(our_videos)}):")
    for v in our_videos:
        print(f"  {v['video_id']} | {v['title']}")
