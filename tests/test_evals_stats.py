import pytest

from signal_engine.evals import judges_suite as js
from signal_engine.evals.stats import kendall_tau, weighted_rate, wilson


def test_wilson_bound_44_of_50_passes_and_43_fails():
    assert wilson(44, 50)[0] == pytest.approx(0.762, abs=0.002) and wilson(44, 50)[0] >= 0.75
    assert wilson(43, 50)[0] == pytest.approx(0.738, abs=0.002) and wilson(43, 50)[0] < 0.75
    assert wilson(0, 0) == (None, None)


def test_weighted_rate_uses_effective_sample_size():
    rate, n_eff, lo, hi = weighted_rate([(True, 1.0), (False, 3.0)])
    assert rate == 0.25 and n_eff == pytest.approx(16 / 10) and lo < 0.25 < hi
    assert weighted_rate([])[0] is None
    assert weighted_rate([(True, 2.0)] * 4)[1] == pytest.approx(4)  # equal weights: effective n is the count


def test_kendall_tau_on_small_rankings():
    assert kendall_tau(["a", "b", "c"], ["a", "b", "c"]) == 1.0
    assert kendall_tau(["a", "b", "c"], ["c", "b", "a"]) == -1.0
    assert kendall_tau(["a", "b", "c", "d"], ["a", "c", "b", "d"]) == pytest.approx(4 / 6)
    assert kendall_tau(["a", "b"], ["b", "x"]) is None  # one shared id


def labels(n_pass_ok, n_fail_ok, n=50):
    """n human passes (judge agrees on the first n_pass_ok) and n human fails (judge agrees on the first n_fail_ok)."""
    return ([("pass", "pass" if i < n_pass_ok else "fail", 1.0, f"2026-11-01T00:{i:02d}") for i in range(n)]
            + [("fail", "fail" if i < n_fail_ok else "pass", 1.0, f"2026-11-01T00:{i:02d}") for i in range(n)])


def test_trusted_needs_44_of_50_on_both_classes():
    assert js.qualify_state(labels(44, 44))[0] == "trusted"
    assert js.qualify_state(labels(43, 50))[0] == "calibrating"
    assert js.qualify_state(labels(50, 43))[0] == "calibrating"


def test_too_few_labels_never_trust():
    assert js.qualify_state(labels(49, 49, n=49))[0] == "calibrating"
    assert js.qualify_state([])[0] == "calibrating"


def test_revocation_uses_the_upper_bound_so_one_bad_week_does_not_flap():
    assert js.qualify_state(labels(40, 50), "trusted")[0] == "trusted"   # 0.80 point, upper bound above 0.75
    assert js.qualify_state(labels(30, 50), "trusted")[0] == "revoked"   # upper bound below 0.75
    assert js.qualify_state(labels(30, 50), "revoked")[0] == "revoked"
    assert js.qualify_state(labels(46, 46), "revoked")[0] == "trusted"   # re-qualifies
