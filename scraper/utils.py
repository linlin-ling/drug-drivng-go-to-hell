"""Rate limiting, retry logic, and progress persistence."""
import json
import random
import time
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

PROGRESS_FILE = Path("data/raw/progress.json")


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    return {"downloaded": [], "failed": []}


def save_progress(progress: dict) -> None:
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_FILE.write_text(json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8")


def polite_sleep(min_s: float = 1.5, max_s: float = 3.5) -> None:
    time.sleep(random.uniform(min_s, max_s))


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
    })
    return session


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=4, max=60))
def safe_get(session: requests.Session, url: str, **kwargs) -> requests.Response:
    resp = session.get(url, timeout=30, **kwargs)
    resp.raise_for_status()
    return resp


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=4, max=60))
def safe_post(session: requests.Session, url: str, **kwargs) -> requests.Response:
    resp = session.post(url, timeout=30, **kwargs)
    resp.raise_for_status()
    return resp
