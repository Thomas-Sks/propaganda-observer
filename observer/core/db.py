"""Stockage Postgres (JSONB + pgvector). Schéma volontairement simple : les objets riches vivent en JSONB."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, MetaData, String, Table, Text, func, select, text
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from observer.core.models import Cluster, ContentItem
from observer.core.settings import settings

metadata = MetaData()

events = Table(
    "events", metadata,
    Column("slug", String, primary_key=True),
    Column("label", Text, nullable=False),
    Column("config", JSONB, nullable=False),
    Column("status", String, nullable=False, server_default="draft"),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

items = Table(
    "items", metadata,
    Column("uid", String, primary_key=True),
    Column("event", String, index=True),
    Column("platform", String, index=True),
    Column("ts", DateTime(timezone=True), index=True),
    Column("author_pseudo", String, index=True),
    Column("data", JSONB, nullable=False),
    Column("ingested_at", DateTime(timezone=True), server_default=func.now()),
)

clusters = Table(
    "clusters", metadata,
    Column("id", String, primary_key=True),
    Column("event", String, index=True),
    Column("kind", String),
    Column("level", String),
    Column("data", JSONB, nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
)

# Instantanés publiés pour le compte de démonstration : réponses JSON figées, servies telles quelles.
snapshots = Table(
    "snapshots", metadata,
    Column("key", String, primary_key=True),      # « GET /api/events/x/summary » (+ « ?requête » triée)
    Column("slug", String, index=True),           # observation, ou « _global » (fiabilité, cartes de provenance)
    Column("status", String, nullable=False),
    Column("body", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=func.now()),
)

_engine: AsyncEngine | None = None


def engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings().database_url, pool_pre_ping=True)
    return _engine


async def init_db() -> None:
    async with engine().begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(metadata.create_all)


async def upsert_event(slug: str, label: str, config: dict, status: str = "draft") -> None:
    stmt = insert(events).values(slug=slug, label=label, config=config, status=status)
    stmt = stmt.on_conflict_do_update(index_elements=["slug"],
                                      set_={"label": label, "config": config, "status": status})
    async with engine().begin() as conn:
        await conn.execute(stmt)


async def save_items(batch: list[ContentItem]) -> int:
    """Insère les nouveaux items, ignore les doublons. Renvoie le nombre d'insertions."""
    if not batch:
        return 0
    rows = [dict(uid=i.uid, event=i.event, platform=i.platform, ts=i.ts,
                 author_pseudo=i.author_pseudo, data=i.model_dump(mode="json")) for i in batch]
    stmt = insert(items).values(rows).on_conflict_do_nothing(index_elements=["uid"]).returning(items.c.uid)
    async with engine().begin() as conn:
        res = await conn.execute(stmt)
        return len(res.fetchall())


async def save_items_returning(batch: list[ContentItem]) -> list[str]:
    """Comme save_items, mais renvoie les uid réellement insérés."""
    if not batch:
        return []
    # Les enrichissements coûteux (transcription, OCR, empreintes d'images, pertinence) sont CONSERVÉS
    # quand un collecteur repasse sur un item : seul le reste (compteurs, profil…) est rafraîchi.
    async with engine().connect() as conn:
        prev = {r[0]: r[1] for r in (await conn.execute(
            select(items.c.uid, items.c.data).where(items.c.uid.in_([i.uid for i in batch])))).fetchall()}
    rows = []
    for i in batch:
        d = i.model_dump(mode="json")
        old = prev.get(i.uid)
        if old:
            for k in ("transcript", "ocr_text", "relevance", "format"):
                if d.get(k) in (None, "") and old.get(k) not in (None, ""):
                    d[k] = old[k]
            kept = [l for l in old.get("links", []) if l.startswith("frame-phash:")]
            d["links"] = sorted(set(d.get("links", [])) | set(kept))
        rows.append(dict(uid=i.uid, event=i.event, platform=i.platform, ts=i.ts, author_pseudo=i.author_pseudo, data=d))
    # Upsert : on ne renvoie que les uid réellement nouveaux.
    stmt = insert(items).values(rows)
    stmt = stmt.on_conflict_do_update(index_elements=["uid"], set_={"data": stmt.excluded.data}).returning(
        items.c.uid, text("(xmax = 0) AS inserted"))
    async with engine().begin() as conn:
        return [r[0] for r in (await conn.execute(stmt)).fetchall() if r[1]]


