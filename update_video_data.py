"""Update video tags, descriptions, and cross-promote on other niches' videos."""

import json
import logging
import random
import re
import time
from pathlib import Path

logger = logging.getLogger("growth.update_video_data")

# Rich SEO tag pools
TAG_POOLS = {
    "AmItheAsshole": [
        "reddit stories", "reddit story", "AITA", "Am I The Asshole",
        "reddit AITA stories", "reddit relationship drama", "storytime",
        "reddit storytime", "reddit shorts", "AITA reddit", "reddit drama",
        "reddit voiceover", "reddit shorts viral", "storytime reddit",
        "reddit shorts compilation", "AITA storytime", "viral reddit stories",
        "reddit relationship advice", "reddit animated", "shorts",
    ],
    "confessions": [
        "reddit confessions", "reddit confession shorts", "confession stories",
        "true confessions", "reddit secrets", "confession reddit",
        "confession storytime", "reddit voiceover", "reddit storytime",
        "reddit shorts", "reddit shorts viral", "storytime", "shorts",
        "reddit shorts compilation", "reddit voiceover compilation",
        "storytime reddit", "reddit stories", "reddit drama",
    ],
    "trueoffmychest": [
        "reddit off my chest", "reddit venting", "reddit emotional stories",
        "true off my chest", "reddit emotional storytime", "reddit drama",
        "reddit voiceover", "reddit storytime", "reddit shorts",
        "reddit shorts viral", "storytime", "shorts", "reddit voiceover compilation",
        "storytime reddit", "reddit stories", "reddit stories compilation",
    ],
    "tifu": [
        "TIFU", "reddit TIFU stories", "TIFU reddit", "reddit fail stories",
        "funny reddit stories", "TIFU storytime", "reddit humor",
        "reddit funny shorts", "reddit voiceover", "reddit storytime",
        "reddit shorts", "reddit shorts viral", "storytime", "shorts",
        "reddit voiceover compilation", "storytime reddit", "reddit stories",
    ],
    "MaliciousCompliance": [
        "malicious compliance", "reddit malicious compliance", "workplace revenge",
        "malicious compliance reddit", "workplace stories",
        "technicality revenge", "malicious compliance storytime", "revenge story",
        "reddit voiceover", "reddit storytime", "reddit shorts",
        "reddit shorts viral", "storytime", "shorts", "reddit voiceover compilation",
        "storytime reddit", "reddit stories", "reddit compliance stories",
    ],
    "pettyrevenge": [
        "petty revenge", "petty revenge reddit", "revenge story", "reddit revenge",
        "petty revenge storytime", "satisfying revenge reddit",
        "petty revenge compilation", "petty revenge stories", "reddit voiceover",
        "reddit storytime", "reddit shorts", "reddit shorts viral",
        "storytime", "shorts", "reddit voiceover compilation", "storytime reddit",
        "reddit stories", "reddit drama",
    ],
    "prorevenge": [
        "reddit pro revenge", "epic revenge stories", "pro revenge reddit",
        "pro revenge storytime", "karma revenge", "reddit dramatic",
        "epic revenge compilation", "reddit voiceover", "reddit storytime",
        "reddit shorts", "reddit shorts viral", "storytime", "shorts",
        "reddit voiceover compilation", "storytime reddit", "reddit stories",
    ],
    "LetsNotMeet": [
        "reddit scary stories", "reddit horror stories", "lets not meet reddit",
        "creepy encounter stories", "scary storytime", "true scary stories",
        "reddit horror shorts", "creepy reddit stories", "true crime reddit",
        "reddit creepy encounter", "reddit voiceover", "reddit storytime",
        "reddit shorts", "reddit shorts viral", "storytime", "shorts",
        "reddit voiceover compilation", "storytime reddit", "reddit stories",
    ],
    "nosleep": [
        "reddit nosleep", "nosleep stories", "horror storytime",
        "scary reddit stories", "reddit horror shorts", "creepypasta reddit",
        "horror voiceover", "reddit horror stories", "nosleep reddit",
        "reddit scary shorts", "reddit voiceover", "reddit storytime",
        "reddit shorts", "reddit shorts viral", "storytime", "shorts",
        "reddit voiceover compilation", "storytime reddit", "reddit stories",
    ],
    "generic": [
        "reddit stories", "reddit storytime", "reddit voiceover",
        "storytime", "reddit drama", "reddit shorts", "reddit shorts viral",
        "reddit voiceover compilation", "reddit stories compilation",
        "reddit stories reddit", "reddit animated", "reddit narration",
        "storytime reddit", "reddit voice acting", "reddit top stories",
        "reddit best stories", "reddit trending", "reddit short stories",
        "reddit viral", "reddit shorts compilation", "shorts",
        "reddit story narration", "reddit audio stories",
        "reddit relationship stories", "reddit funny stories",
        "reddit true stories", "reddit entertaining stories",
    ],
}

