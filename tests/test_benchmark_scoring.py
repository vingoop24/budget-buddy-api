from datetime import date

from benchmark.scoring import field_correct, score


def test_merchant_matching_ignores_case_punctuation_and_store_numbers():
    assert field_correct("merchant", "TRADER JOE'S #552", "Trader Joe's")
    assert not field_correct("merchant", "Whole Foods", "Trader Joe's")


def test_amount_tolerance_and_dates():
    assert field_correct("amount", 12.749, "12.75")
    assert not field_correct("amount", 12.73, "12.75")
    assert field_correct("date", date(2026, 11, 5), "2026-11-05")


def test_blank_answers():
    # Not on the receipt: only a blank answer is right.
    assert field_correct("amount", None, "")
    assert not field_correct("amount", 3.0, "")
    # On the receipt but left blank: wrong.
    assert not field_correct("amount", None, "12.75")


def test_all_correct_uses_the_four_success_fields():
    expected = {"merchant": "Cafe", "amount": "7.75", "date": "2026-11-05", "category": "Food & Dining", "currency": "USD"}
    got = {"merchant": "CAFE", "amount": 7.75, "date": date(2026, 11, 5), "category": "Food & Dining", "currency": None}
    s = score(got, expected)
    assert s["currency"] is False and s["all_correct"] is True  # currency isn't one of the four
