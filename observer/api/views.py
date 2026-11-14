"""Vues agrégées pour l'interface (Brief, Stories, Network, Accounts). Lecture seule, déterministes.

Tout part des items pertinents et des histoires déjà calculées ; aucune requête externe, aucun appel LLM.
"""
from __future__ import annotations

import itertools
from collections import Counter, defaultdict
from datetime import datetime, timezone

import networkx as nx
from fastapi import APIRouter, HTTPException

from observer.core import db
from observer.core.models import Cluster, ContentItem
from observer.tools.relevance import threshold

router = APIRouter(prefix="/api/events/{slug}")
PERSONAL = {"bluesky", "tiktok", "instagram", "mastodon", "x"}  # comptes de particuliers : pas de pseudo en clair


def stance_of(c: Cluster) -> str:
    for s in c.signals:
        if s.name.startswith("stance_"):
            return s.name.removeprefix("stance_")
    return "unclassified"


def _guess_format(i: ContentItem) -> str:
    """Format des items collectés avant l'ajout du champ `format`."""
    if i.platform == "youtube":
        return "short" if i.url and "/shorts/" in i.url else "video"
    return {"tiktok": "video", "instagram": "post", "bluesky": "post", "telegram": "message", "web": "article"}.get(i.platform, "post")


def account_label(it: ContentItem) -> str:
    if it.platform in PERSONAL:
        return f"{it.platform}·{it.author_pseudo[:6]}"
    return (it.urls_canon[0] if it.urls_canon and it.urls_canon[0] else it.author_pseudo[:8])


def account_flags(its: list[ContentItem]) -> list[dict]:
    """Indicateurs de risque explicables pour un compte (à partir de ses items)."""
    from observer.tools.reputation import label_for
    flags: list[dict] = []
    a = its[0].account
    if a.known_network:
        flags.append({"key": "listed", "label": "Listed source", "detail": a.known_network, "risk": "high"})
    else:
        for it in its:
            lab = next((label_for(x) for x in (it.urls_canon[:1] if it.platform == "web" else []) if label_for(x)), None)
            if lab:
                flags.append({"key": "listed", "label": "Listed source", "detail": lab, "risk": "high"})
                break
    if a.automated_declared:
        flags.append({"key": "bot", "label": "Self-declared bot", "detail": "Account labelled as automated", "risk": "high"})
    if a.created_at:
        days = (max(i.ts for i in its) - a.created_at).days
        if days < 30:
            flags.append({"key": "new", "label": "New account", "detail": f"Created {days} days before posting", "risk": "medium"})
    if a.followers is not None and a.followers < 50 and its[0].platform in PERSONAL:
        flags.append({"key": "low_audience", "label": "Low audience", "detail": f"{a.followers} followers", "risk": "low"})
    return flags


def risk_level(flags: list[dict]) -> str:
    r = {f["risk"] for f in flags}
    return "high" if "high" in r else "medium" if "medium" in r else "none"


# Pendant une publication (instantané pour la démo), des centaines de vues sont calculées d'affilée sur les mêmes
# données : on les charge une seule fois. Hors publication, MEMO vaut None et rien n'est mémorisé.
from contextvars import ContextVar  # noqa: E402

MEMO: ContextVar[dict | None] = ContextVar("observer_views_memo", default=None)


async def _load(slug: str) -> tuple[dict, list[ContentItem], list[Cluster]]:
    memo = MEMO.get()
    if memo is not None:
        if ("load", slug) not in memo:
            memo[("load", slug)] = await _load_fresh(slug)
        return memo[("load", slug)]
    return await _load_fresh(slug)


async def _load_fresh(slug: str) -> tuple[dict, list[ContentItem], list[Cluster]]:
    ev = await db.get_event(slug)
    if not ev:
        raise HTTPException(404, "unknown event")
    thr = threshold(ev["config"])
    items = [i for i in await db.load_items(slug, limit=20000) if i.relevance is None or i.relevance >= thr]
    return ev, items, await db.load_clusters(slug)


def _item_stance(clusters: list[Cluster]) -> dict[str, str]:
    """Chaque item hérite de la position de son histoire (sinon « unclassified »)."""
    out: dict[str, str] = {}
    for c in clusters:
        st = stance_of(c)
        for u in c.item_uids:
            if out.get(u) in (None, "unclassified", "neutral"):
                out[u] = st
    return out


