"""Score de provenance : contributions, abstention, parsing des preuves. Réseau et base entièrement simulés."""
from datetime import UTC, datetime, timedelta

import pytest

from observer.core.models import AccountMeta, ContentItem
from observer.tools import provenance as P

NOW = datetime(2026, 11, 14, tzinfo=UTC)
LONG = " ".join(f"mot{k}" for k in range(60))


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setattr(P, "NOW", lambda: NOW)
    monkeypatch.setattr(P, "_cache_get", lambda k: None)
    monkeypatch.setattr(P, "_cache_set", lambda *a, **k: None)

    async def no_event(e):
        return e or "test-event"
    monkeypatch.setattr(P, "_resolve_event", no_event)


def sig(created="2026-11-03T09:05:23Z", masked=True, home=True, captures=1, about=None):
    return {"registration": {"created": created, "registrar": "Spaceship", "registrant": None, "whois_masked": masked,
                             "source": "rdap"} if created else None,
            "crt": None, "wayback": {"captures": captures} if captures is not None else None,
            "homepage": {"final_url": "https://x/", "about_link": about, "legal_link": None, "authors_marker": None,
                         "trackers": ["UA-1"]} if home else None}


def mock_network(monkeypatch, s, squat=None, trk=None):
    async def site(_d, refresh=False):
        return s

    async def ts(_d, twins=True):
        return {"lookalike_of": squat}

    async def st(_d, ids=None, reference=None):
        return trk if trk is not None else {"ids": ids, "matches": [], "compared_with": 3}

    async def ev(_e):
        return [], []
    monkeypatch.setattr(P, "site_signals", site)
    monkeypatch.setattr(P, "typosquat", ts)
    monkeypatch.setattr(P, "shared_trackers", st)
    monkeypatch.setattr(P, "_event_data", ev)


def test_parse_target():
    assert P.parse_target("https://www.LeMonde.fr/a/b?x=1") == ("domain", "lemonde.fr")
    assert P.parse_target("francais.news-pravda.com") == ("domain", "francais.news-pravda.com")
    assert P.parse_target("bluesky:abc123") == ("account", "bluesky:abc123")


def test_label_for_no_suffix_false_positive():
    assert P.label_for("fart.com") is None
    assert P.label_for("francais.news-pravda.com")


def test_combine_sigmoid_and_waterfall():
    feats = [P.feature("typosquat", 1.0, {}, P.DOMAIN_WEIGHTS), P.feature("young_domain", 1.0, {}, P.DOMAIN_WEIGHTS),
             P.feature("whois_masked", 0.0, {}, P.DOMAIN_WEIGHTS)]
    out = P.combine(feats)
    assert out["score"] == pytest.approx(50.0)  # -3 + 2 + 1 = 0 → 50 %
    assert out["band"] == "review" and not out["abstain"]
    # la cascade part de la base σ(-3) et arrive exactement au score
    assert out["base_points"] + sum(f["points"] for f in feats) == pytest.approx(out["score"], abs=0.2)
    assert feats[0]["points"] == pytest.approx(2 * feats[1]["points"], abs=0.1) and feats[2]["points"] == 0


def test_abstention_when_more_than_three_missing():
    W = P.DOMAIN_WEIGHTS
    feats = [P.feature(k, None, {}, W, "x") for k in ("shared_tracker", "cloned_content", "ai_text_share", "few_archives")]
    feats.append(P.feature("listed_network", 1.0, {}, W))
    out = P.combine(feats)
    assert out["abstain"] and out["score"] is None and out["band"] == "insufficient_data"
    assert out["partial_score"] == pytest.approx(50.0)
    assert P.combine(feats[1:])["abstain"] is False  # 3 manquantes : on score encore


async def test_fake_lookalike_site_scores_high(monkeypatch):
    mock_network(monkeypatch, sig(), squat={"media": "washingtonexaminer.com", "method": "affix", "detail": "the"})
    r = await P.provenance_score("https://thewashingtonexaminer.net/story")
    by = {f["key"]: f for f in r["features"]}
    assert by["typosquat"]["contribution"] == 2.0 and by["young_domain"]["value"] == 1.0
    assert by["no_transparency"]["value"] == 1.0 and by["few_archives"]["value"] == 1.0
    assert by["ai_text_share"]["missing"] and "not measured" in by["ai_text_share"]["why_missing"]
    # -3 + 2 + 1 + 0.8 + 0.5 + 0.3 = 1.6 → 83,2
    assert r["score"] == pytest.approx(83.2, abs=0.1) and r["band"] == "priority"
    assert r["model_version"] and r["disclaimer"].startswith("Prioritises")


async def test_established_media_scores_low(monkeypatch):
    mock_network(monkeypatch, sig(created="2005-08-02T14:16:36Z", masked=False, captures=50, about="/qui-sommes-nous"))
    r = await P.provenance_score("lemonde.fr")
    assert r["score"] < 10 and r["band"] == "organic"
    assert all(f["contribution"] in (0, None) for f in r["features"])


async def test_unreachable_site_abstains(monkeypatch):
    mock_network(monkeypatch, sig(created=None, home=False, captures=None))
    r = await P.provenance_score("unknown-site.xyz")
    assert r["abstain"] and r["score"] is None
    assert {"young_domain", "no_transparency", "few_archives", "whois_masked"} <= set(r["missing"])


