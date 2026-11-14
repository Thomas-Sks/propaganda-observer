"""Pertinence d'un élément pour l'événement observé — générique, sans réglage par événement.

Trois zones, sur un score sémantique combiné (récit surveillé + mots-clés) :
  - < LOW  : clairement hors sujet → écarté ;
  - ≥ HIGH, ou mot-clé multi-mots présent tel quel → gardé ;
  - entre les deux (zone grise) → un petit LLM tranche par lots au regard du récit surveillé (mis en cache).
Le score stocké est dans [0, 1] ; THRESHOLD sépare gardé / écarté pour tout le reste du code.
"""
from __future__ import annotations

import hashlib
import json

from observer.core.models import ContentItem
from observer.tools.semantic import embed
from observer.tools.text import normalize

THRESHOLD = 0.5   # score final : ≥ 0.5 = pertinent
LOW, HIGH = 0.30, 0.52


def threshold(cfg: dict | None) -> float:
    return float((cfg or {}).get("relevance_threshold", THRESHOLD))


def lexical_terms(cfg: dict) -> list[list[str]]:
    """Seuls les mots-clés d'au moins 2 mots significatifs comptent (un hashtag générique comme #Ukraine ne suffit pas)."""
    terms = [[w for w in normalize(k).split() if len(w) >= 4] for k in cfg.get("keywords", [])]
    return [t for t in terms if len(t) >= 2]


JUDGE = """You decide whether social posts/articles are ABOUT a monitored narrative (they discuss, repeat, report on,
or debunk it). Posts about the same country or war but a different topic are NOT about it.
Return ONLY a JSON list of booleans, one per item, in order. Example: [true,false,true]"""


def _judge(items: list[ContentItem], narrative: str) -> list[bool]:
    from observer.core import llm
    from observer.core.settings import settings
    r = llm._r()
    out: list[bool | None] = []
    keys = ["observer:rel:" + hashlib.sha1((narrative + i.uid).encode()).hexdigest() for i in items]
    for k in keys:
        v = r.get(k)
        out.append(None if v is None else v == "1")
    todo = [n for n, v in enumerate(out) if v is None]
    for start in range(0, len(todo), 25):
        chunk = todo[start:start + 25]
        body = "\n".join(f"{n + 1}. [{items[i].platform}] {items[i].full_text()[:300]!r}" for n, i in enumerate(chunk))
        try:
            txt = llm.complete(model=settings().model_triage, system=JUDGE, max_tokens=2500, purpose="relevance",
                               user=f"Monitored narrative: {narrative}\n\nItems:\n{body}")
            res = json.loads(txt[txt.find("["): txt.rfind("]") + 1])
        except Exception:
            res = [None] * len(chunk)  # en cas d'échec : on laisse décider le score sémantique
        for i, v in zip(chunk, res + [None] * (len(chunk) - len(res))):
            if isinstance(v, bool):
                out[i] = v
                r.set(keys[i], "1" if v else "0", ex=30 * 86400)
    return [bool(v) if v is not None else None for v in out]  # type: ignore[misc]


def score(items: list[ContentItem], cfg: dict) -> list[float]:
    if not items:
        return []
    narrative = cfg.get("description") or cfg.get("label", "")
    D = embed([narrative])[0]
    K = embed([cfg.get("label", "")] + list(cfg.get("keywords", [])))
    X = embed([i.full_text()[:1500] for i in items])
    sem = 0.5 * (X @ D) + 0.5 * (X @ K.T).max(axis=1)
    terms = lexical_terms(cfg)
    scores: list[float] = []
    gray: list[int] = []
    for n, (it, s) in enumerate(zip(items, sem)):
        words = set(normalize(it.full_text()).split())
        if any(all(w in words for w in t) for t in terms) or s >= HIGH:
            scores.append(round(max(float(s), THRESHOLD + 0.01) if s < HIGH else float(s), 3))
        elif s < LOW:
            scores.append(round(float(s), 3))
        else:
            scores.append(round(float(s), 3))
            gray.append(n)
    if gray:
        verdicts = _judge([items[n] for n in gray], narrative)
        for n, v in zip(gray, verdicts):
            if v is True:
                scores[n] = round(max(scores[n], THRESHOLD + 0.01), 3)
            elif v is False:
                scores[n] = round(min(scores[n], THRESHOLD - 0.01), 3)
            else:  # pas de verdict : on garde seulement le haut de la zone grise
                scores[n] = scores[n] if scores[n] >= 0.42 else round(min(scores[n], THRESHOLD - 0.01), 3)
            if v is None and scores[n] >= 0.42:
                scores[n] = round(max(scores[n], THRESHOLD + 0.01), 3)
    return scores
