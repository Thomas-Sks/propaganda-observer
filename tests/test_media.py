"""Tests hors réseau de observer.tools.media : dHash, liens frame-phash, garde de budget."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from observer.core import llm
from observer.core.models import ContentItem
from observer.tools import media
from observer.tools.links import find_link_shares


def _item(uid: str, author: str, **kw) -> ContentItem:
    p, pid = uid.split(":")
    return ContentItem(platform=p, post_id=pid, ts=datetime(2026, 11, 1, tzinfo=timezone.utc),
                       author_pseudo=author, url=f"https://example.org/{pid}", **kw)


def test_dhash_gradient():
    # Chaque ligne décroît de gauche à droite : tous les bits à 1
    px = [255 - 20 * c for r in range(8) for c in range(9)]
    assert media.dhash_bits(px) == "ffffffffffffffff"
    # Croissante : tous à 0 ; image uniforme : 0 aussi (et jugée non informative)
    assert media.dhash_bits([20 * c for r in range(8) for c in range(9)]) == "0" * 16
    assert not media.informative("0" * 16)
    assert not media.informative("f" * 16)
    assert media.informative("a5a5a5a5a5a5a5a5")


def test_dhash_bytes_and_pattern():
    # Une ligne sur deux décroissante → octets ff/00 alternés
    px = bytes((200 - 10 * c) if r % 2 == 0 else (10 * c) for r in range(8) for c in range(9))
    assert media.dhash_bits(px) == "ff00ff00ff00ff00"


def test_phash_links_and_link_shares():
    a = _item("tiktok:1", "auteurA", links=["tiktok-sound:9"])
    b = _item("youtube:2", "auteurB")
    media.add_links(a, ["a5a5a5a5a5a5a5a5", "0f0f0f0f0f0f0f0f"])
    media.add_links(b, ["a5a5a5a5a5a5a5a5"])
    assert a.links == ["tiktok-sound:9", "frame-phash:a5a5a5a5a5a5a5a5", "frame-phash:0f0f0f0f0f0f0f0f"]
    media.add_links(a, ["a5a5a5a5a5a5a5a5"])  # remplacement idempotent
    assert a.links == ["tiktok-sound:9", "frame-phash:a5a5a5a5a5a5a5a5"]
    shares = find_link_shares([a, b])
    phash = [c for c in shares if c.evidence[0].detail["url"].startswith("frame-phash:")]
    assert len(phash) == 1 and set(phash[0].item_uids) == {"tiktok:1", "youtube:2"}
    assert phash[0].platforms == ["tiktok", "youtube"]


def test_pick_priority_and_filters():
    its = [_item("youtube:a", "x", metrics={"view_count": 10}),
           _item("youtube:b", "x", metrics={"view_count": 1000}),
           _item("tiktok:c", "x", metrics={"playCount": 5}),
           _item("youtube:d", "x", transcript=""),  # déjà traité
           _item("web:e", "x"),  # pas une vidéo
           _item("instagram:f", "x", format="post"),
           _item("youtube:g", "x", relevance=0.1, metrics={"view_count": 10**6})]  # hors sujet
    got = [i.uid for i in media.pick(its, 10, priority_uids={"tiktok:c"}, min_relevance=0.3)]
    assert got == ["tiktok:c", "youtube:b", "youtube:a"]


def test_budget_guard_transcribe(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(llm, "remaining", lambda: 0.0)
    monkeypatch.setattr(llm, "spent", lambda: 5.0)
    called = []
    monkeypatch.setattr(llm, "openai_client", lambda: called.append(1))
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")
    with pytest.raises(llm.BudgetExceeded):
        media.transcribe(f)
    assert not called  # aucun appel réseau


def test_budget_guard_enrich(monkeypatch):
    class R:
        def smembers(self, k): return set()
        def sadd(self, *a): pass
        def expire(self, *a): pass
    monkeypatch.setattr(llm, "_r", lambda: R())
    monkeypatch.setattr(llm, "remaining", lambda: 0.0)
    monkeypatch.setattr(media, "fetch_media", lambda it: pytest.fail("ne doit rien télécharger"))
    done, stats = media.enrich([_item("youtube:a", "x")], max_items=5)
    assert done == [] and stats == []
