"""Collecteur Bluesky : recherche de posts (authentifiée, mot de passe d'application) + profils des auteurs.

- `searchPosts` (tri « latest ») par mot-clé et hashtag ;
- `getProfiles` par lots de 25 : date de création, abonnés, abonnements, nombre de posts → signaux de comptes.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx

from observer.core.models import AccountMeta, ContentItem, pseudonymize
from observer.core.settings import settings

log = logging.getLogger("observer.bluesky")
PDS = "https://bsky.social/xrpc"
_session: dict = {}


def _token(client: httpx.Client) -> str:
    if _session.get("jwt") and _session.get("exp", 0) > time.time():
        return _session["jwt"]
    s = settings()
    if not (s.bsky_handle and s.bsky_app_password):
        raise RuntimeError("BSKY_HANDLE / BSKY_APP_PASSWORD manquants dans .env")
    r = client.post(f"{PDS}/com.atproto.server.createSession",
                    json={"identifier": s.bsky_handle, "password": s.bsky_app_password})
    r.raise_for_status()
    _session.update(jwt=r.json()["accessJwt"], exp=time.time() + 60 * 60)  # jeton valable ~2 h
    return _session["jwt"]


def _ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _links(record: dict) -> list[str]:
    out = []
    for f in record.get("facets") or []:
        for feat in f.get("features") or []:
            if feat.get("uri"):
                out.append(feat["uri"])
    ext = ((record.get("embed") or {}).get("external") or {}).get("uri")
    if ext:
        out.append(ext)
    return out


def fetch(queries: list[str | tuple[str, str]], event: str | None = None, per_query: int = 50,
          since: datetime | None = None, until: datetime | None = None) -> list[ContentItem]:
    """Bloquant : à appeler via asyncio.to_thread. Une requête peut être (texte, langue) pour filtrer la langue."""
    from observer.collectors.gnews import registrable
    from observer.tools.links import canonical_url
    posts: dict[str, dict] = {}
    with httpx.Client(timeout=20) as c:
        headers = {"Authorization": f"Bearer {_token(c)}"}
        for q in queries:
            q, lang = q if isinstance(q, tuple) else (q, None)
            params = {"q": q, "sort": "latest", "limit": min(100, per_query)}
            if lang:
                params["lang"] = lang
            if since:
                params["since"] = since.isoformat().replace("+00:00", "Z")
            if until:
                params["until"] = until.isoformat().replace("+00:00", "Z")
            try:
                r = c.get(f"{PDS}/app.bsky.feed.searchPosts", params=params, headers=headers)
                r.raise_for_status()
            except Exception as e:
                log.warning("searchPosts %r : %s", q, e)
                continue
            for p in r.json().get("posts", []):
                posts.setdefault(p["uri"], p)
        dids = sorted({p["author"]["did"] for p in posts.values()})
        profiles: dict[str, dict] = {}
        for k in range(0, len(dids), 25):
            try:
                r = c.get(f"{PDS}/app.bsky.actor.getProfiles", params=[("actors", d) for d in dids[k:k + 25]],
                          headers=headers)
                r.raise_for_status()
                profiles.update({p["did"]: p for p in r.json().get("profiles", [])})
            except Exception as e:
                log.warning("getProfiles : %s", e)
    out = []
    for p in posts.values():
        rec, author = p.get("record", {}), p["author"]
        ts = _ts(rec.get("createdAt")) or _ts(p.get("indexedAt"))
        if not ts:
            continue
        prof = profiles.get(author["did"], {})
        links = _links(rec)
        ext = ((rec.get("embed") or {}).get("external") or {})
        ext_text = " ".join(x for x in (ext.get("title"), ext.get("description")) if x)
        rkey = p["uri"].rsplit("/", 1)[-1]
        out.append(ContentItem(
            platform="bluesky", post_id=rkey, url=f"https://bsky.app/profile/{author['handle']}/post/{rkey}",
            ts=ts, author_pseudo=pseudonymize("bluesky", author["did"]),
            text=rec.get("text", "") + (f"\n[link] {ext_text}" if ext_text else ""),
            links=sorted({canonical_url(u) for u in links if u.startswith("http")}),
            hashtags=[t.lower() for t in (rec.get("tags") or [])] + [
                f["tag"].lower() for fc in rec.get("facets") or [] for f in fc.get("features") or [] if f.get("tag")],
            urls_canon=sorted({registrable(u) for u in links if u.startswith("http")}),
            lang=(rec.get("langs") or [None])[0], event=event, format="post",
            account=AccountMeta(created_at=_ts(prof.get("createdAt")), followers=prof.get("followersCount"),
                                following=prof.get("followsCount"), posts_count=prof.get("postsCount"),
                                default_avatar=not bool(author.get("avatar")),
                                automated_declared=any(lb.get("val") == "bot" for lb in author.get("labels") or [])),
            metrics={k: p.get(k, 0) for k in ("likeCount", "repostCount", "replyCount", "quoteCount")},
        ))
    return out
