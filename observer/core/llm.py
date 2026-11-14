"""Client LLM unique (AI Router Hostinger, SDK Anthropic) avec plafond de dépense dur.

Chaque réponse du Router renvoie `usage.credits_charged` (1 crédit = 0,01 $ : 5000 crédits = 50 $).
On cumule la dépense en USD dans Redis et on refuse tout appel une fois le plafond atteint.
Deux familles : modèles `claude-*` via le SDK Anthropic, les autres (OpenAI, Mistral…) via le SDK OpenAI.
"""
from __future__ import annotations

import json
from observer.core.settings import settings  # noqa: F401  (réexport pour la CLI)
import time

import anthropic
import redis

from observer.core.settings import settings

SPENT_KEY = "observer:llm:spent_usd"
LOG_KEY = "observer:llm:log"


class BudgetExceeded(RuntimeError):
    pass


_sync_redis: redis.Redis | None = None
_client: anthropic.Anthropic | None = None


def _r() -> redis.Redis:
    global _sync_redis
    if _sync_redis is None:
        _sync_redis = redis.from_url(settings().redis_url, decode_responses=True)
    return _sync_redis


def client() -> anthropic.Anthropic:
    guard()  # toute requête Claude passe par ici
    global _client
    if _client is None:
        s = settings()
        _client = anthropic.Anthropic(api_key=s.ai_router_key, base_url=s.ai_router_anthropic_base_url,
                                      default_headers={"Authorization": f"Bearer {s.ai_router_key}"})
    return _client


def spent() -> float:
    return float(_r().get(SPENT_KEY) or 0.0)


def remaining() -> float:
    return settings().llm_budget_usd - spent()


# Lecture seule (requêtes du compte de démonstration) : aucun appel payant ne doit partir, même par erreur.
from contextvars import ContextVar  # noqa: E402

READ_ONLY: ContextVar[bool] = ContextVar("observer_read_only", default=False)


class ReadOnly(PermissionError):
    """Appel payant tenté dans un contexte en lecture seule (compte de démonstration)."""


def guard() -> None:
    if READ_ONLY.get():
        raise ReadOnly("Paid AI calls are disabled for the read-only demo account")


def _charge(model: str, tokens_in: int, tokens_out: int, credits: float | None, purpose: str) -> float:
    if credits is None:  # champ absent : estimation pessimiste (tarif d'un gros modèle)
        credits = tokens_in * 0.0006 + tokens_out * 0.003
    usd = float(credits) * settings().usd_per_credit
    _r().incrbyfloat(SPENT_KEY, usd)
    _r().lpush(LOG_KEY, json.dumps({"t": time.time(), "model": model, "purpose": purpose,
                                    "in": tokens_in, "out": tokens_out, "credits": credits, "usd": usd}))
    _r().ltrim(LOG_KEY, 0, 999)
    return usd


def create(*, model: str, messages: list, max_tokens: int = 1024, purpose: str = "", **kw):
    """Équivalent de client().messages.create, avec contrôle du budget avant et après l'appel."""
    guard()
    if remaining() <= 0:
        raise BudgetExceeded(f"Plafond LLM atteint ({spent():.4f} / {settings().llm_budget_usd})")
    resp = client().messages.create(model=model, messages=messages, max_tokens=max_tokens, **kw)
    u = resp.usage
    _charge(model, u.input_tokens, u.output_tokens, getattr(u, "credits_charged", None), purpose)
    return resp


_oa = None


def openai_client():
    guard()  # toute requête OpenAI-compatible (embeddings, Whisper, vision, chat) passe par ici
    global _oa
    if _oa is None:
        from openai import OpenAI
        s = settings()
        _oa = OpenAI(api_key=s.ai_router_key, base_url=s.ai_router_openai_base_url)
    return _oa


def complete(*, model: str, system: str, user: str, max_tokens: int = 4000, purpose: str = "") -> str:
    """Appel texte → texte indépendant du fournisseur (claude-* via Anthropic, le reste via OpenAI)."""
    if model.startswith("claude"):
        return text(create(model=model, system=system, max_tokens=max_tokens, purpose=purpose,
                           messages=[{"role": "user", "content": user}]))
    guard()
    if remaining() <= 0:
        raise BudgetExceeded(f"Plafond LLM atteint ({spent():.4f} $ / {settings().llm_budget_usd} $)")
    resp = openai_client().chat.completions.create(
        model=model, max_completion_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    u = resp.usage
    credits = getattr(u, "credits_charged", None)
    if credits is None and getattr(u, "model_extra", None):
        credits = u.model_extra.get("credits_charged")
    _charge(model, u.prompt_tokens, u.completion_tokens, credits, purpose)
    return resp.choices[0].message.content or ""


def text(resp) -> str:
    """Concatène les blocs texte (ignore les blocs de réflexion)."""
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
