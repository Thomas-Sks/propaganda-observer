"""Réseau de coordination entre comptes (approche CooRnet / CooRTweet, Giglietto et al. 2020 ; Righetti 2024).

1. Chaque publication produit des « actions » : partager un TEXTE (écrit par le compte, quasi identique à celui
   d'un autre), un LIEN (URL canonique) ou une COMBINAISON DE HASHTAGS (≥ 2 hashtags identiques).
2. La fenêtre de coordination n'est pas fixée à la main : comme CooRnet, on la tire des données, au 10e centile
   des délais de reprise d'une même action (bornée entre 1 et 10 minutes).
3. Deux comptes sont reliés s'ils ont fait la même action dans cette fenêtre. Poids = nombre d'actions
   distinctes partagées ; un lien « fort » = au moins 2 actions distinctes (une coïncidence arrive une fois).
4. Communautés : Louvain (graine fixe) ; nom déterministe tiré de ce que la communauté partage.

Garde-fous repris du reste du projet : horodatages précis seulement, dépêches et citations attribuées écartées,
grands médias établis écartés, carte d'aperçu des liens ignorée.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta

import networkx as nx
import numpy as np

from observer.core.models import ContentItem
from observer.tools.links import canonical_url, precise
from observer.tools.provenance import media_registry
from observer.tools.stories import is_quoted_or_wire
from observer.tools.suspects import own_text
from observer.tools.text import find_copypasta

MIN_WINDOW_S, MAX_WINDOW_S, QUANTILE = 60, 600, 0.10
KINDS = ("text", "link", "hashtags")


def _domain(url: str) -> str:
    parts = url.split("/")
    return parts[2].removeprefix("www.") if len(parts) > 2 else url


def actions(items: list[ContentItem], label_of: dict[str, str]) -> dict[str, list[tuple[str, ContentItem]]]:
    """{clé d'action: [(compte, item)]}. Clés : 'text:<groupe>', 'link:<url>', 'hashtags:<a,b,…>'."""
    majors = set(media_registry())
    keep = [i for i in items if precise(i) and not (i.platform == "web" and label_of.get(i.author_pseudo, "").removeprefix("www.") in majors)]
    out: dict[str, list[tuple[str, ContentItem]]] = defaultdict(list)
    # Texte : copies quasi identiques du texte ÉCRIT par le compte (sans la carte du lien partagé)
    own = [i.model_copy(update={"text": own_text(i), "transcript": None, "ocr_text": None}) for i in keep
           if not is_quoted_or_wire(own_text(i))]
    by_uid = {i.uid: i for i in keep}
    for c in find_copypasta(own, min_authors=2):
        for u in c.item_uids:
            out[f"text:{c.id}"].append((by_uid[u].author_pseudo, by_uid[u]))
    for i in keep:
        me = label_of.get(i.author_pseudo, "")
        for x in {canonical_url(x) for x in i.links if x.startswith("http")}:
            if me and me in x:  # lien vers son propre site / canal : pas une action partagée
                continue
            out[f"link:{x}"].append((i.author_pseudo, i))
        tags = sorted({h.lower().lstrip("#") for h in i.hashtags if h})
        if len(tags) >= 2:
            out["hashtags:" + ",".join(tags[:6])].append((i.author_pseudo, i))
    return {k: v for k, v in out.items() if len({a for a, _ in v}) >= 2}


def coordination_interval(acts: dict[str, list[tuple[str, ContentItem]]]) -> tuple[int, int]:
    """(fenêtre en secondes, nombre de délais observés) : 10e centile des délais de reprise après le 1er partage."""
    delays = []
    for v in acts.values():
        ts = sorted(i.ts for _, i in v)
        delays += [(t - ts[0]).total_seconds() for t in ts[1:] if t > ts[0]]
    if not delays:
        return MAX_WINDOW_S, 0
    return int(min(MAX_WINDOW_S, max(MIN_WINDOW_S, float(np.quantile(delays, QUANTILE))))), len(delays)


def _name(members: list[dict], keys: Counter) -> tuple[str, str]:
    """Nom lisible et déterministe d'une communauté, d'après ses membres et ce qu'elle partage."""
    listed = Counter(m["listed"] for m in members if m["listed"])
    if listed and listed.most_common(1)[0][1] >= max(2, len(members) / 2):
        lab = listed.most_common(1)[0][0]
        return f"{lab.split('(')[0].strip()} relays", "Most members are sources from a documented network"
    if sum(m["automated"] for m in members) >= max(2, len(members) / 2):
        return "Automated accounts", "Most members post at bot-like volume or declare themselves automated"
    kind_count = Counter(k.split(":", 1)[0] for k in keys.elements())
    kind = kind_count.most_common(1)[0][0] if kind_count else "text"
    top = [k for k, _ in keys.most_common() if k.startswith(kind + ":")]
    if kind == "link" and top:
        doms = Counter(_domain(k.split(":", 1)[1]) for k in top)
        d, n = doms.most_common(1)[0]
        if n >= len(top) / 2:
            return f"Pushing {d}", "Same links shared within minutes"
        return "Same links", f"Same links ({', '.join(x for x, _ in doms.most_common(3))}…) shared within minutes"
    if kind == "hashtags" and top:
        return "#" + " #".join(top[0].split(":", 1)[1].split(",")[:3]), "Same hashtag combination within minutes"
    return "Same text", "Near-identical posts within minutes"


def build(items: list[ContentItem], accounts: dict[str, dict], suspects: dict[str, dict] | None = None) -> dict:
    """Réseau de coordination complet pour l'interface. `accounts` = views._accounts (sur TOUS les items)."""
    suspects = suspects or {}
    label_of = {a: d["label"] for a, d in accounts.items()}
    acts = actions(items, label_of)
    window_s, n_delays = coordination_interval(acts)
    win = timedelta(seconds=window_s)
    edges: dict[tuple[str, str], dict] = {}
    coord_uids: dict[str, set[str]] = defaultdict(set)  # publications impliquées dans une action coordonnée
    for key, v in acts.items():
        v = sorted(v, key=lambda x: x[1].ts)
        kind = key.split(":", 1)[0]
        for k, (a, ia) in enumerate(v):
            for b, ib in v[k + 1:]:
                if ib.ts - ia.ts > win:
                    break
                if a == b:
                    continue
                e = edges.setdefault(tuple(sorted((a, b))), {"keys": set(), "kinds": Counter(), "examples": []})
                if key not in e["keys"]:
                    e["keys"].add(key)
                    e["kinds"][kind] += 1
                    if len(e["examples"]) < 4:
                        e["examples"].append({"kind": kind, "key": key.split(":", 1)[1] if kind != "text" else "",
                                              "text": own_text(ia)[:220], "a_ts": ia.ts.isoformat(), "b_ts": ib.ts.isoformat(),
                                              "delay_s": int((ib.ts - ia.ts).total_seconds())})
                coord_uids[a].add(ia.uid)
                coord_uids[b].add(ib.uid)
    g = nx.Graph()
    for (a, b), e in edges.items():
        g.add_edge(a, b, weight=len(e["keys"]))
    comms = nx.community.louvain_communities(g, weight="weight", seed=42) if g.number_of_edges() else []
    comm_of = {n: k for k, c in enumerate(sorted(comms, key=lambda c: (-len(c), min(c)))) for n in c}

    by_author: dict[str, list[ContentItem]] = defaultdict(list)
    for i in items:
        by_author[i.author_pseudo].append(i)

    def member(a: str) -> dict:
        acc = accounts.get(a, {})
        sus = suspects.get(a, {})
        listed = next((f["detail"] for f in acc.get("flags", []) if f["key"] == "listed"), None)
        automated = bool(sus.get("declared_bot") or (sus.get("posts_per_day") or 0) >= 72)
        return {"id": a, "label": acc.get("label", a[:8]), "platform": acc.get("platform"), "listed": listed,
                "automated": automated, "suspect_level": sus.get("level"), "suspect_score": sus.get("score"),
                "posts": len(by_author[a]), "coordinated_posts": len(coord_uids[a]),
                "degree": g.degree(a), "strength": g.degree(a, weight="weight"), "community": comm_of.get(a)}

    nodes = [member(a) for a in g.nodes]
    node_by = {n["id"]: n for n in nodes}
    out_edges = []
    for (a, b), e in edges.items():
        out_edges.append({"source": a, "target": b, "weight": len(e["keys"]), "strong": len(e["keys"]) >= 2,
                          "kind": e["kinds"].most_common(1)[0][0], "kinds": dict(e["kinds"]), "examples": e["examples"]})
    communities = []
    for k, c in enumerate(sorted(comms, key=lambda c: (-len(c), min(c)))):
        members = sorted((node_by[a] for a in c), key=lambda m: -m["strength"])
        keys = Counter()
        internal = [e for e in out_edges if e["source"] in c and e["target"] in c]
        for (a, b), e in edges.items():
            if a in c and b in c:
                keys.update(e["keys"])
        name, why = _name(members, keys)
        shared = []
        for key, n in keys.most_common(6):
            kind, val = key.split(":", 1)
            ex = next((own_text(i) for _, i in acts[key]), "")
            shared.append({"kind": kind, "value": val if kind != "text" else ex[:240], "pairs": n,
                           "accounts": len({a for a, _ in acts[key] if a in c})})
        ts = sorted(i.ts for a in c for i in by_author[a] if i.uid in coord_uids[a])
        communities.append({
            "id": k, "name": name, "why": why, "size": len(c), "members": [m["id"] for m in members],
            "edges": len(internal), "strong_edges": sum(e["strong"] for e in internal),
            "kinds": dict(Counter(e["kind"] for e in internal)),
            "platforms": dict(Counter(m["platform"] for m in members)),
            "listed": sum(bool(m["listed"]) for m in members), "automated": sum(m["automated"] for m in members),
            "first_ts": ts[0].isoformat() if ts else None, "last_ts": ts[-1].isoformat() if ts else None,
            "shared": shared,
        })
    # Code-barres : toutes les publications des comptes coordonnés (≤ 400 chacun), marquées si coordonnées
    barcode = {a: [{"ts": i.ts.isoformat(), "c": i.uid in coord_uids[a]}
                   for i in sorted(by_author[a], key=lambda i: i.ts)[-400:]] for a in g.nodes}
    return {
        "window_s": window_s, "n_delays": n_delays, "quantile": QUANTILE, "actions": len(acts),
        "action_kinds": dict(Counter(k.split(":", 1)[0] for k in acts)),
        "nodes": nodes, "edges": out_edges, "communities": communities, "barcode": barcode,
        "method": [
            f"An action is posting the same own text, the same link or the same hashtag combination as another account ({len(acts)} shared actions found).",
            f"Coordination window learnt from the data: {QUANTILE:.0%} quantile of re-share delays = {window_s}s (bounded 60–600 s, CooRnet method).",
            "Two accounts are linked when they performed the same action within that window; a strong link needs at least 2 distinct actions.",
            "Communities: Louvain (fixed seed). Wire copies, attributed quotes, imprecise timestamps and major media are excluded.",
        ],
    }
