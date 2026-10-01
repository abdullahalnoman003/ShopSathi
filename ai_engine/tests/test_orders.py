from decimal import Decimal

import pytest

from shopsathi_ai.engine import ChatContext, ConversationEngine
from shopsathi_ai.extraction import OrderExtraction, extract_order
from shopsathi_ai.interfaces import ProductInfo
from shopsathi_ai.phrases import phrase
from shopsathi_ai.providers.base import LLMProviderError
from shopsathi_ai.providers.mock import MockEmbeddingProvider, MockLLMProvider
from shopsathi_ai.understanding import Turn
from tests.helpers import CHECK, FakeGateway, ScriptedLLM, und

PANJABI = ProductInfo(2, "Cotton Panjabi", Decimal("1850"), ["M", "L", "XL"], ["White", "Navy"], 24)
EID = ProductInfo(5, "Eid Special Panjabi", Decimal("1450"), ["M", "L"], ["White"], 8)
SAREE = ProductInfo(1, "Red Jamdani Saree", Decimal("4800.00"), [], ["Red"], 6)
MUG = ProductInfo(7, "Plain Mug", Decimal("150"), [], [], 3)
LIPSTICK = ProductInfo(3, "Matte Lipstick", Decimal("650"), [], ["Rose"], 0)
CATALOGUE = [PANJABI, SAREE, MUG, LIPSTICK]

PHONE = "01712345678"
ADDRESS = "House 5, Road 3, Mirpur 10, Dhaka"


def ex(**kw):
    base = {k: None for k in ("product", "product_en", "size", "colour", "quantity", "name", "phone", "address")}
    base["missing_fields"] = []
    base.update(kw)
    return base


def engine(llm, products=CATALOGUE):
    gw = FakeGateway(products=products)
    return ConversationEngine(llm, MockEmbeddingProvider(8), gw), gw


def ctx(pending=None, turns=None, first=False):
    return ChatContext("Rina Fashion House", is_first_ai_reply=first, recent_turns=turns or [], pending_order=pending)


def run(message, extraction, intent="order", pending=None, turns=None, first=False, products=CATALOGUE, style_words=None):
    llm = ScriptedLLM(understand=[und(intent)], order=[extraction])
    eng, gw = engine(llm, products)
    return eng.process_customer_message(1, ctx(pending, turns, first), message), llm, gw


FULL = dict(product="Cotton Panjabi", size="XL", colour="Navy", quantity=2, name="Rahim Uddin", phone=PHONE, address=ADDRESS)
FULL_TEXT = f"Cotton Panjabi XL Navy quantity 2, Rahim Uddin, {PHONE}, {ADDRESS}"


def pending_of(**kw):
    base = {"product_id": 2, "product_name": "Cotton Panjabi", "size": "XL", "colour": "Navy", "quantity": 2, "name": "Rahim Uddin", "phone": PHONE, "address": ADDRESS}
    base.update(kw)
    return base


# ------------------------------------------------------ asking for what is missing (AI-R09)


def test_asks_only_for_the_missing_fields_with_the_shops_options():
    res, _, _ = run("I want to order the Cotton Panjabi", ex(product="Cotton Panjabi"))
    text = res.reply_text
    assert "size (M, L, XL)" in text and "colour (White, Navy)" in text
    for needed in ("how many", "your name", "11-digit mobile number", "delivery address"):
        assert needed in text
    assert "which product" not in text  # the product is known
    assert "order_ready" not in res.extras and res.extras["order_missing"] == ["size", "colour", "quantity", "name", "phone", "address"]
    assert res.pending_order["product_id"] == 2 and res.pending_order["product_name"] == "Cotton Panjabi"
    assert res.intent == "order" and not res.handover.needed


def test_nothing_known_asks_for_the_product_first():
    res, _, _ = run("I want to order something", ex())
    assert "which product you want" in res.reply_text and res.pending_order is None


def test_size_and_colour_are_not_asked_when_the_product_has_none():
    mug, _, _ = run("I want to order the Plain Mug", ex(product="Plain Mug"))
    assert "size" not in mug.reply_text and "colour" not in mug.reply_text and "how many" in mug.reply_text
    saree, _, _ = run("I want to order the Red Jamdani Saree", ex(product="Red Jamdani Saree"))
    assert "size" not in saree.reply_text and "colour (Red)" in saree.reply_text


