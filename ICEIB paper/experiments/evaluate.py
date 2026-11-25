"""Run the forecast benchmark and anomaly checks on the original UCI archive."""

import argparse
import hashlib
import json
import platform
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor


DATASET_DOI = "10.24432/C58K54"
MEMBER = "household_power_consumption.txt"
METHODS = ("persistence", "daily_seasonal_naive", "random_forest")
FOREST = {"n_estimators": 200, "max_depth": 12, "min_samples_leaf": 5, "random_state": 42}
THRESHOLDS = (3.0, 3.5, 4.0)
REFERENCE_DAYS = np.arange(1, 57) * 24
INJECTION_SEED = 42
INJECTION_COUNT = 150
INJECTION_KWH = (0.5, 1.0)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_hourly(archive_path):
    with ZipFile(archive_path) as archive:
        with archive.open(MEMBER) as stream:
            member_sha = hashlib.file_digest(stream, "sha256").hexdigest()
        with archive.open(MEMBER) as stream:
            rows = pd.read_csv(
                stream, sep=";", usecols=["Date", "Time", "Global_active_power"],
                dtype={"Date": "string", "Time": "string", "Global_active_power": "float64"},
                na_values=["?"],
            )

    minute = pd.to_datetime(rows.pop("Date") + " " + rows.pop("Time"), format="%d/%m/%Y %H:%M:%S")
    if minute.isna().any() or (minute.dt.second != 0).any():
        raise ValueError("The recorded clock must contain minute-aligned timestamps")
    power = rows["Global_active_power"]
    if np.isinf(power).any() or (power.dropna() < 0).any():
        raise ValueError("Invalid active power reading")

    distinct = pd.DataFrame({"minute": minute, "power_kw": power}).drop_duplicates()
    conflicts = distinct["minute"].duplicated(keep=False)
    readings = distinct.loc[~conflicts].set_index("minute")["power_kw"].sort_index()
    hourly = readings.resample("h").agg(["count", "sum"])
    grid = pd.date_range(minute.min().floor("h"), minute.max().floor("h"), freq="h")
    hourly = hourly.reindex(grid, fill_value=0)
    complete_energy = (hourly["sum"] / 60).where(hourly["count"].eq(60)).rename("energy_kwh")
    metadata = {
        "doi": DATASET_DOI, "zip_sha256": digest(archive_path), "member": MEMBER,
        "member_sha256": member_sha, "rows": len(rows), "missing_power_rows": int(power.isna().sum()),
        "identical_readings_collapsed": len(rows) - len(distinct),
        "conflicting_minutes": int(distinct.loc[conflicts, "minute"].nunique()),
        "clock": "Recorded timestamps parsed day-first, with no timezone conversion",
        "first_minute": minute.min().isoformat(), "last_minute": minute.max().isoformat(),
        "complete_hours": int(complete_energy.notna().sum()), "scheduled_hours": len(grid),
    }
    return complete_energy, hourly["count"], metadata


def predictors(energy):
    frame = pd.DataFrame({f"lag_{hour}": energy.shift(hour) for hour in (1, 2, 24, 168)})
    prior = energy.shift(1)
    for size in (3, 24):
        rolling = prior.rolling(size, min_periods=size)
        frame[f"mean_{size}"] = rolling.mean()
        frame[f"sd_{size}"] = rolling.std(ddof=0)
    index = energy.index
    return frame.assign(hour=index.hour, weekday=index.dayofweek, month=index.month, weekend=index.dayofweek >= 5)


def forest_predictions(energy, features, fit_stop, predict_index):
    eligible = features.notna().all(axis=1)
    train = eligible.iloc[:fit_stop] & energy.iloc[:fit_stop].notna()
    fit_hours = train.index[train]
    model = RandomForestRegressor(**FOREST, n_jobs=1)
    model.fit(features.loc[fit_hours], energy.loc[fit_hours])
    selected = predict_index[eligible.loc[predict_index]]
    cutoff = fit_hours[-1] + pd.Timedelta(hours=1)
    if cutoff > predict_index[0]:
        raise ValueError("Training labels extend beyond the prediction boundary")
    predictions = pd.Series(np.nan, index=predict_index, dtype="float64")
    predictions.loc[selected] = model.predict(features.loc[selected])
    return predictions, {
        "training_samples": len(fit_hours), "latest_training_label_end": cutoff.isoformat(),
        "model_parameters": model.get_params(), "features": features.columns.tolist(),
    }


def forecast_metrics(rows):
    common = rows[["target_kwh", *METHODS]].dropna()
    result = {}
    for method in METHODS:
        errors = common[method] - common["target_kwh"]
        available = int(rows[method].notna().sum())
        result[method] = {
            "available_hours": available, "availability": available / len(rows),
            "unavailable_hours": len(rows) - available,
            "mae_kwh": float(errors.abs().mean()) if len(common) else None,
            "rmse_kwh": float(np.sqrt((errors**2).mean())) if len(common) else None,
        }
    return {
        "scheduled_hours": len(rows), "incomplete_targets": int(rows["target_kwh"].isna().sum()),
        "complete_targets_with_any_missing_prediction": int((rows["target_kwh"].notna() & rows[list(METHODS)].isna().any(axis=1)).sum()),
        "common_hours": len(common), "methods": result,
    }


def forecast(energy, valid_minutes, training_end, test_start):
    features = predictors(energy)
    all_results = {}
    for name, fit_stop, end in (("validation", training_end, test_start), ("test", test_start, len(energy))):
        selected = energy.index[fit_stop:end]
        prediction, provenance = forest_predictions(energy, features, fit_stop, selected)
        rows = pd.DataFrame({
            "target_kwh": energy.loc[selected], "valid_minutes": valid_minutes.loc[selected],
            "persistence": features.loc[selected, "lag_1"],
            "daily_seasonal_naive": features.loc[selected, "lag_24"], "random_forest": prediction,
        })
        rows.index.name = "hour_start"
        all_results[name] = {"fit": provenance, **forecast_metrics(rows)}
    return rows, all_results


