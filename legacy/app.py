"""
Streamlit tester for the trained YOLOv8s traffic model (optimized video pipeline).

Run:
    pip install streamlit ultralytics opencv-python pandas
    streamlit run app.py

Optional: put ffmpeg on PATH. The app then streams frames straight into an
H.264 encoder (browser-playable, no second re-encode pass).
"""
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import streamlit as st
import torch
from PIL import Image
from ultralytics import YOLO

DEFAULT_WEIGHTS = str(Path(__file__).resolve().parents[0] / "person_b/data/goi_ban_giao_B/models/best_v2.pt")


def cuda_supports_weights(weights_path: str) -> bool:
    if not torch.cuda.is_available():
        return False
    if Path(weights_path).suffix.lower() != ".onnx":
        return True
    try:
        import onnxruntime
    except (ImportError, OSError):
        return False
    return "CUDAExecutionProvider" in onnxruntime.get_available_providers()



st.set_page_config(page_title="Traffic model tester", layout="wide")
st.title("Traffic detection model tester")


# ---------------------------------------------------------------- sidebar --
with st.sidebar:
    st.header("Settings")
    weights_path = st.text_input("Weights (.pt or .onnx)", DEFAULT_WEIGHTS)
    conf = st.slider("Confidence threshold", 0.05, 0.95, 0.30, 0.05)
    iou = st.slider("NMS IoU threshold", 0.1, 0.9, 0.70, 0.05)
    cuda_ready = cuda_supports_weights(weights_path)
    device_options = ["Auto", "CPU"]
    if cuda_ready:
        device_options.append("GPU")
    device_choice = st.selectbox("Device", device_options)
    device = 0 if cuda_ready and device_choice != "CPU" else "cpu"
    use_onnx = Path(weights_path).suffix.lower() == ".onnx"
    imgsz = st.select_slider("Inference size", options=[320, 416, 512, 640, 800, 960],
                            value=416 if device == "cpu" else 640)
    use_half = st.checkbox(
        "FP16 (faster on GPU)", value=(device != "cpu"),
        disabled=(device == "cpu" or use_onnx),
    )
    half = bool(use_half and device != "cpu" and not use_onnx)


@st.cache_resource(show_spinner="Loading model...")
def load_model(path: str, dev, imgsz: int, half: bool) -> YOLO:
    m = YOLO(path)
    # Warm-up so the first real frame doesn't pay CUDA/cuDNN init cost
    m.predict(np.zeros((imgsz, imgsz, 3), np.uint8), imgsz=imgsz, device=dev, quantize=16 if half else None, verbose=False)
    return m


if not Path(weights_path).exists():
    st.error(f"Weights not found: {weights_path}")
    st.stop()

model = load_model(weights_path, device, imgsz, half)
class_names = model.names
active_device = model.predictor.model.device
using_gpu = active_device.type == "cuda"
device_label = torch.cuda.get_device_name(active_device) if using_gpu else "CPU"
st.sidebar.caption(f"Inference device: {device_label}")


def counts_table(counts: dict, col: str = "count") -> pd.DataFrame:
    return pd.DataFrame({"class": list(counts.keys()), col: list(counts.values())}).sort_values("class")


# ------------------------------------------------------------------ image --
def run_image():
    files = st.file_uploader(
        "Upload image(s)", type=["jpg", "jpeg", "png", "bmp", "webp"], accept_multiple_files=True
    )
    for f in files or []:
        img = Image.open(f).convert("RGB")
        res = model.predict(
            np.array(img), conf=conf, iou=iou, imgsz=imgsz, device=device, quantize=16 if half else None, verbose=False
        )[0]
        annotated = res.plot()[:, :, ::-1]

        counts = defaultdict(int)
        for c in res.boxes.cls.tolist():
            counts[class_names[int(c)]] += 1

        left, right = st.columns([3, 1])
        left.image(annotated, caption=f.name, use_container_width=True)
        with right:
            st.subheader("Detections")
            if counts:
                st.dataframe(counts_table(counts), hide_index=True)
            else:
                st.info("Nothing detected. Try lowering the confidence threshold.")


