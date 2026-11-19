# Rush-hour intersection monitoring and forecasting

## Scope

Start with one fixed camera at one signalized Vietnamese intersection. Measure density by approach and in the junction center, forecast density 5 minutes ahead first, and flag wrong-way and unusually fast vehicles for review. Treat 15- and 30-minute forecasts as additional experiments after real-data evaluation is feasible. Use the existing pilot camera handoff to verify tracker and dashboard integration while collecting intersection footage. The saved pilot camera crossings are flow measurements and its real-data report marks it as insufficient for forecast training.

## Design

One timestamped YOLOv8s and ByteTrack stream feeds three outputs: per-zone density and queue measures, density forecasts, and vehicle alerts. Use broad approach polygons before introducing lane-level geometry. At each sample, count each active ID once in the zone containing its estimated road contact point. Divide by surveyed ground area for vehicles per 100 m². For a fixed zone with unknown area, label the result vehicles present. Track class composition and stopped vehicle count separately. Mark unavailable observations as missing.

Use signal phase information where visible or available. Summarize dwell time and queues remaining at the end of green if the full approach is observable. For speed, score one estimate per comparable vehicle over the same stretch, using recent peers traveling in the same direction and making a comparable movement. Keep the peer baseline internal and surface the flagged vehicle with its evidence.

## Sequence and ownership

Member A leads footage geometry, tracking and alert rules. Member B leads density aggregation, forecasting and dashboard integration. Both label and verify footage. Start collection immediately while testing the existing handoff. See [task checklist](todo.md) for dependencies and completion checks.

## Evaluation limits

Separate calibration, tuning and final evaluation by recording session or day. Track errors by zone, class, signal phase and crowding, including occluded motorcycles. Publish the sample sizes and limitations. Camera-specific rules need recalibration after a viewpoint change. A speed outlier is a candidate for review. Verify alerts against independent labels and report measured processing time on the demo machine.
