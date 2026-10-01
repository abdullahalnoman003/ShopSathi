"""The case file format, the fixture gateway, and an end-to-end run of the harness with the mock provider."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from shopsathi_ai.providers.mock import MockEmbeddingProvider, MockLLMProvider

from evalkit.cases import CaseError, load_cases, parse_case
from evalkit.gateway import EvalGateway, load_fixture
from evalkit.report import build_report, to_markdown
from evalkit.runner import run_cases
from evalkit.metrics import evaluate

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample_cases.jsonl"


def write(tmp_path, *lines: str) -> Path:
    p = tmp_path / "cases.jsonl"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def good(**over) -> dict:
    base = {"id": "c1", "language": "english", "type": "intent", "messages": ["price?"], "labels": {"intent": "price"}}
    base.update(over)
    return base


# ------------------------------------------------------------------------- the sample file


def test_the_sample_file_is_valid_covers_every_type_and_language_and_is_marked_as_sample():
    cases = load_cases(SAMPLE)
    assert len(cases) >= 20
    assert {c.type for c in cases} == {"intent", "answer", "order", "suggestion", "handover"}
    assert {c.language for c in cases} == {"bangla", "english", "banglish"}
    assert all(c.sample for c in cases)
    assert len({c.id for c in cases}) == len(cases)
    assert any("phone_invalid" in c.labels.get("order", {}) for c in cases)


def test_the_sample_labels_agree_with_the_fixture_catalogue():
    """If a price or stock count in the fixture changes, the labels that mention it must change too."""
    fix = load_fixture()
    prices = {p.price for p in fix.products} | {c for _, c in fix.policy.delivery_areas}
    for c in load_cases(SAMPLE):
        for value in c.labels.get("answer", {}).get("prices", []):
            assert value in prices, f"{c.id}: {value} is not a price or charge in the fixture"
        for name in c.labels.get("suggestion", {}).get("must_include", []):
            assert fix.product_by_name(name) and fix.product_by_name(name).stock_count > 0, f"{c.id}: {name} must be an in-stock product"
    zero = {p.name for p in fix.products if p.stock_count == 0}
    assert {"Premium Silk Panjabi", "Matte Lipstick", "Power Bank 10000mAh"} <= zero


# ------------------------------------------------------------------------- format checks


def test_a_valid_case_loads_and_comment_lines_are_ignored(tmp_path):
    p = write(tmp_path, "// a comment", "", json.dumps(good()))
    (c,) = load_cases(p)
    assert c.id == "c1" and c.messages == ["price?"] and c.sample is False


@pytest.mark.parametrize(
    "over,problem",
    [
        ({"id": ""}, "id is required"),
        ({"language": "french"}, "language must be one of"),
        ({"type": "joke"}, "type must be one of"),
        ({"messages": []}, "messages must be"),
        ({"messages": ["ok", ""]}, "messages must be"),
        ({"messages": "price?"}, "messages must be"),
        ({"labels": {}}, "labels is required"),
        ({"labels": {"intent": "shipping"}}, "labels.intent must be one of"),
        ({"labels": {"intent": "price", "colour": "x"}}, "unknown label group"),
        ({"type": "answer", "labels": {"intent": "price"}}, "needs labels.answer"),
        ({"type": "order", "labels": {"intent": "price"}}, "needs labels.order"),
        ({"type": "handover", "labels": {"intent": "price"}}, "needs labels.handover"),
        ({"type": "answer", "labels": {"answer": {"prices": "4800"}}}, "list of numbers"),
        ({"type": "answer", "labels": {"answer": {"colour": 1}}}, "allows prices"),
        ({"type": "answer", "labels": {"answer": {}}}, "must not be empty"),
        ({"type": "order", "labels": {"order": {"fields": {"shoe": "x"}}}}, "keys must be among"),
        ({"type": "order", "labels": {"order": {}}}, "at least"),
        ({"type": "suggestion", "labels": {"suggestion": {"max_price": "cheap"}}}, "max_price must be a number"),
        ({"type": "handover", "labels": {"handover": {"flag": "yes"}}}, "flag: true|false"),
        ({"type": "handover", "labels": {"handover": {"flag": True, "reason": "rude"}}}, "reason must be one of"),
        ({"type": "handover", "labels": {"handover": {"flag": False, "reason": "refund"}}}, "only makes sense when flag is true"),
    ],
)
def test_malformed_cases_are_rejected_with_a_clear_message(tmp_path, over, problem):
    with pytest.raises(CaseError) as e:
        load_cases(write(tmp_path, json.dumps(good(**over))))
    assert problem in str(e.value) and "line 1" in str(e.value)


def test_duplicate_ids_bad_json_and_empty_files(tmp_path):
    with pytest.raises(CaseError, match="duplicate id"):
        load_cases(write(tmp_path, json.dumps(good()), json.dumps(good())))
    with pytest.raises(CaseError, match="line 1: not valid JSON"):
        load_cases(write(tmp_path, "{nope"))
    with pytest.raises(CaseError, match="no cases"):
        load_cases(write(tmp_path, "// only a comment"))
    with pytest.raises(CaseError, match="line 2"):
        load_cases(write(tmp_path, json.dumps(good()), json.dumps(good(id="c2", language="x"))))


def test_parse_case_keeps_extra_fields(tmp_path):
    c = parse_case(good(note="from a public page", source="role-play"), 1)
    assert c.note == "from a public page" and c.extra == {"source": "role-play"}


# ------------------------------------------------------------------------- the fixture gateway


def gateway():
    return EvalGateway(load_fixture(), MockEmbeddingProvider(64))


def test_gateway_finds_products_by_name_like_the_backend():
    g = gateway()
    hits = g.search_products(1, "red saree", None, 3)
    assert hits[0].name == "Red Jamdani Saree" and hits[0].match == "name" and hits[0].score == 1.0
    assert g.search_products(1, "laptop", None, 3) == []  # no similarity fallback without a vector
    only_one_word = g.search_products(1, "panjabi", None, 5)
    assert {p.name for p in only_one_word} == {"Cotton Panjabi", "Eid Special Panjabi", "Premium Silk Panjabi"}


def test_gateway_stock_delivery_and_browse():
    g = gateway()
    assert g.check_stock(1, 4).in_stock is False and g.check_stock(1, 2, "xl").size_offered is True and g.check_stock(1, 2, "S").size_offered is False
    assert g.check_stock(1, 999) is None
    assert g.get_delivery_charge(1, "khagan").charge == 100 and g.get_delivery_charge(1, "INSIDE-dhaka").charge == 60
    assert g.get_delivery_charge(1, "Mars").found is False
    names = {p.name for p in g.browse_products(1, None, 50)}
    assert "Premium Silk Panjabi" not in names and "Matte Lipstick" not in names and "Power Bank 10000mAh" not in names  # never zero-stock
    assert all(p.price <= 1000 for p in g.browse_products(1, 1000, 50))


def test_gateway_vector_search_uses_the_policy_and_product_chunks():
    g = gateway()
    vec = MockEmbeddingProvider(64).embed(["Shop policy - Delivery charge for Khagan: 100 BDT"])[0]
    best = g.vector_search(1, vec, 3)[0]
    assert best.source_type == "policy" and "Khagan" in best.content and best.score == pytest.approx(1.0)
    assert all(h.source_type == "product" for h in g.vector_search(1, vec, 5, ["product"]))


# ------------------------------------------------------------------------- an end-to-end run


def test_the_harness_runs_end_to_end_with_the_mock_provider_and_writes_both_reports(tmp_path):
    cases = load_cases(SAMPLE)
    results, gw = run_cases(cases, MockLLMProvider(), MockEmbeddingProvider(64))
    assert len(results) == len(cases) and all(r.turns for r in results) and not any(r.error for r in results)
    ev = evaluate(results, load_fixture())
    for key in ("intent_accuracy", "price_stock_accuracy", "order_field_accuracy", "zero_stock_suggestions", "phone_reask"):
        assert ev.metrics[key]["overall"]["n"] > 0, key
    report = build_report(results, ev, {"timestamp": "t", "data": "x", "llm_provider": "mock", "llm_model": "mock", "embedding_provider": "mock", "is_mock": True, "sample_only": True, "_usage": []})
    md = to_markdown(report)
    assert "mock provider was used" in md and "Only sample cases" in md and "AI-R01" in md and "AI-R03" in md and "AI-R07" in md
    assert "Bangla" in md and "English" in md and "Banglish" in md and "Failures" in md
    json.dumps(report, default=str)


def test_a_multi_turn_order_carries_the_pending_order_and_stops_after_a_flag():
    from evalkit.cases import Case

    flagged = Case("f", "english", "handover", ["this product is bad and damaged, I am very disappointed", "second message"], {"handover": {"flag": True}})
    (r,), _ = run_cases([flagged], MockLLMProvider(), MockEmbeddingProvider(64))
    assert len(r.turns) == 1 and r.stopped_after_flag and r.turns[0].flagged


def test_the_command_line_tool_runs_and_reports(tmp_path):
    out = subprocess.run(
        [sys.executable, str(ROOT / "run_eval.py"), "--data", str(SAMPLE), "--provider", "mock", "--out-dir", str(tmp_path), "--limit", "12"],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
    )
    assert out.returncode == 0, out.stderr
    assert "Results against the proposal targets" in out.stdout
    files = sorted(p.suffix for p in tmp_path.iterdir())
    assert files == [".json", ".md"]
    data = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert data["meta"]["cases"] == 12 and data["meta"]["is_mock"] is True


def test_the_command_line_tool_fails_clearly_on_bad_input(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text("{nope", encoding="utf-8")
    run = lambda *a: subprocess.run([sys.executable, str(ROOT / "run_eval.py"), *a], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    r = run("--data", str(bad), "--provider", "mock", "--out-dir", str(tmp_path))
    assert r.returncode == 2 and "not valid JSON" in r.stderr
    r = run("--data", str(tmp_path / "missing.jsonl"), "--provider", "mock")
    assert r.returncode == 2
    r = run("--data", str(SAMPLE), "--provider", "openai", "--env-file", str(tmp_path / "none.env"))
    assert r.returncode == 2 and "Cannot read the env file" in r.stderr and "Traceback" not in r.stderr


def test_fail_on_target_sets_the_exit_code(tmp_path):
    r = subprocess.run(
        [sys.executable, str(ROOT / "run_eval.py"), "--data", str(SAMPLE), "--provider", "mock", "--out-dir", str(tmp_path), "--fail-on-target"],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
    )
    assert r.returncode == 1  # the mock test double does not meet the targets
