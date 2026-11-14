"""Partage coordonné de liens : la même URL publiée par plusieurs comptes (méthode « co-link » de CooRnet).

Déterministe : URL canonicalisée (sans paramètres de tracking, sans fragment, sans www, sans slash final),
regroupement exact, fenêtre temporelle explicite pour qualifier la rafale.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from observer.core.models import Cluster, ContentItem, Evidence

TRACKING = ("utm_", "fbclid", "gclid", "mc_", "igshid", "at_", "xtor", "ref", "s", "si", "feature")
SHORTENERS = {"bit.ly", "t.co", "tinyurl.com", "ow.ly", "buff.ly", "dlvr.it", "lnkd.in", "shorturl.at"}


def canonical_url(url: str) -> str:
    p = urlsplit(url.strip())
    host = (p.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False)
         if not any(k.lower() == t or k.lower().startswith(t) for t in TRACKING)]
    path = p.path.rstrip("/") or "/"
    if host in ("youtube.com", "youtu.be"):  # une vidéo = un identifiant
        vid = dict(parse_qsl(p.query)).get("v") or (path.strip("/") if host == "youtu.be" else None)
        if vid:
            return f"https://youtube.com/watch?v={vid}"
    return urlunsplit(("https", host, path, urlencode(sorted(q)), ""))


def find_link_shares(items: list[ContentItem], min_authors: int = 2) -> list[Cluster]:
    by_link: dict[str, list[ContentItem]] = defaultdict(list)
    for it in items:
        for link in set(it.links):
            if link.startswith("tiktok-sound:") or urlsplit(link).hostname not in SHORTENERS:
                by_link[link].append(it)
    out = []
    for link, its in sorted(by_link.items()):
        authors = sorted({i.author_pseudo for i in its})
        if len(authors) < min_authors:
            continue
        its = sorted(its, key=lambda i: i.ts)
        uids = [i.uid for i in its]
        cid = "ln-" + hashlib.sha1(link.encode()).hexdigest()[:10]
        out.append(Cluster(
            id=cid, kind="link", kinds=["link"], item_uids=uids, platforms=sorted({i.platform for i in its}),
            authors=authors, first_ts=its[0].ts, last_ts=its[-1].ts,
            evidence=[Evidence(id=f"{cid}-url", kind="shared_link", item_uids=uids, detail={"url": link})]))
    return out


def precise(it: ContentItem) -> bool:
    """Horodatage à la minute près ? Les agrégateurs (Google News pour les jours passés) arrondissent à l'heure
    pile : ces items ne doivent pas compter dans une rafale, sinon tout article du même jour « publie en même temps »."""
    return not (it.ts.minute == 0 and it.ts.second == 0 and it.ts.microsecond == 0)


def burst_authors(its: list[ContentItem], window: timedelta) -> int:
    """Nombre max d'auteurs distincts dans une fenêtre glissante (horodatages précis seulement)."""
    its = sorted((i for i in its if precise(i)), key=lambda i: i.ts)
    best, j = 0, 0
    for k in range(len(its)):
        while its[k].ts - its[j].ts > window:
            j += 1
        best = max(best, len({i.author_pseudo for i in its[j:k + 1]}))
    return best
