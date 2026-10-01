import pytest

from shopsathi_ai.engine import ChatContext, ConversationEngine
from shopsathi_ai.language import detect_style, normalise_digits
from shopsathi_ai.phrases import is_greeting, phrase
from shopsathi_ai.prompts import load, phrases, render
from shopsathi_ai.providers.base import LLMProviderError
from shopsathi_ai.providers.mock import MockEmbeddingProvider, MockLLMProvider
from shopsathi_ai.reply import ReplyRequest, numbers_in, ungrounded_numbers, write_reply
from shopsathi_ai.understanding import Turn, Understanding, understand
from tests.helpers import CHECK, FakeGateway, ScriptedLLM, policy_chunk, und

# ------------------------------------------------------------------ language


@pytest.mark.parametrize(
    "text,style",
    [
        ("price koto?", "banglish"),
        ("XL ache?", "banglish"),
        ("Khagan e delivery charge koto?", "banglish"),
        ("eta ki XL e pawa jabe?", "banglish"),
        ("XL size ache?", "banglish"),
        ("What is the price of the red saree?", "english"),
        ("Do you have this in XL?", "english"),
        ("দাম কত?", "bangla"),
        ("এটা কি XL সাইজে আছে?", "bangla"),
        ("খাগান এ ডেলিভারি চার্জ কত", "bangla"),
        ("ami lal saree nibo", "banglish"),
        ("hello", "english"),
    ],
)
def test_detect_style(text, style):
    assert detect_style(text) == style


def test_normalise_bangla_digits():
    assert normalise_digits("সাইজ ৩৮, দাম ৪৮০০ টাকা, 12") == "সাইজ 38, দাম 4800 টাকা, 12"


def test_prompts_and_phrases_live_in_files():
    for name in ("understand_system.md", "understand_user.md", "reply_system.md", "reply_user.md"):
        assert len(load(name)) > 100
    assert render("a {{x}} b {\"k\": 1}", x="1") == 'a 1 b {"k": 1}'
    for key in ("disclosure", "check_with_shop", "ask_product", "ask_area", "greeting"):
        assert set(phrases()[key]) == {"english", "banglish", "bangla"}
    assert "Test Shop" in phrase("disclosure", "english", shop_name="Test Shop")
    assert is_greeting("Hello") and is_greeting("assalamu alaikum") is False  # 'alaikum' is not a greeting word
    assert is_greeting("hi, price koto?") is False


# ------------------------------------------------------------ understanding


def test_understanding_schema_accepts_valid_and_rejects_invalid():
    ok = Understanding.model_validate(und("price", product="lal saree", confidence=0.8))
    assert ok.intent == "price" and ok.entities.product_name == "lal saree" and ok.entities.size is None
    assert Understanding.model_validate(und("other", product="  ")).entities.product_name is None  # blank -> None
    for bad in (und("refund"), und("price", confidence=1.5), {"intent": "price"}, {}):
        with pytest.raises(Exception):
            Understanding.model_validate(bad)


def test_understand_retries_once_on_invalid_output():
    llm = ScriptedLLM(understand=[{"intent": "nonsense"}, und("price", product="saree")])
    out = understand(llm, "saree price?", [])
    assert out.understanding.intent == "price" and len(out.usage) == 2
    assert "invalid" in llm.calls[1][2] and "invalid" not in llm.calls[0][2]


def test_understand_gives_up_after_one_retry():
    llm = ScriptedLLM(understand=[{"bad": 1}])
    out = understand(llm, "hi", [])
    assert out.understanding is None and len(llm.calls) == 2


def test_understand_retries_after_a_provider_error_then_raises():
    llm = ScriptedLLM(understand=[LLMProviderError("boom"), und("price", product="x")])
    assert understand(llm, "x", []).understanding.intent == "price"
    with pytest.raises(LLMProviderError):
        understand(ScriptedLLM(understand=[LLMProviderError("boom")]), "x", [])


# ---------------------------------------------------------------- grounding


