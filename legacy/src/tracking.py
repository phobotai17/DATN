"""
aggregate_tracking.py  (Member B, Week 2)

Nhận luồng Tracking (ByteTrack/DeepSORT qua Supervision) của Thành viên A -
mỗi dòng là MỘT lần nhìn thấy một xe ở MỘT khung hình (frame) - và gom
thành time-series: tổng số xe theo từng khung thời gian (1 phút / 5 phút...).

ĐIỂM MẤU CHỐT của việc "đếm xe" (không phải chỉ cộng dòng):
Một xe xuất hiện trên hàng chục/hàng trăm frame liên tiếp với CÙNG track_id.
Nếu chỉ đếm số dòng, một xe đứng chờ đèn đỏ lâu sẽ bị đếm nhiều lần.
=> Trong mỗi khung thời gian, ta đếm SỐ track_id DUY NHẤT theo từng lớp xe,
   không đếm số dòng (số lần xuất hiện).

----------------------------------------------------------------------
Schema đầu vào mong đợi từ Thành viên A (1 dòng = 1 lần thấy xe ở 1 frame):
    frame_id    : int           - số thứ tự khung hình
    timestamp   : datetime-like - thời điểm của frame (vd "2026-09-01 07:03:12")
    track_id    : int           - ID duy nhất Supervision/ByteTrack gán cho xe
    class_name  : str           - 'motorbike' | 'car' | 'truck' | 'bus'
    x, y        : float         - toạ độ tâm bounding box (không bắt buộc cho
                                   bước gom nhóm này, nhưng nên lưu sẵn vì
                                   Tuần 3 cần để tính vector quỹ đạo)

Có thể đọc từ CSV (Bạn A xuất ra) hoặc từ DataFrame (nếu chạy chung pipeline).
----------------------------------------------------------------------

Cách dùng CLI:
    python scripts/aggregate_tracking.py --input tracking_log.csv \
        --window 5 --output data/aggregated_traffic.csv

Cách dùng như module (khi Bạn A đã có pipeline sống, không qua file CSV):
    from scripts.aggregate_tracking import aggregate_tracking_log
    df_timeseries = aggregate_tracking_log(df_tracking_log, window_minutes=5)
"""
import argparse
from pathlib import Path

import pandas as pd

# Phải khớp với 4 lớp trong Mục tiêu đề tài (motorbike, car, truck, bus)
VEHICLE_CLASSES = ["motorbike", "car", "truck", "bus"]

REQUIRED_COLUMNS = {"frame_id", "timestamp", "track_id", "class_name"}


def validate_log(df: pd.DataFrame) -> None:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"Thiếu cột trong tracking log: {missing}. "
            f"Cần các cột: {sorted(REQUIRED_COLUMNS)}"
        )
    unknown = set(df["class_name"].unique()) - set(VEHICLE_CLASSES)
    if unknown:
        print(f"[CẢNH BÁO] class_name lạ, sẽ bị bỏ qua khi gom nhóm: {unknown}")


def aggregate_tracking_log(df: pd.DataFrame, window_minutes: int = 5) -> pd.DataFrame:
    """
    Gom log tracking (per-frame, per-detection) thành time-series:
    mỗi dòng kết quả = 1 khung thời gian, các cột = số XE DUY NHẤT mỗi lớp.

    Logic:
      1. Gán mỗi dòng vào một "bucket" thời gian (floor timestamp theo window).
      2. Trong mỗi (bucket, class_name), lấy tập hợp track_id duy nhất
         rồi đếm kích thước tập hợp đó -> tránh đếm trùng 1 xe nhiều lần.
      3. Pivot ra dạng rộng: mỗi lớp xe thành 1 cột, giống schema mock data
         để cắm thẳng vào Dashboard / mô hình dự báo hiện có.
    """
    validate_log(df)

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df[df["class_name"].isin(VEHICLE_CLASSES)]

    df["time_bucket"] = df["timestamp"].dt.floor(f"{window_minutes}min")

    # Đếm track_id duy nhất mỗi (time_bucket, class_name)
    unique_counts = (
        df.groupby(["time_bucket", "class_name"])["track_id"]
        .nunique()
        .reset_index(name="count")
    )

    wide = unique_counts.pivot(index="time_bucket", columns="class_name", values="count")
    wide = wide.reindex(columns=VEHICLE_CLASSES, fill_value=0).fillna(0).astype(int)
    wide = wide.reset_index().rename(columns={"time_bucket": "timestamp"})

    # Đảm bảo đủ mọi khung thời gian trong khoảng (kể cả khung = 0 xe),
    # nếu không mô hình dự báo Tuần 3 sẽ bị lệch chuỗi thời gian.
    full_range = pd.date_range(
        wide["timestamp"].min(), wide["timestamp"].max(), freq=f"{window_minutes}min"
    )
    wide = (
        wide.set_index("timestamp")
        .reindex(full_range, fill_value=0)
        .rename_axis("timestamp")
        .reset_index()
    )

    wide["total_vehicles"] = wide[VEHICLE_CLASSES].sum(axis=1)
    return wide


def main() -> None:
    ap = argparse.ArgumentParser(description="Gom log tracking thành time-series đếm xe")
    ap.add_argument("--input", required=True, type=Path, help="CSV log tracking từ Bạn A")
    ap.add_argument("--window", type=int, default=5, help="Độ rộng khung thời gian (phút)")
    ap.add_argument("--output", type=Path, default=Path("data/aggregated_traffic.csv"))
    args = ap.parse_args()

    log_df = pd.read_csv(args.input)
    result = aggregate_tracking_log(log_df, window_minutes=args.window)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(f"Đã gom {len(log_df)} dòng log -> {len(result)} khung thời gian")
    print(f"Lưu vào {args.output}")
    print(result.head())


if __name__ == "__main__":
    main()