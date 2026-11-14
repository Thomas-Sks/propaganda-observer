"""Comptes suspects de coordination : classement explicable, au niveau du COMPTE (pas du narratif).

Indices retenus (inspirés de CooRnet / Pacheco et al. 2021, « Uncovering coordinated networks ») :
- partenaires de rafale : autres comptes ayant publié le même texte (quasi identique) ou le même lien
  à moins de WINDOW_MIN minutes de lui ;
- tandems récurrents : un même partenaire retrouvé dans plusieurs narratifs distincts. C'est l'indice le plus
  fort : une coïncidence se produit une fois, une équipe se retrouve ;
- répétition : le compte republie plusieurs fois le même texte (« recommence ») ;
- cadence d'automate : beaucoup de publications à intervalles très réguliers ;
- participation à des narratifs déjà classés Review / Priority ;
- volume d'automate (seuils DFRLab 72 / 144 publications par jour depuis la création du compte) ;
- famille : ≥ 3 comptes à volume d'automate créés à quelques jours d'intervalle avec le même style d'écriture ;
- lettres Unicode stylisées (𝗴𝗿𝗮𝘀), qui échappent à la recherche par mot-clé ;
- indicateurs individuels (source listée, compte neuf, bot déclaré).

Chaque indice a un poids fixe et une phrase. Aucun seuil n'est réglé sur un événement particulier.
Un niveau « likely » signifie « comportement coordonné observable », pas « faux compte » : une organisation
syndicale qui relaie le même appel avec ses sections locales est coordonnée mais authentique ; d'où l'affichage
des preuves et la mention explicite dans l'interface.
"""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import timedelta

from observer.core.models import Cluster, ContentItem
from observer.tools.links import canonical_url, precise
from observer.tools.provenance import media_registry
from observer.tools.stories import is_quoted_or_wire
from observer.tools.text import minhash, normalize

WINDOW_MIN = 10
SIM = 0.7  # Jaccard MinHash au-delà duquel deux textes sont « le même texte »

WEIGHTS = {
    "listed": 0.35,           # source d'un réseau documenté (VIGINUM, CheckFirst…)
    "recurring_tandem": 0.35,  # même partenaire dans ≥ 2 narratifs
    "burst_partners": 0.25,   # ≥ 3 partenaires de rafale (proportionnel)
    "repeats": 0.2,           # republie ≥ 3 fois le même texte
    "cadence": 0.15,          # cadence régulière d'automate
    "flagged_stories": 0.15,  # présent dans un narratif Review/Priority
    "new": 0.1,               # compte créé < 30 j avant de publier
    "declared_bot": 0.2,
    "volume": 0.3,            # ≥ 144 publications/jour depuis la création (≥ 72 : moitié du poids)
    "styled": 0.1,            # lettres Unicode stylisées (𝗴𝗿𝗮𝘀) : échappe à la recherche par mot-clé
    "family": 0.25,           # ≥ 3 comptes à fort volume, créés à ≤ 7 j d'intervalle, même style
}
# Seuils de volume du DFRLab (« #BotSpot: twelve ways to spot a bot ») : 72/jour suspect, 144/jour très suspect
RATE_SUSPECT, RATE_HIGH = 72, 144
LIKELY, REVIEW = 0.5, 0.3


def own_text(it: ContentItem) -> str:
    """Texte écrit par le compte : sans la carte d'aperçu du lien partagé (« [link] titre chapô »)."""
    return (it.text or "").split("[link]")[0]


def _sig(it: ContentItem):
    t = normalize(own_text(it) + " " + (it.transcript or "") + " " + (it.ocr_text or ""))
    return minhash(t) if len(t.split()) >= 8 else None


def _links(it: ContentItem) -> set[str]:
    """Liens partagés significatifs : URL web canoniques et empreintes d'image de vidéo (pas le son TikTok)."""
    return {canonical_url(x) if x.startswith("http") else x for x in it.links
            if x.startswith(("http", "frame-phash:"))}


def _repeats(its: list[ContentItem]) -> int:
    """Plus grand nombre de publications du compte portant (quasiment) le même texte."""
    sigs = [s for s in (_sig(i) for i in its) if s is not None]
    best = 1 if sigs else 0
    used = [False] * len(sigs)
    for a in range(len(sigs)):
        if used[a]:
            continue
        group = 1
        for b in range(a + 1, len(sigs)):
            if not used[b] and sigs[a].jaccard(sigs[b]) >= SIM:
                used[b] = True
                group += 1
        best = max(best, group)
    return best


def _cadence(its: list[ContentItem]) -> tuple[bool, str]:
    """≥ 12 publications dont les intervalles sont très réguliers (coefficient de variation < 0,35)."""
    ts = sorted(i.ts for i in its)
    if len(ts) < 12:
        return False, ""
    gaps = [(b - a).total_seconds() for a, b in zip(ts, ts[1:]) if (b - a).total_seconds() > 0]
    if len(gaps) < 10:
        return False, ""
    mean = statistics.mean(gaps)
    cv = statistics.pstdev(gaps) / mean if mean else 9
    return cv < 0.35, f"{len(ts)} posts at a regular interval of about {mean / 60:.0f} min (variation {cv:.2f})"