def previous_reference(values, weekend, index):
    earlier = index - REFERENCE_DAYS
    earlier = earlier[earlier >= 0]
    return earlier[(weekend[earlier] == weekend[index]) & np.isfinite(values[earlier])]


def score(target, reference):
    median = float(np.median(reference)) if len(reference) else None
    mad = float(np.median(np.abs(reference - median))) if len(reference) else None
    if not np.isfinite(target):
        return median, mad, None, "incomplete_target"
    if len(reference) < 14:
        return median, mad, None, "insufficient_reference"
    if mad == 0:
        return median, mad, None, "zero_mad"
    return median, mad, float(0.6745 * (target - median) / mad), "scored"


def sensitivity(scores):
    return {
        str(cutoff): {"high": int((scores > cutoff).sum()), "low": int((scores < -cutoff).sum())}
        for cutoff in THRESHOLDS
    }


def anomaly(energy, test_start):
    values = energy.to_numpy()
    weekend = energy.index.dayofweek >= 5
    fixture_reference = np.array([0.8] * 5 + [1.0] * 4 + [1.2] * 5)
    median, mad, fixture_score, fixture_status = score(2.2, fixture_reference)
    np.testing.assert_allclose([median, mad, fixture_score], [1.0, 0.2, 4.047])
    assert fixture_status == "scored"
    assert score(2.2, fixture_reference[:-1])[-1] == "insufficient_reference"
    assert score(2.2, np.ones(14))[-1] == "zero_mad"
    assert score(np.nan, fixture_reference)[-1] == "incomplete_target"

    records = []
    for position in range(test_start, len(values)):
        indices = previous_reference(values, weekend, position)
        assert not len(indices) or (indices < position).all()
        median, mad, modified_z, status = score(values[position], values[indices])
        records.append({
            "hour_start": energy.index[position], "target_kwh": values[position], "reference_count": len(indices),
            "earliest_reference": energy.index[indices[-1]] if len(indices) else None,
            "latest_reference": energy.index[indices[0]] if len(indices) else None,
            "median_kwh": median, "mad_kwh": mad, "modified_z": modified_z, "status": status,
        })
    rows = pd.DataFrame(records)

    scored = rows.loc[rows["status"].eq("scored")]
    chosen = np.sort(np.random.default_rng(INJECTION_SEED).choice(scored.index, size=INJECTION_COUNT, replace=False))
    anchors = rows.loc[chosen, ["hour_start", "target_kwh", "median_kwh", "mad_kwh", "modified_z"]].copy()
    for index in chosen:
        position = test_start + index
        original = previous_reference(values, weekend, position)
        altered = values.copy()
        altered[position:] = 999.0
        np.testing.assert_array_equal(original, previous_reference(altered, weekend, position))
        np.testing.assert_array_equal(values[original], altered[original])

    injections = []
    for shift in INJECTION_KWH:
        injected = anchors.assign(delta_kwh=shift, injected_kwh=anchors["target_kwh"] + shift)
        injected["injected_z"] = 0.6745 * (injected["injected_kwh"] - injected["median_kwh"]) / injected["mad_kwh"]
        injections.append(injected)

    return rows, pd.concat(injections, ignore_index=True), {
        "scheduled_hours": len(rows), "scored_hours": len(scored),
        "status_counts": {key: int(count) for key, count in rows["status"].value_counts().items()},
        "observed_candidates_by_threshold": sensitivity(scored["modified_z"]),
        "fixtures": {"modified_z": fixture_score, "passed": 4},
        "time_isolation": {"all_test_reference_indices_strictly_past": True, "mutation_cases_passed": len(chosen)},
        "synthetic": {
            "sampling_seed": INJECTION_SEED, "same_scored_anchors_per_shift": len(anchors),
            "original_anchor_candidates": sensitivity(anchors["modified_z"]),
            "candidate_counts_by_delta_kwh": {
                str(shift): sensitivity(frame["injected_z"]) for shift, frame in zip(INJECTION_KWH, injections, strict=True)
            },
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="UCI dataset ZIP")
    parser.add_argument("output", type=Path, help="Directory for the records and summary")
    args = parser.parse_args()

    energy, valid_minutes, dataset = load_hourly(args.archive)
    training_end = len(energy) * 70 // 100
    test_start = len(energy) * 85 // 100
    forecast_rows, forecast_summary = forecast(energy, valid_minutes, training_end, test_start)
    anomaly_rows, synthetic_rows, anomaly_summary = anomaly(energy, test_start)
    summary = {
        "dataset": dataset, "script_sha256": digest(Path(__file__)),
        "software": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scikit-learn": sklearn.__version__},
        "split": {
            "training_start": energy.index[0].isoformat(), "validation_start": energy.index[training_end].isoformat(),
            "test_start": energy.index[test_start].isoformat(), "end_exclusive": (energy.index[-1] + pd.Timedelta(hours=1)).isoformat(),
            "training_hours": training_end, "validation_hours": test_start - training_end,
            "test_hours": len(energy) - test_start,
        },
        "forecast": forecast_summary, "anomaly": anomaly_summary,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    for name, rows in (
        ("forecast-test", forecast_rows.reset_index()), ("anomaly-observed", anomaly_rows), ("anomaly-synthetic", synthetic_rows),
    ):
        rows.to_json(args.output / f"{name}.jsonl", orient="records", lines=True, date_format="iso", double_precision=15)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
