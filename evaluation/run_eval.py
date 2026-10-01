"""Measure the ShopSathi AI against the proposal's accuracy targets with a labelled JSONL test set.

    python run_eval.py --data data/sample_cases.jsonl --provider mock
    python run_eval.py --data data/test_set.jsonl --provider openai --env-file ../backend/.env

The chat model is --provider (mock | openai | gemini); embeddings default to mock for the mock model and openai
otherwise (--embedding-provider). Keys are read from the environment (OPENAI_API_KEY, GEMINI_API_KEY), optionally
loaded from --env-file; they are never printed or written to a report. Uses only the AI engine and the fixture
shop in fixtures/: no backend or database. Reports go to reports/ (Markdown and JSON).
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from evalkit.cases import CaseError, load_cases  # noqa: E402
from evalkit.gateway import load_fixture  # noqa: E402
from evalkit.metrics import METRICS, evaluate  # noqa: E402
from evalkit.report import build_report, timestamp, to_markdown, write_reports  # noqa: E402
from evalkit.runner import build_providers, load_env_file, run_cases  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="the labelled cases, one JSON object per line (see data/README.md)")
    ap.add_argument("--provider", default="mock", choices=["mock", "openai", "gemini"], help="chat model (default: mock, a test double)")
    ap.add_argument("--embedding-provider", choices=["mock", "openai", "local"], default=None)
    ap.add_argument("--model", default=None, help="chat model name, e.g. gpt-4o-mini")
    ap.add_argument("--env-file", default=None, help="a .env file with OPENAI_API_KEY / GEMINI_API_KEY (existing variables win)")
    ap.add_argument("--out-dir", default=str(HERE / "reports"))
    ap.add_argument("--limit", type=int, default=None, help="only the first N cases (a quick try)")
    ap.add_argument("--fail-on-target", action="store_true", help="exit with status 1 when a proposal target is not met (for CI)")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    if args.env_file:
        try:
            load_env_file(args.env_file)
        except OSError as e:
            print(f"Cannot read the env file: {e}", file=sys.stderr)
            return 2
    try:
        cases = load_cases(args.data)
    except (CaseError, OSError) as e:
        print(f"Cannot read the cases: {e}", file=sys.stderr)
        return 2
    if args.limit:
        cases = cases[: args.limit]
    try:
        llm, embedder, settings = build_providers(args.provider, args.embedding_provider, args.model)
    except Exception as e:  # noqa: BLE001 - missing key / package: say it plainly
        print(f"Cannot start the {args.provider} provider: {e}", file=sys.stderr)
        return 2

    fixture = load_fixture()
    print(f"Running {len(cases)} cases with {settings.llm_provider}/{settings.llm_model} (embeddings: {settings.embedding_provider}) ...")
    results, gateway = run_cases(
        cases, llm, embedder, fixture,
        progress=lambda i, n, c: print(f"  [{i}/{n}] {c.id}", flush=True) if i % 10 == 0 or i == n else None,
    )
    evaluation = evaluate(results, fixture)
    shown, stamp = timestamp()
    meta = {
        "timestamp": shown, "data": str(args.data), "llm_provider": settings.llm_provider, "llm_model": settings.llm_model,
        "embedding_provider": settings.embedding_provider, "is_mock": settings.llm_provider == "mock",
        "sample_only": all(c.sample for c in cases), "_usage": [u for u in gateway.usage],
    }
    report = build_report(results, evaluation, meta)
    md_path, json_path = write_reports(report, Path(args.out_dir), stamp)

    print()
    print(to_markdown(report).split("## Failures")[0])
    print(f"Failures: {len(report['failures'])}. Full report: {md_path}")
    print(f"JSON: {json_path}")
    if args.fail_on_target and report["targets_failed"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
