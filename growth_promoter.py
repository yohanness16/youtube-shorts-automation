"""Channel growth promoter — search similar niche channels, subscribe, and comment."""

import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("video_automation.growth")

# Map subreddits to YouTube search keywords for finding same-niche channels
SUBREDDIT_KEYWORDS = {
    "AmItheAsshole": ["reddit AITA stories", "Am I The Asshole reddit", "reddit relationship drama shorts"],
    "confessions": ["reddit confessions stories", "reddit confession shorts", "true confessions reddit"],
    "trueoffmychest": ["reddit true off my chest stories", "reddit venting shorts", "reddit emotional stories"],
    "tifu": ["reddit TIFU stories", "TIFU reddit shorts", "funny reddit fail stories"],
    "MaliciousCompliance": ["reddit malicious compliance stories", "malicious compliance shorts", "reddit workplace revenge"],
    "pettyrevenge": ["reddit petty revenge stories", "petty revenge shorts", "satisfying revenge reddit"],
    "prorevenge": ["reddit pro revenge stories", "epic revenge reddit shorts", "pro revenge storytime"],
    "EntitledParents": ["reddit entitled parents stories", "entitled parents reddit shorts", "karen stories reddit"],
    "LetsNotMeet": ["reddit scary encounter stories", "reddit horror stories shorts", "lets not meet reddit"],
    "nosleep": ["reddit nosleep horror stories", "r nosleep stories", "reddit creepypasta shorts"],
}

# Contextual, non-spammy comment templates for engagement
ENGAGEMENT_COMMENTS = [
    "Came here from r/{subreddit} — this is one of the best ones I've seen lately! {reaction}",
    "As someone who reads r/{subreddit} daily, this story hits different. {reaction}",
    "Love seeing r/{subreddit} content on YouTube! The stories here are always wild. {reaction}",
    "This is giving me all the r/{subreddit} vibes. The drama! {reaction}",
    "r/{subreddit} never disappoints with these stories. {reaction}",
    "Saw the original on r/{subreddit} and had to see the voiceover version. {reaction}",
    "Been lurking r/{subreddit} for years and this is top-tier content. {reaction}",
    "This is why I love r/{subreddit}. Always something insane happening! {reaction}",
]

REACTIONS = {
    "AmItheAsshole": ["YTA or NTA, you gotta decide!", "The comments on the original were wild.", "Everyone deserves their turn in the judgment."],
    "confessions": ["The guilt must be real!", "Some confessions just need to be heard.", "That takes courage to share."],
    "trueoffmychest": ["What a relief to finally share that.", "We've all been there honestly.", "The internet gets it."],
    "tifu": ["Classic TIFU energy 😂.", "At least it's a good story now!", "The internet never forgets."],
    "MaliciousCompliance": ["The satisfaction of following the rules exactly.", "Best kind of workplace win.", "Technically correct is the best kind of correct."],
    "pettyrevenge": ["The pettiness is chef's kiss.", "Sweet, sweet petty vengeance.", "Satisfying on every level."],
    "prorevenge": ["The ultimate karma.", "Worth the wait for the payoff!", "That plan was flawless."],
    "EntitledParents": ["The entitlement is unreal.", "Every parent's worst nightmare!", "This is peak drama."],
    "LetsNotMeet": ["Actual nightmare fuel.", "You survived though — that's what matters.", "This gave me chills."],
    "nosleep": ["Sleep is overrated anyway.", "The atmosphere is incredible.", "I'm not opening my door tonight."],
}

DAILY_SUBSCRIBE_LIMIT = 10
DAILY_COMMENT_LIMIT = 20
REQUEST_DELAY_SECONDS = 3  # polite delay between API calls


@dataclass
class PromotionLog:
    subscribed_channels: list[dict] = field(default_factory=list)
    comments_posted: list[dict] = field(default_factory=list)
    daily_stats: dict = field(default_factory=dict)

    def get_today_subs(self) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        return len([s for s in self.subscribed_channels if s["date"] == today])

    def get_today_comments(self) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        return len([c for c in self.comments_posted if c["date"] == today])


def _load_log(cache_dir: Path = None) -> PromotionLog:
    base = cache_dir or Path("cache")
    log_file = base / "promotion_log.json"
    if log_file.exists():
        try:
            with open(log_file) as f:
                data = json.load(f)
            return PromotionLog(**data)
        except Exception:
            pass
    return PromotionLog()


def _save_log(log: PromotionLog, cache_dir: Path = None):
    base = cache_dir or Path("cache")
    base.mkdir(parents=True, exist_ok=True)
    with open(base / "promotion_log.json", "w") as f:
        json.dump(
            {
                "subscribed_channels": log.subscribed_channels,
                "comments_posted": log.comments_posted,
                "daily_stats": log.daily_stats,
            },
            f,
            indent=2,
        )


