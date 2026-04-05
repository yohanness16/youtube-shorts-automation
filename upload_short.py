"""Standalone YouTube Shorts uploader — reads .env for credentials."""

import logging
from pathlib import Path
from dotenv import load_dotenv
from config import Settings
from youtube_uploader import upload_video

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
)
logger = logging.getLogger("uploader")


def main():
    load_dotenv()
    settings = Settings.from_env()

    video_path = Path(__file__).parent / "output" / "reddit_short.mp4"
    if not video_path.exists():
        logger.error(f"Video not found: {video_path}")
        return

    logger.info(f"Uploading: {video_path}")
    video_url = upload_video(
        settings.youtube,
        video_path,
        "Reddit Story Compilation",
    )
    logger.info(f"Uploaded! {video_url}")


if __name__ == "__main__":
    main()
