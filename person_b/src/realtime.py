"""Background real-time traffic processing with a latest-frame buffer."""
from collections import deque
from datetime import datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from queue import Queue, Empty, Full
from threading import Event, Lock, Thread
from time import monotonic
from tempfile import TemporaryDirectory
import json
import math
import os
import traceback

import cv2
import numpy as np


class RealtimeSession:
    @classmethod
    def from_local_video(cls, source, root, **options):
        folder = Path(os.environ.get("TRAFFIC_VIDEO_DIR") or Path(root)).resolve()
        path = Path(source.strip().strip('"').strip())
        try:
            path = (folder / path).resolve()
            if not path.is_relative_to(folder):
                raise ValueError("Video phải nằm trong thư mục dự án hoặc TRAFFIC_VIDEO_DIR.")
            if path.suffix.lower() not in {".mp4", ".mov", ".avi", ".mkv", ".webm"} or not path.is_file():
                raise ValueError("Không tìm thấy tệp video được hỗ trợ.")
        except (OSError, RuntimeError) as error:
            raise ValueError("Không đọc được đường dẫn video.") from error
        return cls(str(path), root, replay=True, **options)

    def __init__(self, source, root, *, replay=False, profile=None, analytics_options=None, frame_skip=None,
                 count_labels=None, device="auto", max_seconds=None, output_dir=None, log_tracks=False):
        self.source, self.root = source, Path(root)
        self.replay, self.profile = replay, profile
        self.analytics_options = dict(analytics_options or {})
        if frame_skip is not None and frame_skip not in range(4):
            raise ValueError("Số khung hình bỏ qua phải từ 0 đến 3.")
        self.frame_skip = frame_skip
        self.count_labels = dict(count_labels or {})
        self.device = device
        self.max_seconds = max_seconds
        self.output_dir = output_dir
        self.log_tracks = log_tracks
        self.decoded = self.skipped = 0
        self.sampling_period = 1 / 20
        self.stop_event = Event()
        self.capture_done = Event()
        self.frames = Queue(maxsize=1)
        self.lock = Lock()
        self.latest = {"status": "Đang khởi động", "processed": 0, "time_s": 0.0}
        self.last_viewed = monotonic()
        self.dropped = 0
        self.thread = Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.stop_event.set()

    def snapshot(self):
        self.last_viewed = monotonic()
        with self.lock:
            return dict(self.latest)

    def publish(self, **values):
        with self.lock:
            self.latest.update(values)

    def _capture(self):
        cap = None
        try:
            if isinstance(self.source, int) or self.replay:
                cap = cv2.VideoCapture(self.source)
            else:
                cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG, [
                    cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000,
                ])
            if not cap.isOpened():
                raise ValueError("Không mở được nguồn video.")
            fps = cap.get(cv2.CAP_PROP_FPS)
            fps = fps if math.isfinite(fps) and fps > 0 else 25.
            self.publish(source_fps=fps, frame_skip=self.frame_skip)
            beginning, index = monotonic(), 0
            last_selected = -math.inf
            while not self.stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    if not self.replay:
                        self.publish(error="Mất kết nối camera. Dừng phiên và kết nối lại.")
                    break
                if self.replay:
                    if index == 0:
                        beginning = monotonic()
                    if self.stop_event.wait(max(0, beginning + index / fps - monotonic())):
                        break
                    timestamp = index / fps
                else:
                    timestamp = monotonic() - beginning
                if self.max_seconds is not None and timestamp >= self.max_seconds:
                    break
                self.decoded += 1
                manual_skip = self.frame_skip is not None and index % (self.frame_skip + 1)
                adaptive_skip = self.frame_skip is None and timestamp - last_selected < self.sampling_period
                if manual_skip or adaptive_skip:
                    self.skipped += 1
                    index += 1
                    continue
                last_selected = timestamp
                item = (timestamp, monotonic(), frame)
                try:
                    self.frames.put_nowait(item)
                except Full:
                    try:
                        self.frames.get_nowait()
                        self.dropped += 1
                    except Empty:
                        pass
                    self.frames.put_nowait(item)
                if self.replay and index == 0:
                    # Keep frame zero available until the analysis worker takes it.
                    while not self.frames.empty():
                        if self.stop_event.wait(.005):
                            return
                    beginning = monotonic()
                index += 1
        except Exception:
            self.publish(error="Không đọc được camera. Kiểm tra nguồn hoặc kết nối.")
        finally:
            if cap is not None:
                cap.release()
            self.capture_done.set()

    def _run(self):
        capture = None
        evidence = None
        try:
            import torch
            from ultralytics import YOLO
            from src.traffic_analytics import TrafficAnalytics
            from src.alert_evidence import AlertEvidence
            from src.forecast_truth import forecast_errors
            package = self.root / "data/goi_ban_giao_B"
            spec = spec_from_file_location("realtime_traffic_pipeline", package / "src/traffic_pipeline.py")
            module = module_from_spec(spec)
            spec.loader.exec_module(module)
            device = self.device
            if device == "auto":
                device = "cuda:0" if torch.cuda.is_available() else "cpu"
            if device.startswith("cuda") and not torch.cuda.is_available():
                raise ValueError("CUDA is unavailable.")
            model = YOLO(str(package / "models/best_v2.pt"))
            # Benchmark actual inference before choosing the sampling period.
            timings = []
            for _ in range(4):
                start = monotonic()
                model.predict(np.zeros((384, 640, 3), np.uint8), imgsz=(384, 640),
                              device=device, quantize=16 if device != "cpu" else None, verbose=False)
                timings.append(monotonic() - start)
            period = max(1 / 20, float(np.median(timings[1:])) * 1.2)
            self.sampling_period = period
            self.publish(device=device, status="Đang chạy", benchmark_ms=1000 * np.median(timings[1:]))
            output = self.output_dir or self.root / "results/realtime" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            output.mkdir(parents=True)
            evidence = AlertEvidence(output)
            self.publish(log_dir=str(output), evidence_csv=str(output / "violations.csv"))
            capture = Thread(target=self._capture, daemon=True)
            capture.start()
            history, alerts, latency = deque(maxlen=1200), deque(maxlen=100), deque(maxlen=300)
            forecasts = deque(maxlen=400)
            error_sum = error_count = 0
            processed, last_sample, last_forecast, last_time = 0, -1, -1, -1.
            wall_start = monotonic()
            with TemporaryDirectory() as temp, (output / "telemetry.jsonl").open("w", encoding="utf-8") as log:
                pipe = engine = None
                last_seen = {}
                while not self.stop_event.is_set():
                    if monotonic() - self.last_viewed > 120:
                        self.publish(status="Dừng do dashboard không còn kết nối")
                        break
                    try:
                        timestamp, arrived, frame = self.frames.get(timeout=.25)
                    except Empty:
                        if self.capture_done.is_set():
                            break
                        continue
                    if timestamp <= last_time:
                        continue
                    started = monotonic()
                    if pipe is None:
                        h, w = frame.shape[:2]
                        profile = self.profile or {"frame_size": [w, h], "zones": {
                            "road": [[0, 0], [w-1, 0], [w-1, h-1], [0, h-1]]}}
                        if tuple(profile["frame_size"]) != (w, h):
                            raise ValueError("Kích thước cấu hình phải khớp video nguồn.")
                        engine = TrafficAnalytics(profile, **self.analytics_options)
                        scale = min(1., 640 / w, 384 / h)
                        pipe = module.TrafficPipeline(str(package / "models/best_v2.pt"),
                            cfg={"wrongway_enabled": False, "count_line_y": int(h*.55),
                                 "device": device, "half": device != "cpu", "stride": 1,
                                 "imgsz": (384, 640),
                                 "inference_size": (max(2, int(w*scale)), max(2, int(h*scale)))},
                            tracker_yaml=str(Path(temp) / "tracker.yaml"), model=model)
                        pipe._setup_fps(1000)
                    result = pipe.process_frame(frame, round(timestamp*1000), annotate=True)
                    measurement = engine.update(timestamp, result["tracks"])
                    last_time = timestamp
                    for row in result["tracks"]:
                        last_seen[row["track_id"]] = timestamp
                    expired = [tid for tid, seen in last_seen.items() if timestamp-seen > 30]
                    for tid in expired:
                        for name in ("votes", "age", "asp", "prev_by", "tr", "red"):
                            getattr(pipe, name).pop(tid, None)
                        pipe.counted.discard(tid)
                        del last_seen[tid]
                    alerts.extend(measurement["alerts"])
                    history_changed = int(timestamp) != last_sample
                    if history_changed:
                        history.extend(measurement["zones"])
                        last_sample = int(timestamp)
                        self.publish(zone_history=list(history))
                        totals = {z["zone"]: z["total"] for z in measurement["zones"]}
                        while forecasts and forecasts[0]["target"] <= timestamp:
                            forecast = forecasts.popleft()
                            errors = forecast_errors(forecast, self.count_labels)
                            error_sum += sum(errors)
                            error_count += len(errors)
                        if int(timestamp)//60 > last_forecast:
                            values = {}
                            for zone in totals:
                                recent = [z["total"] for z in history
                                          if z["zone"] == zone and z["time_s"] > timestamp-60]
                                values[zone] = float(np.mean(recent))
                            forecasts.append({"origin": last_sample, "target": last_sample+300, "values": values})
                            last_forecast = int(timestamp)//60
                            self.publish(forecast=forecasts[-1])
                            new_forecast = forecasts[-1]
                        else:
                            new_forecast = None
                    else:
                        new_forecast = None
                    telemetry = {"time_s": timestamp, "zones": measurement["zones"],
                                 "alerts": measurement["alerts"], "crossings": result["new_events"],
                                 "movements": list(engine.movements), "forecast": new_forecast}
                    if self.log_tracks:
                        telemetry["tracks"] = result["tracks"]
                    pipe.events.clear()
                    pipe.alerts.clear()
                    engine.alerts.clear()
                    engine.movements.clear()
                    display = result["annotated"]
                    for zone, polygon in engine.polygons["zones"].items():
                        cv2.polylines(display, [polygon.astype(np.int32)], True, (0, 210, 255), 2)
                    active = {event["track_id"] for event in alerts if timestamp-event["time_s"] <= 3}
                    parked = {row["track_id"] for row in measurement["tracks"] if row["parked"]}
                    for row in result["tracks"]:
                        if row["track_id"] in parked or row["track_id"] in active:
                            label = "PARKING" if row["track_id"] in parked else "CHECK"
                            cv2.putText(display, f"{label} #{row['track_id']}",
                                        (row["x1"], max(20, row["y1"]-8)),
                                        cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 0, 255), 2)
                    scale = min(1., 960/display.shape[1])
                    display = cv2.resize(display, (int(display.shape[1]*scale), int(display.shape[0]*scale)))
                    evidence.update(timestamp, display, result["tracks"], measurement["alerts"], frame.shape)
                    elapsed = monotonic()-started
                    period = .9*period + .1*max(1/20, elapsed*1.15)
                    self.sampling_period = period
                    processed += 1
                    latency.append(monotonic()-arrived)
                    telemetry["ready_ms"] = latency[-1]*1000
                    log.write(json.dumps(telemetry, ensure_ascii=False) + "\n")
                    log.flush()
                    self.publish(frame=display, processed=processed, time_s=timestamp, dropped=self.dropped,
                        skipped=self.skipped, decoded=self.decoded,
                        processed_fps=processed/max(monotonic()-wall_start, .001),
                        latency_ms=latency[-1]*1000, p95_ms=float(np.percentile(latency, 95))*1000,
                        sampling_fps=1/period, zones=measurement["zones"], alerts=list(alerts),
                        crossings={direction: sum(counts.values())
                                   for direction, counts in pipe.counts.items()},
                        forecast_mae=error_sum/error_count if error_count else None,
                        forecast_samples=error_count)
        except Exception as error:
            self.publish(error=f"{type(error).__name__}: {error}")
            traceback.print_exc()
        finally:
            self.stop_event.set()
            if capture is not None:
                capture.join(timeout=6)
            if evidence is not None:
                self.publish(status="Đang hoàn tất xuất clip")
                evidence.close()
            self.publish(status="Đã dừng", decoded=self.decoded, skipped=self.skipped, dropped=self.dropped)
            state = self.snapshot()
            if state.get("log_dir"):
                summary = {key: value for key, value in state.items()
                           if key not in ("frame", "alerts", "zones", "zone_history")}
                (Path(state["log_dir"]) / "summary.json").write_text(
                    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
