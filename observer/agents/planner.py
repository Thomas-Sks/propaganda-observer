"""Agent Planner : événement en texte libre → configuration de surveillance (mots-clés, hashtags, fenêtre).

Le LLM propose ; les données disposent : chaque mot-clé est ensuite validé par un volume réel
(Google News RSS sur 24 h), et ceux sans aucun résultat sont écartés.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date

from pydantic import BaseModel, Field

from observer.core import llm
from observer.core.settings import settings


class EventConfig(BaseModel):
    slug: str
    label: str
    country: str = "FR"
    languages: list[str] = Field(default_factory=lambda: ["fr", "en"])
    start: str
    end: str
    keywords: list[str]
    keyword_langs: dict[str, str] = Field(default_factory=dict)  # mot-clé -> langue (requêtes dans la bonne langue)
    hashtags: list[str]
    description: str = ""  # récit / affirmation à surveiller (sert à juger la position des narratifs)
    claim_is_false: bool | None = None  # le récit est-il une affirmation documentée comme fausse ?
    entities: list[str] = Field(default_factory=list)
    lookalike_media: list[str] = Field(default_factory=list)  # médias susceptibles d'être imités
    telegram_channels: list[str] = Field(default_factory=list)  # canaux publics proposés (vérifiés via t.me/s/)
    rationale: str = ""


SYSTEM = """You are the Planner of an OSINT tool that monitors coordinated propaganda around a news event.
Given a free-text event description and today's date, output ONLY a JSON object with keys:
label (short English label), country (ISO-2), languages (list of ISO-639-1 codes relevant to where the narrative
circulates), start, end (YYYY-MM-DD; window covering preparation and aftermath, max 21 days. If the event is in the PAST,
use its ACTUAL dates from your knowledge — never move a past event to today; if it is ongoing, end <= today + 3 days),
description (2 sentences in English: the narrative or claim to watch, as neutrally as possible, and who is reported
to push it if known), keywords (10-16 objects {"text": "...", "lang": "<iso code>"}: search phrases in EACH relevant
language, mixing neutral and partisan/slang framings people actually use), hashtags (6-12,
without '#', as used on X/TikTok/Instagram), entities (people, organisations, places), lookalike_media
(3-6 domains of major local news outlets likely to be impersonated), telegram_channels (0-8 PUBLIC Telegram channel
usernames, without @, that are known to cover or push this topic; leave empty if unsure — they are verified before use),
claim_is_false (true only if the description is about a claim documented as false / disinformation;
false for an ordinary news event or topic), rationale (one sentence).
Do not invent facts about the event; if you really cannot date it, use a window around today."""


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:48]


def _json_block(txt: str) -> dict:
    start = txt.find("{")
    if start < 0:
        raise ValueError(f"Planner: pas de JSON dans la réponse : {txt[:200]}")
    obj, _ = json.JSONDecoder().raw_decode(txt[start:])  # ignore le texte après l'objet
    return obj


def plan(description: str, model: str | None = None) -> EventConfig:
    today = date.today().isoformat()
    out = llm.complete(model=model or settings().model_planner, system=SYSTEM, max_tokens=8000,
                       purpose="planner", user=f"Today: {today}\nEvent: {description}")
    data = _json_block(out)
    data["hashtags"] = [h.lstrip("#") for h in data.get("hashtags", [])]
    kws = data.get("keywords", [])
    if kws and isinstance(kws[0], dict):  # format {text, lang} → liste + correspondance langue
        data["keyword_langs"] = {k["text"]: k.get("lang", "en") for k in kws if k.get("text")}
        data["keywords"] = [k["text"] for k in kws if k.get("text")]
    return EventConfig(slug=slugify(data.get("label") or description), **data)


async def validate_keywords(cfg: EventConfig, min_hits: int = 1) -> dict[str, int]:
    """Volume réel par mot-clé (articles Google News sur 24 h). Les mots-clés sans résultat sont retirés."""
    import asyncio

    from observer.collectors import gnews

    async def count(kw: str) -> tuple[str, int]:
        lang = cfg.keyword_langs.get(kw) or ("en" if kw.isascii() else (cfg.languages or ["fr"])[0])
        try:
            country = gnews.LANG_COUNTRY.get(lang, cfg.country)
            return kw, len(await gnews.fetch(kw, lang=lang, country=country, when=None,
                                             start=cfg.start, end=cfg.end))
        except Exception:
            return kw, -1

    volumes = dict(await asyncio.gather(*(count(k) for k in cfg.keywords)))
    cfg.keywords = [k for k in cfg.keywords if volumes.get(k, 0) >= min_hits or volumes.get(k) == -1]
    return volumes