def _get_youtube_client(settings, force_ssl: bool = False):
    """Build authenticated YouTube Data API client.

    By default uses the same 'youtube' scope as the uploader.
    Set force_ssl=True when posting comments (requires
    https://www.googleapis.com/auth/youtube.force-ssl scope
    to have been granted during OAuth authorization).
    """
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    yt_conf = settings.youtube
    if not yt_conf.refresh_token:
        logger.error("YOUTUBE_REFRESH_TOKEN not set — growth actions unavailable")
        return None, None

    scopes = (
        ["https://www.googleapis.com/auth/youtube.force-ssl"]
        if force_ssl
        else ["https://www.googleapis.com/auth/youtube"]
    )

    creds = Credentials(
        token=None,
        refresh_token=yt_conf.refresh_token,
        client_id=yt_conf.client_id,
        client_secret=yt_conf.client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=scopes,
    )

    yt = build("youtube", "v3", credentials=creds)
    return yt, creds


# ---- Core actions ----


def search_similar_channels(settings, subreddit: str, max_results: int = 10) -> list[dict]:
    """Search YouTube for channels making content about this subreddit's niche.

    Returns list of {channel_id, channel_title, video_count}.
    """
    yt, _ = _get_youtube_client(settings)
    if not yt:
        return []

    keywords = SUBREDDIT_KEYWORDS.get(subreddit, [f"reddit {subreddit} stories"])
    query = random.choice(keywords)
    logger.info(f"Searching YouTube for: '{query}' (from r/{subreddit})")

    try:
        resp = yt.search().list(
            part="snippet",
            q=query,
            type="video",
            videoDefinition="high",
            order="relevance",
            maxResults=max_results,
            safeSearch="none",
            regionCode="US",
        ).execute()

        seen_channel_ids = set()
        channels = []
        for item in resp.get("items", []):
            channel_id = item["snippet"]["channelId"]
            if channel_id in seen_channel_ids:
                continue
            seen_channel_ids.add(channel_id)

            channels.append({
                "channel_id": channel_id,
                "channel_title": item["snippet"]["channelTitle"],
                "query_used": query,
            })

        logger.info(f"Found {len(channels)} unique channels for r/{subreddit}")
        return channels

    except Exception as e:
        logger.warning(f"Channel search failed: {e}")
        return []


def subscribe_to_channel(settings, channel_id: str, channel_title: str = "") -> bool:
    """Subscribe to a YouTube channel using the API."""
    yt, _ = _get_youtube_client(settings)
    if not yt:
        return False

    logger.info(f"Subscribing to {channel_title or channel_id}")
    try:
        # We need the subscriptionId which is the channel's playlist ID for uploads
        # But subscriptions.insert uses the channel ID directly
        yt.subscriptions().insert(
            part="snippet",
            body={
                "snippet": {
                    "resourceId": {
                        "kind": "youtube#channel",
                        "channelId": channel_id,
                    }
                }
            },
        ).execute()
        logger.info(f"Subscribed to channel: {channel_title or channel_id}")
        return True
    except Exception as e:
        logger.warning(f"Subscribe failed for {channel_id}: {e}")
        return False


def get_recent_shorts(settings, channel_id: str, max_results: int = 5) -> list[dict]:
    """Get recent Shorts from a channel. Returns {video_id, title}."""
    yt, _ = _get_youtube_client(settings)
    if not yt:
        return []

    try:
        resp = yt.search().list(
            part="snippet",
            channelId=channel_id,
            type="video",
            order="date",
            maxResults=max_results,
            videoDuration="short",
        ).execute()

        shorts = []
        for item in resp.get("items", []):
            shorts.append({
                "video_id": item["id"]["videoId"],
                "title": item["snippet"]["title"],
                "channel_id": channel_id,
                "channel_title": item["snippet"]["channelTitle"],
            })
        return shorts
    except Exception as e:
        logger.warning(f"Failed to get shorts from {channel_id}: {e}")
        return []


