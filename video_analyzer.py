"""Video analyzer — downloads YouTube videos or uses local files,
splits into small chunks, transcribes each, samples frames, and
analyzes each chunk independently via vision LLM. Results are merged.
"""

import base64
import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from utils import retry, run_ffmpeg

logger = logging.getLogger("video_automation.analyzer")

# Max chunk size in seconds — AI models handle short videos better
DEFAULT_CHUNK_SECONDS = 60


@dataclass
class ChunkAnalysis:
    """Analysis of a single time chunk."""
    start: float
    end: float
    summary: str
    transcript: str
    is_key_moment: bool
    description: str


@dataclass
class VideoAnalysis:
    """Merged analysis of the full video."""
    source_path: str
    source_title: str
    source_duration: float
    full_summary: str
    chunks: list[ChunkAnalysis]
    recommended_clips: list[str]  # "start-end" strings
    overall_rating: str


def download_youtube_video(url: str, output_dir: Path) -> tuple[Path, str]:
    """Download YouTube video via yt-dlp."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(output_dir / "source_video.%(ext)s")

    cmd = [
        "yt-dlp",
        "--js-runtime", "node",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", out_template,
        "--no-playlist",
        url,
    ]

    logger.info(f"Downloading: {url}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr[-500:]}")

    video_files = list(output_dir.glob("source_video.*"))
    if not video_files:
        raise RuntimeError("yt-dlp succeeded but no video file found")

    video_path = max(video_files, key=lambda p: p.stat().st_size)
    size_mb = video_path.stat().st_size / 1e6

    meta = subprocess.run(
        ["yt-dlp", "--js-runtime", "node", "--print", "title", "--no-download", url],
        capture_output=True, text=True, timeout=60,
    )
    title = meta.stdout.strip() if meta.returncode == 0 else "Unknown Video"

    logger.info(f"Downloaded: {video_path.name} ({size_mb:.1f} MB) — {title}")
    return video_path, title


def get_duration(video_path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def split_into_chunks(video_path: Path, chunk_dir: Path,
                      chunk_size: int = DEFAULT_CHUNK_SECONDS) -> list[tuple[float, float, Path]]:
    """Split video into small chunks. Returns [(start, end, chunk_path), ...]."""
    chunk_dir.mkdir(parents=True, exist_ok=True)
    duration = get_duration(video_path)
    chunks = []

    i = 0
    t = 0.0
    while t < duration:
        actual_chunk = min(chunk_size, duration - t)
        chunk_path = chunk_dir / f"chunk_{i:03d}.mp4"
        run_ffmpeg([
            "-ss", str(t),
            "-i", str(video_path),
            "-t", str(actual_chunk),
            "-c", "copy",
            "-y", str(chunk_path),
        ])
        end = t + actual_chunk
        chunks.append((t, end, chunk_path))
        t += chunk_size
        i += 1

    logger.info(f"Split into {len(chunks)} chunks of {chunk_size}s each ({duration:.0f}s total)")
    return chunks


def extract_audio_clip(chunk_path: Path, output_path: Path):
    """Extract audio from a single chunk."""
    run_ffmpeg([
        "-i", str(chunk_path),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        "-y", str(output_path),
    ])


def sample_frames(chunk_path: Path, output_path: Path, max_frames: int = 4):
    """Sample frames evenly from a short chunk."""
    duration = get_duration(chunk_path)
    frames = []

    if duration <= 0:
        return frames

    step = max(duration / max_frames, 1)
    for i in range(max_frames):
        t = i * step
        if t >= duration:
            break
        run_ffmpeg([
            "-ss", str(t),
            "-i", str(chunk_path),
            "-frames:v", "1",
            "-q:v", "2",
            "-y", str(output_path),
        ])
        frames.append(output_path)

    return frames


def analyze_chunk(
    chunk_path: Path,
    audio_path: Path,
    start: float,
    end: float,
    transcript: str,
    vision_api_key: str,
    vision_model: str,
    vision_base_url: str,
) -> ChunkAnalysis:
    """Analyze a single short chunk using OpenAI-compatible vision API."""
    from openai import OpenAI

    client = OpenAI(api_key=vision_api_key, base_url=vision_base_url)

    # Sample 3-4 frames from this chunk
    frame_jpg = chunk_path.parent / f"frame_{chunk_path.stem}.jpg"
    sample_frames(chunk_path, frame_jpg, max_frames=4)

    # Build content blocks
    content = []
    if frame_jpg.exists():
        b64 = base64.b64encode(frame_jpg.read_bytes()).decode()
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })

    content.append({
        "type": "text",
        "text": f"""Analyze this {end - start:.0f}s video segment.

TRANSCRIPT: {transcript}

