"""Smart voice selection based on story topic/subreddit."""

# Edge-TTS voices mapped to subreddit moods
REDDIT_VOICES = {
    # AITA / drama - warm, conversational
    "AmItheAsshole": "en-US-GuyNeural",
    "confessions": "en-US-JennyNeural",
    "trueoffmychest": "en-US-AvaNeural",
    # Funny / light
    "tifu": "en-US-AndrewNeural",
    "MaliciousCompliance": "en-US-BrianNeural",
    # Revenge / dramatic
    "pettyrevenge": "en-US-ChristopherNeural",
    "prorevenue": "en-US-EricNeural",
    "EntitledParents": "en-US-RogerNeural",
    # Horror / creepy
    "LetsNotMeet": "en-US-GuyNeural",
    "nosleep": "en-US-SteffanNeural",
}

# Default voices for each mood category
DEFAULT_VOICES = {
    "drama": "en-US-GuyNeural",
    "funny": "en-US-AndrewNeural",
    "horror": "en-US-SteffanNeural",
    "revenge": "en-US-EricNeural",
}


def get_voice_for_subreddit(subreddit: str) -> str:
    """Get the best TTS voice for a given subreddit."""
    return REDDIT_VOICES.get(subreddit, REDDIT_VOICES.get("AmItheAsshole"))
