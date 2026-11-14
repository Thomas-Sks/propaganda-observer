"""Diffusion entre plateformes : comment un contenu passe d'une plateforme à l'autre, et à quelle vitesse.

Pas de « patient zéro » : une mobilisation a des milliers de points de départ et notre collecte ne voit qu'une
partie du web (pas de X, pas de groupes privés). On mesure seulement des SAUTS observés :
une publication sur la plateforme B qui reprend une publication antérieure de la plateforme A.

Attribution du parent (cf. Sheng et al., « How the cascade inference problem distorts information diffusion »,
arXiv 2410.21554 : un lien déduit n'est pas un lien observé, on les distingue) :
- prouvé  : la publication cite l'URL de la publication antérieure, ou le canal Telegram qui l'a publiée ;
- déduit  : sinon, la publication antérieure dont le texte écrit est le plus proche (Jaccard ≥ INFER_SIM).

Groupes examinés : chaque narratif, plus chaque groupe de copies quasi identiques sur TOUT ce qui a été collecté
(un relais vers un site Pravda peut être jugé hors sujet et n'appartenir à aucun narratif).
Horodatages arrondis à l'heure (Google News, jours passés) exclus : ils fausseraient les délais.
"""
from __future__ import annotations

import statistics
from collections import defaultdict

from observer.core.models import Cluster, ContentItem
from observer.tools.links import precise
from observer.tools.suspects import own_text
from observer.tools.text import find_copypasta, minhash, normalize

INFER_SIM = 0.3          # similarité minimale pour un parent déduit
MAX_LAG_H = 72           # au-delà, on ne relie plus deux publications
FAST_MIN, SLOW_MIN = 15, 360   # zones « vitesse de relais » (≤ 15 min) et « partage organique » (> 6 h)


def _channel(it: ContentItem) -> str | None:
    """Identifiant citable de la source : canal Telegram (« t.me/x ») ou None."""
    if it.platform == "telegram" and it.urls_canon and it.urls_canon[0].startswith("t.me/"):
        return it.urls_canon[0].split("/")[1].lower()
    return None


def _cites(child: ContentItem, parent: ContentItem) -> str | None:
    """Preuve explicite que `child` reprend `parent` (texte de la preuve), sinon None."""
    hay = ((child.text or "") + " " + " ".join(child.links)).lower()
    if parent.url and parent.url.split("://")[-1].lower().rstrip("/") in hay:
        return "links to the earlier post"
    ch = _channel(parent)
    if ch and (f"t.me/{ch}" in hay or f"@{ch}" in hay or f"[forwarded from] {ch}" in hay):
        return f"cites the Telegram channel {ch}"
    return None


def hops(items: list[ContentItem], clusters: list[Cluster]) -> list[dict]:
    """Sauts entre plateformes (dédoublonnés), avec preuve ou similarité."""
    by_uid = {i.uid: i for i in items}
    own = [i.model_copy(update={"text": own_text(i)}) for i in items if precise(i)]
    groups: list[tuple[str | None, list[str]]] = [(c.id, c.item_uids) for c in clusters]
    groups += [(None, c.item_uids) for c in find_copypasta(own, min_authors=2)]
    story_of: dict[str, str] = {}
    for c in clusters:
        for u in c.item_uids:
            story_of.setdefault(u, c.id)
    sig_cache: dict[str, object] = {}

    def sig(it: ContentItem):
        if it.uid not in sig_cache:
            sig_cache[it.uid] = minhash(normalize(own_text(it) + " " + (it.transcript or "") + " " + (it.ocr_text or "")))
        return sig_cache[it.uid]

    out: dict[tuple[str, str], dict] = {}
    for gid, uids in groups:
        its = sorted((by_uid[u] for u in uids if u in by_uid and precise(by_uid[u])), key=lambda i: i.ts)
        if len({i.platform for i in its}) < 2:
            continue
        for k, child in enumerate(its[1:], 1):
            prev = [p for p in its[:k] if (child.ts - p.ts).total_seconds() <= MAX_LAG_H * 3600 and p.author_pseudo != child.author_pseudo]
            if not prev:
                continue
            parent, kind, why = None, None, None
            for p in reversed(prev):
                why = _cites(child, p)
                if why:
                    parent, kind = p, "proven"
                    break
            if parent is None:
                best = max(prev, key=lambda p: sig(p).jaccard(sig(child)))
                s = sig(best).jaccard(sig(child))
                if s >= INFER_SIM:
                    parent, kind, why = best, "inferred", f"closest earlier text (similarity {s:.2f})"
            if parent is None or parent.platform == child.platform:
                continue
            key = (parent.uid, child.uid)
            if key in out and out[key]["kind"] == "proven":
                continue
            out[key] = {"from_uid": parent.uid, "to_uid": child.uid, "from_platform": parent.platform,
                        "to_platform": child.platform, "from_author": parent.author_pseudo, "to_author": child.author_pseudo,
                        "from_ts": parent.ts.isoformat(), "to_ts": child.ts.isoformat(),
                        "delay_min": round((child.ts - parent.ts).total_seconds() / 60, 1), "kind": kind, "why": why,
                        "story": gid or story_of.get(child.uid) or story_of.get(parent.uid),
                        "text": " ".join(own_text(child).split())[:220]}
    # Un enfant n'a qu'un parent : on garde le lien prouvé, sinon le plus proche dans le temps
    best_for_child: dict[str, dict] = {}
    for h in out.values():
        cur = best_for_child.get(h["to_uid"])
        if cur is None or (h["kind"], -h["delay_min"]) > (cur["kind"], -cur["delay_min"]):
            best_for_child[h["to_uid"]] = h
    return sorted(best_for_child.values(), key=lambda h: h["delay_min"])


def _q(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))]


def flows(hs: list[dict]) -> list[dict]:
    """Agrégat par sens (plateforme A → plateforme B) : volume, preuves, délais (médiane, quartiles, zones)."""
    by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for h in hs:
        by[(h["from_platform"], h["to_platform"])].append(h)
    out = []
    for (a, b), rows in by.items():
        d = [r["delay_min"] for r in rows]
        out.append({"from": a, "to": b, "n": len(rows), "proven": sum(r["kind"] == "proven" for r in rows),
                    "median_min": round(statistics.median(d), 1), "p25_min": round(_q(d, 0.25), 1), "p75_min": round(_q(d, 0.75), 1),
                    "fast_share": round(sum(x <= FAST_MIN for x in d) / len(d), 3),
                    "slow_share": round(sum(x > SLOW_MIN for x in d) / len(d), 3),
                    "delays": [{"min": r["delay_min"], "kind": r["kind"]} for r in rows]})
    return sorted(out, key=lambda f: (f["median_min"], -f["n"]))


def story_diffusion(story_items: list[ContentItem], story_hops: list[dict]) -> dict:
    """Pour un narratif : arrivée sur chaque plateforme (première apparition DANS NOS DONNÉES) et sauts."""
    entry: dict[str, dict] = {}
    for i in sorted(story_items, key=lambda i: i.ts):
        e = entry.setdefault(i.platform, {"platform": i.platform, "first_ts": i.ts.isoformat(), "n": 0, "precise": precise(i)})
        e["n"] += 1
    return {"entries": sorted(entry.values(), key=lambda e: e["first_ts"]), "hops": story_hops}
