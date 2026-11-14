"""Boucle de surveillance live d'un événement : collecte → stockage → détection → diffusion SSE.

Tourne dans le process de l'API (asyncio) pendant le dev ; sera déplacée dans un worker arq en prod.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from observer.core import bus, db
from observer.core.models import ContentItem

log = logging.getLogger("observer.runner")
_tasks: dict[str, asyncio.Task] = {}


STEPS = ["web", "youtube", "bluesky", "tiktok", "telegram", "networks", "instagram",
         "relevance", "narratives", "stance", "video"]
STEP_LABELS = {"web": "News & web", "youtube": "YouTube", "bluesky": "Bluesky", "tiktok": "TikTok",
               "telegram": "Telegram", "networks": "Reference networks", "instagram": "Instagram",
               "relevance": "Filtering off-topic", "narratives": "Grouping narratives", "stance": "Assessing stance",
               "video": "Video analysis"}


async def step(slug: str, key: str, state: str, count: int | None = None, detail: str = "") -> None:
    """Enregistre l'état d'une étape (running | done | skipped | error) et le diffuse au front."""
    from observer.core import llm
    r = llm._r()
    val = {"key": key, "label": STEP_LABELS.get(key, key), "state": state, "count": count, "detail": detail,
           "at": datetime.now(timezone.utc).isoformat()}
    r.hset(f"observer:progress:{slug}", key, json.dumps(val))
    await bus.publish(slug, "progress", progress(slug))


def progress(slug: str) -> dict:
    from observer.core import llm
    r = llm._r()
    raw = {k: json.loads(v) for k, v in r.hgetall(f"observer:progress:{slug}").items()}
    meta = raw.pop("_pass", {})
    return {"pass": meta, "steps": [raw.get(k, {"key": k, "label": STEP_LABELS[k], "state": "pending"}) for k in STEPS]}


async def set_pass(slug: str, state: str, **kw) -> None:
    from observer.core import llm
    r = llm._r()
    if state == "running":  # nouvelle passe : les étapes repartent de zéro
        r.delete(f"observer:progress:{slug}")
    if kw.get("stopped"):  # collecte arrêtée : une étape interrompue n'est plus « en cours »
        for k, v in r.hgetall(f"observer:progress:{slug}").items():
            st = json.loads(v)
            if k != "_pass" and st.get("state") == "running":
                r.hset(f"observer:progress:{slug}", k, json.dumps({**st, "state": "skipped", "detail": "stopped"}))
    r.hset(f"observer:progress:{slug}", "_pass", json.dumps({"state": state, "at": datetime.now(timezone.utc).isoformat(), **kw}))
    await bus.publish(slug, "progress", progress(slug))


class Skip(Exception):
    """Source volontairement ignorée pour cette passe (raison affichée à l'utilisateur)."""


def days_ago(cfg: dict) -> float:
    """Âge du début de la fenêtre de l'événement, en jours (0 si pas de date)."""
    since, _ = window(cfg)
    return (datetime.now(timezone.utc) - since).total_seconds() / 86400 if since else 0.0


def window_is_past(cfg: dict, margin_days: int = 7) -> bool:
    _, until = window(cfg)
    return bool(until and (datetime.now(timezone.utc) - until).days > margin_days)


async def _run(slug: str, key: str, coro) -> int:
    await step(slug, key, "running")
    try:
        n = await coro
        await step(slug, key, "done" if n is not None else "skipped", n or 0)
        return n or 0
    except Skip as e:
        await step(slug, key, "skipped", 0, str(e))
        return 0
    except Exception as e:
        await step(slug, key, "error", detail=str(e)[:160])
        return 0


def window(cfg: dict) -> tuple[datetime | None, datetime | None]:
    """Fenêtre de l'événement [start, end + 1 jour[ en UTC, à partir de la config."""
    from datetime import timedelta
    since = datetime.fromisoformat(cfg["start"]).replace(tzinfo=timezone.utc) if cfg.get("start") else None
    until = (datetime.fromisoformat(cfg["end"]).replace(tzinfo=timezone.utc) + timedelta(days=1)) if cfg.get("end") else None
    return since, until


def in_window(items: list[ContentItem], cfg: dict) -> list[ContentItem]:
    since, until = window(cfg)
    return [i for i in items if (since is None or i.ts >= since) and (until is None or i.ts < until)]


def graph_payload(items: list[ContentItem], clusters) -> dict:
    """Graphe biparti sources ↔ histoires (clusters), consommé tel quel par le front."""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    for it in items:
        sid = f"src:{it.author_pseudo}"
        label = it.urls_canon[0] if it.platform == "web" and it.urls_canon else it.author_pseudo[:8]
        n = nodes.setdefault(sid, {"id": sid, "type": "source", "label": label, "platform": it.platform,
                                   "count": 0})
        n["count"] += 1
    by_uid = {i.uid: i for i in items}
    clustered = {a for c in clusters for a in c.authors}
    for n in nodes.values():
        n["clustered"] = n["id"][4:] in clustered
    for c in clusters:
        cid = f"cl:{c.id}"
        first = by_uid.get(c.item_uids[0])
        nodes[cid] = {"id": cid, "type": "cluster", "kind": c.kind, "kinds": c.kinds,
                      "label": c.title or (first.text[:80] if first else c.id),
                      "count": len(c.item_uids), "authors": len(c.authors), "platforms": c.platforms,
                      "level": c.level, "score": c.score, "item_uids": c.item_uids,
                      "signals": [s.model_dump() for s in c.signals],
                      "first_ts": c.first_ts.isoformat(), "last_ts": c.last_ts.isoformat()}
        for a in c.authors:
            if f"src:{a}" in nodes:
                edges.append({"source": f"src:{a}", "target": cid, "kind": c.kind})
    return {"nodes": list(nodes.values()), "edges": edges}


def _apply_stance(clusters, by_uid, narrative: str, false_claim: bool = True) -> None:
    """Ajoute la position (reprend / dément) comme signal explicite, puis recalcule le niveau."""
    from observer.agents import stance
    from observer.core.models import Signal
    for c in sorted(clusters, key=lambda c: -len(c.authors))[:40]:
        try:
            st = stance.assess(c, by_uid, narrative)
        except Exception as e:  # budget atteint, API indisponible…
            log.warning("stance : %s", e)
            return
        if not st:
            continue
        q = (st.get("quote") or "")[:120]
        if st["stance"] == "promotes":
            c.signals.insert(0, Signal(name="stance_promotes", value="promotes", weight=0.3 if false_claim else 0.0,
                                       explanation=(f"Repeats the documented false claim: “{q}” (LLM-assessed)" if false_claim
                                                    else f"Repeats the monitored narrative (not established as false, no weight): “{q}”")))
        elif st["stance"] == "debunks":
            c.signals.insert(0, Signal(name="stance_debunks", value="debunks", weight=0.0,
                                       explanation=f"Fact-check / debunk of the claim: “{q}” (LLM-assessed)"))
        else:
            c.signals.insert(0, Signal(name="stance_neutral", value="neutral", weight=0.0,
                                       explanation=f"Neutral reporting: “{q}” (LLM-assessed)"))
        c.signals = [s for s in c.signals if s.name != "assessment"]
        c.score = round(min(1.0, sum(s.weight for s in c.signals)), 2)
        c.level = "priority" if c.score >= 0.7 else "review" if c.score >= 0.4 else "organic"
        if st["stance"] == "debunks":
            c.level = "organic"  # un démenti n'est jamais une alerte


async def claim_is_false(slug: str, cfg: dict) -> bool:
    """Le récit surveillé est-il une affirmation DOCUMENTÉE comme fausse ? Décidé une fois (LLM) puis stocké
    dans la config ; un événement d'actualité ordinaire (sport, météo…) répond non."""
    if "claim_is_false" in cfg:
        return bool(cfg["claim_is_false"])
    from observer.core import llm
    from observer.core.settings import settings
    try:
        out = llm.complete(model=settings().model_triage, max_tokens=1500, purpose="claim_status",
                           system="Answer only YES or NO: does this description refer to a specific claim or narrative "
                                  "that is false, fabricated or disinformation (documented as such), rather than to an "
                                  "ordinary news event or topic?", user=cfg.get("description") or cfg.get("label", ""))
        val = out.strip().upper().startswith("YES")
    except Exception:
        return True
    ev = await db.get_event(slug)
    cfg2 = ev["config"] | {"claim_is_false": val}
    await db.upsert_event(slug, ev["label"], cfg2, status=ev["status"])
    return val


async def detect(slug: str) -> None:
    from observer.tools.semantic import semantic_clusters
    from observer.tools.text import find_copypasta
    from observer.tools.stories import assess, merge
    from observer.tools import relevance
    items = await db.load_items(slug, limit=8000)
    ev = await db.get_event(slug)
    await step(slug, "relevance", "running")
    todo = [i for i in items if i.relevance is None]
    if todo:
        try:
            for it, r in zip(todo, await asyncio.to_thread(relevance.score, todo, ev["config"])):
                it.relevance = r
            await db.save_items_returning(todo)  # persiste la pertinence
        except Exception as e:
            log.warning("pertinence indisponible : %s", e)
    thr = relevance.threshold(ev["config"])
    off = sum(1 for i in items if i.relevance is not None and i.relevance < thr)
    items = [i for i in items if i.relevance is None or i.relevance >= thr]
    await step(slug, "relevance", "done", len(items), f"{off} off-topic filtered out")
    await step(slug, "narratives", "running")
    from observer.tools.links import find_link_shares
    raw = find_copypasta(items, min_authors=2) + find_link_shares(items)
    try:
        raw += await asyncio.to_thread(semantic_clusters, items)
    except Exception as e:  # budget atteint ou API indisponible : on garde le déterministe
        log.warning("semantic_clusters désactivé : %s", e)
    by_uid = {i.uid: i for i in items}
    clusters = [assess(c, by_uid) for c in merge(raw)]
    await step(slug, "narratives", "done", len(clusters))
    narrative = ev["config"].get("description") or ""
    if narrative:
        await step(slug, "stance", "running")
        await asyncio.to_thread(_apply_stance, clusters, by_uid, narrative, await claim_is_false(slug, ev["config"]))
        await step(slug, "stance", "done", sum(1 for c in clusters if any(x.name.startswith("stance_") for x in c.signals)))
    await db.replace_clusters(slug, clusters)
    await bus.publish(slug, "graph.snapshot", graph_payload(items, clusters))
    await bus.publish(slug, "stats.tick", {
        "items": len(items), "off_topic": off, "clusters": len(clusters),
        "platforms": sorted({i.platform for i in items}),
        "sources": len({i.author_pseudo for i in items}),
        "at": datetime.now(timezone.utc).isoformat()})


async def collect_once(slug: str) -> int:
    from observer.collectors import gnews
    ev = await db.get_event(slug)
    cfg = ev["config"]
    new = 0
    await step(slug, "web", "running")
    for kw in cfg["keywords"]:
        await bus.publish(slug, "collector.status", {"source": "gnews", "query": kw, "state": "running"})
        lang = (cfg.get("keyword_langs") or {}).get(kw, (cfg.get("languages") or ["fr"])[0])
        country = gnews.LANG_COUNTRY.get(lang, cfg.get("country", "US"))
        try:
            items = await gnews.fetch(kw, lang=lang, country=country, event=slug, when=None,
                                      start=cfg.get("start"), end=cfg.get("end"))
        except Exception as e:
            await bus.publish(slug, "collector.status", {"source": "gnews", "query": kw, "state": "error",
                                                         "error": str(e)[:200]})
            continue
        items = in_window(items, cfg)
        inserted = set(await db.save_items_returning(items))
        for it in items:
            if it.uid in inserted:
                await bus.publish(slug, "item.new", it.model_dump(mode="json"))
                await asyncio.sleep(0.05)  # étale l'arrivée pour un flux lisible
        new += len(inserted)
    await step(slug, "web", "done", new)
    new += await _run(slug, "youtube", _collect_youtube(slug, cfg))
    new += await _run(slug, "bluesky", _collect_bluesky(slug, cfg))
    new += await _run(slug, "tiktok", _collect_tiktok(slug, cfg))
    new += await _run(slug, "telegram", _collect_telegram(slug, cfg))
    new += await _run(slug, "networks", _collect_reference_networks(slug, cfg))
    new += await _run(slug, "instagram", _collect_instagram(slug, cfg))
    return new


def apify_spent(r) -> float:
    """Dépense Apify du mois : chiffre réel du compte (API /users/me/limits), sinon compteur local."""
    import httpx

    from observer.core.settings import settings
    cached = r.get("observer:apify:real_usd")
    if cached is not None:
        return float(cached)
    local = float(r.get("observer:apify:spent_usd") or 0)
    try:
        d = httpx.get("https://api.apify.com/v2/users/me/limits", timeout=10,
                      headers={"Authorization": f"Bearer {settings().apify_token}"}).json()["data"]
        real = float(d["current"]["monthlyUsageUsd"])
    except Exception:
        return local
    r.set("observer:apify:real_usd", real, ex=120)
    return max(real, local)


async def _collect_instagram(slug: str, cfg: dict) -> int:
    """Instagram (Apify, payant) : recherche par mot-clé, au plus une fois par TIKTOK_EVERY_MIN minutes."""
    import time

    from observer.collectors import instagram
    from observer.core import llm
    from observer.core.settings import settings
    s = settings()
    if not s.apify_token:
        return 0
    r = llm._r()
    if days_ago(cfg) > 45:
        raise Skip("Instagram search only reaches recent posts (no date filter): event too old")
    spent = apify_spent(r)
    last = float(r.get(f"observer:instagram:last:{slug}") or 0)
    if spent >= s.apify_budget_usd:
        raise Skip("Apify budget reached")
    if time.time() - last < s.tiktok_every_min * 60:
        raise Skip(f"paid source: at most one run every {s.tiktok_every_min} min")
    r.set(f"observer:instagram:last:{slug}", time.time())
    terms = [k for k in cfg["keywords"] if k.isascii()][:3] + cfg.get("hashtags", [])[:1]
    await bus.publish(slug, "collector.status", {"source": "instagram", "query": ", ".join(terms), "state": "running"})
    try:
        items, cost = await asyncio.to_thread(instagram.fetch, terms, slug, 12)
    except Exception as e:
        await bus.publish(slug, "collector.status", {"source": "instagram", "state": "error", "error": str(e)[:200]})
        return 0
    r.incrbyfloat("observer:apify:spent_usd", cost); r.delete("observer:apify:real_usd")
    since = datetime.fromisoformat(cfg["start"]).replace(tzinfo=timezone.utc) if cfg.get("start") else None
    items = [i for i in items if since is None or i.ts >= since]
    items = in_window(items, cfg)
    inserted = set(await db.save_items_returning(items))
    for it in items:
        if it.uid in inserted:
            await bus.publish(slug, "item.new", it.model_dump(mode="json"))
            await asyncio.sleep(0.03)
    return len(inserted)


async def _collect_reference_networks(slug: str, cfg: dict) -> int:
    """Articles récents des réseaux de référence du registre ; la pertinence est filtrée ensuite comme pour le reste."""
    from observer.collectors import network_rss
    if window_is_past(cfg):
        raise Skip("RSS feeds only carry the latest articles: no archive for a past event")
    await bus.publish(slug, "collector.status", {"source": "reference networks", "query": "registry RSS", "state": "running"})
    try:
        items = await network_rss.fetch(slug)
    except Exception as e:
        await bus.publish(slug, "collector.status", {"source": "reference networks", "state": "error", "error": str(e)[:200]})
        return 0
    items = in_window(items, cfg)
    inserted = set(await db.save_items_returning(items))
    return len(inserted)  # pas de diffusion item.new avant le filtre de pertinence (volume élevé, hors-sujets)


async def _collect_telegram(slug: str, cfg: dict) -> int:
    """Telegram sans compte : canaux de la config + canaux cités dans les posts collectés + graines des réseaux de référence."""
    from observer.collectors import telegram_web as tw
    from observer.core import llm
    r = llm._r()
    seeds = r.get("observer:tg:network_seeds")
    if not seeds:
        seeds = json.dumps(await tw.network_seeds())
        r.set("observer:tg:network_seeds", seeds, ex=12 * 3600)
    items_so_far = await db.load_items(slug, limit=5000)
    cited = tw.handles_from_text([" ".join([i.text] + i.links) for i in items_so_far])
    handles = sorted(set(cfg.get("telegram_channels", [])) | set(json.loads(seeds)) | cited)[:80]
    since = datetime.fromisoformat(cfg["start"]).replace(tzinfo=timezone.utc) if cfg.get("start") else None
    await bus.publish(slug, "collector.status", {"source": "telegram", "query": f"{len(handles)} public channels",
                                                 "state": "running"})
    try:
        items = await tw.fetch(handles, cfg["keywords"], cfg.get("hashtags", []), slug, since,
                               known=json.loads(seeds), until=window(cfg)[1],
                               max_pages=int(cfg.get("telegram_max_pages", 8)))
    except Exception as e:
        await bus.publish(slug, "collector.status", {"source": "telegram", "state": "error", "error": str(e)[:200]})
        return 0
    items = in_window(items, cfg)
    inserted = set(await db.save_items_returning(items))
    for it in items:
        if it.uid in inserted:
            await bus.publish(slug, "item.new", it.model_dump(mode="json"))
            await asyncio.sleep(0.03)
    return len(inserted)


async def _collect_tiktok(slug: str, cfg: dict) -> int:
    """TikTok est payant (Apify) : au plus un run toutes les TIKTOK_EVERY_MIN minutes, plafond global suivi."""
    import time

    from observer.collectors import tiktok
    from observer.core import llm
    from observer.core.settings import settings
    s = settings()
    if not s.apify_token:
        return 0
    r = llm._r()
    spent = apify_spent(r)
    last = float(r.get(f"observer:tiktok:last:{slug}") or 0)
    if spent >= s.apify_budget_usd:
        raise Skip("Apify budget reached")
    if time.time() - last < s.tiktok_every_min * 60:
        raise Skip(f"paid source: at most one run every {s.tiktok_every_min} min")
    r.set(f"observer:tiktok:last:{slug}", time.time())
    since = datetime.fromisoformat(cfg["start"]).replace(tzinfo=timezone.utc) if cfg.get("start") else None
    # Recherche de vidéos par mot-clé (une par langue max), triée par pertinence sur le dernier mois
    kl = cfg.get("keyword_langs") or {}
    seen_langs, queries = set(), []
    for k in cfg["keywords"]:
        lang = kl.get(k, "?")
        if lang not in seen_langs or len(queries) < 2:
            seen_langs.add(lang)
            queries.append(k)
        if len(queries) >= 4:
            break
    tags = []
    await bus.publish(slug, "collector.status", {"source": "tiktok", "query": ", ".join(queries), "state": "running"})
    try:
        items, cost = await asyncio.to_thread(tiktok.fetch, tags, queries, slug, 12, 0.5,
                                              cfg.get("start"), cfg.get("end"))
    except Exception as e:
        await bus.publish(slug, "collector.status", {"source": "tiktok", "state": "error", "error": str(e)[:200]})
        return 0
    r.incrbyfloat("observer:apify:spent_usd", cost); r.delete("observer:apify:real_usd")
    items = [i for i in items if since is None or i.ts >= since]
    items = in_window(items, cfg)
    inserted = set(await db.save_items_returning(items))
    for it in items:
        if it.uid in inserted:
            await bus.publish(slug, "item.new", it.model_dump(mode="json"))
            await asyncio.sleep(0.03)
    return len(inserted)


async def _collect_bluesky(slug: str, cfg: dict) -> int:
    from observer.collectors import bluesky
    from observer.core.settings import settings
    if not (settings().bsky_handle and settings().bsky_app_password):
        return 0
    since = datetime.fromisoformat(cfg["start"]).replace(tzinfo=timezone.utc) if cfg.get("start") else None
    local = (cfg.get("languages") or ["fr"])[0]
    def lang_of(q: str) -> str:  # mots-clés anglais repérés par le Planner (mêmes heuristiques que la validation)
        return "en" if q.isascii() and any(w in q.lower() for w in ("protest", "police", "unrest", "french", "strike")) else local
    kl = cfg.get("keyword_langs") or {}
    kws = cfg["keywords"] if kl else cfg["keywords"][:5]
    queries = [(k, kl.get(k) or lang_of(k)) for k in kws] + [(f"#{h}", None if kl else local) for h in cfg.get("hashtags", [])[:4]]
    await bus.publish(slug, "collector.status", {"source": "bluesky", "query": ", ".join(q for q, _ in queries[:3]), "state": "running"})
    try:
        items = await asyncio.to_thread(bluesky.fetch, queries, slug, 50, since, window(cfg)[1])
    except Exception as e:
        await bus.publish(slug, "collector.status", {"source": "bluesky", "state": "error", "error": str(e)[:200]})
        return 0
    items = in_window(items, cfg)
    inserted = set(await db.save_items_returning(items))
    for it in items:
        if it.uid in inserted:
            await bus.publish(slug, "item.new", it.model_dump(mode="json"))
            await asyncio.sleep(0.03)
    return len(inserted)


async def _collect_youtube(slug: str, cfg: dict) -> int:
    from observer.collectors import youtube
    since = datetime.fromisoformat(cfg["start"]).replace(tzinfo=timezone.utc) if cfg.get("start") else None
    await bus.publish(slug, "collector.status", {"source": "youtube", "query": ", ".join(cfg["keywords"][:4]),
                                                 "state": "running"})
    try:
        kl = cfg.get("keyword_langs") or {}
        items = await asyncio.to_thread(youtube.fetch, cfg["keywords"][:5], cfg.get("hashtags", [])[:3],
                                        slug, 10, 6, since, window(cfg)[1], kl)
    except Exception as e:
        await bus.publish(slug, "collector.status", {"source": "youtube", "state": "error", "error": str(e)[:200]})
        return 0
    items = in_window(items, cfg)
    inserted = set(await db.save_items_returning(items))
    for it in items:
        if it.uid in inserted:
            await bus.publish(slug, "item.new", it.model_dump(mode="json"))
            await asyncio.sleep(0.05)
    return len(inserted)


async def _enrich_media(slug: str) -> int:
    from observer.tools import media
    try:
        await bus.publish(slug, "collector.status", {"source": "video analysis", "query": "", "state": "running"})
        enriched, _ = await media.enrich_event(slug, max_items=5, max_usd=0.05)
        return len(enriched)
    except Exception as e:
        log.warning("enrichissement média indisponible : %s", e)
        return 0


async def warm_views(slug: str) -> None:
    """Précalcule les vues lourdes (comptes suspects, coordination, thèmes) pour que les onglets s'ouvrent vite."""
    from observer.api import views
    for fn in (views.suspects, views.coordination, views.themes):
        try:
            await fn(slug)
        except Exception as e:  # une vue en échec ne doit jamais arrêter la collecte
            log.warning("préchauffage %s : %s", fn.__name__, e)


async def loop(slug: str, every_s: int = 180) -> None:
    await db.upsert_status(slug, "live")
    try:
        while True:
            await set_pass(slug, "running")
            new = await collect_once(slug)
            await detect(slug)
            # Vidéos : transcription + texte incrusté + empreintes d'images (≤ 5 par passe, ≤ 0,05 $), puis
            # nouvelle détection pour que les rapprochements par contenu vidéo apparaissent tout de suite.
            await step(slug, "video", "running")
            n_vid = await _enrich_media(slug)
            await step(slug, "video", "done", n_vid)
            if n_vid:
                await detect(slug)
            await warm_views(slug)
            from datetime import timedelta
            await set_pass(slug, "idle", new=new, next_at=(datetime.now(timezone.utc) + timedelta(seconds=every_s)).isoformat())
            await bus.publish(slug, "collector.status", {"source": "all", "state": "idle", "new": new,
                                                         "next_in_s": every_s})
            await asyncio.sleep(every_s)
    finally:
        await db.upsert_status(slug, "stopped")
        await set_pass(slug, "idle", stopped=True)  # sinon l'interface affiche une passe « en cours » fantôme


def start(slug: str) -> bool:
    if slug in _tasks and not _tasks[slug].done():
        return False
    _tasks[slug] = asyncio.create_task(loop(slug))
    return True


def stop(slug: str) -> bool:
    t = _tasks.pop(slug, None)
    if t:
        t.cancel()
    return bool(t)
