"""Subtitle generator — creates SRT from per-segment timing, converts to ASS for styled rendering."""

import logging
import math
from pathlib import Path

from script_generator import Script

logger = logging.getLogger("video_automation.subtitles")


def generate_srt(
    script: Script,
    seg_durations: list[float],
    output_dir: Path,
) -> Path:
    """Generate SRT file from script segments with timing info.

    Words are distributed proportionally across each segment's audio duration.
    """
    srt_path = output_dir / "subtitles.srt"
    lines: list[str] = []
    entry = 0
    current_time = 0.0

    for i, seg in enumerate(script.segments):
        if not seg.text.strip():
            continue
        duration = seg_durations[i] if i < len(seg_durations) else 5.0
        words = seg.text.split()
        word_count = len(words)
        time_per_word = duration / max(word_count, 1)

        for j, word in enumerate(words):
            start = current_time + j * time_per_word
            end = start + time_per_word
            # Keep word display short enough (max 1 word visible at time, or short groups)
            # For Shorts, show 1-3 words at a time
            entry += 1
            lines.append(str(entry))
            lines.append(f"{_fmt_time(start)} --> {_fmt_time(end)}")
            lines.append(word)
            lines.append("")

        current_time += duration

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info(f"Generated SRT: {srt_path} ({entry} word entries)")
    return srt_path


def srt_to_ass(
    srt_path: Path,
    script: Script,
    output_dir: Path,
    font_size: int = 76,
    font_name: str = "DejaVu Sans",
    center_animated: bool = True,
) -> Path:
    """Convert SRT to ASS format with big centered animated subtitles.

    Centered in the middle of screen, large and readable,
    with a pop-in animation effect.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ass_path = output_dir / "subtitles.ass"

    # Alignment 5 = bottom-center, MarginV controls vertical position;
    # on a 1920-high canvas, MarginV=880 puts text near the center band.
    ass_header = f"""[Script Info]
Title: Reddit Story Subtitles
ScriptType: v4.00+
WrapStyle: 2
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,105,105,2,0,1,5,4,4,2,20,20,880,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # Read SRT entries and convert
    srt_text = srt_path.read_text(encoding="utf-8")
    entries: list[tuple[str, str, str]] = []
    current_entry: dict[str, str] = {}

    for line in srt_text.split("\n"):
        line = line.strip()
        if "-->" in line:
            current_entry["time"] = line
        elif line and line.isdigit() and "time" not in current_entry:
            current_entry["num"] = line
        elif line == "" and current_entry.get("time"):
            if "text" in current_entry:
                start_str, end_str = current_entry["time"].split(" --> ")
                entries.append((_convert_time(start_str.strip()), _convert_time(end_str.strip()), current_entry.get("text", "")))
            current_entry = {}
        elif line and "time" in current_entry:
            current_entry["text"] = current_entry.get("text", "") + (" " if current_entry.get("text") else "") + line

    # Group consecutive single-word entries into 2-4 word lines for impact
    grouped: list[tuple[str, str, str]] = []
    current_group_start: str | None = None
    current_group_end: str | None = None
    current_words: list[str] = []

    for start, end, text in entries:
        current_words.append(text)
        if current_group_start is None:
            current_group_start = start
        current_group_end = end

        # Emit every 3 words
        if len(current_words) >= 3:
            grouped.append((current_group_start, current_group_end, " ".join(current_words)))
            current_words = []
            current_group_start = None
            current_group_end = None

    if current_words:
        grouped.append((current_group_start, current_group_end, " ".join(current_words)))

    # Build dialogue lines with pop-in animation
    lines = [ass_header]
    for start, end, text in grouped:
        escaped = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
        # \fad(fade_in_ms, fade_out_ms) for smooth pop-in/out
        # \an5 = center alignment override
        animated = f"{{\\fad(120,180)}}{{\\an5}}{escaped}"
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{animated}")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    logger.info(f"Generated ASS: {ass_path} ({len(grouped)} lines, font-size {font_size}, centered)")
    return ass_path


def _fmt_time(seconds: float) -> str:
    """Convert seconds to SRT time format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def create_reddit_subtitle_style(
    srt_path: Path,
    output_dir: Path,
    font_name: str = "DejaVu Sans",
    highlight_font_name: str = "DejaVu Sans",
) -> Path:
    """Convert SRT to Reddit-shorts style ASS subtitles.

    YouTube Shorts Reddit story style:
    - LARGE, bold, CENTERED text in the middle of screen
    - White text with thick black outline + gradient shadow
    - 2-3 words per line for maximum readability
    """
    ass_path = output_dir / "reddit_subtitles.ass"

    ass_header = f"""[Script Info]
Title: Reddit Story Subtitles
ScriptType: v4.00+
WrapStyle: 2
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},72,&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,-1,0,0,0,100,100,3,0,1,6,3,5,50,50,860,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    srt_text = srt_path.read_text(encoding="utf-8")
    parsed = _parse_srt_entries(srt_text)

    # Group single words into 2-3 word lines for more impact
    grouped: list[tuple[str, str, str]] = []
    buf_start = None
    buf_end = None
    buf_words = []

    for start, end, word in parsed:
        buf_words.append(word)
        if buf_start is None:
            buf_start = start
        buf_end = end

        if len(buf_words) >= 3:
            text = " ".join(buf_words)
            escaped = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
            grouped.append((buf_start, buf_end, escaped))
            buf_words = []
            buf_start = None
            buf_end = None

    # Flush remaining
    if buf_words:
        text = " ".join(buf_words)
        escaped = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
        grouped.append((buf_start, buf_end, escaped))

    lines = [ass_header]
    for start, end, text in grouped:
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    logger.info(f"Generated Reddit ASS: {ass_path} ({len(grouped)} grouped lines, font-size 64)")
    return ass_path


def _parse_srt_entries(srt_text: str) -> list[tuple[str, str, str]]:
    """Parse SRT content and return (start, end, text) tuples in ASS time format."""
    entries: list[tuple[str, str, str]] = []
    current_entry: dict[str, str] = {}

    for line in srt_text.split("\n"):
        line = line.strip()
        if "-->" in line:
            current_entry["time"] = line
        elif line and line.isdigit() and "time" not in current_entry:
            current_entry["num"] = line
        elif line == "" and current_entry.get("time"):
            if "text" in current_entry:
                start_str, end_str = current_entry["time"].split(" --> ")
                entries.append((_convert_time(start_str.strip()), _convert_time(end_str.strip()), current_entry.get("text", "")))
            current_entry = {}
        elif line and "time" in current_entry:
            current_entry["text"] = current_entry.get("text", "") + (" " if current_entry.get("text") else "") + line
    return entries


def _convert_time(srt_time: str) -> str:
    """Convert SRT time HH:MM:SS,mmm to ASS time H:MM:SS.cs"""
    parts = srt_time.replace(",", ":").split(":")
    h, m, s, cs = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]) // 10
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
