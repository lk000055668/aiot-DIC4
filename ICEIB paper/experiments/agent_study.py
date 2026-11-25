"""Run the Energy Detective pilot and paired evaluation using a configured model adapter."""

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from importlib import import_module
import json
from math import isfinite
from pathlib import Path
import re
from time import perf_counter

from agent_cases import make_suite
from agent_replay import Dataset, REASON_CODES, Replay, agrees, check, claim_from, file_hash, parse_hour, recommendation_supported, supported


TOOL_LIMIT = 8
SYSTEM_PROMPT = """You are Energy Detective, a read-only electricity analyst. Use the recorded clock and the supplied replay cutoff. Request evidence before making a factual claim. Meter fields are household, kitchen, laundry and heating_cooling. Individual appliances need separate measurements. A forecast is an estimate. A partial sum represents only the observed portion. Percentage change is undefined when baseline energy is zero. A forecast for the next hour starts at the replay cutoff. For advice, recommend an inspection backed by an applicable knowledge rule and observation. Ask for clarification when the requested interval is ambiguous.

Return a single JSON object. To call a tool, use {"kind":"tool","name":<name>,"args":{...}}. Available tools:
meter(field, start, end)
compare(field, baseline_start, baseline_end, start, end)
screen(start)
forecast(hours)
knowledge(rule) where rule is inspect_group, inspect_peak or tariff_required.
Times use ISO 8601 without a zone. At most eight tool attempts are available, including errors.

To finish, return {"kind":"response","status":"answer" or "clarify" or "limitation","reason":null or <reason code>,"claims":[...]}. Each claim has evidence, field, start, end, scope, name, unit, and value. Copy the metadata exactly from an evidence record and choose a name from its metrics. Numeric values may be given to three decimal places. Include comparison baseline dates and energy if available. For advice add "recommendation":{"rule":<knowledge evidence identifier>,"observation":<measurement evidence identifier>,"scope":"inspection","text":<short inspection step>}.

Use null for the reason on a complete answer. Limitation reasons include outside_replay, incomplete_interval, zero_baseline, incomplete_target, insufficient_reference, zero_mad, forecast_unavailable, unsupported_horizon, unsupported_scope, missing_tariff and screen_unavailable. Use ambiguous_request when asking for clarification. Include available, correctly scoped partial claims if relevant. Do not include prose outside the JSON."""


class BudgetExceeded(Exception):
    pass


class InvalidResponse(ValueError):
    pass


def money(value):
    try:
        amount = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("Expected a finite cost in USD") from error
    if not amount.is_finite() or amount < 0:
        raise ValueError("Expected a finite nonnegative cost in USD")
    return amount


class CappedCalls:
    """Reserve the adapter's worst-case price before a request and track actual usage."""

    def __init__(self, model, cap, previously_reserved=0):
        self.model = model
        self.cap = money(cap)
        self.reserved = money(previously_reserved)
        if self.reserved > self.cap:
            raise BudgetExceeded("Earlier pilot usage already exceeds the approved total budget")
        self.calls = []
        self.halted = False

    def __call__(self, messages):
        if self.halted:
            raise BudgetExceeded("Earlier request exceeded its declared cost bound")
        ceiling = money(self.model.maximum_cost_usd(messages))
        if self.reserved + ceiling > self.cap:
            raise BudgetExceeded("Worst-case request cost exceeds the remaining approved budget")
        self.reserved += ceiling
        entry = {"ceiling_usd": str(ceiling), "cost_usd": None, "input_tokens": None, "output_tokens": None}
        self.calls.append(entry)
        response = self.model.generate(messages)
        cost = money(response["cost_usd"])
        entry["cost_usd"] = str(cost)
        self.reserved += cost - ceiling
        if cost > ceiling:
            self.halted = True
            raise BudgetExceeded("Adapter returned a cost greater than the reserved bound")
        for name in ("input_tokens", "output_tokens"):
            value = response[name]
            if type(value) is not int or value < 0:
                raise InvalidResponse("Adapter returned invalid token counts")
            entry[name] = value
        return response["action"]


