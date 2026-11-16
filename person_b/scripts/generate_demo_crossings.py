"""Generate a reproducible five-minute sample of line-crossing events."""
import csv
from datetime import datetime, timedelta
from pathlib import Path
from random import Random

ROOT = Path(__file__).resolve().parents[1]
START = datetime(2026, 11, 11, 8, 0)


def main():
    rng = Random(42)
    seconds = sorted(rng.sample(range(300), 185))
    with (ROOT / 'data/demo_crossings_5min.csv').open('w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['timestamp', 'track_id', 'class_name', 'direction'])
        for track_id, offset in enumerate(seconds, 1):
            vehicle = rng.choices(['motorbike', 'car', 'truck', 'bus'], [74, 20, 4, 2])[0]
            direction = rng.choices(['toward', 'away'], [55, 45])[0]
            writer.writerow([(START + timedelta(seconds=offset)).isoformat(sep=' '), track_id, vehicle, direction])


if __name__ == '__main__':
    main()
