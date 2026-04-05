"""Channel Manager — growth tracking, daily upload scheduling, and subreddit promotion."""

import json
import logging
import re
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("video_automation.channel_manager")

TRACKING_FILE = Path("cache/channel_stats.json")
BASE_DIR = Path(__file__).parent


def _load_stats() -> dict:
    if TRACKING_FILE.exists():
        with open(TRACKING_FILE) as f:
            return json.load(f)
    return {
        "start_date": datetime.now().isoformat(),
        "goal": 1000,
        "target_deadline": (datetime.now() + timedelta(days=7)).isoformat(),
        "videos": [],
        "daily_targets": [],
        "milestones": [],
    }


def _save_stats(stats: dict):
    TRACKING_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACKING_FILE, "w") as f:
        json.dump(stats, f, indent=2)


def record_video_upload(video_url: str, title: str, subreddit: str = ""):
    """Log a new video upload."""
    stats = _load_stats()
    video = {
        "url": video_url,
        "title": title,
        "subreddit": subreddit,
        "uploaded_at": datetime.now().isoformat(),
        "views": 0,
        "likes": 0,
        "comments": 0,
        "subs_gained": 0,
    }
    stats["videos"].append(video)

    today = datetime.now().strftime("%Y-%m-%d")
    existing_day = next((d for d in stats["daily_targets"] if d["date"] == today), None)
    if existing_day:
        existing_day["videos_uploaded"] = existing_day.get("videos_uploaded", 0) + 1
    else:
        stats["daily_targets"].append({
            "date": today,
            "target_videos": 3,
            "videos_uploaded": 1,
            "actual_subs_gained": 0,
        })

    _save_stats(stats)
    logger.info(f"Recorded video: {title} ({video_url})")


def generate_daily_schedule():
    """Print the daily upload schedule."""
    stats = _load_stats()
    start = datetime.fromisoformat(stats["start_date"])
    days = []
    subreddits = [
        ("AmItheAsshole", "Relationship drama — highest engagement"),
        ("confessions", "Emotional, personal confessions"),
        ("trueoffmychest", "Raw, emotional venting"),
        ("tifu", "Funny, relatable F-ups"),
        ("pettyrevenge", "Satisfying petty revenge"),
        ("MaliciousCompliance", "Compliance revenge stories"),
        ("prorevenge", "Epic revenge payoffs"),
        ("EntitledParents", "Parent drama stories"),
        ("LetsNotMeet", "Scary encounters"),
        ("nosleep", "Horror stories"),
    ]

    now = datetime.now()
    if now >= start + timedelta(days=7):
        print("=== WEEK COMPLETE ===")
        total = len(stats["videos"])
        print(f"Total videos uploaded: {total}")
        print(f"Goal was 1,000 subs")
        return

    remaining = 7 - (now - start).days
    print(f"=== Days Remaining: {remaining} ===")
    for i in range(min(remaining, 7)):
        day_date = (now + timedelta(days=i)).strftime("%Y-%m-%d")
        day_subs = subreddits[:3]  # Rotate subreddits
        print(f"\nDay {i+1} ({day_date}):")
        print(f"  Upload targets: 3 Shorts")
        print(f"  Times: 8:00am, 2:00pm, 8:00pm")
        print(f"  Subreddits: {day_subs[0][0]}, {day_subs[1][0]}, {day_subs[2][0]}")
        print(f"  Videos uploaded so far: {sum(1 for v in stats['videos'] if v['uploaded_at'].startswith(day_date))}")


def generate_growth_report():
    """Print a full growth report."""
    stats = _load_stats()
    total_videos = len(stats["videos"])
    total_views = sum(v.get("views", 0) for v in stats["videos"])

    start = datetime.fromisoformat(stats["start_date"])
    days_elapsed = max((datetime.now() - start).days, 1)
    daily_avg = total_views / days_elapsed

    # Estimate subs based on 3% conversion rate
    estimated_subs = int(total_views * 0.03)
    progress = (estimated_subs / 1000) * 100

    print("=" * 60)
    print(f"CHANNEL GROWTH REPORT")
    print(f"Started: {start.strftime('%Y-%m-%d')}")
    print(f"Days elapsed: {days_elapsed}/7")
    print(f"Videos uploaded: {total_videos}")
    print(f"Total views: {total_views}")
    print(f"Daily views avg: {daily_avg:.0f}")
    print(f"Estimated subs: ~{estimated_subs}")
    print(f"Progress to 1,000: {progress:.1f}%")
    print("=" * 60)

    if total_videos > 0:
        print("\nRecent Videos:")
        for v in stats["videos"][-5:]:
            print(f"  - {v['title']} ({v.get('views', '?')} views, {v.get('subs_gained', '?')} subs)")


def record_promotion_action(action_type: str, details: dict = None):
    """Record a growth/promotion action for tracking."""
    stats = _load_stats()
    today = datetime.now().strftime("%Y-%m-%d")
    key = f"promotions_{today}"
    if key not in stats:
        stats[key] = []
    entry = {
        "type": action_type,
        "details": details or {},
        "timestamp": datetime.now().isoformat(),
    }
    stats[key].append(entry)
    _save_stats(stats)


def run_growth_for_niche(subreddit: str):
    """Run daily channel growth for a subreddit niche."""
    from config import Settings
    from growth_promoter import run_daily_growth

    settings = Settings.from_env()
    settings.ensure_directories()
    result = run_daily_growth(settings, subreddit)
    record_promotion_action("daily_growth", {
        "subreddit": subreddit,
        "subscribed": result["subscribed"],
        "commented": result["commented"],
        "errors": result["errors"],
    })
    return result


def print_growth_summary():
    """Print a quick summary of today's growth actions."""
    stats = _load_stats()
    today = datetime.now().strftime("%Y-%m-%d")
    key = f"promotions_{today}"
    actions = stats.get(key, [])

    print(f"=== Growth Summary for {today} ===")
    if not actions:
        print("No growth actions today yet.")
        return

    subs = sum(
        1 for a in actions
        if a["type"] == "subscribe" or a["details"].get("subscribed", 0) > 0
    )
    comments = sum(
        a["details"].get("commented", 0) for a in actions
        if a["details"].get("commented")
    )

    print(f"Subscribes today: {sum(d.get('subscribed', 0) for d in [a['details'] for a in actions] if isinstance(d, dict))}")
    print(f"Comments today: {comments}")
    for a in actions:
        print(f"  [{a['timestamp'][:19]}] {a['type']}: {a['details']}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "growth":
        subreddit = sys.argv[2] if len(sys.argv) > 2 else None
        if subreddit:
            print(f"Running growth for r/{subreddit}...")
            result = run_growth_for_niche(subreddit)
            print(f"Result: {result}")
        else:
            from config import Settings
            settings = Settings.from_env()
            niches = settings.reddit.niches
            if niches.lower() == "all":
                from reddit_stories import ALL_NICHES
                niches_list = ALL_NICHES[:3]
            else:
                niches_list = [n.strip() for n in niches.split(",")]

            print(f"Running growth for {niches_list}")
            for niche in niches_list:
                result = run_growth_for_niche(niche)
                print(f"r/{niche}: {result}")
            print()
            print_growth_summary()
    else:
        generate_daily_schedule()
        print()
        generate_growth_report()
        print()
        print_growth_summary()
