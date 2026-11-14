"""Collecteur Instagram via Apify (`apify/instagram-hashtag-scraper`, recherche par mot-clé ou hashtag).

Payant à l'usage : volumes bas, plafond par run. Les métadonnées de compte (abonnés, âge) ne sont pas
renvoyées par ce scraper ; on garde l'identifiant du propriétaire (pseudonymisé) pour la coordination.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from observer.core.models import AccountMeta, ContentItem, pseudonymize
from observer.core.settings import settings

log = logging.getLogger("observer.instagram")
ACTOR = "apify/instagram-hashtag-scraper"


def fetch(terms: list[str], event: str | None = None, per_term: int = 15, keyword: bool = True,
          max_usd: float = 0.5) -> tuple[list[ContentItem], float]:
    from apify_client import ApifyClient
    from observer.tools.links import canonical_url
    client = ApifyClient(settings().apify_token)
    run = client.actor(ACTOR).call(run_input={
        "hashtags": terms, "keywordSearch": keyword, "resultsType": "posts", "resultsLimit": per_term,
    }, run_timeout=timedelta(minutes=6), max_total_charge_usd=Decimal(str(max_usd)), logger=None)
    if run is None:
        raise RuntimeError("Run Apify Instagram sans résultat")
    cost = float(getattr(run, "usage_total_usd", 0) or 0)
    out = []
    for p in client.dataset(run.default_dataset_id).iterate_items():
        ts = p.get("timestamp")
        if not ts or not (p.get("id") or p.get("shortCode")):
            continue
        owner = p.get("ownerId") or p.get("ownerUsername") or "unknown"
        cap = p.get("caption") or ""
        out.append(ContentItem(
            platform="instagram", post_id=str(p.get("shortCode") or p["id"]), url=p.get("url"),
            ts=datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc),
            author_pseudo=pseudonymize("instagram", str(owner)), text=cap[:4000],
            hashtags=[h.lower() for h in p.get("hashtags") or []],
            links=sorted({canonical_url(u) for u in (p.get("externalUrl"),) if u}),
            urls_canon=[p.get("ownerUsername") or ""], event=event,
            format="reel" if (p.get("productType") == "clips" or p.get("type") == "Video") else "post",
            account=AccountMeta(verified=p.get("isVerified")),
            metrics={k: int(p[k]) for k in ("likesCount", "commentsCount", "videoViewCount", "videoPlayCount")
                     if isinstance(p.get(k), (int, float)) and p[k] >= 0},
        ))
    return out, cost
