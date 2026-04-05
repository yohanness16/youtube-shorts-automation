"""CLI — menu to choose between pipelines."""

import os
import sys
from pathlib import Path

os.environ["DOTENV_SILENT"] = "1"

from config import Settings
from utils import setup_logging


def print_banner():
    print("=" * 50)
    print("  YouTube Shorts Automation")
    print("=" * 50)


def validate_settings(settings: Settings, mode: str) -> list[str]:
    """Validate settings for the chosen mode."""
    errors = []
    if mode in ("generate", "reddit"):
        if not settings.script.api_key:
            errors.append("SCRIPT_API_KEY required")
        if not settings.voice.provider:
            errors.append("VOICE_PROVIDER required")
        if settings.voice.provider == "elevenlabs" and not settings.voice.elevenlabs_api_key:
            errors.append("ELEVENLABS_API_KEY required")
        if mode == "generate" and settings.video.provider not in ("mock", "luma", "runway", "pika", "openrouter"):
            errors.append("VIDEO_PROVIDER must be mock, luma, runway, pika, or openrouter")
    elif mode == "review":
        if not settings.vision.api_key:
            errors.append("VISION_API_KEY required for review mode")
        if not settings.vision.model:
            errors.append("VISION_MODEL required for review mode")
        if not settings.script.api_key:
            errors.append("SCRIPT_API_KEY required (for transcription + script gen)")
        if not settings.voice.provider:
            errors.append("VOICE_PROVIDER required")
        if settings.voice.provider == "elevenlabs" and not settings.voice.elevenlabs_api_key:
            errors.append("ELEVENLABS_API_KEY required")
    elif mode == "analyze_only":
        if not settings.vision.api_key:
            errors.append("VISION_API_KEY required for analyze mode")
        if not settings.vision.model:
            errors.append("VISION_MODEL required for analyze mode")
        if not settings.script.api_key:
            errors.append("SCRIPT_API_KEY required (for transcription)")
    return errors


