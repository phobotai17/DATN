# Vehicle counts by zone on the pilot video

Run from the workspace root with .venv/Scripts/python.exe -B person_b/scripts/measure_pilot_camera_density.py.

The script samples the archived tracks once per second and assigns each unique track using its box bottom-center. The polygons cover the interior roadway, using the visible center markings as the shared boundary. Zone labels describe road sides. Individual travel direction does not affect assignment. Ground area is unknown, so values are vehicles present per fixed zone. Frames absent from the tracking log are treated as unavailable because the track rows alone cannot prove a frame was processed. All 1,545 requested sample frames had track records. Each zone has 155 windows, including a final five-sample window.

Visual spot check of counts (toward-side, away-side) at 45, 120, 600 and 900 seconds gave (2,1), (3,0), (1,0) and (1,2), consistent with the exported samples. The second motorcycle on the toward side at 45 seconds is close to the outer boundary. These are four convenience frames, not a held-out accuracy estimate. Ground area, crowded-frame accuracy and fresh inference remain to be checked.
