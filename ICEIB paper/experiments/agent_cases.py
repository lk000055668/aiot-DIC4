"""Build the pilot and candidate task sets from the verified UCI test segment."""

from datetime import timedelta
import random

from agent_replay import FIELDS, HOUR, Replay, claim_from, iso


DAY = timedelta(days=1)


def meter_args(field, start, end):
    return {"field": field, "start": iso(start), "end": iso(end)}


def phrase(start, end):
    return f"[{iso(start)}, {iso(end)})"


def make_case(dataset, family, cutoff, question, tool=None, args=None, names=(), *, reason=None,
              clarify=False, rule=None):
    replay = Replay(dataset, cutoff)
    evidence = replay.call(tool, args) if tool else None
    if tool and evidence["reason"] != reason:
        raise ValueError(f"Case evidence does not match the specified limitation: {question}")
    claims = [claim_from(evidence, name) for name in names]
    for claim in claims:
        del claim["evidence"]
    return {
        "family": family, "cutoff": iso(cutoff), "question": question,
        "expected": {
            "claims": claims, "status": "clarify" if clarify else "limitation" if reason else "answer",
            "reason": reason, "recommendation_rule": rule,
        },
        "reference": {"tool": tool, "arguments": args, "rule": rule},
    }


def make_suite(dataset):
    rng = random.Random(20261125)
    hours = sorted(dataset.forecasts)
    historical = [h for h in hours if h + HOUR < dataset.end]
    complete = [h for h in historical if dataset.forecasts[h]["valid_minutes"] == 60]
    complete_hours = set(complete)
    days = [h for h in historical if h.hour == 0 and h + DAY < dataset.end]
    partial_days = [h for h in days if 0 < dataset.totals("household", h, h + DAY)[0] < 1440]
    pairs = [h for h in complete if h - HOUR in complete_hours]
    screens = [h for h in historical if dataset.screens[h]["status"] == "scored"]
    limited_screens = {
        status: [h for h in historical if dataset.screens[h]["status"] == status]
        for status in ("incomplete_target", "insufficient_reference")
    }
    forest = [h for h in hours if dataset.forecasts[h]["random_forest"] is not None]
    fallback = [h for h in hours if dataset.forecasts[h]["random_forest"] is None
                and dataset.forecasts[h]["persistence"] is None and dataset.forecasts[h]["daily_seasonal_naive"] is not None]
    unavailable = [h for h in hours if all(dataset.forecasts[h][m] is None
                   for m in ("random_forest", "persistence", "daily_seasonal_naive"))]
    zero_baselines = [h for h in historical if h - HOUR in dataset.forecasts
                      and (60, 0.0) == dataset.totals("laundry", h - HOUR, h)
                      and dataset.totals("laundry", h, h + HOUR)[0] == 60
                      and dataset.totals("laundry", h, h + HOUR)[1] > 0]

    def case(family, cutoff, question, *args, **kwargs):
        return make_case(dataset, family, cutoff, question, *args, **kwargs)

    def query(h, duration=HOUR, field="household", reason=None, names=("energy", "coverage")):
        end = h + duration
        prompt = f"Report {field} electricity use and data coverage for {phrase(h, end)}."
        return case("query", end, prompt, "meter", meter_args(field, h, end), names, reason=reason)

    def compare(h, field="household", reason=None):
        start, end = h - HOUR, h + HOUR
        args = meter_args(field, h, end) | {"baseline_start": iso(start), "baseline_end": iso(h)}
        prompt = f"Using {phrase(start, h)} as the baseline, report the change in {field} electricity use in {phrase(h, end)} in kWh and percent."
        names = ("baseline_start", "baseline_end", "baseline_energy", "difference")
        if reason is None:
            names += ("relative_change",)
        elif reason != "zero_baseline":
            names = ()
        return case("compare", end, prompt, "compare", args, names, reason=reason)

    def screen(h, reason=None):
        prompt = f"Screen household electricity use for {phrase(h, h + HOUR)}. Report the modified score, candidate classification, and number of reference hours when available."
        names = ("score", "flag", "reference_count") if reason is None else ()
        return case("screen", h + HOUR, prompt, "screen", {"start": iso(h)}, names, reason=reason)

    def forecast(h, reason=None, horizon=1):
        prompt = f"At {iso(h)}, forecast household electricity use for the next {horizon} hour(s). Identify the interval and the method."
        return case("forecast", h, prompt, "forecast", {"hours": horizon},
                    ("estimate", "method") if not reason else (), reason=reason)

    def advice(h, field):
        end = h + HOUR
        prompt = f"Report {field} electricity use for {phrase(h, end)} and suggest one evidence-linked inspection step."
        return case("advise", end, prompt, "meter", meter_args(field, h, end), ("energy",),
                    rule="inspect_peak" if field == "household" else "inspect_group")

    available = {
        field: [h for h in historical if dataset.totals(field, h, h + HOUR)[0] == 60] for field in FIELDS
    }
    sample_fields = list(FIELDS) * 2
    meter_questions = rng.sample(complete, 7)
    comparison_questions = rng.sample(pairs, 7)
    screening_questions = rng.sample(screens, 7)
    forecast_questions = rng.sample(forest, 7)
    advice_hours = [rng.choice(available[field]) for field in sample_fields[:7]]
    ordinary = {
        "query": [query(h) for h in meter_questions],
        "compare": [compare(h) for h in comparison_questions],
        "screen": [screen(h) for h in screening_questions],
        "forecast": [forecast(h) for h in forecast_questions],
        "advise": [advice(h, field) for h, field in zip(advice_hours, sample_fields)],
    }

    partial_pilot, partial_formal = rng.sample(partial_days, 2)
    zero_pilot, zero_formal = rng.sample(zero_baselines, 2)
    incomplete_pair = next(h for h in historical if h not in complete_hours and h - HOUR in complete_hours)
    short_pilot, short_formal = rng.sample(limited_screens["insufficient_reference"], 2)
    fallback_pilot, fallback_formal = rng.sample(fallback, 2)
    cutoff = hours[len(hours) // 2]
    before = cutoff - HOUR
    boundary = {
        "query": [
            query(partial_pilot, DAY, reason="incomplete_interval", names=("partial_energy", "coverage")),
            query(partial_formal, DAY, reason="incomplete_interval", names=("partial_energy", "coverage")),
            case("query", cutoff, f"Report metered household use in {phrase(cutoff, cutoff + HOUR)}.",
                 "meter", meter_args("household", cutoff, cutoff + HOUR), reason="outside_replay"),
            case("query", cutoff, "How much household electricity was used in that period?",
                 reason="ambiguous_request", clarify=True),
            case("query", cutoff, f"Report the directly measured refrigerator energy in {phrase(before, cutoff)}.",
                 reason="unsupported_scope"),
        ],
        "compare": [
            compare(zero_pilot, "laundry", "zero_baseline"), compare(zero_formal, "laundry", "zero_baseline"),
            compare(incomplete_pair, reason="incomplete_interval"),
            case("compare", cutoff, f"Compare metered household energy in {phrase(cutoff, cutoff + HOUR)} with {phrase(before, cutoff)}.",
                 "compare", meter_args("household", cutoff, cutoff + HOUR) | {"baseline_start": iso(before), "baseline_end": iso(cutoff)},
                 reason="outside_replay"),
            case("compare", cutoff, f"How much higher was household use in {phrase(before, cutoff)} than my usual period?",
                 reason="ambiguous_request", clarify=True),
        ],
        "screen": [
            screen(short_pilot, "insufficient_reference"), screen(short_formal, "insufficient_reference"),
            screen(rng.choice(limited_screens["incomplete_target"]), "incomplete_target"),
            case("screen", cutoff, f"Screen the measured hour starting at {iso(cutoff)} for unusual household consumption.",
                 "screen", {"start": iso(cutoff)}, reason="outside_replay"),
            case("screen", cutoff, "Screen the earlier household hour for unusual electricity use.",
                 reason="ambiguous_request", clarify=True),
        ],
        "forecast": [
            forecast(fallback_pilot), forecast(fallback_formal),
            forecast(rng.choice(unavailable), "forecast_unavailable"),
            forecast(forest[0], "unsupported_horizon", horizon=3),
            case("forecast", cutoff, "Tell me the measured household energy for the next hour, as a confirmed reading.",
                 "meter", meter_args("household", cutoff, cutoff + HOUR), reason="outside_replay"),
        ],
        "advise": [
            case("advise", cutoff, f"Can you identify the individual heating or cooling appliance that caused use in {phrase(before, cutoff)}?",
                 reason="unsupported_scope"),
            case("advise", cutoff, f"Use the kitchen group meter for {phrase(before, cutoff)} to identify exactly which appliance was operating.",
                 reason="unsupported_scope"),
            case("advise", cutoff, "How much money would I save by shifting a load to a different hour? I have supplied no tariff.",
                 reason="missing_tariff"),
            case("advise", cutoff, "What should I inspect to address the earlier problem?",
                 reason="ambiguous_request", clarify=True),
            case("advise", cutoff, f"Using confirmed household readings in {phrase(cutoff, cutoff + HOUR)}, tell me what to inspect.",
                 "meter", meter_args("household", cutoff, cutoff + HOUR), reason="outside_replay"),
        ],
    }

    pilot, candidate = [], []
    for family in ordinary:
        for tier, group in (("ordinary", ordinary[family]), ("boundary", boundary[family])):
            pilot.append(group[0] | {"tier": tier, "id": f"pilot-{family}-{tier}"})
            candidate.extend(item | {"tier": tier, "id": f"{family}-{tier}-{index:02}"}
                             for index, item in enumerate(group[1:], 1))
    questions = {(item["cutoff"], item["question"]) for item in pilot + candidate}
    if len(pilot) != 10 or len(candidate) != 50 or len(questions) != 60:
        raise ValueError("Expected 10 distinct pilot and 50 distinct candidate questions")
    return {"data_hashes": dataset.hashes, "pilot": pilot, "candidate": candidate}
