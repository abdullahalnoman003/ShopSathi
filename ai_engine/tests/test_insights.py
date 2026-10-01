import json
import re

import pytest

from shopsathi_ai import insights
from shopsathi_ai.insights import BATCH_CHARS, MAX_QUESTIONS, redact, summarize_week
from shopsathi_ai.providers.base import LLMProvider, LLMProviderError, LLMResult
from shopsathi_ai.providers.mock import MockLLMProvider


class Recorder(LLMProvider):
    """Answers map/reduce calls from queues and records every prompt (to check what the model is shown)."""

    name, model = "recorder", "rec-1"

    def __init__(self, maps=(), reduce=None, fail_first=0):
        self.maps = list(maps)
        self.reduce = reduce
        self.fail_first = fail_first
        self.calls: list[tuple[str, str]] = []

    def generate_json_with_usage(self, system_prompt, user_prompt, *, task="generic"):
        self.calls.append((task, user_prompt))
        if self.fail_first:
            self.fail_first -= 1
            raise LLMProviderError("temporary")
        if task == "insights_map":
            data = self.maps.pop(0) if len(self.maps) > 1 else self.maps[0]
        else:
            data = self.reduce
        return LLMResult(data, 10, 5, self.name, self.model)

    def sent_text(self) -> str:
        return "\n".join(u for _, u in self.calls)


def q(text, n):
    return {"question": text, "count": n}


def p(name, n):
    return {"name": name, "count": n}


HAS = {"red jamdani saree", "cotton panjabi"}


def lookup(name):
    return any(name.casefold() in h or h in name.casefold() for h in HAS)


# ------------------------------------------------------------------------ personal data is removed


@pytest.mark.parametrize(
    "text,gone,marker",
    [
        ("call me 01712345678 please", "01712345678", "[phone]"),
        ("my number is +880 1712-345678", "345678", "[phone]"),
        ("amar number ০১৭১২৩৪৫৬৭৮", "০১৭১২৩৪৫৬৭৮", "[phone]"),
        ("email rahim@example.com for details", "rahim@example.com", "[link]"),
        ("see https://facebook.com/rahim.profile now", "facebook.com", "[link]"),
        ("my address is House 5, Road 3, Dhanmondi, Dhaka", "Dhanmondi", "[address]"),
        ("amar thikana mirpur 10 dhaka", "mirpur", "[address]"),
        ("আমার ঠিকানা মিরপুর ১০ ঢাকা", "মিরপুর", "[address]"),
        ("my name is Rahim Uddin, saree price koto?", "Rahim", "[name]"),
        ("amar nam Karim Mia", "Karim", "[name]"),
        ("আমার নাম রহিম উদ্দিন", "রহিম", "[name]"),
    ],
)
def test_personal_details_are_removed(text, gone, marker):
    out = redact(text)
    assert gone not in out and marker in out


def test_known_customer_names_are_removed_everywhere():
    assert "Nasrin" not in redact("Hi, Nasrin here, saree ache?", ["Nasrin Sultana", "Nasrin"])
    assert redact("price koto?") == "price koto?"  # ordinary questions are untouched
    assert redact("XL size 1500 taka er moddhe") == "XL size 1500 taka er moddhe"  # short numbers stay


def test_the_model_is_never_shown_personal_data():
    llm = Recorder(maps=[{"questions": [q("Asks the price", 1)], "products": []}])
    summarize_week(
        llm,
        ["price koto? call 01712345678", "my name is Rahim Uddin", "address House 5 Road 3 Dhanmondi", "Nasrin here: delivery charge?", "https://evil.example/x"],
        lookup,
        known_terms=["Nasrin"],
    )
    sent = llm.sent_text()
    for secret in ("01712345678", "Rahim", "Uddin", "Dhanmondi", "Nasrin", "evil.example"):
        assert secret not in sent
    assert "price koto?" in sent and "delivery charge?" in sent


def test_the_models_answer_is_cleaned_too():
    llm = Recorder(maps=[{"questions": [q("Rahim Uddin on 01712345678 asks about price", 3)], "products": [p("saree for 01812345678", 2)]}])
    r = summarize_week(llm, ["price koto?"], lambda n: False, known_terms=["Rahim Uddin"])
    text = json.dumps([r.top_questions[0].question, r.missing_products[0].name])
    assert "01712345678" not in text and "01812345678" not in text and "Rahim" not in text


def test_placeholders_and_empty_messages_are_not_sent():
    llm = Recorder(maps=[{"questions": [], "products": []}])
    r = summarize_week(llm, ["[Customer sent a photo]", "   ", "01712345678", "123", "price?"], lookup)
    assert r.messages_used == 1 and "photo" not in llm.sent_text()


# ------------------------------------------------------------------------ result shape


def test_at_most_five_questions_most_asked_first_with_sane_counts():
    llm = Recorder(maps=[{"questions": [q(f"Question {i}", i) for i in range(1, 9)] + [q("Absurd count", 9999)], "products": []}])
    r = summarize_week(llm, [f"message number {i}" for i in range(10)], lookup)
    assert len(r.top_questions) == MAX_QUESTIONS == 5
    assert r.top_questions[0].question == "Absurd count" and r.top_questions[0].count == 10  # never above the number of messages
    assert [x.count for x in r.top_questions][1:] == [8, 7, 6, 5]
    assert all(x.count >= 1 for x in r.top_questions)


