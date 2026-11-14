from datetime import datetime, timedelta, timezone

from observer.core.models import ContentItem
from observer.tools.diffusion import flows, hops

T0 = datetime(2026, 11, 14, 17, 23, 47, tzinfo=timezone.utc)
TXT = "À Paris, une manifestation contre la hausse des prix a dégénéré en affrontements avec les forces de l'ordre ce soir"


def it(uid, platform, author, minutes, text=TXT, url=None, canon=None, links=None, ts=None):
    return ContentItem(platform=platform, post_id=uid, ts=ts or T0 + timedelta(minutes=minutes), author_pseudo=author,
                       text=text, url=url, urls_canon=canon or [], links=links or [])


def test_proven_relay_from_telegram_channel():
    tg = it("1", "telegram", "chan", 0, url="https://t.me/RUSpresse/31576", canon=["t.me/RUSpresse"])
    pv = it("2", "web", "pravda", 12.5, text=TXT + " t.me/RUSpresse", canon=["france.news-pravda.com"])
    hs = hops([tg, pv], [])
    assert len(hs) == 1 and hs[0]["kind"] == "proven" and hs[0]["delay_min"] == 12.5
    assert "ruspresse" in hs[0]["why"]


def test_inferred_hop_and_flow_summary():
    a = it("1", "web", "site", 0, canon=["example.fr"])
    b = it("2", "bluesky", "user", 600)
    hs = hops([a, b], [])
    assert hs[0]["kind"] == "inferred"
    f = flows(hs)[0]
    assert (f["from"], f["to"], f["n"], f["slow_share"]) == ("web", "bluesky", 1, 1.0)


def test_rounded_timestamps_and_same_author_are_ignored():
    rounded = it("1", "web", "site", 0, ts=datetime(2026, 11, 14, 7, 0, 0, tzinfo=timezone.utc))
    later = it("2", "bluesky", "user", 600)
    assert hops([rounded, later], []) == []                     # date arrondie : délai inconnu
    same = [it("3", "web", "x", 0), it("4", "bluesky", "x", 5)]
    assert hops(same, []) == []                                 # même compte : pas une reprise
