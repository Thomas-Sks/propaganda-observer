"""Enquête multi-agents sur un narratif : Enquêteur ⇄ Sceptique → Juge.

Les agents ne voient QUE le dossier de preuves construit de façon déterministe (publications P#, comptes A#,
signaux S#). Chaque affirmation doit citer ses preuves ; le Juge rend un JSON strict, et toute référence
inexistante est retirée (puis signalée). Résultat mis en cache (Redis) : relancer ne coûte rien.
"""
from __future__ import annotations

import hashlib
import json
import re

from observer.core import llm
from observer.core.settings import settings

# Techniques DISARM (cadre ouvert, red framework) autorisées : liste fermée pour éviter les identifiants inventés.
DISARM = {
    "T0022": "Leverage Conspiracy Theory Narratives",
    "T0023": "Distort Facts",
    "T0049": "Flooding the Information Space",
    "T0087": "Develop Video-Based Content",
    "T0088": "Develop Image-Based Content",
    "T0118": "Amplify Existing Narrative",
}

INVESTIGATOR = """You are the INVESTIGATOR in a disinformation analysis team. You receive an evidence pack about one
narrative (publications P#, accounts A#, detection signals S#) and the documented false claim being monitored.
Build the strongest evidence-based case that this narrative is part of a coordinated or inauthentic amplification
effort. Every claim MUST cite evidence ids in brackets, e.g. [P2][A1][S3]. Never invent facts beyond the pack.
Return 3-6 bullet points, each one line, nothing else."""

SKEPTIC = """You are the SKEPTIC in a disinformation analysis team. You receive the same evidence pack and the
investigator's case. Your job is to find ORGANIC explanations: real news event, wire copy reused by many outlets,
genuine fact-checkers, coincidence, low reach, normal fandom. Test each investigator point against the evidence.
Every claim MUST cite evidence ids in brackets. Return 3-6 bullet points, each one line, nothing else."""

JUDGE = """You are the JUDGE. Weigh the investigator's and the skeptic's points against the evidence pack only.
Return ONLY JSON:
{"verdict": "coordinated" | "suspicious" | "organic" | "insufficient_evidence",
 "confidence": "low" | "medium" | "high",
 "summary": "<2 sentences, plain English, cite evidence ids in brackets>",
 "disarm": ["<technique ids from the allowed list, only if clearly supported>"],
 "key_evidence": ["<evidence ids>"],
 "organic_hypotheses_tested": ["<short phrases>"]}
Allowed DISARM techniques: """ + ", ".join(f"{k} {v}" for k, v in DISARM.items())

_REF = re.compile(r"\[([PAS]\d+)\]")


def evidence_pack(story: dict, narrative: str) -> tuple[str, set[str]]:
    """Dossier déterministe à partir de la vue `stories/{id}` (observer/api/views.py)."""
    ids: set[str] = set()
    lines = [f"Documented false claim under watch: {narrative}", f"Narrative title: {story['title']}",
             f"Platforms: {', '.join(story['platforms'])}; first seen {story['first_ts']}; last seen {story['last_ts']}"]
    lines.append("\nSignals:")
    for k, s in enumerate(story["signals"], 1):
        ids.add(f"S{k}")
        lines.append(f"[S{k}] {s['explanation']} (weight {s['weight']})")
    acc_ix = {}
    lines.append("\nAccounts:")
    for k, a in enumerate(story["accounts_detail"], 1):
        ids.add(f"A{k}")
        acc_ix[a["id"]] = f"A{k}"
        flags = "; ".join(f"{f['label']}: {f['detail']}" for f in a["flags"]) or "no risk flag"
        lines.append(f"[A{k}] {a['label']} on {a['platform']} — {a['items']} posts in this event, followers "
                     f"{a['followers']}, created {a['created_at'] or 'unknown'}; {flags}")
    lines.append("\nPublications:")
    for k, p in enumerate(story["publications"][:25], 1):
        ids.add(f"P{k}")
        sim = f", meaning similarity to P1 {p['similarity']}" if p.get("similarity") is not None else ""
        lines.append(f"[P{k}] {p['ts'][:16]} {p['platform']}/{p.get('format', '')} by {acc_ix.get(p['account_id'], '?')}"
                     f"{sim}: {p['text'][:350]}")
    return "\n".join(lines), ids


def _bullets(txt: str) -> list[str]:
    out = [re.sub(r"^\s*[-*•\d.)]+\s*", "", l).replace("**", "").strip() for l in txt.splitlines()]
    return [l for l in out if len(l) > 8][:6]


def _check(points: list[str], ids: set[str]) -> list[dict]:
    """Garde-fou : chaque point garde ses références valides ; les références inventées sont signalées."""
    res = []
    for p in points:
        refs = _REF.findall(p)
        res.append({"text": p, "refs": [r for r in refs if r in ids], "invalid_refs": [r for r in refs if r not in ids]})
    return res


def cached(story: dict, narrative: str) -> dict | None:
    """Enquête déjà faite pour ce narratif (même dossier de preuves), sans aucun appel LLM."""
    pack, _ = evidence_pack(story, narrative)
    hit = llm._r().get("observer:investigation:" + hashlib.sha1(pack.encode()).hexdigest())
    return json.loads(hit) if hit else None


def investigate(story: dict, narrative: str, force: bool = False) -> dict:
    pack, ids = evidence_pack(story, narrative)
    key = "observer:investigation:" + hashlib.sha1(pack.encode()).hexdigest()
    r = llm._r()
    if not force and (hit := r.get(key)):
        return json.loads(hit)
    model = settings().model_investigator
    before = llm.spent()
    inv = llm.complete(model=model, system=INVESTIGATOR, user=pack, max_tokens=3000, purpose="investigator")
    sk = llm.complete(model=model, system=SKEPTIC, max_tokens=3000, purpose="skeptic",
                      user=f"{pack}\n\nInvestigator's case:\n{inv}")
    jd = llm.complete(model=settings().model_judge, system=JUDGE, max_tokens=3000, purpose="judge",
                      user=f"{pack}\n\nInvestigator:\n{inv}\n\nSkeptic:\n{sk}")
    start = jd.find("{")
    try:
        verdict = json.JSONDecoder().raw_decode(jd[start:])[0] if start >= 0 else {}
    except ValueError:
        verdict = {}
    verdict["disarm"] = [{"id": t, "name": DISARM[t]} for t in verdict.get("disarm", []) if t in DISARM]
    verdict["key_evidence"] = [e for e in verdict.get("key_evidence", []) if e in ids]
    out = {
        "investigator": _check(_bullets(inv), ids),
        "skeptic": _check(_bullets(sk), ids),
        "judge": verdict,
        "evidence_ids": sorted(ids),
        "cost_usd": round(llm.spent() - before, 4),
        "models": {"investigator": model, "skeptic": model, "judge": settings().model_judge},
    }
    r.set(key, json.dumps(out), ex=7 * 86400)
    return out
