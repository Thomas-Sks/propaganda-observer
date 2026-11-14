"""Collecteur YouTube + Shorts sans clé (yt-dlp).

1. Découverte « à plat » (rapide) : recherche triée par date (`ytsearchdate`) et pages hashtag Shorts.
2. Métadonnées complètes pour les N premiers résultats (date exacte, chaîne, abonnés, tags, durée).
La date de création de chaîne n'est pas disponible sans l'API officielle (clé YouTube, à venir).
"""
from __future__ import annotations

import logging
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import yt_dlp

from observer.core.models import AccountMeta, ContentItem, pseudonymize

log = logging.getLogger("observer.youtube")
logging.getLogger("yt_dlp").setLevel(logging.CRITICAL)
BASE_OPTS = {"quiet": True, "no_warnings": True, "skip_download": True, "noprogress": True,
             "ignore_no_formats_error": True, "logger": logging.getLogger("yt_dlp"),
             "extractor_args": {"youtube": {"skip": ["dash", "hls"]}}}


def _flat(url: str, limit: int) -> list[dict]:
    opts = BASE_OPTS | {"extract_flat": True, "playlistend": limit}
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=False) or {}
    return [e for e in (info.get("entries") or []) if e and e.get("id")]


def _full(video_id: str) -> dict | None:
    try:
        with yt_dlp.YoutubeDL(BASE_OPTS) as y:
            return y.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    except Exception as e:  # vidéo privée, bloquée, limitée par l'âge…
        log.info("yt-dlp %s : %s", video_id, str(e)[:120])
        return None


def _to_item(v: dict, event: str | None, is_short: bool) -> ContentItem | None:
    ts = v.get("timestamp")
    if ts:
        when = datetime.fromtimestamp(ts, timezone.utc)
    elif v.get("upload_date"):
        when = datetime.strptime(v["upload_date"], "%Y%m%d").replace(tzinfo=timezone.utc)
    else:
        return None
    channel = v.get("channel_id") or v.get("uploader_id") or "unknown"
    desc = (v.get("description") or "").strip()
    return ContentItem(
        platform="youtube", post_id=v["id"],
        url=f"https://www.youtube.com/{'shorts/' if is_short else 'watch?v='}{v['id']}",
        ts=when, author_pseudo=pseudonymize("youtube", channel),
        text=(v.get("title") or "") + ("\n" + desc[:400] if desc else ""),
        hashtags=[t.lstrip("#").lower() for t in (v.get("tags") or [])][:30],
        lang=v.get("language"), event=event, format="short" if is_short else "video",
        account=AccountMeta(followers=v.get("channel_follower_count"),
                            verified=bool(v.get("channel_is_verified")) if "channel_is_verified" in v else None),
        metrics={k: int(v[k]) for k in ("view_count", "like_count", "comment_count") if v.get(k) is not None},
        urls_canon=[v.get("channel") or channel],
    )


def _search_api(kw: str, since: datetime | None, until: datetime | None, lang: str | None, n: int) -> list[str] | None:
    """Recherche datée via l'API officielle (publishedAfter/Before). Mise en cache 6 h : le quota de
    `search.list` est limité (~100 appels/jour), on ne relance pas la même recherche à chaque passe."""
    import json

    import httpx

    from observer.core import llm
    from observer.core.settings import settings
    key = settings().youtube_api_key
    if not key:
        return None
    ck = f"observer:yt:search:{kw}:{since}:{until}:{lang}"
    r = llm._r()
    if (hit := r.get(ck)):
        return json.loads(hit)
    params = {"part": "id", "q": kw, "type": "video", "maxResults": min(50, n), "key": key,
              "order": "relevance" if since and until else "date"}
    if since:
        params["publishedAfter"] = since.isoformat().replace("+00:00", "Z")
    if until:
        params["publishedBefore"] = until.isoformat().replace("+00:00", "Z")
    if lang and len(lang) == 2:
        params["relevanceLanguage"] = lang
    try:
        resp = httpx.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        log.warning("API YouTube search %r : %s", kw, e)
        return None
    ids = [x["id"]["videoId"] for x in resp.json().get("items", []) if x.get("id", {}).get("videoId")]
    r.set(ck, json.dumps(ids), ex=6 * 3600)
    return ids


