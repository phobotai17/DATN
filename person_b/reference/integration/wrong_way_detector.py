"""
wrong_way_detector.py
=====================
Module phát hiện phương tiện đi sai hướng/ngược chiều (Member A, Week 3 - FR4).
Nguyên lý:
  - Mỗi xe có quỹ đạo các điểm tâm P_i(t) = (x_t, y_t).
  - Tính vector chuyển động v_i = P_i(t) - P_i(t - k) trên cửa sổ k khung hình.
  - So sánh với vector chuẩn của làn đường u = (ux, uy).
  - Góc lệch θ = arccos((v_i . u) / (||v_i|| * ||u||)).
  - Bật cảnh báo (Alert) nếu θ > θ_max (ví dụ: > 90° hoặc > 120°) trong N khung liên tiếp
    và độ dịch chuyển ||v_i|| vượt ngưỡng tối thiểu (loại trừ xe đứng yên / nhiễu).
"""

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np


@dataclass
class WrongWayAlert:
    track_id: int
    class_name: str
    frame_id: int
    timestamp: str
    angle_deg: float
    center: Tuple[float, float]
    speed_px: float


class WrongWayDetector:
    def __init__(
        self,
        ref_vector: Tuple[float, float] = (0.0, 1.0),  # Hướng chuẩn (ví dụ: xe đi xuống theo trục Y)
        angle_threshold_deg: float = 110.0,             # Ngưỡng góc (độ) để coi là ngược chiều
        min_displacement_px: float = 25.0,             # Quãng đường tối thiểu để tránh nhiễu rung lắc
        window_k: int = 8,                              # Số khung hình tính vector vận tốc
        consecutive_frames_n: int = 5,                 # Số khung liên tiếp vượt ngưỡng để kích hoạt alert
    ):
        self.u = np.array(ref_vector, dtype=np.float32)
        norm_u = np.linalg.norm(self.u)
        if norm_u > 0:
            self.u /= norm_u
        else:
            self.u = np.array([0.0, 1.0], dtype=np.float32)

        self.angle_threshold_deg = angle_threshold_deg
        self.min_displacement_px = min_displacement_px
        self.window_k = window_k
        self.consecutive_frames_n = consecutive_frames_n

        # Lưu lịch sử tọa độ theo track_id: track_id -> deque of (x, y, frame_id, ts)
        self.history: Dict[int, deque] = defaultdict(lambda: deque(maxlen=window_k * 3))
        # Đếm số khung liên tiếp vi phạm: track_id -> int
        self.violation_counts: Dict[int, int] = defaultdict(int)
        # Ghi nhận các xe đã bị alert để tránh spam: track_id -> bool
        self.alerted_ids: set[int] = set()

    def update(
        self,
        track_id: int,
        class_name: str,
        x: float,
        y: float,
        frame_id: int,
        timestamp: str = "",
    ) -> Optional[WrongWayAlert]:
        """
        Cập nhật vị trí của xe trong khung hình.
        Nếu phát hiện đi ngược chiều đạt ngưỡng, trả về đối tượng WrongWayAlert.
        """
        track_hist = self.history[track_id]
        track_hist.append((x, y, frame_id, timestamp))

        if len(track_hist) < self.window_k:
            return None

        # Lấy điểm hiện tại và điểm cách đây k bước
        curr_x, curr_y, _, _ = track_hist[-1]
        past_x, past_y, _, _ = track_hist[-self.window_k]

        v = np.array([curr_x - past_x, curr_y - past_y], dtype=np.float32)
        dist = float(np.linalg.norm(v))

        # Nếu xe đứng yên hoặc di chuyển quá ít, bỏ qua
        if dist < self.min_displacement_px:
            self.violation_counts[track_id] = 0
            return None

        v_unit = v / dist
        # Tính cos góc giữa v và u
        cos_theta = float(np.clip(np.dot(v_unit, self.u), -1.0, 1.0))
        angle_rad = np.arccos(cos_theta)
        angle_deg = float(np.degrees(angle_rad))

        if angle_deg >= self.angle_threshold_deg:
            self.violation_counts[track_id] += 1
        else:
            self.violation_counts[track_id] = max(0, self.violation_counts[track_id] - 1)

        # Kiểm tra điều kiện kích hoạt cảnh báo
        if (
            self.violation_counts[track_id] >= self.consecutive_frames_n
            and track_id not in self.alerted_ids
        ):
            self.alerted_ids.add(track_id)
            return WrongWayAlert(
                track_id=track_id,
                class_name=class_name,
                frame_id=frame_id,
                timestamp=timestamp,
                angle_deg=round(angle_deg, 1),
                center=(round(curr_x, 1), round(curr_y, 1)),
                speed_px=round(dist, 1),
            )

        return None

    def reset_track(self, track_id: int):
        self.history.pop(track_id, None)
        self.violation_counts.pop(track_id, None)
        self.alerted_ids.discard(track_id)
