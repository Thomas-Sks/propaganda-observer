"""Bus d'événements temps réel (Redis pub/sub) qui alimente le SSE du front."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import redis.asyncio as redis

from observer.core.settings import settings

_client: redis.Redis | None = None


def client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings().redis_url, decode_responses=True)
    return _client


def channel(event: str) -> str:
    return f"observer:event:{event}"


async def publish(event: str, kind: str, payload: dict) -> None:
    """kind : item.new | cluster.updated | verdict.ready | stats.tick | planner.log | collector.status"""
    await client().publish(channel(event), json.dumps({"type": kind, "data": payload}, default=str))


async def subscribe(event: str) -> AsyncIterator[dict]:
    pubsub = client().pubsub()
    await pubsub.subscribe(channel(event))
    try:
        async for msg in pubsub.listen():
            if msg.get("type") == "message":
                yield json.loads(msg["data"])
    finally:
        await pubsub.unsubscribe(channel(event))
        await pubsub.aclose()