def leave_promotion_comment(settings, video_id: str, subreddit: str, channel_title: str = "") -> bool:
    """Post a contextual engagement comment that references the subreddit niche."""
    yt, creds = _get_youtube_client(settings, force_ssl=True)
    if not yt:
        return False

    # Check our own channel isn't the target (don't comment on own videos)
    try:
        channels_resp = yt.channels().list(
            part="snippet",
            mine=True,
        ).execute()
        own_channel_id = channels_resp["items"][0]["id"] if channels_resp.get("items") else ""
        if own_channel_id:
            channels_resp = yt.videos().list(
                part="snippet",
                id=video_id,
            ).execute()
            if channels_resp.get("items"):
                video_channel = channels_resp["items"][0]["snippet"]["channelId"]
                if video_channel == own_channel_id:
                    logger.info("Skipping — this is our own video")
                    return False
    except Exception:
        pass  # continue even if we can't verify ownership

    # Select a natural comment template
    template = random.choice(ENGAGEMENT_COMMENTS)
    reactions = REACTIONS.get(subreddit, ["Great content!", "Love this!", "More please!"])
    reaction = random.choice(reactions)
    comment = template.format(subreddit=subreddit, reaction=reaction)

    logger.info(f"Posting comment on {video_id}: '{comment[:60]}...'")
    try:
        yt.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {"textOriginal": comment},
                    },
                },
            },
        ).execute()
        logger.info(f"Comment posted on video {video_id}")
        return True
    except Exception as e:
        logger.warning(f"Comment failed on {video_id}: {e}")
        return False


# ---- Orchestrator ----


def run_daily_growth(settings, subreddit: str) -> dict:
    """Run the full daily growth workflow for a given subreddit.

    1. Search for similar channels in the subreddit's niche
    2. Subscribe to new channels (up to DAILY_SUBSCRIBE_LIMIT)
    3. Find recent Shorts from already-subscribed channels and comment
    4. Track all actions

    Returns summary dict with actions taken.
    """
    log = _load_log(settings.cache_dir)
    today = datetime.now().strftime("%Y-%m-%d")
    summary = {"date": today, "subreddit": subreddit, "subscribed": 0, "commented": 0, "errors": 0}

    # Step 1: Search for similar channels
    logger.info(f"=== Daily Growth — r/{subreddit} ===")
    channels = search_similar_channels(settings, subreddit, max_results=10)

    # Step 2: Subscribe to new channels (respect daily limit)
    today_subs = log.get_today_subs()
    available_slots = DAILY_SUBSCRIBE_LIMIT - today_subs

    for ch in channels:
        if available_slots <= 0:
            logger.info("Daily subscribe limit reached")
            break

        cid = ch["channel_id"]
        already = any(s["channel_id"] == cid for s in log.subscribed_channels)
        if already:
            continue

        success = subscribe_to_channel(settings, cid, ch["channel_title"])
        if success:
            log.subscribed_channels.append({
                "channel_id": cid,
                "channel_title": ch["channel_title"],
                "subreddit": subreddit,
                "date": today,
                "subscribed_at": datetime.now().isoformat(),
            })
            summary["subscribed"] += 1
            available_slots -= 1
        else:
            summary["errors"] += 1

        time.sleep(REQUEST_DELAY_SECONDS)

    # Step 3: Comment on recent Shorts from subscribed channels
    today_comments = log.get_today_comments()
    available_comment_slots = DAILY_COMMENT_LIMIT - today_comments

    subscribed_for_sub = [s for s in log.subscribed_channels if s["subreddit"] == subreddit]

    for sub_record in subscribed_for_sub:
        if available_comment_slots <= 0:
            break

        shorts = get_recent_shorts(settings, sub_record["channel_id"], max_results=3)
        for short in shorts:
            if available_comment_slots <= 0:
                break

            vid = short["video_id"]
            already_commented = any(
                c["video_id"] == vid for c in log.comments_posted
            )
            if already_commented:
                continue

            success = leave_promotion_comment(
                settings, vid, subreddit, sub_record["channel_title"]
            )
            if success:
                log.comments_posted.append({
                    "video_id": vid,
                    "video_title": short["title"],
                    "channel_id": sub_record["channel_id"],
                    "channel_title": sub_record["channel_title"],
                    "subreddit": subreddit,
                    "date": today,
                    "commented_at": datetime.now().isoformat(),
                })
                summary["commented"] += 1
                available_comment_slots -= 1

            time.sleep(REQUEST_DELAY_SECONDS)

    # Update daily stats
    log.daily_stats[today] = {
        "subreddit": subreddit,
        "new_subscribes": summary["subscribed"],
        "new_comments": summary["commented"],
        "errors": summary["errors"],
        "total_subscribed": len(log.subscribed_channels),
        "total_comments": len(log.comments_posted),
    }

    _save_log(log, settings.cache_dir)

    logger.info(f"Growth complete: {summary['subscribed']} subs, {summary['commented']} comments, {summary['errors']} errors")
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    from config import Settings
    settings = Settings.from_env()
    settings.ensure_directories()

    print("Running daily channel growth...")
    # Use config niches or default
    niches = settings.reddit.niches
    if niches.lower() == "all":
        from reddit_stories import ALL_NICHES
        niches_list = ALL_NICHES[:5]
    else:
        niches_list = [n.strip() for n in niches.split(",")]

    for niche in niches_list:
        result = run_daily_growth(settings, niche)
        print(f"r/{niche}: {result}")
        time.sleep(5)