def menu_generate(settings: Settings):
    print("\n[MODE 1] Auto Video Generator")
    print("-" * 40)
    print("Runs the automated pipeline in a loop.")
    print("Each run: research topic -> script -> voice -> video -> upload")

    confirm = input("\nStart the generator? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    from main import main as run_generator
    run_generator()


def menu_review(settings: Settings):
    print("\n[MODE 2] Video Review Generator")
    print("-" * 40)
    print("Analyze a source video, generate a condensed review, upload.")

    print("\nOptions:")
    print("  1) Run a single review (pass YouTube URL or file path)")
    print("  2) Add to queue (runs all pending queue items)")

    choice = input("\nSelect (1/2): ").strip()

    if choice == "1":
        source = input("Enter YouTube URL or video path: ").strip()
        if not source:
            print("Cancelled.")
            return
        from review_main import run_single_review
        result = run_single_review(settings, source)
        if result.get("success"):
            print(f"\nDone! Review video generated: {result.get('script_title', 'Unknown')}")
            if result.get("youtube_url"):
                print(f"YouTube URL: {result['youtube_url']}")
            else:
                print(f"Output: {result.get('final_video', 'N/A')}")
        else:
            print(f"\nFailed. Check failed/ directory for details.")

    elif choice == "2":
        print("\nOptions for queue:")
        print("  a) Add a source to queue")
        print("  b) Process all pending queue items")
        sub = input("Select (a/b): ").strip()
        if sub == "a":
            source = input("Enter YouTube URL or video path: ").strip()
            from review_main import add_to_queue
            job_id = add_to_queue(source)
            print(f"Added to queue: {job_id}")
        elif sub == "b":
            from review_main import process_queue
            process_queue(settings)
        else:
            print("Invalid.")
    else:
        print("Invalid.")


def menu_reddit_stories(settings: Settings):
    print("\n[MODE 3] Reddit Stories Generator")
    print("-" * 40)
    print("Scrapes or generates Reddit stories, adds background video,")
    print("voice, subtitles, and music. Creates Shorts and/or long-form videos.")

    print("\nOptions:")
    print("  1) Generate a single Short (~60s)")
    print("  2) Generate a Long-Form video (2+ min)")
    print("  3) Full Pipeline: N Shorts + 1 Long + Upload all")

    choice = input("\nSelect (1/2/3): ").strip()

    from reddit_pipeline import (
        cleanup_workspace,
        run_reddit_long_video,
        run_reddit_pipeline,
        run_reddit_shorts,
        archive_reddit_run,
    )

    if choice == "1":
        cleanup_workspace(settings)
        print("\nGenerating Reddit Short...")
        result = run_reddit_shorts(settings)
        archive_reddit_run(settings, result)
        if result.get("success"):
            print(f"\nDone! Video: {result.get('script_title', 'Unknown')}")
            if result.get("youtube_url"):
                print(f"YouTube URL: {result['youtube_url']}")
        else:
            print(f"\nFailed. Error: {result.get('error', result.get('step', 'unknown'))}")

    elif choice == "2":
        cleanup_workspace(settings)
        print("\nGenerating Long-Form Reddit Story...")
        result = run_reddit_long_video(settings)
        archive_reddit_run(settings, result, prefix="reddit_long")
        if result.get("success"):
            print(f"\nDone! Video: {result.get('script_title', 'Unknown')}")
            if result.get("youtube_url"):
                print(f"YouTube URL: {result['youtube_url']}")
        else:
            print(f"\nFailed. Error: {result.get('error', result.get('step', 'unknown'))}")

    elif choice == "3":
        n = input("How many Shorts? (default 3): ").strip()
        shorts_count = int(n) if n.isdigit() else 3
        print(f"\nRunning full pipeline: {shorts_count} Shorts + 1 Long-Form...")
        results = run_reddit_pipeline(settings, shorts_count=shorts_count)
        short_ok = sum(1 for s in results["shorts"] if s.get("success"))
        long_ok = results["long_video"] and results["long_video"].get("success")
        print(f"\nResults: {short_ok}/{shorts_count} shorts, {'1 long' if long_ok else '0 long'}")
    else:
        print("Invalid.")


def menu_analyze(settings: Settings):
    print("\n[MODE 4] Analyze Only")
    print("-" * 40)
    print("Download/analyze a video and show the structured analysis.")

    source = input("Enter YouTube URL or video path: ").strip()
    if not source:
        print("Cancelled.")
        return

    import re
    from video_analyzer import download_youtube_video, get_duration, analyze_full_video, VideoAnalysis

    if re.search(r"(youtube\.com|youtu\.be)", source):
        src_dir = settings.output_dir / "source"
        source_path, source_title = download_youtube_video(source, src_dir)
    else:
        source_path = Path(source)
        if not source_path.exists():
            print(f"Error: file not found: {source}")
            return
        source_title = source_path.stem

    duration = get_duration(source_path)
    print(f"\nSource: {source_title}")
    print(f"Duration: {duration:.0f}s")
    print("")

    class FakeSettings:
        script = settings.script
        vision = settings.vision

    analysis = analyze_full_video(
        source_path, source_title, FakeSettings(),
        chunk_size=60,
    )

    print("\n" + "=" * 60)
    print(f"ANALYSIS: {analysis.source_title}")
    print(f"Duration: {analysis.source_duration:.0f}s")
    print(f"Chunks: {len(analysis.chunks)}")
    print("=" * 60)

    for i, chunk in enumerate(analysis.chunks):
        marker = "[KEY]" if chunk.is_key_moment else "     "
        ts = f"[{int(chunk.start//60):02d}:{int(chunk.start%60):02d} - {int(chunk.end//60):02d}:{int(chunk.end%60):02d}]"
        print(f"  {i+1:2d}. {ts} {marker}")
        if chunk.summary:
            print(f"      {chunk.summary}")
        if chunk.transcript:
            print(f"      Says: \"{chunk.transcript[:120]}\"")

    print("\n" + "-" * 60)
    print(f"RECOMMENDED CLIPS FOR REVIEW ({len(analysis.recommended_clips)}):")
    for ts in analysis.recommended_clips:
        print(f"  [{ts}]")

    import json
    cache_file = source_path.parent / "analysis_result.json"
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({
            "title": analysis.source_title,
            "duration": analysis.source_duration,
            "summary": analysis.full_summary,
            "chunks": [
                {
                    "start": c.start, "end": c.end,
                    "summary": c.summary,
                    "transcript": c.transcript,
                    "is_key_moment": c.is_key_moment,
                }
                for c in analysis.chunks
            ],
            "recommended_clips": analysis.recommended_clips,
        }, f, indent=2)

    print(f"\nAnalysis saved to: {cache_file}")


def menu_queue_status():
    """Show the current queue."""
    print("\n[QUEUE]")
    print("-" * 40)

    queue_file = Path(__file__).parent / "queue.json"
    if not queue_file.exists():
        print("Queue is empty. No items.")
        return

    import json
    with open(queue_file) as f:
        queue = json.load(f)

    for status in ["pending", "processing", "completed", "failed"]:
        items = queue.get(status, [])
        if items:
            print(f"\n  {status.upper()} ({len(items)}):")
            for item in items:
                print(f"    - {item.get('source', 'N/A')} (id: {item.get('id', '?')})")
                if "error" in item:
                    print(f"      Error: {item['error']}")

    print()


def menu_growth(settings):
    """Channel growth strategy menu — subscribe to same-niche channels, leave comments."""
    print("\n[MODE 6] Channel Growth")
    print("-" * 40)
    print("Automated channel growth strategy:")
    print("  1. Search YouTube for channels in your niche")
    print("  2. Subscribe to same-niche channels")
    print("  3. Leave contextual engagement comments")
    print("  4. Track progress in promotion log")

    print("\nOptions:")
    print("  1) Run growth for all configured niches")
    print("  2) Run growth for a specific subreddit")
    print("  3) View growth summary")

    choice = input("\nSelect (1/2/3): ").strip()

    if choice == "1":
        from channel_manager import run_growth_for_niche
        from reddit_stories import ALL_NICHES

        niches_str = settings.reddit.niches
        if niches_str.lower() == "all":
            niches_list = ALL_NICHES[:3]
        else:
            niches_list = [n.strip() for n in niches_str.split(",") if n.strip()]

        print(f"\nRunning growth for: {', '.join(niches_list)}")
        for niche in niches_list:
            print(f"\n--- r/{niche} ---")
            result = run_growth_for_niche(niche)
            print(f"  Subscribed: {result['subscribed']}, Comments: {result['commented']}, Errors: {result['errors']}")

        print("\nDone! Growth actions complete.")

    elif choice == "2":
        print("\nAvailable niches (from reddit_stories.py):")
        from reddit_stories import SUBREDDITS
        for sub, vibe in SUBREDDITS.items():
            print(f"  {sub:25s} — {vibe}")

        subreddit = input("\nEnter subreddit: ").strip()
        if not subreddit:
            print("Cancelled.")
            return

        from channel_manager import run_growth_for_niche
        print(f"\nRunning growth for r/{subreddit}...")
        result = run_growth_for_niche(subreddit)
        print(f"  Subscribed: {result['subscribed']}, Comments: {result['commented']}, Errors: {result['errors']}")

    elif choice == "3":
        from channel_manager import print_growth_summary
        print_growth_summary()
    else:
        print("Invalid.")


def main_cli():
    settings = Settings.from_env()

    print_banner()
    print()
    print("  1) Auto Generator    (idea -> script -> video -> upload)")
    print("  2) Video Review      (analyze source -> review -> upload)")
    print("  3) Reddit Stories    (scrape/gen -> background -> edit -> upload)")
    print("  4) Analyze Only      (split chunks -> transcribe -> vision AI)")
    print("  5) Queue Status      (view pending review jobs)")
    print("  6) Channel Growth    (search, subscribe, comment on same-niche channels)")
    print()

    while True:
        choice = input("Select mode (1/2/3/4/5/6) or 'q' to quit: ").strip()

        if choice == "q":
            print("Goodbye.")
            return

        if choice in ("1", "2", "3", "4", "5", "6"):
            break

        print("Invalid choice. Select 1, 2, 3, 4, 5, 6, or 'q'.")

    if choice == "1":
        mode = "generate"
        errors = validate_settings(settings, mode)
        if errors:
            print("\nConfiguration errors:")
            for e in errors:
                print(f"  - {e}")
            print("\nFix in .env and restart.")
            return
        menu_generate(settings)

    elif choice == "2":
        mode = "review"
        errors = validate_settings(settings, mode)
        if errors:
            print("\nConfiguration errors:")
            for e in errors:
                print(f"  - {e}")
            print("\nFix in .env and restart.")
            return
        os.environ.setdefault("PYTHONUNBUFFERED", "1")
        menu_review(settings)

    elif choice == "3":
        mode = "reddit"
        errors = validate_settings(settings, mode)
        if errors:
            print("\nConfiguration errors:")
            for e in errors:
                print(f"  - {e}")
            print("\nFix in .env and restart.")
            return
        os.environ.setdefault("PYTHONUNBUFFERED", "1")
        setup_logging(settings.log_dir)
        menu_reddit_stories(settings)

    elif choice == "4":
        mode = "analyze_only"
        errors = validate_settings(settings, mode)
        if errors:
            print("\nConfiguration errors:")
            for e in errors:
                print(f"  - {e}")
            print("\nFix in .env and restart.")
            return
        os.environ.setdefault("PYTHONUNBUFFERED", "1")
        setup_logging(settings.log_dir)
        menu_analyze(settings)

    elif choice == "5":
        menu_queue_status()

    elif choice == "6":
        mode = "reddit"
        errors = validate_settings(settings, mode)
        if errors:
            print("\nConfiguration errors:")
            for e in errors:
                print(f"  - {e}")
            print("\nFix in .env and restart.")
            return
        setup_logging(settings.log_dir)
        menu_growth(settings)


if __name__ == "__main__":
    main_cli()
