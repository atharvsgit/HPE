from decimal import Decimal

from app.models.requests import ExpectedResult


def evaluate_observed_value(observed_value: Decimal, expected: ExpectedResult) -> str:
    match expected.type:
        case "zero_violations":
            return "PASS" if observed_value == Decimal("0") else "FAIL"
        case "min_threshold":
            return "PASS" if observed_value >= expected.decimal_value else "FAIL"
        case "max_threshold":
            return "PASS" if observed_value <= expected.decimal_value else "FAIL"
        case "equals":
            return "PASS" if observed_value == expected.decimal_value else "FAIL"

    raise ValueError(f"Unsupported expected result type: {expected.type}")
