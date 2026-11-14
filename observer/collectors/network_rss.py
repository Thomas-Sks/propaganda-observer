"""Collecteur RSS des RÉSEAUX DE RÉFÉRENCE (registre `data/registry/reference_networks.yaml`), générique.

Chaque réseau documenté qui publie des flux RSS (ex. Pravda / Portal Kombat) est suivi ; seules les publications
pertinentes pour l'événement observé sont gardées ensuite (filtre de pertinence commun).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from observer.core.models import AccountMeta, ContentItem, pseudonymize

log = logging.getLogger("observer.network_rss")
UA = "Mozilla/5.0 (X11; Linux x86_64) propaganda-observer/0.1"


async def _one(c: httpx.AsyncClient, url: str, tag: str, event: str | None) -> list[ContentItem]:
    from bs4 import BeautifulSoup
    from observer.collectors.gnews import registrable  # noqa: F401
    domain = url.split("//")[-1].split("/")[0]
    r = await c.get(url)
    if r.status_code != 200:
        return []
    out = []
    for e in feedparser.parse(r.text).entries:
        html = (e.get("content") or [{}])[0].get("value") or e.get("summary") or ""
        soup = BeautifulSoup(html, "html.parser")
        body = soup.get_text("\n", strip=True)
        links = [a["href"] for a in soup.select("a[href]") if a["href"].startswith("http")]
        try:
            ts = parsedate_to_datetime(e.published).astimezone(timezone.utc)
        except Exception:
            ts = datetime.now(timezone.utc)
        out.append(ContentItem(
            platform="web", post_id="net-" + hashlib.sha1(e.link.encode()).hexdigest()[:16], url=e.link, ts=ts,
            author_pseudo=pseudonymize("web", domain), text=f"{e.title}\n{body}"[:4000],
            links=links[:20], urls_canon=[domain], event=event, format="article",
            account=AccountMeta(known_network=tag),
        ))
    return out


async def fetch(event: str | None = None) -> list[ContentItem]:
    from observer.tools.networks import networks
    feeds = [(n["rss_template"].format(sub=sub), n["label"]) for n in networks() if n.get("rss") for sub in n["rss"]]
    async with httpx.AsyncClient(timeout=25, headers={"User-Agent": UA}, follow_redirects=True) as c:
        res = await asyncio.gather(*(_one(c, u, t, event) for u, t in feeds), return_exceptions=True)
    return [i for r in res if isinstance(r, list) for i in r]
