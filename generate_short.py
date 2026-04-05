"""Generate a single Reddit stories Short — best story, best voice, bg video, bg music — then upload."""

import json
import logging
import random
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import shutil

from config import Settings
from reddit_stories import scrape_reddit_stories, generate_reddit_story, RedditStory
from reddit_stories import split_story_to_paragraphs
from audio_generator import generate_voiceover
from subtitles import generate_srt, srt_to_ass
from video_generator import generate_all_clips
from editor import assemble_video
from background_video import select_local_background
from utils import setup_logging, run_ffmpeg
from youtube_uploader import upload_reddit_video
from script_generator import Script, ScriptSegment, generate_reddit_script


logger = logging.getLogger("video_automation.generate_short")

# High-upvote subreddits we want first
QUALITY_SUBREDDITS = [
    "prorevenge",
    "pettyrevenge",
    "MaliciousCompliance",
    "AmItheAsshole",
    "confessions",
    "trueoffmychest",
    "tifu",
    "EntitledParents",
    "LetsNotMeet",
]


def pick_best_story(settings: Settings) -> RedditStory:
    """Scrape from multiple subreddits, pick the story with most upvotes."""
    all_stories: list[RedditStory] = []

    for sub in QUALITY_SUBREDDITS:
        logger.info(f"Scraping r/{sub}...")
        try:
            stories = scrape_reddit_stories(sub, count=8)
        except Exception as e:
            logger.warning(f"Failed to scrape r/{sub}: {e}")
            stories = []
        for s in stories:
            if len(s.body) >= 200:
                all_stories.append(s)

    if not all_stories:
        logger.info("No scraped stories found, generating AI...")
        niche = random.choice(QUALITY_SUBREDDITS)
        try:
            story = generate_reddit_story(settings, niche)
        except Exception as e:
            logger.warning(f"AI story generation failed: {e}")
            story = None
        if story:
            return story
        raise RuntimeError("Failed to get any story")

    all_stories.sort(key=lambda s: s.upvotes, reverse=True)
    top_stories = all_stories[:max(len(all_stories) // 2, 1)]
    picked = random.choice(top_stories)
    logger.info(f"Best story picked: {picked.title} ({picked.upvotes} upvotes, r/{picked.subreddit})")
    return picked


def convert_story_to_script(story: RedditStory) -> Script:
    """Convert a Reddit story into a Short-ready script using paragraphs as segments."""
    paragraphs = split_story_to_paragraphs(story.body)[:12]
    segments = [
        ScriptSegment(
            text=p,
            visual_prompt="engaging background gameplay footage, minecraft parkour style, 9:16 vertical",
            subtitle_highlight=p.split()[0] if p.split() else "story",
        )
        for p in paragraphs
    ]
    return Script(title=story.full_title, segments=segments)


def generate_story_script(settings: Settings, story: RedditStory) -> Script:
    """Try LLM-based reddit script first, fall back to paragraph-based script."""
    try:
        return generate_reddit_script(settings, story, segments_count=12)
    except Exception as e:
        logger.warning(f"AI script generation failed: {e}, falling back to paragraphs")
        return convert_story_to_script(story)


def get_best_voice(subreddit: str) -> str:
    """Pick an emotional, expressive edge-tts voice for storytelling."""
    sub_lower = subreddit.lower()
    if sub_lower in ("letsnotmeet", "nosleep"):
        return "en-US-GuyNeural"
    if sub_lower in ("prorevenge", "pettyrevenge"):
        return "en-US-ChristopherNeural"
    if sub_lower in ("tifu", "maliciouscompliance"):
        return "en-US-BrianMultilingualNeural"
    if sub_lower in ("amItheAsshole", "entitledparents"):
        return "en-US-AndrewMultilingualNeural"
    if sub_lower in ("confessions", "trueoffmychest"):
        return "en-US-AvaMultilingualNeural"
    return "en-US-AvaMultilingualNeural"


def _pick_bgmusic(folder: Path, duration: float, output_path: Path, story_title: str = "") -> Path:
    """Pick an audio file from bgMusic folder based on story mood, trim/loop to duration.

    Analyzes the story title for keywords and picks a matching track.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audio_files = list(folder.glob("*.mp3")) + list(folder.glob("*.wav")) + list(folder.glob("*.ogg"))
    if not audio_files:
        logger.warning("No audio files in bgMusic folder, generating silent placeholder")
        run_ffmpeg([
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
            "-t", str(duration), "-c:a", "pcm_s16le", "-y", str(output_path),
        ])
        return output_path

    lower_title = story_title.lower()

    # Score each file based on keywords in its filename
    def _mood_score(filepath: Path) -> float:
        name = filepath.name.lower()
        score = 0.0
        # Relaxing/calm — default for most stories
        for kw in ["relax", "calm", "mellow", "gentle", "soft", "meditation"]:
            if kw in name:
                score += 1.0
        # Sad/emotional stories
        for kw in ["sad", "emotional", "touching", "deep", "heart"]:
            if kw in name:
                score += 0.5
        # Dramatic/intense — for revenge, drama
        for kw in ["dramatic", "intense", "epic"]:
            if kw in name:
                score += 0.5
        # Title-based mood boost
        for kw in ["sad", "died", "lost", "cry", "grief", "alone", "depress", "heartbreak", "funeral"]:
            if kw in lower_title:
                score += 2.0
        for kw in ["funny", "stupid", "idiot", "laugh", "absurd", "dumb", "ridiculous"]:
            if kw in lower_title:
                score += 1.0
        for kw in ["revenge", "payback", "destroyed", "karma"]:
            if kw in lower_title:
                score += 1.5
        for kw in ["scary", "creepy", "dark", "terrifying", "haunted"]:
            if kw in lower_title:
                score += 1.5
        # If no keywords matched in title, default: prefer calm/relaxing tracks
        if score == 0:
            for kw in ["calm", "relax", "mellow", "gentle"]:
                if kw in name:
                    score += 1.0
        return score

    scored = [(f, _mood_score(f)) for f in audio_files]
    scored.sort(key=lambda x: x[1], reverse=True)

    # Pick from top 2 scored files for some variety
    top_files = [f for f, s in scored[:min(2, len(scored))]]
    src = random.choice(top_files)
    logger.info(f"Using bg music: {src.name}")

    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(src)],
        capture_output=True, text=True,
    )
    src_dur = float(result.stdout.strip()) if result.returncode == 0 else duration

    if src_dur >= duration:
        run_ffmpeg([
            "-ss", "0", "-i", str(src),
            "-t", str(duration),
            "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
            "-y", str(output_path),
        ])
    else:
        loop_count = int(duration / max(src_dur, 0.1)) + 1
        list_file = output_path.parent / "music_loop.txt"
        with open(list_file, "w") as f:
            for _ in range(loop_count):
                f.write(f"file '{src.absolute()}'\n")
        run_ffmpeg([
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-t", str(duration),
            "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2",
            "-y", str(output_path),
        ])
        list_file.unlink(missing_ok=True)

    logger.info(f"Background music ready: {output_path} ({duration:.1f}s)")
    return output_path


def main():
    setup_logging(Path("logs"))

    settings = Settings.from_env()
    settings.ensure_directories()

    # Validate
    errors = settings.validate(mode="reddit")
    if errors:
        for e in errors:
            logger.error(f"Config error: {e}")
        sys.exit(1)

    base = settings.output_dir
    base.mkdir(parents=True, exist_ok=True)
    for d in ["clips", "audio", "subs"]:
        p = base / d
        if p.exists():
            shutil.rmtree(p)
        p.mkdir(parents=True, exist_ok=True)

    # Step 1: Pick best Reddit story
    logger.info("=" * 50)
    logger.info("STEP 1: Finding best Reddit story")
    story = pick_best_story(settings)

    # Step 2: Build script from story
    logger.info("=" * 50)
    logger.info("STEP 2: Building script")
    script = generate_story_script(settings, story)
    logger.info(f"Script: {script.title} ({script.total_words} words, {len(script.segments)} segments)")

    # Step 3: Generate voiceover with best voice
    voice = get_best_voice(story.subreddit)
    logger.info("=" * 50)
    logger.info(f"STEP 3: Generating voiceover (voice: {voice})")
    voiceover_path = generate_voiceover(settings, script, base, voice=voice)

    # Step 4: Get subtitle timing
    logger.info("=" * 50)
    logger.info("STEP 4: Generating subtitles")
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
    logger.info(f"Total voiceover duration: {total_duration:.1f}s")

    srt_path = generate_srt(script, seg_durations, base / "subs")
    ass_path = srt_to_ass(srt_path, script, base / "subs")

    # Step 5: Get background video from local folder
    logger.info("=" * 50)
    logger.info("STEP 5: Selecting background video from bg_Video/")
    bg_video_path = base / "audio" / "background_video.mp4"
    bg_video_path.parent.mkdir(parents=True, exist_ok=True)
    background_video = select_local_background(
        str(settings.reddit.background_video_folder),
        total_duration,
        bg_video_path,
    )

    # Step 6: Get background music from bgMusic/ folder
    logger.info("=" * 50)
    logger.info("STEP 6: Selecting background music from bgMusic/")
    bgmusic_folder = Path(__file__).parent / "bgMusic"
    music_path = _pick_bgmusic(bgmusic_folder, total_duration, base / "audio" / "background.wav", story_title=story.title)

    # Build clip timestamps from bg video
    clip_durations = seg_durations
    clip_timestamps = []
    t = 0.0
    for dur in clip_durations:
        clip_timestamps.append((t, t + dur))
        t += dur

    # Step 7: Cut clips from bg video
    logger.info("=" * 50)
    logger.info("STEP 7: Generating video clips from background video")
    clips, all_ok = generate_all_clips(settings, script, base, source_path=background_video, clip_timestamps=clip_timestamps)

    # Step 8: Assemble final video
    logger.info("=" * 50)
    logger.info("STEP 8: Assembling final video")
    draft_path = base / "draft.mp4"
    final_video = assemble_video(
        clip_paths=clips,
        voiceover_path=voiceover_path,
        subtitle_ass_path=ass_path,
        output_path=draft_path,
        background_music_path=music_path,
        max_duration=60.0,  # YouTube Shorts must be under 60s
    )

    size_mb = final_video.stat().st_size / 1e6
    logger.info(f"Final video ready: {final_video} ({size_mb:.1f} MB)")

    # Step 9: Upload to YouTube with tags and SEO description
    state = {"title": script.title, "success": False}
    if settings.youtube.refresh_token and settings.youtube.client_id:
        logger.info("=" * 50)
        logger.info("STEP 9: Uploading to YouTube")
        try:
            video_url = upload_reddit_video(settings.youtube, final_video, story)
            state["youtube_url"] = video_url
            state["success"] = True
            logger.info(f"YouTube URL: {video_url}")
        except Exception as e:
            logger.error(f"YouTube upload failed: {e}")
    else:
        logger.info("STEP 9: Skipped (no YouTube credentials)")

    # Archive
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_dir = settings.completed_dir / f"short_{timestamp}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final_video, dest_dir / final_video.name)
    with open(dest_dir / "info.json", "w") as f:
        json.dump(state, f, indent=2)

    logger.info(f"Archived to {dest_dir}")
    print(f"\nDone! Video: {final_video}")
    if state.get("youtube_url"):
        print(f"YouTube link: {state['youtube_url']}")


if __name__ == "__main__":
    main()
