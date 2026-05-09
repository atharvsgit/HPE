from decimal import Decimal

from app.daemon.evaluator import evaluate_observed_value
from app.models.requests import ExpectedResult


def test_zero_violations_passes_when_zero() -> None:
    expected = ExpectedResult(type="zero_violations")

    assert evaluate_observed_value(Decimal("0"), expected) == "PASS"


def test_zero_violations_fails_when_positive() -> None:
    expected = ExpectedResult(type="zero_violations")

    assert evaluate_observed_value(Decimal("1"), expected) == "FAIL"


def test_min_threshold() -> None:
    expected = ExpectedResult(type="min_threshold", value=Decimal("1000"))

    assert evaluate_observed_value(Decimal("1200"), expected) == "PASS"
    assert evaluate_observed_value(Decimal("999"), expected) == "FAIL"


def test_max_threshold() -> None:
    expected = ExpectedResult(type="max_threshold", value=Decimal("25"))

    assert evaluate_observed_value(Decimal("25"), expected) == "PASS"
    assert evaluate_observed_value(Decimal("26"), expected) == "FAIL"


def test_equals() -> None:
    expected = ExpectedResult(type="equals", value=Decimal("42"))

    assert evaluate_observed_value(Decimal("42"), expected) == "PASS"
    assert evaluate_observed_value(Decimal("43"), expected) == "FAIL"
