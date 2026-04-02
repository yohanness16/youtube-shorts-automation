"""Script generator — generates full script with 12 coherent segments and video prompts."""

import json
import logging
from dataclasses import dataclass

from config import Settings
from idea_generator import TopicIdea
from utils import retry

logger = logging.getLogger("video_automation.scripts")


@dataclass
class ScriptSegment:
    text: str  # Voiceover text (~12-15 words)
    visual_prompt: str  # Prompt for AI video generation
    subtitle_highlight: str  # Key word to emphasize


@dataclass
class Script:
    title: str
    segments: list[ScriptSegment]

    @property
    def total_words(self) -> int:
        return sum(len(s.text.split()) for s in self.segments)


def generate_script(settings: Settings, idea: TopicIdea) -> Script:
    """Generate a complete 12-segment script with video prompts in a single API call."""
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.script.api_key,
        base_url=settings.script.base_url,
    )

    clip_count = settings.clips_per_video
    words_per_clip = 13  # ~5 seconds of natural speech

    system_prompt = f"""You are an expert YouTube Shorts scriptwriter specializing in {settings.niche} content. You write compelling, factually interesting scripts that hook viewers instantly."""

    user_prompt = f"""Write a {settings.target_duration_seconds}-second YouTube Shorts script about this topic.

TOPIC:
- Title: {idea.title}
- Hook: {idea.hook}
- Angle: {idea.angle}
- Sub-category: {idea.sub_category}

REQUIREMENTS:
- Exactly {clip_count} segments
- Each segment's voiceover text should be ~{words_per_clip} words (fits ~{settings.clip_duration_seconds} seconds of natural speech)
- Total script ~{clip_count * words_per_clip} words
- Opening segment must use the hook to grab attention immediately
- Segments must flow as a continuous narrative — each connects to the next
- End with a strong closing statement or surprising fact
- visual_prompt: Describe what should be shown (cinematic, specific visuals, NOT text-on-screen)
- subtitle_highlight: Pick the single most important word from the segment's text

Return ONLY valid JSON, nothing else:
{{
  "title": "Short compelling title",
  "segments": [
    {{
      "text": "Voiceover text here, around 13 words",
      "visual_prompt": "Detailed visual description for AI video generation, cinematic style, 9:16 vertical",
      "subtitle_highlight": "keyword"
    }}
  ]
}}"""

    @retry(max_retries=settings.max_retries, delay=settings.retry_delay_seconds, exceptions=(Exception,))
    def _call():
        resp = client.chat.completions.create(
            model=settings.script.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )
        return resp.choices[0].message.content

    try:
        raw = _call()
        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1])
        data = json.loads(raw)

        segs = data.get("segments", [])
        if len(segs) < clip_count:
            logger.warning(f"Script has {len(segs)} segments, expected {clip_count}; padding with empty segments")
            while len(segs) < clip_count:
                segs.append({"text": "", "visual_prompt": "", "subtitle_highlight": ""})

        segments = [ScriptSegment(**s) for s in segs[:clip_count]]
        script = Script(title=data.get("title", idea.title), segments=segments)
        logger.info(f"Generated script: {script.title} ({script.total_words} words, {len(segments)} segments)")
        return script

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Failed to parse script generation response: {e}")
        # Return a fallback script
        return _fallback_script(idea, clip_count)


def _fallback_script(idea: TopicIdea, clip_count: int) -> Script:
    """Minimal fallback script when LLM response is unparseable."""
    text = idea.hook
    segments = [
        ScriptSegment(
            text=text,
            visual_prompt=f"Cinematic historical scene related to {idea.title}, 9:16 vertical, dramatic lighting",
            subtitle_highlight=idea.title.split()[0],
        )
        for _ in range(clip_count)
    ]
    return Script(title=idea.title, segments=segments)
