from observer.core import models
from observer.core.settings import settings


def test_rekey_keeps_accounts_consistent_and_hides_salt(monkeypatch):
    s = settings()
    monkeypatch.setattr(s, "pseudo_key", "")
    legacy = models.pseudonymize("bluesky", "did:plc:abc")          # ancien calcul (sel seul)
    monkeypatch.setattr(s, "pseudo_key", "secret-key-for-test")
    new = models.pseudonymize("bluesky", "did:plc:abc")             # nouvelle collecte
    assert new == models.rekey(legacy)                              # = pseudonyme migré : même compte
    assert new != legacy and len(new) == 16
    monkeypatch.setattr(s, "pseudo_key", "another-key")
    assert models.pseudonymize("bluesky", "did:plc:abc") != new     # sans la clé, impossible de recalculer
