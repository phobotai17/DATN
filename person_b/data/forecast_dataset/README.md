# Forecast dataset preparation status

Target: line-crossing flow per camera, counting line and direction, in complete
five-minute intervals. Source inventory: ../drive_source/inventory.jsonl.

Three downloaded Drive samples were decoded and each is approximately 63.824
seconds. See ../drive_source/video_coverage.csv. This is a sample audit, not a
claim that all 475 files have the same duration.

The pilot script `scripts/extract_drive_pilot.py` now uses the project's YOLOv8s
checkpoint and ByteTrack. The saved Nguyen Thai Hoc - Trinh Hoai Duc pilot
outputs predate that change. The original detector is recorded in `report.json`.
The visible first-frame timestamp is 25/09/2022 16:30:46; filename time alone
is insufficient. Events use a provisional horizontal line across the lower
road. Counts require manual review and camera-specific calibration.

Outputs:
- pilot_crossing_events.csv: automatic, unreviewed events with source IDs.
- coverage_5min.csv: actual partial coverage, never inflated to five minutes.
- training_5min.csv: schema only, intentionally empty until eligible data exists.
- report.json: extraction settings, results and limitations.

To complete a forecasting dataset, obtain continuous recordings long enough for
60 minutes of history plus 30 minutes of future targets per sequence, and enough
separate periods for training/validation/testing. Alternatively, find and verify
continuous recordings elsewhere in the source inventory. Never bridge missing
periods or treat absent recordings as zero traffic. Sparse one-minute clips may
support a different snapshot-flow estimation study, but not the currently
specified continuous five-minute forecasting experiment without changing its
methodology.
