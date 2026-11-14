from datetime import datetime, timedelta, timezone

from observer.api.views import _accounts
from observer.core.models import AccountMeta, Cluster, ContentItem
from observer.tools.suspects import rank

T0 = datetime(2026, 11, 3, 12, 3, 17, tzinfo=timezone.utc)
TXT_A = "Tout le monde dans la rue samedi, ils ne nous écouteront jamais si on ne bloque pas tout le pays maintenant"
TXT_B = "La police a reçu l'ordre de ne plus protéger les quartiers, les émeutiers ont carte blanche ce soir partout"


def it(uid, author, text, minutes, created_days=400):
    return ContentItem(platform="bluesky", post_id=uid, ts=T0 + timedelta(minutes=minutes), author_pseudo=author,
                       text=text, account=AccountMeta(created_at=T0 - timedelta(days=created_days), followers=500))


def cl(cid, its):
    return Cluster(id=cid, kind="copypasta", item_uids=[i.uid for i in its], platforms=["bluesky"],
                   authors=sorted({i.author_pseudo for i in its}), first_ts=its[0].ts, last_ts=its[-1].ts,
                   level="review")


def test_recurring_tandem_ranks_above_one_off_and_organic():
    s1 = [it("1", "a", TXT_A, 0), it("2", "b", TXT_A, 3), it("3", "c", TXT_A, 6), it("4", "lone", TXT_A, 600)]
    s2 = [it("5", "a", TXT_B, 2000), it("6", "b", TXT_B, 2004), it("7", "d", TXT_B, 2007)]
    items = s1 + s2
    clusters = [cl("s1", s1), cl("s2", s2)]
    out = rank(items, clusters, _accounts(items, clusters))
    ids = [r["id"] for r in out]
    assert ids[:2] in (["a", "b"], ["b", "a"])          # tandem a–b retrouvé dans 2 narratifs
    assert "lone" not in ids                            # même texte mais 10 h plus tard : pas de rafale
    top = out[0]
    assert any(e["key"] == "recurring_tandem" for e in top["evidence"]) and top["level"] == "likely"


def test_wire_quotes_are_not_bursts():
    q = "« Nous ne céderons pas », a déclaré le ministre de l'Intérieur lors d'une conférence de presse ce matin à Paris"
    its = [it(str(k), f"m{k}", q, k) for k in range(5)]
    out = rank(its, [cl("w", its)], _accounts(its, [cl("w", its)]))
    assert out == []
