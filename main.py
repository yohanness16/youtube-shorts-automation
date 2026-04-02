"""Main orchestrator — runs the full pipeline in a loop."""

import json
import logging
import shutil
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from config import Settings
from idea_generator import generate_ideas, select_best_idea
from script_generator import generate_script
from audio_generator import generate_voiceover
from video_generator import generate_all_clips
from subtitles import generate_srt, srt_to_ass
from editor import assemble_video
from youtube_uploader import upload_video
from music_generator import generate_background_music
from utils import setup_logging, read_state, save_state

logger = logging.getLogger("video_automation.main")

# Graceful shutdown flag
_shutdown = False


def signal_handler(sig, frame):
    global _shutdown
    logger.info(f"Received signal {sig}, finishing current step then exiting...")
    _shutdown = True


def run_pipeline(settings: Settings) -> dict:
    """Execute one full pipeline cycle. Returns state dict."""
    state = {
        "step": "started",
        "timestamp": datetime.now().isoformat(),
        "success": False,
    }

    base = settings.output_dir

    # Step 1: Generate ideas
    if _shutdown:
        return state
    logger.info("=" * 60)
    logger.info("STEP 1: Generating topic ideas")
    state["step"] = "generating_ideas"
    ideas = generate_ideas(settings)
    idea = select_best_idea(ideas, settings.cache_dir)
    state["idea"] = idea.title
    logger.info(f"Selected idea: {idea.title}")

    # Step 2: Generate script
    if _shutdown:
        return state
    logger.info("=" * 60)
    logger.info("STEP 2: Generating script")
    state["step"] = "generating_script"
    script = generate_script(settings, idea)
    state["script_title"] = script.title
    state["segments"] = len(script.segments)
    logger.info(f"Script: {script.title} ({script.total_words} words)")

    # Step 3: Generate voiceover audio
    if _shutdown:
        return state
    logger.info("=" * 60)
    logger.info("STEP 3: Generating voiceover")
    state["step"] = "generating_audio"
    voiceover_path = generate_voiceover(settings, script, base)
    state["voiceover"] = str(voiceover_path)

    # Step 4: Generate subtitle timing from audio segments
    if _shutdown:
        return state
    logger.info("=" * 60)
    logger.info("STEP 4: Generating subtitles")
    state["step"] = "generating_subtitles"
    import subprocess
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
    state["seg_durations"] = seg_durations

    srt_path = generate_srt(script, seg_durations, base / "subs")
    ass_path = srt_to_ass(srt_path, script, base / "subs")

    # Step 5: Generate video clips
    if _shutdown:
        return state
    logger.info("=" * 60)
    logger.info("STEP 5: Generating video clips")
    state["step"] = "generating_clips"
    clips, all_ok = generate_all_clips(settings, script, base)
    state["clips"] = len(clips)

    # Step 5.5: Compute total video duration for background music
    total_duration = sum(seg_durations)

    # Step 6: Assemble final video
    if _shutdown:
        return state
    logger.info("=" * 60)
    logger.info("STEP 6: Assembling video")
    state["step"] = "assembling"

    # Generate background music dynamically
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

    # Step 7: Upload to YouTube (if configured)
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
        logger.info("STEP 7: Skipped (no YouTube credentials configured)")
        state["upload_skipped"] = True

    state["success"] = True
    state["step"] = "completed"
    return state


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


def archive_run(settings: Settings, state: dict):
    """Move output to completed/ or failed/."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = "completed" if state.get("success") else "failed"
    dest_dir = settings.completed_dir if state.get("success") else settings.failed_dir
    dest = dest_dir / timestamp

    dest.mkdir(parents=True, exist_ok=True)

    # Copy everything from output/ to archive
    for item in settings.output_dir.iterdir():
        if item.is_dir():
            shutil.copytree(item, dest / item.name, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest / item.name)

    # Save metadata
    with open(dest / "state.json", "w") as f:
        json.dump(state, f, indent=2)

    logger.info(f"Archived to {dest}")


def run_once(settings: Settings) -> dict:
    """Run a single pipeline cycle."""
    cleanup_workspace(settings)
    result = run_pipeline(settings)
    archive_run(settings, result)

    # Save persistent state
    state_file = settings.cache_dir / "state.json"
    saved = read_state(settings.cache_dir)
    saved["last_run"] = result
    saved["total_runs"] = saved.get("total_runs", 0) + 1
    if result.get("success"):
        saved["total_successes"] = saved.get("total_successes", 0) + 1
    save_state(settings.cache_dir, saved)
    return result


def main():
    global _shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    settings = Settings.from_env()
    settings.ensure_directories()
    setup_logging(settings.log_dir)

    # Validate configuration
    errors = settings.validate()
    if errors:
        logger.error("Configuration errors:")
        for e in errors:
            logger.error(f"  - {e}")
        logger.error("Fix errors in .env and restart.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("YouTube Shorts Automation Pipeline")
    logger.info(f"Niche: {settings.niche}")
    logger.info(f"Script provider: {settings.script.provider}")
    logger.info(f"Voice provider: {settings.voice.provider}")
    logger.info(f"Video provider: {settings.video.provider}")
    logger.info(f"Clips per video: {settings.clips_per_video}")
    logger.info("=" * 60)
    logger.info("Starting pipeline loop...")

    while not _shutdown:
        state = read_state(settings.cache_dir)
        total = state.get("total_runs", 0)
        successes = state.get("total_successes", 0)
        logger.info(f"Run #{total + 1} (completed: {successes}/{total})")

        try:
            result = run_once(settings)
            if result.get("success"):
                logger.info(f"Run completed successfully: {result.get('script_title', 'Unknown')}")
                if result.get("youtube_url"):
                    logger.info(f"YouTube URL: {result['youtube_url']}")
            else:
                logger.warning("Run completed with errors. Check failed/ directory.")
        except Exception as e:
            logger.error(f"Pipeline crashed: {e}", exc_info=True)
            # Save error state
            error_dir = settings.failed_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
            error_dir.mkdir(parents=True, exist_ok=True)
            with open(error_dir / "error.log", "w") as f:
                f.write(f"Error: {e}\n")
                f.write(f"Step: state unknown\n")

        if _shutdown:
            logger.info("Shutdown requested. Exiting after this run.")
            break

        # Sleep until next run
        logger.info(f"Sleeping for {settings.poll_interval_seconds}s before next run...")
        # Interruptible sleep
        for _ in range(settings.poll_interval_seconds):
            if _shutdown:
                break
            time.sleep(1)

    logger.info("Pipeline stopped.")


if __name__ == "__main__":
    main()
