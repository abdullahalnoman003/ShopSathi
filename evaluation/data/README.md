# Labelled test cases

One JSON object per line (JSONL). Blank lines and lines starting with `//` or `#` are ignored. The format is described
in `case.schema.json`; `run_eval.py` checks every line and stops with the line number and the problem if one is wrong.

| File | What it is |
|---|---|
| `sample_cases.jsonl` | **About 30 SAMPLE cases that only test the harness.** Every record has `"sample": true`. They use the proposal's examples. They are **not** the team's test set: percentages computed on them say nothing about the product. |
| `test_set.jsonl` | **The team's labelled test set (200 real-style customer messages, proposal section 2).** The team collects and labels it (M1: public shop pages and role-play; M5: labelling). It is not in this repository. It is git-ignored because it may contain real messages: remove names, phone numbers and addresses of real people before using real messages. |

## A case

```json
{"id": "c-0001", "language": "banglish", "type": "intent",
 "messages": ["Red Jamdani Saree er dam koto?"],
 "labels": {"intent": "price", "answer": {"prices": [4800]}}}
```

| Field | Meaning |
|---|---|
| `id` | unique name of the case |
| `language` | `bangla` (Bangla script), `english`, or `banglish` (Bangla in English letters). Every metric is also reported per language |
| `type` | the main thing the case tests: `intent`, `answer`, `order`, `suggestion`, `handover`. The label group of the same name is required |
| `messages` | the customer's turns, in order. The AI really answers each turn and its replies become the context of the next one, like in a live chat. The labels describe the **last** turn (orders: the end of the conversation). If the AI hands the chat to a person in a turn, the later turns are not run (the AI is paused in production) |
| `labels` | the expected results: any combination of the groups below, whatever the `type` |
| `sample`, `note` | optional |

### Labels

| Group | Fields | Measured as |
|---|---|---|
| `intent` | one of `price`, `size_stock`, `delivery`, `suggestion`, `order`, `complaint`, `other` | **Intent accuracy** (AI-R01, target 85%) |
| `answer` | `prices` (numbers the reply must state exactly), `stock_counts` (same, for stock numbers), `available` (`true`/`false`: the reply must say the product is / is not available) | **Prices and stock values match the catalogue** (AI-R03, target 95%). Each expected value is one check. Every other number in the reply that is not in the catalogue, the policy or the customer's own message counts as a failed check (an invented price). `available` is a keyword check in the three languages: always read the failure list |
| `order` | `fields` (any of `product`, `size`, `colour`, `quantity`, `name`, `phone`, `address`; `null` means "must be empty"), `ready` (is the order complete after the last turn), `phone_invalid` (the customer gave an invalid phone: the AI must ask again and not draft) | **Order field accuracy** (AI-R07, target 90%): each labelled field is one check. **Phone re-ask** (AI-R08, 100%). Order completion (reported) |
| `suggestion` | `max_price`, `must_include`, `must_not_include` (product names), `expect_none` | Suggestion quality (reported). **Zero-stock suggestions** (AI-R06, no violations) are checked in **every** case, whatever its labels |
| `handover` | `flag` (should the chat go to a person), `reason` (one of the seven flag reasons) | **Flag precision and recall** and **reason accuracy** (reported: the proposal gives no number for AI-R04/AI-R10). Precision only counts cases that carry a `handover` label, so label a good number of "no flag" cases too |

Prices, stock and delivery charges must agree with `../fixtures/shop_catalogue.json` and `../fixtures/shop_policy.json`
(a test checks the sample labels against them). Change the fixtures and the labels together.

## Labelling advice

* Cover Bangla script, English and Banglish about equally: accuracy is reported for each (proposal 5.3).
* Mix easy and hard messages (spelling mistakes, short forms, numbers in Bangla digits, two questions in one message).
* Label what a careful human shop assistant would do, not what the AI currently does. Do not tune the labels to the output.
* Keep one case to one purpose, and write a `note` for anything ambiguous.
