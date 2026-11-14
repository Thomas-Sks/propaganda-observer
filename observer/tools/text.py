"""Outils déterministes sur le texte : normalisation, copypasta (MinHash LSH + vérification RapidFuzz).

Déterminisme : graine MinHash fixe, seuils explicites, sortie triée. Chaque cluster porte ses preuves.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

import networkx as nx
from datasketch import MinHash, MinHashLSH
from rapidfuzz import fuzz

from observer.core.models import Cluster, ContentItem, Evidence

SEED = 1
NUM_PERM = 128
SHINGLE = 3  # shingles de mots

_URL = re.compile(r"https?://\S+")
_MENTION = re.compile(r"[@#]\w+")
_NONWORD = re.compile(r"[^\w\s]")


def normalize(text: str) -> str:
    """Minuscules, sans accents, sans URL ni mentions/hashtags, ponctuation retirée."""
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = _URL.sub(" ", t)
    t = _MENTION.sub(" ", t)
    t = _NONWORD.sub(" ", t)
    return " ".join(t.split())


def shingles(words: list[str], k: int = SHINGLE) -> set[str]:
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


def minhash(text: str) -> MinHash:
    m = MinHash(num_perm=NUM_PERM, seed=SEED)
    for s in shingles(normalize(text).split()):
        m.update(s.encode())
    return m


def find_copypasta(items: list[ContentItem], threshold: float = 0.6, min_words: int = 8,
                   min_authors: int = 3, verify_ratio: float = 80.0) -> list[Cluster]:
    """Regroupe les contenus quasi identiques (texte + transcription + OCR) publiés par ≥ min_authors comptes.

    1. Candidats : MinHash LSH à Jaccard ≥ threshold sur shingles de 3 mots.
    2. Vérification : RapidFuzz token_set_ratio ≥ verify_ratio (élimine les faux candidats LSH).
    3. Clusters = composantes connexes ; on garde celles qui ont ≥ min_authors auteurs distincts.
    """
    texts = {i.uid: normalize(i.full_text()) for i in items}
    eligible = [i for i in items if len(texts[i.uid].split()) >= min_words]
    by_uid = {i.uid: i for i in eligible}

    lsh = MinHashLSH(threshold=threshold, num_perm=NUM_PERM)
    hashes: dict[str, MinHash] = {}
    for it in sorted(eligible, key=lambda x: x.uid):
        m = minhash(it.full_text())
        hashes[it.uid] = m
        lsh.insert(it.uid, m)

    g = nx.Graph()
    pair_scores: dict[tuple[str, str], tuple[float, float]] = {}
    for uid, m in hashes.items():
        for other in lsh.query(m):
            if other <= uid:
                continue
            jac = m.jaccard(hashes[other])
            ratio = fuzz.token_set_ratio(texts[uid], texts[other])
            if jac >= threshold and ratio >= verify_ratio:
                g.add_edge(uid, other)
                pair_scores[(uid, other)] = (jac, ratio)

    out: list[Cluster] = []
    for comp in nx.connected_components(g):
        members = sorted(comp)
        its = [by_uid[u] for u in members]
        authors = sorted({i.author_pseudo for i in its})
        if len(authors) < min_authors:
            continue
        cid = "cp-" + hashlib.sha1("|".join(members).encode()).hexdigest()[:10]
        pairs = [(a, b, *pair_scores[(a, b)]) for (a, b) in pair_scores if a in comp]
        evidence = [Evidence(id=f"{cid}-pair-{n}", kind="near_duplicate_text", item_uids=[a, b],
                             score=round(jac, 3), detail={"jaccard": round(jac, 3), "fuzz_ratio": ratio})
                    for n, (a, b, jac, ratio) in enumerate(sorted(pairs))]
        ts = sorted(i.ts for i in its)
        out.append(Cluster(id=cid, kind="copypasta", item_uids=members,
                           platforms=sorted({i.platform for i in its}), authors=authors,
                           first_ts=ts[0], last_ts=ts[-1], evidence=evidence))
    return sorted(out, key=lambda c: (-len(c.authors), c.id))
