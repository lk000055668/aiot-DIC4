"""Recompute the formal A/B metrics and prepare independent recommendation ratings."""

import argparse
from decimal import Decimal
import hashlib
from pathlib import Path
import random
from statistics import mean, median

from agent_replay import file_hash
from agent_study import grade, read_json, run_workload, write_new


DIMENSIONS = ("evidence_strength", "scope_of_inference", "actionability")
RUBRIC = {
    "evidence_strength": ["No applicable evidence", "Relevant but incomplete evidence", "Applicable rule and verified measurement support the step"],
    "scope_of_inference": ["Claims an unsupported cause or device", "Uncertainty or scope is partly stated", "Keeps the recommendation within the measured field and interval"],
    "actionability": ["No concrete inspection step", "Broad inspection step", "Specific and feasible inspection step"],
}


def load_runs(directory, frozen_path):
    manifest = read_json(directory / "manifest.json")
    frozen = read_json(frozen_path)
    if (manifest["phase"] != "formal" or manifest["cases_sha256"] != file_hash(frozen_path) or
            manifest["code_hashes"] != frozen["code_hashes"] or manifest["expected_runs"] != 300):
        raise ValueError("The formal execution manifest does not match the frozen workload")
    cases = frozen["formal"]
    if len(cases) != 50:
        raise ValueError("Expected the frozen 50-question task set")
    runs = []
    for run_id, case, condition, attempt in run_workload(cases, 3):
        row = read_json(directory / f"{run_id}.json")
        if (row["id"], row["case_id"], row["condition"], row["attempt"]) != (run_id, case["id"], condition, attempt):
            raise ValueError(f"Run identity mismatch: {run_id}")
        if row["state"] not in ("completed", "failed", "timeout"):
            raise ValueError(f"Formal workload is incomplete at {run_id}")
        if row["tool_calls"] > 8 or row["revisions"] > int(condition == "B"):
            raise ValueError(f"Run exceeded the protocol bounds: {run_id}")
        recomputed = grade(case, row["answer"], row["evidence"])
        if recomputed != row["score"]:
            raise ValueError(f"The saved score cannot be reproduced: {run_id}")
        runs.append(row)
    if len(runs) != 300 or len({row["id"] for row in runs}) != 300:
        raise ValueError("Expected exactly 300 distinct formal runs")
    return manifest, runs


def rate(numerator, denominator):
    return {"count": numerator, "denominator": denominator,
            "rate": numerator / denominator if denominator else None}


def condition_summary(rows):
    def counts(key):
        return sum(row["score"][key] for row in rows)

    requests = [item for row in rows for item in row["usage"]]
    costs = [Decimal(item["cost_usd"]) for item in requests if item["cost_usd"] is not None]
    return {
        "runs": len(rows), "failed": sum(row["state"] == "failed" for row in rows),
        "timeouts": sum(row["state"] == "timeout" for row in rows),
        "completion": rate(counts("complete"), len(rows)),
        "evidence_consistency": rate(counts("supported_assertions"), counts("assertions")),
        "required_field_coverage": rate(counts("provided_fields"), counts("required_fields")),
        "appropriate_limitations": rate(counts("appropriate_limitation"), counts("limitation_applicable")),
        "unnecessary_refusals": rate(counts("unnecessary_refusal"), counts("refusal_applicable")),
        "median_elapsed_seconds": median(row["elapsed_seconds"] for row in rows),
        "mean_elapsed_seconds": mean(row["elapsed_seconds"] for row in rows),
        "tool_calls": sum(row["tool_calls"] for row in rows), "revisions": sum(row["revisions"] for row in rows),
        "model_calls": len(requests),
        "reported_input_tokens": sum(item["input_tokens"] or 0 for item in requests),
        "reported_output_tokens": sum(item["output_tokens"] or 0 for item in requests),
        "requests_missing_token_counts": sum(item["input_tokens"] is None or item["output_tokens"] is None for item in requests),
        "reported_cost_usd": str(sum(costs, Decimal(0))), "requests_with_unknown_cost": len(requests) - len(costs),
    }


def summarize(manifest, runs):
    def group(rows):
        by_case = {}
        for row in rows:
            by_case.setdefault(row["case_id"], {"A": [], "B": []})[row["condition"]].append(row["score"]["complete"])
        differences = {key: mean(value["B"]) - mean(value["A"]) for key, value in by_case.items()}
        return {
            "question_count": len(by_case), "mean_paired_completion_B_minus_A": mean(differences.values()),
            "question_differences": differences,
            "conditions": {condition: condition_summary([row for row in rows if row["condition"] == condition])
                           for condition in ("A", "B")},
        }

    families = sorted({row["family"] for row in runs})
    return {
        "manifest": manifest, "paired_comparison": group(runs),
        "by_family": {family: group([row for row in runs if row["family"] == family]) for family in families},
    }