def test_questions_with_the_same_text_are_merged_and_blank_ones_dropped():
    llm = Recorder(maps=[{"questions": [q("Asks the price", 3), q("asks the price.", 2), q("", 5), q("  ", 1), q("Asks about delivery", 1)], "products": []}])
    r = summarize_week(llm, ["a question here"] * 20, lookup)
    assert [(x.question, x.count) for x in r.top_questions] == [("Asks the price", 5), ("Asks about delivery", 1)]


def test_existing_products_are_left_out_of_the_missing_list_and_the_rest_is_ordered_by_demand():
    llm = Recorder(maps=[{"questions": [], "products": [p("Red Jamdani Saree", 9), p("laptop", 4), p("Wireless Earbuds", 6), p("cotton panjabi", 3), p("Smart Watch", 4), p("watch strap", 1)]}])
    r = summarize_week(llm, ["x message"] * 30, lookup)
    assert [(m.name, m.count) for m in r.missing_products] == [("Wireless Earbuds", 6), ("laptop", 4), ("Smart Watch", 4), ("watch strap", 1)]
    assert {m.name for m in r.requested_products} >= {"Red Jamdani Saree", "cotton panjabi"}
    assert all(not lookup(m.name) for m in r.missing_products)


def test_the_missing_list_is_limited_to_five():
    llm = Recorder(maps=[{"questions": [], "products": [p(f"gadget {i}", 20 - i) for i in range(9)]}])
    r = summarize_week(llm, ["x message"] * 30, lookup)
    assert len(r.missing_products) == 5 and r.missing_products[0].name == "gadget 0"
    assert len(r.requested_products) == 9


def test_the_lookup_decides_not_the_model():
    seen = []
    llm = Recorder(maps=[{"questions": [], "products": [p("Red Saree", 2)]}])
    summarize_week(llm, ["x message"], lambda n: seen.append(n) or True)
    assert seen == ["Red Saree"]


def test_product_spellings_are_merged_across_batches_and_case():
    llm = Recorder(maps=[{"questions": [], "products": [p("Laptop", 2)]}, {"questions": [], "products": [p("laptop", 3)]}], reduce={"questions": []})
    r = summarize_week(llm, ["y" * 250 for _ in range(40)], lambda n: False)
    assert [(m.name, m.count) for m in r.missing_products] == [("Laptop", 5)]


def test_no_messages_means_an_empty_summary_without_calling_the_model():
    llm = Recorder(maps=[{}])
    r = summarize_week(llm, [], lookup)
    assert r.top_questions == [] and r.missing_products == [] and r.messages_used == 0 and r.usage == [] and llm.calls == []


# ------------------------------------------------------------------------ batching


def test_a_big_week_is_summarised_in_batches_and_reduced():
    messages = [f"how much is product number {i} please tell" for i in range(400)]
    llm = Recorder(
        maps=[{"questions": [q("Asks the price", 5), q("Asks about stock", 2)], "products": []}],
        reduce={"questions": [q("Asks the price", 77), q("Asks about stock", 30)]},
    )
    r = summarize_week(llm, messages, lookup)
    maps = [c for c in llm.calls if c[0] == "insights_map"]
    reduces = [c for c in llm.calls if c[0] == "insights_reduce"]
    assert len(maps) > 1 and len(reduces) == 1
    for _, prompt in maps:  # no prompt grows without limit
        assert len(prompt) < BATCH_CHARS + 2500
    assert sum(len(json.loads(re.search(r"<input>\s*(.*?)\s*</input>", c[1], re.DOTALL).group(1))["messages"]) for c in maps) == 400
    assert [(x.question, x.count) for x in r.top_questions] == [("Asks the price", 77), ("Asks about stock", 30)]
    assert len(r.usage) == len(maps) + 1  # every call is reported for usage logging


def test_a_small_week_needs_one_call_and_no_reduce():
    llm = Recorder(maps=[{"questions": [q("Asks the price", 2)], "products": []}])
    r = summarize_week(llm, ["price koto?", "dam koto?"], lookup)
    assert [c[0] for c in llm.calls] == ["insights_map"] and len(r.usage) == 1


def test_an_enormous_week_is_sampled(monkeypatch):
    monkeypatch.setattr(insights, "MAX_MESSAGES", 50)
    llm = Recorder(maps=[{"questions": [], "products": []}])
    r = summarize_week(llm, [f"question {i} about something" for i in range(500)], lookup)
    assert r.messages_used == 50


# ------------------------------------------------------------------------ failures


def test_one_bad_answer_is_retried_and_a_dead_model_raises_instead_of_inventing_a_summary():
    ok = Recorder(maps=[{"questions": [q("Asks the price", 1)], "products": []}], fail_first=1)
    assert summarize_week(ok, ["price koto?"], lookup).top_questions[0].question == "Asks the price"
    assert len(ok.calls) == 2
    dead = Recorder(maps=[{}], fail_first=5)
    with pytest.raises(LLMProviderError):
        summarize_week(dead, ["price koto?"], lookup)


def test_junk_from_the_model_is_survived():
    llm = Recorder(maps=[{"questions": "none", "products": [{"name": ""}, {"count": 2}, p("x", "many")]}])
    r = summarize_week(llm, ["something here"], lambda n: False)
    assert r.top_questions == [] and [m.name for m in r.missing_products] == []  # one-character names are ignored


# ------------------------------------------------------------------------ the offline test double


def test_the_mock_provider_runs_the_whole_pipeline():
    messages = ["Red Jamdani Saree price koto?", "saree price koto?", "delivery charge koto Dhaka te?", "XL size ache?"]
    r = summarize_week(MockLLMProvider(), messages, lookup)
    assert 1 <= len(r.top_questions) <= 5 and r.messages_used == 4
