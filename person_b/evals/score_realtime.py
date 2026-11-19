"""Score sampled trajectories and alerts against independent video annotations."""
import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
from math import isfinite
from pathlib import Path
import json

import lap
import numpy as np

from evals.benchmark import read_csv, number
from evals.metrics import errors, event_scores


def box(row):
    return tuple(number(row[k]) for k in ("x1", "y1", "x2", "y2"))


def iou(a, b):
    x, y, r, s = a
    u, v, w, z = b
    intersection = max(0, min(r, w)-max(x, u)) * max(0, min(s, z)-max(y, v))
    union = (r-x)*(s-y) + (w-u)*(z-v) - intersection
    return intersection/union if union > 0 else 0.


def nearest_frame(frames, times, target):
    index = bisect_left(times, target)
    candidates = frames[max(index-1, 0):index+1]
    return min(candidates, key=lambda frame: abs(frame["time_s"]-target), default=None)


def associate(labels, frames, tolerance, roi=None):
    """Globally score IDs; retain local matches for associating alert vehicles."""
    observations, votes, previous = defaultdict(list), Counter(), {}
    for row in labels:
        t = number(row["time_s"])
        identity = row["object_id"].strip()
        bounds = box(row)
        if (not identity or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]
                or any(r[0] == identity for r in observations[t])):
            raise ValueError("Invalid or duplicate object at annotated timestamp")
        observations[t].append((identity, bounds))
    if not observations:
        raise ValueError("Require at least one annotated tracking frame")
    actual = predicted = switches = covered = 0
    anchors = defaultdict(list)
    frames = sorted(frames, key=lambda frame: frame["time_s"])
    times = [frame["time_s"] for frame in frames]
    for t, truth in sorted(observations.items()):
        frame = nearest_frame(frames, times, t)
        tracks = [] if frame is None or abs(frame["time_s"]-t) > tolerance else frame["tracks"]
        covered += int(frame is not None and abs(frame["time_s"]-t) <= tolerance)
        if roi:
            x, y, r, s = roi
            tracks = [p for p in tracks if x <= (p["x1"]+p["x2"])/2 <= r and y <= p["y2"] <= s]
        actual += len(truth)
        predicted += len(tracks)
        if not tracks:
            continue
        costs = 1 - np.array([[iou(bounds, box(p)) for p in tracks] for _, bounds in truth])
        # Use a large constant to prefer more viable pairs before higher IoU.
        costs = np.where(costs <= .5, costs/(len(truth)+len(tracks)), 2.)
        _, pairs, _ = lap.lapjv(costs, extend_cost=True, cost_limit=1.)
        for index, j in enumerate(pairs):
            if j < 0:
                continue
            identity, track = truth[index][0], tracks[j]["track_id"]
            votes[identity, track] += 1
            anchors[track].append((frame["time_s"], identity))
            if identity in previous and previous[identity] != track:
                switches += 1
            previous[identity] = track
    matched = 0
    if votes:
        ids = sorted({k[0] for k in votes})
        tracks = sorted({k[1] for k in votes})
        weights = np.array([[votes[a, b] for b in tracks] for a in ids], dtype=float)
        _, pairs, _ = lap.lapjv(-weights, extend_cost=True)
        matched = int(sum(weights[i, j] for i, j in enumerate(pairs) if j >= 0))
    return dict(idf1=2*matched/(actual+predicted), idtp=matched,
                idfp=predicted-matched, idfn=actual-matched, id_switches=switches,
                annotated_frames=len(observations), frames_with_prediction=covered), anchors


def score_alerts(frames, anchors, truth_rows, kinds, start, end, tolerance, anchor_tolerance):
    truth = []
    for row in truth_rows:
        t, kind, obj = number(row["time_s"]), row["kind"], row["object_id"].strip()
        if not start <= t < end or kind not in kinds or not obj:
            raise ValueError("Event label outside declared time or kinds, or missing object_id")
        truth.append((kind, t, obj))
    predicted = []
    for frame in frames:
        for alert in frame["alerts"]:
            t, track, kind = alert["time_s"], alert["track_id"], alert["event"]
            if not start <= t < end or kind not in kinds:
                continue
            nearby = sorted(anchors.get(track, ()), key=lambda a: abs(a[0]-t))
            identity = nearby[0][1] if nearby and abs(nearby[0][0]-t) <= anchor_tolerance else None
            predicted.append((kind, t, identity))
    scores = {}
    for kind in kinds:
        result = event_scores([r for r in predicted if r[0] == kind],
                              [r for r in truth if r[0] == kind], tolerance)
        result["false_alarms_per_minute"] = result["fp"]*60/(end-start)
        result["predictions_without_object_match"] = sum(r[0] == kind and r[2] is None for r in predicted)
        scores[kind] = result
    return scores


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--tracks", type=Path, required=True)
    parser.add_argument("--roi", nargs=4, type=float)
    parser.add_argument("--anchors-only", action="store_true", help="Boxes cover event vehicles only")
    parser.add_argument("--frame-tolerance", type=float, default=.25)
    parser.add_argument("--zone-truth", type=Path)
    parser.add_argument("--events", type=Path)
    parser.add_argument("--kinds", nargs="+", choices=["abrupt_turn", "relative_speed", "relative_slow", "zone_wrong_way"])
    parser.add_argument("--window", nargs=2, type=float)
    parser.add_argument("--event-tolerance", type=float, default=1.)
    args = parser.parse_args()
    if not all(isfinite(t) and t >= 0 for t in (args.frame_tolerance, args.event_tolerance)):
        parser.error("Tolerances must be finite and nonnegative")
    with (args.run / "telemetry.jsonl").open(encoding="utf-8") as log:
        frames = sorted((json.loads(line) for line in log), key=lambda frame: frame["time_s"])
    if not frames or any("tracks" not in frame for frame in frames):
        parser.error("Scoring requires telemetry from evals.realtime_benchmark with logged tracks")
    labels = read_csv(args.tracks, ("time_s", "object_id", "x1", "y1", "x2", "y2"))
    tracking, anchors = associate(labels, frames, args.frame_tolerance, args.roi)
    report = {"tracking": None if args.anchors_only else tracking, "alerts": None, "zones": None,
              "tracking_labels": str(args.tracks), "roi": args.roi, "frame_tolerance_s": args.frame_tolerance}
    if args.events:
        if not args.kinds or not args.window or not 0 <= args.window[0] < args.window[1]:
            parser.error("Event scoring requires --kinds and a valid --window")
        duration = json.loads((args.run / "summary.json").read_text(encoding="utf-8"))
        if args.window[1] > duration["decoded"]/duration["source_fps"]:
            parser.error("Event window must be inside the replay")
        truth = read_csv(args.events, ("time_s", "kind", "object_id"))
        report["alerts"] = score_alerts(frames, anchors, truth, args.kinds, *args.window,
                                        args.event_tolerance, args.frame_tolerance)
        report["event_window_s"] = args.window
    if args.zone_truth:
        truth = read_csv(args.zone_truth, ("second", "zone", "total"))
        pairs = []
        times = [frame["time_s"] for frame in frames]
        for row in truth:
            t = number(row["second"])
            frame = nearest_frame(frames, times, t)
            for zone in frame["zones"]:
                if zone["zone"] == row["zone"] and abs(frame["time_s"]-t) <= args.frame_tolerance:
                    pairs.append((number(row["total"]), zone["total"]))
        report["zones"] = {**errors(pairs), "labelled": len(truth)}
    (args.run / "accuracy.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
