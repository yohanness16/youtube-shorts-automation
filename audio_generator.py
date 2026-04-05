"""Audio generator — ElevenLabs or OpenAI TTS per-segment voiceover."""

import logging
import time
import subprocess
from pathlib import Path

from config import Settings
from script_generator import Script
from utils import retry, run_ffmpeg

logger = logging.getLogger("video_automation.audio")


def _get_segment_duration(seg_path: Path, clip_duration_seconds: int) -> float:
    """Get audio file duration via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(seg_path)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except (ValueError, TypeError):
        return float(clip_duration_seconds)


def generate_voiceover(settings: Settings, script: Script, output_dir: Path, voice: str = "") -> Path:
    """Generate per-segment voiceover audio, then concatenate into one file.

    Returns path to the full_voiceover.wav file.
    """
    provider = settings.voice.provider
    segments = script.segments
    seg_dir = output_dir / "audio"
    seg_dir.mkdir(parents=True, exist_ok=True)

    # Edge-TTS voice based on subreddit (default to GuyNeural if not specified)
    edge_voice = voice or "en-US-GuyNeural"

    seg_durations: list[float] = []
    for i, seg in enumerate(segments):
        if not seg.text.strip():
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

        try:
            if provider == "elevenlabs":
                _generate_elevenlabs(settings, seg.text, seg_path)
            elif provider == "openai":
                _generate_openai_tts(settings, seg.text, seg_path)
            elif provider == "edge":
                _generate_edge_tts(seg.text, seg_path, edge_voice)
            else:
                raise ValueError(f"Unknown voice provider: {provider}")

            dur = _get_segment_duration(seg_path, settings.clip_duration_seconds)
            seg_durations.append(dur)
            logger.info(f"Segment {i+1} audio: {len(seg.text.split())} words, {dur:.2f}s")

            # Small delay between edge-tts calls to avoid rate limiting
            if provider == "edge":
                time.sleep(0.5)
        except Exception as e:
            logger.warning(f"Segment {i+1} TTS failed ({e}), using silence")
            run_ffmpeg([
                "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
                "-t", str(settings.clip_duration_seconds),
                "-c:a", "pcm_s16le",
                "-y", str(seg_path),
            ])
            seg_durations.append(float(settings.clip_duration_seconds))

    # Concatenate all segments
    full_wav = seg_dir / "full_voiceover.wav"
    list_file = seg_dir / "concat_list.txt"
    with open(list_file, "w") as f:
        for i in range(len(segments)):
            p = seg_dir / f"seg_{i:03d}.wav"
            if p.exists() and p.stat().st_size > 0:
                f.write(f"file '{p.absolute()}'\n")

    run_ffmpeg([
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c:a", "pcm_s16le",
        "-y", str(full_wav),
    ])

    logger.info(f"Full voiceover: {full_wav}")
    return full_wav


@retry(max_retries=2, delay=3.0, exceptions=(Exception,))
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


@retry(max_retries=2, delay=3.0, exceptions=(Exception,))
def _generate_openai_tts(settings: Settings, text: str, output_path: Path):
    """Generate audio using OpenAI-compatible TTS API."""
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


@retry(max_retries=2, delay=3.0, exceptions=(Exception,))
def _generate_edge_tts(text: str, output_path: Path, voice: str = "en-US-GuyNeural"):
    """Generate audio using Edge-TTS (free, no API key)."""
    import edge_tts

    logger.debug(f"Edge-TTS ({voice}): '{text[:50]}...'")
    comm = edge_tts.Communicate(text, voice=voice)
    comm.save_sync(str(output_path))
