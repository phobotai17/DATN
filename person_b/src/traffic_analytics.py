"""Camera-specific measurements from tracks; no detector or UI dependencies."""
from collections import Counter, deque
from copy import deepcopy
import cv2
import numpy as np


def validate_profile(profile):
    if not isinstance(profile, dict):
        raise ValueError('Camera profile must be a JSON object.')
    p = deepcopy(profile)
    size = np.asarray(p.get('frame_size', []), dtype=float)
    if size.shape != (2,) or not np.isfinite(size).all() or (size <= 0).any():
        raise ValueError('frame_size must contain positive width and height.')
    for field in ('zones', 'entry_gates', 'exit_gates', 'parking_zones'):
        if not isinstance(p.get(field, {}), dict):
            raise ValueError(f'{field} must map names to polygons.')
        for name, vertices in p.get(field, {}).items():
            poly = np.asarray(vertices, dtype=np.float32)
            if (not name or poly.ndim != 2 or poly.shape[1] != 2 or len(poly) < 3
                    or not np.isfinite(poly).all() or (poly < 0).any()
                    or (poly >= size).any() or abs(cv2.contourArea(poly)) < 1):
                raise ValueError(f'Invalid polygon: {name}')
    if not p.get('zones'):
        raise ValueError('At least one density zone is required.')
    if p.get('homography') is not None:
        h = np.asarray(p['homography'], dtype=float)
        if h.shape != (3, 3) or not np.isfinite(h).all() or abs(np.linalg.det(h)) < 1e-12:
            raise ValueError('homography must be an invertible 3x3 pixel-to-metre matrix.')
    if not isinstance(p.get('directions', {}), dict):
        raise ValueError('directions must be an object keyed by zone name.')
    for name, vector in p.get('directions', {}).items():
        v = np.asarray(vector, float)
        if name not in p['zones'] or v.shape != (2,) or not np.isfinite(v).all() or np.linalg.norm(v) == 0:
            raise ValueError('directions must contain nonzero image-space vectors for named zones.')
    return p


