"""Position d'une histoire vis-à-vis du récit documenté de l'événement : le reprend, le dément, ou neutre.

Jugement LLM (modèle peu coûteux), toujours accompagné d'une citation exacte tirée des contenus ; mis en cache.
Utilisé comme signal explicite et étiqueté « LLM-assessed », jamais comme verdict à lui seul.
"""
from __future__ import annotations

import hashlib
import json

from observer.core import llm
from observer.core.models import Cluster, ContentItem
from observer.core.settings import settings

SYSTEM = """You assess the STANCE of a group of social posts/articles toward a documented false narrative.
Return ONLY JSON: {"stance": "promotes" | "debunks" | "neutral", "quote": "<exact short quote from the items>",
"reason": "<one short English sentence>"}.
promotes = repeats or endorses the false claim as true; debunks = fact-check, refutes or frames it as propaganda;
neutral = reports facts without endorsing (e.g. arrest of the fake medic, official statements)."""


def assess(c: Cluster, items: dict[str, ContentItem], narrative: str) -> dict | None:
    its = [items[u] for u in c.item_uids if u in items][:6]
    if not its or not narrative:
        return None
    key = "observer:stance:" + hashlib.sha1((narrative + "|".join(sorted(c.item_uids))).encode()).hexdigest()
    r = llm._r()
    if (hit := r.get(key)):
        return json.loads(hit)
    body = "\n---\n".join(f"[{i.platform}] {i.full_text()[:500]}" for i in its)
    out = llm.complete(model=settings().model_triage, system=SYSTEM, max_tokens=3000, purpose="stance",
                       user=f"Documented false narrative:\n{narrative}\n\nItems:\n{body}")
    start = out.find("{")
    try:
        res = json.JSONDecoder().raw_decode(out[start:])[0] if start >= 0 else None
    except ValueError:
        res = None
    if res and res.get("stance") in ("promotes", "debunks", "neutral"):
        r.set(key, json.dumps(res), ex=7 * 86400)
        return res
    return None
