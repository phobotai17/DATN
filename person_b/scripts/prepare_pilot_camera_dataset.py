"""Prepare real line-crossing series from Person A's full pilot_camera recording."""
from pathlib import Path
import hashlib,json
import cv2
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
src=ROOT/'data/tuan4/data'
out=ROOT/'data/forecast_dataset/pilot_camera_real'
out.mkdir(parents=True,exist_ok=True)
meta=json.loads((src/'seg/meta.json').read_text())
events=pd.read_csv(src/'count_events_full.csv')
classes=['motorbike','car','truck','bus']
mapping={'xe_may':'motorbike','xe_hoi':'car','xe_tai':'truck','bus':'bus'}
assert not events.isna().any().any()
assert not events.duplicated(['frame','track_id','direction']).any()
assert set(events.direction)<= {'toward','away'}
events['class_name']=events['class'].map(mapping)
assert not events.class_name.isna().any()
start=pd.Timestamp(meta['video_start'],tz='Asia/Ho_Chi_Minh')
end=start+pd.Timedelta(seconds=meta['duration_s'])
events['timestamp']=pd.to_datetime(events.timestamp,format='mixed').dt.tz_localize('Asia/Ho_Chi_Minh')
assert events.timestamp.ge(start).all() and events.timestamp.lt(end).all()
assert np.max(np.abs((events.timestamp-start).dt.total_seconds()-events.time_s))<0.01
assert np.max(np.abs(events.frame/meta['fps_in']-events.time_s))<0.01
cap=cv2.VideoCapture(str(ROOT/'data/pilot_camera.mp4'))
assert cap.isOpened()
assert cap.get(cv2.CAP_PROP_FRAME_COUNT)==meta['total_frames']
assert abs(cap.get(cv2.CAP_PROP_FPS)-meta['fps_in'])<0.01
cap.release()
# Confirm full processing frame coverage; a detection-only log does not prove
# every frame was processed, but here every expected stride frame is represented.
frames=set()
for chunk in pd.read_csv(src/'tracking_log_full.csv',usecols=['frame'],chunksize=100000):
 frames.update(chunk.frame.tolist())
expected=set(range(0,meta['total_frames'],meta['stride']))
missing=len(expected-frames)
assert (expected-frames) <= {max(expected)}, 'Interior processing gaps require review'
# Last stride frame is absent. Conservatively end coverage before it.
if missing:
 end=start+pd.Timedelta(seconds=max(expected)/meta['fps_in'])
events['camera_id']='pilot_camera'
events['session_id']='pilot_camera_20260409_134150'
events['line_id']='horizontal_y600'
events.to_csv(out/'crossing_events.csv',index=False)
summary={}
for minutes in [1,5]:
 records=[]
 for t in pd.date_range(start.floor(f'{minutes}min'),end.floor(f'{minutes}min'),freq=f'{minutes}min'):
  stop=t+pd.Timedelta(minutes=minutes)
  coverage=max(0,(min(end,stop)-max(start,t)).total_seconds())
  subset=events[(events.timestamp>=t)&(events.timestamp<stop)]
  for direction in ['toward','away']:
   counts=subset[subset.direction==direction].class_name.value_counts()
   row={'camera_id':'pilot_camera','session_id':'pilot_camera_20260409_134150','line_id':'horizontal_y600',
        'direction':direction,'timestamp':t,'interval_minutes':minutes,'coverage_seconds':coverage,
        'complete_interval':coverage==minutes*60,**{c:int(counts.get(c,0)) for c in classes}}
   row['total_vehicles']=sum(row[c] for c in classes)
   records.append(row)
 table=pd.DataFrame(records)
 assert table.total_vehicles.sum()==len(events)
 assert table[classes].sum(axis=1).equals(table.total_vehicles)
 table.to_csv(out/f'flow_{minutes}min_all.csv',index=False)
 complete=table[table.complete_interval].copy()
 complete.to_csv(out/f'flow_{minutes}min_complete.csv',index=False)
 summary[str(minutes)]={'complete_intervals_per_direction':int(len(complete)/2),
                        'partial_intervals_per_direction':int((len(table)-len(complete))/2)}
 # Reconcile one-minute total counts against Person A's delivered aggregate.
 if minutes==1:
  supplied=pd.read_csv(src/'counts_per_minute_full.csv')
  actual=table.groupby('timestamp').total_vehicles.sum().to_numpy()
  assert np.array_equal(actual,supplied.tong.to_numpy())
report={'source':'Person A full pilot_camera logs','events':len(events),'class_counts':events.class_name.value_counts().to_dict(),
        'directions':events.direction.value_counts().to_dict(),'start':str(start),'end':str(end),
        'duration_seconds':meta['duration_s'],'coverage':summary,'expected_tracking_frames':len(expected),
        'missing_tracking_frames':missing,'source_sha256':hashlib.sha256((src/'count_events_full.csv').read_bytes()).hexdigest(),
        'validation':['Video metadata agrees with log metadata','Event times agree with frames and timestamps',
                      'No interior stride-frame gaps; missing final frame excluded from coverage','All 1031 events conserved',
                      'One-minute totals match supplied aggregate'],
        'forecast_sequence_count_60min_history_30min_future':0,
        'training_ready':False,
        'limitations':['25.7 minutes cannot provide the configured 60-minute history and 30-minute future.',
                       'Counts are automatic, not manually verified ground truth.',
                       'Recording date and line configuration are supplied by Person A.',
                       'Tracker resets at segment boundaries may affect crossing counts; manual boundary review remains necessary.']}
(out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))

