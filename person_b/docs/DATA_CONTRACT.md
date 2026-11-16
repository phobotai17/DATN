# Tracking to forecasting handoff

## Standard output

    timestamp,motorbike,car,truck,bus,total_vehicles

Counts are nonnegative integers; total_vehicles is the sum of all four classes.
Timestamps identify the start of each clock-aligned interval. For forecasting,
use a fixed five-minute cadence: 3 future steps = 15 minutes; 6 = 30 minutes.
Do not mix cameras, recording sessions, counting methods, or interval lengths.

## Input from Person A

Required tracking columns:

    frame_id,timestamp,track_id,class_name

Optional columns such as x, y, w, h, and conf are preserved in the source log but
are not needed for aggregation. Allowed class names are motorbike, car, truck,
and bus. IDs must be nonnegative integers and unique within one recording.
Unknown classes fail validation instead of silently disappearing.

The aggregation counts distinct IDs observed in each interval. A vehicle visible
across two intervals is counted once in each. One class is assigned per ID using
the majority of frame predictions, ties resolved by earliest observation.
This offline assignment can use the whole recording; it is not a streaming
classification rule. Duplicate track/frame rows do not bias the vote.

Interior empty buckets become zero only on the assumption that the recording
was continuous. A detection-only log cannot distinguish a stopped camera from
zero traffic or recover leading/trailing empty recording periods. Boundary
buckets can be partial. Review these before training on real data.

## Commands

Run these from D:\code\DATN\person_b with the existing parent environment.

Aggregate a real tracking log after Person A supplies it:

    ..\.venv\Scripts\python.exe -B -m src.tracking --input data/tracking_log.csv --window 5 --output data/observed_counts_5min.csv

Validate an already aggregated five-minute series:

    ..\.venv\Scripts\python.exe -B -m src.tracking --input data/mock_traffic_data.csv --input-kind counts --window 5 --output data/validated_counts_5min.csv

Run contract tests:

    ..\.venv\Scripts\python.exe -B -m unittest discover -s tests -v

## Video app exports

The counts input accepts total as an alias for total_vehicles. It requires all
four vehicle columns, correct totals, and unique, regularly spaced, clock-aligned
timestamps. It rejects missing intervals rather than inventing zero counts.
The current video app defaults to ten-second buckets; export five-minute,
clock-aligned buckets before using this five-minute contract.

Line crossings measure flow past a chosen line. They are not the same as
unique vehicles observed anywhere in the frame. Schema normalization does not
convert one measurement to the other. Use a single definition throughout a
forecasting experiment and record it in the experiment report. A series with
missing vehicle classes is rejected; absence of a detector class does not prove
that there were zero vehicles of that type.

## Validation status

The contract tests cover repeated detections, class flicker, duplicate rows,
empty intervals, empty input, malformed IDs/classes/timestamps, incorrect totals,
missing intervals, and timestamp alignment. Mock data can validate software
behavior, not accuracy on real traffic. The existing 20-row sample has unknown
provenance. Real-log validation remains pending until Person A supplies a log.
