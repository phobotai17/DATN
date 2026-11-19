from pathlib import Path
import json
import cv2
import numpy as np
import pandas as pd
from plotly import graph_objects as go
from plotly.subplots import make_subplots

root = Path(__file__).resolve().parents[1]
out = root / 'results/pilot_camera_density'
out.mkdir(parents=True, exist_ok=True)
source = root / 'data/tuan4/data'
meta = json.loads((source / 'seg/meta.json').read_text())
fps = meta['fps_in']
zones = {
    'toward_side': [(330,190),(672,190),(232,390),(8,390)],
    'away_side': [(672,190),(892,190),(833,390),(232,390)],
}
polygons = {name: np.array(points, dtype=np.int32)*2 for name,points in zones.items()}
(out/'zones.json').write_text(json.dumps({'frame_size':[1920,1080],'zones':{k:v.tolist() for k,v in polygons.items()}},indent=2))
tracks = pd.read_csv(source/'tracking_log_full.csv')
frames = pd.Index(np.arange(0,meta['total_frames'],int(fps)),name='frame')
present = frames.isin(tracks.frame.unique())
sample = tracks[tracks.frame.isin(frames)].drop_duplicates(['frame','track_id']).copy()

def zone_of(x,y):
    for name,poly in polygons.items():
        if cv2.pointPolygonTest(poly,(float(x),float(y)),False)>=0:
            return name
    return ''

sample['x'] = (sample.x1+sample.x2)/2
sample['y'] = sample.y2
sample['zone'] = [zone_of(x,y) for x,y in zip(sample.x,sample.y)]
classes = ['xe_may','xe_hoi','xe_tai','bus']
assert set(sample['class']) <= set(classes)
parts = []
for zone in zones:
    selected = sample[sample.zone.eq(zone)]
    counts = (selected.groupby(['frame','class']).size().unstack(fill_value=0)
              .reindex(index=frames,columns=classes,fill_value=0))
    counts['total'] = counts.sum(axis=1)
    counts = counts.astype('Int64')
    counts.loc[~present,:] = pd.NA
    counts['zone'] = zone
    counts['time_s'] = frames / fps
    counts['observed'] = present
    parts.append(counts.reset_index())
density = pd.concat(parts,ignore_index=True)
density.to_csv(out/'samples_1s.csv',index=False)
density['window_start_s'] = (density.time_s//10*10).astype(int)
groups = density.groupby(['zone','window_start_s'])
summary = groups[classes+['total']].mean().join(groups['observed'].sum().rename('observed_samples')).reset_index()
summary.to_csv(out/'window_means_10s.csv',index=False)
fig = make_subplots(rows=2,cols=1,shared_xaxes=True,subplot_titles=['Toward-camera side','Away-camera side'])
for row,zone in enumerate(zones,1):
    data = summary[summary.zone.eq(zone)]
    for col in ['total',*classes]:
        fig.add_trace(go.Scatter(x=data.window_start_s/60,y=data[col],name=col,legendgroup=col,
                                 showlegend=row==1,mode='lines'),row=row,col=1)
fig.update_layout(title='Pilot camera vehicles present by road zone · 10-second means')
fig.update_yaxes(title='Vehicles present')
fig.update_xaxes(title_text='Minutes from start',row=2,col=1)
fig.write_html(out/'density.html')
cap = cv2.VideoCapture(str(root/'data/pilot_camera.mp4'))
assert cap.isOpened()
assert (int(cap.get(3)),int(cap.get(4))) == (1920,1080)
for sec in (45,120,600,900):
    cap.set(cv2.CAP_PROP_POS_FRAMES,round(sec*fps))
    ok,frame = cap.read()
    if not ok:
        raise RuntimeError(f'Could not decode frame at {sec}s')
    frame = cv2.resize(frame,(960,540))
    for zone,poly in zones.items():
        cv2.polylines(frame,[np.array(poly,np.int32)],True,(0,210,255),2)
    cv2.imwrite(str(out/f'frame_{sec}.jpg'),frame)
cap.release()
print('samples',len(frames),'represented frames',sum(present),'windows',len(summary))
print(density[density.time_s.isin([45,120,600,900])].to_string(index=False))