def test_number_grounding_check():
    assert numbers_in("৪,৮০০ টাকা and 4800.00 and 12.5") == {numbers_in("4800").pop(), numbers_in("12.5").pop()}
    facts = ["Product: Saree | Price: 4800 BDT | Stock: in stock (6 available overall)"]
    assert ungrounded_numbers("It costs 4,800 BDT and 6 are in stock.", facts) == []
    assert ungrounded_numbers("এর দাম ৪৮০০ টাকা", facts) == []
    assert ungrounded_numbers("It costs 4500 BDT.", facts) == ["4500"]
    assert ungrounded_numbers("Only 3 left at 4800.", facts) == ["3"]
    assert ungrounded_numbers("No numbers here.", facts) == []


def test_write_reply_regenerates_once_then_succeeds():
    llm = ScriptedLLM(reply=[{"reply": "It costs 4500 BDT."}, {"reply": "It costs 4800 BDT."}])
    req = ReplyRequest("price?", "price", "english", ["Price: 4800 BDT"])
    out = write_reply(llm, req)
    assert out.text == "It costs 4800 BDT." and len(out.usage) == 2
    assert "not in the facts" in llm.calls[1][2]


def test_write_reply_gives_up_after_second_bad_reply():
    llm = ScriptedLLM(reply=[{"reply": "4500 BDT"}])
    out = write_reply(llm, ReplyRequest("price?", "price", "english", ["Price: 4800 BDT"]))
    assert out.text is None and out.reason == "reply_not_grounded" and len(llm.calls) == 2


# ------------------------------------------------------------------- engine


def make_engine(llm, gateway=None):
    gateway = gateway or FakeGateway()
    return ConversationEngine(llm, MockEmbeddingProvider(16), gateway), gateway


def ctx(first=False, turns=None):
    return ChatContext("Rina Fashion House", is_first_ai_reply=first, recent_turns=turns or [])


def test_price_reply_uses_catalogue_price_and_logs_usage():
    llm = ScriptedLLM(understand=[und("price", product="red saree")], reply=[{"reply": "Red Jamdani Saree costs 4800 BDT."}])
    engine, gw = make_engine(llm)
    res = engine.process_customer_message(1, ctx(), "red saree price?")
    assert res.reply_text == "Red Jamdani Saree costs 4800 BDT."
    assert (res.intent, res.language_style, res.handover.needed) == ("price", "english", False)
    assert res.extras["product_ids"] == [1]
    assert [t["name"] for t in res.extras["tools"]] == ["search_products"]
    facts = llm.payloads("reply")[0]["facts"]
    assert any("Price: 4800 BDT" in f for f in facts)
    assert [(u.operation, u.provider, u.model) for u in res.usage] == [("intent", "scripted", "scripted-1"), ("chat_reply", "scripted", "scripted-1")]
    assert [u[1] for u in gw.usage] == ["embedding"]  # the query embedding is logged through the gateway


def test_disclosure_only_on_first_reply():
    answers = {"understand": [und("price", product="saree")], "reply": [{"reply": "It costs 4800 BDT."}]}
    first = make_engine(ScriptedLLM(**answers))[0].process_customer_message(1, ctx(first=True), "saree price?")
    assert first.disclosure_included and first.reply_text.startswith("Hi! I'm the automatic assistant of Rina Fashion House")
    assert "ask" in first.reply_text.split("\n\n")[0] and first.reply_text.endswith("It costs 4800 BDT.")
    later = make_engine(ScriptedLLM(**answers))[0].process_customer_message(1, ctx(first=False), "saree price?")
    assert not later.disclosure_included and later.reply_text == "It costs 4800 BDT."


def test_disclosure_matches_customer_style():
    llm = ScriptedLLM(understand=[und("price", product="saree")], reply=[{"reply": "Saree er dam 4800 taka."}])
    res = make_engine(llm)[0].process_customer_message(1, ctx(first=True), "saree er dam koto")
    assert res.language_style == "banglish" and res.reply_text.startswith("Assalamu alaikum! Ami Rina Fashion House-er automatic assistant")


