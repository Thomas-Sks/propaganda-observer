"""Score de provenance « Trust the source » (SPECS §3bis) : outils déterministes + régression logistique à poids publiés.

Chaque outil renvoie ses preuves brutes (date RDAP, identifiant GA, sosie, paire de textes…). Le score sert à
PRIORISER une vérification, jamais à condamner. Aucun appel LLM : réseau public (RDAP, WHOIS port 43, crt.sh,
Wayback CDX, page d'accueil, DNS pour dnstwist) + base locale. Cache Redis 7 jours, tolérant à l'absence de Redis.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import UTC, datetime
from functools import lru_cache
from urllib.parse import urlparse

import httpx
import tldextract

from observer.collectors.gnews import registrable
from observer.tools.reputation import label_for, listed

MODEL_VERSION = "prov-0.1.0 (initial weights SPECS §3bis, uncalibrated)"
LISTS_FROZEN = "2026-11-14"
DEFAULT_EVENT = None  # None = l'événement actif le plus récent (aucun événement codé en dur)
CACHE_TTL = 7 * 86400
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
YOUNG_DAYS = 183  # « moins de 6 mois »
MAX_MISSING = 3   # abstention au-delà
CLONE_FULL = 0.2  # part de textes clonés qui donne la contribution pleine
NOW = lambda: datetime.now(UTC)

# ---------------------------------------------------------------- poids publiés (logit)
BIAS = -3.0  # σ(-3) ≈ 5 % : un site sans aucun signal reste en bas de l'échelle
DOMAIN_WEIGHTS: dict[str, tuple[float, str]] = {
    "listed_network": (3.0, "On a public list of documented influence outlets / networks"),
    "shared_tracker": (3.0, "Shares a Google Analytics / GTM / AdSense ID with a listed domain (conclusive indicator)"),
    "cloned_content": (2.0, "Republishes texts first published by a listed source (MinHash Jaccard ≥ 0.8; full weight at 20 % of its texts)"),
    "typosquat": (2.0, "Look-alike of an established news outlet (dnstwist / affix / TLD swap)"),
    "young_domain": (1.0, "Domain registered or first certificate issued less than 6 months ago"),
    "no_transparency": (0.8, "No about page, legal notice or signed authors on the home page"),
    "ai_text_share": (0.7, "≥ 50 % of ≥ 20 long articles flagged as AI-generated (capped)"),
    "few_archives": (0.5, "Fewer than 3 Wayback Machine captures"),
    "amplified_by_cluster": (1.0, "Linked by a coordinated cluster detected in the event"),
    "whois_masked": (0.3, "Registrant hidden in WHOIS/RDAP (very common for legitimate sites too)"),
}
ACCOUNT_WEIGHTS: dict[str, tuple[float, str]] = {
    "listed_network": (3.0, "Account of a listed source / network"),
    "cites_listed": (2.0, "Links to listed sources (share of its posts, bounded)"),
    "copied_posts": (1.0, "Posts near-identical to other accounts' posts (copypasta clusters)"),
    "in_coordinated_cluster": (1.0, "Member of a coordinated cluster flagged for review or priority"),
    "automated": (1.0, "Self-declared automated account"),
    "new_account": (1.0, "Account created less than 30 days before posting"),
    "low_audience": (0.3, "Fewer than 50 followers"),
    "ai_text_share": (0.7, "≥ 50 % of ≥ 20 posts flagged as AI-generated (capped)"),
}
AI_REASON = ("not measured: no reliable open detector for short, multilingual text "
             "(TPR 7-58 % at 1 % FPR, arXiv 2412.05139), see SPECS §3bis")

# Grands médias imitables : liste MONDIALE chargée depuis data/registry/major_media.yaml (extensible, aucun code).
# Format : liste de {domain, name, country, lang} ; un dict {groupe: [domaines]} est aussi accepté.
MEDIA_REGISTRY = "data/registry/major_media.yaml"


@lru_cache(maxsize=1)
def media_registry() -> dict[str, dict]:
    import yaml

    from observer.core.settings import ROOT
    p = ROOT / MEDIA_REGISTRY
    data = yaml.safe_load(p.read_text()) if p.exists() else []
    if isinstance(data, dict):
        data = [{"domain": d} for group in data.values() for d in group]
    return {registrable(e["domain"]): e for e in data or [] if e.get("domain")}


# Préfixes/suffixes génériques ajoutés à une marque (« the » + washingtonexaminer) ; les codes pays/langue à
# 2 lettres et les nombres sont traités par règle, pas listés (aucun pays privilégié).
AFFIXES = ("the", "news", "info", "daily", "today", "online", "live", "media", "press", "post", "official", "real")


def _affix(flat: str, brand: str) -> str | None:
    if len(brand) < 4 or flat == brand or brand not in flat:
        return None
    extra = flat.replace(brand, "", 1)
    if not (flat.startswith(brand) or flat.endswith(brand)):
        return None
    return extra if extra in AFFIXES or re.fullmatch(r"[a-z]{2}|\d{1,4}", extra) else None


# ---------------------------------------------------------------- cache Redis (optionnel)


def _cache_get(key: str):
    try:
        from observer.core.llm import _r
        v = _r().get("observer:prov:" + key)
        return json.loads(v) if v else None
    except Exception:
        return None


def _cache_set(key: str, value, ttl: int = CACHE_TTL) -> None:
    try:
        from observer.core.llm import _r
        _r().set("observer:prov:" + key, json.dumps(value, default=str), ex=ttl)
    except Exception:
        pass


# ---------------------------------------------------------------- cible


def parse_target(target: str) -> tuple[str, str]:
    """→ (« domain » | « account », valeur normalisée). URL et domaine donnent l'hôte en minuscules."""
    t = target.strip()
    m = re.match(r"^(x|youtube|tiktok|instagram|facebook|bluesky|mastodon|telegram|web):(.+)$", t)
    if m and "//" not in t:
        return "account", t
    host = urlparse(t if "://" in t else "http://" + t).hostname or t
    host = host.lower().removeprefix("www.")
    return "domain", host


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=UTC)
        return (NOW() - d).days
    except ValueError:
        return None


