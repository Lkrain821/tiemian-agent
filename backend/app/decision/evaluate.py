"""Explicit opt-in, paid comparison against versioned assessment fixtures.

Run from backend: uv run python -m app.decision.evaluate --output <path>
No live calls are made by pytest or by --validate-only.
"""

import argparse
import asyncio
import json
from pathlib import Path
from statistics import mean
from time import perf_counter

from app.core.settings import Settings
from app.decision.assessment import rubric_targets
from app.decision.client import DeepSeekAssessmentClient, DecisionServiceError, JevDecisionClient
from app.graph.v1.routing import decision_route
from app.llm.client import DeepSeekClient


DEFAULT_CASES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "decision_cases.json"


def load_cases(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    seen = set()
    for case in data["cases"]:
        if case["id"] in seen:
            raise ValueError("duplicate case id")
        seen.add(case["id"])
        targets = rubric_targets(case["question"])
        expected = case["expected"]
        if type(expected["followup"]) is not bool:
            raise ValueError("expected followup must be boolean")
        if expected["target"] is not None and expected["target"] not in targets:
            raise ValueError("unknown expected target")
        if expected["followup"] != (expected["target"] is not None):
            raise ValueError("followup and target labels disagree")
        if not case["turns"] or case["turns"][-1]["role"] != "candidate":
            raise ValueError("case must end with a candidate answer")
        for turn in case["turns"]:
            if not {"id", "role", "kind", "followup_level", "content"} <= turn.keys():
                raise ValueError("case turns must use the full interview turn contract")
    if not seen:
        raise ValueError("empty dataset")
    return data


def summarize(rows: list[dict], label_status: str) -> dict:
    completed = [r for r in rows if r.get("deepseek") is not None]
    def ratio(values):
        return mean(values) if values else None
    usable = [r for r in completed if r.get("jev") is not None]
    direct = [r for r in usable if r["jev_route"] != "fallback"]
    targeted = [r for r in usable if r["expected"]["followup"]]
    return {
        "cases": len(rows), "label_status": label_status,
        "deepseek_completed": len(completed), "jev_completed": len(usable),
        "deepseek_label_agreement": ratio([r["deepseek"]["followup_needed"] == r["expected"]["followup"] for r in completed]),
        "jev_direct_coverage": len(direct) / len(rows) if rows else None,
        "jev_direct_label_agreement": ratio([(r["jev_route"] == "followup") == r["expected"]["followup"] for r in direct]),
        "provider_direct_agreement": ratio([(r["jev_route"] == "followup") == r["deepseek"]["followup_needed"] for r in direct]),
        "jev_target_label_agreement": ratio([r["jev"]["followup_target"] == r["expected"]["target"] for r in targeted]),
        "fallback_rate": ratio([r.get("jev_route") == "fallback" for r in rows]),
        "mean_jev_latency_ms": ratio([r["jev_latency_ms"] for r in rows if "jev_latency_ms" in r]),
        "mean_deepseek_latency_ms": ratio([r["deepseek_latency_ms"] for r in rows if "deepseek_latency_ms" in r]),
        "mean_call_cost": None,
        "cost_note": "Not measured: no billing usage/pricing supplied. Null is not zero.",
        "target_comparison_note": "DeepSeek emits free text; cross-provider target agreement requires human review of rows.",
    }


async def evaluate(data: dict, settings: Settings) -> dict:
    if not settings.jev_api_key.get_secret_value().strip():
        raise ValueError("Configure JEV_API_KEY locally before live evaluation")
    jev = JevDecisionClient(settings)
    llm = DeepSeekClient(settings)
    baseline = DeepSeekAssessmentClient(llm)
    rows = []
    try:
        for case in data["cases"]:
            args = {key: case[key] for key in ("question", "turns", "followup_count")}
            row = {"id": case["id"], "expected": case["expected"]}
            started = perf_counter()
            # Stop on baseline/auth failure rather than spending across the remaining dataset.
            assessment = await baseline.assess_answer(**args)
            row["deepseek_latency_ms"] = (perf_counter() - started) * 1000
            row["deepseek"] = assessment.model_dump(mode="json")
            started = perf_counter()
            try:
                decision = await jev.assess_answer(**args)
                row["jev"] = decision.model_dump(mode="json")
                route, reason = decision_route(row["jev"],
                    followup_threshold=settings.jev_followup_threshold,
                    score_threshold=settings.jev_score_threshold,
                    min_confidence=settings.jev_min_confidence)
            except DecisionServiceError as exc:
                if exc.reason in {"jev_http_401", "jev_http_403", "jev_missing_key"}:
                    raise
                row["jev"] = None
                route, reason = "fallback", exc.reason
            row.update(jev_latency_ms=(perf_counter() - started) * 1000,
                       jev_route=route, fallback_reason=reason)
            rows.append(row)
    finally:
        await jev.close()
        await llm.close()
    return {"dataset_version": data["version"],
            "summary": summarize(rows, data["label_status"]), "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = load_cases(args.cases)
    if args.validate_only:
        print(json.dumps({"cases": len(data["cases"]), "label_status": data["label_status"]}))
        return
    if args.output is None:
        parser.error("--output is required for live evaluation")
    if args.output.exists():
        parser.error("output already exists; choose a new path")
    result = asyncio.run(evaluate(data, Settings()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
