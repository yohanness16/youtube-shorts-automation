"""Reddit Stories pipeline — scrape/Generate story → voiceover → background video → edit → upload."""

import logging
import shutil
from datetime import datetime
from pathlib import Path

from config import Settings
from reddit_stories import pick_story
from script_generator import generate_reddit_script, generate_reddit_long_script
from audio_generator import generate_voiceover
from subtitles import generate_srt, create_reddit_subtitle_style
from background_video import get_background
from editor import assemble_video
from youtube_uploader import upload_reddit_video, post_engaging_comment
from music_generator import generate_background_music
from utils import setup_logging, run_ffmpeg
import voice_selector

logger = logging.getLogger("video_automation.reddit_pipeline")


def cleanup_workspace(settings: Settings, subdir: str = ""):
    """Clean up output directory for a fresh run."""
    base = settings.output_dir / subdir if subdir else settings.output_dir
    for d in ["clips", "audio", "subs"]:
        p = base / d
        if p.exists():
            shutil.rmtree(p)
        p.mkdir(parents=True, exist_ok=True)


def run_reddit_shorts(settings: Settings) -> dict:
    """Generate a single Reddit story short video (~60 seconds)."""
    state = {"step": "started", "timestamp": datetime.now().isoformat(), "success": False}
    base = settings.output_dir

    logger.info("=" * 60)
    logger.info("REDDIT SHORTS PIPELINE")
    logger.info("=" * 60)

    # Step 1: Pick/generate Reddit story
    logger.info("STEP 1: Picking Reddit story...")
    state["step"] = "picking_story"
    story = pick_story(settings)
    if not story:
        logger.error("Failed to get a Reddit story")
        state["error"] = "No Reddit story available"
        return state
    state["story_title"] = story.title
    state["story_subreddit"] = story.subreddit
    state["story_source"] = story.url if story.is_scraped else "AI-generated"
    logger.info(f"Story: r/{story.subreddit} - {story.title}")

    # Step 2: Generate script from story
    logger.info("STEP 2: Generating script from story...")
    state["step"] = "generating_script"
    script = generate_reddit_script(settings, story, segments_count=settings.clips_per_video)
    state["script_title"] = script.title
    state["segments"] = len(script.segments)
    logger.info(f"Script: {script.title} ({script.total_words} words)")

    # Step 3: Generate voiceover — pick voice based on subreddit
    voice_name = voice_selector.get_voice_for_subreddit(story.subreddit)
    state["voice"] = voice_name
    logger.info(f"STEP 3: Generating voiceover ({voice_name})...")
    state["step"] = "generating_audio"
    voiceover_path = generate_voiceover(settings, script, base, voice=voice_name)
    state["voiceover"] = str(voiceover_path)

    # Step 4: Get subtitle timings
    logger.info("STEP 4: Generating subtitles...")
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
    total_duration = sum(seg_durations)

    srt_path = generate_srt(script, seg_durations, base / "subs")
    ass_path = create_reddit_subtitle_style(srt_path, base / "subs")

    # Step 5: Get background video
    logger.info(f"STEP 5: Getting background video ({total_duration:.0f}s needed)...")
    state["step"] = "getting_background"
    bg_video_path = base / "clips" / "background.mp4"
    get_background(settings, total_duration, bg_video_path)

    # Step 6: Cut background into clips matching each segment duration
    logger.info("STEP 6: Cutting background clips per segment...")
    state["step"] = "cutting_clips"
    clip_dir = base / "clips"
    clips = []
    current_offset = 0.0
    for i, dur in enumerate(seg_durations):
        clip_path = clip_dir / f"clip_{i:03d}.mp4"
        run_ffmpeg([
            "-ss", str(current_offset),
            "-i", str(bg_video_path),
            "-t", str(dur),
            "-an",
            "-c:v", "copy",
            "-y", str(clip_path),
        ])
        clips.append(clip_path)
        current_offset += dur
        logger.info(f"  Clip {i+1}: {dur:.1f}s ({current_offset - dur:.1f}s -> {current_offset:.1f}s)")
    state["clips"] = len(clips)

    # Step 7: Assemble final video
    logger.info("STEP 7: Assembling video...")
    state["step"] = "assembling"
    music_path = base / "audio" / "background.wav"
    generate_background_music(music_path, duration=total_duration, subreddit=getattr(story, 'subreddit', ''))

    final_video = assemble_video(
        clip_paths=clips,
        voiceover_path=voiceover_path,
        subtitle_ass_path=ass_path,
        output_path=base / "reddit_short.mp4",
        background_music_path=music_path,
        max_duration=59.0,
    )
    state["final_video"] = str(final_video)

    # Step 8: Upload to YouTube
    if settings.youtube.refresh_token and settings.youtube.client_id:
        logger.info("STEP 8: Uploading to YouTube...")
        state["step"] = "uploading"
        try:
            video_url = upload_reddit_video(settings.youtube, final_video, story)
            state["youtube_url"] = video_url

            # Post engaging comment
            post_engaging_comment(settings, video_url, story)
        except Exception as e:
            logger.error(f"YouTube upload failed: {e}")
            state["upload_error"] = str(e)
    else:
        logger.info("STEP 8: Skipped (no YouTube credentials)")
        state["upload_skipped"] = True

    state["success"] = True
    state["step"] = "completed"
    logger.info(f"Reddit short complete: {state.get('script_title', 'Unknown')}")
    return state


