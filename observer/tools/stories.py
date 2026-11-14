"""Fusion des clusters en « histoires » et niveau d'alerte expliqué (règles déterministes).

Une histoire = un groupe de contenus qui racontent la même chose. Elle n'est PAS suspecte par défaut :
une même actualité reprise par plusieurs médias est normale. Le niveau monte seulement avec des signaux
de coordination (texte identique en rafale, comptes neufs, plusieurs plateformes en quelques minutes…).
"""
from __future__ import annotations

import hashlib
import re
from datetime import timedelta

from observer.core.models import Cluster, ContentItem, Signal

BURST_WINDOW = timedelta(minutes=30)


# Indices d'attribution (citation d'une déclaration, reprise de dépêche), multilingues et génériques
_QUOTES = re.compile(r"[«»“”„\"].{20,}[«»“”„\"]", re.S)
_ATTRIB = re.compile(
    r"\b(said|says|stated|statement|according to|quoted?|full quote|official|press release|communiqu[eé]|"
    r"a d[ée]clar[ée]|d[ée]clare|selon|indique|erkl[äa]rt(e)?|sagte|laut|ha dichiarato|secondo|ha declarado|seg[uú]n|"
    r"powiedzia[łl]|wed[łl]ug|заявил[аи]?|сообщил[аи]?|по словам|заявив|за словами)\b", re.I)
_WIRE = re.compile(r"\((AFP|AP|Reuters|dpa|ANSA|EFE|PAP|Belga|ATS|Kyodo|Xinhua|Ukrinform|TASS)\)|\b(AFP|Reuters|AP)\s*[—–-]", re.I)


def is_quoted_or_wire(text: str) -> bool:
    """Le texte présente-t-il le contenu commun comme une citation attribuée ou une dépêche d'agence ?"""
    t = text or ""
    # Guillemets SEULS ne suffisent pas (beaucoup de titres en contiennent) : il faut aussi une attribution.
    return bool(_WIRE.search(t) or (_QUOTES.search(t) and _ATTRIB.search(t)))


def merge(clusters: list[Cluster], overlap: float = 0.5) -> list[Cluster]:
    """Fusionne les clusters qui partagent ≥ overlap de leurs items (copypasta ⊂ sémantique, etc.)."""
    groups: list[list[Cluster]] = []
    for c in sorted(clusters, key=lambda c: -len(c.item_uids)):
        s = set(c.item_uids)
        for g in groups:
            gs = set().union(*(x.item_uids for x in g))
            if len(s & gs) / min(len(s), len(gs)) >= overlap:
                g.append(c)
                break
        else:
            groups.append([c])
    out = []
    for g in groups:
        uids = sorted(set().union(*(c.item_uids for c in g)))
        kinds = sorted({k for c in g for k in (c.kinds or [c.kind])})
        main = "copypasta" if "copypasta" in kinds else "link" if "link" in kinds else g[0].kind
        out.append(Cluster(
            id="st-" + hashlib.sha1("|".join(uids).encode()).hexdigest()[:10], kind=main, kinds=kinds,
            item_uids=uids, platforms=sorted({p for c in g for p in c.platforms}),
            authors=sorted({a for c in g for a in c.authors}),
            first_ts=min(c.first_ts for c in g), last_ts=max(c.last_ts for c in g),
            evidence=[e for c in g for e in c.evidence]))
    return out


