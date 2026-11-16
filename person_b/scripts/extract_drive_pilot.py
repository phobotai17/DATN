"""Pilot crossing extraction for the visually inspected Nguyen Thai Hoc clip.
Counts are automatic and require manual review before scientific evaluation.
"""
from pathlib import Path
import json
import cv2
import pandas as pd
from ultralytics import YOLO

ROOT=Path(__file__).resolve().parents[1]
ID='1VB0CZ2khc6hAO4T88rEjblGBSk6MyUMI'
video=ROOT/'data/drive_source/videos'/f'{ID}.mp4'
out=ROOT/'data/forecast_dataset'
out.mkdir(parents=True,exist_ok=True)
model=YOLO(str(ROOT/'data/goi_ban_giao_B/models/best_v2.pt'))
classes={'xe_may':'motorbike','xe_hoi':'car','xe_tai':'truck','bus':'bus'}
cap=cv2.VideoCapture(str(video))
fps=cap.get(cv2.CAP_PROP_FPS); frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
width=cap.get(cv2.CAP_PROP_FRAME_WIDTH); height=cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
# Pilot screen line across the lower road, inspected from the first frame.
line_y=height*0.6; xmin=width*0.1; xmax=width*0.85
states={}; counted=set(); events=[]; index=0
start=pd.Timestamp('2022-09-25 16:30:46',tz='Asia/Ho_Chi_Minh')
while True:
 ok,frame=cap.read()
 if not ok: break
 result=model.track(frame,persist=True,tracker='bytetrack.yaml',conf=0.3,verbose=False)[0]
 if result.boxes.id is not None:
  for tid,cid,box in zip(result.boxes.id.int().tolist(),result.boxes.cls.int().tolist(),result.boxes.xyxy.tolist()):
   name=classes.get(model.names[cid])
   if name is None: continue
   x=(box[0]+box[2])/2; y=box[3]
   # Hysteresis avoids repeated boundary jitter. Interpolate crossing x.
   side=1 if y>line_y+4 else (-1 if y<line_y-4 else 0)
   prev=states.get(tid)
   if side and prev and prev['side']!=side and tid not in counted and index-prev['frame']<=round(fps*2):
    ratio=(line_y-prev['y'])/(y-prev['y'])
    crossing_x=prev['x']+ratio*(x-prev['x'])
    if xmin<=crossing_x<=xmax:
     counted.add(tid)
     time_s=(prev['frame']+ratio*(index-prev['frame']))/fps
     events.append({'camera_id':'nguyen_thai_hoc_trinh_hoai_duc','session_id':ID,'line_id':'pilot_y60',
                    'timestamp':start+pd.Timedelta(seconds=time_s),'time_s':time_s,'track_id':tid,
                    'class_name':name,'direction':'down' if side>0 else 'up','review_status':'unreviewed'})
   if side: states[tid]={'side':side,'x':x,'y':y,'frame':index}
 index+=1
cap.release()
cols=['camera_id','session_id','line_id','timestamp','time_s','track_id','class_name','direction','review_status']
df=pd.DataFrame(events,columns=cols)
df.to_csv(out/'pilot_crossing_events.csv',index=False)
# Explicit coverage table. Partial bins are NOT scaled to five-minute counts.
end=start+pd.Timedelta(seconds=index/fps)
coverage=[]
for bucket in pd.date_range(start.floor('5min'),end.floor('5min'),freq='5min'):
 seconds=max(0,(min(end,bucket+pd.Timedelta(minutes=5))-max(start,bucket)).total_seconds())
 coverage.append({'camera_id':'nguyen_thai_hoc_trinh_hoai_duc','session_id':ID,'timestamp':bucket,
                  'coverage_seconds':seconds,'complete':seconds>=300,'eligible_for_training':False})
pd.DataFrame(coverage).to_csv(out/'coverage_5min.csv',index=False)
pd.DataFrame(columns=['camera_id','line_id','direction','timestamp','motorbike','car','truck','bus','total_vehicles']).to_csv(out/'training_5min.csv',index=False)
report={'status':'pilot_only_no_eligible_training_intervals','events':len(df),'processed_frames':index,
        'duration_seconds':index/fps,'start_time_source':'visible overlay on first frame, second precision',
        'weights':'data/goi_ban_giao_B/models/best_v2.pt','counting_line_normalized':[0.1,0.6,0.85,0.6],
        'limitations':['Automatic counts unreviewed; model and line require calibration.',
                       'Screen up/down is not a validated lane direction.',
                       'Only one pilot clip processed; source-wide extraction incomplete.',
                       'No complete five-minute interval, so training CSV intentionally has no rows.']}
(out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
