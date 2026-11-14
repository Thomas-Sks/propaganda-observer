"""Onglet Reliability : expose les mesures de fiabilité produites hors ligne par eval/run.py.

Lecture seule d'un fichier JSON figé (data/eval/results.json) : aucun calcul ni appel externe à la requête.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

RESULTS = Path(__file__).resolve().parents[2] / "data" / "eval" / "results.json"

router = APIRouter(prefix="/api", tags=["reliability"])


@router.get("/reliability")
def reliability() -> dict:
    if not RESULTS.exists():
        raise HTTPException(404, "No evaluation results yet: run `uv run python -m eval.run`")
    return json.loads(RESULTS.read_text())
