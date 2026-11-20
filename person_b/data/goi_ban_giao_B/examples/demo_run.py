"""Chạy thử pipeline trên clip demo: in cảnh báo, đếm xe và lưu một ảnh đã vẽ."""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import cv2
from traffic_pipeline_fast import FastPipeline

pipe = FastPipeline(str(ROOT / "models" / "best_v2.pt"), clock0="2026-04-09 13:47:00",
                    tracker_yaml=str(ROOT / "bytetrack_v1.yaml"))
n, t0, saved, out = 0, time.time(), False, None
for out in pipe.run(str(ROOT / "demo" / "clip_ngc.mp4"), annotate=True):
    if n == 0:
        print(f"Inference device: {pipe.device}", flush=True)
    n += 1
    for a in out["new_alerts"]:
        print(f"CANH BAO {a['gio_canh_bao']} #{a['track_id']} {a['loai']} vi tri ({a['x']},{a['y']})")
    if out["new_alerts"] and not saved:
        cv2.imwrite(str(ROOT / "demo_alert.jpg"), out["annotated"])
        saved = True
print(f"{n} khung, {n / (time.time() - t0):.1f} FPS | dem xe: {out['counts']}")

