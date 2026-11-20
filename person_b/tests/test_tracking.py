"""Contract tests for the tracking-to-forecasting handoff."""
import unittest
from io import StringIO
import pandas as pd
from src.tracking import OUTPUT_COLUMNS, aggregate_tracking_log, normalize_counts


def log(rows):
    return pd.DataFrame(rows, columns=["frame_id", "timestamp", "track_id", "class_name"])


class TrackingTests(unittest.TestCase):
    def test_duplicate_frames_class_flicker_cross_bucket_and_empty_bucket(self):
        source = log([
            (0, "2026-09-01 07:00:00", 1, "car"),
            (1, "2026-09-01 07:00:01", 1, "motorbike"),
            (2, "2026-09-01 07:00:02", 1, "car"),
            (3, "2026-09-01 07:05:00", 1, "car"),
            (4, "2026-09-01 07:15:00", 2, "bus"),
        ])
        result = aggregate_tracking_log(pd.concat([source, source.iloc[[1]]]))
        self.assertEqual(result.columns.tolist(), OUTPUT_COLUMNS)
        self.assertEqual(result.total_vehicles.tolist(), [1, 1, 0, 1])
        self.assertEqual(result.car.tolist(), [1, 1, 0, 0])
        self.assertEqual(result.motorbike.sum(), 0)
        restored = normalize_counts(pd.read_csv(StringIO(result.to_csv(index=False))))
        pd.testing.assert_frame_equal(result, restored)

    def test_empty_log_has_schema(self):
        result = aggregate_tracking_log(log([]))
        self.assertTrue(result.empty)
        self.assertEqual(result.columns.tolist(), OUTPUT_COLUMNS)

    def test_reject_invalid_tracking_input(self):
        for row in [(0, "bad-date", 1, "car"), (0, "2026-09-01", 1, "Car"),
                    (0, "2026-09-01", None, "car"), (0, "2026-09-01", -1, "car"),
                    (0, "2026-09-01", 1.5, "car")]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                aggregate_tracking_log(log([row]))
        with self.assertRaises(ValueError):
            aggregate_tracking_log(pd.DataFrame())
        with self.assertRaises(ValueError):
            aggregate_tracking_log(log([]), window_minutes=0)

    def test_conflicting_predictions_for_same_frame_fail(self):
        with self.assertRaises(ValueError):
            aggregate_tracking_log(log([(0, "2026-09-01", 1, "car"), (0, "2026-09-01", 1, "bus")]))

    def test_counts_alias_and_sorting(self):
        source = pd.DataFrame({"timestamp": ["2026-09-01 07:05", "2026-09-01 07:00"],
                               "motorbike": [2, 1], "car": [0, 1], "truck": [0, 0],
                               "bus": [0, 0], "total": [2, 2]})
        result = normalize_counts(source)
        self.assertEqual(result.columns.tolist(), OUTPUT_COLUMNS)
        self.assertEqual(result.motorbike.tolist(), [1, 2])
        self.assertIn("total", source)

    def test_reject_wrong_total_gaps_negative_counts_duplicates_and_misalignment(self):
        source = pd.DataFrame({"timestamp": ["2026-09-01 07:00", "2026-09-01 07:05"],
                               "motorbike": [1, 1], "car": [0, 0], "truck": [0, 0],
                               "bus": [0, 0], "total_vehicles": [1, 1]})
        for column, value in [("total_vehicles", 7), ("motorbike", -1),
                              ("timestamp", "2026-09-01 07:10"),
                              ("timestamp", "2026-09-01 07:00"),
                              ("timestamp", "2026-09-01 07:06")]:
            changed = source.copy()
            changed.loc[1, column] = value
            with self.subTest(column=column, value=value), self.assertRaises(ValueError):
                normalize_counts(changed)


if __name__ == "__main__":
    unittest.main()