class TrafficAnalytics:
    def __init__(self, profile, *, min_peers=5, persistence=1., speed_ratio=1.8,
                 mad_multiplier=3.5, peer_radius=.15, max_gap=1.5):
        self.profile = validate_profile(profile)
        self.size = np.array(self.profile['frame_size'], float)
        self.polygons = {key: {name: np.asarray(poly, np.float32) for name, poly in self.profile.get(key, {}).items()}
                         for key in ('zones', 'entry_gates', 'exit_gates', 'parking_zones')}
        self.h = self.profile.get('homography')
        self.unit = 'km/h' if self.h is not None else 'px/s'
        self.min_peers, self.persistence = int(min_peers), float(persistence)
        if self.min_peers < 3 or self.persistence <= 0 or speed_ratio <= 1:
            raise ValueError('Require at least 3 peers, positive persistence and speed ratio >1.')
        self.ratio, self.mad_multiplier = float(speed_ratio), float(mad_multiplier)
        self.radius, self.max_gap = peer_radius, max_gap
        self.states, self.alerts, self.movements = {}, [], []
        self.last_time = None

    def region(self, point, kind='zones'):
        # First polygon owns a shared edge: presence is never counted twice.
        return next((name for name, poly in self.polygons[kind].items()
                     if cv2.pointPolygonTest(poly, tuple(map(float, point)), False) >= 0), '')

    def position(self, point):
        if self.h is None:
            return point
        value = np.asarray(self.h) @ np.array([*point, 1.])
        if abs(value[2]) < 1e-8:
            return None
        return value[:2] / value[2]

    def turn_angle(self, history):
        if len(history) < 5 or history[-1][0] - history[0][0] < .7:
            return None
        middle = (history[0][0] + history[-1][0]) / 2
        mid = min(range(1, len(history) - 1), key=lambda i: abs(history[i][0] - middle))
        t0, p0 = history[0]
        tm, pm = history[mid]
        t1, p1 = history[-1]
        if min(tm - t0, t1 - tm) < .25:
            return None
        before, after = (pm - p0) / (tm - t0), (p1 - pm) / (t1 - tm)
        a, b = np.linalg.norm(before), np.linalg.norm(after)
        if min(a, b) < max(5., self.size[1] * .02):
            return None
        angle = float(np.degrees(np.arccos(np.clip((before @ after) / (a * b), -1, 1))))
        return angle if angle >= 55 else None

    def update(self, time_s, tracks):
        t = float(time_s)
        if not np.isfinite(t) or (self.last_time is not None and t <= self.last_time):
            raise ValueError('Frame timestamps must increase strictly.')
        self.last_time = t
        self.states = {k: s for k, s in self.states.items() if t-s['last'] <= 30}
        measured, seen, new_alerts = [], set(), []
        for row in tracks:
            tid = row['track_id']
            if tid in seen:
                continue
            seen.add(tid)
            point = np.array([(row['x1']+row['x2'])/2, row['y2']], float)
            zone = self.region(point)
            s = self.states.setdefault(tid, dict(history=deque(maxlen=90), last=t, point=point,
                candidate=None, alerted=set(), stopped_since=None, entry='', exit='', movement_done=False,
                wrong_since=None, wrong_alerted=False, left_entry=False, curb_turn=None, curb_stop=None))
            dt, jump = t-s['last'], np.linalg.norm((point-s['point'])/self.size)
            quality = 'ok'
            if dt > self.max_gap:
                quality = 'gap'
            elif dt > 0 and jump/dt > 1.5:
                quality = 'jump'
            if quality != 'ok':
                s['history'].clear()
                s.update(candidate=None, stopped_since=None, entry='', exit='', movement_done=False,
                         wrong_since=None, left_entry=False, curb_turn=None, curb_stop=None)
            s['last'], s['point'] = t, point
            s['history'].append((t, point))
            while len(s['history']) > 2 and t-s['history'][1][0] >= 1.:
                s['history'].popleft()
            speed, heading = None, None
            history = s['history']
            if quality == 'ok' and len(history) >= 2 and t-history[0][0] >= .3:
                times = np.array([v[0] for v in history])
                pts = np.array([v[1] for v in history])
                centered = times-times.mean()
                velocity = (centered[:, None]*pts).sum(axis=0)/(centered@centered)
                magnitude = np.linalg.norm(velocity)
                heading = velocity/max(magnitude, 1e-9)
                positions = [self.position(p) for p in pts]
                if all(p is not None for p in positions):
                    v = (centered[:, None]*np.array(positions)).sum(axis=0)/(centered@centered)
                    speed = float(np.linalg.norm(v))*(3.6 if self.h is not None else 1.)
                if magnitude < max(2., self.size[1]*.002):
                    s['stopped_since'] = s['stopped_since'] if s['stopped_since'] is not None else history[0][0]
                else:
                    s['stopped_since'] = None
            elif quality == 'ok':
                quality = 'warming'
            if quality in ('ok', 'warming'):
                entry, exit_gate = self.region(point, 'entry_gates'), self.region(point, 'exit_gates')
                if entry and not s['entry']:
                    s['entry'] = entry
                if s['entry'] and entry != s['entry']:
                    s['left_entry'] = True
                if exit_gate and s['entry'] and s['left_entry'] and not s['movement_done']:
                    s['exit'] = exit_gate
                    s['movement_done'] = True
                    self.movements.append(dict(time_s=t, track_id=tid, entry=s['entry'], exit=exit_gate))
            dwell = 0. if s['stopped_since'] is None else t-s['stopped_since']
            at_curb = bool(self.region(point, 'parking_zones'))
            if at_curb and s['stopped_since'] is not None:
                if s['curb_stop'] is None:
                    s['curb_stop'] = t
            else:
                s['curb_stop'] = None
            parked = s['curb_stop'] is not None and t-s['curb_stop'] >= 3.
            measured.append(dict(track_id=tid, loai=row['loai'], zone=zone, x=point[0], y=point[1],
                speed=speed, speed_unit=self.unit, quality=quality, dwell_s=round(dwell, 2),
                heading=heading, peer_count=0, peer_median=None, parked=parked, at_curb=at_curb))
        for r in measured:
            s = self.states[r['track_id']]
            if r['parked']:
                s['curb_turn'] = s['candidate'] = s['wrong_since'] = None
                continue
            if r['quality'] != 'ok' or not r['zone'] or r['speed'] is None:
                s['candidate'] = s['wrong_since'] = None
                continue
            if 'abrupt_turn' not in s['alerted']:
                angle = self.turn_angle(s['history'])
                pending = s['curb_turn']
                if pending is None and angle is not None:
                    pending = s['curb_turn'] = (t, angle, r['zone'])
                if pending is not None:
                    detected_at, turn_angle, zone = pending
                    if not r['at_curb'] or t-detected_at >= 5.:
                        s['alerted'].add('abrupt_turn')
                        s['curb_turn'] = None
                        new_alerts.append(dict(time_s=t, track_id=r['track_id'], event='abrupt_turn',
                                               zone=zone, angle_deg=round(turn_angle, 1)))
            peers = [q['speed'] for q in measured if q['track_id'] != r['track_id']
                     and q['quality'] == 'ok' and not q['parked'] and q['speed'] is not None and q['zone'] == r['zone']
                     and q['loai'] == r['loai'] and q['heading'] @ r['heading'] > .85
                     and np.linalg.norm((np.array([q['x'], q['y']])-np.array([r['x'], r['y']]))/self.size) <= self.radius]
            r['peer_count'] = len(peers)
            if len(peers) >= self.min_peers:
                median = float(np.median(peers))
                mad = float(np.median(np.abs(np.array(peers)-median)))
                floor = 5. if self.h is not None else self.size[1]*.01
                deviation = max(floor, self.mad_multiplier*1.4826*mad)
                upper = max(median*self.ratio, median+deviation)
                lower = min(median/self.ratio, median-deviation)
                r['peer_median'] = median
                # An observed heading is required so stationary vehicles are
                # not compared with moving traffic in an unknown direction.
                event = ('relative_speed' if r['speed'] > upper else
                         'relative_slow' if r['speed'] < lower else None)
                if event:
                    if s['candidate'] is None or s['candidate'][0] != event:
                        s['candidate'] = (event, t)
                    if t-s['candidate'][1] >= self.persistence and event not in s['alerted']:
                        s['alerted'].add(event)
                        new_alerts.append(dict(time_s=t, track_id=r['track_id'], event=event,
                            zone=r['zone'], speed=r['speed'], speed_unit=self.unit, peer_median=median, peer_count=len(peers)))
                else:
                    s['candidate'] = None
            else:
                s['candidate'] = None
            direction = self.profile.get('directions', {}).get(r['zone'])
            if direction is not None:
                d = np.array(direction, float)
                if r['speed'] > (3 if self.h is not None else self.size[1]*.01) and r['heading'] @ (d/np.linalg.norm(d)) < -.85:
                    s['wrong_since'] = t if s['wrong_since'] is None else s['wrong_since']
                    if t-s['wrong_since'] >= self.persistence and not s['wrong_alerted']:
                        s['wrong_alerted'] = True
                        new_alerts.append(dict(time_s=t, track_id=r['track_id'], event='zone_wrong_way', zone=r['zone']))
                else:
                    s['wrong_since'] = None
        # Missing observations must break persistence, even before a track expires.
        for tid, s in self.states.items():
            if tid not in seen:
                s['candidate'] = s['wrong_since'] = s['stopped_since'] = None
                s['curb_stop'] = s['curb_turn'] = None
        zones = []
        for name in self.polygons['zones']:
            inside = [r for r in measured if r['zone'] == name]
            counts = Counter(r['loai'] for r in inside)
            zones.append(dict(time_s=t, zone=name, total=len(inside), stopped=sum(r['dwell_s'] >= 2 for r in inside),
                              parked=sum(r['parked'] for r in inside),
                              **{c: counts[c] for c in ('xe_may', 'xe_hoi', 'xe_tai', 'bus')}))
        self.alerts.extend(new_alerts)
        for r in measured:
            r.pop('heading')
        return dict(zones=zones, tracks=measured, alerts=new_alerts)
