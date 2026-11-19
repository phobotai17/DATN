"""Offline endpoint clustering to propose gates for human review."""
import cv2
import numpy as np
import pandas as pd


def propose_gates(log, frame_size, clusters=2, min_tracks=20):
    required = {'track_id', 'time_s', 'x1', 'x2', 'y2'}
    if not required.issubset(log.columns):
        raise ValueError('Tracking CSV needs track_id, time_s, x1, x2, y2.')
    data = log.copy()
    for col in required-{'track_id'}:
        data[col] = pd.to_numeric(data[col], errors='raise')
    if data.empty or not np.isfinite(data[list(required-{'track_id'})].to_numpy()).all():
        raise ValueError('Tracking CSV is empty or contains invalid coordinates/times.')
    size = np.asarray(frame_size, float)
    if size.shape != (2,) or (size <= 0).any():
        raise ValueError('Invalid frame size.')
    data['x'] = (data.x1+data.x2)/2
    data['y'] = data.y2
    first_time, last_time = data.time_s.min(), data.time_s.max()
    starts, ends, all_points = [], [], []
    keys = ['segment_id', 'track_id'] if 'segment_id' in data else ['track_id']
    for _, track in data.groupby(keys, sort=False):
        track = track.sort_values('time_s').drop_duplicates('time_s')
        pts = track[['x', 'y']].to_numpy(float)
        if (len(pts) < 14 or track.time_s.iloc[-1]-track.time_s.iloc[0] < 1
                or track.time_s.iloc[0] <= first_time+.5 or track.time_s.iloc[-1] >= last_time-.5
                or (track.time_s.diff().dropna() > 1.5).any()
                or np.linalg.norm((pts[-1]-pts[0])/size) < .1
                or (pts < 0).any() or (pts >= size).any()):
            continue
        starts.append(pts[:7])
        ends.append(pts[-7:])
        all_points.extend(pts)
    if len(starts) < max(min_tracks, clusters*3):
        raise ValueError(f'Only {len(starts)} complete usable tracks; need at least {max(min_tracks, clusters*3)}.')
    if not 2 <= clusters <= 9:
        raise ValueError('Choose 2–9 gates per endpoint type.')
    pts = np.asarray(all_points)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    span = np.maximum(hi-lo, 1)
    result = {'entry_gates': {}, 'exit_gates': {}, 'usable_tracks': len(starts),
              'method': 'K-Means endpoints; peripheral rectangles; review required'}
    for kind, chunks in [('entry_gates', starts), ('exit_gates', ends)]:
        points = np.concatenate(chunks)
        relative = (points-lo)/span
        points = points[((relative < 1/6) | (relative > 5/6)).any(axis=1)]
        if len(points) < clusters*3:
            raise ValueError('Too few peripheral endpoints. Review camera geometry.')
        cv2.setRNGSeed(42)
        _, labels, centers = cv2.kmeans(points.astype(np.float32), clusters, None,
            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, .1), 10, cv2.KMEANS_PP_CENTERS)
        for i in range(clusters):
            members = points[labels.ravel() == i]
            a, b = members.min(axis=0)-span*.02, members.max(axis=0)+span*.02
            center = (centers[i]-lo)/span
            side = int(np.argmin([center[0], 1-center[0], center[1], 1-center[1]]))
            if side == 0:
                b[0] = min(b[0], lo[0]+span[0]/6)
            elif side == 1:
                a[0] = max(a[0], hi[0]-span[0]/6)
            elif side == 2:
                b[1] = min(b[1], lo[1]+span[1]/6)
            else:
                a[1] = max(a[1], hi[1]-span[1]/6)
            a, b = np.clip(a, 0, size-1), np.clip(b, 0, size-1)
            if (b-a > 1).all():
                result[kind][f'{kind}_{i+1}'] = [[a[0], a[1]], [b[0], a[1]], [b[0], b[1]], [a[0], b[1]]]
    return result
