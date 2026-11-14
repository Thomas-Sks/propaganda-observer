"""Référentiel de sources listées, chargé depuis `data/registry/listed_sources.yaml` (multi-pays, sourcé).

Utilisé comme SIGNAL (« cite ou relaie une source listée »), jamais comme verdict à lui seul. Pour étendre le
référentiel à un nouveau pays ou réseau, on ajoute des lignes au fichier : aucun code spécifique à un événement.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from observer.collectors.gnews import registrable
from observer.core.settings import ROOT

REGISTRY = ROOT / "data" / "registry" / "listed_sources.yaml"


@lru_cache
def listed() -> dict[str, dict]:
    if not Path(REGISTRY).exists():
        return {}
    return {e["domain"]: e for e in yaml.safe_load(REGISTRY.read_text()) or []}


def entry_for(url_or_domain: str) -> dict | None:
    d = registrable(url_or_domain) if ("/" in url_or_domain or "." in url_or_domain) else url_or_domain
    reg = listed()
    if d in reg:
        return reg[d]
    host = url_or_domain.split("//")[-1].split("/")[0].lower()
    for k, v in reg.items():  # sous-domaines (ex. francais.news-pravda.com), sans faux suffixes (techdirt ≠ rt.com)
        if host == k or host.endswith("." + k) or d.endswith("." + k):
            return v
    return None


def label_for(url_or_domain: str) -> str | None:
    e = entry_for(url_or_domain)
    return e["label"] if e else None


LISTED = {k: v["label"] for k, v in listed().items()}  # compatibilité
