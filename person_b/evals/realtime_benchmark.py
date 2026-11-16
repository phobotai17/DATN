"""Measure the dashboard's paced replay worker, including alert clip export."""
import argparse
from collections import Counter
import csv
from datetime import datetime
import json
from pathlib import Path
from time import monotonic

import numpy as np
import psutil
import torch

from evals.benchmark import ROOT, write_csv
from src.realtime import RealtimeSession
from src.traffic_analytics import validate_profile


def run(video, out, profile, device, skip, seconds):
    process = psutil.Process()
    if device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()
    started = monotonic()
    worker = RealtimeSession(str(video), ROOT, replay=True, profile=profile, device=device,
                             frame_skip=skip, max_seconds=seconds, output_dir=out, log_tracks=True)
    worker.start()
    rss = process.memory_info().rss
    while worker.thread.is_alive():
        worker.thread.join(.25)
        worker.snapshot()
        rss = max(rss, process.memory_info().rss)
        if monotonic() - started > seconds + 120:
            worker.stop()
            raise RuntimeError("Replay exceeded its deadline")
    state = worker.snapshot()
    if state.get("error") or not state["processed"]:
        raise RuntimeError(state.get("error", "No frame was processed"))
    elapsed = monotonic() - started
    latencies = []
    with (out / "telemetry.jsonl").open(encoding="utf-8") as log:
        for line in log:
            latencies.append(json.loads(line)["ready_ms"])
    with (out / "violations.csv").open(encoding="utf-8-sig", newline="") as csv_file:
        clips = Counter(row["clip_status"] for row in csv.DictReader(csv_file))
    frames = state["processed"]
    accounted = frames + state["skipped"] + state["dropped"]
    return dict(device=device, frame_skip="auto" if skip is None else skip,
                source_fps=state["source_fps"], decoded=state["decoded"], processed=frames,
                skipped=state["skipped"], dropped=state["dropped"], unaccounted=state["decoded"]-accounted,
                processed_fps=round(state["processed_fps"], 2), wall_seconds=round(elapsed, 2),
                video_seconds=round(state["decoded"]/state["source_fps"], 2),
                p50_ms=round(float(np.percentile(latencies, 50)), 2),
                p95_ms=round(float(np.percentile(latencies, 95)), 2),
                peak_process_rss_mib=round(rss/2**20, 1),
                peak_torch_cuda_mib=round(torch.cuda.max_memory_allocated()/2**20, 1)
                if device.startswith("cuda") else None,
                alerts=sum(clips.values()), clips_saved=clips["saved"],
                clips_busy=clips["skipped_busy"], clips_failed=clips["encode_failed"],
                crossings=sum(state["crossings"].values()), out=out.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, default=ROOT / "data/cam5.mp4")
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--devices", nargs="+", choices=["cpu", "cuda:0"], default=["cpu", "cuda:0"])
    parser.add_argument("--skips", nargs="+", choices=["0", "1", "2", "3", "auto"],
                        default=["0", "1", "2", "3", "auto"])
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.seconds <= 0 or args.repeat <= 0 or not args.video.is_file():
        parser.error("Provide an existing video and positive duration and repeat count")
    if "cuda:0" in args.devices and not torch.cuda.is_available():
        parser.error("CUDA unavailable. Use --devices cpu")
    profile = validate_profile(json.loads(args.profile.read_text(encoding="utf-8-sig"))) if args.profile else None
    out = args.out or ROOT / "evals/runs" / datetime.now().strftime("realtime-%Y%m%d-%H%M%S-%f")
    out.mkdir(parents=True)
    metadata = {"video": str(args.video.resolve()), "profile": profile, "seconds": args.seconds,
                "torch": torch.__version__, "cpu_threads": torch.get_num_threads(),
                "gpu": torch.cuda.get_device_name() if torch.cuda.is_available() else None}
    (out / "experiment.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    rows = []
    for device in args.devices:
        for mode in args.skips:
            for repeat in range(1, args.repeat + 1):
                row = run(args.video.resolve(), out / f"{device.replace(':', '')}-skip-{mode}-{repeat}",
                          profile, device, None if mode == "auto" else int(mode), args.seconds)
                rows.append(row)
                write_csv(out / "comparison.csv", rows, tuple(row))
                print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
