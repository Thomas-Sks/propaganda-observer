from datetime import datetime, timedelta, timezone

from observer.core.models import AccountMeta, ContentItem
from observer.tools.coordination import actions, build, coordination_interval

T0 = datetime(2026, 11, 3, 12, 3, 17, tzinfo=timezone.utc)
A = "Grand rassemblement samedi place de la République, ils veulent nous faire taire mais nous serons des milliers"
B = "Le gouvernement prépare un décret pour interdire les manifestations, partagez avant que ce soit supprimé partout"


def it(uid, author, text, sec, links=None, tags=None):
    return ContentItem(platform="bluesky", post_id=uid, ts=T0 + timedelta(seconds=sec), author_pseudo=author, text=text,
                       links=links or [], hashtags=tags or [], account=AccountMeta())


def acc(items):
    return {i.author_pseudo: {"label": i.author_pseudo, "platform": "bluesky", "flags": []} for i in items}


def test_pair_acting_twice_is_a_strong_link_in_one_community():
    items = [it("1", "a", A, 0), it("2", "b", A, 20), it("3", "a", B, 90000), it("4", "b", B, 90015),
             it("5", "c", A, 50000)]  # c copie aussi, mais 14 h plus tard : pas coordonné
    out = build(items, acc(items))
    e = {(x["source"], x["target"]): x for x in out["edges"]}
    assert e[("a", "b")]["weight"] == 2 and e[("a", "b")]["strong"]
    assert "c" not in {n["id"] for n in out["nodes"]}
    assert out["communities"][0]["members"] == ["a", "b"] or set(out["communities"][0]["members"]) == {"a", "b"}


def test_window_is_learnt_and_bounded():
    items = [it(str(k), f"u{k}", A, k * 5) for k in range(10)]
    w, n = coordination_interval(actions(items, {}))
    assert 60 <= w <= 600 and n == 9


def test_shared_link_and_hashtag_combination_are_actions():
    items = [it("1", "a", "x", 0, links=["https://site.example/p?utm_source=t"], tags=["Greve", "17nov"]),
             it("2", "b", "y", 30, links=["https://site.example/p"], tags=["greve", "17nov"])]
    keys = set(actions(items, {}))
    assert "link:https://site.example/p" in keys and "hashtags:17nov,greve" in keys
