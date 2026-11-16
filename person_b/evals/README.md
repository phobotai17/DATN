# Traffic system evaluation

See the [detector checkpoint review](DETECTOR_REVIEW.md) for per-class AP, checkpoint selection and the validation settings.

See [pilot results](PILOT_RESULTS.md) for the CPU/GPU replay, labelled tracking and alert samples, and the comparison of five-minute forecasts.

## Paced replay and independent labels

From the project directory with the app's Python environment active:

```powershell
python -m evals.realtime_benchmark --video data/cam5.mp4 --profile results/cam5_density/zones.json --devices cpu cuda:0 --seconds 20 --out evals/runs/new-matrix
python -m evals.score_realtime evals/runs/new-matrix/cuda0-skip-auto-1 --tracks evals/labels/cam5_pilot_tracks.csv --roi 400 360 1480 880 --zone-truth evals/labels/cam5_pilot_counts.csv
python -m evals.realtime_benchmark --video data/goi_ban_giao_B/demo/clip_ngc.mp4 --profile evals/demo_profile.json --devices cuda:0 --skips auto --seconds 56 --out evals/runs/new-demo
python -m evals.score_realtime evals/runs/new-demo/cuda0-skip-auto-1 --tracks evals/labels/demo_wrongway_anchors.csv --anchors-only --events evals/labels/demo_wrongway_events.csv --kinds zone_wrong_way --window 46 53 --frame-tolerance .35
python -m evals.forecast_replay --observations results/cam5_density/samples_1s.csv --labels evals/labels/cam5_forecast_counts.csv --cutoff 840 --out evals/runs/new-forecast
python -m unittest discover -s tests
python -m unittest discover -s evals
```

- Replay uses the same background worker as Streamlit. Use `--repeat 3` for repeated trials. Adaptive sampling runs before the latest-frame buffer. `decoded` counts source frames inside the benchmark window, `skipped` counts policy skips, and `dropped` counts frames replaced in the buffer. `unaccounted` includes a frame left in the buffer if a run is stopped.
- P50/P95 measure arrival at the worker input through annotated frame and evidence submission. They exclude browser rendering and completed H.264 encoding. Wall time includes model loading and evidence flush. RSS is sampled process memory. CUDA MiB is PyTorch's peak allocated tensor memory and covers part of the card's total usage. Keep other workloads idle and compare repeated runs on the same input.
- Tracking labels use `time_s,object_id,x1,y1,x2,y2` in source pixels. Label all vehicles on annotated frames in the declared ROI for IDF1. The scorer matches boxes with IoU ≥ 0.5 on the nearest processed frame within tolerance, then pairs truth and tracker IDs across the sequence. Report the number of annotated frames covered alongside IDF1 and count MAE.
- Alert labels use `time_s,kind,object_id`. Annotate all occurrences of the requested kinds in `--window` and include bounding boxes near each event. Kinds are `zone_wrong_way`, `abrupt_turn` (Dangerous), `relative_speed` and `relative_slow`. A prediction matches only when kind, time and the vehicle association agree. Predictions without a verified object association are unmatched. Use `--anchors-only` when boxes only cover event subjects. For timing, a negative signed error means the alert preceded the labelled reference frame.
- The forecast benchmark reads a contiguous history of up to the last 60 observed one-second counts (requires all 60 for each scored forecast). GRU targets precede the cutoff, and scored test history starts at or after the cutoff. Use independently counted `second,zone,total` at each target, with the same zones as the observation series. The optional CSV input in the dashboard uses the same label format.

## Offline throughput benchmark

Run from the person_b project folder with the same Python environment as the integrated dashboard:

```powershell
.\.venv\Scripts\python.exe -m evals.benchmark --seconds 20
.\.venv\Scripts\python.exe -m evals.benchmark --video data/cam5.mp4 --calibrated --seconds 60 --stride 3 --height 480 --record
.\.venv\Scripts\python.exe -m unittest discover -s evals
```

The recording option needs the `imageio-ffmpeg` package listed in `requirements.txt`.

The default video is the bundled calibrated demo. Only pass `--calibrated` for the same Cam5 view. For another camera use `--video` and optionally `--profile` to load its own zones, directions and gates. Use `--stride 1` to process every frame; `--stride 3` skips two between detections.

Each run writes a fresh directory in `evals/runs/` with `report.json` and prediction CSVs. Use `--out` to specify a new directory. The report records the input, settings, device, library versions, track diagnostics and activity counts.

| Metric | Meaning |
| --- | --- |
| End-to-end processed FPS | Frames actually processed divided by wall time for the dashboard runner and zone forecast. Includes model setup, decode, detection, tracking, analytics, drawing and optional encoding. |
| After-first-frame FPS | Dashboard's warm throughput estimate, including the encoder flush when recording. |
| Video seconds per wall second | How fast the clip is covered at the chosen stride. Above 1 means it processes the clip faster than its playback duration. |
| Forecast latency | Time to compute the five-minute zone baseline after processing. |

The runner uses headless sinks for UI updates. Browser rendering, upload transfer, Streamlit serialization and dashboard CSV downloads are outside the timer. Use separate cold runs with the same clip duration and settings for a fair comparison, and report stride alongside FPS. A short clip is a smoke test; use longer, representative clips and repeat runs for reportable numbers.

## Accuracy

Pass independently annotated CSVs. Without them, the report leaves video accuracy null; the exported predictions are for review and are not labels.

- `--zone-truth labels.csv`: columns `second,zone,total,stopped`. Label the first sampled frame in each annotated source-video second for this stride. Use zone names from the camera profile. The scorer reports MAE, RMSE, signed bias and MAPE separately for total and stopped vehicles. Zero actuals count toward MAE/RMSE but are excluded from MAPE.
- `--event-truth labels.csv`: columns `time_s,kind,object_id`. For alert rows, use a human-assigned identity and pass `--event-id-map` with `track_id,object_id` for the tracks reviewed in this run. Crossing and movement rows may leave `object_id` blank. Label **all** events for the evaluated interval and enabled event types. Use kinds such as `crossing:toward`, `crossing:away`, `alert:calibrated_wrong_way`, `alert:relative_speed:zone_name`, `alert:zone_wrong_way:zone_name`, and `movement:entry_name:exit_name`. The scorer matches each event once within its kind, vehicle identity for alerts, and `--tolerance` seconds (default 1). It reports precision, recall and F1 together with TP/FP/FN, overall and by kind. Undefined rates are null.
- The dashboard zone forecast uses the mean observed count over the last 60 seconds. To score it, pass `--forecast-truth labels.csv` with `second,zone,total` for independently counted vehicles 300 seconds after the final sampled second (see `target_second` in the report). Without those labels, forecast accuracy is null. If present, the existing offline experiment's MAE/RMSE/MAPE for persistence, moving average, seasonal naive, GRU and LSTM are copied to `synthetic_forecast_metrics.csv`. These are synthetic flow results; they do not validate the zone forecast.
- Detector mAP and tracker IDF1/HOTA require compatible labelled boxes and track identities on held-out video. This benchmark exercises both components and reports their downstream behavior; it does not infer box or identity accuracy from the prediction logs.

## Demo smoke result

On the RTX 4050 Laptop GPU, the first 12 seconds of the bundled 60 FPS clip at 480p output and stride 2 produced 360 processed frames in 40.9 seconds: **8.8 end-to-end processed FPS**, **11.7 FPS after the first frame**, and **0.29 video seconds per wall second**. This run excluded encoding, overlapped the test suite, and had no independent labels. Treat it as a smoke result; repeat on an idle machine before comparing settings.
