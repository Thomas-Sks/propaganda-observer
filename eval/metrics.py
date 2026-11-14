"""Métriques d'évaluation binaires : confusion, précision, rappel, FPR, F1, intervalles de Wilson 95 %.

Aucune dépendance lourde : utilisable dans les tests et par eval/run.py.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """Intervalle de Wilson pour une proportion k/n (None si n = 0)."""
    if n <= 0:
        return None
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def confusion(y_true: Sequence[int | bool], y_pred: Sequence[int | bool]) -> dict[str, int]:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true et y_pred de longueurs différentes")
    tp = fp = tn = fn = 0
    for t, p in zip(y_true, y_pred):
        if t and p:
            tp += 1
        elif p:
            fp += 1
        elif t:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def _ratio(a: int, b: int) -> float | None:
    return a / b if b else None


def _round(x: float | None, d: int = 4) -> float | None:
    return None if x is None else round(x, d)


def summarize(cm: dict[str, int]) -> dict:
    """Précision, rappel, FPR, F1 + IC de Wilson (précision, rappel, FPR) à partir d'une matrice de confusion."""
    tp, fp, tn, fn = cm["tp"], cm["fp"], cm["tn"], cm["fn"]
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    fpr = _ratio(fp, fp + tn)
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else (0.0 if precision is not None
                                                                                       and recall is not None else None)
    ci = lambda k, n: [round(v, 4) for v in wilson(k, n)] if n else None  # noqa: E731
    return {
        "confusion": dict(cm),
        "n": tp + fp + tn + fn, "positives": tp + fn, "negatives": fp + tn,
        "precision": _round(precision), "precision_ci": ci(tp, tp + fp),
        "recall": _round(recall), "recall_ci": ci(tp, tp + fn),
        "fpr": _round(fpr), "fpr_ci": ci(fp, fp + tn),
        "f1": _round(f1),
    }


def evaluate(y_true: Sequence[int | bool], y_pred: Sequence[int | bool]) -> dict:
    return summarize(confusion(y_true, y_pred))
