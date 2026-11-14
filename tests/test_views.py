from datetime import datetime, timedelta, timezone

from observer.api.views import _accounts, _item_stance, account_flags
from observer.core.models import AccountMeta, Cluster, ContentItem, Signal

T0 = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)


def it(uid, author, platform="bluesky", **acc):
    return ContentItem(platform=platform, post_id=uid, ts=T0, author_pseudo=author, text="x", account=AccountMeta(**acc))


def cl(cid, uids, authors, stance):
    return Cluster(id=cid, kind="semantic", item_uids=uids, platforms=["bluesky"], authors=authors, first_ts=T0,
                   last_ts=T0, signals=[Signal(name=f"stance_{stance}", value=stance, explanation="")])


def test_item_inherits_story_stance():
    st = _item_stance([cl("a", ["bluesky:1"], ["u1"], "promotes"), cl("b", ["bluesky:2"], ["u2"], "debunks")])
    assert st == {"bluesky:1": "promotes", "bluesky:2": "debunks"}


def test_account_flags_new_listed_bot():
    items = [it("1", "u1", created_at=T0 - timedelta(days=5), automated_declared=True, known_network="Pravda")]
    keys = {f["key"] for f in account_flags(items)}
    assert keys == {"new", "bot", "listed"}


def test_accounts_aggregate_stories_and_risk():
    items = [it("1", "u1", created_at=T0 - timedelta(days=3)), it("2", "u2")]
    acc = _accounts(items, [cl("a", ["bluesky:1", "bluesky:2"], ["u1", "u2"], "promotes")])
    assert acc["u1"]["risk"] == "medium" and acc["u1"]["stories"] == ["a"] and acc["u2"]["risk"] == "none"


def test_robust_peaks():
    from observer.tools.bursts import robust_peaks
    s = [(f"d{i}", v) for i, v in enumerate([3, 4, 2, 5, 40, 4, 3])]
    peaks = robust_peaks(s)
    assert [p["period"] for p in peaks] == ["d4"]