def test_questions_follow_the_customers_style():
    banglish, _, _ = run("Cotton Panjabi nibo", ex(product="Cotton Panjabi"))
    assert "Dhonnobad! Order ta ready korte aro lagbe" in banglish.reply_text and "apnar naam" in banglish.reply_text
    bangla, _, _ = run("কটন পাঞ্জাবি নিব", ex(product="Cotton Panjabi", product_en="Cotton Panjabi"))
    assert "ধন্যবাদ! অর্ডারটি তৈরি করতে আরও লাগবে" in bangla.reply_text and "আপনার নাম" in bangla.reply_text
    english, _, _ = run("I want to order the Cotton Panjabi", ex(product="Cotton Panjabi"))
    assert english.reply_text.startswith("Thanks! To prepare your order I still need")


def test_pending_fields_are_merged_across_turns_and_only_new_gaps_are_asked():
    first, _, _ = run("I want to order the Cotton Panjabi, XL Navy", ex(product="Cotton Panjabi", size="XL", colour="Navy"))
    second, _, _ = run("2 pieces, Name: Rahim Uddin", ex(quantity=2, name="Rahim Uddin"), intent="other", pending=first.pending_order)
    assert second.pending_order["size"] == "XL" and second.pending_order["quantity"] == 2 and second.pending_order["name"] == "Rahim Uddin"
    assert second.extras["order_missing"] == ["phone", "address"] and "11-digit" in second.reply_text and "how many" not in second.reply_text


# ---------------------------------------------------------------- phone check (AI-R08)


@pytest.mark.parametrize("bad", ["1712345678", "0171234567", "01212345678", "017123456789", "abc"])
def test_invalid_phone_is_asked_again(bad):
    pending = pending_of(phone=None)
    res, _, _ = run(f"my number is {bad}", ex(phone=bad), intent="other", pending=pending)
    assert "does not look right" in res.reply_text and "01XXXXXXXXX" in res.reply_text
    assert res.pending_order["phone"] is None and "order_ready" not in res.extras
    assert res.extras["order_missing"] == ["phone"]


def test_invalid_phone_reask_in_banglish_and_bangla():
    pending = pending_of(phone=None)
    res, _, _ = run("phone 1712345678 ta", ex(phone="1712345678"), intent="other", pending=pending)
    assert "Ei phone number ta thik mone hocche na" in res.reply_text
    res, _, _ = run("ফোন ১৭১২৩৪৫৬৭৮", ex(phone="১৭১২৩৪৫৬৭৮"), intent="other", pending=pending)
    assert "এই ফোন নম্বরটি সঠিক মনে হচ্ছে না" in res.reply_text


def test_bangla_digit_phone_is_accepted_and_normalised():
    pending = pending_of(phone=None)
    res, _, _ = run("আমার নম্বর ০১৭১২৩৪৫৬৭৮", ex(phone="০১৭১২৩৪৫৬৭৮"), intent="other", pending=pending)
    assert res.extras["order_ready"]["customer_phone"] == PHONE


def test_phone_with_country_code_and_dashes_is_accepted():
    pending = pending_of(phone=None)
    res, _, _ = run("+88 017-1234-5678", ex(phone="+88 017-1234-5678"), intent="other", pending=pending)
    assert res.extras["order_ready"]["customer_phone"] == PHONE


# ---------------------------------------------------------- checks against the shops data


def test_size_not_in_the_products_options_is_rejected():
    res, _, _ = run("I want the Cotton Panjabi in XXL", ex(product="Cotton Panjabi", size="XXL"))
    assert "Size XXL is not available for Cotton Panjabi. Available: M, L, XL." in res.reply_text
    assert res.pending_order["size"] is None and "size" in res.extras["order_missing"]


def test_colour_not_in_the_products_options_is_rejected():
    res, _, _ = run("I want the Cotton Panjabi in Pink", ex(product="Cotton Panjabi", colour="Pink"))
    assert "Colour Pink is not available for Cotton Panjabi. Available: White, Navy." in res.reply_text