def test_unknown_product_gets_check_with_shop_and_handover():
    llm = ScriptedLLM(understand=[und("price", product="blender")])
    res = make_engine(llm)[0].process_customer_message(1, ctx(), "blender price?")
    assert res.reply_text == CHECK["english"]
    assert (res.handover.needed, res.handover.reason) == (True, "not_in_shop_data")
    assert llm.payloads("reply") == []  # the model was never asked to write something without facts


def test_check_with_shop_is_in_the_customers_style():
    for message, style in [("blender er dam koto", "banglish"), ("ব্লেন্ডারের দাম কত", "bangla")]:
        res = make_engine(ScriptedLLM(understand=[und("price", product="blender")]))[0].process_customer_message(1, ctx(), message)
        assert res.language_style == style and res.reply_text == CHECK[style]


def test_ungrounded_number_regenerates_then_falls_back_with_handover():
    llm = ScriptedLLM(understand=[und("price", product="saree")], reply=[{"reply": "It costs 4500 BDT."}])
    res = make_engine(llm)[0].process_customer_message(1, ctx(), "saree price?")
    assert res.reply_text == CHECK["english"] and res.handover.reason == "reply_not_grounded"
    assert "4500" not in res.reply_text
    assert [u.operation for u in res.usage].count("chat_reply") == 2  # both attempts are logged


def test_size_question_uses_check_stock():
    llm = ScriptedLLM(understand=[und("size_stock", product="panjabi", size="xl")], reply=[{"reply": "XL is available, 24 in stock."}])
    res = make_engine(llm)[0].process_customer_message(1, ctx(), "panjabi XL ache?")
    assert res.entities["size"] == "XL"
    assert [t["name"] for t in res.extras["tools"]] == ["search_products", "check_stock"]
    facts = llm.payloads("reply")[0]["facts"]
    assert any("size XL is offered" in f and "24 available" in f for f in facts)


def test_product_is_remembered_from_the_previous_turn():
    llm = ScriptedLLM(understand=[und("size_stock", product=None, size="XL")], reply=[{"reply": "Yes, XL is offered. 24 in stock."}])
    history = [Turn("customer", "Cotton Panjabi price?", {"product_name": "Cotton Panjabi"}), Turn("ai", "1850 BDT", {"product_name": "Cotton Panjabi"})]
    res = make_engine(llm)[0].process_customer_message(1, ctx(turns=history), "eta ki XL e pawa jabe?")
    assert res.entities["product_name"] == "Cotton Panjabi" and res.extras["product_ids"] == [2]


def test_english_product_form_is_used_to_search_the_catalogue():
    """"লাল শাড়ি" has no word in common with the catalogue; its English form "red saree" does."""
    entities = und("price", product="লাল শাড়ি")
    entities["entities"]["product_name_en"] = "red saree"
    llm = ScriptedLLM(understand=[entities], reply=[{"reply": "Red Jamdani Saree এর দাম 4800 টাকা।"}])  # a Bangla message gets a Bangla reply
    engine, gw = make_engine(llm)
    res = engine.process_customer_message(1, ctx(), "লাল শাড়ির দাম কত?")
    assert ("search_products", 1, "red saree") in gw.calls and res.extras["product_ids"] == [1]
    assert not res.handover.needed and res.entities["product_name_en"] == "red saree"


def test_missing_product_asks_which_product_without_the_llm_reply_step():
    llm = ScriptedLLM(understand=[und("price")])
    res = make_engine(llm)[0].process_customer_message(1, ctx(), "price koto?")
    assert res.reply_text == phrase("ask_product", "banglish") and not res.handover.needed
    assert res.extras["clarification"] == "product" and llm.payloads("reply") == []


