"""Shared utilities — logging, retry, ffmpeg helpers, atomic writes."""

import json
import logging
import subprocess
import time
from functools import wraps
from pathlib import Path
from typing import Any

logger = logging.getLogger("video_automation")


def setup_logging(log_dir: Path = Path("logs")):
    """Configure dual handlers: console (INFO) + file (DEBUG)."""
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    root.addHandler(console)

    fhandler = logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8")
    fhandler.setLevel(logging.DEBUG)
    fhandler.setFormatter(fmt)
    root.addHandler(fhandler)


def retry(max_retries: int = 3, delay: float = 5.0, backoff: float = 2.0, exceptions: tuple = (Exception,)):
    """Decorator with exponential backoff."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_error = None
            for attempt in range(1, max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    last_error = e
                    logger.warning(f"[{fn.__name__}] Attempt {attempt}/{max_retries} failed: {e}")
                    if attempt < max_retries:
                        logger.info(f"Retrying in {current_delay:.0f}s...")
                        time.sleep(current_delay)
                        current_delay *= backoff
            raise last_error
        return wrapper
    return decorator


def run_ffmpeg(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    """Run ffmpeg with logging. Raises on non-zero exit."""
    cmd = ["ffmpeg"] + args
    logger.debug(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        logger.error(f"ffmpeg failed (exit {result.returncode}): {result.stderr[-500:]}")
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")
    return result


def atomic_write(path: Path, data: Any):
    """Write JSON atomically via temp file + rename."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.flush()
    tmp.rename(path)


def read_state(cache_dir: Path) -> dict:
    state_file = cache_dir / "state.json"
    if state_file.exists():
        with open(state_file) as f:
            return json.load(f)
    return {}


def save_state(cache_dir: Path, state: dict):
    atomic_write(cache_dir / "state.json", state)
