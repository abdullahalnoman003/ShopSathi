from decimal import Decimal

import pytest

from shopsathi_ai.budget import parse_budget, resolve_budget
from shopsathi_ai.engine import ChatContext, ConversationEngine
from shopsathi_ai.interfaces import ProductInfo, RetrievedChunk
from shopsathi_ai.phrases import phrase
from shopsathi_ai.prompts import load
from shopsathi_ai.providers.base import LLMProviderError
from shopsathi_ai.providers.mock import MockEmbeddingProvider, MockLLMProvider
from shopsathi_ai.suggestions import Needs, extract_needs, find_suggestions, matches_needs
from shopsathi_ai.tools import ShopTools
from tests.helpers import CHECK, FakeGateway, ScriptedLLM, und

BUDGET = ProductInfo(10, "Budget Panjabi", Decimal("1200"), ["M", "L"], ["White"], 5, photos=["http://img/10a.jpg", "http://img/10b.jpg"])
EID = ProductInfo(11, "Eid Panjabi", Decimal("900"), ["L", "XL"], ["Navy"], 3)
PREMIUM_SOLD_OUT = ProductInfo(12, "Premium Panjabi", Decimal("1400"), ["M", "L", "XL"], ["Navy", "White"], 0, photos=["http://img/12.jpg"])
SILK = ProductInfo(13, "Silk Panjabi", Decimal("2500"), ["M"], ["White"], 9)
SAREE = ProductInfo(14, "Red Jamdani Saree", Decimal("4800"), [], ["Red"], 6)
CATALOGUE = [BUDGET, EID, PREMIUM_SOLD_OUT, SILK, SAREE]


def suggest(needs, gateway=None, vector=None):
    gw = gateway or FakeGateway(products=CATALOGUE)
    return find_suggestions(ShopTools(gw, 1), gw, 1, needs, vector or [0.0] * 4)


# --------------------------------------------------------------- budget parsing


@pytest.mark.parametrize(
    "message,budget",
    [
        ("eid er jonno 1500 er moddhe panjabi", 1500),
        ("panjabi under 2000", 2000),
        ("১৫০০ টাকার মধ্যে পাঞ্জাবি", 1500),
        ("budget 1.5k", 1500),
        ("1,500 taka er saree", 1500),
        ("panjabi 1500 tk", 1500),
        ("2 hajar taka", 2000),
        ("XL size 38 ache", None),
        ("2 ta panjabi lagbe", None),
        ("kichu dekhan", None),
        ("stock 5 ache?", None),
    ],
)
def test_parse_budget(message, budget):
    assert parse_budget(message) == (None if budget is None else Decimal(str(budget)))


def test_model_budget_is_only_accepted_if_the_customer_wrote_it():
    assert resolve_budget("panjabi dekhan", Decimal("1000")) is None  # invented by the model
    assert resolve_budget("panjabi 1500 dibo", Decimal("1500")) == Decimal("1500")  # the number is in the message
    assert resolve_budget("under 800 panjabi", Decimal("5000")) == Decimal("800")  # code's reading wins


# ------------------------------------------------------------------ filtering


def test_zero_stock_is_never_suggested_even_as_the_best_match():
    # by name: "premium panjabi" matches the sold-out product best (2 of 2 words)
    got = suggest(Needs(product_type="premium panjabi"))
    assert PREMIUM_SOLD_OUT.id not in [p.id for p in got] and got
    # by similarity: the sold-out product is the closest chunk of all
    gw = FakeGateway(products=CATALOGUE, chunks=[RetrievedChunk("product", 12, "Premium Panjabi", 0.99), RetrievedChunk("product", 10, "Budget", 0.5)])
    got = suggest(Needs(occasion="eid"), gw)
    assert 12 not in [p.id for p in got] and 10 in [p.id for p in got]
    assert not matches_needs(PREMIUM_SOLD_OUT, Needs())


def test_budget_size_and_colour_are_respected():
    ids = lambda needs: sorted(p.id for p in suggest(needs))  # noqa: E731
    assert ids(Needs(product_type="panjabi", budget_max=Decimal("1500"))) == [10, 11]  # not 2500, not sold out
    assert ids(Needs(product_type="panjabi", budget_max=Decimal("1200"))) == [10, 11]  # equal to the budget is fine
    assert ids(Needs(product_type="panjabi", budget_max=Decimal("1000"))) == [11]
    assert ids(Needs(product_type="panjabi", budget_max=Decimal("100"))) == []
    assert ids(Needs(product_type="panjabi", size="xl")) == [11]  # Premium has XL but no stock
    assert ids(Needs(product_type="panjabi", colour="White")) == [10, 13]
    assert ids(Needs(product_type="panjabi", size="L", colour="navy", budget_max=Decimal("1000"))) == [11]
    assert ids(Needs(product_type="panjabi", size="XXL")) == []