def run_reddit_long_video(settings: Settings) -> dict:
    """Generate a single long-form Reddit story video (120-150 seconds)."""
    state = {"step": "started", "timestamp": datetime.now().isoformat(), "success": False}
    base = settings.output_dir

    logger.info("=" * 60)
    logger.info("REDDIT LONG FORM PIPELINE")
    logger.info("=" * 60)

    # Step 1: Pick story (prefer longer stories for long-form)
    logger.info("STEP 1: Picking Reddit story...")
    state["step"] = "picking_story"

    # Try up to 3 times to get a story with enough content
    story = None
    for attempt in range(3):
        candidate = pick_story(settings)
        if candidate and len(candidate.body.split()) > 200:
            story = candidate
            break

    if not story:
        logger.error("Failed to get a substantial Reddit story")
        state["error"] = "No suitable Reddit story found"
        return state

    state["story_title"] = story.title
    state["story_subreddit"] = story.subreddit
    state["story_word_count"] = len(story.body.split())
    logger.info(f"Story: r/{story.subreddit} - {story.title} ({len(story.body.split())} words)")

    # Step 2: Generate long-form script (30 segments = ~2.5 min)
    logger.info("STEP 2: Generating long-form script...")
    state["step"] = "generating_script"
    long_segments = 30
    script = generate_reddit_long_script(settings, story, segments_count=long_segments)
    state["script_title"] = script.title
    state["segments"] = len(script.segments)
    logger.info(f"Script: {script.title} ({script.total_words} words)")

    # Step 3: Voiceover — pick voice based on subreddit
    voice_name = voice_selector.get_voice_for_subreddit(story.subreddit)
    state["voice"] = voice_name
    logger.info(f"STEP 3: Generating voiceover ({voice_name})...")
    state["step"] = "generating_audio"
    voiceover_path = generate_voiceover(settings, script, base, voice=voice_name)
    state["voiceover"] = str(voiceover_path)

    # Step 4: Subtitles
    logger.info("STEP 4: Generating subtitles...")
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
            dur = float(result.stdout.strip()) if result.returncode == 0 else 5.0
        else:
            dur = 5.0
        seg_durations.append(dur)
    total_duration = sum(seg_durations)
    logger.info(f"Total voiceover duration: {total_duration:.0f}s")

    srt_path = generate_srt(script, seg_durations, base / "subs")
    ass_path = create_reddit_subtitle_style(srt_path, base / "subs")

    # Step 5: Background video (loop if needed for longer duration)
    logger.info(f"STEP 5: Getting background video ({total_duration:.0f}s)...")
    state["step"] = "getting_background"
    bg_video_path = base / "clips" / "background.mp4"
    get_background(settings, total_duration, bg_video_path)

    # Step 6: Cut background clips per segment
    logger.info("STEP 6: Cutting background clips...")
    state["step"] = "cutting_clips"
    clip_dir = base / "clips"
    clips = []
    current_offset = 0.0
    for i, dur in enumerate(seg_durations):
        clip_path = clip_dir / f"clip_{i:03d}.mp4"
        run_ffmpeg([
            "-ss", str(current_offset),
            "-i", str(bg_video_path),
            "-t", str(dur),
            "-an",
            "-c:v", "libx264",
            "-crf", "23",
            "-y", str(clip_path),
        ])
        clips.append(clip_path)
        current_offset += dur
    state["clips"] = len(clips)

    # Step 7: Assemble
    logger.info("STEP 7: Assembling long-form video...")
    state["step"] = "assembling"
    music_path = base / "audio" / "background.wav"
    generate_background_music(music_path, duration=total_duration, subreddit=getattr(story, 'subreddit', ''))

    final_video = assemble_video(
        clip_paths=clips,
        voiceover_path=voiceover_path,
        subtitle_ass_path=ass_path,
        output_path=base / "reddit_long.mp4",
        background_music_path=music_path,
    )
    state["final_video"] = str(final_video)

    # Step 8: Upload
    if settings.youtube.refresh_token and settings.youtube.client_id:
        logger.info("STEP 8: Uploading to YouTube...")
        state["step"] = "uploading"
        try:
            from youtube_uploader import upload_video
            video_url = upload_video(settings.youtube, final_video, script.title)
            state["youtube_url"] = video_url
            post_engaging_comment(settings, video_url, story)
        except Exception as e:
            logger.error(f"YouTube upload failed: {e}")
            state["upload_error"] = str(e)
    else:
        logger.info("STEP 8: Skipped (no YouTube credentials)")
        state["upload_skipped"] = True

    state["success"] = True
    state["step"] = "completed"
    logger.info(f"Reddit long-form complete: {state.get('script_title', 'Unknown')}")
    return state