async def upsert_status(slug: str, status: str) -> None:
    async with engine().begin() as conn:
        await conn.execute(events.update().where(events.c.slug == slug).values(status=status))


async def load_items(event: str, since: datetime | None = None, limit: int = 5000) -> list[ContentItem]:
    q = select(items.c.data).where(items.c.event == event)
    if since:
        q = q.where(items.c.ts >= since)
    q = q.order_by(items.c.ts.desc()).limit(limit)
    async with engine().connect() as conn:
        return [ContentItem.model_validate(r[0]) for r in (await conn.execute(q)).fetchall()]


async def save_clusters(event: str, batch: list[Cluster]) -> None:
    if not batch:
        return
    rows = [dict(id=c.id, event=event, kind=c.kind, level=c.level, data=c.model_dump(mode="json"),
                 updated_at=datetime.now(timezone.utc)) for c in batch]
    stmt = insert(clusters).values(rows)
    stmt = stmt.on_conflict_do_update(index_elements=["id"], set_={
        "kind": stmt.excluded.kind, "level": stmt.excluded.level,
        "data": stmt.excluded.data, "updated_at": stmt.excluded.updated_at})
    async with engine().begin() as conn:
        await conn.execute(stmt)


async def replace_clusters(event: str, batch: list[Cluster]) -> None:
    """Remplace l'ensemble des clusters d'un événement (ils sont recalculés à chaque passe)."""
    async with engine().begin() as conn:
        await conn.execute(clusters.delete().where(clusters.c.event == event))
    await save_clusters(event, batch)


async def load_clusters(event: str) -> list[Cluster]:
    q = select(clusters.c.data).where(clusters.c.event == event).order_by(clusters.c.updated_at.desc())
    async with engine().connect() as conn:
        return [Cluster.model_validate(r[0]) for r in (await conn.execute(q)).fetchall()]


async def list_events() -> list[dict]:
    q = select(events.c.slug, events.c.label, events.c.status, events.c.created_at).where(
        events.c.status != "archived").order_by(events.c.created_at.desc())
    async with engine().connect() as conn:
        return [dict(r._mapping) for r in (await conn.execute(q)).fetchall()]


async def get_event(slug: str) -> dict | None:
    async with engine().connect() as conn:
        r = (await conn.execute(select(events).where(events.c.slug == slug))).first()
        return dict(r._mapping) if r else None


async def put_snapshots(slug: str, rows: list[tuple[str, int, str]]) -> None:
    """Remplace atomiquement l'instantané d'une observation (ou de « _global »)."""
    async with engine().begin() as conn:
        await conn.execute(snapshots.delete().where(snapshots.c.slug == slug))
        if rows:
            await conn.execute(insert(snapshots), [{"key": k, "slug": slug, "status": str(st), "body": b} for k, st, b in rows])


async def get_snapshot(key: str) -> tuple[int, str] | None:
    async with engine().connect() as conn:
        row = (await conn.execute(select(snapshots.c.status, snapshots.c.body).where(snapshots.c.key == key))).first()
    return (int(row[0]), row[1]) if row else None


async def snapshot_info() -> dict[str, dict]:
    """{slug: {"n": nombre de réponses figées, "at": date de publication}}."""
    async with engine().connect() as conn:
        rows = (await conn.execute(select(snapshots.c.slug, func.count(), func.max(snapshots.c.created_at))
                                   .group_by(snapshots.c.slug))).all()
    return {r[0]: {"n": r[1], "at": r[2].isoformat() if r[2] else None} for r in rows}
