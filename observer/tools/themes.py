"""Thèmes : regroupe TOUTES les publications pertinentes d'un événement en une dizaine de thèmes, puis montre
qui pousse quoi (type de source, langue, plateforme, position) et comment chaque thème évolue dans le temps.

- Embeddings multilingues déjà calculés pour les narratifs (cache Redis) → un même thème réunit les langues.
- KMeans (graine fixe), nombre de thèmes choisi par silhouette (cosinus) entre K_MIN et K_MAX.
- Nommage : UN appel LLM peu coûteux pour tous les thèmes, à partir des publications les plus centrales ;
  mis en cache tant que la composition des thèmes ne change pas. Sans budget LLM, nom = mots les plus fréquents.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict

import numpy as np

from observer.core.models import Cluster, ContentItem
from observer.tools.text import normalize

K_MIN, K_MAX, MIN_CHARS = 6, 12, 25
SOURCE_TYPES = ("listed", "automated", "media", "social")

_STOP = {
    "fr": "le la les des une est pour dans que qui sur pas avec ce sont aux du au par".split(),
    "en": "the and is are for with that this from was have has not they will".split(),
    "de": "der die das und ist nicht mit sich auf für ein eine den von zu".split(),
    "it": "il che di la per non sono una con del della gli le si".split(),
    "es": "el los las del que por una con para es se lo como más".split(),
    "pl": "się nie jest na że do to w z i jak ale przez".split(),
}


def guess_lang(it: ContentItem) -> str:
    """Langue déclarée par la plateforme, sinon devinette par mots-outils (suffisant pour une agrégation)."""
    if it.lang and it.lang[:2] not in ("un", "?"):
        return it.lang[:2]
    t = (it.text or "")[:600]
    if sum(1 for ch in t if "Ѐ" <= ch <= "ӿ") > len(t) * 0.3:
        return "ru"
    words = re.findall(r"\w+", t.lower())
    scores = {l: sum(w in set(s) for w in words) for l, s in _STOP.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else "?"


def _keywords(texts: list[str], k: int = 6) -> list[str]:
    stop = {w for s in _STOP.values() for w in s} | {"link", "https", "http", "www", "com", "les", "des", "plus"}
    c = Counter(w for t in texts for w in normalize(t).split() if len(w) > 3 and w not in stop and not w.isdigit())
    return [w for w, _ in c.most_common(k)]


def cluster(items: list[ContentItem]) -> tuple[list[ContentItem], np.ndarray, np.ndarray]:
    """(items retenus, étiquette de thème par item, centroïdes). Déterministe."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    from observer.tools.semantic import embed
    elig = sorted([i for i in items if len(i.full_text()) >= MIN_CHARS], key=lambda x: x.uid)
    if len(elig) < K_MIN * 3:
        return elig, np.zeros(len(elig), dtype=int), np.zeros((1, 1))
    X = embed([i.full_text()[:2000] for i in elig])
    X = X / np.maximum(1e-9, np.linalg.norm(X, axis=1, keepdims=True))
    rng = np.random.default_rng(0)
    sample = rng.choice(len(X), size=min(1500, len(X)), replace=False)
    best = None
    for k in range(K_MIN, min(K_MAX, len(elig) // 10) + 1):
        km = KMeans(n_clusters=k, random_state=0, n_init=4).fit(X)
        s = silhouette_score(X[sample], km.labels_[sample], metric="cosine")
        if best is None or s > best[0]:
            best = (s, km)
    km = best[1]
    return elig, km.labels_, km.cluster_centers_


def name_themes(samples: dict[int, list[str]]) -> dict[int, dict]:
    """Un seul appel LLM pour nommer tous les thèmes (nom court + cadrage en une phrase)."""
    from observer.core import llm
    from observer.core.settings import settings
    key = "observer:themes:" + hashlib.sha1(json.dumps(samples, sort_keys=True).encode()).hexdigest()
    r = llm._r()
    if (hit := r.get(key)):
        return {int(k): v for k, v in json.loads(hit).items()}
    body = "\n\n".join(f"THEME {k}:\n" + "\n".join(f"- {t[:220]}" for t in ts) for k, ts in samples.items())
    system = ("You label topic clusters of social posts and articles about one event. For each THEME return a short "
              "English name (2-5 words, specific, no quotes) and the dominant FRAMING in one neutral sentence "
              "(how the posts present the topic). Return ONLY JSON: {\"<id>\": {\"name\": \"...\", \"framing\": \"...\"}}.")
    try:
        out = llm.complete(model=settings().model_triage, system=system, user=body, max_tokens=3000, purpose="themes")
        res = json.JSONDecoder().raw_decode(out[out.find("{"):])[0]
        res = {int(k): v for k, v in res.items() if isinstance(v, dict) and v.get("name")}
    except Exception:
        return {}
    r.set(key, json.dumps(res), ex=14 * 86400)
    return res


def build(items: list[ContentItem], clusters: list[Cluster], source_type: dict[str, str],
          stance_of_item: dict[str, str], label_of: dict[str, str]) -> dict:
    elig, labels, centers = cluster(items)
    if not elig:
        return {"themes": [], "days": [], "method": []}
    by_theme: dict[int, list[int]] = defaultdict(list)
    for idx, t in enumerate(labels):
        by_theme[int(t)].append(idx)
    from observer.tools.semantic import embed
    X = embed([i.full_text()[:2000] for i in elig])
    X = X / np.maximum(1e-9, np.linalg.norm(X, axis=1, keepdims=True))
    samples, central = {}, {}
    for t, idxs in by_theme.items():
        c = centers[t] / max(1e-9, np.linalg.norm(centers[t]))
        order = sorted(idxs, key=lambda i: -float(X[i] @ c))
        central[t] = order
        seen, pick = set(), []
        for i in order:  # échantillon central, sans doublons de texte
            k = normalize(elig[i].text or "")[:60]
            if k not in seen:
                seen.add(k)
                pick.append(" ".join((elig[i].full_text()).split()))
            if len(pick) >= 8:
                break
        samples[t] = pick
    names = name_themes(samples)
    uid_theme = {elig[i].uid: int(t) for i, t in enumerate(labels)}
    narr_theme = {}
    for c in clusters:
        ts = Counter(uid_theme[u] for u in c.item_uids if u in uid_theme)
        if ts:
            narr_theme[c.id] = ts.most_common(1)[0][0]
    days = sorted({i.ts.date().isoformat() for i in elig})
    themes = []
    for t, idxs in sorted(by_theme.items(), key=lambda kv: -len(kv[1])):
        its = [elig[i] for i in idxs]
        per_day = Counter(i.ts.date().isoformat() for i in its)
        acc = Counter(i.author_pseudo for i in its)
        nm = names.get(t, {})
        themes.append({
            "id": t, "name": nm.get("name") or " · ".join(_keywords([i.full_text() for i in its], 3)),
            "framing": nm.get("framing") or "", "keywords": _keywords([i.full_text() for i in its]),
            "items": len(its), "accounts": len(acc),
            "platforms": dict(Counter(i.platform for i in its)),
            "langs": dict(Counter(guess_lang(i) for i in its)),
            "sources": dict(Counter(source_type.get(i.author_pseudo, "social") for i in its)),
            "stance": dict(Counter(stance_of_item.get(i.uid, "unclassified") for i in its)),
            "series": [per_day.get(d, 0) for d in days],
            "narratives": sorted(cid for cid, th in narr_theme.items() if th == t),
            "top_accounts": [{"id": a, "label": label_of.get(a, a[:8]), "posts": n,
                              "source": source_type.get(a, "social")} for a, n in acc.most_common(8)],
            "examples": [{"uid": elig[i].uid, "platform": elig[i].platform, "url": elig[i].url,
                          "ts": elig[i].ts.isoformat(), "text": " ".join(elig[i].full_text().split())[:280]}
                         for i in central[t][:5]],
        })
    return {
        "themes": themes, "days": days, "k": len(themes), "n_items": len(elig),
        "method": [
            f"All {len(elig)} relevant posts are embedded with a multilingual model, so one theme gathers every language.",
            f"KMeans (fixed seed); the number of themes ({len(themes)}) is the one with the best cosine silhouette between {K_MIN} and {K_MAX}.",
            "Names and framings are written by an LLM from the most central posts of each theme (one call, cached).",
            "Source type: listed = documented network or state media; automated = bot-like volume or declared bot; media = news site; social = other accounts.",
        ],
    }
