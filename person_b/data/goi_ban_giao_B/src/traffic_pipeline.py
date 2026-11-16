"""Pipeline giám sát giao thông: YOLOv8 + ByteTrack + đếm xe + cảnh báo đi ngược hướng làn."""
import csv
import datetime
import os
from collections import Counter, defaultdict, deque

import cv2
import numpy as np

TRACKER_YAML_TEXT = """tracker_type: bytetrack
track_high_thresh: 0.30
track_low_thresh: 0.10
new_track_thresh: 0.35
track_buffer: 45
match_thresh: 0.8
fuse_score: True
"""

DEFAULT_CFG = dict(
    imgsz=960, stride=2, yolo_conf=0.20, yolo_iou=0.5,
    min_conf=[0.30, 0.30, 0.55, 0.45],              # xe_hoi, xe_may, xe_tai, bus
    count_line_y=600, min_age=3, asp_fix=1.45,
    line_pts=[(80, 955), (1280, 410), (1600, 250), (1919, 80)],
    win_s=1.0, persist_s=0.6, ang_thr=165, ang_cont=135, neutral_max=40,
    min_move_frac=0.15, min_move_px=15, min_consist=0.70, jump_frac=0.5,
    wrongway_enabled=True, margin_frac=0.12, margin_min=10, check_left=False,
    min_h=75, wh_max=1.35, far_y=225,
)
COLORS = {"xe_hoi": (255, 100, 0), "xe_may": (0, 255, 255), "xe_tai": (0, 0, 255), "bus": (0, 255, 0)}
NEUTRAL = {"sat_vach", "bo_qua", "nhay_id", "rung_nhieu"}
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _build_line(pts):
    p = [np.array(q, float) for q in pts]
    if p[0][0] > 0:
        d = p[1] - p[0]
        p.insert(0, p[0] - d * (p[0][0] / d[0]))
    if p[-1][0] < 1919:
        d = p[-1] - p[-2]
        p.append(p[-1] + d * ((1919 - p[-1][0]) / d[0]))
    return np.array(p)


