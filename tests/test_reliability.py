import math

import pytest

from eval.metrics import confusion, evaluate, wilson


def test_wilson_reference_values():
    # Valeurs de référence (Newcombe 1998) : 81/263 → [0.2553, 0.3662]
    lo, hi = wilson(81, 263)
    assert lo == pytest.approx(0.2553, abs=1e-3) and hi == pytest.approx(0.3662, abs=1e-3)


def test_wilson_edges():
    assert wilson(0, 0) is None
    lo, hi = wilson(0, 50)
    assert lo == pytest.approx(0.0, abs=1e-12) and 0.05 < hi < 0.08  # zéro observé ≠ zéro garanti
    lo, hi = wilson(50, 50)
    assert hi == 1.0 and 0.92 < lo < 0.95


def test_wilson_contains_point_estimate():
    for k, n in [(1, 10), (5, 7), (99, 1000)]:
        lo, hi = wilson(k, n)
        assert lo <= k / n <= hi


def test_confusion_and_metrics():
    y = [1, 1, 1, 1, 0, 0, 0, 0, 0, 0]
    p = [1, 1, 1, 0, 1, 0, 0, 0, 0, 0]
    assert confusion(y, p) == {"tp": 3, "fp": 1, "tn": 5, "fn": 1}
    m = evaluate(y, p)
    assert m["precision"] == 0.75 and m["recall"] == 0.75
    assert m["fpr"] == pytest.approx(1 / 6, abs=1e-4)
    assert m["f1"] == 0.75
    assert m["positives"] == 4 and m["negatives"] == 6
    assert m["fpr_ci"][0] <= m["fpr"] <= m["fpr_ci"][1]


def test_metrics_undefined_without_predictions():
    m = evaluate([1, 0], [0, 0])
    assert m["precision"] is None and m["recall"] == 0.0 and m["fpr"] == 0.0
    assert not math.isnan(m["fpr_ci"][1])


def test_confusion_length_mismatch():
    with pytest.raises(ValueError):
        confusion([1], [1, 0])
