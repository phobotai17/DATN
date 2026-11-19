# Extended source audit

32 video files exceed the connector's 256 MiB raw-download limit. Their URLs
are listed in data/drive_source/large_video_candidates.csv.

The accessible candidate 1307aXLAziibIW7_GeeJKgl-HCNr2y_Gd is an NB-LC AVI.
Its filename says ACC Export 2022-10-19, but its first visible recording timestamp
is 2022-Sep-21 01:00:00.007 PM (WIB). The image identifies Km 98+500, IC11,
Noi Bai - Lao Cai. Therefore the export filename is not a recording timestamp.
The container reports 600 FPS and 72,337 frames. These metadata must be checked
against visible timestamps before time-series generation. Duration is not yet
verified. Do not label this clip as a two-minute real-time recording based on
container playback duration alone.

Verified follow-up after complete download (262,464,284 bytes):
- Sequential decoding yielded 2,922 frames, despite header claiming 72,337.
- First visible timestamp: 13:00:00.007, 21 September 2022.
- Last visible timestamp: 13:02:00.569, same date.
- Visible elapsed recording time: 120.562 seconds.
- Header FPS (600) must NOT be used to timestamp sequentially decoded events.
- Random frame seeking was inconsistent; sequential decode completed to EOF.
- This recording provides no complete five-minute interval.

Conclusion: the larger accessible sample is still approximately two minutes.
No new eligible forecasting interval was obtained. The 32 files above the
connector limit remain uninspected; this audit does not establish their duration.
For such AVI exports, extract and validate the on-screen clock or recover reliable
presentation timestamps before converting detections into time-series counts.