def test_size_matching_ignores_case_and_uses_the_catalogue_spelling():
    res, _, _ = run("xl", ex(size="xl", colour="navy"), intent="other", pending=pending_of(size=None, colour=None))
    assert res.extras["order_ready"]["size"] == "XL" and res.extras["order_ready"]["colour"] == "Navy"


@pytest.mark.parametrize("qty", [0, -2, 1001])
def test_quantity_must_be_a_positive_whole_number(qty):
    res, _, _ = run("quantity please", ex(quantity=qty), intent="other", pending=pending_of(quantity=None))
    assert res.intent == "order"
    assert "how many" in res.reply_text and res.pending_order["quantity"] is None and "order_ready" not in res.extras


def test_quantity_above_the_catalogue_stock_is_refused():
    res, _, _ = run("30 pieces", ex(quantity=30), intent="other", pending=pending_of(quantity=None))
    assert "only 24 of Cotton Panjabi in stock" in res.reply_text and "order_ready" not in res.extras


def test_ambiguous_product_asks_which_one():
    products = CATALOGUE + [EID]
    res, _, _ = run("I want to order a panjabi", ex(product="panjabi"), products=products)
    assert "Which one would you like: Cotton Panjabi, Eid Special Panjabi?" in res.reply_text
    assert res.pending_order is None or res.pending_order.get("product_id") is None


def test_unknown_product_is_not_guessed():
    res, _, _ = run("laptop nibo", ex(product="laptop"))
    assert res.reply_text == CHECK["banglish"] and (res.handover.needed, res.handover.reason) == (True, "not_in_shop_data")
    assert "order_ready" not in res.extras


def test_out_of_stock_product_is_not_drafted_and_the_data_says_so():
    res, _, _ = run(f"I want the Matte Lipstick, Rahim Uddin, {PHONE}, {ADDRESS}", ex(product="Matte Lipstick", quantity=1, name="Rahim Uddin", phone=PHONE, address=ADDRESS))
    assert "Matte Lipstick is out of stock right now" in res.reply_text
    assert "order_ready" not in res.extras
    assert not res.pending_order or res.pending_order.get("product_id") is None


def test_product_going_out_of_stock_during_collection_stops_the_draft():
    sold_out = ProductInfo(2, "Cotton Panjabi", Decimal("1850"), ["M", "L", "XL"], ["White", "Navy"], 0)
    res, _, _ = run("phone", ex(phone=PHONE), intent="other", pending=pending_of(phone=None), products=[sold_out])
    assert "out of stock" in res.reply_text and "order_ready" not in res.extras


def test_changing_the_product_resets_size_and_colour():
    res, _, _ = run("I want the Plain Mug instead", ex(product="Plain Mug"), pending=pending_of(phone=None))
    assert res.pending_order["product_id"] == 7 and res.pending_order["size"] is None and res.pending_order["colour"] is None


def test_product_can_come_from_the_previous_turns():
    turns = [Turn("customer", "Cotton Panjabi price koto?", {"product_name": "Cotton Panjabi"}), Turn("ai", "1850 BDT", {"product_name": "Cotton Panjabi"})]
    res, _, _ = run("ami eta nibo", ex(), turns=turns)
    assert res.pending_order["product_id"] == 2


# ------------------------------------- values must really come from the customer (no inventing)


def test_name_phone_and_address_the_customer_never_wrote_are_dropped():
    res, _, _ = run("Cotton Panjabi nibo", ex(product="Cotton Panjabi", size="XL", colour="Navy", quantity=1, name="Karim Hossain", phone="01812345678", address="Dhanmondi 27 Dhaka"))
    assert res.pending_order["name"] is None and res.pending_order["phone"] is None and res.pending_order["address"] is None
    assert "order_ready" not in res.extras and "does not look right" not in res.reply_text


# ------------------------------------------------------------- the finished draft


