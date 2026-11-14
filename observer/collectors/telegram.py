"""Collecteur Telegram (canaux publics) via Telethon, avec une session utilisateur.

Première connexion interactive (une seule fois) :  uv run python -m observer telegram-login
Ensuite : recherche globale des posts de canaux publics par mot-clé (`messages.searchGlobal`,
`broadcasts_only`), plus métadonnées du canal (date de création, abonnés quand disponibles).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from observer.core.models import AccountMeta, ContentItem, pseudonymize
from observer.core.settings import ROOT, settings

log = logging.getLogger("observer.telegram")
SESSION = str(ROOT / "data" / "telegram")


def client():
    from telethon import TelegramClient
    s = settings()
    if not (s.telegram_api_id and s.telegram_api_hash):
        raise RuntimeError("TELEGRAM_API_ID / TELEGRAM_API_HASH manquants dans .env")
    (ROOT / "data").mkdir(exist_ok=True)
    return TelegramClient(SESSION, int(s.telegram_api_id), s.telegram_api_hash)


async def login() -> None:
    async with client() as c:  # demande le numéro puis le code reçu dans l'app Telegram
        me = await c.get_me()
        print(f"Session Telegram OK : {me.first_name} (id {me.id}). Fichier : {SESSION}.session")


def is_logged_in() -> bool:
    """Vrai seulement si une session existe ET est autorisée (jamais d'invite interactive ici)."""
    import asyncio
    if not (ROOT / "data" / "telegram.session").exists():
        return False

    async def check() -> bool:
        c = client()
        await c.connect()
        try:
            return await c.is_user_authorized()
        finally:
            await c.disconnect()
    try:
        return asyncio.run(check())
    except Exception:
        return False


async def fetch(queries: list[str], event: str | None = None, per_query: int = 50,
                since: datetime | None = None) -> list[ContentItem]:
    from telethon.tl.functions.messages import SearchGlobalRequest
    from telethon.tl.types import Channel, InputMessagesFilterEmpty, InputPeerEmpty, MessageEntityTextUrl, MessageEntityUrl

    from observer.tools.links import canonical_url
    from observer.collectors.gnews import registrable
    out: list[ContentItem] = []
    c = client()
    await c.connect()  # connect() et non start() : ne demande jamais de numéro dans la boucle live
    try:
        if not await c.is_user_authorized():
            raise RuntimeError("Session Telegram non autorisée : lancer `uv run python -m observer telegram-login`")
        for q in queries:
            try:
                res = await c(SearchGlobalRequest(
                    q=q, filter=InputMessagesFilterEmpty(), min_date=since, max_date=None, offset_rate=0,
                    offset_peer=InputPeerEmpty(), offset_id=0, limit=per_query, broadcasts_only=True))
            except Exception as e:
                log.warning("searchGlobal %r : %s", q, e)
                continue
            chats = {ch.id: ch for ch in res.chats}
            for m in res.messages:
                ch = chats.get(getattr(m.peer_id, "channel_id", None))
                if not isinstance(ch, Channel) or not m.message:
                    continue
                urls = []
                for ent in m.entities or []:
                    if isinstance(ent, MessageEntityTextUrl):
                        urls.append(ent.url)
                    elif isinstance(ent, MessageEntityUrl):
                        urls.append(m.message[ent.offset:ent.offset + ent.length])
                urls = [u if u.startswith("http") else "https://" + u for u in urls]
                handle = ch.username or str(ch.id)
                out.append(ContentItem(
                    platform="telegram", post_id=f"{ch.id}_{m.id}",
                    url=f"https://t.me/{ch.username}/{m.id}" if ch.username else None,
                    ts=m.date.astimezone(timezone.utc), author_pseudo=pseudonymize("telegram", str(ch.id)),
                    text=m.message[:4000], links=sorted({canonical_url(u) for u in urls}),
                    urls_canon=[f"t.me/{handle}"] + sorted({registrable(u) for u in urls}),
                    event=event,
                    account=AccountMeta(created_at=ch.date.astimezone(timezone.utc) if ch.date else None,
                                        followers=getattr(ch, "participants_count", None),
                                        verified=bool(getattr(ch, "verified", False))),
                    metrics={k: int(v) for k, v in (("views", m.views), ("forwards", m.forwards)) if v is not None},
                ))
    finally:
        await c.disconnect()
    return out
