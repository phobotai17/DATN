# Intersection project tasks

| # | Lead | Task | Depends on | Done when |
|---|---|---|---|---|
| 1 | Both | Select a fixed, elevated intersection view and collect continuous footage over multiple rush-hour sessions plus an off-peak comparison. Record timestamps, coverage gaps and visible signal phases. Reserve entire sessions for final testing. | None | A clip inventory documents usable approaches, signal visibility, session splits and camera setup. |
| 2 | A | Smoke-test the pilot camera checkpoint end to end. Export timestamped frame-level tracks for the new junction and audit class labels, occlusion, ID jumps and gaps. | 1 for new footage | The saved clip runs through the handoff, and exported tracks can be traced to annotated frames. pilot camera startup can be checked in parallel with 1. |
| 3 | A + B | Draw approach and center polygons. Calibrate visible road geometry where possible and document permitted travel directions. Label sample frames and full signal cycles across crowding levels. | 1 | Zone overlays align on footage and a manual reference set includes class counts, queue or dwell observations and excluded areas. |
| 4 | B | Build per-zone counts and density series, including vehicle classes and coverage. Add a dashboard replay showing accumulation and stopped vehicles. | 2, 3 | Hand-count comparisons report count error and bias by zone and crowding. Missing footage remains missing and each ID contributes once per sample. |
| 5 | A | Port wrong-way detection to clearly directed approaches. Require sustained opposing movement and account for legal turns and tracker jumps. | 2, 3 | Replay overlays and blinded event labels support event-level precision, recall and false alarms per hour. |
| 6 | A | Estimate speed on a calibrated approach stretch and flag sustained high outliers against recent comparable vehicles. Compare mean-based and median-based peer rules, excluding the scored vehicle. | 2, 3 | Speed is checked against reference traversal times or another independent measurement. Scoring skips sparse baselines and unreliable tracks. Report event metrics and reviewed examples on held-out clips. |
| 7 | B | Forecast the actual zone density series. Start with persistence and a recent average. Compare a candidate model on identical forecast origins and test days. | 4 and sufficient continuous data | Report zone-level MAE and RMSE at +5 minutes. Add +15 and +30 minutes when coverage supports them. Log every input as available by forecast time. |
| 8 | Both | Integrate dashboard density, forecasts and alert replay, then run a continuous demo on the defense machine. | 4–7 | One recording feeds all three outputs. Record FPS, alert delay, memory and run duration. Save a reproducible run command, config and evidence clips. |

## Checkpoints

- [ ] After 1–3, review footage coverage, tracker quality, and label definitions before tuning.
- [ ] After 4–6, review density errors on crowded frames and false alerts around legal turns and heavy occlusion.
- [ ] After 7–8, reproduce a full replay and match thesis claims to held-out measurements. If the real series remains too short, report the measured density and alerts and describe the forecast as a separate demonstration.

## Assignment-aligned checklist — 15 November 2026

This checklist expands the tasks above using VLU.ĐAKLTN.08.docx and the agreed intersection scope. A leads computer vision and trajectory logic. B leads time series and dashboard work. Both own annotation and evaluation. The assignment gives 15 weeks in total; remaining time has not been confirmed.

### Existing starting points

- [x] Four-class checkpoint and tracking pipeline available in the handoff.
- [x] Three-frame CUDA startup smoke test completed on the short pilot camera demo.
- [x] Wrong-way threshold candidates compared on archived demo tracks. Candidate start angle 160 degrees, continuation angle 135 degrees, persistence 0.6 seconds. Six identifiable positives matched; seventh reported case lacks an identified label.
- [x] pilot camera zone-count script, 1-second samples and 10-second chart generated from archived tracks.
- [x] Four sampled video frames visually checked against zone counts.
- [x] Synthetic LSTM/GRU experiment and comparison artifacts available.

These checks cover prototypes and saved-data experiments. Complete the validation items below before claiming performance on urban intersections.

### P0 — Define targets and prepare evaluation data

- [ ] **Both — Define the density target.** Fix polygons and sampling/aggregation intervals. Use vehicles present per fixed zone, or vehicles per 100 m² when area is measured. Define the future time window predicted. Agree with the adviser on how density and congestion are described. Done when the units, interval and forecast target are written and illustrated on a frame.
- [ ] **A — Collect fixed-camera intersection recordings.** Cover multiple continuous rush-hour sessions, an off-peak comparison and available lighting variation. Document timestamp reliability, camera position and gaps. Done when footage supports the chosen history and forecast horizon without crossing gaps.
- [ ] **Both — Split recordings before tuning.** Separate training, validation and test sessions. Exclude the short demo's overlapping interval from pilot camera evaluation. Done when every clip has one documented role.
- [ ] **Both — Prepare reference labels.** Label vehicle boxes, four classes and persistent identities on short representative clips for MOT evaluation. Label zone counts on frames and wrong-way events with onset times, plus ordinary traffic and legal turns. Done when labels are reviewed and ambiguous/occluded cases have an explicit convention.

### P1 — Detection and tracking