def parse_answer(action):
    if not isinstance(action, dict) or action.get("kind") != "response":
        raise InvalidResponse("Expected a JSON response action")
    status, reason = action.get("status"), action.get("reason")
    if status not in ("answer", "clarify", "limitation"):
        raise InvalidResponse("Unknown response status")
    if reason is not None and (not isinstance(reason, str) or reason not in REASON_CODES):
        raise InvalidResponse("Unknown response reason")
    claims = action.get("claims")
    if not isinstance(claims, list) or len(claims) > 16:
        raise InvalidResponse("Claims must be a list with at most 16 items")
    keys = ("evidence", "field", "start", "end", "scope", "name", "unit", "value")
    cleaned = []
    for claim in claims:
        if not isinstance(claim, dict) or any(key not in claim for key in keys):
            raise InvalidResponse("A claim is missing required fields")
        for key in keys[:-1]:
            value = claim[key]
            if value is None and key in {"field", "start", "end"}:
                continue
            if not isinstance(value, str) or len(value) > 80:
                raise InvalidResponse("Invalid claim metadata")
        value = claim["value"]
        if not ((isinstance(value, str) and len(value) <= 400) or
                (type(value) in (int, float) and abs(value) <= 1e15 and isfinite(value))):
            raise InvalidResponse("Invalid claim value")
        cleaned.append({key: claim[key] for key in keys})
    response = {"status": status, "reason": reason, "claims": cleaned}
    recommendation = action.get("recommendation")
    if recommendation is not None:
        rec_keys = ("rule", "observation", "scope", "text")
        if not isinstance(recommendation, dict) or any(
            not isinstance(recommendation.get(key), str) or not recommendation[key].strip()
            or len(recommendation[key]) > (360 if key == "text" else 40) for key in rec_keys
        ):
            raise InvalidResponse("Invalid recommendation record")
        response["recommendation"] = {key: recommendation[key] for key in rec_keys}
    return response


def render(answer):
    if answer is None:
        return None
    status = answer["status"].capitalize()
    lines = [status + (f" ({answer['reason']})" if answer["reason"] else "")]
    for item in answer["claims"]:
        value = item["value"]
        if type(value) is float:
            value = f"{value:.3f}"
        interval = f" [{item['start']}, {item['end']})" if item["start"] else ""
        field = f" {item['field']}" if item["field"] else ""
        unit = f" {item['unit']}" if item["unit"] else ""
        lines.append(f"{item['scope']}{field}{interval} {item['name']}: {value}{unit} ({item['evidence']})")
    if answer.get("recommendation"):
        recommendation = answer["recommendation"]
        lines.append(f"Inspection: {recommendation['text']} ({recommendation['rule']}, {recommendation['observation']})")
    return "\n".join(lines)


def run_case(dataset, case, condition, model):
    if condition not in ("A", "B"):
        raise ValueError("Unknown study condition")
    replay = Replay(dataset, parse_hour(case["cutoff"]))
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({"question": case["question"], "replay_cutoff": case["cutoff"]})},
    ]
    started = perf_counter()
    call_start = len(model.calls)
    revisions = 0
    checks = []
    answer = None
    state = "completed"
    error = None
    try:
        while True:
            action = model(messages)
            if not isinstance(action, dict):
                raise InvalidResponse("Model output is not a JSON object")
            if action.get("kind") == "tool":
                if len(replay.records) >= TOOL_LIMIT:
                    raise InvalidResponse("Tool-call limit exceeded")
                record = replay.call(action.get("name"), action.get("args"))
                messages.extend((
                    {"role": "assistant", "content": json.dumps(action)},
                    {"role": "user", "content": json.dumps({"tool_result": record, "remaining_tools": TOOL_LIMIT - len(replay.records)})},
                ))
                continue
            answer = parse_answer(action)
            if condition == "A":
                break
            problems = check(answer, replay.records)
            checks.append(problems)
            if not problems:
                break
            if revisions:
                answer = {"status": "limitation", "reason": "verification_failed", "claims": []}
                break
            revisions += 1
            messages.extend((
                {"role": "assistant", "content": json.dumps(action)},
                {"role": "user", "content": json.dumps({"revise_once": problems, "remaining_tools": TOOL_LIMIT - len(replay.records)})},
            ))
    except BudgetExceeded as exc:
        state, answer, error = "budget_stopped", None, str(exc)
    except TimeoutError as exc:
        state, answer, error = "timeout", None, type(exc).__name__
    except (OSError, ValueError, TypeError, KeyError) as exc:
        state, answer, error = "failed", None, type(exc).__name__
    usage = model.calls[call_start:]
    return {
        "state": state, "error": error, "answer": answer, "rendered": render(answer),
        "evidence": replay.records, "checker_messages": checks,
        "tool_calls": len(replay.records), "revisions": revisions, "model_calls": len(usage),
        "usage": usage, "elapsed_seconds": perf_counter() - started,
        "score": grade(case, answer, replay.records) if state == "completed" else grade(case, None, []),
    }


