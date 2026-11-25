"""Read-only electricity tools and the evidence checker for the Agent study."""

import csv
from datetime import date, datetime, time, timedelta
from functools import lru_cache
import hashlib
from io import TextIOWrapper
from itertools import groupby
import json
from math import isclose, isfinite
from zipfile import ZipFile


HOUR = timedelta(hours=1)
MAX_INTERVAL = timedelta(days=31)
FIELDS = {
    "household": ("Global_active_power", 60),
    "kitchen": ("Sub_metering_1", 1000),
    "laundry": ("Sub_metering_2", 1000),
    "heating_cooling": ("Sub_metering_3", 1000),
}
RULES = {
    "inspect_group": {
        "source": "https://doi.org/10.24432/C58K54",
        "guidance": "Review what was operating in the measured group during the stated interval. Use appliance-level evidence before attributing usage to a specific device.",
    },
    "inspect_peak": {
        "source": "https://doi.org/10.24432/C58K54",
        "guidance": "Check your activity log for the measured interval and compare it with an equivalent interval before assigning a cause.",
    },
    "tariff_required": {
        "source": "https://www.iea.org/reports/the-value-of-demand-flexibility",
        "guidance": "A monetary estimate requires the applicable tariff. Shifting electricity use can affect peak demand and cost.",
    },
}
REASON_CODES = {
    "ambiguous_request", "outside_replay", "incomplete_interval", "zero_baseline",
    "incomplete_target", "insufficient_reference", "zero_mad", "forecast_unavailable",
    "unsupported_horizon", "unsupported_scope", "missing_tariff", "screen_unavailable",
}


def parse_hour(value):
    if not isinstance(value, str):
        raise ValueError("An ISO 8601 timestamp is required")
    result = datetime.fromisoformat(value)
    if result.tzinfo is not None or result.minute or result.second or result.microsecond:
        raise ValueError("Use an hour-aligned timestamp on the recorded clock")
    return result