def test_at_most_three_and_cheapest_first_among_equal_matches():
    many = [ProductInfo(100 + i, f"Panjabi {i}", Decimal(1000 + 100 * i), ["M"], ["White"], 4) for i in range(6)]
    got = suggest(Needs(product_type="panjabi"), FakeGateway(products=many))
    assert len(got) == 3 and [p.id for p in got] == [100, 101, 102]


def test_no_match_returns_nothing_and_never_relaxes_the_stock_rule():
    only_sold_out = FakeGateway(products=[PREMIUM_SOLD_OUT])
    assert suggest(Needs(product_type="panjabi"), only_sold_out) == []
    assert suggest(Needs(product_type="laptop")) == []  # no such product type in this shop


def test_no_product_type_browses_in_stock_products_within_budget():
    got = suggest(Needs(budget_max=Decimal("1300")))
    assert sorted(p.id for p in got) == [10, 11]


def test_stock_is_read_again_just_before_replying():
    class Racing(FakeGateway):
        reads = 0

        def get_products(self, shop_id, product_ids):
            self.reads += 1
            sold = [p for p in super().get_products(shop_id, product_ids)]
            return [ProductInfo(**{**p.__dict__, "stock_count": 0}) if p.id == 10 else p for p in sold]

    got = suggest(Needs(product_type="panjabi", budget_max=Decimal("1500")), Racing(products=CATALOGUE))
    assert [p.id for p in got] == [11]  # product 10 sold its last piece in between


# ---------------------------------------------------------------- needs (LLM)


def test_extract_needs_validates_and_retries():
    llm = ScriptedLLM(needs=[{"budget_max": "lots"}, {"product_type": "panjabi", "budget_max": 1500, "occasion": "eid"}])
    out = extract_needs(llm, "eid er jonno 1500 er moddhe panjabi", [], {})
    assert not out.used_fallback and len(llm.calls) == 2
    assert (out.needs.product_type, out.needs.budget_max, out.needs.occasion) == ("panjabi", Decimal("1500"), "eid")
    assert "invalid" in llm.calls[1][2]


def test_extract_needs_falls_back_to_understood_entities_and_code():
    llm = ScriptedLLM(needs=[{"nope": 1}])
    entities = {"product_name": "panjabi", "product_name_en": "panjabi", "size": "XL", "colour": None, "area": None}
    out = extract_needs(llm, "panjabi XL 2000 er moddhe", [], entities)
    assert out.used_fallback and out.needs.product_type == "panjabi" and out.needs.size == "XL"
    assert out.needs.budget_max == Decimal("2000")
    down = extract_needs(ScriptedLLM(needs=[LLMProviderError("down")]), "panjabi dekhan", [], entities)
    assert down.used_fallback and down.needs.product_type == "panjabi"


def test_invented_budget_is_dropped():
    out = extract_needs(ScriptedLLM(needs=[{"product_type": "panjabi", "budget_max": 999}]), "panjabi dekhan", [], {})
    assert out.needs.budget_max is None


def test_prompts_forbid_guessing_about_the_customer():
    for name in ("needs_system.md", "reply_system.md"):
        text = load(name).lower()
        assert "gender" in text and "religion" in text


# ------------------------------------------------------------------- engine


def make_engine(llm, gateway=None):
    gateway = gateway or FakeGateway(products=CATALOGUE)
    return ConversationEngine(llm, MockEmbeddingProvider(8), gateway), gateway


def ctx(first=False):
    return ChatContext("Rina Fashion House", is_first_ai_reply=first)


