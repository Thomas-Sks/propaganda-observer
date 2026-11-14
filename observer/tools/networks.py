"""Registre des réseaux d'influence de référence (`data/registry/reference_networks.yaml`), générique."""
from __future__ import annotations

from functools import lru_cache

import yaml

from observer.core.settings import ROOT

PATH = ROOT / "data" / "registry" / "reference_networks.yaml"


@lru_cache
def networks() -> list[dict]:
    return yaml.safe_load(PATH.read_text()) or [] if PATH.exists() else []