def review_packet(runs):
    items, private = [], {}
    for row in runs:
        response = row["answer"] or {}
        recommendation = response.get("recommendation")
        if row["family"] != "advise" or not recommendation:
            continue
        identifier = hashlib.sha256(("dic4-review-2026/" + row["id"]).encode()).hexdigest()[:16]
        private[identifier] = {"id": row["id"], "condition": row["condition"]}
        identifiers = {recommendation["rule"], recommendation["observation"]}
        items.append({
            "id": identifier, "question": row["question"], "cutoff": row["cutoff"],
            "recommendation": recommendation["text"],
            "cited_evidence": [record for record in row["evidence"] if record["evidence"] in identifiers],
        })
    random.Random(1987).shuffle(items)
    return {"dimensions": list(DIMENSIONS), "rubric": RUBRIC, "items": items}, private


def scores_of(value):
    if not isinstance(value, list) or len(value) != len(DIMENSIONS) or any(type(x) is not int or x not in range(3) for x in value):
        raise ValueError("Enter three integer ratings from zero to two in rubric order")
    return value


def combine_reviews(mapping, first, second, reconciled):
    reviewers = (first["reviewer"].strip(), second["reviewer"].strip())
    if not reviewers[0] or not reviewers[1] or reviewers[0].casefold() == reviewers[1].casefold():
        raise ValueError("Two distinct reviewers must submit independent ratings")
    if set(first["scores"]) != set(mapping) or set(second["scores"]) != set(mapping):
        raise ValueError("Each reviewer must rate every recommendation")
    agreement = [0] * len(DIMENSIONS)
    results = {condition: [] for condition in ("A", "B")}
    disagreements = []
    unresolved = []
    for item, identity in mapping.items():
        one, two = (scores_of(review["scores"][item]) for review in (first, second))
        for index in range(len(DIMENSIONS)):
            agreement[index] += int(one[index] == two[index])
        if one != two:
            disagreements.append(item)
            if item not in reconciled:
                unresolved.append(item)
                continue
            values = scores_of(reconciled[item])
            if any(a == b and value != a for a, b, value in zip(one, two, values, strict=True)):
                raise ValueError("A reconciled score can only change the disputed dimensions")
        else:
            values = one
        results[identity["condition"]].append(values)
    if set(reconciled) - set(disagreements):
        raise ValueError("Reconciliation contains an item with no scoring disagreement")
    return {
        "recommendations": len(mapping), "initial_exact_agreement": {
            key: rate(n, len(mapping)) for key, n in zip(DIMENSIONS, agreement, strict=True)
        },
        "disagreement_items": disagreements, "unresolved_items": unresolved,
        "conditions": {
            condition: {"rated_recommendations": len(values), "mean_scores": {
                key: mean(item[index] for item in values) if values else None for index, key in enumerate(DIMENSIONS)
            }} for condition, values in results.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("metrics", "review-packet"):
        command = commands.add_parser(name)
        command.add_argument("formal_dir", type=Path)
        command.add_argument("frozen", type=Path)
        command.add_argument("output", type=Path)
    reviews = commands.add_parser("review-metrics")
    for value in ("private_mapping", "reviewer_one", "reviewer_two", "reconciliation", "output"):
        reviews.add_argument(value, type=Path)
    args = parser.parse_args()
    if args.command == "review-metrics":
        report = combine_reviews(*(read_json(path) for path in (
            args.private_mapping, args.reviewer_one, args.reviewer_two, args.reconciliation,
        )))
        write_new(args.output, report)
        return
    manifest, rows = load_runs(args.formal_dir, args.frozen)
    if args.command == "metrics":
        write_new(args.output, summarize(manifest, rows))
    else:
        args.output.mkdir(parents=True, exist_ok=False)
        packet, mapping = review_packet(rows)
        write_new(args.output / "review-packet.json", packet)
        write_new(args.output / "private-mapping.json", mapping)
        write_new(args.output / "score-form.json", {"reviewer": "", "scores": {item["id"]: [None] * 3 for item in packet["items"]}})


if __name__ == "__main__":
    main()
