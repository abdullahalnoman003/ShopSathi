"""The Markdown and JSON reports (written to evaluation/reports/, timestamped)."""

import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from evalkit.cases import LANGUAGES
from evalkit.metrics import METRICS, Evaluation, flag_stats
from evalkit.runner import CaseResult

LOW_SAMPLE = 30  # fewer checks than this: the percentage is shaky (the proposal's test set is 200 messages)


def _fmt(stat: dict[str, Any]) -> str:
    if stat["n"] == 0:
        return "no data"
    if stat["unit"] == "violations":
        return f"{stat['value']} of {stat['n']}"
    return f"{stat['value'] * 100:.1f}% ({stat['passed']}/{stat['n']})"


def _mark(stat: dict[str, Any]) -> str:
    return {True: "PASS", False: "FAIL", None: "-"}[stat["ok"]]


def build_report(results: list[CaseResult], evaluation: Evaluation, meta: dict[str, Any]) -> dict[str, Any]:
    """Everything in one JSON-able dict."""
    counts = Counter((r.case.language, r.case.type) for r in results)
    languages = {lang: sum(n for (l, _), n in counts.items() if l == lang) for lang in LANGUAGES}
    types = Counter(r.case.type for r in results)
    failures = []
    by_case = {r.case.id: r for r in results}
    for c in evaluation.failures:
        r = by_case[c.case_id]
        failures.append({
            "case": c.case_id, "language": c.language, "type": r.case.type, "metric": c.metric, "expected": c.expected, "actual": c.actual,
            "detail": c.detail, "messages": r.case.messages, "replies": [t.reply for t in r.turns], "error": r.error,
        })
    meta.pop("_usage", None)
    tokens_in = sum(t.tokens_in for r in results for t in r.turns)
    tokens_out = sum(t.tokens_out for r in results for t in r.turns)
    return {
        "meta": {**meta, "cases": len(results), "by_language": languages, "by_type": dict(types), "seconds": round(sum(r.seconds for r in results), 2)},
        "targets_failed": evaluation.targets_failed,
        "metrics": {
            k: {"ref": METRICS[k]["ref"], "title": METRICS[k]["title"], "target": METRICS[k]["target"], "kind": METRICS[k]["kind"], "results": evaluation.metrics[k]}
            for k in METRICS
        },
        "flag_counts": flag_stats(evaluation.checks),
        "failures": failures,
        "cases": [
            {"id": r.case.id, "language": r.case.language, "type": r.case.type, "sample": r.case.sample, "stopped_after_flag": r.stopped_after_flag, "error": r.error,
             "seconds": round(r.seconds, 2), "turns": [asdict(t) for t in r.turns]}
            for r in results
        ],
        "tokens": {"input": tokens_in, "output": tokens_out},
    }


def to_markdown(report: dict[str, Any]) -> str:
    m = report["meta"]
    lines = [f"# ShopSathi AI evaluation: {m['timestamp']}", ""]
    if m.get("is_mock"):
        lines += ["> **The mock provider was used.** It is a keyword test double, not an AI model: these numbers only prove the harness runs. "
                  "Run with a real provider (`--provider openai`) to measure the AI.", ""]
    if m.get("sample_only"):
        lines += ["> **Only sample cases were evaluated** (every case is marked `sample`). They test the harness; they are not the team's labelled 200-message test set, so none of these percentages is a result for the product.", ""]
    lines += [
        f"- Data: `{m['data']}` ({m['cases']} cases: " + ", ".join(f"{k} {v}" for k, v in m["by_language"].items()) + ")",
        f"- Case types: " + ", ".join(f"{k} {v}" for k, v in m["by_type"].items()),
        f"- Chat model: `{m['llm_provider']}` / `{m['llm_model']}`; embeddings: `{m['embedding_provider']}`",
        f"- Time spent in the engine: {m['seconds']} s; chat-model tokens: {report['tokens']['input']} in / {report['tokens']['output']} out",
        "",
    ]
    failed = report["targets_failed"]
    lines += [("**Targets not met overall: " + ", ".join(f"`{k}`" for k in failed) + "**") if failed else "**All measurable targets met overall.**", ""]
    lines += ["## Results against the proposal targets", "", "| Metric | Proposal | Target | Overall | Bangla | English | Banglish |", "|---|---|---|---|---|---|---|"]
    for key, meta in report["metrics"].items():
        r = meta["results"]
        target = "none (reported)" if meta["target"] is None else ("0 violations" if meta["kind"] == "zero" else f">= {meta['target'] * 100:.0f}%")
        cells = []
        for g in ("overall", *LANGUAGES):
            s = r[g]
            cells.append(f"{_fmt(s)} {_mark(s)}" if meta["target"] is not None else _fmt(s))
        lines.append(f"| {meta['title']} | {meta['ref']} | {target} | " + " | ".join(cells) + " |")
    f = report["flag_counts"]
    lines += ["", f"Flags: {f['flagged']} chats flagged ({f['true_flags']} needed a person, {f['false_flags']} did not); {f['needed_a_person']} chats needed a person, {f['missed']} were missed.", ""]
    thin = sorted({meta["title"] for meta in report["metrics"].values() if meta["kind"] != "info" for s in meta["results"].values() if 0 < s["n"] < LOW_SAMPLE})
    if thin:
        lines += [f"_Some groups have fewer than {LOW_SAMPLE} checks, so their percentage is unreliable (the proposal's test set has 200 messages). Affected: " + "; ".join(thin) + ". The `n` is in each cell._", ""]
    lines += [f"## Failures ({len(report['failures'])}) for prompt improvement", ""]
    if not report["failures"]:
        lines.append("None.")
    for x in report["failures"]:
        lines += [f"### `{x['case']}` ({x['language']}, {x['type']}): {x['metric']}", ""]
        for i, msg in enumerate(x["messages"]):
            lines.append(f"- Customer: {msg}")
            if i < len(x["replies"]):
                lines.append(f"  - AI: {x['replies'][i]}")
        lines += [f"- Expected: `{json.dumps(x['expected'], ensure_ascii=False)}`", f"- Actual: `{json.dumps(x['actual'], ensure_ascii=False)}`"]
        if x["detail"]:
            lines.append(f"- Note: {x['detail']}")
        if x["error"]:
            lines.append(f"- Engine error: {x['error']}")
        lines.append("")
    return "\n".join(lines) + "\n"


def write_reports(report: dict[str, Any], out_dir: Path, stamp: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"report_{stamp}_{report['meta']['llm_provider']}"
    json_path, md_path = base.with_suffix(".json"), base.with_suffix(".md")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md_path.write_text(to_markdown(report), encoding="utf-8")
    return md_path, json_path


def timestamp() -> tuple[str, str]:
    now = datetime.now().astimezone()
    return now.strftime("%Y-%m-%d %H:%M:%S %Z"), now.strftime("%Y%m%d_%H%M%S")