def assess(c: Cluster, items: dict[str, ContentItem]) -> Cluster:
    its = sorted((items[u] for u in c.item_uids if u in items), key=lambda i: i.ts)
    if its:
        c.title = its[0].text[:140]
    sig: list[Signal] = []
    n_src = len(c.authors)
    sig.append(Signal(name="sources", value=n_src, explanation=f"{n_src} distinct sources tell this story"))

    # 1. Texte identique publié par ≥ 3 sources en moins de 30 min : signal de copier-coller coordonné
    if "copypasta" in c.kinds:
        cp_authors = {i.author_pseudo for i in its}
        from observer.tools.links import precise
        pits = [i for i in its if precise(i)]  # dates arrondies à l'heure : inutilisables pour une rafale
        burst = [i for i in pits if i.ts - pits[0].ts <= BURST_WINDOW] if pits else []
        burst_src = len({i.author_pseudo for i in burst})
        quoted = sum(is_quoted_or_wire(i.text) for i in its) / max(1, len(its))
        established = all(i.account.created_at and (i.ts - i.account.created_at).days > 365 for i in its) \
            or all(i.platform == "web" for i in its)
        conc = burst_src / max(1, len(cp_authors))
        if burst_src >= 3 and quoted < 0.5 and conc < 0.3:
            sig.append(Signal(name="copy_viral", value=len(cp_authors), weight=0.1,
                              explanation=f"Same text from {len(cp_authors)} sources over time; only {burst_src} within "
                                          "30 min — looks like ordinary pickup"))
        elif burst_src >= 3 and quoted >= 0.5:
            # Citer la même déclaration officielle ou reprendre la même dépêche est NORMAL : signal fortement réduit,
            # surtout si les sources sont établies. Les autres signaux (comptes neufs, sources listées…) restent actifs.
            sig.append(Signal(name="copy_burst_quoted", value=burst_src, weight=0.05 if established else 0.15,
                              explanation=f"{burst_src} sources repeat the same text within 30 min, but "
                                          f"{round(quoted * 100)}% present it as a quote or wire copy"
                                          + (" from established accounts" if established else "")
                                          + " — usual in normal coverage"))
        elif burst_src >= 3:
            sig.append(Signal(name="copy_burst", value=burst_src, weight=0.5,
                              explanation=f"Near-identical text published by {burst_src} sources within 30 min"))
        else:
            sig.append(Signal(name="copy_slow", value=len(cp_authors), weight=0.1,
                              explanation="Near-identical wording, but spread over time (typical of wire copy)"))
    # 1b. Même lien poussé par plusieurs comptes en peu de temps (amplification de lien)
    if "link" in c.kinds:
        from observer.tools.links import burst_authors
        url = next((e.detail.get("url") for e in c.evidence if e.kind == "shared_link"), "")
        b = burst_authors(its, timedelta(minutes=10))
        conc = b / max(1, len(c.authors))
        if b >= 3 and conc >= 0.5:
            sig.append(Signal(name="link_burst", value=b, weight=0.4,
                              explanation=f"Same link pushed by {b} accounts within 10 min ({url[:60]})"))
        elif b >= 3:
            # Viralité normale : beaucoup de comptes sur la durée, seule une minorité dans la même rafale
            sig.append(Signal(name="link_viral", value=len(c.authors), weight=0.05,
                              explanation=f"Same link shared by {len(c.authors)} accounts over time; only {b} within "
                                          f"10 min — looks like ordinary virality ({url[:50]})"))
        else:
            sig.append(Signal(name="link_shared", value=len(c.authors), weight=0.05,
                              explanation=f"Same link shared by {len(c.authors)} accounts ({url[:60]})"))
    # 2. Plusieurs plateformes en peu de temps
    if len(c.platforms) >= 2:
        span = (its[-1].ts - its[0].ts) if its else timedelta(0)
        fast = span <= timedelta(minutes=15)
        sig.append(Signal(name="cross_platform", value=len(c.platforms), weight=0.4 if fast else 0.15,
                          explanation=f"Seen on {len(c.platforms)} platforms"
                                      + (f" within {int(span.total_seconds() // 60)} min" if fast else "")))
    # 3. Comptes neufs (si la plateforme fournit l'âge)
    new_accts = [i for i in its if i.account.created_at and (i.ts - i.account.created_at).days < 30]
    if len(new_accts) >= 2:
        sig.append(Signal(name="new_accounts", value=len(new_accts), weight=0.3,
                          explanation=f"{len(new_accts)} posts come from accounts created less than 30 days earlier"))

    # 3b. Liens vers des médias d'État / réseaux documentés
    from observer.tools.reputation import label_for
    cited = {}
    for i in its:
        if i.account.known_network:  # déjà compté par le signal « known_network » : pas de double comptage
            continue
        for l in i.links + i.urls_canon:
            lab = label_for(l)
            if lab:
                cited.setdefault(lab, set()).add(i.uid)
    if cited:
        n = len(set().union(*cited.values()))
        sig.append(Signal(name="listed_source_link", value=n, weight=min(0.4, 0.2 + 0.05 * n),
                          explanation=f"{n} item(s) cite or relay listed sources: " + "; ".join(sorted(cited))))
    # 4. Sources listées par un référentiel public (ex. canaux qui alimentent le réseau Pravda, CheckFirst)
    listed = sorted({i.account.known_network for i in its if i.account.known_network})
    n_listed = sum(1 for i in its if i.account.known_network)
    if n_listed:
        sig.append(Signal(name="known_network", value=n_listed, weight=min(0.45, 0.25 + 0.05 * n_listed),
                          explanation=f"{n_listed} item(s) from sources listed as: {', '.join(listed)}"))

    score = min(1.0, sum(s.weight for s in sig))
    c.score = round(score, 2)
    c.level = "priority" if score >= 0.7 else "review" if score >= 0.4 else "organic"
    if c.level == "organic":
        sig.append(Signal(name="assessment", value="organic",
                          explanation="Looks like normal coverage: no coordination signal above threshold"))
    c.signals = sig
    return c
