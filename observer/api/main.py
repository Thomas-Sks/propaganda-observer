"""API FastAPI : REST + SSE. Lancer : uv run uvicorn observer.api.main:app --reload --port 8000"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from observer.core import bus, db, llm
from observer.workers import runner


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.init_db()
    # Reprend automatiquement la surveillance des observations « live » après un redémarrage de l'API
    for ev in await db.list_events():
        if ev["status"] == "live":
            runner.start(ev["slug"])
    yield


app = FastAPI(title="Propaganda Observer API", version="0.1.0", lifespan=lifespan)
from observer.api.views import router as views_router  # noqa: E402

from observer.api.reliability import router as reliability_router  # noqa: E402

app.include_router(views_router)
app.include_router(reliability_router)
from observer.api.provenance import router as provenance_router  # noqa: E402

app.include_router(provenance_router)
from observer.api.publish import router as publish_router  # noqa: E402

app.include_router(publish_router)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"],
                   allow_headers=["*"])


@app.middleware("http")
async def internal_token(request, call_next):
    """L'API n'est jamais appelée directement par le navigateur : seul le serveur Next (qui vérifie la session et
    le rôle de l'utilisateur) la joint, avec un jeton interne. Sans jeton valide : 401 (sauf /api/health)."""
    import hmac

    from fastapi.responses import JSONResponse

    from observer.core.settings import settings
    if request.url.path != "/api/health" and request.method != "OPTIONS":
        got = request.headers.get("x-internal-token", "")
        if not hmac.compare_digest(got.encode(), settings().api_token.encode()):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        # Compte de démonstration (rôle transmis par le serveur Next, seul détenteur du jeton) : uniquement des
        # réponses déjà publiées ; aucun calcul, aucun appel externe ou payant (garde-fou llm.READ_ONLY en plus).
        if request.headers.get("x-viewer-role") == "demo":
            from fastapi.responses import Response

            from observer.api.publish import serve_snapshot
            from observer.core.llm import READ_ONLY
            READ_ONLY.set(True)
            status, body = await serve_snapshot(request.method, request.url.path, dict(request.query_params))
            return Response(body, status_code=status, media_type="application/json")
    return await call_next(request)


class PlanIn(BaseModel):
    description: str


@app.get("/api/health")
async def health() -> dict:
    await bus.client().ping()
    return {"status": "ok", "llm_spent_usd": round(llm.spent(), 4), "llm_budget_usd": llm.settings().llm_budget_usd}


@app.post("/api/events/plan")
async def plan_event(body: PlanIn) -> dict:
    from observer.agents.planner import plan, validate_keywords
    try:
        cfg = await asyncio.to_thread(plan, body.description)
    except llm.BudgetExceeded as e:
        raise HTTPException(402, str(e)) from e
    volumes = await validate_keywords(cfg)
    await db.upsert_event(cfg.slug, cfg.label, cfg.model_dump() | {"volumes": volumes}, status="planned")
    return {"slug": cfg.slug, "config": cfg.model_dump(), "volumes": volumes}


@app.post("/api/events/{slug}/start")
async def start_event(slug: str) -> dict:
    if not await db.get_event(slug):
        raise HTTPException(404, "unknown event")
    return {"started": runner.start(slug)}


@app.get("/api/events/{slug}/progress")
async def event_progress(slug: str) -> dict:
    return runner.progress(slug)


@app.post("/api/events/{slug}/stop")
async def stop_event(slug: str) -> dict:
    return {"stopped": runner.stop(slug)}


@app.get("/api/events")
async def events() -> list[dict]:
    return await db.list_events()


@app.get("/api/events/{slug}")
async def event(slug: str) -> dict:
    ev = await db.get_event(slug)
    if not ev:
        raise HTTPException(404, "unknown event")
    return ev


@app.get("/api/events/{slug}/items")
async def event_items(slug: str, limit: int = 500, include_off_topic: bool = False) -> list[dict]:
    from observer.tools.relevance import threshold
    ev = await db.get_event(slug)
    thr = threshold(ev["config"] if ev else None)
    its = await db.load_items(slug, limit=20000)  # filtre AVANT la limite, sinon les hors-sujets récents masquent tout
    if not include_off_topic:
        its = [i for i in its if i.relevance is None or i.relevance >= thr]
    return [i.model_dump(mode="json") for i in its[:limit]]


@app.get("/api/events/{slug}/clusters")
async def event_clusters(slug: str) -> list[dict]:
    return [c.model_dump(mode="json") for c in await db.load_clusters(slug)]


@app.get("/api/events/{slug}/graph")
async def event_graph(slug: str) -> dict:
    from observer.tools.relevance import threshold
    ev = await db.get_event(slug)
    thr = threshold(ev["config"] if ev else None)
    items = [i for i in await db.load_items(slug, limit=8000) if i.relevance is None or i.relevance >= thr]
    return runner.graph_payload(items, await db.load_clusters(slug))


@app.get("/api/stream/{slug}")
async def stream(slug: str):
    async def gen():
        async for msg in bus.subscribe(slug):
            yield {"event": msg["type"], "data": json.dumps(msg["data"], default=str)}
    return EventSourceResponse(gen(), ping=15)
