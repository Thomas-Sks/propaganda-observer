"""Évalue chaque détecteur sur des données étiquetées et écrit data/eval/results.json (onglet Reliability).

Usage : uv run python -m eval.fetch && uv run python -m eval.run

Règle d'or (SPECS §8) : tout ce qui est réglé (seuils, paramètres) l'est sur un jeu d'entraînement ;
les chiffres publiés viennent d'un jeu jamais vu pendant le réglage. Aucun appel LLM ni Apify.
"""
from __future__ import annotations

import asyncio
import csv
import json
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from eval import coordination
from eval.fetch import RAW, SAMPLE, SOURCES
from eval.metrics import evaluate
from observer.tools.reputation import LISTED, label_for

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "eval" / "results.json"
SEED = 42
FPR_TARGET = 0.02  # cible SPECS §8 : FPR ≤ 2 % au seuil retenu
EVENT = "azov-torture-chambers-nov-2026"
VERSION = "reliability-v1"


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def auc_ci(y: np.ndarray, s: np.ndarray, n_boot: int = 1000) -> dict:
    """AUC + IC 95 % par bootstrap (1 000 rééchantillonnages, graine fixe)."""
    rng = np.random.default_rng(SEED)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if y[idx].min() != y[idx].max():
            vals.append(roc_auc_score(y[idx], s[idx]))
    return {"auc": round(float(roc_auc_score(y, s)), 4),
            "auc_ci": [round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)]}


# ---------------------------------------------------------------- a. Score de compte (Cresci-2017)

