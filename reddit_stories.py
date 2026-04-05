"""Reddit stories — scrape real posts or generate AI Reddit-style stories."""

import json
import logging
import random
import subprocess
from dataclasses import dataclass

from config import Settings

logger = logging.getLogger("video_automation.reddit")

# Subreddits grouped by vibe
SUBREDDITS = {
    "AmItheAsshole": "AITA / relationship drama",
    "confessions": "confessions",
    "trueoffmychest": "confessions",
    "tifu": "funny/entertaining",
    "MaliciousCompliance": "funny/entertaining",
    "pettyrevenge": "revenge",
    "prorevenge": "revenge",
    "EntitledParents": "drama",
    "LetsNotMeet": "horror/scary",
    "nosleep": "horror/scary",
}

ALL_NICHES = list(SUBREDDITS.keys())


@dataclass
class RedditStory:
    subreddit: str
    title: str
    body: str
    url: str
    author: str
    upvotes: int
    is_scraped: bool

    @property
    def full_title(self) -> str:
        return f"r/{self.subreddit}: {self.title}"


def scrape_reddit_stories(subreddit: str, count: int = 10) -> list[RedditStory]:
    """Scrape top posts from a subreddit using Reddit's public JSON API."""
    url = f"https://old.reddit.com/r/{subreddit}/top/.json?t=week&limit={max(count, 5)}"
    headers = {
        "User-Agent": "reddit-shorts-generator/1.0"
    }

    logger.info(f"Scraping r/{subreddit} for stories...")
    try:
        result = subprocess.run(
            ["curl", "-s", "-A", "reddit-shorts-generator/1.0", url],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            logger.warning(f"curl failed for r/{subreddit}: {result.stderr[:200]}")
            return []

        data = json.loads(result.stdout)
        posts = data.get("data", {}).get("children", [])

        stories = []
        for post in posts:
            p = post.get("data", {})
            body = p.get("selftext", "").strip()
            if not body or len(body) < 100:
                continue  # Skip posts without substantial body text

            stories.append(RedditStory(
                subreddit=subreddit,
                title=_clean_title(p.get("title", "")),
                body=body,
                url=f"https://reddit.com{p.get('permalink', '')}",
                author=p.get("author", "u/anonymous"),
                upvotes=int(p.get("ups", 0)),
                is_scraped=True,
            ))
            if len(stories) >= count:
                break

        logger.info(f"Scraped {len(stories)} stories from r/{subreddit}")
        return stories
    except Exception as e:
        logger.warning(f"Scraping r/{subreddit} failed: {e}")
        return []


def generate_reddit_story(settings: Settings, niche: str) -> RedditStory:
    """Generate a Reddit-style story using the script LLM."""
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.script.api_key,
        base_url=settings.script.base_url,
    )

    system_prompt = f"""You are an expert at writing realistic, engaging Reddit stories. Your stories feel authentic and go viral frequently."""

    user_prompt = f"""Write a Reddit post for r/{niche}. Make it engaging, dramatic, and realistic.

Format the output as valid JSON with these fields:
{{
  "title": "A catchy post title",
  "body": "The full story body, at least 300-500 words. Write in first person, make it dramatic and engaging. Use casual/reddit-style language.",
  "subreddit": "{niche}"
}}

Requirements:
- First person POV
- Casual, conversational Reddit tone
- Include specific details to make it feel real
- Build tension and resolution
- Body should be 300-500 words (long enough for a good video)
- Make it entertaining and dramatic

Return ONLY valid JSON, nothing else."""

    try:
        resp = client.chat.completions.create(
            model=settings.script.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.85,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1])
        data = json.loads(raw)
        return RedditStory(
            subreddit=data.get("subreddit", niche),
            title=data["title"],
            body=data["body"],
            url="",
            author="u/ai_generated",
            upvotes=0,
            is_scraped=False,
        )
    except Exception as e:
        logger.error(f"AI story generation failed: {e}")
        return None


def pick_story(settings: Settings) -> RedditStory:
    """Try scraping first, fall back to AI generation."""
    niches = _get_niches(settings)
    chosen_niche = random.choice(niches)

    # Try scraping
    logger.info(f"Trying to scrape r/{chosen_niche}")
    stories = scrape_reddit_stories(chosen_niche, count=8)

    if stories:
        # Sort by upvotes, pick from top half for quality
        stories.sort(key=lambda s: s.upvotes, reverse=True)
        pick = random.choice(stories[:max(len(stories) // 2, 1)])
        logger.info(f"Picked scraped story: {pick.title} ({pick.upvotes} upvotes)")
        return pick

    # Fall back to AI generation
    logger.info(f"Falling back to AI generation for r/{chosen_niche}")
    story = generate_reddit_story(settings, chosen_niche)
    if story:
        logger.info(f"Generated AI story: {story.title}")
    return story


def _get_niches(settings: Settings) -> list[str]:
    """Parse configured niches."""
    raw = settings.reddit.niches.strip()
    if raw.lower() == "all":
        return ALL_NICHES[:5]  # Pick a subset for variety
    return [n.strip() for n in raw.split(",") if n.strip()]


def _clean_title(title: str) -> str:
    """Remove AITA-style prefixes like [Update], [EDIT], etc."""
    import re
    # Remove bracketed prefixes
    title = re.sub(r"^\[.*?\]\s*", "", title).strip()
    # Remove AITA prefixes that clutter the title
    title = re.sub(r"^(AITA|TIFU|Confession|Let's Not Meet|Malicious Compliance)\s*", "", title, flags=re.IGNORECASE).strip()
    return title or "Untitled Reddit Story"


def split_story_to_paragraphs(body: str) -> list[str]:
    """Split a Reddit story body into readable paragraphs."""
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    if not paragraphs and body.strip():
        paragraphs = [body.strip()]
    return paragraphs
