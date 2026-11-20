"""Run from the repository root with python -m evals.benchmark."""
import argparse
import csv
import json
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
import platform
import sys
from time import perf_counter

from evals.metrics import errors, event_scores

ROOT = Path(__file__).resolve().parents[1]
PERSON_B = ROOT
PACKAGE = PERSON_B / "data/goi_ban_giao_B"
DEMO = PACKAGE / "demo/clip_ngc.mp4"


class DashboardSink:
    """Accept the real runner's preview, caption and chart updates headlessly."""
    def image(self, *args, **kwargs):
        pass

    caption = info = plotly_chart = image


def read_csv(path, required):
    with path.open(encoding="utf-8-sig", newline="") as upstream:
        reader = csv.DictReader(upstream)
        if not set(required).issubset(reader.fieldnames or []):
            raise ValueError(f"{path}: required columns: {', '.join(required)}")
        return list(reader)


def number(value):
    result = float(value)
    if not isfinite(result) or result < 0:
        raise ValueError(f"Expected finite, nonnegative value: {value!r}")
    return result


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def score_video(out, result, args):
    covered = result["position"]
    zones = result["zone_samples"]
    events = [
        {"time_s": row["time_s"], "track_id": row.get("track_id"), "kind": f"crossing:{row['huong']}"}
        for row in result["events"]
    ] + [
        {"time_s": row["time_s"], "track_id": row.get("track_id"), "kind": "alert:calibrated_wrong_way"}
        for row in result["alerts"].to_dict("records")
    ] + [
        {"time_s": row["time_s"], "track_id": row.get("track_id"), "kind": f"alert:{row['event']}:{row['zone']}"}
        for row in result["analytics_alerts"]
    ] + [
        {"time_s": row["time_s"], "track_id": row.get("track_id"), "kind": f"movement:{row['entry']}:{row['exit']}"}
        for row in result["movements"]
    ]
    write_csv(out / "zone_predictions.csv", zones, ("time_s", "zone", "total", "stopped"))
    write_csv(out / "event_predictions.csv", events, ("time_s", "kind", "track_id"))
    accuracy = {"zones": None, "events": None}
    if args.zone_truth:
        predictions = {(int(r["time_s"]), r["zone"]): r for r in zones}
        truth = read_csv(args.zone_truth, ("second", "zone", "total", "stopped"))
        keyed = {}
        for row in truth:
            second = number(row["second"])
            if not second.is_integer():
                raise ValueError("Zone ground truth second must be an integer")
            key = (int(second), row["zone"])
            if key in keyed or key not in predictions:
                raise ValueError(f"Duplicate or missing zone prediction for {key}")
            keyed[key] = row
        if not keyed:
            raise ValueError("Zone ground truth must contain at least one observation")
        accuracy["zones"] = {
            field: errors((number(row[field]), predictions[key][field])
                          for key, row in keyed.items())
            for field in ("total", "stopped")
        }
    if args.event_truth:
        mapping = {}
        if args.event_id_map:
            for row in read_csv(args.event_id_map, ("track_id", "object_id")):
                track, identity = row["track_id"].strip(), row["object_id"].strip()
                if not track or not identity or track in mapping:
                    raise ValueError("Expected one nonempty identity per predicted track")
                mapping[track] = identity
        truth = []
        for row in read_csv(args.event_truth, ("time_s", "kind", "object_id")):
            kind, t, identity = row["kind"], number(row["time_s"]), row["object_id"].strip()
            if t >= covered or (kind.startswith("alert:") and not identity):
                raise ValueError("Event truth must be in range with an object_id for every alert")
            truth.append((kind, t, identity) if kind.startswith("alert:") else (kind, t))
        predicted = [
            (r["kind"], r["time_s"], mapping.get(str(r["track_id"]), None))
            if r["kind"].startswith("alert:") else (r["kind"], r["time_s"])
            for r in events
        ]
        if any(r[0].startswith("alert:") for r in predicted + truth) and not args.event_id_map:
            raise ValueError("Alert scoring requires --event-id-map from reviewed trajectories")
        kinds = sorted({r[0] for r in predicted + truth})
        accuracy["events"] = {
            "per_kind": {
                kind: event_scores([r for r in predicted if r[0] == kind],
                                   [r for r in truth if r[0] == kind], args.tolerance)
                for kind in kinds
            },
            "overall": event_scores(predicted, truth, args.tolerance),
        }
    return accuracy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=DEMO)
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--stride", type=int, choices=(1, 2, 3, 4), default=2)
    parser.add_argument("--height", type=int, choices=(480, 720, 1080), default=480)
    parser.add_argument("--calibrated", action="store_true", help="Only for the calibrated pilot camera view")
    parser.add_argument("--profile", type=Path, help="Custom camera profile (JSON)")
    parser.add_argument("--record", action="store_true", help="Include H.264 encoding")
    parser.add_argument("--zone-truth", type=Path)
    parser.add_argument("--event-truth", type=Path)
    parser.add_argument("--event-id-map", type=Path)
    parser.add_argument("--forecast-truth", type=Path)
    parser.add_argument("--tolerance", type=float, default=1.0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.seconds <= 0 or not isfinite(args.tolerance) or args.tolerance < 0:
        parser.error("seconds must be positive and tolerance finite and nonnegative")
    video = args.video.resolve()
    for path in (video, args.profile, args.zone_truth, args.event_truth, args.event_id_map, args.forecast_truth):
        if path is not None and not path.is_file():
            parser.error(f"File not found: {path}")
    now = datetime.now(timezone.utc)
    out = args.out or ROOT / "evals/runs" / now.strftime("%Y%m%dT%H%M%S%fZ")
    if out.exists():
        parser.error(f"Output directory already exists: {out}")

    sys.path.insert(0, str(PERSON_B / "app"))
    import cv2
    import pandas as pd
    import torch
    import ultralytics
    from components.handoff_panel import detector_resource, run_video, video_info
    from components.analytics_panel import validate_profile, zone_forecast

    profile = validate_profile(json.loads(args.profile.read_text(encoding="utf-8-sig"))) if args.profile else None
    fps, _, size = video_info(video)
    receiver = DashboardSink()
    started = perf_counter()
    result = run_video(
        PACKAGE, video, args.seconds, receiver, receiver, receiver,
        calibrated=args.calibrated or video == DEMO, record=args.record,
        clock0="2000-01-01 00:00:00", processing_height=args.height,
        stride=args.stride, analytics_settings={"profile": profile},
        model_loader=detector_resource.__wrapped__,
    )
    video_elapsed = perf_counter() - started

    # Same calculation as the dashboard's five-minute zone forecast.
    started = perf_counter()
    zones = pd.DataFrame(result["zone_samples"])
    forecast = zone_forecast(zones).to_dict()
    forecast_elapsed = perf_counter() - started
    total = video_elapsed + forecast_elapsed

    target_second = int(zones.time_s.max()) + 300
    forecast_accuracy = None
    if args.forecast_truth:
        actuals = {}
        for row in read_csv(args.forecast_truth, ("second", "zone", "total")):
            zone = row["zone"]
            if number(row["second"]) != target_second or zone in actuals or zone not in forecast:
                raise ValueError(f"Expected one label per matching zone at second {target_second}")
            actuals[zone] = number(row["total"])
        if not actuals:
            raise ValueError("Forecast ground truth must contain at least one observation")
        forecast_accuracy = errors((actual, forecast[zone]) for zone, actual in actuals.items())

    out.mkdir(parents=True, exist_ok=False)
    report = {
        "time_utc": now.isoformat(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "versions": {"torch": torch.__version__, "opencv": cv2.__version__, "ultralytics": ultralytics.__version__},
        "input": {"video": str(video), "source_fps": fps, "size": size,
                  "seconds_requested": args.seconds, "processing_height": args.height,
                  "stride": result["stride"], "record": args.record,
                  "calibrated_wrong_way": result["calibrated"], "camera_profile": result["profile"],
                  "zone_truth": str(args.zone_truth) if args.zone_truth else None,
                  "event_truth": str(args.event_truth) if args.event_truth else None,
                  "event_tolerance_seconds": args.tolerance},
        "performance": {
            "device": result["device"],
            "gpu": torch.cuda.get_device_name(0) if result["device"].startswith("cuda") else None,
            "processed_frames": result["frames"], "video_seconds_covered": result["position"],
            "wall_seconds": total, "video_wall_seconds": video_elapsed,
            "forecast_ms": 1000 * forecast_elapsed,
            "end_to_end_processed_fps": result["frames"] / total,
            "after_first_frame_fps": result["processing_fps"] if result["frames"] > 1 else None,
            "video_seconds_per_wall_second": result["position"] / total,
        },
        "observed": {"crossings": len(result["events"]), "calibrated_alerts": len(result["alerts"]),
                     "analytics_alerts": len(result["analytics_alerts"]), "movements": len(result["movements"]),
                     "track_quality": result["quality_counts"], "zone_samples": len(zones)},
        "zone_forecast": {"horizon_minutes": 5, "target_second": target_second,
                          "prediction_by_zone": forecast, "accuracy": forecast_accuracy,
                          "truth": str(args.forecast_truth) if args.forecast_truth else None},
        "video_accuracy": score_video(out, result, args),
    }
    saved = PERSON_B / "results/mock_forecast/metrics.csv"
    if saved.is_file():
        (out / "synthetic_forecast_metrics.csv").write_bytes(saved.read_bytes())
        report["offline_synthetic_forecast_metrics"] = "synthetic_forecast_metrics.csv"
    (out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report["performance"], indent=2))
    print(f"Report: {out.resolve() / 'report.json'}")


if __name__ == "__main__":
    main()

