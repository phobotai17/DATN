# Drive source preparation

Forecast target: line-crossing counts per complete five-minute interval, per camera, line and direction. Classes: motorbike, car, truck, bus. Observed-track counts are not the forecasting target.

Source: https://drive.google.com/drive/folders/194pi0dANgFZBJ5JwCOzOdWYg7sWG_31t
Inventory: data/drive_source/inventory.jsonl contains 475 metadata entries from 18 camera folders in sections 02 and 03. Section 01 accident data was excluded. Files are mostly raw videos, not counts.

Pending preparation:
- Download videos and inspect duration, continuity and camera view.
- Confirm recording times. Filename dates are provisional; Drive upload times and ACC Export names do not prove capture times.
- Configure and verify a counting line per camera before extracting events.
- Deduplicate suspected copies, especially the two Lang Ha - Thai Ha folders.
- Exclude zero-byte files. AVE recordings require compatible decoding; executable players are not data.
- Aggregate only complete observed intervals. Keep gaps missing rather than zero.
- Keep cameras/sessions separate; never create forecasting windows across missing periods.

Urban filenames suggest morning/noon/evening samples on different days. Continuous five-minute coverage remains unverified. Inventory preparation is complete; video extraction and forecasting tables are not yet complete.
