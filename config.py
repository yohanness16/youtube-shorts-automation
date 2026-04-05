"""Application configuration — loads .env, validates settings, ensures directories."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _required_env(key: str) -> str:
    val = os.getenv(key, "")
    if not val:
        raise ValueError(f"Missing required env variable: {key}")
    return val


@dataclass
class ScriptConfig:
    provider: str = "qwen"
    api_key: str = ""
    model: str = "qwen-plus"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"


@dataclass
class VoiceConfig:
    provider: str = "elevenlabs"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "EXAVITQu4vr4xnSDxMaL"
    openai_api_key: str = ""


@dataclass
class VideoConfig:
    provider: str = "mock"
    api_key: str = ""
    base_url: str = ""


@dataclass
class VisionConfig:
    provider: str = ""
    api_key: str = ""
    model: str = ""
    base_url: str = ""
    transcription_model: str = ""


@dataclass
class YouTubeConfig:
    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    privacy_status: str = "private"


@dataclass
class RedditConfig:
    niches: str = "all"  # comma-separated subreddit list
    background_video_source: str = "youtube"  # youtube, local
    background_video_folder: str = ""  # path to local video folder
    background_video_query: str = "minecraft parkour gameplay no copyright"


@dataclass
class Settings:
    script: ScriptConfig = field(default_factory=ScriptConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    reddit: RedditConfig = field(default_factory=RedditConfig)

    niche: str = "history-facts"
    source_video: str = ""  # YouTube URL or local file path (review mode)
    review_mode: bool = False
    clips_per_video: int = 12
    clip_duration_seconds: int = 5
    target_duration_seconds: int = 60
    max_retries: int = 3
    retry_delay_seconds: int = 30
    poll_interval_seconds: int = 600
    max_videos_per_day: int = 0  # 0 = unlimited
    background_music_path: str = ""

    base_dir: Path = field(default_factory=lambda: Path(__file__).parent)
    output_dir: Path = field(init=False)
    cache_dir: Path = field(init=False)
    completed_dir: Path = field(init=False)
    failed_dir: Path = field(init=False)
    log_dir: Path = field(init=False)

    def __post_init__(self):
        self.output_dir = self.base_dir / "output"
        self.cache_dir = self.base_dir / "cache"
        self.completed_dir = self.base_dir / "completed"
        self.failed_dir = self.base_dir / "failed"
        self.log_dir = self.base_dir / "logs"

    @classmethod
    def from_env(cls) -> "Settings":
        script = ScriptConfig(
            provider=os.getenv("SCRIPT_PROVIDER", "qwen"),
            api_key=os.getenv("SCRIPT_API_KEY", ""),
            model=os.getenv("SCRIPT_MODEL", "qwen-plus"),
            base_url=os.getenv("SCRIPT_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        )
        voice = VoiceConfig(
            provider=os.getenv("VOICE_PROVIDER", "elevenlabs"),
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", ""),
            elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        )
        video = VideoConfig(
            provider=os.getenv("VIDEO_PROVIDER", "mock"),
            api_key=os.getenv("VIDEO_API_KEY", ""),
            base_url=os.getenv("VIDEO_BASE_URL", ""),
        )
        youtube = YouTubeConfig(
            client_id=os.getenv("YOUTUBE_CLIENT_ID", ""),
            client_secret=os.getenv("YOUTUBE_CLIENT_SECRET", ""),
            refresh_token=os.getenv("YOUTUBE_REFRESH_TOKEN", ""),
            privacy_status=os.getenv("YOUTUBE_PRIVACY_STATUS", "private"),
        )
        reddit = RedditConfig(
            niches=os.getenv("REDDIT_NICHES", "all"),
            background_video_source=os.getenv("BACKGROUND_VIDEO_SOURCE", "youtube"),
            background_video_folder=os.getenv("BACKGROUND_VIDEO_FOLDER", ""),
            background_video_query=os.getenv("BACKGROUND_VIDEO_QUERY", "minecraft parkour gameplay no copyright"),
        )
        vision = VisionConfig(
            provider=os.getenv("VISION_PROVIDER", ""),
            api_key=os.getenv("VISION_API_KEY", ""),
            model=os.getenv("VISION_MODEL", ""),
            base_url=os.getenv("VISION_BASE_URL", ""),
            transcription_model=os.getenv("TRANSCRIPTION_MODEL", "google/gemini-2.5-flash-lite-preview-09-2025"),
        )
        return cls(
            script=script,
            voice=voice,
            video=video,
            vision=vision,
            youtube=youtube,
            reddit=reddit,
            niche=os.getenv("NICHE", "history-facts"),
            source_video=os.getenv("SOURCE_VIDEO", ""),
            review_mode=os.getenv("REVIEW_MODE", "false").lower() == "true",
            clips_per_video=int(os.getenv("CLIPS_PER_VIDEO", "12")),
            clip_duration_seconds=int(os.getenv("CLIP_DURATION_SECONDS", "5")),
            target_duration_seconds=int(os.getenv("TARGET_DURATION_SECONDS", "60")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            retry_delay_seconds=int(os.getenv("RETRY_DELAY_SECONDS", "30")),
            poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "600")),
            max_videos_per_day=int(os.getenv("MAX_VIDEOS_PER_DAY", "0")),
            background_music_path=os.getenv("BACKGROUND_MUSIC_PATH", ""),
        )

    def ensure_directories(self):
        for d in [
            self.output_dir,
            self.output_dir / "clips",
            self.output_dir / "audio",
            self.output_dir / "subs",
            self.cache_dir,
            self.cache_dir / "ideas",
            self.completed_dir,
            self.failed_dir,
            self.log_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def validate(self, mode: str = "generate") -> list[str]:
        errors: list[str] = []
        if not self.script.api_key:
            errors.append("SCRIPT_API_KEY is required")
        if not self.voice.provider or self.voice.provider not in ("elevenlabs", "openai", "edge"):
            errors.append("VOICE_PROVIDER must be 'elevenlabs', 'openai', or 'edge'")
        if self.voice.provider == "elevenlabs" and not self.voice.elevenlabs_api_key:
            errors.append("ELEVENLABS_API_KEY is required when VOICE_PROVIDER=elevenlabs")
        if self.voice.provider == "openai" and not self.voice.openai_api_key:
            errors.append("OPENAI_API_KEY is required when VOICE_PROVIDER=openai")
        if mode != "reddit":
            if self.video.provider not in ("mock", "luma", "runway", "pika", "openrouter"):
                errors.append("VIDEO_PROVIDER must be 'mock', 'luma', 'runway', 'pika', or 'openrouter'")
            if self.video.provider != "mock" and not self.video.api_key:
                errors.append("VIDEO_API_KEY is required for real video providers")
        return errors