def test_delivery_charge_comes_from_policy_tool():
    llm = ScriptedLLM(understand=[und("delivery", area="Khagan")], reply=[{"reply": "Delivery to Khagan is 100 BDT."}])
    res = make_engine(llm)[0].process_customer_message(1, ctx(), "Khagan e delivery charge koto?")
    assert res.reply_text == "Delivery to Khagan is 100 BDT."
    assert llm.payloads("reply")[0]["facts"][0] == "Delivery charge for Khagan: 100 BDT"


def test_delivery_area_not_in_policy_is_not_guessed():
    llm = ScriptedLLM(understand=[und("delivery", area="Sylhet")])
    res = make_engine(llm)[0].process_customer_message(1, ctx(), "Sylhet e delivery charge koto?")
    assert res.reply_text == CHECK["banglish"] and res.handover.reason == "not_in_shop_data"


def test_delivery_without_area_uses_policy_or_asks():
    chunks = [policy_chunk("Shop policy - Delivery time: 1-2 days inside Dhaka")]
    llm = ScriptedLLM(understand=[und("delivery")], reply=[{"reply": "Delivery takes 1-2 days inside Dhaka."}])
    res = make_engine(llm, FakeGateway(chunks=chunks))[0].process_customer_message(1, ctx(), "delivery time koto?")
    assert res.reply_text == "Delivery takes 1-2 days inside Dhaka."
    asked = make_engine(ScriptedLLM(understand=[und("delivery")]), FakeGateway(chunks=[]))[0].process_customer_message(1, ctx(), "delivery koto")
    assert asked.reply_text == phrase("ask_area", "banglish") and not asked.handover.needed


def test_other_questions_use_retrieved_policy_chunks():
    chunks = [policy_chunk("Shop policy - Return rules: Return within 3 days")]
    llm = ScriptedLLM(understand=[und("other")], reply=[{"reply": "You can return within 3 days."}])
    res = make_engine(llm, FakeGateway(chunks=chunks))[0].process_customer_message(1, ctx(), "return policy ki?")
    assert res.reply_text == "You can return within 3 days."
    unrelated = make_engine(ScriptedLLM(understand=[und("other")]), FakeGateway(chunks=[]))[0].process_customer_message(1, ctx(), "who won the match?")
    assert unrelated.reply_text == CHECK["english"] and unrelated.handover.needed


def test_low_scoring_chunks_are_ignored():
    chunks = [policy_chunk("Shop policy - Return rules: Return within 3 days", score=0.05)]
    res = make_engine(ScriptedLLM(understand=[und("other")]), FakeGateway(chunks=chunks))[0].process_customer_message(1, ctx(), "weather?")
    assert res.handover.needed and res.handover.reason == "not_in_shop_data"


def test_greeting_needs_no_handover():
    res = make_engine(ScriptedLLM(understand=[und("other")]))[0].process_customer_message(1, ctx(), "Hello")
    assert res.reply_text == phrase("greeting", "english") and not res.handover.needed


def test_complaint_gets_the_safe_reply_only():
    llm = ScriptedLLM(understand=[und("complaint", product="saree")])
    res = make_engine(llm)[0].process_customer_message(1, ctx(), "product ta kharap chilo")
    assert res.reply_text == CHECK["banglish"] and (res.handover.needed, res.handover.reason) == (True, "complaint")
    assert llm.payloads("reply") == []


def test_unusable_understanding_hands_over():
    res = make_engine(ScriptedLLM(understand=[{"junk": True}]))[0].process_customer_message(1, ctx(), "???")
    assert res.reply_text == CHECK["english"] and res.handover.reason == "understanding_failed"


def test_llm_outage_falls_back_safely():
    res = make_engine(ScriptedLLM(understand=[LLMProviderError("down")]))[0].process_customer_message(1, ctx(), "price?")
    assert res.reply_text == CHECK["english"] and res.handover.reason == "ai_unavailable"


