import pytest

from shopsathi_ai.engine import ChatContext, ConversationEngine
from shopsathi_ai.handover import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    FLAG_REASONS,
    EngineState,
    decide_handover,
    detect_terms,
    reason_for_failure,
)
from shopsathi_ai.phrases import phrase
from shopsathi_ai.providers.mock import MockEmbeddingProvider, MockLLMProvider
from shopsathi_ai.understanding import Understanding
from tests.helpers import FakeGateway, ScriptedLLM, und


def u(intent="price", confidence=0.9, **flags) -> Understanding:
    return Understanding.model_validate({**und(intent, confidence=confidence), **flags})


# ------------------------------------------------------------------- the decision


def test_the_flag_reasons_are_exactly_the_agreed_set():
    assert set(FLAG_REASONS) == {
        "complaint", "refund", "abusive_language", "low_confidence", "off_topic", "not_in_shop_data", "human_requested",
    }
    assert set(reason_for_failure(d) for d in ("ai_unavailable", "understanding_failed", "reply_not_grounded", "order_extraction_failed", "x")) == {"low_confidence"}
    assert reason_for_failure("order_product_unavailable") == "not_in_shop_data"


def test_a_normal_message_is_not_flagged():
    for message, understanding in [
        ("Red Jamdani Saree price koto?", u("price")),
        ("Cotton Panjabi XL ache?", u("size_stock")),
        ("Khagan e delivery charge koto?", u("delivery")),
        ("panjabi dekhan 1500 er moddhe", u("suggestion")),
        ("ami Cotton Panjabi nibo", u("order")),
        ("return policy ki?", u("other")),
        ("refund policy ki?", u("other")),
        ("How long does delivery take?", u("delivery", confidence=0.5)),
    ]:
        assert decide_handover(message, understanding) == decide_handover(message, understanding, EngineState())
        assert not decide_handover(message, understanding).flag, message


@pytest.mark.parametrize(
    "message,understanding,reason",
    [
        ("product ta kharap chilo", u("complaint"), "complaint"),
        ("I want a refund", u("other", refund_request=True), "refund"),  # the model saw it
        ("I want a refund", u("other"), "refund"),  # the code saw it even if the model did not
        ("taka ferot den", u("other"), "refund"),
        ("টাকা ফেরত চাই", u("other"), "refund"),
        ("tui harami", u("other"), "abusive_language"),
        ("You are an idiot", u("other"), "abusive_language"),
        ("তুমি একটা হারামি", u("other"), "abusive_language"),
        ("hello", u("other", abusive_language=True), "abusive_language"),
        ("I want to talk to a person", u("other"), "human_requested"),
        ("ami manusher sathe kotha bolte chai", u("other"), "human_requested"),
        ("আমি মালিকের সাথে কথা বলতে চাই", u("other"), "human_requested"),
        ("hello", u("other", human_requested=True), "human_requested"),
        ("who won the cricket match?", u("other", off_topic=True), "off_topic"),
        ("???", u("other", confidence=0.2), "low_confidence"),
        ("blender price", u("price", confidence=0.49), "low_confidence"),
    ],
)
def test_each_reason_flags_the_chat(message, understanding, reason):
    decision = decide_handover(message, understanding)
    assert decision.flag and decision.reason == reason


def test_not_in_shop_data_flags_through_the_engine_state():
    assert decide_handover("blender price", u("price"), EngineState(not_in_shop_data=True)).reason == "not_in_shop_data"
    assert not decide_handover("blender price", u("price"), EngineState()).flag


def test_priority_when_several_reasons_apply():
    both = u("complaint", refund_request=True, abusive_language=True, human_requested=True, off_topic=True, confidence=0.1)
    assert decide_handover("x", both, EngineState(not_in_shop_data=True)).reason == "abusive_language"
    assert decide_handover("x", u("complaint", refund_request=True)).reason == "refund"
    assert decide_handover("x", u("complaint", human_requested=True)).reason == "complaint"
    assert decide_handover("x", u("other", human_requested=True, off_topic=True)).reason == "human_requested"
    assert decide_handover("x", u("other", off_topic=True, confidence=0.1)).reason == "off_topic"
    assert decide_handover("x", u("price", confidence=0.1), EngineState(not_in_shop_data=True)).reason == "low_confidence"