class TrafficPipeline:
    def __init__(self, model_path, cfg=None, clock0="2026-04-09 13:41:50", tracker_yaml="bytetrack_v1.yaml", model=None):
        self.cfg = dict(DEFAULT_CFG)
        if cfg:
            self.cfg.update(cfg)
        self.model_path = model_path
        self.device = None
        self.model = model
        self.clock0 = datetime.datetime.strptime(clock0, "%Y-%m-%d %H:%M:%S")
        self.tracker_yaml = tracker_yaml
        with open(tracker_yaml, "w") as f:
            f.write(TRACKER_YAML_TEXT)
        line = _build_line(self.cfg["line_pts"])
        self.line_poly = line.astype(np.int32).reshape(-1, 1, 2)
        self.segs = []
        for a, b in zip(line[:-1], line[1:]):
            L = float(np.linalg.norm(b - a))
            self.segs.append((a, (b - a) / L, L))
        self._setup_fps(30.0)
        self._reset_state()

    # ---------- thiết lập ----------
    def _setup_fps(self, fps_in):
        c = self.cfg
        self.fps_in = fps_in
        self.fps_eff = fps_in / c["stride"]
        self.Wn = max(6, int(c["win_s"] * self.fps_eff))
        self.persist = max(3, int(c["persist_s"] * self.fps_eff))

    def _reset_state(self):
        import torch
        from ultralytics import YOLO

        self.device = self.cfg.get("device") or ("cuda:0" if torch.cuda.is_available() else "cpu")
        if self.model is None:
            self.model = YOLO(self.model_path)
        # Keep detector weights warm, but never carry identities between videos.
        predictor = getattr(self.model, 'predictor', None)
        for tracker in getattr(predictor, 'trackers', []):
            tracker.reset()
        self.names = self.model.names
        self.votes = defaultdict(Counter)
        self.age = defaultdict(int)
        self.asp = defaultdict(lambda: deque(maxlen=40))
        self.prev_by, self.counted, self.tr, self.red = {}, set(), {}, {}
        self.counts = {"toward": Counter(), "away": Counter()}
        self.alerts, self.suppressed, self.events = [], [], []

    def clock(self, frame_idx):
        return (self.clock0 + datetime.timedelta(seconds=frame_idx / self.fps_in)).strftime("%Y-%m-%d %H:%M:%S")

    # ---------- hình học làn ----------
    def _line_geom(self, P):
        best = None
        for a, t, L in self.segs:
            s = float(np.clip((P - a) @ t, 0, L))
            dd = float(np.linalg.norm(P - (a + s * t)))
            if best is None or dd < best[0]:
                best = (dd, a, t)
        dd, a, t = best
        sgn = t[0] * (P[1] - a[1]) - t[1] * (P[0] - a[0])
        return (dd if sgn > 0 else -dd), t        # dương: làn phải (ra xa); âm: làn trái (về camera)

    # ---------- đánh giá một cửa sổ chuyển động ----------
    def _evaluate(self, T):
        c = self.cfg
        S = np.array(T["sm"], float)              # cột: frame, x, y, h, edge
        F, P, Hh, E = S[:, 0], S[:, 1:3], S[:, 3], S[:, 4]
        i, j = len(S) - 1, 0
        h = max(Hh[i], 1.0)
        if F[i] - F[j] > 1.5 * self.Wn * c["stride"] or E.any():
            return "bo_qua", None, None
        d = P[i] - P[j]
        n = float(np.linalg.norm(d))
        if np.linalg.norm(np.diff(P, axis=0), axis=1).max() > c["jump_frac"] * h:
            return "nhay_id", None, None
        if n < max(c["min_move_px"], c["min_move_frac"] * h):
            return "dung_yen", None, None
        sd = np.diff(P[::2], axis=0)
        if (float(np.mean(sd @ d > 0)) if len(sd) else 0.0) < c["min_consist"]:
            return "rung_nhieu", None, None
        dist, t = self._line_geom(P[i])
        dist_j, _ = self._line_geom(P[j])
        margin = max(c["margin_min"], c["margin_frac"] * h)
        if abs(dist) < margin or abs(dist_j) < margin or np.sign(dist) != np.sign(dist_j):
            return "sat_vach", None, None
        if (not c["check_left"]) and dist < 0:
            return "bo_lan_trai", None, None
        e = t if dist > 0 else -t
        ang = float(np.degrees(np.arccos(np.clip(d @ e / n, -1, 1))))
        return "xet", dist, ang

    def _update_wrongway(self, tid, g, cname, T):
        c = self.cfg
        if T["done"] or len(T["sm"]) < self.Wn + 1:
            return None
        st, dist, ang = self._evaluate(T)
        if st == "xet":
            if ang > c["ang_thr"] or (T["run"] > 0 and ang > c["ang_cont"]):
                if T["run"] == 0:
                    T["k0_frame"], T["a0"] = int(T["sm"][-1][0]), ang
                T["run"] += 1
                T["neutral"] = 0
                T["last"] = (ang, dist)
            else:
                T["run"], T["neutral"] = 0, 0
        elif st in NEUTRAL:
            if T["run"] > 0:
                T["neutral"] += 1
                if T["neutral"] > c["neutral_max"]:
                    T["run"], T["neutral"] = 0, 0
        else:
            T["run"], T["neutral"] = 0, 0
        if T["run"] < self.persist:
            return None
        T["done"] = True
        h = float(np.median([x[0] for x in T["hw"]]))
        wh = float(np.median([x[1] for x in T["hw"]]))
        S = np.array(T["sm"], float)
        ang_l, dist_l = T["last"]
        reason = "nho" if h < c["min_h"] else ("ngang" if wh > c["wh_max"] else "")
        alert = dict(frame=g, time_s=round(g / self.fps_in, 2), gio_canh_bao=self.clock(g).split(" ")[1],
                     gio_bat_dau=self.clock(T["k0_frame"]).split(" ")[1], timestamp=self.clock(g),
                     track_id=tid, loai=cname, goc=round(ang_l), cach_vach_px=round(dist_l),
                     x=int(S[-1, 1]), y=int(S[-1, 2]), cao_px=int(h), wh=round(wh, 2),
                     vung="xa" if S[-1, 2] < c["far_y"] else "gan", bi_loai=reason)
        if reason:
            self.suppressed.append(alert)
            return None
        self.red[tid] = g
        self.alerts.append(alert)
        return alert

    # ---------- xử lý một khung hình ----------
    def process_frame(self, frame, g, annotate=True):
        c = self.cfg
        frame_height, frame_width = frame.shape[:2]
        inference_size = c.get("inference_size", (frame_width, frame_height))
        inference_frame = frame
        if inference_size != (frame_width, frame_height):
            inference_frame = cv2.resize(frame, inference_size, interpolation=cv2.INTER_AREA)
        res = self.model.track(inference_frame, imgsz=c["imgsz"], conf=c["yolo_conf"], iou=c["yolo_iou"],
                               persist=True, tracker=self.tracker_yaml, verbose=False,
                               device=self.device,
                               quantize=16 if self.device != "cpu" and c.get("half", False) else None)[0]
        rows, new_events, new_alerts = [], [], []
        b = res.boxes
        if b is not None and len(b) > 0 and b.id is not None:
            # Results are already tracked: copy coordinates, ID, confidence and
            # class together to avoid four separate GPU-to-CPU transfers.
            detections = b.data.cpu().numpy()
            xyxy = detections[:, :4]
            if inference_frame is not frame:
                scale_x = frame_width / inference_size[0]
                scale_y = frame_height / inference_size[1]
                xyxy = xyxy * (scale_x, scale_y, scale_x, scale_y)
            ids = detections[:, -3].astype(int)
            conf = detections[:, -2]
            cls = detections[:, -1].astype(int)
            mc = np.array(c["min_conf"])
            for k in np.where(conf >= mc[cls])[0]:
                tid = int(ids[k])
                x1, y1, x2, y2 = [float(v) for v in xyxy[k]]
                w, h = x2 - x1, max(y2 - y1, 1.0)
                self.votes[tid][int(cls[k])] += float(conf[k])
                cname = self.names[self.votes[tid].most_common(1)[0][0]]
                if not (x1 <= 5 or x2 >= frame_width - 6 or y1 <= 5 or y2 >= frame_height - 5):
                    self.asp[tid].append(h / max(w, 1.0))
                if cname in ("xe_tai", "bus") and len(self.asp[tid]) >= 3 and np.median(self.asp[tid]) > c["asp_fix"]:
                    cname = "xe_may"                       # xe máy chở 2 người bị nhầm là xe tải
                self.age[tid] += 1
                by = y2
                # --- đếm qua vạch ---
                if tid in self.prev_by and tid not in self.counted and self.age[tid] >= c["min_age"]:
                    py, L = self.prev_by[tid], c["count_line_y"]
                    direction = "toward" if py < L <= by else ("away" if py >= L > by else None)
                    if direction:
                        self.counted.add(tid)
                        self.counts[direction][cname] += 1
                        ev = dict(frame=g, time_s=round(g / self.fps_in, 2), timestamp=self.clock(g),
                                  track_id=tid, loai=cname, nhom="xe_lon" if cname in ("xe_tai", "bus") else cname,
                                  huong=direction)
                        self.events.append(ev)
                        new_events.append(ev)
                self.prev_by[tid] = by
                # --- cảnh báo ngược chiều ---
                if c["wrongway_enabled"]:
                    T = self.tr.get(tid)
                    if T is None:
                        T = dict(raw=deque(maxlen=7), sm=deque(maxlen=self.Wn + 1), hw=deque(maxlen=10),
                                 run=0, neutral=0, last=None, a0=None, k0_frame=None, done=False)
                        self.tr[tid] = T
                    edge_y = 1.0 if (y1 <= 5 or y2 >= 1075) else 0.0
                    T["raw"].append((g, (x1 + x2) / 2, by, h, edge_y))
                    T["hw"].append((h, w / h))
                    if len(T["raw"]) == 7:                     # làm mượt bằng trung vị 7 khung, chốt phần tử giữa
                        R = np.array(T["raw"], float)
                        T["sm"].append((R[3, 0], np.median(R[:, 1]), np.median(R[:, 2]), np.median(R[:, 3]), R[3, 4]))
                        al = self._update_wrongway(tid, g, cname, T)
                        if al:
                            new_alerts.append(al)
                rows.append(dict(frame=g, time_s=round(g / self.fps_in, 3), timestamp=self.clock(g), track_id=tid,
                                 loai=cname, conf=round(float(conf[k]), 3),
                                 x1=int(x1), y1=int(y1), x2=int(x2), y2=int(y2)))
        out = dict(frame_idx=g, time_s=g / self.fps_in, timestamp=self.clock(g), tracks=rows,
                   new_events=new_events, new_alerts=new_alerts,
                   counts={d: dict(v) for d, v in self.counts.items()})
        if annotate:
            out["annotated"] = self._annotate(frame, rows)
        return out

    def _annotate(self, frame, rows):
        img = frame.copy()
        any_red = False
        for r in rows:
            red = r["track_id"] in self.red
            col = (0, 0, 255) if red else COLORS.get(r["loai"], (200, 200, 200))
            cv2.rectangle(img, (r["x1"], r["y1"]), (r["x2"], r["y2"]), col, 5 if red else 2)
            label = f"#{r['track_id']} {r['loai']}" + (" NGUOC CHIEU" if red else "")
            cv2.putText(img, label, (r["x1"], max(25, r["y1"] - 8)), FONT, 0.9 if red else 0.6, col, 2)
            any_red = any_red or red
        W = img.shape[1]
        cv2.line(img, (0, self.cfg["count_line_y"]), (W - 1, self.cfg["count_line_y"]), (255, 0, 0), 3)
        if self.cfg["wrongway_enabled"]:
            cv2.polylines(img, [self.line_poly], False, (0, 255, 255), 2)
        y0 = 50
        directions = (("toward", "VE CAMERA"), ("away", "RA XA")) if self.cfg["wrongway_enabled"] else (("toward", "XUONG KHUNG"), ("away", "LEN KHUNG"))
        for key, title in directions:
            txt = f"{title}: " + " ".join(f"{n}={self.counts[key][n]}" for n in self.names.values())
            cv2.putText(img, txt, (30, y0), FONT, 1.0, (0, 255, 255), 3)
            y0 += 45
        if any_red:
            cv2.putText(img, "CANH BAO: XE DI NGUOC CHIEU", (30, y0 + 30), FONT, 1.5, (0, 0, 255), 4)
        return img

    # ---------- chạy trên video hoặc luồng camera (generator) ----------
    def run(self, source, max_frames=None, annotate=True):
        cap = cv2.VideoCapture(source)
        try:
            self._setup_fps(cap.get(cv2.CAP_PROP_FPS) or 30.0)
            self._reset_state()
            g, n = -1, 0
            while True:
                if not cap.grab():
                    break
                g += 1
                if g % self.cfg["stride"]:
                    continue
                ok, frame = cap.retrieve()
                if not ok:
                    break
                yield self.process_frame(frame, g, annotate)
                n += 1
                if max_frames and n >= max_frames:
                    break
        finally:
            cap.release()