Return ONLY JSON:
{{
    "summary": "What happens in this segment",
    "is_key_moment": true/false — is this a highlight worth including in a review?
}}""",
    })

    @retry(max_retries=2, delay=5.0)
    def _call():
        resp = client.chat.completions.create(
            model=vision_model,
            messages=[{"role": "user", "content": content}],
            temperature=0.3,
            max_tokens=256,
        )
        return resp.choices[0].message.content

    try:
        raw = _call().strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1])
        data = json.loads(raw)
        return ChunkAnalysis(
            start=start,
            end=end,
            summary=data.get("summary", ""),
            transcript=transcript,
            is_key_moment=data.get("is_key_moment", False),
            description=data.get("summary", ""),
        )
    except Exception as e:
        logger.error(f"Chunk [{start:.0f}s-{end:.0f}s] analyze failed: {e}")
        return ChunkAnalysis(
            start=start, end=end, summary="", transcript=transcript,
            is_key_moment=False, description="",
        )


def transcribe_chunk(audio_path: Path, api_key: str, model: str,
                     base_url: str) -> str:
    """Transcribe audio by sending it to a Gemini audio model via OpenRouter."""
    from openai import OpenAI

    if not audio_path.exists() or audio_path.stat().st_size == 0:
        return ""

    client = OpenAI(api_key=api_key, base_url=base_url)

    b64 = base64.b64encode(audio_path.read_bytes()).decode()

    @retry(max_retries=2, delay=5.0)
    def _call():
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": f"data:audio/wav;base64,{b64}",
                                "format": "wav",
                            },
                        },
                        {
                            "type": "text",
                            "text": "Transcribe all speech in this audio. Return only the transcription, no intro or outro.",
                        },
                    ],
                }
            ],
            temperature=0.0,
            max_tokens=500,
        )
        return resp.choices[0].message.content

    try:
        return _call().strip()
    except Exception as e:
        logger.warning(f"Transcription failed for chunk: {e}")
        return ""


def analyze_full_video(
    video_path: Path,
    title: str,
    settings,
    chunk_size: int = DEFAULT_CHUNK_SECONDS,
) -> VideoAnalysis:
    """Full pipeline: split, transcribe each chunk, analyze each, merge."""
    chunk_dir = video_path.parent / "chunks"
    audio_dir = video_path.parent / "audio_chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    # 1. Split video into chunks
    chunks = split_into_chunks(video_path, chunk_dir, chunk_size)
    full_duration = get_duration(video_path)

    # 2. Transcribe AND analyze each chunk
    chunk_analyses: list[ChunkAnalysis] = []

    for start, end, chunk_path in chunks:
        logger.info(f"Processing chunk [{start:.0f}s - {end:.0f}s] / {full_duration:.0f}s")

        # Extract + transcribe audio
        audio_path = audio_dir / f"audio_{int(start):04d}.wav"
        if not audio_path.exists():
            extract_audio_clip(chunk_path, audio_path)
        transcript = transcribe_chunk(
            audio_path,
            api_key=settings.vision.api_key,
            model=getattr(settings.vision, 'transcription_model', settings.vision.model),
            base_url=settings.vision.base_url,
        )

        # Analyze with vision LLM
        analysis = analyze_chunk(
            chunk_path=chunk_path,
            audio_path=audio_path,
            start=start,
            end=end,
            transcript=transcript,
            vision_api_key=settings.vision.api_key,
            vision_model=settings.vision.model,
            vision_base_url=settings.vision.base_url,
        )
        chunk_analyses.append(analysis)

    # 3. Merge results
    key_moments = [a for a in chunk_analyses if a.is_key_moment]
    recommended = [f"{a.start:.0f}-{a.end:.0f}" for a in key_moments]

    # If too few key moments, add some non-key ones for variety
    if len(recommended) < settings.clips_per_video and len(chunk_analyses) >= settings.clips_per_video:
        step = len(chunk_analyses) // settings.clips_per_video
        for a in chunk_analyses[::step][:settings.clips_per_video]:
            tag = f"{a.start:.0f}-{a.end:.0f}"
            if tag not in recommended:
                recommended.append(tag)

    full_summary = "\n".join(
        f"[{a.start:.0f}s-{a.end:.0f}s] {a.summary}"
        for a in chunk_analyses
    )

    # 4. Save cached analysis
    cache_data = {
        "title": title,
        "duration": full_duration,
        "full_summary": full_summary,
        "chunks": [
            {
                "start": a.start, "end": a.end,
                "summary": a.summary,
                "transcript": a.transcript,
                "is_key_moment": a.is_key_moment,
            }
            for a in chunk_analyses
        ],
        "recommended_clips": recommended,
    }
    cache_file = video_path.parent / "cached_analysis.json"
    with open(cache_file, "w") as f:
        json.dump(cache_data, f, indent=2)

    logger.info(f"Analysis complete: {len(key_moments)} key moments, {len(recommended)} total clips")

    return VideoAnalysis(
        source_path=str(video_path),
        source_title=title,
        source_duration=full_duration,
        full_summary=full_summary,
        chunks=chunk_analyses,
        recommended_clips=recommended,
        overall_rating=f"{len(key_moments)} of {len(chunk_analyses)} chunks are highlights",
    )


def load_cached_analysis(video_path: Path) -> VideoAnalysis | None:
    """Load previously cached analysis for a video."""
    cache_file = video_path.parent / "cached_analysis.json"
    if not cache_file.exists():
        return None

    with open(cache_file) as f:
        data = json.load(f)

    chunks = [
        ChunkAnalysis(
            start=c["start"], end=c["end"],
            summary=c["summary"], transcript=c.get("transcript", ""),
            is_key_moment=c["is_key_moment"], description=c["summary"],
        )
        for c in data.get("chunks", [])
    ]

    return VideoAnalysis(
        source_path=str(video_path),
        source_title=data.get("title", "Unknown"),
        source_duration=data["duration"],
        full_summary=data.get("full_summary", ""),
        chunks=chunks,
        recommended_clips=data.get("recommended_clips", []),
        overall_rating="",
    )
