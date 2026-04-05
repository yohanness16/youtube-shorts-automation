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


def generate_summary_script(settings: Settings, analysis) -> Script:
    """Generate a condensed review/summary script from a video analysis.

    The LLM uses the chunked analysis (timestamps, transcripts) to write
    a compelling short review script.
    """
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.script.api_key,
        base_url=settings.script.base_url,
    )

    clip_count = settings.clips_per_video
    words_per_clip = 13

    # Build chunk context
    chunk_lines = []
    for i, chunk in enumerate(analysis.chunks):
        ts_min = int(chunk.start // 60)
        ts_sec = int(chunk.start % 60)
        end_min = int(chunk.end // 60)
        end_sec = int(chunk.end % 60)
        line = f"[{ts_min}:{ts_sec:02d} - {end_min}:{end_sec:02d}] {chunk.summary}"
        if chunk.transcript:
            line += f' — Says: "{chunk.transcript[:100]}"'
        if chunk.is_key_moment:
            line += " **[KEY MOMENT]**"
        chunk_lines.append(line)

    clip_timestamps = str(analysis.recommended_clips)

    system_prompt = "You are an expert YouTube Shorts reviewer. You take existing long-form content and create compelling, condensed review Shorts that summarize the key points in an engaging way."

    user_prompt = f"""Write a {settings.target_duration_seconds}-second YouTube Shorts review script about this video.

ORIGINAL VIDEO:
- Title: {analysis.source_title}
- Full analysis: {analysis.full_summary[:500]}
- Duration: {analysis.source_duration:.0f} seconds

CHUNK-BY-CHUNK ANALYSIS:
{chr(10).join(chunk_lines)}

SUGGESTED CLIP TIMESTAMP RANGES (start-end):
{clip_timestamps}

REQUIREMENTS:
- Exactly {clip_count} segments
- Each segment's voiceover text should be ~{words_per_clip} words
- Opening must hook the viewer immediately
- Write commentary that reviews/summarizes the video's content
- Use phrases like "this video shows", "the creator explains", "look at this"
- subtitle_highlight: Pick the single most important word

Return ONLY valid JSON:
{{
  "title": "Short compelling review title",
  "segments": [
    {{
      "text": "Review voiceover text, ~13 words",
      "visual_prompt": "Description of what to show from the source video",
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
            logger.warning(f"Review script has {len(segs)} segments, expected {clip_count}; padding")
            while len(segs) < clip_count:
                segs.append({"text": "", "visual_prompt": "", "subtitle_highlight": ""})

        segments = [ScriptSegment(**s) for s in segs[:clip_count]]
        script = Script(title=data.get("title", f"Review: {analysis.source_title}"), segments=segments)
        logger.info(f"Generated review script: {script.title} ({script.total_words} words, {len(segments)} segments)")
        return script

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Failed to parse review script: {e}")
        segments = [
            ScriptSegment(
                text=f"This video is about {analysis.full_summary[:60]}.",
                visual_prompt=f"Scene from: {analysis.source_title}",
                subtitle_highlight="review",
            )
            for _ in range(clip_count)
        ]
        return Script(title=f"Review: {analysis.source_title}", segments=segments)


def generate_reddit_script(settings: Settings, story, segments_count: int = 12) -> Script:
    """Generate a script from a Reddit story for voiceover.

    The LLM breaks the Reddit story body into segments for timed voiceover,
    each segment being ~5 seconds of speech.
    """
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.script.api_key,
        base_url=settings.script.base_url,
    )

    words_per_clip = 13

    system_prompt = "You are an expert at adapting Reddit stories into YouTube Shorts voiceover scripts. You create engaging, well-paced narrations."

    user_prompt = f"""Adapt this Reddit story into a {segments_count}-segment voiceover script for a YouTube Short.

REDDIT STORY:
Title: r/{story.subreddit} - {story.title}
Body:
{story.body[:2000]}

REQUIREMENTS:
- Exactly {segments_count} segments
- Each segment's text should be ~{words_per_clip} words (fits ~5 seconds of natural speech)
- Opening segment must hook the viewer with the most compelling part of the story
- Segments must flow as a continuous narrative — tell the full story
- End with a strong conclusion or cliffhanger
- visual_prompt: Always use "engaging background gameplay footage, minecraft parkour style, 9:16 vertical"
- subtitle_highlight: Pick the most impactful word from each segment

Return ONLY valid JSON:
{{
  "title": "Short compelling title based on the story",
  "segments": [
    {{
      "text": "Voiceover text, ~{words_per_clip} words",
      "visual_prompt": "engaging background gameplay footage, minecraft parkour style, 9:16 vertical",
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
        if len(segs) < segments_count:
            logger.warning(f"Reddit script has {len(segs)} segments, expected {segments_count}; padding")
            while len(segs) < segments_count:
                segs.append({"text": "", "visual_prompt": "", "subtitle_highlight": ""})

        segments = [ScriptSegment(**s) for s in segs[:segments_count]]
        script = Script(title=data.get("title", story.title), segments=segments)
        logger.info(f"Generated Reddit script: {script.title} ({script.total_words} words, {len(segments)} segments)")
        return script

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Failed to parse Reddit script: {e}")
        return _reddit_fallback_script(story, segments_count)


def generate_reddit_long_script(settings: Settings, story, segments_count: int = 30) -> Script:
    """Generate a script for a long-form Reddit story video (60-120 seconds)."""
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.script.api_key,
        base_url=settings.script.base_url,
    )

    words_per_clip = 13

    system_prompt = "You are an expert at adapting Reddit stories into long-form YouTube video scripts. You create engaging, well-paced narrations that keep viewers watching."

    user_prompt = f"""Adapt this Reddit story into a {segments_count}-segment voiceover script for a long-form YouTube video (120-150 seconds).

REDDIT STORY:
Title: r/{story.subreddit} - {story.title}
Body:
{story.body[:3000]}

REQUIREMENTS:
- Exactly {segments_count} segments
- Each segment's text should be ~{words_per_clip} words
- Tell the COMPLETE story in detail — don't rush
- Opening must hook the viewer instantly
- Segments flow continuously
- subtitle_highlight: Pick the most impactful word
- visual_prompt: Always use "engaging background gameplay footage, minecraft parkour style, 9:16 vertical"

Return ONLY valid JSON:
{{
  "title": "Compelling title",
  "segments": [
    {{
      "text": "Voiceover text, ~{words_per_clip} words",
      "visual_prompt": "engaging background gameplay footage, minecraft parkour style, 9:16 vertical",
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
            temperature=0.75,
        )
        return resp.choices[0].message.content

    try:
        raw = _call()
        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1])
        data = json.loads(raw)

        segs = data.get("segments", [])
        if len(segs) < segments_count:
            logger.warning(f"Long Reddit script has {len(segs)} segments, expected {segments_count}; padding")
            while len(segs) < segments_count:
                segs.append({"text": "", "visual_prompt": "", "subtitle_highlight": ""})

        segments = [ScriptSegment(**s) for s in segs[:segments_count]]
        script = Script(title=data.get("title", story.title), segments=segments)
        logger.info(f"Generated long Reddit script: {script.title} ({script.total_words} words, {len(segments)} segments)")
        return script

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Failed to parse long Reddit script: {e}")
        return _reddit_fallback_script(story, segments_count)


def _reddit_fallback_script(story: object, clip_count: int) -> Script:
    """Fallback when LLM response is unparseable for Reddit stories."""
    body = getattr(story, "body", "")
    words = body.split()
    segment_text = " ".join(words[:clip_count * 13]) if len(words) >= clip_count * 13 else body[:300]

    segments = [
        ScriptSegment(
            text=segment_text,
            visual_prompt="engaging background gameplay footage, minecraft parkour style, 9:16 vertical",
            subtitle_highlight="story",
        )
        for _ in range(clip_count)
    ]
    return Script(title=getattr(story, "title", "Reddit Story"), segments=segments)