- [ ] **A — Evaluate the existing checkpoint at the junction.** Review missed motorcycles, class errors, false detections and ID switches by crowding and lighting. Done when representative annotated clips show where changes are needed.
- [ ] **A — Fine-tune where measured errors warrant it.** Keep test footage out of training and select thresholds on validation footage. Record checkpoint, training configuration and class mapping.
- [ ] **A — Export one synchronized tracking stream.** Include recording ID, frame, source time, vehicle ID, class, confidence and box/contact-point coordinates. Reset session state between recordings. Done when exports align with decoded frames at the selected stride.
- [ ] **A — Report MOTA and MOTP.** Use fixed matching rules and document MOTP distance/overlap convention. Report identity errors and sample sizes. Done when metrics reproduce from predictions and ground truth. Dependencies: reference labels and tracking export.

### P2 — Density measurement

- [ ] **B — Validate the existing pilot camera zone counter on broader samples.** Include boundaries, empty zones, parked vehicles and occlusion. Done when MAE and signed bias are reported beyond the four spot checks.
- [ ] **A + B — Configure intersection approach and center zones.** Document polygon boundaries, any overlap and visible coverage. Done when a reviewed overlay supports unambiguous counting.
- [ ] **B — Generate the continuous intersection density series.** Count each active vehicle once per sample and preserve class counts. Keep unavailable samples distinct from observed zeros. Done when exports match reviewed frames and include coverage flags.
- [ ] **B — Show current density in Streamlit.** Add zone overlays and history synchronized to source time. Done when a recording processed through the normal app entry point reproduces the exported series. Dependencies: validated geometry and aggregation.

### P3 — Wrong-way event detection

- [ ] **A — Reproduce the short pilot camera result with fresh inference.** Match actual vehicle episodes across tracker runs, including the unidentified seventh case where possible. Done when events and timestamps are manually reconciled.
- [ ] **A — Evaluate frozen thresholds on separate pilot camera footage.** Report precision, recall, false alerts per hour and delay with stated denominators.
- [ ] **A — Adapt permitted directions to intersection movements.** Handle legal turns and trajectory gaps. Define which approaches are covered. Done when ordinary turns and reviewed wrong-way examples are correctly assessed on validation clips.
- [ ] **A + B — Integrate event evidence.** Log one candidate per episode with camera, track, source time, reason and a reviewable frame or clip. Done when dashboard alerts map back to labeled events.
- [ ] **A — Evaluate on the held-out intersection set.** Freeze geometry and thresholds first. Report error cases and event sample counts. Dependencies: intersection labels and movement rules.

### P4 — Short-term density forecasting

- [ ] **B — Build windows from real density history.** Respect recording gaps and session boundaries. Fit preprocessing using training data only. Done when each prediction uses only information available at its forecast origin.
- [ ] **B — Establish persistence and recent-average baselines.** Use identical target windows and test origins for all methods.
- [ ] **B — Train and save at least one LSTM, GRU or TCN model.** Select model settings on validation sessions, reload the checkpoint and verify predictions.
- [ ] **B — Evaluate +5 minutes first.** This is a proposed first horizon. Add +15/+30 minutes if data and the agreed scope support them. Report MAE/RMSE by zone, rush-hour period and model. Handle zero density explicitly if reporting MAPE.
- [ ] **B — Connect forecasts to the dashboard.** Refresh forecasts using observed history and show their target time and zone. Done when a complete replay produces current density and future estimates from the same stream.

### P5 — Performance and final deliverables

- [ ] **Both — Measure baseline end-to-end performance.** Record hardware, resolution, stride, processed FPS, source-video speed, latency and memory. Separate startup time from steady processing.
- [ ] **A — Evaluate TensorRT or OpenVINO on the chosen hardware.** Compare output accuracy and runtime against the original model on the same clips. Retain the configuration that meets the agreed demo needs.
- [ ] **Both — Test continuous operation.** Exercise normal video upload/replay, selected live input if available, reruns, new recordings and decoder failures. Record run duration and resource usage.
- [ ] **Both — Prepare a reproducible demonstration.** Save dependencies, checkpoint/config references, startup instructions and a demo recording.
- [ ] **Both — Complete report and presentation.** Include architecture, data splits, density definition, detection/tracking and alert metrics, forecast results, runtime measurements and observed limitations.

### Extensions agreed in discussion

- [ ] **A — Peer-relative speed alerts.** Use comparable vehicles in the same direction/stretch, calibrated distance or explicit traversal-time units, and enough prior peers. Compare mean-based and median-based scoring, exclude the candidate from its reference and validate flags independently. This adds an alert type beyond the assignment's explicit wrong-way requirement.
- [ ] **A + B — Automatic zone proposals.** Compare road/marking detection with trajectory-based proposals. Review and save camera geometry before measuring density.
- [ ] **B — Model warmup on page open.** Reuse the loaded detector, reset tracking state per video and measure cold versus warm first-frame latency.

### Immediate work order

1. Confirm density target and collect intersection footage while validating the pilot camera prototype.
2. Create recording splits and reference annotations.
3. Complete fresh-inference density and wrong-way validation, then adapt them to the intersection.
4. Train a real-data forecast once the density history is adequate.
5. Integrate, benchmark and prepare the defense artifacts.
