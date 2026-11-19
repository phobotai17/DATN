# Traffic measurement and event screening

The video page now runs YOLO/ByteTrack plus classical measurements on each processed frame.
Model weights are warmed when the video page opens and cached per browser session. Tracker
identities and event counters reset for every video. Browser refresh starts a new session.

## Use

Run `.venv/Scripts/python.exe -m streamlit run app/app.py` from `person_b`.
Choose the video page. Open **Vùng đo và ngưỡng cảnh báo** to adjust peer count,
persistence and the speed ratio, or upload a camera profile. Processing starts on upload.
The demo uses the existing two pilot camera zones. Other videos default to a whole-frame observation
zone. Confirming the calibrated pilot camera view additionally enables the original wrong-way detector.

Results include a zone count chart, stopped-vehicle counts, motion quality, speed/direction
alerts, gate movements when configured, and CSV exports. Presence counts and crossing flow
are different measures. Counts are observed vehicles, not vehicles per square metre.
Only the first processed frame in each video second is exported for count/motion time series;
alert decisions use every processed frame. Zero means no tracked vehicle in that decoded frame.

## Camera profile

Download the pilot camera template in the app. Coordinates are pixels in the original video, with
bottom-center bounding-box anchors. Frame dimensions must match exactly. Shared polygon
edges belong to the first matching zone. Zones should describe disjoint road areas.

```json
{
  "frame_size": [640, 480],
  "zones": {"road": [[0, 0], [639, 0], [639, 479], [0, 479]]},
  "directions": {"road": [0, 1]},
  "entry_gates": {"north": [[0, 0], [639, 0], [639, 60], [0, 60]]},
  "exit_gates": {"south": [[0, 420], [639, 420], [639, 479], [0, 479]]}
}
```

Optional `homography` is a calibrated invertible 3x3 image-to-ground-plane matrix,
with output coordinates in metres. With it speed is km/h; without it speed is px/s.
Do not supply an identity matrix and label the output metric speed. Derive calibration
from measured ground correspondences and validate against independent measurements.
Optional `directions` are reviewed legal **image-space** direction vectors per zone.
Do not assign one vector to an intersection interior with multiple legal turning paths.
The zone wrong-way detector is separate from the existing pilot camera road-line detector.

## Algorithms and defaults

- Presence: point-in-polygon, including stationary vehicles; no stale-track extrapolation.
- Quality: reject gaps >1.5s and jumps >1.5 normalized frame diagonals/components per second
  (Euclidean distance after dividing x/y by image width/height). Fit velocity over up to
  one second, requiring 0.3s history. Reset persistence when a track is absent.
- Dwell: image motion below max(2 px/s, 0.002 times image height); count stopped after 2s.
  This is a camera-specific proxy, not a calibrated physical stop threshold.
- Speed peers: distinct current tracks, same class and zone, heading cosine >0.85,
  within normalized distance 0.15. Default at least 5 peers.
- Speed threshold: max(1.8 times median, median + max(3.5 times 1.4826 times MAD,
  5 km/h or 0.01 times image height px/s)). Require 1s persistence; one alert per track.
- Zone wrong way: heading cosine below -0.85, minimum motion, same persistence duration.
- Gate movements: track visits entry, leaves entry, then visits exit. First observed
  entry is retained; one movement per continuous track. Gaps/jumps reset incomplete routes.
- Zone forecast: constant mean of available samples from the last 60s, horizon 5 minutes.
  This is an unvalidated baseline; existing synthetic LSTM/GRU experiments remain separate.

## Gate proposals

The fourth video-page tab clusters the first/last seven points of complete tracks,
using OpenCV K-Means and a user-selected number of gates. It filters short, low-displacement,
gapped and recording-boundary tracks, then creates rectangles constrained to ROI peripheral
strips. This is an adaptation, not an exact reproduction of the paper's grid-polygons method.
Review proposals on video; occlusion endpoints and segment resets can produce false gates.
Upload the reviewed profile explicitly to use it. `segment_id` is supported in CSV grouping;
otherwise track IDs must be unique across recording segments. More representative footage
is needed before claiming cross-camera accuracy.

## Verification and limits

Unit tests cover presence, stopped vehicles, time-based speed, homography, gaps/jumps,
peer filtering/persistence, direction rules, gate visits and invalid geometry. The real-model
smoke test processes the demo twice to verify repeatability and tracker reset.
Run `python -m unittest discover -s tests` in the project environment.

These are functional checks, not held-out event accuracy or real-time throughput certification.
Speed flags are candidates for review, not validated collision predictions. Training real-data
forecast models and measuring event precision/recall still require independent labels and
longer recordings. The original pipeline defaults (including wrong-way angle 165 degrees)
are preserved; earlier demo threshold tuning was not treated as held-out validation.