def _rate(its: list[ContentItem]) -> float | None:
    """Publications par jour depuis la création du compte (compteur du profil), si connu."""
    a = its[0].account
    if not a.created_at or not a.posts_count:
        return None
    days = max(1.0, (max(i.ts for i in its) - a.created_at).total_seconds() / 86400)
    return a.posts_count / days


def _styled(its: list[ContentItem]) -> float:
    """Part des publications utilisant des lettres « mathématiques » Unicode (U+1D400–1D7FF)."""
    return sum(any(0x1D400 <= ord(ch) <= 0x1D7FF for ch in (i.text or "")[:200]) for i in its) / max(1, len(its))


def _marker(its: list[ContentItem]) -> str | None:
    """Marqueur commun possible d'un opérateur : écriture stylisée, ou site poussé dans ≥ 60 % des posts."""
    if _styled(its) >= 0.5:
        return "styled"
    doms = Counter(canonical_url(x).split("/")[2] for i in its for x in set(i.links) if x.startswith("http")
                   and len(canonical_url(x).split("/")) > 2)
    if doms:
        d, n = doms.most_common(1)[0]
        if n / len(its) >= 0.6 and d.removeprefix("www.") not in media_registry() and d not in ("bsky.app", "youtube.com", "youtu.be"):
            return f"site:{d}"
    return None


def families(by_author: dict[str, list[ContentItem]]) -> dict[str, tuple[str, list[str]]]:
    """Groupes de ≥ 3 comptes RÉCENTS (≤ 60 j) à volume d'automate, créés à ≤ 7 jours d'intervalle et partageant
    un marqueur (même écriture stylisée, ou même site poussé). {compte: (marqueur, autres membres)}."""
    cand = []
    for a, its in by_author.items():
        r = _rate(its)
        young = (min(i.ts for i in its) - its[0].account.created_at).days <= 60 if r is not None else False
        m = _marker(its) if r is not None and r >= RATE_SUSPECT and young else None
        if m:
            cand.append((its[0].account.created_at, a, its[0].platform, m))
    out: dict[str, tuple[str, list[str]]] = {}
    for key in {(p, m) for _, _, p, m in cand}:
        grp = sorted(c for c in cand if (c[2], c[3]) == key)
        chain: list = []
        for c in grp + [None]:
            if c is not None and (not chain or (c[0] - chain[-1][0]).days <= 7):
                chain.append(c)
                continue
            if len(chain) >= 3:
                for x in chain:
                    out[x[1]] = (key[1], [y[1] for y in chain if y[1] != x[1]])
            chain = [c] if c is not None else []
    return out


def burst_pairs(items: list[ContentItem], clusters: list[Cluster]) -> dict[tuple[str, str], set[str]]:
    """{(compte A, compte B): {groupes}} pour les paires ayant publié même texte ou même lien à < WINDOW_MIN.

    Les groupes issus d'un simple partage de lien sont suffixés « #link » : partager le même article dans les
    mêmes minutes est banal pour un média lu ; il faut que cela se répète plus souvent qu'une copie de texte."""
    by_uid = {i.uid: i for i in items}
    win = timedelta(minutes=WINDOW_MIN)
    pairs: dict[tuple[str, str], set[str]] = defaultdict(set)
    for c in clusters:
        its = sorted((by_uid[u] for u in c.item_uids if u in by_uid and precise(by_uid[u])), key=lambda i: i.ts)
        sigs = {i.uid: _sig(i) for i in its}
        for k, a in enumerate(its):
            for b in its[k + 1:]:
                if b.ts - a.ts > win:
                    break
                if a.author_pseudo == b.author_pseudo:
                    continue
                same_link = bool(_links(a) & _links(b))
                sa, sb = sigs[a.uid], sigs[b.uid]
                same_text = sa is not None and sb is not None and sa.jaccard(sb) >= SIM
                if same_text and is_quoted_or_wire(own_text(a)) and is_quoted_or_wire(own_text(b)):
                    same_text = False  # dépêche d'agence / citation attribuée reprise : normal
                if same_link or same_text:
                    # une « occasion » = une paire de publications (évite de compter deux fois le même échange)
                    occ = "|".join(sorted((a.uid, b.uid)))
                    pairs[tuple(sorted((a.author_pseudo, b.author_pseudo)))].add(occ if same_text else f"{occ}#link")
    return pairs


