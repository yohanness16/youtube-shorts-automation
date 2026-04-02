"""Background music generator — creates ambient cinematic music using ffmpeg synthesis."""

import logging
from pathlib import Path

from utils import run_ffmpeg

logger = logging.getLogger("video_automation.music")


def generate_background_music(
    output_path: Path,
    duration: float = 10,
) -> Path:
    """Generate ambient background music using ffmpeg audio synthesis.

    Creates a low-volume ambient drone that won't distract from voiceover.
    Uses sine wave + brown noise blend for a cinematic feel.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Two separate lavfi inputs, mixed together at low volume
    run_ffmpeg([
        "-f", "lavfi", "-i", f"sine=frequency=220:duration={duration}",
        "-f", "lavfi", "-i", f"anoisesrc=color=brown:duration={duration}",
        "-filter_complex",
        f"[0]volume=0.05[s1];"
        f"[1]lowpass=f=440,volume=0.03[n1];"
        f"[s1][n1]amix=inputs=2:duration=shortest:dropout_transition=1[out]",
        "-map", "[out]",
        "-c:a", "pcm_s16le",
        "-y", str(output_path),
    ])

    logger.info(f"Generated background music: {output_path} ({duration}s)")
    return output_path
