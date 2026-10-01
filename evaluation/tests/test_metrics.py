"""Unit tests for the metric functions: hand-built engine results with known right and wrong answers."""

from decimal import Decimal

import pytest

from evalkit.cases import Case
from evalkit.gateway import load_fixture
from evalkit.metrics import (
    availability_claim,
    checks_for_case,
    evaluate,
    final_order_fields,
    flag_stats,
    numbers_in,
    order_field_matches,
    summarize,
)
from evalkit.runner import CaseResult, TurnResult

FIX = load_fixture()


def turn(reply="", intent="other", flagged=False, reason=None, suggested=(), ready=None, missing=(), pending=None, style="english") -> TurnResult:
    return TurnResult("msg", reply, intent, 0.9, style, flagged, reason, None, list(suggested), ready, list(missing), pending, 0.0)


def case(labels, language="english", type_="intent", messages=("m",), cid="c1") -> Case:
    return Case(cid, language, type_, list(messages), labels)


def result(c: Case, *turns: TurnResult, error=None) -> CaseResult:
    return CaseResult(c, list(turns), error=error)


def ok_metrics(r: CaseResult, metric: str) -> list[bool]:
    return [c.ok for c in checks_for_case(r, FIX) if c.metric == metric]


# ---------------------------------------------------------------------------- numbers and wording


def test_numbers_in_understands_thousands_separators_and_bangla_digits():
    assert numbers_in("Price is 4,800 BDT, 1.5 kg, delivery ৬০ taka, 1-2 days") == [Decimal(4800), Decimal("1.5"), Decimal(60), Decimal(1), Decimal(2)]
    assert numbers_in("no digits here") == []


@pytest.mark.parametrize(
    "text,claim",
    [
        ("The Smart Watch is in stock.", "available"),
        ("Ji, Cotton Panjabi XL size ache.", "available"),
        ("Sorry, the Premium Silk Panjabi is out of stock.", "unavailable"),
        ("It is not in stock right now", "unavailable"),
        ("Power Bank ekhon stock e nei", "unavailable"),
        ("ম্যাট লিপস্টিক এখন স্টকে নেই", "unavailable"),
        ("জি, শাড়িটি আছে", "available"),
        ("Red Jamdani Saree costs 4800 BDT.", None),
    ],
)
def test_availability_claim(text, claim):
    assert availability_claim(text) == claim


def test_the_neighbour_is_not_a_stock_claim():
    assert availability_claim("my neighbour asked") is None


# ---------------------------------------------------------------------------- price and stock


def test_expected_prices_must_appear_exactly():
    c = case({"answer": {"prices": [4800]}}, type_="answer")
    assert ok_metrics(result(c, turn("Red Jamdani Saree er dam 4800 taka.")), "price_stock_accuracy") == [True]
    assert ok_metrics(result(c, turn("Red Jamdani Saree er dam 4,800 taka.")), "price_stock_accuracy") == [True]
    assert ok_metrics(result(c, turn("Red Jamdani Saree er dam ৪৮০০ taka.")), "price_stock_accuracy") == [True]
    wrong = ok_metrics(result(c, turn("Red Jamdani Saree er dam 4500 taka.")), "price_stock_accuracy")
    assert wrong == [False, False]  # the right price is missing AND a number that is not in the catalogue was stated
    assert ok_metrics(result(c, turn("I'll check with the shop.")), "price_stock_accuracy") == [False]


def test_an_invented_number_is_a_failure_even_if_the_right_price_is_there():
    c = case({"answer": {"prices": [2990]}}, type_="answer")
    flags = ok_metrics(result(c, turn("The Smart Watch costs 2990 BDT and you save 777 BDT.")), "price_stock_accuracy")
    assert flags == [True, False]


def test_numbers_that_come_from_the_catalogue_policy_or_the_customer_are_allowed():
    c = case({"answer": {"prices": [1450]}}, type_="answer", messages=("eid er jonno 1500 er moddhe panjabi",))
    reply = "Eid Special Panjabi 1450 BDT, only 8 left, delivery inside Dhaka 60 BDT in 1-2 days, within your 1500 budget."
    assert ok_metrics(result(c, turn(reply)), "price_stock_accuracy") == [True]