def rank(items: list[ContentItem], clusters: list[Cluster], accounts: dict[str, dict],
         all_items: list[ContentItem] | None = None) -> list[dict]:
    """Classe les comptes. `accounts` = agrégats de views._accounts (libellé, indicateurs individuels…).

    `all_items` (optionnel) : TOUT ce qui a été collecté, y compris hors sujet. La coordination est un comportement
    du compte : deux canaux qui publient le même texte à la minute près sont en tandem, quel que soit le sujet."""
    by_author: dict[str, list[ContentItem]] = defaultdict(list)
    for i in items:
        by_author[i.author_pseudo].append(i)
    pairs = burst_pairs(items, clusters)
    if all_items:
        from observer.tools.text import find_copypasta
        for (a, b), st in burst_pairs(all_items, find_copypasta(all_items, min_authors=2)).items():
            pairs[(a, b)] |= st
    partners: dict[str, dict[str, set[str]]] = defaultdict(dict)
    for (a, b), st in pairs.items():
        partners[a][b] = st
        partners[b][a] = st
    majors = set(media_registry())
    fam = families(by_author)
    flagged = {c.id for c in clusters if c.level in ("review", "priority")}
    out = []
    for a, its in by_author.items():
        acc = accounts.get(a)
        if not acc:
            continue
        ev: list[dict] = []

        def add(key: str, weight: float, text: str) -> None:
            ev.append({"key": key, "weight": round(weight, 3), "text": text})

        flags = {f["key"]: f for f in acc["flags"]}
        if "listed" not in flags and acc["platform"] == "web" and acc["label"].removeprefix("www.") in majors:
            continue  # grand média établi : la reprise de dépêches n'est pas un indice
        if "listed" in flags:
            add("listed", WEIGHTS["listed"], f"Listed source: {flags['listed']['detail']}")
        if "bot" in flags:
            add("declared_bot", WEIGHTS["declared_bot"], "The account labels itself as automated")
        p = partners.get(a, {})
        # Tandem : ≥ 2 copies de texte, ou ≥ 3 occasions au total si ce ne sont que des partages du même lien
        tandem = {b: st for b, st in p.items()
                  if len({x for x in st if not x.endswith("#link")}) >= 2 or len(st) >= 3}
        if tandem:
            add("recurring_tandem", WEIGHTS["recurring_tandem"],
                f"Posts the same text or link within {WINDOW_MIN} min as the same {len(tandem)} account(s), "
                f"{max(len(s) for s in tandem.values())} separate times")
        if len(p) >= 3:
            add("burst_partners", WEIGHTS["burst_partners"] * min(1.0, len(p) / 8),
                f"Same text or link as {len(p)} other accounts within {WINDOW_MIN} min")
        rep = _repeats(its)
        if rep >= 3:
            add("repeats", WEIGHTS["repeats"] * min(1.0, rep / 6), f"Republished the same text {rep} times")
        cad, why = _cadence(its)
        if cad:
            add("cadence", WEIGHTS["cadence"], why)
        rate = _rate(its)
        if rate is not None and rate >= RATE_SUSPECT:
            add("volume", WEIGHTS["volume"] * (1 if rate >= RATE_HIGH else 0.5),
                f"{its[0].account.posts_count:,} posts since its creation, about {rate:.0f} per day "
                f"(DFRLab: over {RATE_SUSPECT}/day is suspect, over {RATE_HIGH}/day highly suspect)"
                + ("" if "bot" in flags else " — and it does not declare itself automated"))
        sty = _styled(its)
        if sty >= 0.5:
            add("styled", WEIGHTS["styled"], f"Writes in stylised Unicode letters in {sty:.0%} of its posts, which keyword search misses")
        if a in fam:
            mk, others = fam[a]
            same = "the same stylised writing" if mk == "styled" else f"all pushing {mk.removeprefix('site:')}"
            add("family", WEIGHTS["family"], f"Belongs to a group of {len(others) + 1} new high-volume accounts created "
                f"within days of each other, {same}")
        fs = sorted(set(acc["stories"]) & flagged)
        if fs and (p or rep >= 3):  # seulement s'il y a aussi un comportement : pas de culpabilité par association
            add("flagged_stories", WEIGHTS["flagged_stories"], f"Takes part in {len(fs)} narrative(s) flagged Review or Priority")
        if "new" in flags:
            add("new", WEIGHTS["new"], flags["new"]["detail"])
        score = round(min(1.0, sum(e["weight"] for e in ev)), 3)
        behaviour = any(e["key"] in ("recurring_tandem", "burst_partners", "repeats", "cadence", "volume", "family") for e in ev)
        if score < REVIEW or not behaviour and "listed" not in flags:
            continue
        top_partners = sorted(p.items(), key=lambda kv: -len(kv[1]))[:8]
        out.append({
            **{k: acc[k] for k in ("id", "label", "platform", "items", "stories", "followers", "created_at",
                                   "first_ts", "last_ts", "flags", "stance_mix")},
            "score": score, "level": "likely" if score >= LIKELY else "review", "evidence": ev,
            "partners": [{"id": b, "label": accounts.get(b, {}).get("label", b[:8]), "stories": sorted(st)}
                         for b, st in top_partners],
            "declared_bot": "bot" in flags,
            "repeats": rep, "flagged_stories": fs, "posts_per_day": round(rate, 1) if rate else None,
            "family": [{"id": b, "label": accounts.get(b, {}).get("label", b[:8])} for b in fam.get(a, (None, []))[1]],
        })
    out.sort(key=lambda r: (-r["score"], -len(r["partners"]), -r["items"]))
    return out
