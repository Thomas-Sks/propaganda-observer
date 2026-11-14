"""Détection de pics d'activité : z-score robuste (médiane / MAD) sur des comptes par période. Déterministe."""
from __future__ import annotations

import statistics


def robust_peaks(series: list[tuple[str, int]], z_min: float = 3.0, min_count: int = 5) -> list[dict]:
    """Renvoie les périodes dont le volume dépasse médiane + z_min × MAD normalisée (et au moins `min_count`)."""
    vals = [v for _, v in series]
    if len(vals) < 3:
        return []
    med = statistics.median(vals)
    mad = statistics.median([abs(v - med) for v in vals]) * 1.4826 or 1.0
    out = []
    for key, v in series:
        z = (v - med) / mad
        if z >= z_min and v >= min_count:
            out.append({"period": key, "count": v, "z": round(z, 1), "baseline": med,
                        "explanation": f"{v} publications vs a typical {med:g} (robust z = {z:.1f})"})
    return out
