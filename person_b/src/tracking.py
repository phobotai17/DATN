"""Tracking/count CSV contract for one continuous camera recording.

Tracking counts are distinct IDs observed per interval, not line crossings or
vehicles/km. An ID may count in several intervals. Never combine recordings
with reused IDs. Zero-filled interior buckets assume uninterrupted recording.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

VEHICLE_CLASSES = ["motorbike", "car", "truck", "bus"]
OUTPUT_COLUMNS = ["timestamp", *VEHICLE_CLASSES, "total_vehicles"]
REQUIRED_COLUMNS = {"frame_id", "timestamp", "track_id", "class_name"}


def _window(window_minutes):
    if isinstance(window_minutes, bool) or not isinstance(window_minutes, int) or window_minutes <= 0:
        raise ValueError("window_minutes must be a positive integer.")


def _integers(values, name):
    numbers = pd.to_numeric(values, errors="raise")
    if numbers.isna().any() or not np.isfinite(numbers).all() or (numbers < 0).any() or (numbers % 1 != 0).any():
        raise ValueError(f"{name} must contain nonnegative integers.")
    return numbers.astype("int64")


def validate_log(df):
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing tracking columns: {sorted(missing)}")
    if df[list(REQUIRED_COLUMNS)].isna().any().any():
        raise ValueError("Tracking columns cannot contain missing values.")
    for column in ("frame_id", "track_id"):
        _integers(df[column], column)
    unknown = set(df["class_name"]) - set(VEHICLE_CLASSES)
    if unknown:
        raise ValueError(f"Unknown classes: {sorted(map(str, unknown))}. Normalize labels first.")
    timestamps = pd.to_datetime(df["timestamp"], errors="raise", format="mixed")
    if timestamps.isna().any():
        raise ValueError("Timestamps cannot be missing.")


def aggregate_tracking_log(df, window_minutes=5):
    """Count unique tracks per clock-aligned interval.

    Use one class per track: majority frame-level class, ties resolved by earliest
    observation. This prevents class flicker from counting a vehicle twice.
    Leading/trailing intervals without observations cannot be inferred.
    """
    _window(window_minutes)
    validate_log(df)
    if df.empty:
        return pd.DataFrame({c: pd.Series(dtype="datetime64[ns]" if c == "timestamp" else "int64")
                             for c in OUTPUT_COLUMNS})
    log = df.copy()
    log["timestamp"] = pd.to_datetime(log["timestamp"], format="mixed").dt.as_unit("ns")
    for column in ("frame_id", "track_id"):
        log[column] = _integers(log[column], column)
    log = log.sort_values(["timestamp", "frame_id"], kind="stable")
    if (log.groupby(["frame_id", "track_id"])["class_name"].nunique() > 1).any():
        raise ValueError("Conflicting classes for the same track_id and frame_id.")
    log = log.drop_duplicates(["frame_id", "track_id"])
    votes = (log.groupby(["track_id", "class_name"], sort=False)
             .agg(votes=("frame_id", "size"), first=("timestamp", "min")).reset_index())
    canonical = (votes.sort_values(["votes", "first"], ascending=[False, True], kind="stable")
                 .drop_duplicates("track_id").set_index("track_id")["class_name"])
    log["class_name"] = log["track_id"].map(canonical)
    log["timestamp"] = log["timestamp"].dt.floor(f"{window_minutes}min")
    counts = log.groupby(["timestamp", "class_name"])["track_id"].nunique().unstack(fill_value=0)
    index = pd.date_range(log["timestamp"].min(), log["timestamp"].max(), freq=f"{window_minutes}min")
    counts = counts.reindex(index=index, columns=VEHICLE_CLASSES, fill_value=0).fillna(0).astype("int64")
    counts.columns.name = None
    counts["total_vehicles"] = counts[VEHICLE_CLASSES].sum(axis=1)
    return counts.rename_axis("timestamp").reset_index()[OUTPUT_COLUMNS]


def normalize_counts(df, window_minutes=5):
    """Validate pre-aggregated data, accepting the video app's `total` alias.

    Preserves count semantics. Does not resample or invent missing observations.
    All four classes and regular clock-aligned intervals are required.
    """
    _window(window_minutes)
    out = df.copy()
    if "total_vehicles" not in out and "total" in out:
        out = out.rename(columns={"total": "total_vehicles"})
    missing = set(OUTPUT_COLUMNS) - set(out.columns)
    if missing:
        raise ValueError(f"Missing count columns: {sorted(missing)}")
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="raise", format="mixed").dt.as_unit("ns")
    if out[OUTPUT_COLUMNS].isna().any().any():
        raise ValueError("Count data cannot contain missing values.")
    for column in OUTPUT_COLUMNS[1:]:
        out[column] = _integers(out[column], column)
    expected_total = out[VEHICLE_CLASSES].sum(axis=1)
    if not out["total_vehicles"].eq(expected_total).all():
        raise ValueError("total_vehicles must equal the sum of the four classes.")
    if "total" in out and not pd.to_numeric(out["total"], errors="raise").eq(expected_total).all():
        raise ValueError("total and total_vehicles disagree.")
    out = out.sort_values("timestamp").reset_index(drop=True)
    if out["timestamp"].duplicated().any():
        raise ValueError("Duplicate timestamps in count data.")
    if not out["timestamp"].eq(out["timestamp"].dt.floor(f"{window_minutes}min")).all():
        raise ValueError(f"Timestamps must align to {window_minutes}-minute clock intervals.")
    if not out["timestamp"].diff().dropna().eq(pd.Timedelta(minutes=window_minutes)).all():
        raise ValueError("Missing intervals or wrong cadence; missing data is not necessarily zero traffic.")
    return out[OUTPUT_COLUMNS]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--input-kind", choices=["tracking", "counts"], default="tracking")
    parser.add_argument("--window", type=int, default=5, help="Interval in minutes")
    parser.add_argument("--output", type=Path, default=Path("data/aggregated_traffic.csv"))
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Input and output must be different files.")
    try:
        source = pd.read_csv(args.input)
        operation = aggregate_tracking_log if args.input_kind == "tracking" else normalize_counts
        result = operation(source, window_minutes=args.window)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(f"Validated {len(source)} input rows -> {len(result)} intervals: {args.output}")
    if args.input_kind == "tracking":
        print("Counts mean unique tracks observed per interval, not line crossings.")
    else:
        print("Count semantics preserved. Record source and counting method separately.")


if __name__ == "__main__":
    main()

