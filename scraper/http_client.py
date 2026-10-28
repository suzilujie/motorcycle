# -*- coding: utf-8 -*-
"""HTTP layer: GBK percent-encoding, GB18030 decoding, rate limiting,
retry with backoff, and on-disk raw HTML cache (resumable crawling).
"""

from __future__ import annotations

import hashlib
import os
import random
import threading
import time
import urllib.error
import urllib.request

import config

_CACHE_LOCK = threading.Lock()
_RATE_LOCK = threading.Lock()
_LAST_CALL = [0.0]
_STAT = {"request": 0, "cache_hit": 0, "fail": 0}


def gbk_encode(value: str) -> str:
    """Percent-encode a string using GBK bytes (server expects GBK)."""
    out = []
    for byte in value.encode("gbk", errors="ignore"):
        out.append("%%%02X" % byte)
    return "".join(out)


def gbk_decode(value: str) -> str:
    """Decode a percent-encoded GBK query value back to text."""
    raw = bytearray()
    i = 0
    while i < len(value):
        if value[i] == "%" and i + 2 < len(value):
            raw.append(int(value[i + 1:i + 3], 16))
            i += 3
        else:
            raw.extend(value[i].encode("gbk", errors="ignore"))
            i += 1
    return bytes(raw).decode("gb18030", errors="ignore")


def _cache_path(url: str) -> str:
    name = hashlib.md5(url.encode("utf-8")).hexdigest() + ".html"
    return os.path.join(config.RAW_DIR, name)


def _rate_wait() -> None:
    with _RATE_LOCK:
        now = time.monotonic()
        delta = config.MIN_INTERVAL - (now - _LAST_CALL[0])
        if delta > 0:
            time.sleep(delta)
        _LAST_CALL[0] = time.monotonic()


def _open(url: str) -> bytes:
    request = urllib.request.Request(url, headers={
        "User-Agent": config.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Connection": "close",
    })
    with urllib.request.urlopen(request, timeout=config.TIMEOUT) as resp:
        return resp.read()


def fetch_bytes(url: str, use_cache: bool = True) -> bytes:
    """Download raw bytes with retry; cached on disk when possible."""
    path = _cache_path(url)
    if use_cache and os.path.exists(path):
        with _CACHE_LOCK:
            _STAT["cache_hit"] += 1
        with open(path, "rb") as fh:
            return fh.read()
    last_error = None
    for attempt in range(config.MAX_RETRY):
        _rate_wait()
        try:
            data = _open(url)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            last_error = exc
            with _CACHE_LOCK:
                _STAT["fail"] += 1
            time.sleep(config.RETRY_BACKOFF ** attempt + random.random() * 0.3)
            continue
        with _CACHE_LOCK:
            _STAT["request"] += 1
        with open(path, "wb") as fh:
            fh.write(data)
        return data
    raise RuntimeError("fetch failed: %s (%s)" % (url, last_error))


def fetch_text(url: str, use_cache: bool = True) -> str:
    """Download a page and decode it from GB18030."""
    return fetch_bytes(url, use_cache=use_cache).decode(
        config.PAGE_ENCODING, errors="ignore")


def download_file(url: str, dest: str) -> bool:
    """Download a binary file; returns False when already present."""
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return False
    data = fetch_bytes(url, use_cache=False)
    if not data:
        return False
    tmp = dest + ".part"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, dest)
    return True


def stats() -> dict:
    with _CACHE_LOCK:
        return dict(_STAT)
