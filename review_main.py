"""Review pipeline — takes a source video, splits it into small chunks,
analyzes each independently, generates a condensed review script,
cuts clips from the source, assembles with voiceover + subtitles + music,
and uploads.

Supports a JSON queue for future web UI integration.
"""

import json
import logging
import shutil
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from config import Settings
from script_generator import generate_summary_script
from audio_generator import generate_voiceover
from video_generator import generate_all_clips
from subtitles import generate_srt, srt_to_ass
from editor import assemble_video
from youtube_uploader import upload_video
from music_generator import generate_background_music
from utils import setup_logging, read_state, save_state
from video_analyzer import (
    download_youtube_video,
    get_duration,
    analyze_full_video,
    load_cached_analysis,
)

logger = logging.getLogger("video_automation.review")

_shutdown = False


def signal_handler(sig, frame):
    global _shutdown
    logger.info(f"Received signal {sig}, shutting down...")
    _shutdown = True


def cleanup_workspace(settings: Settings):
    """Clean up output directory for a fresh run."""
    for d in ["clips", "audio", "subs"]:
        p = settings.output_dir / d
        if p.exists():
            shutil.rmtree(p)
        p.mkdir(parents=True, exist_ok=True)
    draft = settings.output_dir / "draft.mp4"
    if draft.exists():
        draft.unlink()
    concat = settings.output_dir / "concat_list.txt"
    if concat.exists():
        concat.unlink()


def run_review_pipeline(settings: Settings, source_path: Path, source_title: str) -> dict:
    """Run the full review pipeline for one source video."""
    state = {"step": "started", "timestamp": datetime.now().isoformat(), "success": False}
    base = settings.output_dir

    # Step 1: Analyze (split into chunks, transcribe, vision analysis per chunk)
    if _shutdown:
        return state
    logger.info("=" * 60)
    logger.info("STEP 1: Analyzing source video (chunked)")
    state["step"] = "analyzing"

    # Try cache first
    cached = load_cached_analysis(source_path)
    if cached:
        logger.info("Using cached analysis")
        analysis = cached
    else:
        analysis = analyze_full_video(source_path, source_title, settings)

    state["source_title"] = analysis.source_title
    state["source_duration"] = analysis.source_duration
    state["recommended_clips"] = len(analysis.recommended_clips)
    logger.info(f"Source: {source_title} ({analysis.source_duration:.0f}s)")
    logger.info(f"Recommended clips: {analysis.recommended_clips}")

    # Build timestamp pairs from the analysis for direct clip extraction
    clip_timestamps = []
    for item in analysis.recommended_clips:
        if "-" in item:
            try:
                parts = item.split("-", 1)
                clip_timestamps.append((float(parts[0]), float(parts[1])))
            except ValueError:
                clip_timestamps.append((0, settings.clip_duration_seconds))

    # Step 2: Generate review script from analysis
    if _shutdown:
        return state
    logger.info("=" * 60)
    logger.info("STEP 2: Generating review script")
    state["step"] = "generating_script"

    script = generate_summary_script(settings, analysis)
    state["script_title"] = script.title
    state["segments"] = len(script.segments)
    logger.info(f"Review script: {script.title} ({script.total_words} words)")

    # Step 3: Generate voiceover
    if _shutdown:
        return state
    logger.info("=" * 60)
    logger.info("STEP 3: Generating voiceover")
    state["step"] = "generating_audio"

    voiceover_path = generate_voiceover(settings, script, base)
    state["voiceover"] = str(voiceover_path)

    # Step 4: Subtitles
    if _shutdown:
        return state
    logger.info("=" * 60)
    logger.info("STEP 4: Generating subtitles")
    state["step"] = "generating_subtitles"

    seg_durations = []
    audio_dir = base / "audio"
    for i in range(len(script.segments)):
        seg_path = audio_dir / f"seg_{i:03d}.wav"
        if seg_path.exists():
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(seg_path)],
                capture_output=True, text=True,
            )
            dur = float(result.stdout.strip()) if result.returncode == 0 else settings.clip_duration_seconds
        else:
            dur = settings.clip_duration_seconds
        seg_durations.append(dur)

    srt_path = generate_srt(script, seg_durations, base / "subs")
    ass_path = srt_to_ass(srt_path, script, base / "subs")

    # Step 5: Cut clips from source using analysis timestamps
    if _shutdown:
        return state
    logger.info("=" * 60)
    logger.info("STEP 5: Cutting video clips from source")
    state["step"] = "cutting_clips"

    clips, all_ok = generate_all_clips(
        settings, script, base,
        source_path=source_path,
        clip_timestamps=clip_timestamps,
    )
    state["clips"] = len(clips)
    logger.info(f"Extracted {len(clips)} clips from source")

    # Step 6: Assemble final video
    if _shutdown:
        return state
    logger.info("=" * 60)
    logger.info("STEP 6: Assembling video")
    state["step"] = "assembling"

    total_duration = sum(seg_durations)
    music_path = base / "audio" / "background.wav"
    generate_background_music(music_path, duration=total_duration)

    final_video = assemble_video(
        clip_paths=clips,
        voiceover_path=voiceover_path,
        subtitle_ass_path=ass_path,
        output_path=base / "draft.mp4",
        background_music_path=music_path,
    )
    state["final_video"] = str(final_video)

    # Step 7: Upload
    if _shutdown:
        return state
    if settings.youtube.refresh_token and settings.youtube.client_id:
        logger.info("=" * 60)
        logger.info("STEP 7: Uploading to YouTube")
        state["step"] = "uploading"
        try:
            video_url = upload_video(settings.youtube, final_video, script.title)
            state["youtube_url"] = video_url
        except Exception as e:
            logger.error(f"YouTube upload failed: {e}")
            state["upload_error"] = str(e)
    else:
        logger.info("STEP 7: Skipped (no YouTube credentials)")
        state["upload_skipped"] = True

    state["success"] = True
    state["step"] = "completed"
    return state


