"""Collecteur Telegram SANS compte : aperçu web public des canaux (`https://t.me/s/<canal>`).

Pas de recherche globale possible sans session utilisateur : on suit une liste de canaux, construite
1) à partir de la config de l'événement (`telegram_channels`, proposés par le Planner ou l'analyste),
2) à partir des liens t.me trouvés dans les posts déjà collectés sur l'événement,
3) à partir des graines des réseaux de référence du registre (`data/registry/reference_networks.yaml`).
Les messages sont ensuite filtrés par pertinence (termes de l'événement) et par fenêtre de dates.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from observer.core.models import AccountMeta, ContentItem, pseudonymize

log = logging.getLogger("observer.telegram")
UA = "Mozilla/5.0 (X11; Linux x86_64) propaganda-observer/0.1"
_TME = re.compile(r"(?:https?://)?t\.me/(?:s/)?([A-Za-z][A-Za-z0-9_]{3,31})(?:/\d+)?", re.I)
_SKIP = {"joinchat", "share", "addstickers", "iv", "proxy", "socks", "s", "c", "contact"}


def handles_from_text(texts: list[str]) -> set[str]:
    return {m.group(1) for t in texts for m in _TME.finditer(t or "") if m.group(1).lower() not in _SKIP}


async def network_seeds() -> dict[str, str]:
    """Canaux Telegram connus pour alimenter un réseau de référence du registre : {canal: étiquette}."""
    from observer.tools.networks import networks
    out: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": UA}) as c:
        for n in networks():
            ts = n.get("telegram_seeds")
            if not ts:
                continue
            try:
                r = await c.get(ts["checkfirst_json"].format(domain=ts["domain"]))
                r.raise_for_status()
            except Exception as e:
                log.warning("graines %s : %s", n["name"], e)
                continue
            srcs = json.loads(r.text).get("topSources", [])
            for s in [s for s in srcs if s["source"].startswith("Telegram:")][: ts.get("top", 30)]:
                out[s["source"].split(":", 1)[1].strip()] = ts["label"]
    return out


def _count(s: str) -> int | None:
    m = re.match(r"([\d.,]+)\s*([KM]?)", s.replace(" ", ""))
    if not m:
        return None
    n = float(m.group(1).replace(",", "."))
    return int(n * {"K": 1e3, "M": 1e6}.get(m.group(2), 1))


def _parse_page(html: str, handle: str, event: str | None, known: str | None) -> tuple[list[ContentItem], int | None]:
    """Messages d'une page d'aperçu + nombre d'abonnés."""
    from observer.collectors.gnews import registrable
    from observer.tools.links import canonical_url
    soup = BeautifulSoup(html, "html.parser")
    subs = None
    for ctr in soup.select(".tgme_channel_info_counter"):
        if "subscriber" in ctr.get_text():
            subs = _count(ctr.select_one(".counter_value").get_text())
    out = []
    for msg in soup.select(".tgme_widget_message[data-post]"):
        body = msg.select_one(".tgme_widget_message_text")
        t = msg.select_one("time[datetime]")
        if not body or not t:
            continue
        post = msg["data-post"]  # "canal/123"
        links = [a["href"] for a in body.select("a[href]") if a["href"].startswith("http")]
        views = msg.select_one(".tgme_widget_message_views")
        fwd = msg.select_one(".tgme_widget_message_forwarded_from_name")
        out.append(ContentItem(
            platform="telegram", post_id=post.replace("/", "_"), url=f"https://t.me/{post}",
            ts=datetime.fromisoformat(t["datetime"]).astimezone(timezone.utc),
            author_pseudo=pseudonymize("telegram", handle.lower()),
            text=body.get_text("\n", strip=True)[:4000] + (f"\n[forwarded from] {fwd.get_text(strip=True)}" if fwd else ""),
            links=sorted({canonical_url(u) for u in links if "t.me/" not in u}),
            urls_canon=[f"t.me/{handle}"] + sorted({registrable(u) for u in links}), event=event, format="message",
            account=AccountMeta(followers=subs, known_network=known),
            metrics={"views": _count(views.get_text())} if views and _count(views.get_text()) is not None else {},
        ))
    return out, subs


def _msg_id(it: ContentItem) -> int:
    return int(it.post_id.rsplit("_", 1)[-1])


async def fetch_channel(c: httpx.AsyncClient, handle: str, event: str | None, known: str | None = None,
                        since: datetime | None = None, until: datetime | None = None,
                        max_pages: int = 8) -> list[ContentItem]:
    """Lit l'aperçu public d'un canal SUR LA FENÊTRE de l'événement.

    Les identifiants de messages sont séquentiels : pour un événement passé, on localise d'abord la fin de la
    fenêtre par recherche dichotomique sur `?before=<id>` (≈ 12 requêtes), puis on remonte page par page
    jusqu'au début de la fenêtre (au plus `max_pages`)."""
    async def page(before: int | None) -> list[ContentItem]:
        url = f"https://t.me/s/{handle}" + (f"?before={before}" if before else "")
        r = await c.get(url)
        if r.status_code != 200 or "tgme_widget_message" not in r.text:
            return []
        return _parse_page(r.text, handle, event, known)[0]

    latest = await page(None)
    if not latest:
        return []  # canal privé, inexistant ou sans aperçu public
    out = list(latest)
    cursor: int | None = min(_msg_id(i) for i in latest)
    oldest = min(i.ts for i in latest)
    if until and oldest > until:  # fenêtre passée : dichotomie sur les identifiants
        lo, hi = 1, cursor
        for _ in range(16):
            if hi - lo < 20:
                break
            mid = (lo + hi) // 2
            pts = await page(mid)
            if not pts:
                lo = mid
                continue
            if max(i.ts for i in pts) > until:
                hi = mid
            else:
                lo = mid
        cursor = hi
        out = []
    for _ in range(max_pages):
        if since and out and min(i.ts for i in out) < since:
            break
        pts = await page(cursor)
        if not pts:
            break
        out.extend(pts)
        new_cursor = min(_msg_id(i) for i in pts)
        if new_cursor >= (cursor or 10**12):
            break
        cursor = new_cursor
    return out


def relevant(it: ContentItem, terms: list[list[str]]) -> bool:
    """Pertinent si tous les mots significatifs d'au moins un terme apparaissent dans le texte."""
    from observer.tools.text import normalize
    words = set(normalize(it.text).split())
    return any(all(w in words for w in t) for t in terms if t)


async def fetch(handles: list[str], keywords: list[str], hashtags: list[str], event: str | None = None,
                since: datetime | None = None, concurrency: int = 5,
                known: dict[str, str] | None = None, until: datetime | None = None,
                max_pages: int = 8) -> list[ContentItem]:
    from observer.tools.text import normalize
    terms = [[w for w in normalize(k).split() if len(w) >= 4] for k in keywords] + [[normalize(h)] for h in hashtags]
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": UA}, follow_redirects=True) as c:
        async def one(h: str) -> list[ContentItem]:
            async with sem:
                try:
                    tag = (known or {}).get(h)
                    return await fetch_channel(c, h, event, tag, since, until, max_pages)
                except Exception as e:
                    log.info("t.me/s/%s : %s", h, e)
                    return []
        batches = await asyncio.gather(*(one(h) for h in handles))
    return [i for b in batches for i in b if (since is None or i.ts >= since) and (until is None or i.ts < until)
            and relevant(i, terms)]
