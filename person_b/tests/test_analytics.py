import unittest
from src.traffic_analytics import TrafficAnalytics, validate_profile


def profile():
    return {'frame_size': [1000, 1000], 'zones': {'road': [[0, 0], [999, 0], [999, 999], [0, 999]]}}


def vehicle(tid, x, y=200):
    return dict(track_id=tid, loai='xe_may', x1=x-10, x2=x+10, y1=y-40, y2=y)


class AnalyticsTests(unittest.TestCase):
    def test_presence_includes_stopped_vehicles_and_empty_frames(self):
        engine = TrafficAnalytics(profile())
        for t in range(5):
            out = engine.update(float(t), [vehicle(1, 100)])
        self.assertEqual(out['zones'][0]['total'], 1)
        self.assertEqual(out['zones'][0]['stopped'], 1)
        self.assertEqual(engine.update(5., [])['zones'][0]['total'], 0)

    def test_speed_uses_elapsed_time_and_rejects_jump_and_gap(self):
        engine = TrafficAnalytics(profile())
        engine.update(0., [vehicle(1, 100)])
        out = engine.update(.5, [vehicle(1, 110)])
        self.assertAlmostEqual(out['tracks'][0]['speed'], 20.)
        self.assertEqual(engine.update(.6, [vehicle(1, 800)])['tracks'][0]['quality'], 'jump')
        self.assertEqual(engine.update(4., [vehicle(1, 810)])['tracks'][0]['quality'], 'gap')

    def test_peer_alert_requires_distinct_peers_and_persistence(self):
        engine = TrafficAnalytics(profile(), min_peers=3, persistence=.5)
        for i in range(11):
            t = i / 10
            rows = [vehicle(k, 100 + k*10 + t*10) for k in range(1, 5)]
            rows.append(vehicle(9, 100+t*80))
            out = engine.update(t, rows)
        self.assertEqual([a['track_id'] for a in engine.alerts], [9])
        lone = TrafficAnalytics(profile(), min_peers=3)
        for i in range(15):
            lone.update(i/10, [vehicle(1, 100+i*8)])
        self.assertFalse(lone.alerts)

    def test_metric_projection(self):
        p = profile()
        p['homography'] = [[.1, 0, 0], [0, .1, 0], [0, 0, 1]]
        engine = TrafficAnalytics(p)
        engine.update(0., [vehicle(1, 100)])
        out = engine.update(.5, [vehicle(1, 110)])
        self.assertAlmostEqual(out['tracks'][0]['speed'], 7.2)
        self.assertEqual(out['tracks'][0]['speed_unit'], 'km/h')

    def test_slow_vehicle_requires_sustained_difference(self):
        engine = TrafficAnalytics(profile(), min_peers=3, persistence=.5)
        for i in range(12):
            t = i / 10
            peers = [vehicle(k, 100 + k * 10 + t * 70) for k in range(1, 5)]
            engine.update(t, peers + [vehicle(9, 100 + t * 10)])
            if i < 8:
                self.assertFalse(engine.alerts)
        self.assertEqual([(a['track_id'], a['event']) for a in engine.alerts], [(9, 'relative_slow')])

    def test_flags_sharp_turn_but_not_straight_track_or_stationary_jitter(self):
        engine = TrafficAnalytics(profile())
        for i in range(13):
            t = i / 10
            engine.update(t, [
                vehicle(1, 100 + 100 * min(t, .5), 200 + 100 * max(0, t - .5)),
                vehicle(2, 100 + 100 * t, 350),
                vehicle(3, 100 + i % 2, 400),
            ])
        self.assertEqual([(a['track_id'], a['event']) for a in engine.alerts], [(1, 'abrupt_turn')])

    def test_profile_rejects_degenerate_geometry(self):
        p = profile()
        p['zones']['road'] = [[1, 1], [2, 2], [3, 3]]
        with self.assertRaises(ValueError):
            validate_profile(p)

    def test_permitted_direction_and_gate_movement(self):
        p = profile()
        p['directions'] = {'road': [-1, 0]}
        p['entry_gates'] = {'west': [[0, 0], [150, 0], [150, 999], [0, 999]]}
        p['exit_gates'] = {'east': [[300, 0], [999, 0], [999, 999], [300, 999]]}
        engine = TrafficAnalytics(p, persistence=.5)
        for i in range(31):
            engine.update(i/10, [vehicle(1, 100+i*10)])
        self.assertEqual(len(engine.movements), 1)
        self.assertEqual(engine.movements[0]['entry'], 'west')
        self.assertEqual([a['event'] for a in engine.alerts], ['zone_wrong_way'])

    def test_gate_discovery_rejects_short_recording(self):
        from src.gate_discovery import propose_gates
        import pandas as pd
        with self.assertRaises(ValueError):
            propose_gates(pd.DataFrame(), [1000, 1000])

    def test_overlapping_gates_do_not_count_stationary_vehicle_as_movement(self):
        p = profile()
        p['entry_gates'] = p['exit_gates'] = p['zones']
        engine = TrafficAnalytics(p)
        for i in range(10):
            engine.update(i/10, [vehicle(1, 100)])
        self.assertFalse(engine.movements)

    def test_invalid_profile_type_is_a_validation_error(self):
        with self.assertRaises(ValueError):
            validate_profile([])

    def test_speed_peer_group_excludes_opposite_direction(self):
        engine = TrafficAnalytics(profile(), min_peers=3, persistence=.3)
        for i in range(15):
            t = i/10
            rows = [vehicle(k, 150+k*10-t*10) for k in range(1, 5)] + [vehicle(9, 100+t*80)]
            out = engine.update(t, rows)
        self.assertEqual(out['tracks'][-1]['peer_count'], 0)
        self.assertFalse(engine.alerts)


if __name__ == '__main__':
    unittest.main()