def account_features(df: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    age = (pd.to_datetime(df.observed_at) - pd.to_datetime(df.created_at)).dt.total_seconds() / 86400
    f["age_days"] = age.clip(lower=1)
    f["followers"] = df.followers_count
    f["following"] = df.friends_count
    f["ratio"] = df.followers_count / df.friends_count.clip(lower=1)
    f["per_day"] = df.statuses_count / f.age_days
    f["default_avatar"] = df.default_profile_image
    f["no_bio"] = 1 - df.has_description
    f["favourites"] = df.favourites_count
    f["listed"] = df.listed_count
    return f


def rule_hits(f: pd.Series, p: dict) -> list[str]:
    """Règles explicables (même esprit que observer/api/views.py::account_flags), une raison lisible par règle."""
    out = []
    if f.age_days < 30:
        out.append(f"new account ({f.age_days:.0f} days)")
    if f.followers < p["low_audience"]:
        out.append(f"low audience ({f.followers:.0f} followers)")
    if f.following >= 100 and f.ratio < p["ratio"]:
        out.append(f"follows many, followed by few ({f.followers:.0f}/{f.following:.0f})")
    if f.per_day > p["per_day"]:
        out.append(f"high cadence ({f.per_day:.0f} posts/day)")
    if f.default_avatar:
        out.append("default avatar")
    if f.no_bio:
        out.append("empty bio")
    if f.favourites < p["no_likes"]:
        out.append(f"almost never likes anything ({f.favourites:.0f} likes)")
    return out


def describe_account(f: pd.Series, group: str) -> str:
    fam = "Human (genuine)" if group == "genuine_accounts" else group.replace("_", " ")
    return (f"{fam} · {f.age_days:.0f} days old · {f.followers:.0f} followers / {f.following:.0f} following"
            f" · {f.per_day:.1f} posts/day · avatar {'default' if f.default_avatar else 'custom'}"
            f" · bio {'empty' if f.no_bio else 'present'}")


def eval_accounts() -> dict:
    df = pd.read_csv(RAW / SAMPLE)
    feats = account_features(df)
    y = df.label.to_numpy()
    tr, te = train_test_split(np.arange(len(df)), test_size=0.5, random_state=SEED, stratify=df.group)

    # Réglage sur TRAIN uniquement : paramètres des règles + nombre minimal de règles déclenchées
    grid = [{"low_audience": la, "ratio": r, "per_day": pd_, "no_likes": nl, "k": k}
            for la in (50, 100) for r in (0.05, 0.1, 0.2) for pd_ in (20, 50, 100) for nl in (1, 5, 20)
            for k in (1, 2, 3)]

    def n_rules(p) -> np.ndarray:
        # Version vectorisée de rule_hits (mêmes règles), pour parcourir la grille rapidement
        f = feats
        hits = [f.age_days < 30, f.followers < p["low_audience"], (f.following >= 100) & (f.ratio < p["ratio"]),
                f.per_day > p["per_day"], f.default_avatar == 1, f.no_bio == 1, f.favourites < p["no_likes"]]
        return np.sum([h.to_numpy() for h in hits], axis=0)

    def predict(idx, p):
        n = n_rules(p)[idx]
        return n, (n >= p["k"]).astype(int)

    best = None
    for p in grid:
        _, pred = predict(tr, p)
        m = evaluate(y[tr], pred)
        key = (m["fpr"] <= FPR_TARGET, m["recall"] if m["fpr"] <= FPR_TARGET else -m["fpr"])
        if best is None or key > best[0]:
            best = (key, p, m)
    _, params, train_m = best
    n_te, pred_te = predict(te, params)
    test_m = evaluate(y[te], pred_te)
    test_m.update(auc_ci(y[te], n_te.astype(float)))

    # Règles de production telles quelles (âge < 30 j OU < 50 abonnés), sans réglage
    prod = np.array([int(feats.iloc[i].age_days < 30 or feats.iloc[i].followers < 50) for i in te])
    prod_m = evaluate(y[te], prod)

    # Référence : régression logistique (features log), seuil choisi sur train pour FPR ≤ 2 %
    X = np.column_stack([np.log1p(feats[c]) for c in ["age_days", "followers", "following", "per_day", "favourites",
                                                       "listed"]] + [np.log(feats.ratio + 1e-3), feats.default_avatar,
                                                                     feats.no_bio])
    lr = LogisticRegression(max_iter=2000).fit(X[tr], y[tr])
    s_tr, s_te = lr.predict_proba(X[tr])[:, 1], lr.predict_proba(X[te])[:, 1]
    thr = float(np.quantile(s_tr[y[tr] == 0], 1 - FPR_TARGET))
    lr_m = evaluate(y[te], (s_te > thr).astype(int))
    lr_m.update(auc_ci(y[te], s_te))

    # Détail par famille de bots (rappel) et humains (FPR) sur TEST
    breakdown = []
    for g, sub in df.iloc[te].groupby("group"):
        pos = [list(te).index(i) for i in sub.index]
        rate = float(pred_te[pos].mean())
        breakdown.append({"label": "Genuine humans" if g == "genuine_accounts" else g.replace("_", " "),
                          "kind": "fpr" if g == "genuine_accounts" else "recall", "n": len(pos), "rate": round(rate, 4)})
    breakdown.sort(key=lambda b: (b["kind"] != "fpr", -b["rate"]))

    rng = random.Random(SEED)
    fps = [i for k, i in enumerate(te) if pred_te[k] and not y[i]]
    fns = [i for k, i in enumerate(te) if not pred_te[k] and y[i]]
    gallery = {
        "false_positives": [{"item": describe_account(feats.iloc[i], df.group[i]),
                             "reason": "Flagged because: " + "; ".join(rule_hits(feats.iloc[i], params))}
                            for i in rng.sample(fps, min(5, len(fps)))],
        "false_negatives": [{"item": describe_account(feats.iloc[i], df.group[i]),
                             "reason": ("Only fired: " + "; ".join(h) if (h := rule_hits(feats.iloc[i], params))
                                        else "No rule fired") + f" — below the {params['k']}-rule threshold"}
                            for i in rng.sample(fns, min(5, len(fns)))],
    }
    rules = (f"new account < 30 days; < {params['low_audience']} followers; follower/following ratio < "
             f"{params['ratio']} (when following ≥ 100); > {params['per_day']} posts/day; default avatar; empty bio; fewer than {params['no_likes']} likes given")
    return {
        "id": "account", "name": "Account risk score",
        "question": "Is this account likely automated or fake?",
        "method": "Seven explainable rules (" + rules + "). Flag when at least "
                  f"{params['k']} rules fire. Rule cut-offs and the minimum count were tuned on the training half "
                  f"only (maximise recall with training FPR ≤ {_pct(FPR_TARGET)}).",
        "threshold": f"≥ {params['k']} of 7 rules",
        "split": "Stratified 50/50 train/test by account family, seed 42. Numbers below are on the test half.",
        "datasets": [{"name": "Cresci-2017 (Bot Repository)", "url": SOURCES["cresci-2017.csv.zip"],
                      "n": int(len(df)), "positives": int(y.sum()), "negatives": int((1 - y).sum()),
                      "note": "Balanced sample: 1,000 genuine accounts, 1,000 bots across 8 families. "
                              "Twitter profiles collected 2014–2016."}],
        "test": test_m, "train": train_m,
        "baselines": [
            {"name": "Logistic regression (9 log features)", "threshold": f"p > {thr:.3f} (train FPR {_pct(FPR_TARGET)})",
             **lr_m},
            {"name": "Production rules as deployed (age < 30 d or < 50 followers)", "threshold": "any rule", **prod_m},
        ],
        "breakdown": breakdown, "breakdown_title": "Recall by bot family (test)",
        "errors": gallery,
        "limits": [
            "Twitter-only data from 2014–2016: Bluesky, Telegram or TikTok accounts may behave differently; "
            "no labelled set exists for them.",
            "The 'new account' rule never fires here: Cresci bots were months or years old when collected. "
            "It is kept because fresh accounts do appear in live swarms (see coordination bench).",
            "The strongest rule here ('almost never likes anything') needs a likes-given count, which X exposes "
            "but Bluesky, Telegram and TikTok do not.",
            "Social spambots that imitate humans are the hardest family: see the breakdown.",
            f"The rules currently deployed (age < 30 days or < 50 followers) flag {_pct(prod_m['fpr'])} of genuine "
            "humans on this test set: they are shown as weak hints in the UI, never as an alert on their own.",
        ],
    }


# ---------------------------------------------------------------- b. Référentiel de sources listées

def eval_domains() -> dict:
    pravda = sorted(set(json.loads((RAW / "pravda_viz.json").read_text())["allDomains"]))
    with (RAW / "iffy.csv").open() as f:
        iffy = sorted({r["Domain"].strip().lower() for r in csv.DictReader(f) if r["Domain"].strip()})
    with (RAW / "lin_domain_pc1.csv").open() as f:
        lin = [(r["domain"].strip().lower(), float(r["pc1"])) for r in csv.DictReader(f)]
    pos = {d: "Pravda network (CheckFirst)" for d in pravda} | {d: "Iffy+ unreliable list" for d in iffy if d not in pravda}
    neg = sorted({d for d, s in lin if s >= 0.8} - set(pos))
    domains = sorted(pos) + neg
    y = [1] * len(pos) + [0] * len(neg)
    y_src = [pos[d] for d in sorted(pos)] + ["Lin et al. pc1 ≥ 0.8"] * len(neg)
    pred = [int(label_for(d) is not None) for d in domains]
    m = evaluate(y, pred)

    breakdown = []
    for src, kind in (("Pravda network (CheckFirst)", "recall"), ("Iffy+ unreliable list", "recall"),
                      ("Lin et al. pc1 ≥ 0.8", "fpr")):
        idx = [k for k, s in enumerate(y_src) if s == src]
        breakdown.append({"label": src, "kind": kind,
                          "n": len(idx), "rate": round(sum(pred[k] for k in idx) / len(idx), 4)})
    lin_score = dict(lin)
    rng = random.Random(SEED)
    fps = [d for d, t, p in zip(domains, y, pred) if p and not t]
    fn_all = [d for d, t, p in zip(domains, y, pred) if t and not p]
    fn_pravda = [d for d in fn_all if pos[d] != "Iffy+ unreliable list"]
    fn_iffy = [d for d in fn_all if pos[d] == "Iffy+ unreliable list"]
    gallery = {
        "false_positives": [{"item": f"{d} (Lin pc1 = {lin_score[d]:.2f})", "reason": f"Listed as: {label_for(d)}"}
                            for d in fps[:5]],
        "false_negatives": [{"item": f"{d} — Pravda network (CheckFirst)", "reason":
                             "Hosting or mirror domain (AMP cache, blogging platform) shared with legitimate sites: "
                             "not a network domain we can list without flagging everyone on it"}
                            for d in fn_pravda[:2]]
                           + [{"item": f"{d} — on the Iffy+ list", "reason":
                               f"Not in our referential of {len(LISTED)} state-media / documented-network domains: "
                               "Iffy+ covers general low-credibility sites, which we do not list"}
                              for d in rng.sample(fn_iffy, min(5 - len(fn_pravda[:2]), len(fn_iffy)))],
    }
    return {
        "id": "domains", "name": "Listed-source referential",
        "question": "Does this link point to state media or a documented influence network?",
        "method": f"Exact match (with sub-domains) against a hand-curated list of {len(LISTED)} domains "
                  "(EU sanctions, VIGINUM, US State Dept, CheckFirst). Nothing was tuned: the list was frozen "
                  "before this test.",
        "threshold": "Exact match on the domain or a parent domain",
        "split": "No training: every domain is held-out.",
        "datasets": [
            {"name": "Pravda network domains (CheckFirst)", "url": SOURCES["pravda_viz.json"], "n": len(pravda),
             "positives": len(pravda), "negatives": 0, "note": "allDomains of the CheckFirst Pravda map"},
            {"name": "Iffy+ (Iffy.news, CC BY 4.0)", "url": SOURCES["iffy.csv"], "n": len(iffy),
             "positives": len(iffy), "negatives": 0, "note": "Low-credibility sites (MBFC/fact-checker based)"},
            {"name": "Lin et al. 2023 domain quality (pc1 ≥ 0.8)", "url": SOURCES["lin_domain_pc1.csv"],
             "n": len(neg), "positives": 0, "negatives": len(neg),
             "note": "High-quality outlets by expert consensus; Iffy overlaps removed"},
        ],
        # Historique : ce que le banc a trouvé et corrigé (mesuré le 14/11/2026 sur les mêmes jeux)
        "changelog": [
            {"version": "v1", "date": "2026-11-14", "status": "fixed in v2",
             "summary": "Suffix-match bug: any domain ending in 'rt.com' was labelled Russian state media. "
                        "4 false positives out of 1,260 trusted domains (FPR 0.3%).",
             "domains": ["everycrsreport.com", "sciencealert.com", "spectrumreport.com", "techdirt.com"]},
            {"version": "v2", "date": "2026-11-14", "status": "current",
             "summary": "Matching restricted to the exact domain or a true sub-domain ('.' + listed domain).",
             "domains": []},
        ],
        "test": m, "breakdown": breakdown, "breakdown_title": "Detection rate by source list",
        "errors": gallery,
        "limits": [
            "Recall on Pravda domains is trivially high: they all share the news-pravda.com parent, which is listed. "
            "It checks the matching code, not discovery.",
            "Recall on Iffy+ is low by design: the referential only names state media and documented networks. "
            "It is one signal among several, never a verdict on its own.",
            "False positives are near zero, which is what a referential is for: when it fires, it is right.",
        ],
    }


# ---------------------------------------------------------------- c. Coordination (banc par injection)

async def _event_items():
    from observer.core import db
    return await db.load_items(EVENT, limit=20000)


def eval_coordination() -> dict:
    items = asyncio.run(_event_items())
    rng = random.Random(coordination.SEED)
    seeds, background = coordination.prepare_texts(items, rng)
    t0, t1 = min(i.ts for i in items), max(i.ts for i in items)
    scenarios = coordination.build(seeds, t0, t1)
    rows = []
    for sc in scenarios:
        alert, level, reasons = coordination.run_scenario(sc, background)
        rows.append((sc, alert, level, reasons))
    y = [int(sc.positive) for sc, *_ in rows]
    pred = [int(a) for _, a, *_ in rows]
    m = evaluate(y, pred)

    breakdown = []
    for kind, label, pos, desc in coordination.TYPES:
        sub = [r for r in rows if r[0].kind == kind]
        breakdown.append({"label": label, "kind": "recall" if pos else "fpr", "n": len(sub), "detail": desc,
                          "rate": round(sum(r[1] for r in sub) / len(sub), 4)})

    def show(sc: coordination.Scenario) -> str:
        first = sc.items[0].text
        return f"{sc.label} · {len(sc.items)} posts · “{first[:110]}{'…' if len(first) > 110 else ''}”"

    r2 = random.Random(SEED)
    fps = [r for r in rows if r[1] and not r[0].positive]
    fns = [r for r in rows if not r[1] and r[0].positive]
    gallery = {
        "false_positives": [{"item": show(sc), "reason": f"Raised to {lvl}: " + "; ".join(rs)}
                            for sc, _, lvl, rs in r2.sample(fps, min(5, len(fps)))],
        "false_negatives": [{"item": show(sc), "reason": "Stayed organic: " + "; ".join(rs)}
                            for sc, _, lvl, rs in r2.sample(fns, min(5, len(fns)))],
    }
    n_items = sum(len(sc.items) for sc in scenarios)
    return {
        "id": "coordination", "name": "Coordination detection",
        "question": "Is this story pushed by a coordinated swarm rather than spreading organically?",
        "method": "Production pipeline unchanged: near-duplicate text (MinHash + RapidFuzz) and shared links "
                  "→ stories → explainable signals (copy burst, link burst, new accounts, cross-platform). "
                  "Alert = level Review or Priority (score ≥ 0.40). Thresholds were fixed before the bench was built.",
        "threshold": "Story score ≥ 0.40 (Review)",
        "split": "No training on this bench. Each scenario is injected into 300 real background posts.",
        "datasets": [{"name": "Injection bench (synthetic swarms + legitimate viral content)", "url": None,
                      "n": len(scenarios), "positives": sum(y), "negatives": len(y) - sum(y),
                      "note": f"{len(scenarios)} scenarios, {n_items} posts, built with seed {coordination.SEED} from "
                              f"{len(seeds)} real texts collected for the event '{EVENT}'."}],
        "test": m, "breakdown": breakdown, "breakdown_title": "Rate by scenario type",
        "errors": gallery,
        "limits": [
            "Synthetic bench: swarms follow scripted patterns. Real operations adapt; recall here is an upper bound.",
            "Precision depends on the mix of swarms and legitimate cases in the bench (5 swarm types, 3 legitimate "
            "types, 30 each); the false-alarm rate on legitimate cases is the number to watch.",
            "Paraphrase and translation swarms are not in this bench (the semantic layer is not evaluated here).",
            "Patient swarms of aged accounts spread over days are designed to evade timing rules: expect misses.",
        ],
    }


def main() -> None:
    detectors = [eval_accounts(), eval_domains(), eval_coordination()]
    out = {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fpr_target": FPR_TARGET,
        "detectors": detectors,
        "known_limits": [
            "Scores rank what to check first; they never prove that an account or a source is malicious.",
            "Account data is Twitter 2014–2016; no labelled dataset exists for Bluesky, Telegram or TikTok accounts.",
            "The coordination bench is synthetic; it measures known patterns, not novel tactics.",
            "AI-generated-text detection and semantic (paraphrase) clustering are not evaluated yet.",
            "Confidence intervals are Wilson 95 %; with zero observed errors the upper bound is still above zero.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    for d in detectors:
        t = d["test"]
        print(f"{d['id']:13s} P={t['precision']} R={t['recall']} FPR={t['fpr']} F1={t['f1']} {t['confusion']}")
        for b in d.get("baselines", []):
            print(f"  ↳ {b['name'][:40]:40s} P={b['precision']} R={b['recall']} FPR={b['fpr']} AUC={b.get('auc')}")
        for b in d["breakdown"]:
            print(f"    {b['label'][:45]:45s} n={b['n']:4d} rate={b['rate']}")
    print("→", OUT)


if __name__ == "__main__":
    main()