def grade(case, answer, records):
    expected = case["expected"]
    slots = expected["claims"]
    target_rule = expected["recommendation_rule"]
    evidence = {record["evidence"]: record for record in records}
    actual = answer["claims"] if answer else []
    rec = answer.get("recommendation") if answer else None
    rec_supported = bool(rec and recommendation_supported(rec, evidence))
    rec_correct = False
    if target_rule and rec_supported:
        rule_record = evidence[rec["rule"]]
        observed = evidence[rec["observation"]]
        rec_correct = rule_record["metrics"]["rule"]["value"] == target_rule and any(
            all(slot[key] == observed[key] for key in ("field", "start", "end")) for slot in slots
        )
    slot_keys = ("name", "field", "start", "end", "scope")
    provided = sum(any(all(claim[key] == slot[key] for key in slot_keys) for claim in actual) for slot in slots)
    consistent = [supported(claim, evidence) for claim in actual]
    correct = sum(any(ok and agrees(claim, slot) for claim, ok in zip(actual, consistent, strict=True)) for slot in slots)
    boundary = expected["status"] in ("clarify", "limitation")
    matches = bool(answer and (answer["status"], answer["reason"]) == (expected["status"], expected["reason"]))
    extra_percentage = expected["reason"] == "zero_baseline" and any(c["name"] == "relative_change" for c in actual)
    complete = matches and correct == len(slots) and all(consistent) and not extra_percentage and (not target_rule or rec_correct)
    return {
        "complete": complete, "provided_fields": provided + int(bool(target_rule and rec)),
        "required_fields": len(slots) + int(bool(target_rule)),
        "assertions": len(actual) + int(bool(rec)), "supported_assertions": sum(consistent) + int(rec_supported),
        "limitation_applicable": boundary, "appropriate_limitation": boundary and complete,
        "refusal_applicable": case["tier"] == "ordinary",
        "unnecessary_refusal": case["tier"] == "ordinary" and bool(answer and answer["status"] != "answer"),
    }


def run_workload(cases, repeats):
    for question_index, case in enumerate(cases):
        for attempt in range(1, repeats + 1):
            conditions = "AB" if (question_index + attempt) % 2 else "BA"
            for condition in conditions:
                yield f"{case['id']}-{condition}-{attempt}", case, condition, attempt


def code_hashes():
    directory = Path(__file__).parent
    names = ("agent_replay.py", "agent_cases.py", "agent_study.py", "agent_reports.py")
    return {name: file_hash(directory / name) for name in names}