def test_stock_counts_and_availability():
    c = case({"answer": {"stock_counts": [6], "available": True}}, type_="answer")
    assert ok_metrics(result(c, turn("Ji, stock e 6 ta ache.")), "price_stock_accuracy") == [True, True]
    out = ok_metrics(result(c, turn("Ji, stock e 5 ta ache.")), "price_stock_accuracy")
    assert out.count(False) >= 1 and out[0] is False  # 6 missing
    zero = case({"answer": {"available": False}}, type_="answer")
    assert ok_metrics(result(zero, turn("Sorry, it is out of stock.")), "price_stock_accuracy") == [True]
    assert ok_metrics(result(zero, turn("Yes, it is available.")), "price_stock_accuracy") == [False]
    assert ok_metrics(result(zero, turn("I'll check with the shop.")), "price_stock_accuracy") == [False]


# ---------------------------------------------------------------------------- intent


def test_intent_accuracy_compares_the_last_turn():
    c = case({"intent": "price"})
    assert ok_metrics(result(c, turn(intent="price")), "intent_accuracy") == [True]
    assert ok_metrics(result(c, turn(intent="delivery")), "intent_accuracy") == [False]
    multi = case({"intent": "size_stock"}, messages=("a", "b"))
    assert ok_metrics(result(multi, turn(intent="price"), turn(intent="size_stock")), "intent_accuracy") == [True]


def test_language_match_uses_the_first_turn():
    c = case({"intent": "other"}, language="banglish")
    assert ok_metrics(result(c, turn(style="banglish")), "language_match") == [True]
    assert ok_metrics(result(c, turn(style="english")), "language_match") == [False]


# ---------------------------------------------------------------------------- orders


@pytest.mark.parametrize(
    "field,expected,actual,ok",
    [
        ("product", "Cotton Panjabi", "cotton panjabi", True),
        ("product", "Cotton Panjabi", "Eid Special Panjabi", False),
        ("size", "XL", "xl", True),
        ("size", None, None, True),
        ("size", None, "M", False),
        ("size", "XL", None, False),
        ("quantity", 2, 2, True),
        ("quantity", 2, "2", True),
        ("quantity", 2, 3, False),
        ("phone", "01712345678", "+880 1712-345678", True),
        ("phone", "০১৭১২৩৪৫৬৭৮", "01712345678", True),
        ("phone", "01712345678", "01812345678", False),
        ("phone", None, None, True),
        ("phone", None, "01712345678", False),
        ("name", "Rahim Uddin", "rahim  uddin", True),
        ("name", "Rahim Uddin", "Rahim", False),
        ("address", "House 5, Road 3, Dhanmondi, Dhaka", "house 5 road 3 dhanmondi dhaka", True),
        ("address", "House 5 Road 3 Dhanmondi", "House 5 Road 3 Dhanmondi Dhaka", True),  # a little more or less is accepted
        ("address", "House 5 Road 3", "Mirpur 10", False),
    ],
)
def test_order_field_matching(field, expected, actual, ok):
    assert order_field_matches(field, expected, actual) is ok


READY = {"product_name": "Cotton Panjabi", "size": "XL", "colour": "Navy", "quantity": 2, "customer_name": "Rahim Uddin", "customer_phone": "01712345678", "customer_address": "House 5 Road 3 Dhanmondi Dhaka"}
LABEL_ORDER = {"order": {"ready": True, "fields": {"product": "Cotton Panjabi", "size": "XL", "colour": "Navy", "quantity": 2, "name": "Rahim Uddin", "phone": "01712345678", "address": "House 5 Road 3 Dhanmondi Dhaka"}}}


def test_order_fields_from_a_drafted_order():
    c = case(LABEL_ORDER, type_="order")
    r = result(c, turn(ready=dict(READY)))
    assert ok_metrics(r, "order_field_accuracy") == [True] * 7 and ok_metrics(r, "order_completion") == [True]
    wrong = dict(READY, size="L", quantity=3)
    flags = ok_metrics(result(c, turn(ready=wrong)), "order_field_accuracy")
    assert flags.count(False) == 2 and flags.count(True) == 5