def test_shared_tracker_is_conclusive():
    s = sig(created="2010-01-01T00:00:00Z", masked=False, captures=50, about="/about")
    trk = {"ids": ["UA-123"], "matches": [{"id": "UA-123", "domain": "rt.com", "label": "x"}], "compared_with": 5}
    feats = P.domain_features(s, {"lookalike_of": None}, trk, {"share": None, "reason": "none"},
                              {"n_clusters": 0}, None)
    out = P.combine(feats)
    assert out["score"] == pytest.approx(50.0)  # -3 + 3


def test_parse_homepage_internal_links_and_trackers():
    html = ('<a href="/about-us">About</a><a href="https://real-media.com/privacy">Privacy</a>'
            '<a href="/news/midterms-recap">Midterms</a><script>gtag("config","G-AB12CD34EF")</script>'
            '<ins data-ad-client="ca-pub-1234567890123456"></ins> UA-555555-2 GTM-ABC123')
    h = P.parse_homepage(html, "https://fake-media.net/")
    assert h["about_link"] == "https://fake-media.net/about-us"
    assert h["legal_link"] is None and h["offsite_about_or_legal"] == ["https://real-media.com/privacy"]
    assert h["trackers"] == ["G-AB12CD34EF", "GTM-ABC123", "UA-555555", "pub-1234567890123456"]


def test_parse_rdap_and_whois():
    rd = P.parse_rdap({"events": [{"eventAction": "registration", "eventDate": "2026-11-03T09:05:23Z"}],
                       "entities": [{"roles": ["registrar"], "vcardArray": ["vcard", [["fn", {}, "text", "Spaceship"]]]}]})
    assert rd["created"].startswith("2026-11-03") and rd["whois_masked"] and rd["registrar"] == "Spaceship"
    wh = P.parse_whois_text("domain: X.SU\nperson:        Private Person\nregistrar:     RUCENTER-SU\ncreated: 2017-06-30T07:44:10Z\n")
    assert wh["created"] == "2017-06-30T07:44:10Z" and wh["whois_masked"]


def test_lookalike_of_uses_global_registry(monkeypatch):
    reg = {"washingtonexaminer.com": {"domain": "washingtonexaminer.com", "name": "WE", "country": "US"},
           "thehindu.com": {"domain": "thehindu.com", "name": "The Hindu", "country": "IN"},
           "lemonde.fr": {"domain": "lemonde.fr", "name": "Le Monde", "country": "FR"}}
    monkeypatch.setattr(P, "media_registry", lambda: reg)
    assert P.lookalike_of("thewashingtonexaminer.net")["method"] == "affix"
    assert P.lookalike_of("thehindu-in.com")["detail"] == "'in' added to 'thehindu'"
    assert P.lookalike_of("lemonde.ltd")["method"] == "tld-swap"
    assert P.lookalike_of("lemonde.fr") is None and P.lookalike_of("example.org") is None


def test_media_registry_file_is_global():
    P.media_registry.cache_clear()
    reg = P.media_registry()
    assert len(reg) >= 80 and len({e["country"] for e in reg.values()}) >= 25


def _web(uid, host, ts, text, known=None):
    return ContentItem(platform="web", post_id=uid, ts=ts, author_pseudo=host, text=text, urls_canon=[host],
                       account=AccountMeta(known_network=known))


def test_cloned_content_only_counts_later_copies():
    t0 = NOW - timedelta(days=2)
    items = [_web("src", "fr.news-pravda.com", t0, LONG, known="Pravda"),
             _web("copy", "copycat.fr", t0 + timedelta(hours=1), LONG),
             _web("earlier", "victim.fr", t0 - timedelta(hours=1), LONG)]
    c = P.cloned_content("copycat.fr", items)
    assert c["cloned"] == 1 and c["share"] == 1.0 and c["pairs"][0]["source_item"] == "web:src"
    assert P.cloned_content("victim.fr", items)["cloned"] == 0  # publié AVANT la source listée : victime, pas clone
    assert P.cloned_content("absent.fr", items)["share"] is None


async def test_account_target(monkeypatch):
    t = NOW - timedelta(days=1)
    items = [ContentItem(platform="bluesky", post_id=str(k), ts=t, author_pseudo="acc1", text="x",
                         urls_canon=["rt.com"] if k < 2 else [],
                         account=AccountMeta(created_at=t - timedelta(days=3), followers=10, automated_declared=False))
             for k in range(4)]

    async def ev(_e):
        return items, []
    monkeypatch.setattr(P, "_event_data", ev)
    r = await P.provenance_score("bluesky:acc1")
    by = {f["key"]: f for f in r["features"]}
    assert r["kind"] == "account" and not r["abstain"]
    assert by["cites_listed"]["value"] == 1.0 and by["new_account"]["value"] == 1.0 and by["low_audience"]["value"] == 1.0
    # le uid d'un item mène au même compte
    assert (await P.provenance_score("bluesky:0"))["account_id"] == "acc1"
    assert (await P.provenance_score("bluesky:nobody"))["error"]


def test_generic_brand_needs_dnstwist_permutation(monkeypatch):
    reg = {"pravda.com.ua": {"domain": "pravda.com.ua", "generic": True}}
    monkeypatch.setattr(P, "media_registry", lambda: reg)
    assert P.lookalike_of("news-pravda.com") is None and P.lookalike_of("pravda.ru") is None
