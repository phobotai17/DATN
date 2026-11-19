import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

import cv2
import numpy as np

from src.alert_evidence import AlertEvidence
from src.forecast_truth import forecast_errors, read_count_labels
from src.realtime import RealtimeSession
from src.traffic_analytics import TrafficAnalytics
from test_analytics import profile, vehicle


class RealtimeTest(unittest.TestCase):
    def test_replay_starts_at_zero_and_accounts_for_manual_skips(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "frames.avi"
            writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 20, (32, 32))
            try:
                self.assertTrue(writer.isOpened())
                for _ in range(8):
                    writer.write(np.zeros((32, 32, 3), dtype=np.uint8))
            finally:
                writer.release()
            worker = RealtimeSession.from_local_video(str(source), Path(directory), frame_skip=1)
            producer = Thread(target=worker._capture, daemon=True)
            producer.start()
            try:
                received = [worker.frames.get(timeout=2)[0] for _ in range(4)]
            finally:
                worker.stop()
                producer.join(2)
            self.assertEqual(received, [0., .1, .2, .3])
            self.assertEqual(worker.decoded, worker.skipped + len(received) + worker.dropped)
            self.assertTrue(worker.capture_done.is_set())

    def test_evidence_csv_points_to_decodable_software_encoded_clip(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            frame = np.zeros((64, 64, 3), dtype=np.uint8)
            evidence = AlertEvidence(output)
            try:
                track = vehicle(7, 32, 56)
                event = dict(time_s=.5, track_id=7, event="abrupt_turn", zone="road")
                for i in range(10):
                    evidence.update(i/8, frame, [track], [event] if i == 4 else [], frame.shape)
            finally:
                evidence.close()
            with (output/"violations.csv").open(encoding="utf-8-sig", newline="") as source:
                row, = csv.DictReader(source)
            self.assertEqual((row["track_id"], row["clip_status"]), ("7", "saved"))
            clip = cv2.VideoCapture(str(output / row["clip"]))
            try:
                self.assertTrue(clip.read()[0])
            finally:
                clip.release()

    def test_forecast_only_scores_matching_independent_labels(self):
        labels = read_count_labels(StringIO("second,zone,total\n300,road,2\n301,other,0\n"))
        forecast = {"target": 300, "values": {"road": 5, "other": 10}}
        self.assertEqual(forecast_errors(forecast, labels), [3])
        self.assertEqual(forecast_errors(forecast, {}), [])

    def test_curb_turn_then_parking_suppresses_dangerous(self):
        p = profile()
        p["parking_zones"] = {"curb": [[140, 180], [170, 180], [170, 320], [140, 320]]}
        analytics = TrafficAnalytics(p)
        comparison = TrafficAnalytics(profile())
        for i in range(60):
            t = i/10
            tracks = [vehicle(1, 100+100*min(t, .5), 200+100*min(.8, max(0, t-.5)))]
            result = analytics.update(t, tracks)
            comparison.update(t, tracks)
        self.assertTrue(result["tracks"][0]["parked"])
        self.assertFalse(analytics.alerts)
        self.assertIn("abrupt_turn", {alert["event"] for alert in comparison.alerts})