def _accounts(items: list[ContentItem], clusters: list[Cluster]) -> dict[str, dict]:
    by_author: dict[str, list[ContentItem]] = defaultdict(list)
    for i in items:
        by_author[i.author_pseudo].append(i)
    stories_of: dict[str, set[str]] = defaultdict(set)
    stance_mix: dict[str, Counter] = defaultdict(Counter)
    for c in clusters:
        st = stance_of(c)
        for a in c.authors:
            stories_of[a].add(c.id)
            stance_mix[a][st] += 1
    out = {}
    for a, its in by_author.items():
        its.sort(key=lambda i: i.ts)
        flags = account_flags(its)
        acc = its[0].account
        out[a] = {
            "id": a, "label": account_label(its[0]), "platform": its[0].platform,
            "items": len(its), "stories": sorted(stories_of[a]), "stance_mix": dict(stance_mix[a]),
            "followers": acc.followers, "created_at": acc.created_at.isoformat() if acc.created_at else None,
            "flags": flags, "risk": risk_level(flags),
            "first_ts": its[0].ts.isoformat(), "last_ts": its[-1].ts.isoformat(),
        }
    return out


def _story_card(c: Cluster, by_uid: dict[str, ContentItem]) -> dict:
    its = sorted((by_uid[u] for u in c.item_uids if u in by_uid), key=lambda i: i.ts)
    days = Counter(i.ts.date().isoformat() for i in its)
    return {
        "id": c.id, "title": c.title, "level": c.level, "score": c.score, "stance": stance_of(c),
        "platforms": c.platforms, "items": len(c.item_uids), "accounts": len(c.authors),
        "first_ts": c.first_ts.isoformat(), "last_ts": c.last_ts.isoformat(),
        "headline_signal": next((s.explanation for s in c.signals if s.weight > 0 and not s.name.startswith("stance_")), None),
        "stance_quote": next((s.explanation for s in c.signals if s.name.startswith("stance_")), None),
        "days": sorted(days.items()),
    }


def _peaks(series: dict) -> list[dict]:
    from observer.tools.bursts import robust_peaks
    return robust_peaks([(d, sum(series[d].values())) for d in sorted(series)])


@router.get("/summary")
async def summary(slug: str) -> dict:
    ev, items, clusters = await _load(slug)
    by_uid = {i.uid: i for i in items}
    st = _item_stance(clusters)
    series: dict[str, Counter] = defaultdict(Counter)        # jour -> position -> n
    by_platform: dict[str, Counter] = defaultdict(Counter)   # plateforme -> jour -> n
    for i in items:
        d = i.ts.date().isoformat()
        series[d][st.get(i.uid, "unclassified")] += 1
        by_platform[i.platform][d] += 1
    accounts = _accounts(items, clusters)
    stories = sorted((_story_card(c, by_uid) for c in clusters),
                     key=lambda s: (-{"priority": 2, "review": 1}.get(s["level"], 0), -s["score"], -s["accounts"]))
    top_acc = sorted(accounts.values(), key=lambda a: (-len(a["stories"]), {"high": 0, "medium": 1}.get(a["risk"], 2), -a["items"]))
    cfg = ev["config"]
    return {
        "event": {"slug": slug, "label": ev["label"], "description": cfg.get("description"),
                  "sources": cfg.get("sources", []), "start": cfg.get("start"), "end": cfg.get("end"),
                  "keywords": cfg.get("keywords", []), "languages": cfg.get("languages", [])},
        "kpis": {
            "items": len(items), "accounts": len(accounts), "platforms": len({i.platform for i in items}),
            "stories": len(clusters), "priority": sum(c.level == "priority" for c in clusters),
            "review": sum(c.level == "review" for c in clusters),
            "promotes": sum(stance_of(c) == "promotes" for c in clusters),
            "debunks": sum(stance_of(c) == "debunks" for c in clusters),
        },
        "daily": [{"day": d, **dict(series[d])} for d in sorted(series)],
        "peaks": _peaks(series),
        "platform_daily": {p: sorted(c.items()) for p, c in by_platform.items()},
        "stories": stories,
        "top_accounts": top_acc[:8],
    }


