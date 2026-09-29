"""Tiny HTTP layer: retry with backoff, and an on-disk cache.

Every source we use is free and keyless, but rate-limited (GeckoTerminal is
30 req/min). Caching raw responses keeps re-runs instant and keeps us well
inside the limits while iterating on the model.
"""
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / "cache"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
# Jupiter rejects requests without a User-Agent with a 403, so HEADERS is
# not optional here.


def _cache_path(key: str) -> Path:
    return CACHE / f"{hashlib.sha256(key.encode()).hexdigest()[:20]}.json"


def _load(key: str, max_age: float | None):
    p = _cache_path(key)
    if not p.exists():
        return None
    if max_age is not None and time.time() - p.stat().st_mtime > max_age:
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def _store(key: str, value) -> None:
    CACHE.mkdir(exist_ok=True)
    _cache_path(key).write_text(json.dumps(value))


def _attempt(req: urllib.request.Request, tries: int, pause: float):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = e
            if i < tries - 1:
                time.sleep(pause * (i + 1))
    raise last


def is_cached(key: str, max_age: float | None = None) -> bool:
    """Whether a request is already on disk, so callers can skip rate-limit sleeps."""
    return _load(key, max_age) is not None


def get(url: str, *, cache: bool = True, max_age: float | None = None,
        tries: int = 4, pause: float = 8.0):
    if cache:
        hit = _load(url, max_age)
        if hit is not None:
            return hit
    out = _attempt(urllib.request.Request(url, headers=HEADERS), tries, pause)
    if cache:
        _store(url, out)
    return out


def post(url: str, body: dict, *, cache: bool = True,
         max_age: float | None = None, tries: int = 3, pause: float = 4.0):
    key = url + json.dumps(body, sort_keys=True)
    if cache:
        hit = _load(key, max_age)
        if hit is not None:
            return hit
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={**HEADERS, "Content-Type": "application/json"})
    out = _attempt(req, tries, pause)
    if cache:
        _store(key, out)
    return out