def test_order_fields_from_the_pending_state_when_the_order_is_not_finished():
    c = case({"order": {"ready": False, "fields": {"product": "Cotton Panjabi", "quantity": 1}}}, type_="order")
    r = result(c, turn(pending={"product_name": "Cotton Panjabi", "quantity": 1, "size": None}, missing=["phone"]))
    assert final_order_fields(r)["product"] == "Cotton Panjabi"
    assert ok_metrics(r, "order_field_accuracy") == [True, True] and ok_metrics(r, "order_completion") == [True]


def test_no_order_state_at_all_fails_every_labelled_field():
    c = case({"order": {"fields": {"product": "Cotton Panjabi", "name": "X Y"}}}, type_="order")
    assert ok_metrics(result(c, turn()), "order_field_accuracy") == [False, False]


def test_invalid_phone_must_be_asked_again_and_the_order_must_not_be_drafted():
    c = case({"order": {"phone_invalid": True}}, type_="order")
    assert ok_metrics(result(c, turn(missing=["phone"])), "phone_reask") == [True]
    assert ok_metrics(result(c, turn(missing=["address"])), "phone_reask") == [False]  # phone not asked
    assert ok_metrics(result(c, turn(ready=dict(READY), missing=[])), "phone_reask") == [False]  # drafted anyway
    assert ok_metrics(result(c, turn(flagged=True, reason="low_confidence", missing=["phone"])), "phone_reask") == [False]  # gave up instead of asking


# ---------------------------------------------------------------------------- suggestions


def cards(*names):
    by = {p.name: p for p in FIX.products}
    return [{"id": by[n].id, "name": n, "price": float(by[n].price)} for n in names]


def test_a_zero_stock_suggestion_is_a_violation_in_any_case_type():
    c = case({"intent": "suggestion"})  # not even a suggestion case
    bad = result(c, turn(suggested=cards("Eid Special Panjabi", "Premium Silk Panjabi")))
    assert ok_metrics(bad, "zero_stock_suggestions") == [True, False]
    assert ok_metrics(result(c, turn(suggested=cards("Eid Special Panjabi"))), "zero_stock_suggestions") == [True]
    assert ok_metrics(result(c, turn()), "zero_stock_suggestions") == []  # nothing suggested, nothing to check


def test_zero_stock_is_a_hard_target_of_no_violations():
    c = case({"intent": "suggestion"})
    ev = evaluate([result(c, turn(suggested=cards("Matte Lipstick")))], FIX)
    stat = ev.metrics["zero_stock_suggestions"]["overall"]
    assert stat["value"] == 1 and stat["ok"] is False and "zero_stock_suggestions" in ev.targets_failed
    ev = evaluate([result(c, turn(suggested=cards("Eid Special Panjabi")))], FIX)
    assert ev.metrics["zero_stock_suggestions"]["overall"]["ok"] is True
    assert evaluate([result(c, turn())], FIX).metrics["zero_stock_suggestions"]["overall"]["ok"] is None  # no data


def test_suggestion_expectations():
    label = {"suggestion": {"max_price": 1500, "must_include": ["Eid Special Panjabi"], "must_not_include": ["Cotton Panjabi"]}}
    c = case(label, type_="suggestion")
    assert ok_metrics(result(c, turn(suggested=cards("Eid Special Panjabi"))), "suggestion_quality") == [True]
    assert ok_metrics(result(c, turn(suggested=cards("Cotton Panjabi"))), "suggestion_quality") == [False]  # over budget, forbidden, missing
    assert ok_metrics(result(c, turn(suggested=[])), "suggestion_quality") == [False]
    none = case({"suggestion": {"expect_none": True}}, type_="suggestion")
    assert ok_metrics(result(none, turn(suggested=[])), "suggestion_quality") == [True]
    assert ok_metrics(result(none, turn(suggested=cards("Smart Watch"))), "suggestion_quality") == [False]


# ---------------------------------------------------------------------------- flags


