"""Modèle commun ContentItem et objets de détection (SPECS §3.1)."""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from observer.core.settings import settings

Platform = Literal["x", "youtube", "tiktok", "instagram", "facebook", "bluesky", "mastodon", "telegram", "web"]
Level = Literal["organic", "review", "priority", "insufficient_data"]


def _salted(platform: str, handle: str) -> str:
    key = settings().pseudo_salt.encode()
    return hmac.new(key, f"{platform}:{handle.lower()}".encode(), hashlib.sha256).hexdigest()[:16]


def rekey(salted: str) -> str:
    """Seconde couche : HMAC avec la clé secrète PSEUDO_KEY. Elle s'applique aussi aux pseudonymes déjà stockés
    (migration sans les pseudos d'origine), donc un même compte garde le même identifiant avant et après."""
    k = settings().pseudo_key
    return hmac.new(k.encode(), salted.encode(), hashlib.sha256).hexdigest()[:16] if k else salted


def pseudonymize(platform: str, handle: str) -> str:
    """Hash salé puis clé secrète, stable : on ne stocke jamais le pseudo en clair dans les tables d'analyse."""
    return rekey(_salted(platform, handle))


class AccountMeta(BaseModel):
    created_at: datetime | None = None
    created_at_estimated: bool = False  # True si estimé (ex. plus ancienne vidéo TikTok)
    followers: int | None = None
    following: int | None = None
    posts_count: int | None = None
    verified: bool | None = None
    automated_declared: bool | None = None
    default_avatar: bool | None = None
    known_network: str | None = None  # ex. « Pravda feeder (CheckFirst) » : source listée par un référentiel public


class ContentItem(BaseModel):
    platform: Platform
    post_id: str
    url: str | None = None
    ts: datetime
    author_pseudo: str
    text: str = ""
    transcript: str | None = None
    ocr_text: str | None = None
    urls_canon: list[str] = Field(default_factory=list)  # domaines (eTLD+1)
    links: list[str] = Field(default_factory=list)  # URL complètes canonicalisées
    hashtags: list[str] = Field(default_factory=list)
    media_urls: list[str] = Field(default_factory=list)
    lang: str | None = None
    account: AccountMeta = Field(default_factory=AccountMeta)
    metrics: dict[str, int] = Field(default_factory=dict)  # vues, likes, partages…
    event: str | None = None
    relevance: float | None = None  # pertinence pour l’événement (tools/relevance.py)
    format: str | None = None  # post, reel, video, short, article, message

    @property
    def uid(self) -> str:
        return f"{self.platform}:{self.post_id}"

    def full_text(self) -> str:
        """Texte utilisé par les empreintes : post + transcription + OCR."""
        return "\n".join(t for t in (self.text, self.transcript, self.ocr_text) if t)


class Evidence(BaseModel):
    """Toute sortie d'outil porte ses preuves : le LLM n'a le droit de citer que celles-ci."""
    id: str
    kind: str
    item_uids: list[str] = Field(default_factory=list)
    score: float | None = None
    detail: dict = Field(default_factory=dict)


class Signal(BaseModel):
    """Raison lisible d'un niveau d'alerte : affichée telle quelle à l'utilisateur."""
    name: str
    value: float | int | str
    weight: float = 0.0
    explanation: str


class Cluster(BaseModel):
    id: str
    kind: Literal["copypasta", "semantic", "media", "link", "cross_platform", "coordination"]
    kinds: list[str] = Field(default_factory=list)
    title: str = ""
    signals: list[Signal] = Field(default_factory=list)
    item_uids: list[str]
    platforms: list[str]
    authors: list[str]
    first_ts: datetime
    last_ts: datetime
    evidence: list[Evidence] = Field(default_factory=list)
    level: Level = "review"
    score: float = 0.0
