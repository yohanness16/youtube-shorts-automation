"""YouTube Data API v3 uploader — OAuth2 resumable upload."""

import json
import logging
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
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
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