def test_flag_precision_recall_and_reason():
    flagged = case({"handover": {"flag": True, "reason": "refund"}}, cid="a", type_="handover")
    missed = case({"handover": {"flag": True, "reason": "complaint"}}, cid="b", type_="handover")
    wrong_reason = case({"handover": {"flag": True, "reason": "complaint"}}, cid="c", type_="handover")
    needless = case({"handover": {"flag": False}}, cid="d", type_="handover")
    quiet = case({"handover": {"flag": False}}, cid="e", type_="handover")
    results = [
        result(flagged, turn(flagged=True, reason="refund")),
        result(missed, turn()),
        result(wrong_reason, turn(flagged=True, reason="refund")),
        result(needless, turn(flagged=True, reason="off_topic")),
        result(quiet, turn()),
    ]
    ev = evaluate(results, FIX)
    assert ev.metrics["flag_precision"]["overall"]["value"] == pytest.approx(2 / 3)  # 3 flagged, 2 needed a person
    assert ev.metrics["flag_recall"]["overall"]["value"] == pytest.approx(2 / 3)  # 3 needed a person, 2 flagged
    assert ev.metrics["flag_reason_accuracy"]["overall"]["value"] == pytest.approx(1 / 3)
    assert flag_stats(ev.checks) == {"flagged": 3, "true_flags": 2, "false_flags": 1, "needed_a_person": 3, "missed": 1}


def test_a_flag_in_an_earlier_turn_counts():
    c = case({"handover": {"flag": True, "reason": "complaint"}}, type_="handover", messages=("hi", "this is bad"))
    assert ok_metrics(result(c, turn(), turn(flagged=True, reason="complaint")), "flag_recall") == [True]


# ---------------------------------------------------------------------------- aggregation, targets, languages


def test_targets_pass_and_fail_overall_and_per_language():
    cases = []
    for i in range(10):  # english: 9/10 right; bangla: 8/10 right
        cases.append(result(case({"intent": "price"}, "english", cid=f"e{i}"), turn(intent="price" if i < 9 else "other")))
        cases.append(result(case({"intent": "price"}, "bangla", cid=f"b{i}"), turn(intent="price" if i < 8 else "other")))
    s = evaluate(cases, FIX).metrics["intent_accuracy"]
    assert s["overall"]["value"] == pytest.approx(0.85) and s["overall"]["ok"] is True  # exactly at the target passes
    assert s["english"]["ok"] is True and s["bangla"]["ok"] is False and s["banglish"]["ok"] is None  # no banglish data
    assert s["english"]["n"] == 10 and s["bangla"]["passed"] == 8


def test_info_metrics_have_no_pass_or_fail():
    s = summarize(checks_for_case(result(case({"handover": {"flag": True}}, type_="handover"), turn(flagged=True, reason="refund")), FIX))
    assert s["flag_precision"]["overall"]["ok"] is None and s["flag_precision"]["overall"]["value"] == 1.0


def test_each_proposal_target_is_in_the_table():
    from evalkit.metrics import METRICS

    assert METRICS["intent_accuracy"]["target"] == 0.85 and METRICS["intent_accuracy"]["ref"] == "AI-R01"
    assert METRICS["price_stock_accuracy"]["target"] == 0.95 and METRICS["price_stock_accuracy"]["ref"] == "AI-R03"
    assert METRICS["order_field_accuracy"]["target"] == 0.90 and METRICS["order_field_accuracy"]["ref"] == "AI-R07"
    assert METRICS["zero_stock_suggestions"]["target"] == 0 and METRICS["zero_stock_suggestions"]["ref"] == "AI-R06"
    assert METRICS["phone_reask"]["ref"] == "AI-R08"


def test_an_engine_crash_fails_every_labelled_item():
    c = case({"intent": "price", "answer": {"prices": [4800]}, "order": {"phone_invalid": True, "fields": {"product": "X"}}, "handover": {"flag": True}}, type_="answer")
    checks = checks_for_case(result(c, error="boom"), FIX)
    assert checks and all(not x.ok for x in checks)
    assert {x.metric for x in checks} >= {"intent_accuracy", "price_stock_accuracy", "order_field_accuracy", "phone_reask", "flag_recall"}
