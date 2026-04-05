"""Background music generator — story-based mood music with ambient background sound via ffmpeg synthesis."""

import logging
import random
from pathlib import Path

from utils import run_ffmpeg

logger = logging.getLogger("video_automation.music")

# Different mood presets with varied instrumentation
MOOD_PRESETS = {
    "drama": {
        # Tension-building, low piano + subtle strings
        "layers": [
            ("sine", "f=130", "volume=0.015"),       # Low piano-ish drone
            ("sine", "f=261.6", "volume=0.01"),       # Mid note
            ("anoisesrc", "color=brown:r=44100", "lowpass=f=300,volume=0.02"),  # Warm rumble
        ],
    },
    "funny": {
        # Light, bouncy feel
        "layers": [
            ("sine", "f=329.6", "volume=0.012"),      # E4 - light tone
            ("sine", "f=392", "volume=0.008"),        # G4
            ("sine", "f=196", "volume=0.01"),         # G3 bass
            ("anoisesrc", "color=pink:r=44100", "highpass=f=8000,volume=0.005"),  # Soft shimmer
        ],
    },
    "horror": {
        # Dark, unsettling, low rumble + high tension
        "layers": [
            ("sine", "f=55", "volume=0.02"),          # Low rumble (A1)
            ("sine", "f=58.3", "volume=0.015"),       # Slightly dissonant (Bb1)
            ("anoisesrc", "color=brown:r=44100", "bandpass=f=400:w=2,volume=0.03"),  # Eerie mid
        ],
    },
    "revenge": {
        # Driving, intense, medium bass
        "layers": [
            ("sine", "f=146.8", "volume=0.018"),      # D3
            ("sine", "f=220", "volume=0.012"),        # A3
            ("anoisesrc", "color=brown:r=44100", "lowpass=f=200,volume=0.025"),  # Sub bass rumble
        ],
    },
    "sad": {
        # Melancholic, slow, soft tones
        "layers": [
            ("sine", "f=220", "volume=0.012"),        # A3 - soft
            ("sine", "f=261.6", "volume=0.01"),       # C4
            ("sine", "f=87.3", "volume=0.015"),       # F2 bass
            ("anoisesrc", "color=pink:r=44100", "bandpass=f=1000:w=3,volume=0.008"),  # Gentle ambience
        ],
    },
    "triumph": {
        # Uplifting, bold, victorious
        "layers": [
            ("sine", "f=329.6", "volume=0.015"),      # E4
            ("sine", "f=392", "volume=0.012"),        # G4
            ("sine", "f=523.3", "volume=0.01"),       # C5
            ("sine", "f=164.8", "volume=0.012"),      # E3 bass
            ("anoisesrc", "color=pink:r=44100", "highpass=f=5000,volume=0.004"),  # Bright shimmer
        ],
    },
}

# Keywords used to guess story mood
MOOD_KEYWORDS = {
    "horror": ["scary", "creepy", "dark", "terrifying", "haunted", "ghost", "nightmare",
               "paranormal", "eerie", "chilling", "stalker", "watching", "followed"],
    "revenge": ["revenge", "payback", "destroyed", "karma", "served", "crushed",
                "instant karma", "got what he deserved", "fired", "banned"],
    "funny": ["funny", "hilarious", "laugh", "stupid", "ridiculous", "absurd",
              "comedy", "idiot", "dumb", "accidentally", "whoops"],
    "sad": ["sad", "cry", "tragic", "lost", "died", "grief", "depressed",
            "heartbreak", "lonely", "alone", "miss", "goodbye", "cancer", "hospice"],
    "triumph": ["won", "victory", "success", "beat", "incredible", "amazing",
                "proved", "achieved", "champion", "hero"],
}


def _detect_mood(story_text: str = "", subreddit: str = "") -> str:
    """Detect the mood from story content and subreddit."""
    lower_text = story_text.lower() if story_text else ""
    lower_sub = subreddit.lower() if subreddit else ""

    # Score each mood by keyword matches
    scores = {}
    for mood, keywords in MOOD_KEYWORDS.items():
        score = sum(lower_text.count(kw) for kw in keywords)
        scores[mood] = score

    # Subreddit hints
    subreddit_moods = {
        "nosleep": "horror",
        "letsnotmeet": "horror",
        "creepy": "horror",
        "prorevenge": "revenge",
        "pettyrevenge": "revenge",
        "tifu": "funny",
        "maliciouscompliance": "funny",
        "entitledparents": "drama",
        "trueoffmychest": "sad",
        "confessions": "sad",
        "aita": "drama",
        "amiytheasshole": "drama",
    }
    for sub, mood in subreddit_moods.items():
        if sub in lower_sub:
            scores[mood] = scores.get(mood, 0) + 3

    best_mood = max(scores, key=scores.get) if scores and max(scores.values()) > 0 else "drama"
    return best_mood


def generate_background_music(
    output_path: Path,
    duration: float = 10,
    mood: str = "",
    subreddit: str = "",
    story_text: str = "",
    add_ambient_bg: bool = True,
) -> Path:
    """Generate story-matched background music with optional ambient sound layer."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not mood:
        if story_text or subreddit:
            mood = _detect_mood(story_text=story_text, subreddit=subreddit)
        else:
            mood = "drama"

    preset = MOOD_PRESETS.get(mood, MOOD_PRESETS["drama"])

    # Build filter chain
    inputs = []
    filters = []

    for i, (src_type, src_args, filter_str) in enumerate(preset["layers"]):
        inputs += ["-f", "lavfi", "-i", f"{src_type}={src_args}:duration={duration}"]
        filters.append(f"[{i}:a]{filter_str}[m{i}]")

    # Optional ambient background hum/atmosphere layer
    if add_ambient_bg:
        amb_idx = len(preset["layers"])
        inputs += ["-f", "lavfi", "-i", f"anoisesrc=color=pink:r=44100:duration={duration}"]
        filters.append(f"[{amb_idx}:a]bandpass=f=600:w=2,volume=0.01[a_amb]")
        amb_mix = "".join(f"[m{i}]" for i in range(len(preset["layers"]))) + "[a_amb]"
        filters.append(f"{amb_mix}amix=inputs={len(preset['layers']) + 1}:duration=shortest:dropout_transition=1[out]")
    else:
        mix = "".join(f"[m{i}]" for i in range(len(preset["layers"])))
        filters.append(f"{mix}amix=inputs={len(preset['layers'])}:duration=shortest:dropout_transition=1[out]")

    cmd = [
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[out]",
        "-c:a", "pcm_s16le",
        "-y", str(output_path),
    ]

    run_ffmpeg(cmd)
    logger.info(f"Generated {mood} background music: {output_path} ({duration:.1f}s, {len(preset['layers']) + (1 if add_ambient_bg else 0)} layers)")
    return output_path