# ---------------------------------------------------------------- site_signals

_PRIVACY = re.compile(r"redact|privacy|private|proxy|withheld|not disclosed|data protected|gdpr|masked", re.IGNORECASE)


def _whois43(domain: str) -> str | None:
    """WHOIS port 43 (repli quand le TLD n'a pas de RDAP, ex. .su) : IANA donne le serveur."""
    def q(server: str, query: str) -> str:
        with socket.create_connection((server, 43), timeout=10) as s:
            s.sendall((query + "\r\n").encode())
            buf = b""
            while chunk := s.recv(4096):
                buf += chunk
        return buf.decode("utf-8", "replace")
    try:
        tld = domain.rsplit(".", 1)[-1]
        ref = re.search(r"^whois:\s*(\S+)", q("whois.iana.org", tld), re.MULTILINE)
        return q(ref.group(1), domain) if ref else None
    except OSError:
        return None


def parse_rdap(j: dict) -> dict:
    created = next((e.get("eventDate") for e in j.get("events", []) if e.get("eventAction") == "registration"), None)
    registrar, registrant = None, None
    for ent in j.get("entities", []):
        fn = next((x[3] for x in (ent.get("vcardArray") or [None, []])[1] if x[0] in ("fn", "org")), None)
        if "registrar" in ent.get("roles", []):
            registrar = fn
        if "registrant" in ent.get("roles", []):
            registrant = fn or "(no name)"
    remarks = " ".join(" ".join(r.get("description", [])) for r in j.get("remarks", []))
    masked = registrant is None or bool(_PRIVACY.search(registrant or "")) or bool(_PRIVACY.search(remarks) and not registrant)
    return {"created": created, "registrar": registrar, "registrant": registrant, "whois_masked": masked, "source": "rdap"}


def parse_whois_text(txt: str) -> dict:
    created = re.search(r"^\s*(?:created|creation date|registered on|registration time)\s*:\s*(\S+)", txt, re.IGNORECASE | re.MULTILINE)
    registrar = re.search(r"^\s*registrar\s*:\s*(.+)$", txt, re.IGNORECASE | re.MULTILINE)
    registrant = re.search(r"^\s*(?:person|registrant(?: name)?|org)\s*:\s*(.+)$", txt, re.IGNORECASE | re.MULTILINE)
    name = registrant.group(1).strip() if registrant else None
    return {"created": created.group(1) if created else None, "registrar": registrar.group(1).strip() if registrar else None,
            "registrant": name, "whois_masked": name is None or bool(_PRIVACY.search(name)), "source": "whois:43"}