def test_engine_returns_cards_with_price_and_first_photo():
    llm = ScriptedLLM(
        understand=[und("suggestion", product="panjabi")],
        needs=[{"product_type": "panjabi", "budget_max": 1500, "occasion": "eid"}],
        reply=[{"reply": "Try Budget Panjabi (1200 BDT) or Eid Panjabi (900 BDT)."}],
    )
    res = make_engine(llm)[0].process_customer_message(1, ctx(), "eid er jonno 1500 er moddhe panjabi")
    cards = res.extras["suggested_products"]
    assert [c["id"] for c in cards] == [11, 10] or [c["id"] for c in cards] == [10, 11]
    by_id = {c["id"]: c for c in cards}
    assert by_id[10] == {"id": 10, "name": "Budget Panjabi", "price": 1200.0, "photo": "http://img/10a.jpg"}
    assert by_id[11]["photo"] is None
    assert res.extras["needs"] == {"product_type": "panjabi", "budget_max": 1500.0, "size": None, "colour": None, "occasion": "eid"}
    assert not res.handover.needed
    # the model is shown only the products that passed the filters
    facts = " ".join(llm.payloads("reply")[0]["facts"])
    assert "Budget Panjabi" in facts and "Eid Panjabi" in facts
    for hidden in ("Premium Panjabi", "Silk Panjabi", "Saree"):
        assert hidden not in facts
    assert [u.operation for u in res.usage] == ["intent", "suggestion_needs", "chat_reply"]


def test_engine_never_shows_a_zero_stock_card():
    llm = ScriptedLLM(understand=[und("suggestion", product="premium panjabi")], needs=[{"product_type": "premium panjabi"}], reply=[{"reply": "ok 900 BDT"}])
    res = make_engine(llm)[0].process_customer_message(1, ctx(), "premium panjabi dekhan")
    assert 12 not in [c["id"] for c in res.extras["suggested_products"]]


@pytest.mark.parametrize("message,style", [("laptop dekhan 1000 er moddhe", "banglish"), ("Show me a laptop under 1000", "english"), ("ল্যাপটপ দেখান ১০০০ টাকার মধ্যে", "bangla")])
def test_no_match_gives_an_honest_reply_in_the_customers_style(message, style):
    llm = ScriptedLLM(understand=[und("suggestion", product="laptop")], needs=[{"product_type": "laptop", "product_type_en": "laptop", "budget_max": 1000}])
    res = make_engine(llm)[0].process_customer_message(1, ctx(), message)
    assert res.language_style == style and res.reply_text == phrase("no_suggestion", style)
    assert res.extras["suggested_products"] == [] and not res.handover.needed
    assert llm.payloads("reply") == []  # nothing to write about: no invented items


def test_no_needs_at_all_asks_what_the_customer_wants():
    llm = ScriptedLLM(understand=[und("suggestion")], needs=[{}])
    res = make_engine(llm)[0].process_customer_message(1, ctx(), "kichu suggest korun")
    assert res.reply_text == phrase("ask_needs", "banglish") and res.extras["suggested_products"] == []
    assert llm.payloads("reply") == []


def test_ungrounded_reply_means_no_cards():
    llm = ScriptedLLM(understand=[und("suggestion", product="panjabi")], needs=[{"product_type": "panjabi"}], reply=[{"reply": "Only 700 BDT!"}])
    res = make_engine(llm)[0].process_customer_message(1, ctx(), "panjabi dekhan")
    assert res.reply_text == CHECK["banglish"] and (res.handover.reason, res.handover.detail) == ("low_confidence", "reply_not_grounded")
    assert res.extras["suggested_products"] == []


def test_single_suggestion_can_be_referred_to_as_eta():
    llm = ScriptedLLM(understand=[und("suggestion", product="panjabi")], needs=[{"product_type": "panjabi", "budget_max": 1000}], reply=[{"reply": "Eid Panjabi, 900 BDT."}])
    res = make_engine(llm)[0].process_customer_message(1, ctx(), "panjabi 1000 er moddhe")
    assert [c["id"] for c in res.extras["suggested_products"]] == [11] and res.entities["product_name"] == "Eid Panjabi"


def test_mock_llm_handles_the_proposal_example():
    engine, _ = make_engine(MockLLMProvider())
    res = engine.process_customer_message(1, ctx(), "eid er jonno 1500 er moddhe panjabi")
    ids = {c["id"] for c in res.extras["suggested_products"]}
    assert ids == {10, 11}  # in stock, within 1500; not sold-out Premium, not Silk (2500)
    assert res.extras["needs"]["budget_max"] == 1500.0 and res.extras["needs"]["occasion"] == "eid"
    assert "Panjabi" in res.reply_text and 1 <= len(res.extras["suggested_products"]) <= 3