# ------------------------------------------------------- video: IO helpers --
def start_reader(path: str, stride: int, limit: int, stop: threading.Event) -> "queue.Queue":
    """Decode frames on a background thread so the GPU never waits on disk/decode.
    grab() skips decoding for frames dropped by `stride`."""
    q: queue.Queue = queue.Queue(maxsize=32)

    def put(item):
        while not stop.is_set():
            try:
                q.put(item, timeout=0.2)
                return True
            except queue.Full:
                continue
        return False

    def run():
        cap = cv2.VideoCapture(path)
        i = sent = 0
        while sent < limit and not stop.is_set():
            if not cap.grab():
                break
            if i % stride == 0:
                ok, frame = cap.retrieve()
                if not ok or not put(frame):
                    break
                sent += 1
            i += 1
        cap.release()
        put(None)

    threading.Thread(target=run, daemon=True).start()
    return q


class VideoSink:
    """Encodes on a background thread. Uses an ffmpeg H.264 pipe when available
    (plays in the browser), otherwise falls back to OpenCV's mp4v writer."""

    def __init__(self, path: str, fps: float, size: tuple):
        self.path, self.failed = path, False
        self.q: queue.Queue = queue.Queue(maxsize=64)
        w, h = size
        ffmpeg = shutil.which("ffmpeg")
        self.h264 = ffmpeg is not None
        if self.h264:
            self.proc = subprocess.Popen(
                [ffmpeg, "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                 "-r", f"{fps:.3f}", "-i", "-", "-an", "-vcodec", "libx264",
                 "-preset", "ultrafast", "-crf", "24", "-pix_fmt", "yuv420p", path],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            self.writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        self.t = threading.Thread(target=self._run, daemon=True)
        self.t.start()

    def _run(self):
        while True:
            fr = self.q.get()
            if fr is None:
                break
            try:
                if self.h264:
                    self.proc.stdin.write(np.ascontiguousarray(fr).tobytes())
                else:
                    self.writer.write(fr)
            except (BrokenPipeError, OSError):
                self.failed = True
                break
        try:
            if self.h264:
                self.proc.stdin.close()
                self.proc.wait()
            else:
                self.writer.release()
        except OSError:
            pass

    def write(self, frame):
        if not self.failed:
            self.q.put(frame)

    def close(self):
        if not self.failed:
            self.q.put(None)
        self.t.join()


# ------------------------------------------------------------ video: main --
def process_video(path, use_tracking, stride, max_frames, det_batch, max_out_w, min_track_frames,
                  show_labels, show_conf):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    avail = max(1, total // stride) if total > 0 else 10**9
    limit = avail if max_frames == 0 else min(avail, int(max_frames))

    # Output size: optionally downscaled, always even (required by yuv420p)
    scale = min(1.0, max_out_w / w) if max_out_w else 1.0
    ow, oh = int(w * scale) // 2 * 2, int(h * scale) // 2 * 2
    resize_out = (ow, oh) != (w, h)

    out_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
    sink = VideoSink(out_path, fps / stride, (ow, oh))

    stop = threading.Event()
    q = start_reader(path, stride, limit, stop)

    seen = defaultdict(int)          # (class, track_id) -> frames seen
    det_totals = defaultdict(int)    # class -> total detections (no-tracking mode)
    infer_ms = []
    n = 0

    progress = st.progress(0.0, text="Starting...")
    preview = st.empty()
    last_ui = 0.0
    t0 = time.perf_counter()
    batch_size = 1 if use_tracking else det_batch  # tracking is sequential by nature
    buf = []

    def handle(res):
        nonlocal n, last_ui
        annotated = res.plot(line_width=2, labels=show_labels, conf=show_conf)
        if resize_out:
            annotated = cv2.resize(annotated, (ow, oh), interpolation=cv2.INTER_LINEAR)
        sink.write(annotated)

        infer_ms.append(res.speed.get("inference", 0.0))
        cls_list = res.boxes.cls.int().tolist()
        if use_tracking:
            if res.boxes.id is not None:
                for tid, c in zip(res.boxes.id.int().tolist(), cls_list):
                    seen[(class_names[c], tid)] += 1
        else:
            for c in cls_list:
                det_totals[class_names[c]] += 1

        n += 1
        now = time.perf_counter()
        if now - last_ui > 0.4 or n == limit:  # throttle UI updates (they are expensive)
            last_ui = now
            progress.progress(min(n / limit, 1.0), text=f"Frame {n}/{limit} - {n / (now - t0):.1f} FPS")
            pv = annotated
            if pv.shape[1] > 640:
                pv = cv2.resize(pv, (640, int(pv.shape[0] * 640 / pv.shape[1])))
            preview.image(pv[:, :, ::-1], caption="Live preview")

    def run_batch(frames):
        if use_tracking:
            # persist=False on the first frame resets ByteTrack state from any previous run
            res = model.track(
                frames[0], persist=(n > 0), tracker="bytetrack.yaml", conf=conf, iou=iou,
                imgsz=imgsz, device=device, quantize=16 if half else None, verbose=False,
            )
        else:
            res = model.predict(
                frames, conf=conf, iou=iou, imgsz=imgsz, device=device, quantize=16 if half else None, verbose=False
            )
        for r in res:
            handle(r)

    try:
        while True:
            frame = q.get()
            if frame is None:
                break
            buf.append(frame)
            if len(buf) >= batch_size:
                run_batch(buf)
                buf = []
        if buf:
            run_batch(buf)
    finally:
        stop.set()
        sink.close()
        progress.empty()
        preview.empty()

    elapsed = time.perf_counter() - t0
    result = {
        "path": out_path,
        "playable": sink.h264,
        "frames": n,
        "fps": n / elapsed if elapsed else 0,
        "infer_ms": float(np.mean(infer_ms)) if infer_ms else 0.0,
        "tracking": use_tracking,
    }
    if use_tracking:
        # Ignore very short tracks: they are mostly flicker / ID switches that inflate counts
        agg = defaultdict(int)
        for (cname, _), frames_seen in seen.items():
            if frames_seen >= min_track_frames:
                agg[cname] += 1
        result["counts"] = dict(agg)
    else:
        result["counts"] = {k: round(v / max(n, 1), 2) for k, v in det_totals.items()}
    return result


def run_video():
    c1, c2, c3 = st.columns(3)
    use_tracking = c1.checkbox("Track objects (ByteTrack)", value=True)
    max_frames = c2.number_input("Max frames (0 = all)", min_value=0, value=300, step=100)
    stride = c3.number_input(
        "Process every Nth frame", min_value=1, max_value=10, value=1,
        help="Higher = faster, but tracking gets less reliable and output FPS drops.",
    )
    c4, c5, c6 = st.columns(3)
    max_out_w = c4.select_slider("Output width", options=[480, 640, 960, 1280, 1920, 0], value=1280,
                                 format_func=lambda v: "original" if v == 0 else f"{v}px")
    det_batch = c5.slider("Batch size (no tracking)", 1, 16, 4 if using_gpu else 1, disabled=use_tracking)
    min_track_frames = c6.slider("Min frames to count a track", 1, 30, 5, disabled=not use_tracking)
    c7, c8 = st.columns(2)
    show_labels = c7.checkbox("Draw labels", value=True)
    show_conf = c8.checkbox("Draw confidence", value=False)

    f = st.file_uploader("Upload video", type=["mp4", "avi", "mov", "mkv"])
    if f is not None:
        # Save the upload once per file, not on every Streamlit rerun
        key = (f.name, f.size)
        if st.session_state.get("video_key") != key:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(f.name).suffix)
            tmp.write(f.getbuffer())
            tmp.close()
            st.session_state.update(video_key=key, video_path=tmp.name, video_result=None)

        if st.button("Run on video", type="primary"):
            st.session_state["video_result"] = process_video(
                st.session_state["video_path"], use_tracking, int(stride), int(max_frames),
                int(det_batch), int(max_out_w), int(min_track_frames), show_labels, show_conf,
            )

    # Results live in session_state so clicking Download doesn't wipe them
    res = st.session_state.get("video_result")
    if res:
        st.success(
            f"{res['frames']} frames in {res['frames'] / res['fps']:.1f}s "
            f"({res['fps']:.1f} FPS overall, {res['infer_ms']:.1f} ms/frame model time)"
        )
        left, right = st.columns([3, 1])
        with left:
            if res["playable"]:
                st.video(res["path"])
            else:
                st.info("ffmpeg not found on PATH, so inline playback is unavailable. Download the file instead.")
            with open(res["path"], "rb") as fh:
                st.download_button("Download annotated video", fh, file_name="annotated.mp4", mime="video/mp4")
        with right:
            if res["tracking"]:
                st.subheader("Unique tracks")
                st.dataframe(counts_table(res["counts"], "tracks"), hide_index=True)
            else:
                st.subheader("Avg per frame")
                st.dataframe(counts_table(res["counts"], "avg/frame"), hide_index=True)


# ----------------------------------------------------------------- layout --
tab_img, tab_vid = st.tabs(["Image", "Video"])
with tab_img:
    run_image()
with tab_vid:
    run_video()
