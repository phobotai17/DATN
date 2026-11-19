"""Bản pipeline đọc video bằng luồng riêng (giải mã chồng với suy luận). Kết quả giống hệt TrafficPipeline."""
import queue
import threading

import cv2

from traffic_pipeline import TrafficPipeline, run_to_files  # noqa: F401


class FastPipeline(TrafficPipeline):
    def run(self, source, max_frames=None, annotate=True, qsize=6):
        cap = cv2.VideoCapture(source)
        self._setup_fps(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        self._reset_state()
        stride = self.cfg["stride"]
        q = queue.Queue(maxsize=qsize)
        stop = threading.Event()

        def reader():
            g = -1
            while not stop.is_set():
                if not cap.grab():
                    break
                g += 1
                if g % stride:
                    continue
                ok, fr = cap.retrieve()
                if not ok:
                    break
                q.put((g, fr))
            q.put(None)

        th = threading.Thread(target=reader, daemon=True)
        th.start()
        n = 0
        try:
            while True:
                item = q.get()
                if item is None:
                    break
                g, fr = item
                yield self.process_frame(fr, g, annotate)
                n += 1
                if max_frames and n >= max_frames:
                    break
        finally:
            stop.set()
            try:
                while True:
                    q.get_nowait()
            except queue.Empty:
                pass
            th.join(timeout=3)
            cap.release()