def write_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def check_cases(cases, phase):
    groups = Counter((case["family"], case["tier"]) for case in cases)
    families = ("query", "compare", "screen", "forecast", "advise")
    pairs = (("ordinary", 1), ("boundary", 1)) if phase == "pilot" else (("ordinary", 6), ("boundary", 4))
    expected = {(family, tier): count for family in families for tier, count in pairs}
    identifiers = {case["id"] for case in cases}
    questions = {(case["cutoff"], case["question"]) for case in cases}
    if (groups != expected or len(identifiers) != len(cases) or len(questions) != len(cases) or
            not all(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", value) for value in identifiers)):
        raise ValueError(f"Invalid {phase} task identities or stratification")


def audit_case(dataset, case):
    reference = case["reference"]
    gold = case["expected"]
    replay = Replay(dataset, parse_hour(case["cutoff"]))
    if reference["tool"]:
        source = replay.call(reference["tool"], reference["arguments"])
        if source["reason"] != gold["reason"] or any(
            slot["name"] not in source["metrics"] or not agrees(slot, claim_from(source, slot["name"]))
            for slot in gold["claims"]
        ):
            raise ValueError(f"Answer key differs from reproducible tool evidence: {case['id']}")
    elif gold["claims"]:
        raise ValueError(f"Missing reference tool for answer key: {case['id']}")


def freeze(prepared, pilot_dir, target, reviewed_candidates=None):
    draft = read_json(prepared)
    manifest = read_json(pilot_dir / "manifest.json")
    check_cases(draft["pilot"], "pilot")
    tasks = list(run_workload(draft["pilot"], 1))
    if (manifest["phase"] != "pilot" or manifest["data_hashes"] != draft["data_hashes"] or
            manifest["cases_sha256"] != file_hash(prepared) or len(tasks) != 20 or not manifest["model"]["snapshot"]):
        raise ValueError("The pilot manifest does not match the prepared ten-question workload")
    reserved = Decimal(0)
    completed = 0
    pilot_hashes = {}
    for run_id, case, condition, attempt in tasks:
        path = pilot_dir / f"{run_id}.json"
        row = read_json(path)
        if row["state"] not in ("completed", "failed", "timeout") or (row["case_id"], row["condition"], row["attempt"]) != (case["id"], condition, attempt):
            raise ValueError(f"The pilot requires an execution record for {run_id}")
        completed += int(row["state"] == "completed")
        reserved += sum(money(item["cost_usd"] if item["cost_usd"] is not None else item["ceiling_usd"]) for item in row["usage"])
        pilot_hashes[run_id] = file_hash(path)
    if not completed:
        raise ValueError("The pilot needs completed responses to review before freezing the workload")
    candidate_path = reviewed_candidates or prepared
    reviewed = read_json(candidate_path)
    formal = reviewed["candidate"]
    check_cases(formal, "formal")
    pilot_questions = {(case["cutoff"], case["question"]) for case in draft["pilot"]}
    if reviewed["data_hashes"] != draft["data_hashes"] or any(
        (case["cutoff"], case["question"]) in pilot_questions for case in formal
    ):
        raise ValueError("Formal candidates must use the same dataset and remain distinct from the pilot questions")
    write_new(target, {
        "data_hashes": draft["data_hashes"], "formal": formal,
        "pilot_manifest_sha256": file_hash(pilot_dir / "manifest.json"),
        "pilot_run_sha256": pilot_hashes, "pilot_reserved_usd": str(reserved),
        "pilot_model": manifest["model"],
        "prepared_cases_sha256": file_hash(prepared), "formal_candidates_sha256": file_hash(candidate_path),
        "code_hashes": code_hashes(),
    })


def run_study(args, dataset):
    case_file = read_json(args.cases)
    if case_file["data_hashes"] != dataset.hashes:
        raise ValueError("Task-set provenance does not match the meter inputs")
    cases = case_file[args.phase]
    repeats, expected = (1, 10) if args.phase == "pilot" else (3, 50)
    check_cases(cases, args.phase)
    if args.phase == "formal" and case_file.get("code_hashes") != code_hashes():
        raise ValueError("Unexpected task set or implementation versions. Freeze again after changes.")
    for case in cases:
        audit_case(dataset, case)
    model = import_module(args.adapter).make_model()
    configuration = model.configuration
    if (not configuration.get("provider") or not configuration.get("snapshot") or
            not configuration.get("price_source") or not isinstance(configuration.get("settings"), dict)):
        raise ValueError("Record the provider, model snapshot, price source, and generation settings")
    cap = money(args.max_usd)
    prior = money(case_file["pilot_reserved_usd"]) if args.phase == "formal" else Decimal(0)
    calls = CappedCalls(model, cap, prior)
    args.output.mkdir(parents=True, exist_ok=False)
    write_new(args.output / "manifest.json", {
        "phase": args.phase, "cases_sha256": file_hash(args.cases), "model": configuration,
        "data_hashes": dataset.hashes, "code_hashes": code_hashes(), "max_usd": str(cap), "prior_reserved_usd": str(prior),
        "prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "started_at": datetime.now(timezone.utc).isoformat(), "expected_runs": expected * repeats * 2,
    })
    for run_id, case, condition, attempt in run_workload(cases, repeats):
        path = args.output / f"{run_id}.json"
        write_new(path, {"id": run_id, "state": "started"})
        row = run_case(dataset, case, condition, calls)
        temporary = path.with_suffix(".pending")
        write_new(temporary, row | {
            "id": run_id, "case_id": case["id"], "family": case["family"], "question": case["question"],
            "cutoff": case["cutoff"], "condition": condition, "attempt": attempt,
        })
        temporary.replace(path)
        if row["state"] == "budget_stopped":
            raise BudgetExceeded(f"Stopped at {run_id}. Partial execution records are saved.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--outcomes", type=Path, default=Path(__file__).parent / "results")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("output", type=Path)
    freeze_command = subparsers.add_parser("freeze")
    freeze_command.add_argument("prepared", type=Path)
    freeze_command.add_argument("pilot_dir", type=Path)
    freeze_command.add_argument("output", type=Path)
    freeze_command.add_argument("--reviewed-candidates", type=Path)
    run = subparsers.add_parser("run")
    run.add_argument("phase", choices=("pilot", "formal"))
    run.add_argument("cases", type=Path)
    run.add_argument("output", type=Path)
    run.add_argument("--adapter", required=True)
    run.add_argument("--max-usd", required=True)
    args = parser.parse_args()
    if args.command == "freeze":
        freeze(args.prepared, args.pilot_dir, args.output, args.reviewed_candidates)
        return
    if args.archive is None:
        parser.error("--archive is required for prepare and run")
    dataset = Dataset(args.archive, args.outcomes)
    if args.command == "prepare":
        suite = make_suite(dataset)
        write_new(args.output, suite)
        print(f"Prepared {len(suite['pilot'])} pilot questions and {len(suite['candidate'])} formal candidates")
    else:
        run_study(args, dataset)


if __name__ == "__main__":
    main()
