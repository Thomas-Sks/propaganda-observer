"""Collecteur TikTok via Apify (`clockworks/tiktok-scraper`). Payant à l'usage : volumes volontairement bas.

Le son (musicId) est stocké comme lien `tiktok-sound:<id>` : le regroupement par lien détecte ainsi
les vidéos qui réutilisent le même son.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from observer.core.models import AccountMeta, ContentItem, pseudonymize
from observer.core.settings import settings

log = logging.getLogger("observer.tiktok")
ACTOR = "clockworks/tiktok-scraper"


def _ts(v) -> datetime | None:
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, timezone.utc)
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _date_filter(start: str | None) -> str:
    """Plage de recherche TikTok couvrant le début de la fenêtre de l'événement."""
    if not start:
        return "PAST_MONTH"
    days = (datetime.now(timezone.utc) - datetime.fromisoformat(start).replace(tzinfo=timezone.utc)).days
    for lim, name in ((1, "PAST_24_HOURS"), (7, "PAST_WEEK"), (31, "PAST_MONTH"), (92, "LAST_3_MONTHS"), (183, "LAST_6_MONTHS")):
        if days <= lim:
            return name
    return "ALL_TIME"


def fetch(hashtags: list[str], queries: list[str], event: str | None = None,
          per_input: int = 15, max_usd: float = 0.50, start: str | None = None,
          end: str | None = None) -> tuple[list[ContentItem], float]:
    """Bloquant. Renvoie (items, coût USD du run)."""
    from apify_client import ApifyClient
    client = ApifyClient(settings().apify_token)
    run = client.actor(ACTOR).call(run_input={
        # Recherche de VIDÉOS triées par date sur le dernier mois (les pages hashtag renvoient du vieux contenu populaire)
        "hashtags": hashtags, "searchQueries": queries, "resultsPerPage": per_input,
        "searchSection": "/video", "videoSearchSorting": "MOST_RELEVANT", "videoSearchDateFilter": _date_filter(start),
        **({"oldestPostDateUnified": start} if start else {}), **({"newestPostDate": end} if end else {}),
        "shouldDownloadVideos": False, "shouldDownloadCovers": False, "shouldDownloadSubtitles": False,
        "shouldDownloadSlideshowImages": False, "shouldDownloadAvatars": False, "shouldDownloadMusicCovers": False,
    }, run_timeout=timedelta(minutes=5), max_total_charge_usd=Decimal(str(max_usd)), logger=None)
    if run is None:
        raise RuntimeError("Run Apify TikTok sans résultat")
    cost = float(getattr(run, "usage_total_usd", 0) or 0)
    ds = run.default_dataset_id
    out = []
    for v in client.dataset(ds).iterate_items():
        a = v.get("authorMeta") or {}
        ts = _ts(v.get("createTimeISO") or v.get("createTime"))
        if not ts or not v.get("id"):
            continue
        music = (v.get("musicMeta") or {}).get("musicId")
        out.append(ContentItem(
            platform="tiktok", post_id=str(v["id"]), url=v.get("webVideoUrl"), ts=ts,
            author_pseudo=pseudonymize("tiktok", str(a.get("id") or a.get("name") or "unknown")),
            text=v.get("text") or "", hashtags=[h.get("name", "").lower() for h in v.get("hashtags") or [] if h.get("name")],
            links=[f"tiktok-sound:{music}"] if music else [], urls_canon=[a.get("name") or ""],
            event=event, lang=v.get("textLanguage"), format="video",
            account=AccountMeta(followers=a.get("fans"), following=a.get("following"), posts_count=a.get("video"),
                                verified=a.get("verified"), created_at=_ts(a.get("createTime")),
                                default_avatar=None),
            metrics={k: int(v[k]) for k in ("playCount", "diggCount", "shareCount", "commentCount") if v.get(k) is not None},
        ))
    return out, cost