def test_the_confidence_threshold_is_configurable():
    shaky = u("price", confidence=0.6)
    assert not decide_handover("x", shaky).flag  # default threshold 0.5
    assert decide_handover("x", shaky, EngineState(confidence_threshold=0.7)).reason == "low_confidence"
    assert not decide_handover("x", u("price", confidence=0.7), EngineState(confidence_threshold=0.7)).flag  # equal is fine
    assert DEFAULT_CONFIDENCE_THRESHOLD == 0.5


def test_a_failed_understanding_counts_as_low_confidence_but_abuse_is_still_seen():
    assert decide_handover("???", None).reason == "low_confidence"
    assert decide_handover("tui harami", None).reason == "abusive_language"


def test_short_answers_during_an_order_are_not_low_confidence():
    answer = u("other", confidence=0.3)
    assert decide_handover("Rahim Uddin", answer).reason == "low_confidence"
    assert not decide_handover("Rahim Uddin", answer, EngineState(order_in_progress=True)).flag


def test_term_detection_is_precise():
    assert detect_terms("I want a refund please") == {"refund"}
    assert detect_terms("what is your refund policy?") == set()
    assert detect_terms("can I return this? return rules ki?") == set()
    assert detect_terms("Fuck this") == {"abusive"}
    assert detect_terms("classic shirt") == set()  # 'ass' inside a word is not abuse
    assert detect_terms("talk   to   someone") == {"human"}
    assert detect_terms("price koto? XL ache?") == set()


# ---------------------------------------------------------- the engine: holding replies


def make_engine(llm):
    return ConversationEngine(llm, MockEmbeddingProvider(8), FakeGateway())


def ctx(first=False):
    return ChatContext("Rina Fashion House", is_first_ai_reply=first)


@pytest.mark.parametrize(
    "message,understanding,reason,phrase_name",
    [
        ("product ta kharap chilo", und("complaint"), "complaint", "holding_complaint"),
        ("I want a refund for my order", und("other"), "refund", "holding_complaint"),
        ("you are an idiot", und("other"), "abusive_language", "holding_abusive"),
        ("I want to talk to a person", und("other"), "human_requested", "holding_human"),
        ("who won the cricket match?", {**und("other"), "off_topic": True}, "off_topic", "holding_off_topic"),
        ("blah blah", und("other", confidence=0.2), "low_confidence", "check_with_shop"),
    ],
)
def test_the_engine_flags_with_a_polite_holding_reply(message, understanding, reason, phrase_name):
    llm = ScriptedLLM(understand=[understanding])
    res = make_engine(llm).process_customer_message(1, ctx(), message)
    assert res.handover.needed and res.handover.reason == reason
    assert res.reply_text == phrase(phrase_name, res.language_style)
    assert llm.payloads("reply") == []  # no model-written reply: nothing can be promised


def test_the_shop_data_gap_flags_as_not_in_shop_data():
    res = make_engine(ScriptedLLM(understand=[und("price", product="blender")])).process_customer_message(1, ctx(), "blender price?")
    assert (res.handover.needed, res.handover.reason) == (True, "not_in_shop_data")
    assert res.reply_text == phrase("check_with_shop", "english")


@pytest.mark.parametrize("style,message", [("english", "I want a refund"), ("banglish", "ami refund chai"), ("bangla", "আমি টাকা ফেরত চাই")])
def test_holding_replies_follow_the_customers_style_and_promise_nothing(style, message):
    res = make_engine(ScriptedLLM(understand=[und("other")])).process_customer_message(1, ctx(), message)
    assert res.language_style == style and res.reply_text == phrase("holding_complaint", style)
    low = res.reply_text.lower()
    for banned in ("will refund", "refund you", "full refund", "discount", "free", "guarantee", "replacement", "ফেরত দেব", "ছাড়"):
        assert banned not in low
    assert not any(ch.isdigit() for ch in res.reply_text)  # no amounts, no deadlines


