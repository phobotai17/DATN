"""
video_tracker.py
================
Module theo dõi đa đối tượng (Multi-Object Tracking - Member A, Week 2).
Hỗ trợ ByteTrack và DeepSORT, trích xuất tọa độ tâm quỹ đạo và xuất ra
tracking log chuẩn (frame_id, timestamp, track_id, class_name, x, y, conf)
để cắm thẳng vào module gom nhóm time-series (Member B).
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator, Optional, Tuple, Dict, Any

import cv2
import numpy as np
import pandas as pd
from ultralytics import YOLO

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WEIGHTS = Path(__file__).resolve().parents[1] / "person_b/data/goi_ban_giao_B/models/best_v2.pt"
VEHICLE_CLASSES = ["motorbike", "car", "truck", "bus"]


class VideoVehicleTracker:
    def __init__(
        self,
        weights_path: str = str(DEFAULT_WEIGHTS),
        tracker_type: str = "bytetrack",  # 'bytetrack' or 'botsort' (or custom deepsort)
        conf: float = 0.3,
        iou: float = 0.7,
        imgsz: int = 640,
        device: str = "0",
    ):
        self.weights_path = weights_path
        self.tracker_type = tracker_type
        self.conf = conf
        self.iou = iou
        self.imgsz = imgsz
        self.device = 0 if device == "0" else device
        self.model = YOLO(self.weights_path)
        self.names = self.model.names

        # Config file for ultralytics tracker
        if self.tracker_type.lower() == "bytetrack":
            self.tracker_cfg = "bytetrack.yaml"
        elif self.tracker_type.lower() in ["deepsort", "botsort"]:
            self.tracker_cfg = "botsort.yaml"
        else:
            self.tracker_cfg = "bytetrack.yaml"

    def process_video(
        self,
        video_path: str,
        start_time: Optional[datetime] = None,
        stride: int = 1,
        max_frames: int = 0,
        output_video_path: Optional[str] = None,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Xử lý video, trả về:
          1. DataFrame tracking log với các cột:
             [frame_id, timestamp, track_id, class_name, x, y, w, h, conf]
          2. Thống kê meta (tổng số frames, số track id duy nhất, FPS trung bình)
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise FileNotFoundError(f"Không thể mở video tại {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if start_time is None:
            start_time = datetime.now()

        writer = None
        if output_video_path:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(output_video_path, fourcc, fps / stride, (width, height))

        records = []
        frame_idx = 0
        processed_count = 0

        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % stride == 0:
                    current_ts = start_time + timedelta(seconds=frame_idx / fps)

                    # Chạy tracking qua Ultralytics
                    results = self.model.track(
                        frame,
                        persist=True,
                        tracker=self.tracker_cfg,
                        conf=self.conf,
                        iou=self.iou,
                        imgsz=self.imgsz,
                        device=self.device,
                        verbose=False,
                    )[0]

                    if results.boxes.id is not None:
                        track_ids = results.boxes.id.int().cpu().tolist()
                        cls_ids = results.boxes.cls.int().cpu().tolist()
                        confs = results.boxes.conf.cpu().tolist()
                        xywh = results.boxes.xywh.cpu().numpy()

                        for tid, cid, cf, (cx, cy, w, h) in zip(track_ids, cls_ids, confs, xywh):
                            cname = {"xe_may": "motorbike", "xe_hoi": "car", "xe_tai": "truck"}.get(self.names.get(cid), self.names.get(cid, str(cid)))
                            records.append({
                                "frame_id": frame_idx,
                                "timestamp": current_ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                                "track_id": tid,
                                "class_name": cname,
                                "x": round(float(cx), 2),
                                "y": round(float(cy), 2),
                                "w": round(float(w), 2),
                                "h": round(float(h), 2),
                                "conf": round(float(cf), 3),
                            })

                    if writer is not None:
                        annotated_frame = results.plot(labels=True, conf=True)
                        writer.write(annotated_frame)

                    processed_count += 1
                    if max_frames > 0 and processed_count >= max_frames:
                        break

                frame_idx += 1

        finally:
            cap.release()
            if writer is not None:
                writer.release()

        df_tracking = pd.DataFrame(records)
        unique_tracks = df_tracking["track_id"].nunique() if not df_tracking.empty else 0
        meta = {
            "processed_frames": processed_count,
            "total_video_frames": total_frames,
            "unique_tracks": unique_tracks,
            "video_fps": fps,
        }
        return df_tracking, meta


def main():
    parser = argparse.ArgumentParser(description="Chạy Multi-Object Tracking trích xuất log")
    parser.add_argument("--video", required=True, help="Đường dẫn file video đầu vào")
    parser.add_argument("--tracker", default="bytetrack", choices=["bytetrack", "botsort", "deepsort"])
    parser.add_argument("--weights", default=str(DEFAULT_WEIGHTS), help="File trọng số .pt")
    parser.add_argument("--stride", type=int, default=1, help="Xử lý mỗi n frames")
    parser.add_argument("--max-frames", type=int, default=0, help="Số khung hình tối đa (0 = toàn bộ)")
    parser.add_argument("--output-csv", default="data/tracking_log.csv", help="Đường dẫn lưu file tracking CSV")
    parser.add_argument("--output-video", default=None, help="Đường dẫn lưu video kết quả đã vẽ box & ID")
    parser.add_argument("--device", default="0", help="GPU id (0) hoặc cpu")
    args = parser.parse_args()

    tracker = VideoVehicleTracker(
        weights_path=args.weights,
        tracker_type=args.tracker,
        device=args.device,
    )
    print(f"Bắt đầu tracking ({args.tracker}) trên video: {args.video} ...")
    df_log, meta = tracker.process_video(
        video_path=args.video,
        stride=args.stride,
        max_frames=args.max_frames,
        output_video_path=args.output_video,
    )

    out_csv = Path(args.output_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df_log.to_csv(out_csv, index=False)
    print(f"Hoàn thành tracking!")
    print(f"- Số dòng log thu được: {len(df_log)}")
    print(f"- Số phương tiện duy nhất: {meta['unique_tracks']}")
    print(f"- File CSV lưu tại: {out_csv}")


if __name__ == "__main__":
    main()
