import unittest

from evals.metrics import errors, event_scores
from evals.score_realtime import associate, score_alerts


class MetricsTest(unittest.TestCase):
    def test_zero_actual_is_excluded_only_from_mape(self):
        result = errors([(0, 2), (4, 3)])
        self.assertEqual(result["mae"], 1.5)
        self.assertEqual(result["mape_percent"], 25)
        self.assertEqual(result["mape_samples"], 1)

    def test_matching_is_one_to_one_and_kind_specific(self):
        result = event_scores(
            [("up", 2), ("up", 2.2), ("down", 5)],
            [("up", 2.1), ("up", 5)], .5
        )
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 2, 1))
        self.assertEqual(result["f1"], .4)

    def test_alert_for_different_vehicle_is_false_positive(self):
        result = event_scores([("wrong_way", 2, "vehicle-b")],
                              [("wrong_way", 2, "vehicle-a")], .5)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (0, 1, 1))

    def test_association_tracks_switch_and_checks_alert_identity(self):
        left = dict(x1=10, y1=10, x2=30, y2=30)
        right = dict(x1=50, y1=10, x2=70, y2=30)
        labels = [dict(time_s=t, object_id=obj, **bounds)
                  for t in (0, 1) for obj, bounds in (("left", left), ("right", right))]
        frames = [
            dict(time_s=0, tracks=[dict(track_id=1, **left), dict(track_id=2, **right)], alerts=[]),
            dict(time_s=1, tracks=[dict(track_id=3, **left), dict(track_id=2, **right)],
                 alerts=[dict(time_s=1, track_id=2, event="abrupt_turn")]),
        ]
        tracking, anchors = associate(labels, frames, .25)
        self.assertEqual(tracking["id_switches"], 1)
        self.assertEqual(tracking["idf1"], .75)
        scores = score_alerts(frames, anchors, [dict(time_s=1, kind="abrupt_turn", object_id="left")],
                              ["abrupt_turn"], 0, 2, .5, .25)["abrupt_turn"]
        self.assertEqual((scores["tp"], scores["fp"], scores["fn"]), (0, 1, 1))


if __name__ == "__main__":
    unittest.main()
