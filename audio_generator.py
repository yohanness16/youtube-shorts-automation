"""Audio generator — ElevenLabs or OpenAI TTS per-segment voiceover."""

import logging
from pathlib import Path

from config import Settings
from script_generator import Script
from utils import retry

logger = logging.getLogger("video_automation.audio")


def generate_voiceover(settings: Settings, script: Script, output_dir: Path) -> Path:
    """Generate per-segment voiceover audio, then concatenate into one file.

    Returns path to the full_voiceover.wav file.
    """
    provider = settings.voice.provider
    segments = script.segments
    seg_dir = output_dir / "audio"
    seg_dir.mkdir(parents=True, exist_ok=True)

    # Generate each segment's audio
    seg_durations: list[float] = []
    for i, seg in enumerate(segments):
        if not seg.text.strip():
            # Generate silence for empty segments
            from utils import run_ffmpeg
            silence_len = settings.clip_duration_seconds
            run_ffmpeg([
                "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
                "-t", str(silence_len),
                "-c:a", "pcm_s16le",
                "-y", str(seg_dir / f"seg_{i:03d}.wav"),
            ])
            seg_durations.append(float(silence_len))
            continue

        seg_path = seg_dir / f"seg_{i:03d}.wav"

        if provider == "elevenlabs":
            _generate_elevenlabs(settings, seg.text, seg_path)
        elif provider == "openai":
            _generate_openai_tts(settings, seg.text, seg_path)
        else:
            raise ValueError(f"Unknown voice provider: {provider}")

        # Get segment duration
        from utils import run_ffmpeg
        probe = run_ffmpeg([
            "-i", str(seg_path),
            "-f", "null", "-",
        ])
        # Parse duration from stderr - simpler: use ffprobe
        import subprocess
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(seg_path)],
            capture_output=True, text=True,
        )
        dur = float(result.stdout.strip()) if result.returncode == 0 else settings.clip_duration_seconds
        seg_durations.append(dur)
        logger.info(f"Segment {i+1} audio: {len(seg.text)} words, {dur:.2f}s")

    # Concatenate all segments into one file
    full_wav = seg_dir / "full_voiceover.wav"
    from utils import run_ffmpeg
    if all(d > 0 for d in seg_durations):
        # Build concat filter
        inputs = []
        filters = []
        for i in range(len(segments)):
            inputs += ["-i", str(seg_dir / f"seg_{i:03d}.wav")]
        concat_args = "".join(f"[{i}:a]" for i in range(len(segments)))
        filters.append(f"{concat_args}concat=n={len(segments)}:v=0:a=1[out]")
        run_ffmpeg([*inputs, "-filter_complex", ";".join(filters), "-map", "[out]", "-y", str(full_wav)])
    else:
        # Fallback: use concat demuxer
        list_file = seg_dir / "concat_list.txt"
        with open(list_file, "w") as f:
            for i in range(len(segments)):
                f.write(f"file 'seg_{i:03d}.wav'\n")
        run_ffmpeg([
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c:a", "pcm_s16le",
            "-y", str(full_wav),
        ])

    logger.info(f"Full voiceover: {full_wav}")
    return full_wav


@retry(max_retries=3, delay=5.0, exceptions=(Exception,))
def _generate_elevenlabs(settings: Settings, text: str, output_path: Path):
    """Generate audio using ElevenLabs API."""
    import httpx

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{settings.voice.elevenlabs_voice_id}"
    headers = {
        "xi-api-key": settings.voice.elevenlabs_api_key,
        "Content-Type": "application/json",
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "output_format": "wav_44100",
        "settings": {"stability": 0.5, "similarity_boost": 0.75},
    }

    logger.debug(f"ElevenLabs TTS: '{text[:50]}...'")
    with httpx.Client(timeout=60) as client:
        resp = client.post(url, headers=headers, json=data)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(resp.content)


@retry(max_retries=3, delay=5.0, exceptions=(Exception,))
def _generate_openai_tts(settings: Settings, text: str, output_path: Path):
    """Generate audio using OpenAI TTS API."""
    from openai import OpenAI

    client = OpenAI(api_key=settings.voice.openai_api_key)
    logger.debug(f"OpenAI TTS: '{text[:50]}...'")

    response = client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text,
        response_format="wav",
    )
    response.stream_to_file(str(output_path))
