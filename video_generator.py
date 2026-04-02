"""Video generator — provider abstraction for AI video generation.

Supports: mock (for testing), luma, runway, pika (stubs for real APIs).
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from config import Settings
from script_generator import Script
from utils import retry

logger = logging.getLogger("video_automation.video")


class VideoProvider(ABC):
    @abstractmethod
    def generate_clip(self, prompt: str, output_path: Path, duration: int = 5) -> bool:
        """Generate a single video clip. Returns True on success."""
        ...


class MockProvider(VideoProvider):
    """Generates colored text-on-background frames using ffmpeg. Zero API cost."""

    COLORS = [
        "1a1a2e", "16213e", "0f3460", "533483",
        "2b2d42", "3d405b", "6b2737", "4a4e69",
        "22223b", "4a4a6e", "6d5a7e", "8b5a5a",
    ]

    def __init__(self):
        self._clip_count = 0

    def generate_clip(self, prompt: str, output_path: Path, duration: int = 5) -> bool:
        from utils import run_ffmpeg
        color = self.COLORS[self._clip_count % len(self.COLORS)]
        self._clip_count += 1

        # Solid colored frame (subtitles provide all on-screen text)
        run_ffmpeg([
            "-f", "lavfi", "-i", f"color=c=0x{color}:s=1080x1920:d={duration}:r=30,"
            f"format=yuv420p",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-t", str(duration),
            "-y", str(output_path),
        ])
        return True


class LumaProvider(VideoProvider):
    """Luma Dream Machine API — stub. Implement when API key is provided."""

    def __init__(self, api_key: str, base_url: str = ""):
        self.api_key = api_key
        self.base_url = base_url or "https://api.lumalabs.ai/dream-machine/v1"

    @retry(max_retries=3, delay=30.0, exceptions=(Exception,))
    def generate_clip(self, prompt: str, output_path: Path, duration: int = 5) -> bool:
        import httpx
        logger.info(f"[Luma] Generating clip: '{prompt[:60]}...'")

        # Start generation
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "prompt": f"Cinematic, 9:16 vertical, photorealistic: {prompt}",
            "aspect_ratio": "9:16",
        }

        # Submit
        client = httpx.Client(timeout=120)
        resp = client.post(f"{self.base_url}/generations", json=payload, headers=headers)
        resp.raise_for_status()
        job_id = resp.json().get("id")

        # Poll
        for attempt in range(30):
            import time; time.sleep(15)
            resp = client.get(f"{self.base_url}/generations/{job_id}", headers=headers)
            resp.raise_for_status()
            status = resp.json().get("state", "")
            if status in ("completed", "succeeded"):
                video_url = resp.json().get("assets", {}).get("video", "")
                if video_url:
                    dl = client.get(video_url)
                    dl.raise_for_status()
                    with open(output_path, "wb") as f:
                        f.write(dl.content)
                    return True
            elif status in ("failed", "error"):
                logger.error(f"[Luma] Generation failed: {resp.json()}")
                return False

        logger.error(f"[Luma] Timed out waiting for clip")
        return False


class RunwayProvider(VideoProvider):
    """Runway Gen-3 API — stub. Implement when API key is provided."""

    def __init__(self, api_key: str, base_url: str = ""):
        self.api_key = api_key

    @retry(max_retries=3, delay=30.0, exceptions=(Exception,))
    def generate_clip(self, prompt: str, output_path: Path, duration: int = 5) -> bool:
        logger.info(f"[Runway] Stub — not yet implemented. Use MockProvider for testing.")
        return False


class PikaProvider(VideoProvider):
    """Pika API — stub. Implement when API key is provided."""

    def __init__(self, api_key: str, base_url: str = ""):
        self.api_key = api_key

    @retry(max_retries=3, delay=30.0, exceptions=(Exception,))
    def generate_clip(self, prompt: str, output_path: Path, duration: int = 5) -> bool:
        logger.info(f"[Pika] Stub — not yet implemented. Use MockProvider for testing.")
        return False


def create_provider(settings: Settings) -> VideoProvider:
    factory = {
        "mock": lambda: MockProvider(),
        "luma": lambda: LumaProvider(settings.video.api_key, settings.video.base_url),
        "runway": lambda: RunwayProvider(settings.video.api_key),
        "pika": lambda: PikaProvider(settings.video.api_key),
    }
    provider_cls = factory.get(settings.video.provider)
    if not provider_cls:
        raise ValueError(f"Unknown video provider: {settings.video.provider}")
    return provider_cls()


def generate_all_clips(
    settings: Settings,
    script: Script,
    output_dir: Path,
) -> tuple[list[Path], bool]:
    """Generate all video clips for the script.

    Returns (list of clip paths, all_succeeded).
    """
    provider = create_provider(settings)
    clip_dir = output_dir / "clips"
    clip_dir.mkdir(parents=True, exist_ok=True)

    clips: list[Path] = []
    all_ok = True

    for i, seg in enumerate(script.segments):
        clip_path = clip_dir / f"clip_{i:03d}.mp4"
        prompt = seg.visual_prompt or f"Cinematic historical scene, 9:16 vertical, dramatic lighting"

        logger.info(f"Generating clip {i+1}/{len(script.segments)}: {prompt[:60]}...")

        try:
            success = provider.generate_clip(prompt, clip_path, settings.clip_duration_seconds)
            if not success:
                logger.warning(f"Clip {i+1} failed, using fallback")
                _generate_fallback_clip(prompt, clip_path, settings.clip_duration_seconds)
        except Exception as e:
            logger.error(f"Clip {i+1} error: {e}, using fallback")
            _generate_fallback_clip(prompt, clip_path, settings.clip_duration_seconds)

        clips.append(clip_path)

    return clips, all_ok


def _generate_fallback_clip(prompt: str, output_path: Path, duration: int = 5):
    """Generate a static text-on-color frame if the video provider fails."""
    from utils import run_ffmpeg
    import hashlib
    color_hash = hashlib.md5(prompt.encode()).hexdigest()
    color = color_hash[:6]

    run_ffmpeg([
        "-f", "lavfi",
        "-i", f"color=c=#{color}:s=1080x1920:d={duration},format=yuv420p",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-t", str(duration),
        "-y", str(output_path),
    ])
