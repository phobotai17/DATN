"""
generate_mock.py
Sinh dữ liệu giả lập (Mock Time-Series Data) lưu lượng xe trong 24 giờ,
mỗi nấc 5 phút, có biến thiên theo giờ cao điểm (7-9h sáng, 17-19h chiều).

Chạy từ thư mục gốc của repo:
    python scripts/generate_mock.py
Kết quả: data/mock_traffic_data.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42  # cố định seed để kết quả tái lập được
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "mock_traffic_data.csv"


def generate_mock_data() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)

    timestamps = pd.date_range(
        start="2026-09-01 00:00", end="2026-09-01 23:55", freq="5min"
    )

    rows = []
    for ts in timestamps:
        hour = ts.hour

        # Giả lập giờ cao điểm (7-9h sáng và 17-19h chiều)
        is_peak = (7 <= hour <= 9) or (17 <= hour <= 19)
        base_multiplier = 3.5 if is_peak else 1.0

        motorbike = int(rng.normal(loc=120 * base_multiplier, scale=15))
        car = int(rng.normal(loc=40 * base_multiplier, scale=5))
        truck = int(rng.normal(loc=10, scale=3))
        bus = int(rng.normal(loc=5, scale=2))

        # Không cho phép giá trị âm
        motorbike, car, truck, bus = (max(0, v) for v in (motorbike, car, truck, bus))

        rows.append(
            {
                "timestamp": ts,
                "motorbike": motorbike,
                "car": car,
                "truck": truck,
                "bus": bus,
                "total_vehicles": motorbike + car + truck + bus,
            }
        )

    return pd.DataFrame(rows)


def main() -> None:
    df = generate_mock_data()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Đã lưu {len(df)} dòng vào {OUTPUT_PATH}")
    print(df.head())
    print(df.describe())


if __name__ == "__main__":
    main()
