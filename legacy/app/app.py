"""
Vehicle detection + tracking + line-crossing counting for video,
using the trained YOLOv8s traffic model.

Run:
    pip install streamlit ultralytics opencv-python pandas
    streamlit run app.py

Optional: put ffmpeg on PATH for browser-playable H.264 output.
"""
import atexit
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import streamlit as st
from ultralytics import YOLO

DEFAULT_WEIGHTS = str(Path(__file__).resolve().parents[1] / "person_b/data/goi_ban_giao_B/models/best_v2.pt")

st.set_page_config(page_title="Vehicle detection (video)", layout="wide")
st.title("Vehicle detection, tracking & counting")

# ---------------------------------------------------------------- sidebar --
with st.sidebar:
    st.header("Model")
    weights_path = st.text_input("Weights (.pt or .onnx)", DEFAULT_WEIGHTS)
    conf = st.slider("Confidence", 0.05, 0.95, 0.30, 0.05)
    iou = st.slider("NMS IoU", 0.1, 0.9, 0.70, 0.05)
    imgsz = st.select_slider("Inference size", [320, 416, 512, 640, 800, 960], value=640)
    device_choice = st.selectbox("Device", ["0 (GPU)", "cpu"])
    device = 0 if device_choice.startswith("0") else "cpu"
    is_onnx = weights_path.endswith(".onnx")
    half = bool(device != "cpu" and not is_onnx and
                st.checkbox("FP16 (faster on GPU)", value=True, disabled=(device == "cpu" or is_onnx)))

    st.header("Tracking")
    min_track_frames = st.slider("Min frames before a track counts", 1, 30, 5,
                                 help="Filters flicker and ID switches that inflate counts.")

    st.header("Output")
    max_out_w = st.select_slider("Output width", [480, 640, 960, 1280, 1920, 0], value=1280,
                                 format_func=lambda v: "original" if v == 0 else f"{v}px")
    show_labels = st.checkbox("Draw labels", True)
    show_conf = st.checkbox("Draw confidence", False)


@st.cache_resource(show_spinner="Loading model...")
def load_model(path: str, dev, imgsz: int, half: bool) -> YOLO:
    m = YOLO(path)
    m.predict(np.zeros((imgsz, imgsz, 3), np.uint8), imgsz=imgsz, device=dev, quantize=16 if half else None, verbose=False)
    return m


if not Path(weights_path).exists():
    st.error(f"Weights not found: {weights_path}")
    st.stop()

model = load_model(weights_path, device, imgsz, half)
names = model.names


# ------------------------------------------------------- temp file cleanup --
@st.cache_resource
def get_workdir() -> Path:
    """One temp folder for every upload and annotated video; removed when the server exits."""
    d = Path(tempfile.mkdtemp(prefix="vehicle_app_"))
    atexit.register(shutil.rmtree, d, ignore_errors=True)
    return d


WORKDIR = get_workdir()


def safe_delete(path):
    """Delete a file, ignoring errors (e.g. Windows still holding a handle)."""
    if path:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass


def reset_session():
    """Delete the uploaded video and the annotated result, and forget them."""
    res = st.session_state.get("video_result")
    if res:
        safe_delete(res["path"])
    safe_delete(st.session_state.get("video_path"))
    for k in ("video_key", "video_path", "video_result"):
        st.session_state.pop(k, None)