async def _registration(c: httpx.AsyncClient, domain: str) -> dict | None:
    try:
        r = await c.get(f"https://rdap.org/domain/{domain}", timeout=15)
        if r.status_code == 200:
            return parse_rdap(r.json())
    except (httpx.HTTPError, ValueError):
        pass
    txt = await asyncio.to_thread(_whois43, domain)
    return parse_whois_text(txt) if txt and "no match" not in txt.lower() else None


async def _crt_first(c: httpx.AsyncClient, domain: str) -> dict | None:
    try:
        r = await c.get("https://crt.sh/", params={"q": domain, "output": "json"}, timeout=20)
        rows = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not rows:
        return {"first_cert": None, "certs": 0}
    first = min(rows, key=lambda x: x.get("not_before", "9999"))
    return {"first_cert": first.get("not_before"), "issuer": first.get("issuer_name"), "certs": len(rows),
            "crt_id": first.get("id")}


async def _wayback(c: httpx.AsyncClient, domain: str) -> dict | None:
    try:
        r = await c.get("http://web.archive.org/cdx/search/cdx", timeout=20,
                        params={"url": domain, "output": "json", "fl": "timestamp", "limit": 50, "collapse": "timestamp:8"})
        rows = r.json() if r.text.strip() else []
    except (httpx.HTTPError, ValueError):
        return None
    caps = [x[0] for x in rows[1:]]
    return {"captures": len(caps), "capped_at": 50, "first_capture": caps[0] if caps else None}


# Segments de chemin et libellés de lien (comparaison exacte, pas de sous-chaîne : « midterms » ≠ « terms »)
_ABOUT_SEG = re.compile(r"^(about|about-us|about-[a-z]+|a-propos|apropos|qui-sommes-nous|ueber-uns|uber-uns|chi-siamo|"
                        r"quienes-somos|over-ons|o-nas|redaction|la-redaction|the-team|our-team|who-we-are)$")
_LEGAL_SEG = re.compile(r"^(mentions-legales|legal|legal-notice|impressum|imprint|privacy|privacy-policy|privacy_policy|"
                        r"datenschutz|aviso-legal|note-legali|terms|terms-of-use|terms-of-service|terms-and-conditions|cgu|"
                        r"cgv|user-agreement|politique-de-confidentialite|copyright|disclaimer)$")
_ABOUT_TXT = {"about", "about us", "à propos", "a propos", "qui sommes-nous", "qui sommes nous", "über uns", "chi siamo",
              "quiénes somos", "over ons", "о нас", "who we are", "our team", "la rédaction", "redaktion"}
_LEGAL_TXT = {"privacy policy", "privacy", "terms", "terms of use", "terms of service", "legal notice", "legal",
              "mentions légales", "impressum", "datenschutz", "cgu", "conditions générales", "politique de confidentialité",
              "aviso legal", "note legali", "disclaimer"}
_AUTHOR = re.compile(r'rel=["\']author|/author/|/auteur/|/autor/|name=["\']author|class=["\'][^"\']*(?:byline|author)', re.IGNORECASE)
_HREF = re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
TRACKER_PATTERNS = [
    re.compile(r"googletagmanager\.com/gtag/js\?id=((?:G|UA|AW)-[A-Z0-9-]+)"),
    re.compile(r"""gtag\(\s*['"]config['"]\s*,\s*['"]((?:G|UA|AW)-[A-Z0-9-]+)"""),
    re.compile(r"\b(GTM-[A-Z0-9]{4,9})\b"),
    re.compile(r"\b(UA-\d{4,10}-\d{1,4})\b"),
    re.compile(r"\b(?:ca-)?(pub-\d{10,20})\b"),
]


def extract_trackers(html: str) -> list[str]:
    """Identifiants analytics / pub (regex). UA-123-4 est normalisé en UA-123 (le compte, pas la propriété)."""
    ids: set[str] = set()
    for p in TRACKER_PATTERNS:
        for m in p.findall(html):
            ids.add(re.sub(r"^(UA-\d+)-\d+$", r"\1", m))
    return sorted(ids)