def test_only_recent_turns_and_no_personal_data_reach_the_llm():
    old = [Turn("customer", f"old message {i} with phone 01700000{i:03d}", {}) for i in range(30)]
    llm = ScriptedLLM(understand=[und("price", product="saree")], reply=[{"reply": "4800 BDT"}])
    make_engine(llm)[0].process_customer_message(1, ctx(turns=old), "saree price?")
    for task in ("understand", "reply"):
        payload = llm.payloads(task)[0]
        assert len(payload["recent_messages"]) == 6
        assert payload["recent_messages"][-1]["text"].startswith("old message 29")
        assert "old message 3 " not in str(payload)
    reply_prompt = llm.calls[-1][2]
    assert "customer_name" not in reply_prompt and "psid" not in reply_prompt.lower()
    assert "Red Jamdani Saree" in reply_prompt and "Cotton Panjabi" not in reply_prompt  # only the matched product


def test_bangla_digits_are_normalised_before_understanding():
    llm = ScriptedLLM(understand=[und("size_stock", product="panjabi", size="৩৮")], reply=[{"reply": "ok"}])
    engine, _ = make_engine(llm)
    engine.process_customer_message(1, ctx(), "panjabi ৩৮ সাইজ আছে?")
    assert llm.payloads("understand")[0]["message"] == "panjabi 38 সাইজ আছে?"


# ---------------------------------------------- the mock LLM through the engine


@pytest.mark.parametrize(
    "message,intent",
    [
        ("Red Jamdani Saree price koto?", "price"),
        ("Cotton Panjabi XL ache?", "size_stock"),
        ("Khagan e delivery charge koto?", "delivery"),
        ("ami Cotton Panjabi nibo", "order"),
        ("product ta kharap chilo", "complaint"),
        ("kono saree dekhan", "suggestion"),
    ],
)
def test_mock_llm_understands_the_proposal_examples(message, intent):
    out = understand(MockLLMProvider(), message, [])
    assert out.understanding.intent == intent


def test_mock_llm_end_to_end_answers_from_catalogue():
    engine, _ = make_engine(MockLLMProvider())
    price = engine.process_customer_message(1, ctx(first=True), "Red Jamdani Saree price koto?")
    assert "4800" in price.reply_text and "Red Jamdani Saree" in price.reply_text and price.disclosure_included
    size = engine.process_customer_message(1, ctx(), "Cotton Panjabi XL ache?")
    assert "XL" in size.reply_text and "24" in size.reply_text
    delivery = engine.process_customer_message(1, ctx(), "Khagan e delivery charge koto?")
    assert "100" in delivery.reply_text and "Khagan" in delivery.reply_text
    out_of_stock = engine.process_customer_message(1, ctx(), "Matte Lipstick ache?")
    assert "stock" in out_of_stock.reply_text.lower() and "0" not in out_of_stock.reply_text.replace("650", "")
    unknown = engine.process_customer_message(1, ctx(), "Blender price koto?")
    assert unknown.reply_text == CHECK["banglish"] and unknown.handover.needed


def test_banglish_reply_in_bangla_script_is_regenerated_then_rejected():
    from shopsathi_ai.reply import script_matches_style

    assert script_matches_style("Saree er dam 4800 taka.", "banglish") and script_matches_style("Price 4800", "english")
    assert not script_matches_style("দাম 4800 টাকা", "banglish") and script_matches_style("দাম 4800 টাকা", "bangla")
    assert not script_matches_style("Saree er dam 4800 taka.", "bangla")  # a Bangla message needs a Bangla reply
    assert script_matches_style("Red Jamdani Saree এর দাম 4800 টাকা", "bangla")

    llm = ScriptedLLM(reply=[{"reply": "দাম 4800 টাকা"}, {"reply": "Saree er dam 4800 taka."}])
    out = write_reply(llm, ReplyRequest("dam koto", "price", "banglish", ["Price: 4800 BDT"]))
    assert out.text == "Saree er dam 4800 taka." and "writing style" in llm.calls[1][2]

    stubborn = write_reply(ScriptedLLM(reply=[{"reply": "দাম 4800 টাকা"}]), ReplyRequest("dam koto", "price", "banglish", ["Price: 4800 BDT"]))
    assert stubborn.text is None and stubborn.reason == "reply_wrong_script"
