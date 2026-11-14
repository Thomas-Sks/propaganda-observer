"""Collecteur Google News RSS (sans clé) : articles récents par mot-clé, domaine source en clair."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import feedparser
import httpx
import tldextract

from observer.core.models import ContentItem, pseudonymize

UA = "Mozilla/5.0 (X11; Linux x86_64) propaganda-observer/0.1"


def _url(q: str, lang: str, country: str, when: str | None, start: str | None = None, end: str | None = None) -> str:
    hl = f"{lang}-{country}" if lang != "en" else "en-US"
    gl = country if lang != "en" else "US"
    period = f" after:{start} before:{end}" if start and end else (f" when:{when}" if when else "")
    return (f"https://news.google.com/rss/search?q={quote(q + period)}"
            f"&hl={hl}&gl={gl}&ceid={gl}:{lang}")


# Édition Google News par défaut pour une langue (générique, extensible) ; sinon le pays de l'événement.
LANG_COUNTRY = {"en": "US", "fr": "FR", "de": "DE", "es": "ES", "it": "IT", "pt": "BR", "nl": "NL", "pl": "PL",
                "uk": "UA", "ru": "RU", "ro": "RO", "cs": "CZ", "sk": "SK", "hu": "HU", "el": "GR", "sv": "SE",
                "fi": "FI", "da": "DK", "no": "NO", "tr": "TR", "ar": "EG", "fa": "IR", "he": "IL", "hi": "IN",
                "id": "ID", "ja": "JP", "ko": "KR", "zh": "TW", "vi": "VN", "th": "TH", "bg": "BG", "sr": "RS",
                "hr": "HR", "lt": "LT", "lv": "LV", "et": "EE", "ka": "GE", "hy": "AM", "az": "AZ", "kk": "KZ"}


def registrable(url: str) -> str:
    e = tldextract.extract(url)
    return ".".join(p for p in (e.domain, e.suffix) if p)


async def fetch(query: str, lang: str = "fr", country: str = "FR", when: str | None = "1d",
                event: str | None = None, start: str | None = None, end: str | None = None) -> list[ContentItem]:
    """`start`/`end` (AAAA-MM-JJ) : fenêtre de l'événement ; sinon `when` (ex. 1d)."""
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": UA}, follow_redirects=True) as c:
        r = await c.get(_url(query, lang, country, when, start, end))
        r.raise_for_status()
    feed = feedparser.parse(r.text)
    out = []
    for e in feed.entries:
        src = getattr(e, "source", None) or {}
        src_url = src.get("href") or src.get("url") or ""
        domain = registrable(src_url) if src_url else "unknown"
        try:
            ts = parsedate_to_datetime(e.published).astimezone(timezone.utc)
        except Exception:
            ts = datetime.now(timezone.utc)
        pid = hashlib.sha1(e.link.encode()).hexdigest()[:16]
        title = e.title.rsplit(" - ", 1)[0] if " - " in e.title else e.title
        out.append(ContentItem(platform="web", post_id=pid, url=e.link, ts=ts,
                               author_pseudo=pseudonymize("web", domain), text=title,
                               urls_canon=[domain], lang=lang, event=event, format="article",
                               metrics={}, hashtags=[]))
        out[-1].account.verified = None
    return out