def parse_homepage(html: str, base_url: str = "") -> dict:
    """Pages à-propos / mentions légales / auteurs (liens INTERNES seulement) + identifiants analytics."""
    from urllib.parse import urljoin
    base_reg = registrable(base_url) if base_url else None
    about = legal = None
    offsite: list[str] = []
    for href, inner in _HREF.findall(html):
        txt = " ".join(re.sub(r"<[^>]+>", " ", inner).split()).lower()
        full = urljoin(base_url or "http://x/", href)
        u = urlparse(full)
        segs = [re.sub(r"\.(html?|php|aspx?)$", "", x).lower() for x in u.path.split("/") if x]
        is_about = any(_ABOUT_SEG.match(x) for x in segs) or txt in _ABOUT_TXT
        is_legal = any(_LEGAL_SEG.match(x) for x in segs) or txt in _LEGAL_TXT
        if not (is_about or is_legal):
            continue
        if base_reg and u.hostname and registrable(u.hostname) != base_reg:
            offsite.append(full)  # ex. faux site qui renvoie vers les mentions du vrai média
            continue
        if is_about and not about:
            about = full
        if is_legal and not legal:
            legal = full
    author = _AUTHOR.search(html)
    return {"about_link": about, "legal_link": legal, "authors_marker": author.group(0) if author else None,
            "offsite_about_or_legal": sorted(set(offsite))[:5], "trackers": extract_trackers(html), "bytes": len(html)}


async def _homepage(c: httpx.AsyncClient, host: str) -> dict | None:
    """Page d'accueil en direct ; sinon (site bloqué dans l'UE, refus, page vide) dernière capture Wayback brute."""
    err = None
    for url in (f"https://{host}/", f"http://{host}/"):
        try:
            r = await c.get(url, timeout=12, follow_redirects=True)
        except httpx.HTTPError as e:
            err = type(e).__name__
            continue
        if r.status_code < 400 and len(r.text) >= 2000:
            return {"final_url": str(r.url), "status": r.status_code, "via": "live", **parse_homepage(r.text, str(r.url))}
        err = f"HTTP {r.status_code}, {len(r.text)} bytes"
        break
    try:  # id_ = HTML d'origine, sans la barre Wayback
        r = await c.get(f"https://web.archive.org/web/2026id_/https://{host}/", timeout=25, follow_redirects=True)
        if r.status_code < 400 and len(r.text) >= 2000:
            snap = re.search(r"/web/(\d{14})", str(r.url))
            return {"final_url": f"https://{host}/", "status": r.status_code, "via": "wayback",
                    "snapshot": snap.group(1) if snap else None, "live_error": err,
                    **parse_homepage(r.text, f"https://{host}/")}
    except httpx.HTTPError:
        pass
    return {"error": err or "unreachable", "final_url": f"https://{host}/"} if err else None


async def site_signals(domain: str, refresh: bool = False) -> dict:
    """Âge (RDAP / WHOIS), premier certificat (crt.sh), captures Wayback, WHOIS masqué, page d'accueil, trackers."""
    host = parse_target(domain)[1]
    reg = registrable(host) or host
    key = f"site:{host}"
    if not refresh and (hit := _cache_get(key)):
        return hit
    async with httpx.AsyncClient(headers={"User-Agent": UA}, follow_redirects=True) as c:
        registration, crt, wb, home = await asyncio.gather(
            _registration(c, reg), _crt_first(c, reg), _wayback(c, reg), _homepage(c, host))
    out = {"domain": host, "registrable": reg, "registration": registration, "crt": crt, "wayback": wb,
           "homepage": home, "fetched_at": NOW().isoformat()}
    complete = all((registration, crt, wb, home)) and "error" not in (home or {})
    _cache_set(key, out, CACHE_TTL if complete else 3600)  # résultat partiel : on réessaie dans 1 h
    return out


# ---------------------------------------------------------------- typosquat


def _label(d: str) -> tuple[str, str]:
    e = tldextract.extract(d)
    return e.domain, e.suffix


@lru_cache(maxsize=64)
def _fuzz_set(media: str) -> frozenset[str]:
    import dnstwist
    f = dnstwist.Fuzzer(media)
    f.generate()
    return frozenset(x["domain"] for x in f.domains if x["fuzzer"] != "*original")