def run_to_files(pipe, source, out_dir, save_video=True, out_w=1280, report_every=1000):
    """Chạy và ghi: tracking_log.csv, count_events.csv, wrongway_alerts.csv, video chú thích (.mp4)."""
    import time
    os.makedirs(out_dir, exist_ok=True)
    writer, n, t0 = None, 0, time.time()
    f_log = open(os.path.join(out_dir, "tracking_log.csv"), "w", newline="", encoding="utf-8")
    wl = csv.writer(f_log)
    wl.writerow(["frame", "time_s", "timestamp", "track_id", "class", "conf", "x1", "y1", "x2", "y2"])
    for out in pipe.run(source, annotate=save_video):
        for r in out["tracks"]:
            wl.writerow([r["frame"], r["time_s"], r["timestamp"], r["track_id"], r["loai"], r["conf"],
                         r["x1"], r["y1"], r["x2"], r["y2"]])
        if save_video:
            im = out["annotated"]
            if writer is None:
                oh = int(im.shape[0] * out_w / im.shape[1])
                writer = cv2.VideoWriter(os.path.join(out_dir, "annotated_raw.mp4"),
                                         cv2.VideoWriter_fourcc(*"mp4v"), pipe.fps_eff, (out_w, oh))
            writer.write(cv2.resize(im, (out_w, int(im.shape[0] * out_w / im.shape[1]))))
        n += 1
        if report_every and n % report_every == 0:
            print(f"  {n} khung | {n / (time.time() - t0):.1f} FPS | {sum(sum(v.values()) for v in pipe.counts.values())} xe qua vạch | {len(pipe.alerts)} cảnh báo")
    f_log.close()
    if writer:
        writer.release()
    for name, data, cols in (("count_events.csv", pipe.events, ["frame", "time_s", "timestamp", "track_id", "loai", "nhom", "huong"]),
                             ("wrongway_alerts.csv", pipe.alerts, list(pipe.alerts[0].keys()) if pipe.alerts else ["frame"]),
                             ("wrongway_suppressed.csv", pipe.suppressed, list(pipe.suppressed[0].keys()) if pipe.suppressed else ["frame"])):
        with open(os.path.join(out_dir, name), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(data)
    print(f"Xong {n} khung trong {time.time() - t0:.0f}s ({n / (time.time() - t0):.1f} FPS)")
    return n