def test_complete_order_produces_order_ready_and_clears_the_pending_state():
    res, llm, _ = run("I want to order: " + FULL_TEXT, ex(**FULL))
    ready = res.extras["order_ready"]
    assert ready == {
        "product_id": 2,
        "product_name": "Cotton Panjabi",
        "size": "XL",
        "colour": "Navy",
        "quantity": 2,
        "unit_price": 1850.0,  # the catalogue price, not something the customer or the model said
        "customer_name": "Rahim Uddin",
        "customer_phone": PHONE,
        "customer_address": ADDRESS,
    }
    assert res.pending_order is None and res.extras["order_missing"] == [] and not res.handover.needed
    assert "sent your order details to the shop for confirmation" in res.reply_text
    for line in ("Product: Cotton Panjabi", "Size: XL", "Colour: Navy", "Quantity: 2", "Price: 1850 BDT each", f"Phone: {PHONE}"):
        assert line in res.reply_text
    assert [u.operation for u in res.usage] == ["intent", "order_extraction"]  # no LLM call is needed to write the reply
    assert [t["name"] for t in res.extras["tools"]][-1] == "update_order_draft"


@pytest.mark.parametrize("text", ["I want to order it", "ami nibo", "আমি নিব"])
def test_reply_never_says_the_order_is_confirmed_or_mentions_discounts(text):
    for ex_kwargs, intent in ((FULL, "order"),):
        res, _, _ = run(f"{text} {FULL_TEXT}", ex(**ex_kwargs), intent=intent)
        low = res.reply_text.lower()
        for banned in ("confirmed", "discount", "offer", "free delivery", "kom dam", "ছাড়", "নিশ্চিত হয়েছে", "কনফার্ম"):
            assert banned not in low
        assert "order_ready" in res.extras


def test_all_three_styles_of_the_ready_reply_are_safe():
    for message, expect in [("ami nibo", "Dhonnobad! Apnar order-er details"), ("আমি এই পণ্যটি অর্ডার করতে চাই, আমার তথ্য নিচে দিলাম", "ধন্যবাদ! আপনার অর্ডারের তথ্য নিশ্চিতকরণের জন্য"), ("I want to order", "Thank you! I have sent")]:
        res, _, _ = run(f"{message} {FULL_TEXT}", ex(**FULL))
        assert expect in res.reply_text and "order_ready" in res.extras
        assert "confirmed" not in res.reply_text.lower() and "discount" not in res.reply_text.lower()


def test_the_reply_only_contains_numbers_from_the_order_and_the_catalogue():
    import re

    res, _, _ = run(FULL_TEXT, ex(**FULL))
    allowed = {"2", "1850", PHONE, "5", "3", "10"}  # quantity, catalogue price, phone, and the numbers in the address
    assert set(re.findall(r"\d+", res.reply_text)) <= allowed


def test_first_reply_has_the_disclosure_even_for_an_order():
    res, _, _ = run("Cotton Panjabi nibo", ex(product="Cotton Panjabi"), first=True)
    assert res.disclosure_included and res.reply_text.startswith("Assalamu alaikum! Ami Rina Fashion House-er automatic assistant")


# ------------------------------------------------------- during collection, other messages


def test_a_question_in_the_middle_is_answered_and_the_pending_order_is_kept():
    pending = pending_of(phone=None, address=None)
    llm = ScriptedLLM(understand=[und("delivery", area="Khagan")], order=[ex()], reply=[{"reply": "Delivery to Khagan is 100 BDT."}])
    eng, _ = engine(llm)
    res = eng.process_customer_message(1, ctx(pending), "Khagan e delivery charge koto?")
    assert res.reply_text == "Delivery to Khagan is 100 BDT." and res.intent == "delivery"
    assert res.pending_order == pending  # untouched


def test_a_complaint_in_the_middle_is_handed_over_and_the_pending_order_is_kept():
    pending = pending_of(phone=None)
    llm = ScriptedLLM(understand=[und("complaint")], order=[ex()])
    res = engine(llm)[0].process_customer_message(1, ctx(pending), "ager order e problem chilo")
    assert res.handover.reason == "complaint" and res.pending_order == pending


def test_unusable_extraction_is_safe():
    res, _, _ = run("ami nibo", {"quantity": "many"})
    assert res.reply_text == CHECK["banglish"] and res.handover.reason == "order_extraction_failed"
    mid, _, _ = run("hello", {"quantity": "many"}, intent="other", pending=pending_of(phone=None))
    assert mid.pending_order is not None and not mid.reply_text.startswith("Thanks! To prepare")  # fell through to normal handling