def lookalike_of(domain: str) -> dict | None:
    """Ce domaine est-il un sosie d'un grand média du registre ? Échange de TLD, préfixe/suffixe, ou permutation dnstwist."""
    from rapidfuzz import fuzz
    media = media_registry()
    reg = registrable(domain)
    if reg in media:
        return None
    lab, suf = _label(reg)
    flat = lab.replace("-", "")
    for m, entry in sorted(media.items()):
        mlab, msuf = _label(m)
        info = {"media": m, "name": entry.get("name"), "country": entry.get("country")}
        generic = bool(entry.get("generic"))  # marque = mot courant : TLD et affixes non concluants
        if not generic and lab == mlab and suf != msuf:
            return {**info, "method": "tld-swap", "detail": f"{reg} vs {m}"}
        if not generic and (extra := _affix(flat, mlab.replace("-", ""))) is not None:
            return {**info, "method": "affix", "detail": f"'{extra}' added to '{mlab}'"}
        if fuzz.ratio(lab, mlab) >= 80 and reg in _fuzz_set(m):
            return {**info, "method": "dnstwist", "detail": f"{reg} is a dnstwist permutation of {m}"}
    return None


def registered_lookalikes(domain: str, budget_s: float = 10.0, max_candidates: int = 400) -> dict:
    """Sosies ENREGISTRÉS de ce domaine (résolution DNS, budget de temps borné). Informatif, sans poids."""
    import dnstwist
    reg = registrable(domain)
    if (hit := _cache_get(f"twins:{reg}")) is not None:
        return hit
    f = dnstwist.Fuzzer(reg)
    f.generate(fuzzers=["omission", "transposition", "replacement", "hyphenation", "homoglyph", "repetition", "vowel-swap"])
    cands = sorted({x["domain"] for x in f.domains if x["fuzzer"] != "*original"})[:max_candidates]

    def resolves(d: str) -> str | None:
        try:
            socket.getaddrinfo(d, None)
            return d
        except OSError:
            return None
    t0 = time.monotonic()
    ex = ThreadPoolExecutor(max_workers=48)
    futs = [ex.submit(resolves, d) for d in cands]
    done, pending = wait(futs, timeout=budget_s)
    ex.shutdown(wait=False, cancel_futures=True)
    found = sorted(r for f_ in done if (r := f_.result()) and r != reg)
    out = {"checked": len(done), "candidates": len(cands), "registered": found[:30], "n_registered": len(found),
           "complete": not pending, "seconds": round(time.monotonic() - t0, 1)}
    if not pending:
        _cache_set(f"twins:{reg}", out)
    return out


async def typosquat(domain: str, twins: bool = True) -> dict:
    out = {"lookalike_of": lookalike_of(domain)}
    if twins:
        out["registered_lookalikes"] = await asyncio.to_thread(registered_lookalikes, domain)
    return out


# ---------------------------------------------------------------- shared_trackers


async def _trackers_of(c: httpx.AsyncClient, host: str) -> list[str] | None:
    if (hit := _cache_get(f"trk:{host}")) is not None:
        return hit
    home = await _homepage(c, host)
    if not home or "error" in home:
        return None
    _cache_set(f"trk:{host}", home["trackers"])
    return home["trackers"]


async def shared_trackers(domain: str, ids: list[str] | None = None, reference: dict[str, list[str]] | None = None) -> dict:
    """Compare les identifiants analytics de `domain` à ceux des domaines listés (page d'accueil, cache 7 j)."""
    reg = registrable(domain)
    async with httpx.AsyncClient(headers={"User-Agent": UA}, follow_redirects=True) as c:
        if ids is None:
            ids = await _trackers_of(c, domain)
        if reference is None:
            hosts = sorted({d for d in listed() if registrable(d) != reg})
            sem = asyncio.Semaphore(16)  # registre multi-pays : concurrence bornée, résultats en cache 7 j

            async def one(h: str) -> list[str] | None:
                async with sem:
                    return await _trackers_of(c, h)
            vals = await asyncio.gather(*(one(h) for h in hosts))
            reference = {h: v for h, v in zip(hosts, vals) if v is not None}
    if ids is None:
        return {"ids": None, "matches": [], "compared_with": len(reference)}
    matches = [{"id": i, "domain": h, "label": label_for(h)} for h, v in sorted(reference.items()) for i in ids if i in v]
    return {"ids": ids, "matches": matches, "compared_with": len(reference)}


# ---------------------------------------------------------------- base locale : clonage, amplification


def _host_of(it) -> str | None:
    return (it.urls_canon[0] if it.urls_canon else None) if it.platform == "web" else None


