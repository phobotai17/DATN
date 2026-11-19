from pathlib import Path
import json, cv2, pandas as pd
root=Path('person_b/data/drive_source')
rows=[json.loads(x) for x in (root/'inventory.jsonl').read_text(encoding='utf-8-sig').splitlines() if x.strip()]
lookup={x['id']:x for x in rows}
records=[]
for p in (root/'videos').iterdir():
 if p.suffix.lower() not in {'.mp4', '.avi', '.mov'}: continue
 c=cv2.VideoCapture(str(p)); fps=c.get(cv2.CAP_PROP_FPS); n=c.get(cv2.CAP_PROP_FRAME_COUNT)
 if fps>0 and n>0:
  records.append({'file_id':p.stem,'filename':lookup[p.stem]['name'],'location':lookup[p.stem]['location'],'fps':fps,'frames':n,'duration_seconds':n/fps,'possible_complete_5min_intervals_upper_bound':int(n/fps//300)})
 c.release()
pd.DataFrame(records).to_csv(root/'video_coverage.csv',index=False)
print(pd.DataFrame(records).to_string(index=False))

