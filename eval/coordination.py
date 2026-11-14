"""Banc de coordination par injection (SPECS §8, dernière ligne du tableau).

Principe : on part de VRAIS textes collectés pour l'événement, puis on fabrique, avec une graine fixe :
- des essaims (positifs) : copie exacte par comptes neufs, copie retouchée en rafale, même lien en rafale,
  comptes neufs étalés dans le temps, et un essaim « patient » (comptes vieillis, 2 jours) volontairement difficile ;
- des contenus viraux LÉGITIMES (négatifs) : dépêche reprise par 10 médias sur 6 h, même lien partagé par des
  comptes anciens sur 2 jours, déclaration officielle citée par des comptes anciens sur 2 h.

Chaque scénario est injecté dans un bruit de fond réel (items de l'événement), puis passe par la même chaîne
que la production : find_copypasta(min_authors=2) + find_link_shares → merge → assess. Aucun seuil n'est réglé
sur ce banc : les seuils de stories.py étaient figés avant sa construction.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from observer.core.models import AccountMeta, ContentItem
from observer.tools.links import find_link_shares
from observer.tools.stories import assess, merge
from observer.tools.text import find_copypasta, normalize

SEED = 20261114
N_PER_TYPE = 30
BACKGROUND = 300
LEVEL_RANK = {"organic": 0, "insufficient_data": 0, "review": 1, "priority": 2}

SOCIAL = ["bluesky", "x", "telegram", "mastodon"]
MEDIA = ["lemonde.fr", "lefigaro.fr", "liberation.fr", "francetvinfo.fr", "ouest-france.fr", "20minutes.fr",
         "leparisien.fr", "lexpress.fr", "rfi.fr", "france24.com", "bfmtv.com", "lci.fr", "lepoint.fr"]
PREFIXES = ["BREAKING:", "Must read:", "Share this!", "🚨", "They don't want you to see this:", "Wake up:"]
TAGS = ["#Ukraine", "#Azov", "#truth", "#news", "#warcrimes", "#StopTheWar"]

# (type, libellé, positif ?, description)
TYPES = [
    ("swarm_exact", "Exact copy by new accounts", True,
     "5–10 accounts created 2–25 days earlier post the same text within 20 min"),
    ("swarm_edited", "Edited copy in a burst", True,
     "5–10 aged accounts post lightly edited copies (prefix, hashtags, dropped words) within 25 min"),
    ("link_burst", "Same link in a burst", True,
     "4–8 aged accounts push the same link with different comments within 8 min"),
    ("new_slow", "New accounts, spread over hours", True,
     "4–8 accounts created < 20 days earlier post near-identical text over 3–8 h"),
    ("patient_swarm", "Patient swarm (hard case)", True,
     "5–8 aged accounts post edited copies spread over 2 days — designed to look organic"),
    ("wire_copy", "Wire story republished by media", False,
     "8–12 established outlets republish the same dispatch over 6 h, each with its own article link"),
    ("link_organic", "Popular link shared over days", False,
     "5–10 accounts older than 1 year share the same link with their own words over 2 days"),
    ("official_quote", "Official statement quoted", False,
     "5–8 accounts older than 1 year quote the same official statement over 2 h"),
]


@dataclass
class Scenario:
    sid: str
    kind: str
    label: str
    positive: bool
    description: str
    items: list[ContentItem] = field(default_factory=list)


def _edit(text: str, rng: random.Random) -> str:
    """Retouche légère : préfixe, mots retirés, hashtags — ce que font les essaims pour éviter le dédoublonnage."""
    words = text.split()
    for _ in range(rng.randint(1, 2)):
        if len(words) > 12:
            words.pop(rng.randrange(len(words)))
    out = " ".join(words)
    if rng.random() < 0.7:
        out = f"{rng.choice(PREFIXES)} {out}"
    if rng.random() < 0.7:
        out += " " + " ".join(rng.sample(TAGS, rng.randint(1, 3)))
    return out


def _acct(rng: random.Random, ts: datetime, min_days: int, max_days: int) -> AccountMeta:
    days = rng.randint(min_days, max_days)
    young = days < 30
    return AccountMeta(created_at=ts - timedelta(days=days, hours=rng.randint(0, 23)),
                       followers=rng.randint(0, 40) if young else rng.randint(80, 5000),
                       following=rng.randint(50, 900) if young else rng.randint(50, 1500))


def _post(sid: str, k: int, platform: str, ts: datetime, text: str, acct: AccountMeta | None,
          link: str | None = None, author: str | None = None) -> ContentItem:
    links = [link] if link else []
    dom = link.split("/")[2] if link else None
    return ContentItem(platform=platform, post_id=f"{sid}-{k}", ts=ts, author_pseudo=author or f"{sid}-a{k}",
                       text=text, links=links, urls_canon=[dom] if dom else [], account=acct or AccountMeta(),
                       event="bench")


def _first_sentence(text: str, n: int = 18) -> str:
    return " ".join(text.split()[:n])


def build(texts: list[str], t0: datetime, t1: datetime) -> list[Scenario]:
    """Construit N_PER_TYPE scénarios par type, chacun avec un texte source distinct."""
    rng = random.Random(SEED)
    pool = list(texts)
    rng.shuffle(pool)
    span = (t1 - t0).total_seconds()
    out: list[Scenario] = []
    for kind, label, pos, desc in TYPES:
        for n in range(N_PER_TYPE):
            sid = f"{kind}-{n:02d}"
            sc = Scenario(sid, kind, label, pos, desc)
            base = t0 + timedelta(seconds=rng.uniform(0, span))
            seed = pool.pop()
            plats = rng.sample(SOCIAL, rng.choice([1, 1, 2]))
            if kind == "swarm_exact":
                for k in range(rng.randint(5, 10)):
                    ts = base + timedelta(minutes=rng.uniform(0, 20))
                    sc.items.append(_post(sid, k, rng.choice(plats), ts, seed, _acct(rng, ts, 2, 25)))
            elif kind == "swarm_edited":
                for k in range(rng.randint(5, 10)):
                    ts = base + timedelta(minutes=rng.uniform(0, 25))
                    sc.items.append(_post(sid, k, rng.choice(plats), ts, _edit(seed, rng), _acct(rng, ts, 60, 2000)))
            elif kind in ("link_burst", "link_organic"):
                link = f"https://{rng.choice(['news-site.example', 'blog.example', 'video.example'])}/p/{sid}"
                n_acc, minutes, (lo, hi) = ((rng.randint(4, 8), 8, (60, 2000)) if kind == "link_burst"
                                            else (rng.randint(5, 10), 48 * 60, (400, 4000)))
                # Chaque compte écrit ses propres mots (début d'un autre texte réel ; scénarios exécutés isolément)
                others = rng.sample([t for t in texts if t != seed], n_acc)
                for k in range(n_acc):
                    ts = base + timedelta(minutes=rng.uniform(0, minutes))
                    comment = _first_sentence(others[k], rng.randint(6, 16))
                    sc.items.append(_post(sid, k, rng.choice(plats), ts, f"{comment} {link}", _acct(rng, ts, lo, hi),
                                          link=link))
            elif kind == "new_slow":
                for k in range(rng.randint(4, 8)):
                    ts = base + timedelta(minutes=rng.uniform(0, rng.uniform(180, 480)))
                    sc.items.append(_post(sid, k, rng.choice(plats), ts, _edit(seed, rng), _acct(rng, ts, 1, 19)))
            elif kind == "patient_swarm":
                for k in range(rng.randint(5, 8)):
                    ts = base + timedelta(minutes=rng.uniform(0, 48 * 60))
                    sc.items.append(_post(sid, k, rng.choice(plats), ts, _edit(seed, rng), _acct(rng, ts, 200, 3000)))
            elif kind == "wire_copy":
                for k, media in enumerate(rng.sample(MEDIA, rng.randint(8, 12))):
                    ts = base + timedelta(minutes=rng.uniform(0, 360))
                    text = f"{seed} (AFP) — {media.split('.')[0].capitalize()}"
                    sc.items.append(_post(sid, k, "web", ts, text, None, link=f"https://{media}/article/{sid}-{k}",
                                          author=f"media:{media}"))
            elif kind == "official_quote":
                quote = _first_sentence(seed, 40)
                for k in range(rng.randint(5, 8)):
                    ts = base + timedelta(minutes=rng.uniform(0, 120))
                    intro = rng.choice(["Statement just now:", "Official:", "Full quote:", "", "Read the statement:"])
                    sc.items.append(_post(sid, k, rng.choice(plats), ts, f"{intro} «{quote}»".strip(),
                                          _acct(rng, ts, 400, 4000)))
            out.append(sc)
    return out


def run_scenario(sc: Scenario, background: list[ContentItem]) -> tuple[bool, str, list[str]]:
    """Passe le scénario + bruit de fond dans la chaîne de production. Renvoie (alerte ?, niveau, raisons)."""
    items = background + sc.items
    by_uid = {i.uid: i for i in items}
    raw = find_copypasta(items, min_authors=2) + find_link_shares(items)
    mine = {i.uid for i in sc.items}
    # Histoires qui regroupent au moins 2 posts du scénario ; on retient la plus alarmante
    stories = [st for st in (assess(c, by_uid) for c in merge(raw)) if len(mine & set(st.item_uids)) >= 2]
    if not stories:
        return False, "organic", ["no story formed: the posts were not grouped together"]
    st = max(stories, key=lambda s: (LEVEL_RANK[s.level], s.score))
    reasons = [s.explanation for s in st.signals if s.weight > 0] or ["no coordination signal above threshold"]
    reasons.append(f"score {st.score:.2f}")
    return LEVEL_RANK[st.level] >= 1, st.level, reasons


def prepare_texts(items: list[ContentItem], rng: random.Random) -> tuple[list[str], list[ContentItem]]:
    """Sépare les items réels en deux moitiés : textes sources des scénarios / bruit de fond (sans recouvrement)."""
    seen, uniq = set(), []
    for i in sorted(items, key=lambda x: x.uid):
        t = " ".join(i.full_text().split())
        key = normalize(t)[:80]
        if len(t.split()) >= 25 and key not in seen:
            seen.add(key)
            uniq.append((key, t[:600]))
    rng.shuffle(uniq)
    half = len(uniq) // 2
    seeds, seed_keys = [t for _, t in uniq[:half]], {k for k, _ in uniq[:half]}
    bg = [i for i in items if normalize(i.full_text())[:80] not in seed_keys]
    rng.shuffle(bg)
    return seeds, bg[:BACKGROUND]