def _is_listed_item(it) -> bool:
    return bool(it.account.known_network or (_host_of(it) and label_for(_host_of(it))))


def cloned_content(domain: str, items: list, threshold: float = 0.8, min_words: int = 30) -> dict:
    """Part des textes de `domain` quasi identiques (MinHash ≥ 0,8) à un texte ANTÉRIEUR d'une source listée."""
    from datasketch import MinHashLSH

    from observer.tools.text import NUM_PERM, minhash, normalize
    reg = registrable(domain)
    mine = [i for i in items if (h := _host_of(i)) and (h == domain or registrable(h) == reg)
            and len(normalize(i.full_text()).split()) >= min_words]
    if not mine:
        return {"n": 0, "cloned": 0, "share": None, "pairs": [], "reason": "no article from this domain in the event data"}
    ref = [i for i in items if _is_listed_item(i) and registrable(_host_of(i) or "") != reg
           and len(normalize(i.full_text()).split()) >= min_words]
    lsh = MinHashLSH(threshold=threshold, num_perm=NUM_PERM)
    hashes = {}
    for r in ref:
        hashes[r.uid] = minhash(r.full_text())
        lsh.insert(r.uid, hashes[r.uid])
    by_uid = {r.uid: r for r in ref}
    pairs = []
    for it in mine:
        m = minhash(it.full_text())
        best = None
        for u in lsh.query(m):
            j = m.jaccard(hashes[u])
            if j >= threshold and by_uid[u].ts <= it.ts and (best is None or j > best[1]):
                best = (u, j)
        if best:
            src = by_uid[best[0]]
            pairs.append({"item": it.uid, "url": it.url, "source_item": src.uid, "source_url": src.url,
                          "source": _host_of(src) or src.account.known_network, "jaccard": round(best[1], 3)})
    return {"n": len(mine), "cloned": len(pairs), "share": round(len(pairs) / len(mine), 3), "pairs": pairs[:10],
            "compared_with": len(ref), "threshold": threshold}


def amplification(domain: str, items: list, clusters: list) -> dict:
    """Le domaine est-il lié par un cluster coordonné (niveau review/priority, ≥ 2 auteurs) de l'événement ?"""
    reg = registrable(domain)
    linking = {i.uid for i in items if any(registrable(u) == reg for u in (i.urls_canon + i.links) if u)}
    hits = [{"cluster": c.id, "level": c.level, "authors": len(c.authors), "platforms": c.platforms}
            for c in clusters if c.level in ("review", "priority") and len(c.authors) >= 2 and linking & set(c.item_uids)]
    return {"items_linking": len(linking), "clusters": hits[:10], "n_clusters": len(hits)}


def ai_text_share(_texts: list[str] | None = None) -> dict:
    return {"share": None, "n": len(_texts or []), "detector": None, "tpr_at_1fpr": None, "reason": AI_REASON}


# ---------------------------------------------------------------- modèle


def feature(key: str, value: float | None, evidence, weights: dict, why: str | None = None) -> dict:
    w, label = weights[key]
    return {"key": key, "label": label, "weight": w, "value": value,
            "contribution": None if value is None else round(w * value, 3), "missing": value is None,
            "evidence": evidence, **({"why_missing": why} if value is None and why else {})}


def band(score: float | None) -> str:
    if score is None:
        return "insufficient_data"
    return "priority" if score >= 70 else "review" if score >= 40 else "organic"


def combine(features: list[dict], bias: float = BIAS) -> dict:
    """Score = σ(β₀ + Σ βᵢxᵢ) × 100 (risque). Cascade : base σ(β₀) puis la part de chaque feature."""
    present = [f for f in features if not f["missing"]]
    missing = [f["key"] for f in features if f["missing"]]
    logit = bias + sum(f["contribution"] for f in present)
    raw = round(100 / (1 + math.exp(-logit)), 1)
    base = 100 / (1 + math.exp(-bias))
    total = sum(f["contribution"] for f in present)
    for f in present:  # points répartis au prorata des logits : indépendant de l'ordre, somme = score - base
        f["points"] = round((raw - base) * f["contribution"] / total, 1) if total else 0.0
    for f in features:
        f.setdefault("points", None)
    abstain = len(missing) > MAX_MISSING
    return {"score": None if abstain else raw, "partial_score": raw, "band": band(None if abstain else raw),
            "abstain": abstain, "missing": missing, "logit": round(logit, 3),
            "base_points": round(100 / (1 + math.exp(-bias)), 1), "bias": bias}


