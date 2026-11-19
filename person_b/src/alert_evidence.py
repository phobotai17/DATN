"""Bounded evidence capture with software H.264 encoding."""
import csv
from collections import deque
from queue import Full, Queue
from subprocess import DEVNULL, PIPE, Popen
from threading import Lock, Thread

import cv2


class AlertEvidence:
    fps = 8
    fields = ("time_s", "track_id", "event", "vehicle_class", "zone", "speed",
              "speed_unit", "peer_median", "peer_count", "angle_deg", "clip", "clip_status")

    def __init__(self, folder):
        self.folder = folder
        self.history = deque(maxlen=25)
        self.pending = []
        self.jobs = Queue(maxsize=4)
        self.last_sample = float("-inf")
        self.sequence = 0
        self.csv_file = (folder / "violations.csv").open("w", newline="", encoding="utf-8-sig")
        self.writer = csv.DictWriter(self.csv_file, self.fields, extrasaction="ignore")
        self.writer.writeheader()
        self.csv_file.flush()
        self.lock = Lock()
        self.thread = Thread(target=self._encode_jobs, daemon=True)
        self.thread.start()

    def _record(self, event, status):
        with self.lock:
            self.writer.writerow({**event, "clip_status": status})
            self.csv_file.flush()

    def update(self, timestamp, frame, tracks, alerts, source_shape):
        if alerts or timestamp - self.last_sample >= 1 / self.fps:
            self.last_sample = timestamp
            sx, sy = frame.shape[1] / source_shape[1], frame.shape[0] / source_shape[0]
            boxes = {r["track_id"]: (round(r["x1"]*sx), round(r["y1"]*sy),
                                     round(r["x2"]*sx), round(r["y2"]*sy)) for r in tracks}
            sample = (timestamp, frame, boxes)
            self.history.append(sample)
            for event, frames in self.pending:
                if timestamp <= event["time_s"] + 3:
                    frames.append(sample)
        for alert in alerts:
            self.sequence += 1
            event = dict(alert, clip=f"clips/track_{int(alert['track_id'])}_{self.sequence:06d}.mp4")
            event["vehicle_class"] = next((r["loai"] for r in tracks if r["track_id"] == alert["track_id"]), "")
            if len(self.pending) >= 8:
                self._record(dict(event, clip=""), "skipped_busy")
            else:
                self.pending.append((event, [s for s in self.history if s[0] >= timestamp - 3]))
        for event, frames in self.pending.copy():
            if timestamp >= event["time_s"] + 3:
                self.pending.remove((event, frames))
                self._submit(event, frames)

    def _submit(self, event, frames):
        try:
            self.jobs.put_nowait((event, frames))
        except Full:
            self._record(dict(event, clip=""), "skipped_busy")

    def _encode_jobs(self):
        while (job := self.jobs.get()) is not None:
            event, frames = job
            try:
                self._encode(event, frames)
            except Exception:
                self._record(dict(event, clip=""), "encode_failed")
            else:
                self._record(event, "saved")

    def _encode(self, event, frames):
        from imageio_ffmpeg import get_ffmpeg_exe

        path = self.folder / event["clip"]
        path.parent.mkdir(exist_ok=True)
        temp = path.with_suffix(".part.mp4")
        h, w = frames[0][1].shape[:2]
        w, h = w // 2 * 2, h // 2 * 2
        command = [get_ffmpeg_exe(), "-nostdin", "-loglevel", "error", "-y",
                   "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(self.fps),
                   "-i", "-", "-an", "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1",
                   "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temp)]
        try:
            first, last = frames[0][0], frames[-1][0]
            index = 0
            with Popen(command, stdin=PIPE, stdout=DEVNULL, stderr=DEVNULL) as encoder:
                with encoder.stdin as sink:
                    for i in range(round((last-first)*self.fps) + 1):
                        t = first + i / self.fps
                        while index + 1 < len(frames) and frames[index+1][0] <= t:
                            index += 1
                        _, frame, boxes = frames[index]
                        image = frame[:h, :w].copy()
                        box = boxes.get(event["track_id"])
                        if box:
                            x1, y1, x2, y2 = box
                            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 0, 255), 3)
                        cv2.putText(image, f"ID {event['track_id']} | {event['event']}", (10, 25),
                                    cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 0, 255), 2)
                        sink.write(image.tobytes())
                if encoder.wait():
                    raise RuntimeError("Software video encoding failed")
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)

    def close(self):
        for event, frames in self.pending:
            self._submit(event, frames)
        self.pending.clear()
        self.jobs.put(None)
        self.thread.join()
        self.csv_file.close()
