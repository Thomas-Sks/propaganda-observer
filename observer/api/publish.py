"""Publication pour la démo : fige les réponses de l'API d'une observation dans la table `snapshots`.

Le compte de démonstration (public) ne lit QUE ces réponses figées : aucun calcul, aucun appel externe ou payant.
Un administrateur republie quand il y a du nouveau ; l'instantané précédent est remplacé d'un bloc.

Les réponses sont produites par la même application FastAPI, appelée en interne (httpx + ASGI) : le compte de
démonstration voit exactement ce qu'un administrateur voyait au moment de la publication.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException

from observer.core import db, llm
from observer.core.settings import settings

log = logging.getLogger("observer.publish")
router = APIRouter()
STATUS_KEY = "observer:publish:{slug}"
# Cartes de provenance proposées en exemple sur la page Trust card (web/components/trust/TrustCard.tsx)
TRUST_EXAMPLES = ["thewashingtonexaminer.net", "globaltimes.cn", "francais.news-pravda.com", "thehindu.com",
                  "abc.net.au", "tagesschau.de"]
IGNORED_QUERY = {"cached_only", "force"}


def snapshot_key(method: str, path: str, query: dict[str, str] | None = None) -> str:
    """Clé canonique d'une requête (paramètres triés ; ceux qui ne changent pas la réponse sont ignorés)."""
    q = {k: v for k, v in (query or {}).items() if k not in IGNORED_QUERY}
    return f"{method} {path}" + (f"?{urlencode(sorted(q.items()))}" if q else "")


def _status(slug: str, **kw) -> None:
    llm._r().set(STATUS_KEY.format(slug=slug), json.dumps({**kw, "at": datetime.now(timezone.utc).isoformat()}), ex=86400)


async def _publish(slug: str) -> None:
    from observer.api import views
    from observer.api.main import app
    token = views.MEMO.set({})  # les centaines de vues réutilisent les mêmes données chargées une fois
    rows: list[tuple[str, int, str]] = []
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://internal",
                                     headers={"x-internal-token": settings().api_token}, timeout=600) as c:
            async def grab(method: str, path: str, query: dict | None = None, keep_errors: bool = False) -> httpx.Response:
                r = await c.request(method, path, params=query)
                if r.status_code < 400 or keep_errors:
                    rows.append((snapshot_key(method, path, query), r.status_code, r.text))
                return r

            base = f"/api/events/{slug}"
            _status(slug, state="running", step="views")
            for p in ("", "/progress", "/summary", "/network", "/accounts", "/suspects", "/coordination", "/themes", "/diffusion",
                      "/clusters"):
                r = await grab("GET", base + p)
                if p == "" and r.status_code != 200:
                    raise HTTPException(404, "unknown event")
            clusters = json.loads(next(b for k, _, b in rows if k == f"GET {base}/clusters"))
            accounts = json.loads(next(b for k, _, b in rows if k == f"GET {base}/accounts"))
            for k, c_ in enumerate(clusters):
                _status(slug, state="running", step=f"narratives {k + 1}/{len(clusters)}")
                await grab("GET", f"{base}/stories/{c_['id']}")
                # Enquêtes IA déjà faites (cache) : publiées ; aucune nouvelle n'est lancée
                await grab("POST", f"{base}/stories/{c_['id']}/investigate", {"cached_only": "true"}, keep_errors=True)
            for k, a in enumerate(accounts):
                if k % 100 == 0:
                    _status(slug, state="running", step=f"accounts {k + 1}/{len(accounts)}")
                await grab("GET", f"{base}/accounts/{a['id']}")
            await db.put_snapshots(slug, rows)

            # Pages communes : fiabilité et cartes de provenance d'exemple
            _status(slug, state="running", step="reliability and trust cards")
            rows = []
            await grab("GET", "/api/reliability")
            for t in TRUST_EXAMPLES:
                await grab("GET", "/v1/provenance", {"target": t})
            await db.put_snapshots("_global", rows)
        info = (await db.snapshot_info()).get(slug, {})
        _status(slug, state="done", n=info.get("n"), published_at=info.get("at"))
    except Exception as e:  # noqa: BLE001
        log.exception("publication %s", slug)
        _status(slug, state="error", error=str(e)[:300])
    finally:
        views.MEMO.reset(token)


_tasks: dict[str, asyncio.Task] = {}


@router.post("/api/events/{slug}/publish")
async def publish(slug: str) -> dict:
    """Lance la publication en arrière-plan (quelques minutes : chaque narratif et chaque compte est figé)."""
    if slug in _tasks and not _tasks[slug].done():
        return {"started": False, "reason": "already running"}
    _status(slug, state="running", step="starting")
    _tasks[slug] = asyncio.create_task(_publish(slug))
    return {"started": True}


@router.get("/api/events/{slug}/publication")
async def publication(slug: str) -> dict:
    """État de la publication (en cours / faite / erreur) et date de l'instantané actuellement visible."""
    raw = llm._r().get(STATUS_KEY.format(slug=slug))
    info = (await db.snapshot_info()).get(slug)
    return {"job": json.loads(raw) if raw else None, "published": info}


async def serve_snapshot(method: str, path: str, query: dict[str, str]) -> tuple[int, str]:
    """Réponse figée pour le compte de démonstration (jamais de calcul)."""
    if method == "GET" and path == "/api/events":
        published = await db.snapshot_info()
        rows = []
        for slug in published:
            hit = await db.get_snapshot(f"GET /api/events/{slug}")
            if hit and hit[0] == 200:
                ev = json.loads(hit[1])
                rows.append({"slug": ev["slug"], "label": ev["label"], "status": "published",
                             "created_at": published[slug]["at"]})
        return 200, json.dumps(rows)
    if method == "GET" and path.startswith("/api/events/") and path.endswith("/publication"):
        slug = path.split("/")[3]
        return 200, json.dumps({"job": None, "published": (await db.snapshot_info()).get(slug)})
    hit = await db.get_snapshot(snapshot_key(method, path, query))
    if hit:
        return hit
    detail = ("Only the example sources are available in the demo." if path == "/v1/provenance"
              else "Not available in the demo (only published data can be viewed).")
    return 404, json.dumps({"detail": detail})