def run_reddit_pipeline(settings: Settings, shorts_count: int = 5) -> dict:
    """Run full pipeline: N shorts + 1 long video.
    Each video gets its own workspace to avoid overwriting files.
    """
    logger.info("=" * 60)
    logger.info(f"REDDIT FULL PIPELINE: {shorts_count} shorts + 1 long-form")
    logger.info("=" * 60)

    results = {
        "shorts": [],
        "long_video": None,
        "timestamp": datetime.now().isoformat(),
    }

    # Generate shorts
    for i in range(shorts_count):
        logger.info(f"\n{'='*60}")
        logger.info(f"SHORT VIDEO {i+1}/{shorts_count}")
        logger.info(f"{'='*60}")

        # Each short gets its own output subdirectory
        short_dir = settings.output_dir / f"short_{i+1}"
        short_dir.mkdir(parents=True, exist_ok=True)

        # Temporarily swap output_dir pointer
        original_output = settings.output_dir
        settings.output_dir = short_dir
        settings.ensure_directories()

        result = run_reddit_shorts(settings)
        results["shorts"].append(result)

        # Restore
        settings.output_dir = original_output

    # Generate long-form
    logger.info(f"\n{'='*60}")
    logger.info("LONG-FORM VIDEO")
    logger.info(f"{'='*60}")

    if settings.source_video:
        original_output = settings.output_dir
        settings.output_dir = settings.output_dir / "long_video"
        settings.output_dir.mkdir(parents=True, exist_ok=True)
        settings.ensure_directories()

        long_result = run_reddit_long_video(settings)
        results["long_video"] = long_result

        settings.output_dir = original_output
    else:
        long_output_dir = settings.output_dir / "long_form"
        long_output_dir.mkdir(parents=True, exist_ok=True)
        original_output = settings.output_dir
        settings.output_dir = long_output_dir
        settings.ensure_directories()

        long_result = run_reddit_long_video(settings)
        results["long_video"] = long_result

        settings.output_dir = original_output

    # Summary
    short_successes = sum(1 for s in results["shorts"] if s.get("success"))
    logger.info("\n" + "=" * 60)
    logger.info(f"PIPELINE COMPLETE: {short_successes}/{shorts_count} shorts, {'YES' if results['long_video'] and results['long_video'].get('success') else 'FAILED'} long-form")
    logger.info("=" * 60)

    return results


def archive_reddit_run(settings: Settings, state: dict, prefix: str = "reddit_short"):
    """Archive a Reddit video run to completed/ or failed/."""
    import json
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