@router.get("/stories/{story_id}")
async def story(slug: str, story_id: str) -> dict:
    import asyncio

    from observer.tools.semantic import embed
    _, items, clusters = await _load(slug)
    c = next((c for c in clusters if c.id == story_id), None)
    if not c:
        raise HTTPException(404, "unknown story")
    by_uid = {i.uid: i for i in items}
    its = sorted((by_uid[u] for u in c.item_uids if u in by_uid), key=lambda i: i.ts)
    sims: list[float | None] = [None] * len(its)
    if its:
        try:  # similarité de SENS avec la première publication (embeddings en cache ; traductions comprises)
            v = await asyncio.to_thread(embed, [i.full_text()[:1500] for i in its])
            sims = [round(float(x), 2) for x in v @ v[0]]
        except Exception:
            pass
    accounts = _accounts(its, [c])
    return {
        **_story_card(c, by_uid),
        "signals": [s.model_dump() for s in c.signals],
        "publications": [{
            "uid": i.uid, "platform": i.platform, "format": i.format or _guess_format(i), "ts": i.ts.isoformat(), "url": i.url, "text": i.full_text()[:600],
            "account": accounts[i.author_pseudo]["label"], "account_id": i.author_pseudo,
            "similarity": sims[k], "links": [l for l in i.links if not l.startswith("frame-phash:")][:3],
            "transcript": (i.transcript or "")[:400] or None, "ocr": (i.ocr_text or "")[:200] or None,
            "caption": i.text[:600]} for k, i in enumerate(its)],
        "accounts_detail": sorted(accounts.values(), key=lambda a: a["first_ts"]),
        "evidence": [e.model_dump() for e in c.evidence[:30]],
    }


@router.get("/network")
async def network(slug: str, max_nodes: int = 160) -> dict:
    """Graphe PROJETÉ comptes ↔ comptes (méthode CooRnet) : lien = ont publié dans la même histoire."""
    _, items, clusters = await _load(slug)
    accounts = _accounts(items, clusters)
    g = nx.Graph()
    for c in clusters:
        st = stance_of(c)
        for a, b in itertools.combinations(sorted(set(c.authors)), 2):
            if g.has_edge(a, b):
                g[a][b]["stories"].append(c.id)
                g[a][b]["stances"][st] += 1
            else:
                g.add_edge(a, b, stories=[c.id], stances=Counter({st: 1}))
        if len(set(c.authors)) == 1:
            g.add_node(c.authors[0])
    keep = sorted(g.nodes, key=lambda n: (-g.degree(n), -accounts.get(n, {}).get("items", 0)))[:max_nodes]
    g = g.subgraph(keep).copy()
    comms = nx.community.louvain_communities(g, seed=42) if g.number_of_edges() else [set(g.nodes)]
    titles = {c.id: c.title for c in clusters}
    communities = []
    for k, members in enumerate(sorted(comms, key=len, reverse=True)):
        story_counts = Counter(s for a in members for s in accounts.get(a, {}).get("stories", []))
        top = story_counts.most_common(1)[0][0] if story_counts else None
        communities.append({"id": k, "size": len(members), "name": (titles.get(top) or "")[:60], "members": sorted(members)})
    comm_of = {a: c["id"] for c in communities for a in c["members"]}
    nodes = [{**accounts[n], "community": comm_of.get(n), "degree": g.degree(n)} for n in g.nodes if n in accounts]
    edges = [{"source": a, "target": b, "weight": len(d["stories"]), "stories": d["stories"],
              "stance": d["stances"].most_common(1)[0][0]} for a, b, d in g.edges(data=True)]
    return {"nodes": nodes, "edges": edges, "communities": communities,
            "stories": {c.id: {"title": c.title, "stance": stance_of(c), "level": c.level} for c in clusters}}


@router.get("/accounts")
async def accounts(slug: str) -> list[dict]:
    _, items, clusters = await _load(slug)
    acc = _accounts(items, clusters)
    return sorted(acc.values(), key=lambda a: ({"high": 0, "medium": 1}.get(a["risk"], 2), -len(a["stories"]), -a["items"]))


_CACHE: dict[tuple, dict] = {}


async def _cached(name: str, slug: str, n: int, latest, fn):
    """Les vues lourdes ne sont recalculées que si les données ont changé (nombre d'items, dernière date)."""
    key = (name, slug, n, latest)
    if key not in _CACHE:
        for k in [k for k in _CACHE if k[:2] == (name, slug)]:
            del _CACHE[k]
        _CACHE[key] = await fn()
    return _CACHE[key]


async def _suspect_rows(slug: str, items, clusters, all_items) -> list[dict]:
    from observer.tools import suspects as sus

    async def run():
        return sus.rank(items, clusters, _accounts(items, clusters), all_items=all_items)
    return await _cached("suspects", slug, len(all_items) + len(clusters), max((i.ts for i in all_items), default=None), run)


