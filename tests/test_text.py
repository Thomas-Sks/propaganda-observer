from datetime import datetime, timedelta, timezone

from observer.core.models import ContentItem
from observer.tools.text import find_copypasta, normalize

T0 = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
BASE = "Le gouvernement cache la vérité sur les violences policières pendant la manifestation de samedi à Paris"


def item(i, text, platform="x", author=None, minutes=0):
    return ContentItem(platform=platform, post_id=str(i), ts=T0 + timedelta(minutes=minutes),
                       author_pseudo=author or f"a{i}", text=text)


def test_normalize_strips_noise():
    assert normalize("Vérité!! https://x.co/a #Manif @bob") == "verite"


def test_detects_cross_platform_copypasta():
    items = [item(1, BASE, "x"), item(2, BASE + " !!!", "tiktok"), item(3, "RT " + BASE, "youtube"),
             item(4, "Belle journée au marché, les tomates sont enfin de saison et pas chères du tout")]
    clusters = find_copypasta(items)
    assert len(clusters) == 1
    c = clusters[0]
    assert set(c.item_uids) == {"x:1", "tiktok:2", "youtube:3"}
    assert c.platforms == ["tiktok", "x", "youtube"]
    assert c.evidence and all(e.kind == "near_duplicate_text" for e in c.evidence)


def test_requires_distinct_authors():
    items = [item(i, BASE, author="same") for i in range(5)]
    assert find_copypasta(items) == []


def test_short_texts_ignored():
    items = [item(i, "On lâche rien") for i in range(5)]
    assert find_copypasta(items) == []


def test_deterministic():
    items = [item(i, BASE + (" vraiment" if i % 2 else "")) for i in range(6)]
    assert [c.model_dump() for c in find_copypasta(items)] == [c.model_dump() for c in find_copypasta(items)]


def test_canonical_url_and_link_shares():
    from observer.tools.links import canonical_url, find_link_shares
    assert canonical_url("https://www.Liberation.fr/a/b/?utm_source=x&id=3#top") == "https://liberation.fr/a/b?id=3"
    assert canonical_url("https://youtu.be/abc") == canonical_url("https://www.youtube.com/watch?v=abc&t=10")
    its = [ContentItem(platform="bluesky", post_id=str(k), ts=T0 + timedelta(minutes=k), author_pseudo=f"u{k}",
                       links=["https://liberation.fr/a"]) for k in range(3)]
    cl = find_link_shares(its)
    assert len(cl) == 1 and cl[0].kind == "link" and len(cl[0].authors) == 3


def test_quoted_or_wire_detection():
    from observer.tools.stories import is_quoted_or_wire
    assert is_quoted_or_wire("Official: «We will open the border crossings tomorrow at 8 am for all civilians»")
    assert is_quoted_or_wire("Le ministre a déclaré : \"nous ne céderons pas sur la réforme des retraites cette année\"")
    assert is_quoted_or_wire("Floods hit the region overnight (AFP) — Lemonde")
    assert not is_quoted_or_wire("Le gouvernement cache la vérité sur les violences policières pendant la manifestation")
