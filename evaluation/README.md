# ShopSathi AI evaluation

Measures the AI against the proposal's accuracy targets with a labelled test set. It is independent of the backend: it
imports only the AI engine (`shopsathi_ai`) and runs the real `ConversationEngine` against an in-memory shop built from
`fixtures/` (an invented shop with zero-stock items, several sizes and colours, and delivery areas with charges). No
database, no API, no Facebook.

| Target | Proposal | Measured as |
|---|---|---|
| Intent accuracy >= 85% | AI-R01 | share of cases whose intent equals the label |
| Prices and stock in replies match the catalogue >= 95% | AI-R03 | expected values present exactly, no invented numbers |
| Order fields correct >= 90% | AI-R07 | share of labelled order fields that are right |
| No zero-stock product suggested | AI-R06 | violations over every suggestion shown, in every case |
| Invalid phone numbers asked again | AI-R08 | share of invalid-phone cases not drafted and re-asked |
| Flagging | AI-R04, AI-R10 | precision, recall, reason accuracy (reported, no number in the proposal) |

Every metric is reported overall **and for Bangla script, English and Banglish separately** (section 5.3).

## Run it

```bash
cd evaluation
pip install -r requirements.txt            # or use the backend's virtual environment: it already has shopsathi_ai

python run_eval.py --data data/sample_cases.jsonl --provider mock
python run_eval.py --data data/test_set.jsonl --provider openai --env-file ../backend/.env
```

* `--provider mock|openai|gemini` is the chat model. The mock is a keyword **test double, not an AI**: with it a run only proves the harness works. Embeddings default to mock for the mock model and to OpenAI otherwise (`--embedding-provider mock|openai|local`); `--model gpt-4o-mini` picks the model.
* Keys come from the environment (`OPENAI_API_KEY`, `GEMINI_API_KEY`) or from a `.env` file given with `--env-file` (variables that already exist win). They are never printed or written to a report.
* `--limit N` runs the first N cases; `--fail-on-target` exits with status 1 when a proposal target is not met (for CI).
* Reports are written to `reports/` as `report_<timestamp>_<provider>.md` and `.json` (git-ignored). The Markdown has the target table (overall and per language) and **every failed check with the customer messages, the AI's replies, the expected and the actual value**, for prompt improvement. The JSON also has every turn of every case.

A real run calls the model for every turn (about 2-4 calls per message) and, for OpenAI, embeds the fixture shop once: the 32 sample cases took about two minutes. Percentages on fewer than about 30 checks are unreliable; the report says so.

## The test set

The team's 200 labelled messages go in `data/test_set.jsonl` (git-ignored). See `data/README.md` for the format and labelling advice, and `data/sample_cases.jsonl` for examples. **Do not tune prompts on the same cases you report**: keep some cases aside.

## Tests

```bash
cd evaluation
pytest          # metric functions, case-file checks, the fixture gateway, an end-to-end mock run and the command line
```

## Files

```
run_eval.py         command line
evalkit/cases.py    loading and checking the JSONL cases
evalkit/gateway.py  in-memory ShopDataGateway from the fixtures (follows the backend's search rules)
evalkit/runner.py   runs the cases through ConversationEngine (pending order and short-term memory like the backend)
evalkit/metrics.py  the metrics, targets and per-language grouping (pure functions)
evalkit/report.py   Markdown and JSON reports
fixtures/           the evaluation shop: catalogue and policy
data/               case format, sample cases, (the team's test set)
reports/            generated reports
```