def archive_run(settings: Settings, state: dict, prefix: str = "review"):
    """Move output to completed/ or failed/."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_dir = settings.completed_dir if state.get("success") else settings.failed_dir
    dest = dest_dir / f"{prefix}_{timestamp}"
    dest.mkdir(parents=True, exist_ok=True)

    for item in settings.output_dir.iterdir():
        if item.is_dir():
            shutil.copytree(item, dest / item.name, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest / item.name)

    with open(dest / "state.json", "w") as f:
        json.dump(state, f, indent=2)

    logger.info(f"Archived {prefix} run to {dest}")


# ===========================================================================
# Queue system — JSON file for future web UI integration
# ===========================================================================

QUEUE_FILE = Path(__file__).parent / "queue.json"


def load_queue() -> dict:
    if QUEUE_FILE.exists():
        with open(QUEUE_FILE) as f:
            return json.load(f)
    return {"pending": [], "processing": [], "completed": [], "failed": []}


def save_queue(queue: dict):
    tmp = QUEUE_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(queue, f, indent=2)
    tmp.rename(QUEUE_FILE)


def add_to_queue(source: str) -> str:
    """Add a source (URL or path) to the queue. Returns job ID."""
    queue = load_queue()
    job_id = datetime.now().strftime("%Y%m%d_%H%M%S_") + f"{len(queue['pending'])+1:03d}"
    queue["pending"].append({
        "id": job_id,
        "source": source,
        "added": datetime.now().isoformat(),
        "status": "queued",
    })
    save_queue(queue)
    logger.info(f"Added to queue: {source} (id: {job_id})")
    return job_id


def process_queue(settings: Settings):
    """Process all pending items in the queue one by one."""
    import re

    while True:
        queue = load_queue()
        if not queue["pending"]:
            logger.info("Queue empty. Processing complete.")
            break

        job = queue["pending"].pop(0)
        queue["processing"].append(job)
        save_queue(queue)

        source = job["source"]
        logger.info(f"Processing queue job: {source} (id: {job['id']})")

        try:
            if re.search(r"(youtube\.com|youtu\.be)", source):
                src_dir = settings.output_dir / "source"
                source_path, source_title = download_youtube_video(source, src_dir)
            else:
                source_path = Path(source)
                if not source_path.exists():
                    raise FileNotFoundError(f"Source not found: {source}")
                source_title = source_path.stem

            cleanup_workspace(settings)
            result = run_review_pipeline(settings, source_path, source_title)
            archive_run(settings, result)

            job["status"] = "completed" if result.get("success") else "failed"
            job["completed"] = datetime.now().isoformat()
            queue["processing"] = [j for j in queue["processing"] if j["id"] != job["id"]]
            target = queue["completed"] if job["status"] == "completed" else queue["failed"]
            target.append(job)
            save_queue(queue)

        except Exception as e:
            logger.error(f"Queue job failed: {e}", exc_info=True)
            job["status"] = "failed"
            job["error"] = str(e)
            job["failed"] = datetime.now().isoformat()
            queue["processing"] = [j for j in queue["processing"] if j["id"] != job["id"]]
            queue["failed"].append(job)
            save_queue(queue)


def run_single_review(settings: Settings, source: str):
    """Run a review pipeline for a single source, bypassing the queue."""
    from video_analyzer import download_youtube_video, is_youtube_url
    import re

    if re.search(r"(youtube\.com|youtu\.be)", source):
        src_dir = settings.output_dir / "source"
        source_path, source_title = download_youtube_video(source, src_dir)
    else:
        source_path = Path(source)
        if not source_path.exists():
            raise FileNotFoundError(f"Source not found: {source}")
        source_title = source_path.stem

    cleanup_workspace(settings)
    result = run_review_pipeline(settings, source_path, source_title)
    archive_run(settings, result)

    # Update state
    saved = read_state(settings.cache_dir)
    saved["last_review_run"] = result
    saved["total_review_runs"] = saved.get("total_review_runs", 0) + 1
    if result.get("success"):
        saved["total_review_successes"] = saved.get("total_review_successes", 0) + 1
    today = datetime.now().strftime("%Y-%m-%d")
    if result.get("success"):
        saved.setdefault(f"reviews_{today}", 0)
        saved[f"reviews_{today}"] += 1
    save_state(settings.cache_dir, saved)

    return result