@router.get("/coordination")
async def coordination(slug: str) -> dict:
    """Réseau de coordination comptes ↔ comptes, communautés et code-barres temporel (tools/coordination.py)."""
    from observer.tools import coordination as co
    _, items, clusters = await _load(slug)
    all_items = await db.load_items(slug, limit=20000)
    sus = {r["id"]: r for r in await _suspect_rows(slug, items, clusters, all_items)}

    on_topic = {i.author_pseudo for i in items}  # comptes ayant au moins une publication pertinente
    scope = [i for i in all_items if i.author_pseudo in on_topic]

    async def run():
        return co.build(scope, _accounts(scope, clusters), sus)
    out = await _cached("coordination", slug, len(all_items) + len(clusters), max((i.ts for i in all_items), default=None), run)
    return {**out, "generated_at": datetime.now(timezone.utc).isoformat()}


@router.get("/themes")
async def themes(slug: str) -> dict:
    """Thèmes de l'événement et qui les pousse (tools/themes.py)."""
    import asyncio

    from observer.tools import themes as th
    _, items, clusters = await _load(slug)
    all_items = await db.load_items(slug, limit=20000)
    sus = {r["id"]: r for r in await _suspect_rows(slug, items, clusters, all_items)}
    acc = _accounts(items, clusters)
    source = {}
    for a, d in acc.items():
        if any(f["key"] == "listed" for f in d["flags"]):
            source[a] = "listed"
        elif sus.get(a, {}).get("declared_bot") or (sus.get(a, {}).get("posts_per_day") or 0) >= 72:
            source[a] = "automated"
        elif d["platform"] == "web":
            source[a] = "media"
        else:
            source[a] = "social"

    async def run():
        return await asyncio.to_thread(th.build, items, clusters, source, _item_stance(clusters),
                                       {a: d["label"] for a, d in acc.items()})
    out = await _cached("themes", slug, len(items) + len(clusters), max((i.ts for i in items), default=None), run)
    return {**out, "generated_at": datetime.now(timezone.utc).isoformat()}


@router.get("/suspects")
async def suspects(slug: str) -> dict:
    """Comptes suspects de coordination, classés, chacun avec ses preuves (voir tools/suspects.py)."""
    from observer.tools import suspects as sus
    _, items, clusters = await _load(slug)
    rows = await _suspect_rows(slug, items, clusters, await db.load_items(slug, limit=20000))
    return {"accounts": rows, "weights": sus.WEIGHTS, "thresholds": {"likely": sus.LIKELY, "review": sus.REVIEW},
            "window_min": sus.WINDOW_MIN, "generated_at": datetime.now(timezone.utc).isoformat()}


@router.get("/accounts/{account_id}")
async def account(slug: str, account_id: str) -> dict:
    _, items, clusters = await _load(slug)
    memo = MEMO.get()
    if memo is not None and ("acc", slug) in memo:
        all_acc, st, by_author = memo[("acc", slug)]
    else:
        all_acc, st = _accounts(items, clusters), _item_stance(clusters)
        by_author = defaultdict(list)
        for i in items:
            by_author[i.author_pseudo].append(i)
        if memo is not None:
            memo[("acc", slug)] = (all_acc, st, by_author)
    acc = all_acc.get(account_id)
    if not acc:
        raise HTTPException(404, "unknown account")
    its = sorted(by_author.get(account_id, []), key=lambda i: i.ts, reverse=True)
    titles = {c.id: {"title": c.title, "stance": stance_of(c), "level": c.level} for c in clusters if c.id in acc["stories"]}
    return {**acc, "story_info": titles, "publications": [{"uid": i.uid, "ts": i.ts.isoformat(), "url": i.url, "text": i.full_text()[:400],
                                     "format": i.format or _guess_format(i),
                                     "stance": st.get(i.uid, "unclassified")} for i in its[:50]],
            "generated_at": datetime.now(timezone.utc).isoformat()}


@router.post("/stories/{story_id}/investigate")
async def investigate_story(slug: str, story_id: str, force: bool = False, cached_only: bool = False) -> dict:
    """Lance (ou relit en cache) l'enquête Enquêteur ⇄ Sceptique → Juge sur un narratif.

    `cached_only` (imposé pour le compte de démonstration) : ne relit que le cache, aucun appel LLM payant."""
    import asyncio

    from observer.agents.investigation import investigate
    from observer.core import llm
    ev = await db.get_event(slug)
    detail = await story(slug, story_id)
    narrative = (ev["config"] or {}).get("description", "")
    if cached_only:
        from observer.agents.investigation import cached
        hit = cached(detail, narrative)
        if hit is None:
            raise HTTPException(404, "This narrative has not been investigated yet (demo accounts can only read existing investigations).")
        return hit
    try:
        return await asyncio.to_thread(investigate, detail, narrative, force)
    except llm.BudgetExceeded as e:
        raise HTTPException(402, str(e)) from e
