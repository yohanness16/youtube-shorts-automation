"""YouTube Data API v3 uploader — OAuth2 resumable upload."""

import json
import logging
import random
from pathlib import Path

from config import YouTubeConfig

logger = logging.getLogger("video_automation.youtube")


def upload_video(settings: YouTubeConfig, video_path: Path, script_title: str) -> str:
    """Upload a video to YouTube. Returns the video URL.

    Requires OAuth2 refresh token to be set in YOUTUBE_REFRESH_TOKEN.
    The video is uploaded with the configured privacy status (default: private).
    """
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    import httpx

    if not settings.refresh_token:
        logger.error("YOUTUBE_REFRESH_TOKEN not set. Run: python scripts/get_youtube_token.py")
        raise RuntimeError("YouTube OAuth refresh token not configured")

    # Build credentials from refresh token
    creds = Credentials(
        token=None,
        refresh_token=settings.refresh_token,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube"],
    )

    youtube = build("youtube", "v3", credentials=creds)

    # Prepare metadata
    description = f"{script_title}\n\n#history #facts #education #learnontiktok"
    tags = ["history", "facts", "education", "shorts", "history facts", "did you know"]

    body = {
        "snippet": {
            "title": script_title,
            "description": description,
            "tags": tags,
            "categoryId": "27",  # Education
        },
        "status": {
            "privacyStatus": settings.privacy_status,
        },
    }

    # Resumable upload
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)

    logger.info(f"Uploading: {video_path.name} (privacy: {settings.privacy_status})")
    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info(f"Upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    video_url = f"https://youtube.com/shorts/{video_id}"
    logger.info(f"Uploaded successfully: {video_url}")
    return video_url


# ===========================================================================
# Reddit story video uploads
# ===========================================================================

REDDIT_TAGS_BY_SUB = {
    "AmItheAsshole": ["AITA", "reddit story", "reddit stories", "AITA reddit", "relationship drama", "storytime"],
    "confessions": ["reddit confession", "reddit stories", "storytime", "confession", "reddit", "story time"],
    "trueoffmychest": ["reddit story", "true off my chest", "reddit stories", "storytime", "reddit", "confession"],
    "tifu": ["TIFU", "reddit story", "tifu reddit", "funny reddit stories", "storytime", "reddit"],
    "MaliciousCompliance": ["reddit story", "malicious compliance", "reddit stories", "pro revenge", "storytime"],
    "pettyrevenge": ["reddit story", "petty revenge", "reddit stories", "revenge story", "storytime"],
    "prorevenge": ["reddit story", "pro revenge", "reddit stories", "revenge story", "storytime"],
    "EntitledParents": ["reddit story", "entitled parents", "reddit stories", "drama", "storytime"],
    "LetsNotMeet": ["reddit story", "lets not meet", "scary reddit stories", "creepy encounters", "horror stories"],
    "nosleep": ["reddit horror", "nosleep reddit", "scary stories", "horror stories reddit", "creepypasta"],
}

DEFAULT_REDDIT_TAGS = ["reddit story", "reddit stories", "storytime", "reddit", "reddit voiceover", "reddit readings"]


def upload_reddit_video(settings, video_path: Path, story) -> str:
    """Upload a Reddit story video with subreddit-specific tags."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    yt_conf = settings.youtube if hasattr(settings, 'youtube') else settings
    if not yt_conf.refresh_token:
        logger.error("YOUTUBE_REFRESH_TOKEN not set.")
        raise RuntimeError("YouTube OAuth not configured")

    creds = Credentials(
        token=None,
        refresh_token=yt_conf.refresh_token,
        client_id=yt_conf.client_id,
        client_secret=yt_conf.client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube"],
    )

    yt = build("youtube", "v3", credentials=creds)

    # Subreddit-specific tags
    sub = getattr(story, "subreddit", "AmItheAsshole")
    tags = REDDIT_TAGS_BY_SUB.get(sub, DEFAULT_REDDIT_TAGS)

    # Title formatting
    title = f"{story.title}"

    description = f"r/{sub}\n\n{story.title}\n\n#reddit #redditstories #storytime #redditreading"
    if hasattr(story, "url") and story.url:
        description += f"\n\nOriginal post: {story.url}"

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "22",
        },
        "status": {"privacyStatus": yt_conf.privacy_status},
    }

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    logger.info(f"Uploading Reddit story: {video_path.name} (privacy: {yt_conf.privacy_status})")

    request = yt.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info(f"Upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    video_url = f"https://youtube.com/shorts/{video_id}"
    logger.info(f"Uploaded Reddit story successfully: {video_url}")
    return video_url


def generate_engaging_comment(story) -> str:
    """Generate an engaging first comment for a Reddit story video."""
    comments = [
        "What would you have done in their place? 🤔",
        "Drop your thoughts below! Was OP in the right?",
        "Would you have handled it the same way? Let me know 👇",
        "Who else is invested in this story now? 😂",
        "Part 2? Let me know in the comments! 👀",
        f"Rate this story 1-10 👇",
        "Tag someone who needs to hear this 😅",
        f"The plot twist at the end though 💀",
    ]
    return random.choice(comments)


def post_engaging_comment(settings, video_url: str, story):
    """Post an engaging comment on the video using the YouTube API."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    import re

    youtube = settings.youtube
    if not youtube.refresh_token:
        return

    # Extract video ID
    match = re.search(r"(?:shorts/|v=)([a-zA-Z0-9_-]+)", video_url)
    if not match:
        return
    video_id = match.group(1)

    creds = Credentials(
        token=None,
        refresh_token=youtube.refresh_token,
        client_id=youtube.client_id,
        client_secret=youtube.client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
    )

    yt = build("youtube", "v3", credentials=creds)

    comment_text = generate_engaging_comment(story)

    try:
        yt.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {"textOriginal": comment_text},
                    },
                },
            },
        ).execute()
        logger.info(f"Posted engaging comment on video {video_id}")
    except Exception as e:
        logger.warning(f"Failed to post comment: {e}")
