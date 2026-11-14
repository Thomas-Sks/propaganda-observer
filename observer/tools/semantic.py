"""Regroupement sémantique (même histoire / paraphrase / traduction) par embeddings + seuil cosinus.

Embeddings via l'AI Router (`text-embedding-3-small`, coût négligeable), mis en cache par hash de texte.
Déterministe à embeddings fixés : seuil explicite, composantes connexes, sortie triée.
"""
from __future__ import annotations

import hashlib
import json

import networkx as nx
import numpy as np

from observer.core import llm
from observer.core.models import Cluster, ContentItem, Evidence
from observer.core.settings import settings

CACHE = "observer:emb:"


def embed(texts: list[str]) -> np.ndarray:
    texts = [t.strip() or "(empty)" for t in texts]  # l’API refuse les chaînes vides
    r = llm._r()
    keys = [CACHE + hashlib.sha1(t.encode()).hexdigest() for t in texts]
    cached = r.mget(keys) if keys else []
    missing = [i for i, c in enumerate(cached) if c is None]
    if missing:
        llm.guard()
        if llm.remaining() <= 0:
            raise llm.BudgetExceeded("Plafond LLM atteint")
        model = settings().model_embed
        for start in range(0, len(missing), 256):
            chunk = missing[start:start + 256]
            resp = llm.openai_client().embeddings.create(model=model, input=[texts[i] for i in chunk])
            u = resp.usage
            credits = (u.model_extra or {}).get("credits_charged") if getattr(u, "model_extra", None) else None
            llm._charge(model, u.prompt_tokens, 0, credits, "embed")
            pipe = r.pipeline()
            for i, d in zip(chunk, resp.data):
                cached[i] = json.dumps(d.embedding)
                pipe.set(keys[i], cached[i], ex=7 * 86400)
            pipe.execute()
    m = np.array([json.loads(c) for c in cached], dtype=np.float32)
    return m / np.linalg.norm(m, axis=1, keepdims=True)


def semantic_clusters(items: list[ContentItem], threshold: float = 0.82, min_authors: int = 2,
                      min_chars: int = 25) -> list[Cluster]:
    eligible = sorted([i for i in items if len(i.full_text()) >= min_chars], key=lambda x: x.uid)
    if len(eligible) < 2:
        return []
    vecs = embed([i.full_text()[:2000] for i in eligible])
    sims = vecs @ vecs.T
    g = nx.Graph()
    idx = np.argwhere(np.triu(sims, k=1) >= threshold)
    for a, b in idx:
        g.add_edge(int(a), int(b), sim=float(sims[a, b]))
    out = []
    for comp in nx.connected_components(g):
        its = [eligible[k] for k in sorted(comp)]
        authors = sorted({i.author_pseudo for i in its})
        if len(authors) < min_authors:
            continue
        uids = [i.uid for i in its]
        cid = "sem-" + hashlib.sha1("|".join(uids).encode()).hexdigest()[:10]
        sub = g.subgraph(comp)
        ev = [Evidence(id=f"{cid}-pair-{n}", kind="semantic_similarity",
                       item_uids=[eligible[a].uid, eligible[b].uid], score=round(d["sim"], 3))
              for n, (a, b, d) in enumerate(sorted(sub.edges(data=True), key=lambda e: -e[2]["sim"])[:20])]
        ts = sorted(i.ts for i in its)
        out.append(Cluster(id=cid, kind="semantic", item_uids=uids, platforms=sorted({i.platform for i in its}),
                           authors=authors, first_ts=ts[0], last_ts=ts[-1], evidence=ev))
    return sorted(out, key=lambda c: (-len(c.authors), c.id))