# Cross-promo comment templates
PROMO_COMMENTS = [
    "I do voiceovers of r/{subreddit} stories — this one is wild! https://youtube.com/watch?v={video_id}",
    "Love r/{subreddit} content! I narrate these on my channel: https://youtube.com/watch?v={video_id}",
    "As a r/{subreddit} voiceover creator, one of my recent uploads: https://youtube.com/watch?v={video_id}",
    "r/{subreddit} hits different with a voiceover! My take: https://youtube.com/watch?v={video_id}",
    "I make r/{subreddit} shorts — check this one out: https://youtube.com/watch?v={video_id}",
    "Big r/{subreddit} fan and content creator here: https://youtube.com/watch?v={video_id}",
    "I narrate r/{subreddit} stories on my channel too! Here's mine: https://youtube.com/watch?v={video_id}",
]

DAILY_CROSS_PROMO_LIMIT = 20


def get_our_videos(settings, max_results=10):
    """Get our channel's video IDs and titles."""
    creds = _get_creds(settings, ["https://www.googleapis.com/auth/youtube"])
    yt = _build_client(settings, creds)

    ch = yt.channels().list(part="snippet", mine=True).execute()
    if not ch.get("items"):
        return []
    cid = ch["items"][0]["id"]

    resp = yt.search().list(
        part="snippet", channelId=cid, type="video",
        order="date", maxResults=max_results,
    ).execute()

    return [
        {
            "video_id": item["id"]["videoId"],
            "title": item["snippet"]["title"],
            "channel_id": cid,
        }
        for item in resp.get("items", [])
    ]


def detect_subreddit_from_description(video_data):
    """Detect the subreddit from the video description."""
    match = re.search(r"r/(\w+)", video_data.get("description", ""))
    return match.group(1) if match else "generic"


def update_video_metadata(settings, video_id: str, subreddit: str,
                          our_video_ids: list = None) -> dict:
    """Update tags and description for a video.

    Adds relevant tags to the existing set, appends our other video
    links to the description, and optimizes metadata.
    """
    creds = _get_creds(settings, ["https://www.googleapis.com/auth/youtube"])
    yt = _build_client(settings, creds)

    # Current metadata
    resp = yt.videos().list(part="snippet", id=video_id).execute()
    if not resp.get("items"):
        return {"status": "not_found"}

    snippet = resp["items"][0]["snippet"]
    current_tags = snippet.get("tags", [])
    desc = snippet.get("description", "")

    # Merge existing + new tags (dedupe)
    niche_tags = TAG_POOLS.get(subreddit, TAG_POOLS["generic"])
    all_tags = list(dict.fromkeys(current_tags + niche_tags))

    # Limit to YouTube's 500-char constraint for tags
    while len(",".join(all_tags)) > 480 and all_tags:
        all_tags.pop()

    # Build enhanced description with other video links
    new_desc = desc
    if our_video_ids:
        # Check if we already have "Also watch" links
        if "\n---" not in new_desc and "\n🎬 " not in new_desc and not re.search(r"also watch|more videos|watch next", new_desc.lower()):
            # Find other videos (not this one)
            others = [v for v in our_video_ids if v["video_id"] != video_id][:5]
            if others:
                new_desc += "\n"
                for ov in others:
                    new_desc += f"\n📺 {ov['title']}: https://youtube.com/watch?v={ov['video_id']}"

    snippet["tags"] = all_tags
    snippet["description"] = new_desc
    snippet.pop("thumbnails", None)
    snippet.pop("localized", None)

    try:
        yt.videos().update(part="snippet", body={"id": video_id, "snippet": snippet}).execute()
        return {
            "status": "updated",
            "video_id": video_id,
            "tags_added": len(all_tags),
            "tags": all_tags,
        }
    except Exception as e:
        logger.warning(f"Update failed for {video_id}: {e}")
        return {"status": "failed", "error": str(e)}


def post_cross_promo_comment(settings, target_video_id, our_video_id, subreddit):
    """Post a cross-promotion comment on a target video."""
    creds = _get_creds(settings, ["https://www.googleapis.com/auth/youtube.force-ssl"])
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=creds)

    template = random.choice(PROMO_COMMENTS)
    comment = template.format(subreddit=subreddit, video_id=our_video_id)

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
        return True
    except Exception as e:
        logger.warning(f"Cross-promo comment failed on {target_video_id}: {e}")
        return False


# ---- Internal helpers ----
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def _get_creds(settings, scopes):
    yt_conf = settings.youtube
    return Credentials(
        token=None,
        refresh_token=yt_conf.refresh_token,
        client_id=yt_conf.client_id,
        client_secret=yt_conf.client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=scopes,
    )

def _build_client(settings, creds):
    return build("youtube", "v3", credentials=creds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
