"""Optional real-model integration smoke test; run explicitly on the demo host."""
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'app'))


class VideoAnalyticsSmoke(unittest.TestCase):
    def test_demo_and_clean_second_video(self):
        from components.handoff_panel import run_video, detector_resource

        class Output:
            def __getattr__(self, name):
                return lambda *args, **kwargs: None

        package = ROOT/'data/goi_ban_giao_B'
        output = Output()
        kwargs = dict(calibrated=True, record=False, clock0='2026-04-09 13:47:00', stride=3)
        resource = detector_resource.__wrapped__(str(package/'models/best_v2.pt'))
        # Exercise real inference; only bypass Streamlit's session cache outside the UI thread.
        with patch('components.handoff_panel.detector_resource', return_value=resource):
            first = run_video(package, package/'demo/clip_ngc.mp4', 3, output, output, output, **kwargs)
            second = run_video(package, package/'demo/clip_ngc.mp4', 3, output, output, output, **kwargs)
        self.assertEqual(first['frames'], 60)
        self.assertEqual(len(first['zone_samples']), 6)
        self.assertEqual(first['zone_samples'], second['zone_samples'])
        self.assertEqual(first['motion_samples'][0]['track_id'], second['motion_samples'][0]['track_id'])
        self.assertTrue(first['motion_samples'])
        self.assertEqual(first['motion_samples'][0]['speed_unit'], 'px/s')


if __name__ == '__main__':
    unittest.main()