def fetch(keywords: list[str], hashtags: list[str], event: str | None = None,
          per_query: int = 12, workers: int = 6, since: datetime | None = None,
          until: datetime | None = None, kw_langs: dict[str, str] | None = None) -> list[ContentItem]:
    """Bloquant : à appeler via asyncio.to_thread. Respecte la fenêtre [since, until[ de l'événement :
    recherche DATÉE via l'API officielle (sinon repli yt-dlp, qui ne voit que le récent)."""
    candidates: dict[str, bool] = {}  # id -> is_short
    recent = since is None or (datetime.now(timezone.utc) - since).days <= 7
    for kw in keywords:
        ids = _search_api(kw, since, until, (kw_langs or {}).get(kw), per_query * 2)
        if ids is not None:
            for vid in ids:
                candidates.setdefault(vid, False)
            continue
        try:
            url = f"https://www.youtube.com/results?search_query={quote_plus(kw)}&sp=CAI%253D"  # tri par date
            for e in _flat(url, per_query):
                candidates.setdefault(e["id"], "/shorts/" in (e.get("url") or ""))
        except Exception as ex:
            log.warning("recherche %r : %s", kw, ex)
    # Les pages hashtag Shorts ne donnent que du contenu récent : utiles seulement pour un événement en cours
    for tag in (hashtags if recent else []):
        try:
            for e in _flat(f"https://www.youtube.com/hashtag/{tag}/shorts", per_query):
                candidates[e["id"]] = True
        except Exception as ex:
            log.warning("hashtag #%s : %s", tag, ex)
    infos = _videos_api(list(candidates))  # API officielle : 1 unité / 50 vidéos, pas de scraping
    if infos is None:  # pas de clé ou API indisponible : repli yt-dlp page par page
        with ThreadPoolExecutor(workers) as pool:
            infos = list(pool.map(_full, candidates))
    channels = _channel_meta({i.get("channel_id") for i in infos if i and i.get("channel_id")})
    out = []
    for vid, info in zip(candidates, infos):
        if info:
            short = candidates[vid] or (info.get("duration") or 999) <= 180
            it = _to_item(info, event, short)
            meta = channels.get(info.get("channel_id") or "")
            if it and meta:
                it.account.created_at = meta["created_at"]
                it.account.posts_count = meta["videos"]
                it.account.followers = meta["subscribers"] if meta["subscribers"] is not None else it.account.followers
            if it and (since is None or it.ts >= since) and (until is None or it.ts < until):
                out.append(it)
    return out


def _channel_meta(ids: set[str]) -> dict[str, dict]:
    """Âge, abonnés et nombre de vidéos des chaînes via l'API officielle (1 unité par lot de 50).
    Sans clé, renvoie {} : le collecteur reste fonctionnel."""
    import httpx

    from observer.core.settings import settings
    key = settings().youtube_api_key
    if not key or not ids:
        return {}
    out: dict[str, dict] = {}
    ids_l = sorted(ids)
    for k in range(0, len(ids_l), 50):
        try:
            r = httpx.get("https://www.googleapis.com/youtube/v3/channels", timeout=20, params={
                "part": "snippet,statistics", "id": ",".join(ids_l[k:k + 50]), "key": key})
            r.raise_for_status()
        except Exception as e:
            log.warning("API YouTube channels : %s", e)
            continue
        for c in r.json().get("items", []):
            st = c.get("statistics", {})
            out[c["id"]] = {
                "created_at": datetime.fromisoformat(c["snippet"]["publishedAt"].replace("Z", "+00:00")),
                "subscribers": None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0)),
                "videos": int(st.get("videoCount", 0)),
            }
    return out


def _iso_duration(d: str) -> int:
    import re
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    dd, h, mi, se = (int(x or 0) for x in m.groups())
    return ((dd * 24 + h) * 60 + mi) * 60 + se


def _videos_api(ids: list[str]) -> list[dict | None] | None:
    """Métadonnées via videos.list, converties au format yt-dlp utilisé par _to_item."""
    import httpx

    from observer.core.settings import settings
    key = settings().youtube_api_key
    if not key:
        return None
    by_id: dict[str, dict] = {}
    try:
        for k in range(0, len(ids), 50):
            r = httpx.get("https://www.googleapis.com/youtube/v3/videos", timeout=20, params={
                "part": "snippet,statistics,contentDetails", "id": ",".join(ids[k:k + 50]), "key": key})
            r.raise_for_status()
            for v in r.json().get("items", []):
                sn, st = v["snippet"], v.get("statistics", {})
                by_id[v["id"]] = {
                    "id": v["id"], "title": sn.get("title"), "description": sn.get("description"),
                    "timestamp": datetime.fromisoformat(sn["publishedAt"].replace("Z", "+00:00")).timestamp(),
                    "channel_id": sn.get("channelId"), "channel": sn.get("channelTitle"),
                    "tags": sn.get("tags") or [], "language": sn.get("defaultAudioLanguage") or sn.get("defaultLanguage"),
                    "duration": _iso_duration(v.get("contentDetails", {}).get("duration", "")),
                    **{f"{x}_count": int(st[f"{x}Count"]) for x in ("view", "like", "comment") if f"{x}Count" in st},
                }
    except Exception as e:
        log.warning("API YouTube videos : %s ; repli yt-dlp", e)
        return None
    return [by_id.get(i) for i in ids]