def test_every_holding_phrase_exists_in_all_styles_and_is_short():
    for name in ("holding_complaint", "holding_abusive", "holding_human", "holding_off_topic", "check_with_shop"):
        for style in ("english", "banglish", "bangla"):
            text = phrase(name, style)
            assert text and len(text) < 200


def test_the_disclosure_still_comes_first_in_a_flagged_first_reply():
    res = make_engine(ScriptedLLM(understand=[und("complaint")])).process_customer_message(1, ctx(first=True), "product ta kharap")
    assert res.disclosure_included and res.reply_text.endswith(phrase("holding_complaint", res.language_style))


def test_greetings_are_never_flagged_even_with_low_confidence():
    res = make_engine(ScriptedLLM(understand=[und("other", confidence=0.1)])).process_customer_message(1, ctx(), "Hello")
    assert not res.handover.needed and res.reply_text == phrase("greeting", "english")


def test_a_complaint_while_an_order_is_collected_keeps_the_pending_order():
    pending = {"product_id": 2, "product_name": "Cotton Panjabi", "size": "XL"}
    res = make_engine(ScriptedLLM(understand=[und("complaint")])).process_customer_message(
        1, ChatContext("Rina", pending_order=pending), "ager order e problem chilo"
    )
    assert res.handover.reason == "complaint" and res.pending_order == pending


def test_the_engine_uses_the_configured_confidence_threshold():
    from shopsathi_ai.engine import EngineConfig

    llm = ScriptedLLM(understand=[und("price", product="saree", confidence=0.6)], reply=[{"reply": "Red Jamdani Saree costs 4800 BDT."}])
    strict = ConversationEngine(llm, MockEmbeddingProvider(8), FakeGateway(), EngineConfig(confidence_threshold=0.7))
    assert strict.process_customer_message(1, ctx(), "saree price?").handover.reason == "low_confidence"
    llm2 = ScriptedLLM(understand=[und("price", product="saree", confidence=0.6)], reply=[{"reply": "Red Jamdani Saree costs 4800 BDT."}])
    relaxed = ConversationEngine(llm2, MockEmbeddingProvider(8), FakeGateway())
    assert not relaxed.process_customer_message(1, ctx(), "saree price?").handover.needed


def test_mock_llm_flags_the_proposals_hard_cases():
    engine = ConversationEngine(MockLLMProvider(), MockEmbeddingProvider(8), FakeGateway())
    cases = {
        "product ta kharap chilo": "complaint",
        "I want a refund": "refund",
        "tui harami": "abusive_language",
        "I want to talk to a person": "human_requested",
        "who won the cricket match?": "off_topic",
        "???": "low_confidence",
        "Blender price koto?": "not_in_shop_data",
    }
    for message, reason in cases.items():
        res = engine.process_customer_message(1, ctx(), message)
        assert (res.handover.needed, res.handover.reason) == (True, reason), message
    normal = engine.process_customer_message(1, ctx(), "Red Jamdani Saree price koto?")
    assert not normal.handover.needed


@pytest.mark.parametrize(
    "written_intent,flag",
    [("off_topic", "off_topic"), ("Off-Topic", "off_topic"), ("refund", "refund_request"), ("abusive_language", "abusive_language"), ("human_requested", "human_requested")],
)
def test_a_handover_word_written_as_the_intent_is_kept_as_the_flag(written_intent, flag):
    parsed = Understanding.model_validate({**und("other"), "intent": written_intent})
    assert parsed.intent == "other" and getattr(parsed, flag) is True
    assert decide_handover("x", parsed).flag
    with pytest.raises(Exception):
        Understanding.model_validate({**und("other"), "intent": "something_else"})  # unknown intents still fail
