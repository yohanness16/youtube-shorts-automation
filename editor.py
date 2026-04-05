"""Video editor — ffmpeg assembly: normalize clips, merge, add audio + subtitles."""

import logging
import subprocess
from pathlib import Path
from typing import Optional

from utils import run_ffmpeg

logger = logging.getLogger("video_automation.editor")


def _get_duration(path: Path) -> float:
    """Get media file duration in seconds via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except (ValueError, TypeError):
        return 0.0


def assemble_video(
    clip_paths: list[Path],
    voiceover_path: Path,
    subtitle_ass_path: Path,
    output_path: Path,
    background_music_path: Optional[Path] = None,
    bg_music_volume: float = 0.20,  # Clearly audible but doesn't overpower voice
    target_duration: float = 0,
    max_duration: float = 0,
) -> Path:
    """Assemble the final video in a single ffmpeg pass.

    If max_duration > 0 and voiceover exceeds it, the voiceover will be
    sped up (atempo) and subtitles are re-timed to match — crucial for
    YouTube Shorts (< 60s) sync.

    If target_duration > 0 and voiceover is under it, the video will be
    padded with silence to hit the target length.
    """
    # Step 1: Verify all clips exist
    for p in clip_paths:
        if not p.exists():
            raise FileNotFoundError(f"Missing clip: {p}")
    if not voiceover_path.exists():
        raise FileNotFoundError(f"Missing voiceover: {voiceover_path}")
    if not subtitle_ass_path.exists():
        raise FileNotFoundError(f"Missing subtitle ASS: {subtitle_ass_path}")

    # Measure actual voiceover duration
    voice_duration = _get_duration(voiceover_path)

    # Step 2: Create concat list
    concat_path = output_path.parent / "concat_list.txt"
    with open(concat_path, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p.absolute()}'\n")

    # Step 3: Build single ffmpeg call with filter_complex
    music_input = bool(background_music_path and background_music_path.exists())
    voice_idx = 1
    music_idx = 2 if music_input else None

    cmd = [
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_path),
        "-i", str(voiceover_path),
    ]
    if music_input:
        cmd.extend(["-i", str(background_music_path)])

    # Check if voiceover needs speeding up
    speed_factor = 1.0
    final_video_duration = voice_duration

    if max_duration > 0 and voice_duration > max_duration:
        speed_factor = voice_duration / max_duration
        final_video_duration = max_duration
        logger.info(f"Speeding up voice by {speed_factor:.3f}x to fit within {max_duration:.1f}s")

        # Re-time subtitles: rewrite ASS with scaled timings
        subtitle_ass_path = _rescale_ass_subtitles(
            subtitle_ass_path, output_path.parent, speed_factor
        )
    elif target_duration > 0 and voice_duration < target_duration:
        final_video_duration = target_duration

    # Video filter: scale + pad + ass subtitles
    video_filter = (
        f"scale=1080:1920:force_original_aspect_ratio=decrease,"
        f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
        f"ass='{subtitle_ass_path.absolute()}'"
    )

    # Audio filter: voiceover + optional background music (low volume)
    audio_filter = f"[{voice_idx}:a]volume=1.0"

    if speed_factor != 1.0:
        audio_filter += f",atempo={speed_factor:.4f}[a_voice]"
    else:
        audio_filter += "[a_voice]"

    # Merge with optional background music at low volume so it doesn't distract
    if music_idx is not None:
        audio_filter += f";[{music_idx}:a]volume={bg_music_volume:.4f}[a_bg]"
        audio_filter += ";[a_voice][a_bg]amix=inputs=2:duration=longest[a_out]"
    else:
        audio_filter += ";[a_voice]anull[a_out]"

    cmd.extend([
        "-filter_complex", audio_filter,
        "-vf", video_filter,
        "-map", "0:v",
        "-map", "[a_out]",
        "-t", str(final_video_duration),
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "192k",
        "-y",
        str(output_path),
    ])

    logger.info(f"Running ffmpeg assembly... (voice={voice_duration:.1f}s, output={final_video_duration:.1f}s, bg_music_vol={bg_music_volume:.2f})")
    run_ffmpeg(cmd, timeout=600)
    logger.info(f"Assembled video: {output_path} ({_get_duration(output_path):.1f}s)")
    return output_path


def _rescale_ass_subtitles(ass_path: Path, output_dir: Path, speed_factor: float) -> Path:
    """Rewrite ASS subtitle file with timings divided by speed_factor.

    When audio is sped up by atempo, timings must shrink by the same factor.
    """
    import re

    new_path = output_dir / "subtitles_scaled.ass"
    content = ass_path.read_text(encoding="utf-8")

    # Parse ASS time format: H:MM:SS.cs
    def rescale_time(match: re.Match) -> str:
        h, m, s_cs = int(match.group(1)), int(match.group(2)), match.group(3)
        total_seconds = h * 3600 + m * 60 + float(s_cs)
        new_seconds = total_seconds / speed_factor
        new_h = int(new_seconds // 3600)
        new_m = int((new_seconds % 3600) // 60)
        new_s = new_seconds % 60
        return f"{new_h}:{new_m:02d}:{new_s:06.3f}"

    # Match ASS times: H:MM:SS.cs
    content = re.sub(r"(\d+):(\d{2}):(\d{2}\.\d+)", rescale_time, content)
    new_path.write_text(content, encoding="utf-8")
    logger.info(f"Rescaled subtitles by {speed_factor:.3f}x: {new_path}")
    return new_path


def make_thumbnail(clip_path: Path, output_path: Path):
    """Extract a frame from the middle of the clip as a thumbnail."""
    import subprocess
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(clip_path)],
        capture_output=True, text=True,
    )
    duration = float(result.stdout.strip()) if result.returncode == 0 else 5.0
    midpoint = duration / 2

    run_ffmpeg([
        "-i", str(clip_path),
        "-ss", str(midpoint),
        "-frames:v", "1",
        "-y", str(output_path),
    ])
