"""API « pour Hostinger » : GET /v1/provenance?target=<url|domaine|compte> → score, features, preuves, version.

Cas d'usage : l'équipe abus d'un hébergeur vérifie si un site hébergé appartient à un réseau de propagande connu.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from observer.tools.provenance import DEFAULT_EVENT, provenance_score

router = APIRouter(prefix="/v1", tags=["provenance"])


@router.get("/provenance")
async def provenance(target: str = Query(..., min_length=3, max_length=500,
                                         description="URL, domain, or account as <platform>:<id>"),
                     event: str | None = DEFAULT_EVENT, twins: bool = True) -> dict:
    """Score de risque de provenance 0-100 (priorise une vérification, ne condamne pas)."""
    try:
        return await provenance_score(target, event=event, twins=twins)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
