"""Prepare Person A logs without inventing a recording date.
Run from person_b: python scripts/prepare_person_a.py
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ['motorbike', 'car', 'truck', 'bus']
MAPPING = {'xe_may': 'motorbike', 'xe_hoi': 'car', 'xe_tai': 'truck', 'bus': 'bus',
           'motorbike': 'motorbike', 'car': 'car', 'truck': 'truck'}


def read_log(path, events=False):
    df = pd.read_csv(path)
    required = ['frame', 'time_s', 'track_id', 'class'] + (['direction'] if events else [])
    if not set(required).issubset(df):
        raise ValueError(f'{path}: missing required columns')
    if df.empty or df[required].isna().any().any():
        raise ValueError(f'{path}: empty log or missing values')
    for col in ['frame', 'time_s', 'track_id']:
        df[col] = pd.to_numeric(df[col], errors='raise')
        if not np.isfinite(df[col]).all() or (df[col] < 0).any():
            raise ValueError(f'Invalid {col}')
    for col in ['frame', 'track_id']:
        if (df[col] % 1 != 0).any():
            raise ValueError(f'Noninteger {col}')
    if df.duplicated(['frame', 'track_id']).any():
        raise ValueError('Duplicate frame/track pair')
    df['class_name'] = df['class'].map(MAPPING)
    if df.class_name.isna().any():
        raise ValueError('Unknown vehicle class')
    return df.rename(columns={'frame': 'frame_id', 'cx': 'x', 'cy': 'y'}).drop(columns='class').sort_values(['time_s', 'frame_id'])


def counts(df, duration, bucket_seconds, observed):
    work = df.copy()
    if observed:
        votes = work.groupby(['track_id', 'class_name'], sort=False).agg(n=('frame_id', 'size'), first=('time_s', 'min')).reset_index()
        chosen = votes.sort_values(['n', 'first'], ascending=[False, True], kind='stable').drop_duplicates('track_id').set_index('track_id').class_name
        work['class_name'] = work.track_id.map(chosen)
    work['bucket'] = (work.time_s // bucket_seconds).astype(int)
    group = work.groupby(['bucket', 'class_name']).track_id
    table = (group.nunique() if observed else group.size()).unstack(fill_value=0)
    n = int(duration // bucket_seconds) + 1
    table = table.reindex(index=range(n), columns=CLASSES, fill_value=0).fillna(0).astype(int)
    table.columns.name = None
    table['total_vehicles'] = table[CLASSES].sum(axis=1)
    table.insert(0, 'time_s', np.arange(n) * bucket_seconds)
    table['bucket_seconds'] = bucket_seconds
    table['coverage_seconds_lower_bound'] = np.maximum(0, np.minimum(bucket_seconds, duration - table.time_s))
    table['complete_interval'] = table.time_s.add(bucket_seconds).le(duration)
    return table.reset_index(drop=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tracking', type=Path, default=ROOT/'data/tracking_log_fixed.csv')
    p.add_argument('--events', type=Path, default=ROOT/'data/count_events_fixed.csv')
    p.add_argument('--output', type=Path, default=ROOT/'data/person_a_prepared')
    args = p.parse_args()
    tracks, events = read_log(args.tracking), read_log(args.events, True)
    matched = events.merge(tracks[['frame_id', 'track_id', 'time_s']], on=['frame_id', 'track_id'], how='left', suffixes=('', '_tracking'), validate='one_to_one')
    if matched.time_s_tracking.isna().any() or not np.allclose(matched.time_s, matched.time_s_tracking, atol=0.001, rtol=0):
        raise ValueError('Crossing event lacks a matching frame/ID/time in tracking')
    duration = float(tracks.time_s.max())
    if float(tracks.time_s.min()) != 0:
        raise ValueError('Recording must begin at relative time zero for these interval coverage estimates')
    frames = tracks.groupby('frame_id').time_s
    if (frames.nunique() > 1).any() or not frames.first().sort_index().is_monotonic_increasing:
        raise ValueError('Inconsistent frame timestamps')
    args.output.mkdir(parents=True, exist_ok=True)
    tracks.to_csv(args.output/'tracking_relative.csv', index=False)
    events.to_csv(args.output/'crossing_events_relative.csv', index=False)
    for seconds in [10, 60, 300]:
        for name, df, observed in [('observed', tracks, True), ('crossings', events, False)]:
            result = counts(df, duration, seconds, observed)
            result.to_csv(args.output/f'{name}_{seconds}s.csv', index=False)
            if not observed:
                assert int(result.total_vehicles.sum()) == len(events)
    report = {
        'tracking_source': str(args.tracking.resolve()), 'events_source': str(args.events.resolve()),
        'time_basis': 'seconds since video start; actual recording date unknown',
        'duration_lower_bound_seconds': duration, 'tracking_rows': len(tracks),
        'unique_tracks': int(tracks.track_id.nunique()), 'crossing_events': len(events),
        'crossings_by_class': events.class_name.value_counts().to_dict(),
        'crossings_by_direction': events.direction.value_counts().to_dict(),
        'tracks_with_class_changes': int((tracks.groupby('track_id').class_name.nunique() > 1).sum()),
        'event_tracking_match': 'passed', 'complete_5min_intervals': int(duration // 300),
        'forecast_training_ready': False,
        'limitations': ['Duration is inferred from the last detection, not video metadata.',
                       'Coverage assumes a continuous recording; detection logs alone cannot prove it.',
                       'Observed counts use whole-recording majority class; crossing counts retain event class.',
                       'Relative-time outputs are not timestamp-based forecasting input.',
                       'Collect a longer continuous series before forecasting training.']}
    (args.output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