def domain_features(sig: dict, squat: dict, trk: dict, clone: dict, amp: dict, listed: str | None) -> list[dict]:
    W = DOMAIN_WEIGHTS
    reg, crt, wb, home = sig.get("registration"), sig.get("crt"), sig.get("wayback"), sig.get("homepage")
    home_ok = bool(home) and "error" not in home
    # âge : RDAP en priorité, crt.sh en complément
    ages = {k: _days_since(v) for k, v in (("rdap", (reg or {}).get("created")), ("crt.sh", (crt or {}).get("first_cert")))}
    known = [a for a in ages.values() if a is not None]
    young = None if not known else float(min(known) < YOUNG_DAYS)
    no_transp = None if not home_ok else float(not (home["about_link"] or home["legal_link"] or home["authors_marker"]))
    return [
        feature("listed_network", float(bool(listed)), {"list": listed, "lists_frozen": LISTS_FROZEN}, W),
        feature("shared_tracker", None if trk.get("ids") is None else float(bool(trk["matches"])),
                {"ids": trk.get("ids"), "matches": trk.get("matches"), "compared_with": trk.get("compared_with")}, W,
                "home page unreachable: analytics IDs unknown"),
        # borné : x = min(1, part clonée / 20 %) — un seul texte repris sur 1 000 ne pèse presque rien
        feature("cloned_content", None if clone.get("share") is None else round(min(1.0, clone["share"] / CLONE_FULL), 3),
                {k: clone.get(k) for k in ("n", "cloned", "share", "pairs", "compared_with")}, W, clone.get("reason")),
        feature("typosquat", float(bool(squat.get("lookalike_of"))), squat, W),
        feature("young_domain", young, {"registered": (reg or {}).get("created"), "registrar": (reg or {}).get("registrar"),
                                        "first_certificate": (crt or {}).get("first_cert"), "age_days": ages,
                                        "source": (reg or {}).get("source")}, W, "RDAP/WHOIS and crt.sh unavailable"),
        feature("no_transparency", no_transp, {k: (home or {}).get(k) for k in
                                               ("final_url", "via", "snapshot", "about_link", "legal_link",
                                                "authors_marker", "offsite_about_or_legal", "error")}, W,
                "home page unreachable"),
        feature("ai_text_share", None, ai_text_share(), W, AI_REASON),
        feature("few_archives", None if wb is None else float(wb["captures"] < 3), wb, W, "Wayback CDX unavailable"),
        feature("amplified_by_cluster", float(amp["n_clusters"] > 0), amp, W),
        feature("whois_masked", None if reg is None else float(reg["whois_masked"]),
                {"registrant": (reg or {}).get("registrant"), "source": (reg or {}).get("source")}, W,
                "RDAP/WHOIS unavailable"),
    ]


def account_features(its: list, clusters: list) -> list[dict]:
    from observer.api.views import account_flags
    W = ACCOUNT_WEIGHTS
    flags = {f["key"]: f for f in account_flags(its)}
    a = its[0].account
    uids = {i.uid for i in its}
    cited = [(i.uid, u) for i in its for u in i.urls_canon if u and label_for(u)]
    share_cited = len({c[0] for c in cited}) / len(its)
    copied = [c.id for c in clusters if c.kind == "copypasta" and uids & set(c.item_uids) and len(c.authors) >= 2]
    coord = [{"cluster": c.id, "level": c.level, "kind": c.kind} for c in clusters
             if c.level in ("review", "priority") and len(c.authors) >= 2 and uids & set(c.item_uids)]
    new = flags.get("new")
    return [
        feature("listed_network", float("listed" in flags), flags.get("listed"), W),
        feature("cites_listed", round(min(1.0, share_cited / 0.5), 3),
                {"posts": len(its), "posts_citing_listed": len({c[0] for c in cited}),
                 "examples": [{"item": u, "domain": d, "label": label_for(d)} for u, d in cited[:5]]}, W),
        feature("copied_posts", float(bool(copied)), {"copypasta_clusters": copied[:10]}, W),
        feature("in_coordinated_cluster", float(bool(coord)), {"clusters": coord[:10]}, W),
        feature("automated", None if a.automated_declared is None else float(bool(a.automated_declared)),
                flags.get("bot"), W, "platform does not expose an automation label"),
        feature("new_account", None if a.created_at is None else float(bool(new)),
                new or {"created_at": a.created_at.isoformat() if a.created_at else None}, W, "account creation date unknown"),
        feature("low_audience", None if a.followers is None else float(a.followers < 50), {"followers": a.followers}, W,
                "follower count unknown"),
        feature("ai_text_share", None, ai_text_share([i.full_text() for i in its]), W, AI_REASON),
    ]


