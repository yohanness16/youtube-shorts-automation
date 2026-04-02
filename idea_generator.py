"""Idea generator — researches trending topics in the niche and returns classified ideas."""

import hashlib
import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

from config import Settings
from utils import retry

logger = logging.getLogger("video_automation.ideas")


@dataclass
class TopicIdea:
    title: str
    hook: str  # Opening sentence/hook
    angle: str  # Unique angle or perspective
    sub_category: str


def generate_ideas(settings: Settings, count: int = 5) -> list[TopicIdea]:
    """Ask the script LLM for fresh topic ideas in the configured niche."""
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.script.api_key,
        base_url=settings.script.base_url,
    )

    prompt = f"""Generate {count} unique video topic ideas for a YouTube Shorts channel in the "{settings.niche}" niche.

Each idea should be:
- Specific and factual (not generic)
- Hookable in one sentence
- Suitable for a 60-second video
- Interesting to a general audience

Return ONLY valid JSON in this format, nothing else:
{{
  "ideas": [
    {{
      "title": "Short catchy title",
      "hook": "Opening sentence that grabs attention",
      "angle": "What makes this topic unique or surprising",
      "sub_category": "e.g., ancient-history, ww2, inventions, mysteries"
    }}
  ]
}}"""

    @retry(max_retries=settings.max_retries, delay=settings.retry_delay_seconds, exceptions=(Exception,))
    def _call():
        resp = client.chat.completions.create(
            model=settings.script.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
        )
        return resp.choices[0].message.content

    try:
        raw = _call()
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1])
        data = json.loads(raw)
        ideas = [TopicIdea(**i) for i in data.get("ideas", [])]
        logger.info(f"Generated {len(ideas)} topic ideas")
        return ideas
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Failed to parse idea generation response: {e}")
        # Return fallback ideas so the pipeline can continue
        return _fallback_ideas()


def _fallback_ideas() -> list[TopicIdea]:
    return [
        TopicIdea(
            title="The Library of Alexandria",
            hook="The Library of Alexandria wasn't destroyed in a single fire — it was a slow death over centuries.",
            angle="Debunking the single-fire myth",
            sub_category="ancient-history",
        ),
        TopicIdea(
            title="The Dancing Plague of 1518",
            hook="In 1518, an entire town in France danced for days — without stopping — until people died.",
            angle="Mass hysteria and medieval psychology",
            sub_category="bizarre-history",
        ),
        TopicIdea(
            title="The Voynich Manuscript",
            hook="There's a 600-year-old book that nobody has ever been able to read — not even the best cryptographers.",
            angle="History's most famous unsolved code",
            sub_category="mysteries",
        ),
    ]


def select_best_idea(ideas: list[TopicIdea], cache_dir: Path) -> TopicIdea:
    """Pick the first idea whose title hasn't been used recently."""
    used_file = cache_dir / "ideas" / "used_titles.json"
    used_titles: set[str] = set()
    if used_file.exists():
        with open(used_file) as f:
            used_titles = set(json.load(f))

    for idea in ideas:
        title_hash = hashlib.md5(idea.title.lower().encode()).hexdigest()
        if title_hash not in used_titles:
            # Mark as used
            used_titles.add(title_hash)
            used_file.parent.mkdir(parents=True, exist_ok=True)
            with open(used_file, "w") as f:
                json.dump(sorted(used_titles), f, indent=2)
            return idea

    # All used — return the first one anyway
    logger.warning("All generated ideas have been used before; returning first idea")
    return ideas[0]