def iso(value):
    return value.isoformat(timespec="seconds")


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_lines(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


@lru_cache(maxsize=2048)
def parse_date(value):
    day, month, year = map(int, value.split("/"))
    return date(year, month, day)


def read_meter(archive):
    hours = {}
    columns = [column for column, _ in FIELDS.values()]
    with ZipFile(archive) as file, file.open("household_power_consumption.txt") as binary:
        rows = csv.reader(TextIOWrapper(binary, encoding="ascii"), delimiter=";")
        header = next(rows)
        columns = [header.index(column) for column in columns]
        clock = [header.index("Date"), header.index("Time")]
        previous = None
        for (day, minute), records in groupby(rows, lambda row: (row[clock[0]], row[clock[1]])):
            stamp = datetime.combine(parse_date(day), time.fromisoformat(minute))
            if stamp.second or stamp.microsecond or (previous is not None and stamp <= previous):
                raise ValueError("Expected consecutive duplicates on a strictly ordered minute grid")
            previous = stamp
            hour = stamp.replace(minute=0)
            if hour not in hours:
                hours[hour] = [[0, 0.0] for _ in columns]
            totals = hours[hour]
            records = list(records)
            for index, column in enumerate(columns):
                readings = {row[column] for row in records}
                if len(readings) != 1:
                    continue
                reading = readings.pop()
                if reading in ("", "?"):
                    continue
                value = float(reading)
                if not isfinite(value) or value < 0:
                    raise ValueError("Invalid meter reading")
                totals[index][0] += 1
                totals[index][1] += value
    return hours


class Dataset:
    def __init__(self, archive, outcomes):
        paths = {key: outcomes / name for key, name in (
            ("summary", "summary.json"), ("forecast", "forecast-test.jsonl"), ("screen", "anomaly-observed.jsonl"),
        )}
        self.summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
        self.hashes = {"archive": file_hash(archive), **{key: file_hash(path) for key, path in paths.items()}}
        if self.hashes["archive"] != self.summary["dataset"]["zip_sha256"]:
            raise ValueError("Archive checksum differs from the verified offline evaluation")
        self.start = parse_hour(self.summary["split"]["test_start"])
        self.end = parse_hour(self.summary["split"]["end_exclusive"])
        self.fit_end = parse_hour(self.summary["forecast"]["test"]["fit"]["latest_training_label_end"])
        self.meter = read_meter(archive)
        self.forecasts = self._index(paths["forecast"])
        self.screens = self._index(paths["screen"])
        for hour, row in self.forecasts.items():
            count, value = self.totals("household", hour, hour + HOUR)
            observed = self.screens[hour]
            if count != row["valid_minutes"] or observed["target_kwh"] != row["target_kwh"]:
                raise ValueError(f"Stored evaluation records disagree at {iso(hour)}")
            if (count == 60) != (row["target_kwh"] is not None):
                raise ValueError(f"Stored target has inconsistent coverage at {iso(hour)}")
            if count == 60 and not isclose(value, row["target_kwh"], abs_tol=1e-10):
                raise ValueError(f"Stored target differs from meter readings at {iso(hour)}")
            if observed["latest_reference"] and parse_hour(observed["latest_reference"]) >= hour:
                raise ValueError(f"Future data in anomaly baseline at {iso(hour)}")

    def _index(self, path):
        rows = json_lines(path)
        by_hour = {parse_hour(row["hour_start"]): row for row in rows}
        expected = self.summary["split"]["test_hours"]
        if len(rows) != expected or set(by_hour) != {self.start + i * HOUR for i in range(expected)}:
            raise ValueError(f"Invalid holdout grid in {path.name}")
        return by_hour

    def totals(self, field, start, end):
        index = list(FIELDS).index(field)
        divisor = FIELDS[field][1]
        total, valid = 0.0, 0
        while start < end:
            readings = self.meter.get(start)
            if readings:
                valid += readings[index][0]
                total += readings[index][1]
            start += HOUR
        return valid, total / divisor


def metric(value, unit=""):
    return {"value": value, "unit": unit}


class Replay:
    def __init__(self, dataset, cutoff):
        if not dataset.start <= cutoff < dataset.end:
            raise ValueError("Replay cutoff must be in the test segment")
        self.dataset = dataset
        self.cutoff = cutoff
        self.records = []

    def _record(self, tool, field, start, end, scope, reason, values):
        return {
            "evidence": f"E{len(self.records) + 1:02}", "tool": tool, "field": field,
            "start": iso(start) if start else None, "end": iso(end) if end else None,
            "scope": scope, "reason": reason, "metrics": values,
            "replay_cutoff": iso(self.cutoff),
        }

    def _historical(self, start, end):
        start, end = parse_hour(start), parse_hour(end)
        if not HOUR <= end - start <= MAX_INTERVAL:
            raise ValueError("Request an interval from one hour to 31 days")
        return start, end

    def meter(self, field, start, end):
        if field not in FIELDS:
            raise ValueError("Unknown meter field")
        start, end = self._historical(start, end)
        if end > self.cutoff:
            return self._record("meter", field, start, end, "unavailable", "outside_replay", {})
        count, value = self.dataset.totals(field, start, end)
        expected = int((end - start).total_seconds() // 60)
        complete = count == expected
        values = {"coverage": metric(count * 100 / expected, "%")}
        if count:
            values["energy" if complete else "partial_energy"] = metric(value, "kWh")
        return self._record("meter", field, start, end, "observed" if complete else "partial",
                            None if complete else "incomplete_interval", values)

    def compare(self, field, baseline_start, baseline_end, start, end):
        before = self.meter(field, baseline_start, baseline_end)
        after = self.meter(field, start, end)
        start, end = self._historical(start, end)
        b_start, b_end = self._historical(baseline_start, baseline_end)
        if b_end - b_start != end - start:
            raise ValueError("Comparison intervals must have equal lengths")
        values = {"baseline_start": metric(iso(b_start)), "baseline_end": metric(iso(b_end))}
        for label, record in (("baseline", before), ("comparison", after)):
            if "coverage" in record["metrics"]:
                values[f"{label}_coverage"] = record["metrics"]["coverage"]
        reasons = (before["reason"], after["reason"])
        if any(reasons):
            reason = "outside_replay" if "outside_replay" in reasons else "incomplete_interval"
            return self._record("compare", field, start, end, "unavailable", reason, values)
        base = before["metrics"]["energy"]["value"]
        diff = after["metrics"]["energy"]["value"] - base
        values.update(baseline_energy=metric(base, "kWh"), difference=metric(diff, "kWh"))
        if base:
            values["relative_change"] = metric(diff / base * 100, "%")
        return self._record("compare", field, start, end, "comparison", "zero_baseline" if base == 0 else None, values)

    def screen(self, start):
        start = parse_hour(start)
        end = start + HOUR
        row = self.dataset.screens.get(start)
        if end > self.cutoff or row is None:
            reason = "outside_replay" if end > self.cutoff else "screen_unavailable"
            return self._record("screen", "household", start, end, "unavailable", reason, {})
        values = {"reference_count": metric(row["reference_count"], "hours")}
        if row["status"] != "scored":
            return self._record("screen", "household", start, end, "unavailable", row["status"], values)
        score = row["modified_z"]
        flag = "high" if score > 3.5 else "low" if score < -3.5 else "within_threshold"
        values.update(score=metric(score), flag=metric(flag), reference_median=metric(row["median_kwh"], "kWh"))
        return self._record("screen", "household", start, end, "screening", None, values)

    def forecast(self, hours):
        if type(hours) is not int or hours != 1:
            return self._record("forecast", "household", self.cutoff, self.cutoff + HOUR,
                                "unavailable", "unsupported_horizon", {})
        row = self.dataset.forecasts[self.cutoff]
        for method in ("random_forest", "persistence", "daily_seasonal_naive"):
            if method == "random_forest" and self.dataset.fit_end > self.cutoff:
                continue
            if row[method] is not None:
                return self._record("forecast", "household", self.cutoff, self.cutoff + HOUR, "forecast", None,
                                    {"estimate": metric(row[method], "kWh"), "method": metric(method)})
        return self._record("forecast", "household", self.cutoff, self.cutoff + HOUR, "unavailable", "forecast_unavailable", {})

    def knowledge(self, rule):
        definition = RULES.get(rule)
        if definition is None:
            raise ValueError("Unknown knowledge rule")
        return self._record("knowledge", None, None, None, "guidance", None,
                            {key: metric(value) for key, value in {"rule": rule, **definition}.items()})

    def call(self, tool, args):
        tools = {name: getattr(self, name) for name in ("meter", "compare", "screen", "forecast", "knowledge")}
        try:
            if tool not in tools or not isinstance(args, dict):
                raise ValueError("Unknown tool or invalid arguments")
            record = tools[tool](**args)
        except (TypeError, ValueError, OverflowError):
            record = self._record("invalid", None, None, None, "unavailable", "invalid_tool", {})
        self.records.append(record)
        return record


def claim_from(record, name):
    return {key: record[key] for key in ("evidence", "field", "start", "end", "scope")} | {"name": name, **record["metrics"][name]}


def agrees(claim, expected):
    keys = ("field", "start", "end", "scope", "name", "unit")
    if any(claim.get(key) != expected[key] for key in keys):
        return False
    value, target = claim.get("value"), expected["value"]
    if type(target) in (int, float):
        if type(value) not in (int, float) or not isfinite(value):
            return False
        if target and value and (target > 0) != (value > 0):
            return False
        return isclose(value, target, rel_tol=0, abs_tol=0.000500000001)
    return value == target


def supported(claim, evidence):
    record = evidence.get(claim.get("evidence"))
    name = claim.get("name")
    return bool(record and name in record["metrics"] and agrees(claim, claim_from(record, name)))


def recommendation_supported(recommendation, evidence):
    if not recommendation or recommendation.get("scope") != "inspection":
        return False
    rule = evidence.get(recommendation.get("rule"))
    source = evidence.get(recommendation.get("observation"))
    if not rule or not source or source["scope"] not in {"observed", "comparison", "screening"}:
        return False
    code = rule["metrics"].get("rule", {}).get("value")
    if code == "inspect_group":
        return source["field"] in {"kitchen", "laundry", "heating_cooling"}
    return code == "inspect_peak" and source["field"] == "household"


def check(answer, records):
    evidence = {record["evidence"]: record for record in records}
    concerns = [f"Claim {index} conflicts with the cited record" for index, claim in enumerate(answer["claims"], 1)
                if not supported(claim, evidence)]
    names_by_record = {}
    for claim in answer["claims"]:
        names_by_record.setdefault(claim["evidence"], set()).add(claim["name"])
    companion_claims = {
        "partial_energy": {"coverage"},
        "estimate": {"method"},
        "relative_change": {"baseline_start", "baseline_end", "baseline_energy"},
    }
    for identifier, names in names_by_record.items():
        for metric_name, companions in companion_claims.items():
            if metric_name in names and not companions <= names:
                concerns.append(f"{identifier} {metric_name} needs {', '.join(sorted(companions))}")
    if answer["status"] == "answer" and not (answer["claims"] or answer.get("recommendation")):
        concerns.append("An answered request needs at least one evidence-linked item")
    if answer.get("recommendation") and not recommendation_supported(answer["recommendation"], evidence):
        concerns.append("Recommendation needs an applicable inspection rule and an eligible observation")
    if (answer["status"] == "answer") != (answer["reason"] is None):
        concerns.append("Supply a reason for a clarification or limitation and use null only for a complete answer")
    if answer["status"] == "clarify" and answer["reason"] != "ambiguous_request":
        concerns.append("A clarification needs ambiguous_request as its reason")
    return concerns
