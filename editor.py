"""Video editor — ffmpeg assembly: normalize clips, merge, add audio + subtitles."""

import logging
from pathlib import Path
from typing import Optional

from utils import run_ffmpeg

logger = logging.getLogger("video_automation.editor")


def assemble_video(
    clip_paths: list[Path],
    voiceover_path: Path,
    subtitle_ass_path: Path,
    output_path: Path,
    background_music_path: Optional[Path] = None,
) -> Path:
    """Assemble the final video in a single ffmpeg pass.
    """
    # Step 1: Verify all clips exist
    for p in clip_paths:
        if not p.exists():
            raise FileNotFoundError(f"Missing clip: {p}")
    if not voiceover_path.exists():
        raise FileNotFoundError(f"Missing voiceover: {voiceover_path}")
    if not subtitle_ass_path.exists():
        raise FileNotFoundError(f"Missing subtitle ASS: {subtitle_ass_path}")

    # Step 2: Create concat list
    concat_path = output_path.parent / "concat_list.txt"
    with open(concat_path, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p.absolute()}'\n")

    # Step 3: Build single ffmpeg call with filter_complex
    # Input 0: concat video stream
    # Input 1: voiceover wav
    # Input 2: background music wav (optional)
    music_input = background_music_path and background_music_path.exists()
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

    # Video filter: scale + pad + ass subtitles
    video_filter = (
        f"scale=1080:1920:force_original_aspect_ratio=decrease,"
        f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
        f"ass='{subtitle_ass_path.absolute()}'"
    )

    # Audio filter: voiceover + optional background music
    audio_filter = f"[{voice_idx}:a]volume=1.0[a_voice]"
    if music_idx is not None:
        audio_filter += f";[{music_idx}:a]volume=0.08[a_bg]"
        audio_filter += ";[a_voice][a_bg]amix=inputs=2:duration=first[a_out]"
    else:
        audio_filter += ";[a_voice]anull[a_out]"

    cmd.extend([
        "-filter_complex", audio_filter,
        "-vf", video_filter,
        "-map", "0:v",
        "-map", "[a_out]",
        "-shortest",
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "192k",
        "-y",
        str(output_path),
    ])

    logger.info(f"Running ffmpeg assembly...")
    run_ffmpeg(cmd, timeout=600)
    logger.info(f"Assembled video: {output_path}")
    return output_path


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
