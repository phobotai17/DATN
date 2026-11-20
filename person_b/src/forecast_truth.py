"""Independent counts indexed by source-video second and camera zone."""
import csv


def read_count_labels(lines):
    reader = csv.DictReader(lines)
    if not {"second", "zone", "total"}.issubset(reader.fieldnames or []):
        raise ValueError("Expected CSV columns second,zone,total.")
    counts = {}
    for row in reader:
        second, total = int(row["second"] or ""), int(row["total"] or "")
        zone = (row["zone"] or "").strip()
        key = (second, zone)
        if second < 0 or total < 0 or not zone or key in counts:
            raise ValueError("Expected unique, nonnegative counts by second and zone.")
        counts[key] = total
    if not counts:
        raise ValueError("The count CSV is empty.")
    return counts


def forecast_errors(forecast, counts):
    return [abs(predicted - counts[key])
            for zone, predicted in forecast["values"].items()
            if (key := (forecast["target"], zone)) in counts]
