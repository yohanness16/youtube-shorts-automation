"""Background video manager for Reddit stories — downloads from YouTube or picks from local folder."""

import logging
import random
import shutil
import subprocess
from pathlib import Path

from config import Settings
from utils import run_ffmpeg

logger = logging.getLogger("video_automation.background_video")

DOWNLOAD_QUERIES = [
    "minecraft parkour gameplay no copyright",
    "subway surfers gameplay no copyright",
    "gta 5 ramp gameplay no copyright",
    "satisfying slime cutting no copyright",
]

# Direct YouTube URLs that are CC-free / safe for background
FALLBACK_VIDEOS = [
    "https://www.youtube.com/watch?v=XBIaqOm0RKQ",  # Primary fallback (also as youtu.be/XBIaqOm0RKQ)
    "https://youtu.be/XBIaqOm0RKQ",
]


def search_and_download_youtube(query: str, output_path: Path, timeout: int = 300) -> bool:
    """Search YouTube via yt-dlp and download the first result."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    search_url = f"ytsearch1:{query}"
    tmp_name = output_path.with_suffix(".tmp.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(tmp_name),
        "--no-playlist",
        "--max-filesize", "100M",
        "--socket-timeout", "30",
        search_url,
    ]

    logger.info(f"Searching and downloading for: '{query}'")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            logger.warning(f"yt-dlp search failed: {result.stderr[-500:]}")
            return False
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.warning(f"yt-dlp search failed: {e}")
        return False

    # Find the downloaded file
    files = list(output_path.parent.glob("search_*.mp4")) + list(output_path.parent.glob("*.tmp.mp4"))
    if not files:
        logger.warning("No video file found from yt-dlp search")
        return False

    src = max(files, key=lambda p: p.stat().st_size)
    if src != output_path:
        shutil.move(str(src), str(output_path))
        # Clean up any extra files
        for f in output_path.parent.glob("*.tmp.*"):
            f.unlink(missing_ok=True)

    size_mb = output_path.stat().st_size / 1e6
    logger.info(f"Downloaded: {output_path.name} ({size_mb:.1f} MB)")
    return True


def download_fallback_video(output_path: Path, timeout: int = 300) -> bool:
    """Download a pre-configured fallback background video."""
    logger.info(f"Downloading fallback background video...")

    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(output_path.with_suffix(".tmp.%(ext)s")),
        "--no-playlist",
        "--socket-timeout", "30",
        FALLBACK_VIDEOS[0],
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            logger.warning(f"yt-dlp fallback download failed: {result.stderr[-500:]}")
            return False
    except (subprocess.TimeoutExpired, Exception) as e:
        logger.warning(f"Fallback download failed: {e}")
        return False

    # Find the downloaded file
    files = list(output_path.parent.glob("*.tmp.mp4")) + list(output_path.parent.glob("*.mp4"))
    if not files:
        return False

    src = max(files, key=lambda p: p.stat().st_size)
    if src != output_path:
        shutil.move(str(src), str(output_path))
        for f in output_path.parent.glob("*.tmp.*"):
            f.unlink(missing_ok=True)

    size_mb = output_path.stat().st_size / 1e6
    logger.info(f"Downloaded fallback video: {output_path.name} ({size_mb:.1f} MB)")
    return True


def get_background_video(output_path: Path, duration: float, query: str = "") -> Path:
    """Get a background video by downloading from YouTube via yt-dlp."""
    query = query or random.choice(DOWNLOAD_QUERIES)
    logger.info(f"Getting background video for '{query}'...")

    if search_and_download_youtube(query, output_path, timeout=300):
        _cut_or_loop_video(output_path, output_path.with_suffix(".trimmed.mp4"), int(duration) + 5)
        output_path.unlink(missing_ok=True)
        output_path.with_suffix(".trimmed.mp4").rename(output_path)
        logger.info(f"Background video ready: {output_path}")
        return output_path

    # Try hardcoded fallback video
    logger.info("Search failed, trying configured fallback video URL...")
    if download_fallback_video(output_path, timeout=300):
        _cut_or_loop_video(output_path, output_path.with_suffix(".trimmed.mp4"), int(duration) + 5)
        output_path.with_suffix(".mp4").unlink(missing_ok=True)
        output_path.with_suffix(".trimmed.mp4").rename(output_path)
        logger.info(f"Background video ready (from fallback): {output_path}")
        return output_path

    # Final fallback: generate a solid color background
    logger.warning("All downloads failed, generating fallback background")
    return _generate_fallback_bg(duration, output_path)


def select_local_background(folder: str, duration: float, output_path: Path) -> Path:
    """Pick a random video from a local folder and cut/loop to duration."""
    folder_path = Path(folder)
    if not folder_path.exists():
        logger.warning(f"Background folder not found: {folder}")
        return _generate_fallback_bg(duration, output_path)

    video_files = (
        list(folder_path.glob("*.mp4"))
        + list(folder_path.glob("*.mkv"))
        + list(folder_path.glob("*.mov"))
        + list(folder_path.glob("*.webm"))
    )
    if not video_files:
        logger.warning("No video files in background folder")
        return _generate_fallback_bg(duration, output_path)

    src = random.choice(video_files)
    logger.info(f"Using local background: {src.name}")

    # Convert webm to mp4 first if needed (ffmpeg input compatibility)
    work_src = src
    if src.suffix.lower() == ".webm":
        converted = output_path.parent / "_temp_bg_source.mp4"
        logger.info(f"Converting webm to mp4 for compatibility: {src.name}")
        run_ffmpeg([
            "-i", str(src),
            "-c:v", "libx264",
            "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            "-y",
            str(converted),
        ])
        work_src = converted

    try:
        _cut_or_loop_video(work_src, output_path.with_suffix(".trimmed.mp4"), int(duration) + 5)
        output_path.with_suffix(".trimmed.mp4").rename(output_path)
        logger.info(f"Background video ready: {output_path}")
    finally:
        # Clean up temp conversion if we made one
        if work_src != src and work_src.exists():
            work_src.unlink(missing_ok=True)

    return output_path


def get_background(settings: Settings, duration: float, output_path: Path) -> Path:
    """Main entry point — decides youtube vs local based on settings."""
    source = settings.reddit.background_video_source.lower()

    if source == "local" and settings.reddit.background_video_folder:
        return select_local_background(
            settings.reddit.background_video_folder, duration, output_path
        )

    return get_background_video(
        output_path, duration, settings.reddit.background_video_query
    )


def _cut_or_loop_video(src: Path, output_path: Path, duration: int):
    """Cut video to duration or loop it if shorter."""
    from utils import run_ffmpeg

    # Get source duration
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(src)],
        capture_output=True, text=True,
    )
    src_dur = float(result.stdout.strip()) if result.returncode == 0 else duration

    if src_dur >= duration:
        run_ffmpeg([
            "-ss", "0",
            "-i", str(src),
            "-t", str(duration),
            "-an",
            "-c:v", "libx264",
            "-crf", "23",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-y", str(output_path),
        ])
    else:
        # Loop using concat demuxer
        loop_count = (duration // max(int(src_dur), 1)) + 1
        list_file = src.parent / "bg_loop_list.txt"
        with open(list_file, "w") as f:
            for _ in range(loop_count):
                f.write(f"file '{src.absolute()}'\n")

        run_ffmpeg([
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-t", str(duration),
            "-an",
            "-c:v", "libx264",
            "-crf", "23",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-y", str(output_path),
        ])
        list_file.unlink(missing_ok=True)


def _generate_fallback_bg(duration: float, output_path: Path) -> Path:
    """Generate a solid colored background as a last resort."""
    run_ffmpeg([
        "-f", "lavfi", "-i",
        f"color=c=0x1a1a2e:s=1080x1920:d={duration}:r=30,format=yuv420p",
        "-c:v", "libx264",
        "-t", str(duration),
        "-pix_fmt", "yuv420p",
        "-y", str(output_path),
    ])
    logger.info(f"Generated fallback background: {output_path}")
    return output_path