# ------------------------------------------------------------- IO helpers --
def start_reader(path, stride, limit, stop):
    """Decode on a background thread; grab() skips decoding for dropped frames."""
    q = queue.Queue(maxsize=32)

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
    """Background encoder: ffmpeg H.264 pipe if available, else OpenCV mp4v."""

    def __init__(self, path, fps, size):
        self.failed = False
        self.q = queue.Queue(maxsize=64)
        w, h = size
        ffmpeg = shutil.which("ffmpeg")
        self.h264 = ffmpeg is not None
        if self.h264:
            self.proc = subprocess.Popen(
                [ffmpeg, "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                 "-r", f"{fps:.3f}", "-i", "-", "-an", "-vcodec", "libx264",
                 "-preset", "ultrafast", "-crf", "24", "-pix_fmt", "yuv420p", path],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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


def line_endpoints(orientation, pos_pct, w, h):
    if orientation == "Horizontal":
        y = int(h * pos_pct / 100)
        return (0, y), (w, y), y
    x = int(w * pos_pct / 100)
    return (x, 0), (x, h), x


# ------------------------------------------------------------- processing --
def process_video(path, stride, max_frames, orientation, pos_pct):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    avail = max(1, total // stride) if total > 0 else 10**9
    limit = avail if max_frames == 0 else min(avail, int(max_frames))

    scale = min(1.0, max_out_w / w) if max_out_w else 1.0
    ow, oh = int(w * scale) // 2 * 2, int(h * scale) // 2 * 2
    resize_out = (ow, oh) != (w, h)

    horizontal = orientation == "Horizontal"
    p1, p2, line_pos = line_endpoints(orientation, pos_pct, w, h)
    dir_neg, dir_pos = ("Up", "Down") if horizontal else ("Left", "Right")

    out_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4", dir=WORKDIR).name
    sink = VideoSink(out_path, fps / stride, (ow, oh))
    stop = threading.Event()
    q = start_reader(path, stride, limit, stop)

    age = defaultdict(int)       # track id -> frames seen
    cls_of = {}                  # track id -> latest class name
    last_side = {}               # track id -> -1 / +1 relative to the line
    counted = set()              # ids that already crossed (each id counts once)
    events = []                  # (time_s, track_id, class, direction)
    dir_totals = defaultdict(int)
    infer_ms = []
    n = 0

    progress = st.progress(0.0, text="Starting...")
    preview = st.empty()
    last_ui = 0.0
    t0 = time.perf_counter()

    def handle(res):
        nonlocal n, last_ui
        frame_t = n * stride / fps

        if res.boxes.id is not None:
            ids = res.boxes.id.int().tolist()
            cls = res.boxes.cls.int().tolist()
            xyxy = res.boxes.xyxy.cpu().numpy()
            for tid, c, (x1, y1, x2, y2) in zip(ids, cls, xyxy):
                age[tid] += 1
                cls_of[tid] = names[c]
                coord = (y1 + y2) / 2 if horizontal else (x1 + x2) / 2
                side = 1 if coord > line_pos else -1
                prev = last_side.get(tid)
                last_side[tid] = side
                if prev is not None and prev != side and tid not in counted and age[tid] >= min_track_frames:
                    counted.add(tid)
                    d = dir_pos if side > 0 else dir_neg
                    events.append((frame_t, tid, names[c], d))
                    dir_totals[d] += 1

        annotated = res.plot(line_width=2, labels=show_labels, conf=show_conf)
        cv2.line(annotated, p1, p2, (0, 255, 255), 3)
        cv2.putText(annotated, f"{dir_neg}: {dir_totals[dir_neg]}   {dir_pos}: {dir_totals[dir_pos]}",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2, cv2.LINE_AA)
        if resize_out:
            annotated = cv2.resize(annotated, (ow, oh), interpolation=cv2.INTER_LINEAR)
        sink.write(annotated)

        infer_ms.append(res.speed.get("inference", 0.0))
        n += 1
        now = time.perf_counter()
        if now - last_ui > 0.4 or n == limit:
            last_ui = now
            progress.progress(min(n / limit, 1.0), text=f"Frame {n}/{limit} - {n / (now - t0):.1f} FPS")
            pv = annotated
            if pv.shape[1] > 640:
                pv = cv2.resize(pv, (640, int(pv.shape[0] * 640 / pv.shape[1])))
            preview.image(pv[:, :, ::-1], caption="Live preview")

    try:
        while True:
            frame = q.get()
            if frame is None:
                break
            # persist=False on the first frame resets ByteTrack state from earlier runs
            res = model.track(frame, persist=(n > 0), tracker="bytetrack.yaml", conf=conf, iou=iou,
                              imgsz=imgsz, device=device, quantize=16 if half else None, verbose=False)[0]
            handle(res)
    finally:
        stop.set()
        sink.close()
        progress.empty()
        preview.empty()

    elapsed = time.perf_counter() - t0
    unique = defaultdict(int)
    for tid, a in age.items():
        if a >= min_track_frames:
            unique[cls_of[tid]] += 1

    return {
        "path": out_path, "playable": sink.h264, "frames": n, "fps": n / elapsed if elapsed else 0,
        "infer_ms": float(np.mean(infer_ms)) if infer_ms else 0.0,
        "duration_s": n * stride / fps, "unique": dict(unique), "events": events,
        "dirs": (dir_neg, dir_pos),
    }


def counts_csv(res, bucket_s, start_dt):
    """Wide CSV: one row per time bucket, one column per class, plus total."""
    ev = pd.DataFrame(res["events"], columns=["t", "id", "class", "direction"])
    n_buckets = max(1, int(np.ceil(res["duration_s"] / bucket_s)))
    index = pd.DatetimeIndex([start_dt + timedelta(seconds=i * bucket_s) for i in range(n_buckets)],
                             name="timestamp")
    classes = list(names.values())
    out = pd.DataFrame(0, index=index, columns=classes)
    if not ev.empty:
        ev["bucket"] = (ev["t"] // bucket_s).astype(int).clip(upper=n_buckets - 1)
        pivot = ev.pivot_table(index="bucket", columns="class", values="id", aggfunc="count", fill_value=0)
        for b, row in pivot.iterrows():
            for c, v in row.items():
                out.iloc[b, out.columns.get_loc(c)] = v
    out["total"] = out.sum(axis=1)
    return out.reset_index().to_csv(index=False).encode("utf-8")


# ----------------------------------------------------------------- layout --
f = st.file_uploader("Upload video", type=["mp4", "avi", "mov", "mkv"])
if f is None:
    reset_session()  # upload was removed: free the old input and annotated video
else:
    key = (f.name, f.size)
    if st.session_state.get("video_key") != key:
        reset_session()  # new upload: delete the previous input and annotated video first
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(f.name).suffix, dir=WORKDIR)
        tmp.write(f.getbuffer())
        tmp.close()
        st.session_state.update(video_key=key, video_path=tmp.name, video_result=None)

    path = st.session_state["video_path"]
    cap = cv2.VideoCapture(path)
    ok, first = cap.read()
    vw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    vh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    if not ok:
        st.error("Could not read the video.")
        st.stop()

    left, right = st.columns([2, 1])
    with right:
        st.subheader("Counting line")
        orientation = st.radio("Orientation", ["Horizontal", "Vertical"], horizontal=True)
        pos_pct = st.slider("Position (%)", 5, 95, 60)
        max_frames = st.number_input("Max frames (0 = all)", min_value=0, value=300, step=100)
        stride = st.number_input("Process every Nth frame", min_value=1, max_value=10, value=1,
                                 help="Higher is faster, but tracking is less reliable.")
        run = st.button("Run", type="primary")
    with left:
        p1, p2, _ = line_endpoints(orientation, pos_pct, vw, vh)
        prev = first.copy()
        cv2.line(prev, p1, p2, (0, 255, 255), 4)
        st.image(prev[:, :, ::-1], caption="First frame with counting line", use_container_width=True)

    if run:
        old = st.session_state.get("video_result")
        if old:
            safe_delete(old["path"])  # replace the last annotated video, don't pile them up
            st.session_state["video_result"] = None
        st.session_state["video_result"] = process_video(path, int(stride), int(max_frames), orientation, pos_pct)

res = st.session_state.get("video_result")
if res:
    st.success(f"{res['frames']} frames in {res['frames'] / max(res['fps'], 1e-6):.1f}s "
               f"({res['fps']:.1f} FPS overall, {res['infer_ms']:.1f} ms/frame model time)")
    vcol, tcol = st.columns([3, 1])
    with vcol:
        if res["playable"]:
            st.video(res["path"])
        else:
            st.info("ffmpeg not found on PATH, so inline playback is unavailable. Download the file instead.")
        with open(res["path"], "rb") as fh:
            st.download_button("Download annotated video", fh, file_name="annotated.mp4", mime="video/mp4")
    with tcol:
        st.subheader("Unique tracks")
        st.dataframe(pd.DataFrame({"class": list(res["unique"]), "tracks": list(res["unique"].values())})
                     .sort_values("class"), hide_index=True)

        st.subheader("Line crossings")
        ev = pd.DataFrame(res["events"], columns=["t", "id", "class", "direction"])
        if ev.empty:
            st.info("No crossings. Move the line or lower the confidence.")
        else:
            st.dataframe(ev.pivot_table(index="class", columns="direction", values="id",
                                        aggfunc="count", fill_value=0), use_container_width=True)

    st.subheader("Export counts")
    e1, e2, e3 = st.columns(3)
    bucket_s = e1.number_input("Bucket size (seconds)", min_value=1, value=10)
    d = e2.date_input("Video start date", value=date.today())
    t = e3.time_input("Video start time", value=datetime.now().replace(second=0, microsecond=0).time())
    st.download_button("Download counts CSV", counts_csv(res, int(bucket_s), datetime.combine(d, t)),
                       file_name="vehicle_counts.csv", mime="text/csv")