async def _resolve_event(event: str | None) -> str | None:
    """Événement explicite, sinon le plus récent non archivé."""
    if event:
        return event
    try:
        from observer.core import db
        evs = await db.list_events()
        return evs[0]["slug"] if evs else None
    except Exception:
        return None


async def _event_data(event: str | None) -> tuple[list, list]:
    if not event:
        return [], []
    try:
        from observer.core import db
        return await db.load_items(event, limit=20000), await db.load_clusters(event)
    except Exception:
        return [], []


def _method(weights: dict) -> dict:
    return {"model": "logistic regression, published weights", "formula": "risk = 100 × σ(β₀ + Σ βᵢ·xᵢ)",
            "bias": BIAS, "weights": {k: {"weight": w, "label": l} for k, (w, l) in weights.items()},
            "bands": {"priority": "≥ 70", "review": "40-70", "organic": "< 40"},
            "abstention": f"insufficient data if more than {MAX_MISSING} features are missing",
            "calibration": "none yet: initial weights from SPECS §3bis, to be re-fitted (isotonic) on labelled sets"}


LIMITS = [
    "Prioritises a check, does not convict: a high score means 'look first', never 'propaganda'.",
    "Weights are initial expert values (SPECS §3bis), not yet fitted or calibrated on labelled data.",
    "AI-generated text is not measured: open detectors are unreliable on short French/English texts.",
    "Shared analytics IDs are compared only with listed domains whose home pages we could fetch.",
    "Cloned content and amplification only use the current event's data (one event in base).",
    "Young domains, masked WHOIS and missing about pages are common on legitimate small sites.",
    "Look-alikes are checked against a registry of ~90 major outlets worldwide (data/registry/major_media.yaml).",
    "Lists are frozen on " + LISTS_FROZEN + "; a site absent from them is not 'clean'.",
]


async def provenance_score(target: str, event: str | None = DEFAULT_EVENT, twins: bool = True) -> dict:
    """Fiche de provenance d'une URL, d'un domaine ou d'un compte (`<platform>:<id>`)."""
    kind, value = parse_target(target)
    event = await _resolve_event(event)
    items, clusters = await _event_data(event)
    base = {"target": target, "model_version": MODEL_VERSION, "lists_frozen": LISTS_FROZEN, "event": event,
            "computed_at": NOW().isoformat(), "disclaimer": "Prioritises a check, does not convict.", "limits": LIMITS}
    if kind == "account":
        its = [i for i in items if i.uid == value]
        if its:  # uid d'un item → son auteur
            its = [i for i in items if i.author_pseudo == its[0].author_pseudo and i.platform == its[0].platform]
        else:
            plat, aid = value.split(":", 1)
            its = [i for i in items if i.platform == plat and i.author_pseudo == aid]
        if not its:
            return {**base, "kind": "account", "error": "account not found in the event data", "score": None,
                    "band": "insufficient_data", "abstain": True, "features": [], "method": _method(ACCOUNT_WEIGHTS)}
        its.sort(key=lambda i: i.ts)
        from observer.api.views import account_label
        feats = account_features(its, clusters)
        return {**base, "kind": "account", "subject": account_label(its[0]), "platform": its[0].platform,
                "account_id": its[0].author_pseudo, **combine(feats), "features": feats, "method": _method(ACCOUNT_WEIGHTS)}

    sig, squat = await asyncio.gather(site_signals(value), typosquat(value, twins=twins))
    home = sig.get("homepage") or {}
    trk = await shared_trackers(value, ids=None if "error" in home or not home else home["trackers"])
    clone = cloned_content(value, items)
    amp = amplification(value, items, clusters)
    listed = label_for(value)
    feats = domain_features(sig, squat, trk, clone, amp, listed)
    return {**base, "kind": "domain", "subject": value, "registrable": registrable(value), **combine(feats),
            "features": feats, "signals": sig, "method": _method(DOMAIN_WEIGHTS)}
