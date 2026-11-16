"""
mock_tracking_log.py  (dùng để TEST, không phải bài nộp của Bạn A)

Sinh ra một log tracking giả lập đúng schema mà aggregate_tracking.py mong
đợi, để Bạn B kiểm thử module gom nhóm TRƯỚC KHI Bạn A có pipeline
ByteTrack/Supervision thật chạy. Khi Bạn A xuất CSV thật, chỉ cần trỏ
aggregate_tracking.py sang file đó - không cần sửa logic gì thêm.
"""
import numpy as np
import pandas as pd

VEHICLE_CLASSES = ["motorbike", "car", "truck", "bus"]
WEIGHTS = [0.65, 0.25, 0.05, 0.05]  # mô phỏng tỉ lệ xe máy áp đảo ở VN


def generate_mock_tracking_log(
    start="2026-09-01 07:00:00", minutes=20, fps=15, seed=42
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start_ts = pd.Timestamp(start)
    n_frames = minutes * 60 * fps

    rows = []
    track_id = 0
    active = []  # (track_id, class_name, frames_left)

    for frame_id in range(n_frames):
        ts = start_ts + pd.Timedelta(seconds=frame_id / fps)

        # Thỉnh thoảng có xe mới đi vào khung hình
        if rng.random() < 0.08:
            cls = rng.choice(VEHICLE_CLASSES, p=WEIGHTS)
            life = rng.integers(fps * 1, fps * 8)  # xe "sống" 1-8 giây trong khung hình
            active.append([track_id, cls, life])
            track_id += 1

        still_active = []
        for tid, cls, life in active:
            if life <= 0:
                continue
            rows.append(
                {
                    "frame_id": frame_id,
                    "timestamp": ts,
                    "track_id": tid,
                    "class_name": cls,
                    "x": rng.uniform(0, 1280),
                    "y": rng.uniform(0, 720),
                }
            )
            still_active.append([tid, cls, life - 1])
        active = still_active

    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = generate_mock_tracking_log()
    out = "data/mock_tracking_log.csv"
    df.to_csv(out, index=False)
    print(f"{len(df)} dòng detection, {df['track_id'].nunique()} xe duy nhất -> {out}")