def test_llm_outage_is_safe():
    llm = ScriptedLLM(understand=[und("order")], order=[LLMProviderError("down")])
    res = engine(llm)[0].process_customer_message(1, ctx(), "ami nibo")
    assert res.handover.reason == "ai_unavailable" and "order_ready" not in res.extras


def test_order_extraction_is_logged_as_its_own_operation():
    res, _, _ = run("Cotton Panjabi nibo", ex(product="Cotton Panjabi"))
    assert [u.operation for u in res.usage] == ["intent", "order_extraction"]


def test_extract_order_validates_and_only_sends_recent_turns():
    llm = ScriptedLLM(order=[{"quantity": "many"}, ex(product="Plain Mug", quantity="2")])
    turns = [Turn("customer", f"message {i} 01711111{i:03d}", {}) for i in range(30)]
    out = extract_order(llm, turns, {"product_name": "Plain Mug", "ignored": 1}, "2 ta", max_turns=6)
    assert out.extraction.quantity == 2 and out.extraction.product == "Plain Mug" and len(out.usage) == 1 or len(llm.calls) == 2
    payload = llm.payloads("order")[0]
    assert len(payload["conversation"]) == 6 and payload["pending"] == {"product_name": "Plain Mug"}
    assert OrderExtraction.model_validate(ex(quantity="3")).quantity == 3


# -------------------------------------------------------------- the mock LLM end to end


def test_mock_llm_collects_a_whole_order_piece_by_piece():
    eng, gw = engine(MockLLMProvider())
    pending, turns = None, []
    steps = [
        "Cotton Panjabi nibo",
        "XL Navy 2 ta",
        "Name: Rahim Uddin",
        "Phone: 0171234567",  # 10 digits: must be asked again
        "Phone: ০১৭১২৩৪৫৬৭৮",
        f"Address: {ADDRESS}",
    ]
    results = []
    for message in steps:
        res = eng.process_customer_message(1, ctx(pending, turns), message)
        results.append(res)
        pending = res.pending_order
        turns = turns + [Turn("customer", message, {}), Turn("ai", res.reply_text, {})]
    assert "size (M, L, XL)" in results[0].reply_text
    assert results[1].extras["order_missing"] == ["name", "phone", "address"]
    assert results[2].extras["order_missing"] == ["phone", "address"]
    assert "Ei phone number ta thik mone hocche na" in results[3].reply_text and "order_ready" not in results[3].extras
    assert results[4].extras["order_missing"] == ["address"] and results[4].pending_order["phone"] == PHONE
    ready = results[5].extras["order_ready"]
    assert (ready["product_name"], ready["size"], ready["colour"], ready["quantity"]) == ("Cotton Panjabi", "XL", "Navy", 2)
    assert ready["customer_phone"] == PHONE and ready["customer_address"] == ADDRESS and ready["unit_price"] == 1850.0
    assert results[5].pending_order is None
    assert all("confirmed" not in r.reply_text.lower() for r in results)


def test_data_only_messages_keep_the_style_of_the_conversation_while_an_order_is_collected():
    history = [Turn("customer", "Cotton Panjabi nibo", {}), Turn("ai", "Order ta ready korte aro lagbe", {}), Turn("customer", "amar nam Rahim", {})]
    pending = pending_of(phone=None, address=None)
    res, _, _ = run(f"Phone: {PHONE}", ex(phone=PHONE), intent="other", pending=pending, turns=history)
    assert res.language_style == "banglish" and "Dhonnobad! Order ta ready korte aro lagbe: apnar puro delivery address." in res.reply_text
    # a customer who really writes in English stays in English
    english = [Turn("customer", "I want the Cotton Panjabi", {}), Turn("ai", "Thanks!", {})]
    res, _, _ = run(f"Phone: {PHONE}", ex(phone=PHONE), intent="other", pending=pending, turns=english)
    assert res.language_style == "english" and res.reply_text.startswith("Thanks! To prepare your order")
    # without a pending order nothing is inherited
    res, _, _ = run(f"Phone: {PHONE}", ex(), intent="other", pending=None, turns=history)
    assert res.language_style == "english"
