"""Streamlit view for the calibrated video and logs delivered by Person A."""
from contextlib import closing, contextmanager, nullcontext
from math import ceil, isfinite
from hashlib import sha256
from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from subprocess import DEVNULL, PIPE, Popen, TimeoutExpired, run
import os
from tempfile import TemporaryDirectory
from time import monotonic
from collections import Counter
from threading import RLock
import json

import pandas as pd
import streamlit as st

from components.alert_table import render_alert_table
from components.flow_candles import counts_by_elapsed, flow_candles, video_time
from components.analytics_panel import (TrafficAnalytics, camera_profile, draw_analytics,
    render_settings, render_measurements, render_gate_proposals)

CLASSES = {'xe_may': 'motorbike', 'xe_hoi': 'car', 'xe_tai': 'truck', 'bus': 'bus'}
DIRECTIONS = {'toward': 'Về phía camera', 'away': 'Ra xa camera'}
EVENT_FIELDS = ['timestamp', 'track_id', 'class_name', 'direction']
PROCESSING_HEIGHTS = [480, 720, 1080]
FRAME_STRIDES = [1, 2, 3, 4]
HIDE_CONSOLE = 0x08000000 if os.name == 'nt' else 0
DEMO_VIDEO = Path('demo/clip_ngc.mp4')
VIDEO_SUFFIXES = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}


def inference_device():
    import torch
    return 'cuda:0' if torch.cuda.is_available() else 'cpu'


@st.cache_resource(scope='session', show_spinner='Khởi động bộ nhận diện…')
def detector_resource(model_path):
    import numpy as np
    from ultralytics import YOLO
    model = YOLO(model_path)
    device = inference_device()
    model.predict(np.zeros((384, 640, 3), dtype=np.uint8), imgsz=(384, 640),
                  device=device, quantize=16 if device != 'cpu' else None, verbose=False)
    return model, RLock()


def video_info(video):
    import cv2

    with closing_capture(video, cv2) as capture:
        fps = capture.get(cv2.CAP_PROP_FPS)
        total_frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if not capture.isOpened() or not isfinite(fps) or fps <= 0 or not isfinite(total_frames) or total_frames <= 0:
            raise ValueError('Không đọc được thông tin video.')
        size = (capture.get(cv2.CAP_PROP_FRAME_WIDTH), capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    return fps, total_frames, size


@lru_cache(maxsize=1)
def nvenc_available(ffmpeg):
    """Check encoder and driver support before streaming any frames."""
    try:
        result = run(
            [ffmpeg, '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
             'color=s=320x240:r=24', '-frames:v', '1', '-c:v', 'h264_nvenc',
             '-preset', 'p1', '-f', 'null', '-'],
            stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL, timeout=8,
            creationflags=HIDE_CONSOLE,
        )
    except (OSError, TimeoutExpired):
        return False
    return result.returncode == 0


@contextmanager
def annotated_encoder(path, size, fps, device):
    from imageio_ffmpeg import get_ffmpeg_exe

    ffmpeg = get_ffmpeg_exe()
    width, height = size
    if device.startswith('cuda') and nvenc_available(ffmpeg):
        codec = ['-c:v', 'h264_nvenc', '-preset', 'p1', '-tune', 'll', '-cq', '25', '-bf', '0']
    else:
        codec = ['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '25', '-threads', '2']
    command = [
        ffmpeg, '-nostdin', '-loglevel', 'error', '-y',
        '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{width}x{height}',
        '-r', str(fps), '-i', '-', '-an', *codec,
        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(path),
    ]
    with Popen(command, stdin=PIPE, stdout=DEVNULL, creationflags=HIDE_CONSOLE) as encoder:
        try:
            yield encoder.stdin
        finally:
            try:
                encoder.stdin.close()
            finally:
                if encoder.wait():
                    raise RuntimeError('Không thể mã hóa video đã nhận diện.')



def run_video(package: Path, video: Path, seconds: int | None, preview, status, chart,
              *, calibrated: bool, record: bool, clock0: str, processing_height: int = 480, stride: int = 2,
              analytics_settings=None, model_loader=None):
    import cv2
    fps, total_frames, size = video_info(video)
    if calibrated and size != (1920, 1080):
        raise ValueError('Cấu hình vạch đếm yêu cầu video 1920×1080 của camera demo.')
    settings = dict(analytics_settings or {})
    profile = settings.pop('profile', None) or camera_profile(size, calibrated)
    if tuple(profile['frame_size']) != tuple(size):
        raise ValueError('Kích thước cấu hình camera phải trùng video; hãy hiệu chỉnh lại tọa độ.')
    analytics = TrafficAnalytics(profile, **settings)
    spec = spec_from_file_location('person_a_pipeline', package / 'src/traffic_pipeline.py')
    pipeline_module = module_from_spec(spec)
    spec.loader.exec_module(pipeline_module)
    duration = total_frames / fps
    limit = duration if seconds is None else min(duration, seconds)
    status.caption(f'Thời lượng video {video_time(duration)} · Đang tải mô hình')
    events, alerts = [], []
    zone_samples, motion_samples, quality_counts = [], [], Counter()
    last_sample_second = -1
    started = monotonic()
    next_preview = started
    frame_count = 0
    first_frame_at = None
    candles_drawn = 0
    visible_total = 0
    recording = None
    scale = min(1, processing_height / size[1], (processing_height * 16 / 9) / size[0])
    output_size = tuple(max(2, int(dimension * scale) // 2 * 2) for dimension in size)
    # Keep 480p playback while using a smaller detector input for the fast mode.
    inference_scale = min(1, 640 / max(output_size)) if processing_height == 480 else 1
    model_size = tuple(max(32, ceil(dimension * inference_scale / 32) * 32)
                       for dimension in reversed(output_size))
    inference_size = tuple(max(2, round(dimension * inference_scale)) for dimension in output_size)
    load_model = model_loader if model_loader is not None else detector_resource
    model, model_lock = load_model(str(package / 'models/best_v2.pt'))
    with model_lock, TemporaryDirectory(prefix='traffic_tracker_') as temp:
        pipeline = pipeline_module.TrafficPipeline(
            str(package / 'models/best_v2.pt'), clock0=clock0,
            cfg={'wrongway_enabled': calibrated, 'count_line_y': 600 if calibrated else int(size[1] * 600 / 1080),
                 'imgsz': model_size, 'inference_size': inference_size, 'device': inference_device(),
                 'half': True, 'stride': stride},
            tracker_yaml=str(Path(temp) / 'bytetrack.yaml'),
            model=model,
        )
        frame_limit = max(1, ceil(limit * fps / stride))
        movie_path = Path(temp) / 'annotated.mp4'
        encoder = annotated_encoder(movie_path, output_size, fps / stride, pipeline.device) if record else nullcontext()
        with encoder as writer:
            with closing(pipeline.run(str(video), max_frames=frame_limit, annotate=True)) as frames:
                for frame_count, result in enumerate(frames, 1):
                    measurement = analytics.update(result['time_s'], result['tracks'])
                    quality_counts.update(row['quality'] for row in measurement['tracks'])
                    if int(result['time_s']) != last_sample_second:
                        zone_samples.extend(measurement['zones'])
                        motion_samples.extend(dict(time_s=result['time_s'], **row) for row in measurement['tracks'])
                        last_sample_second = int(result['time_s'])
                    result['annotated'] = draw_analytics(result['annotated'], analytics, measurement)
                    visible_total += len(result['tracks'])
                    events.extend(result['new_events'])
                    alerts.extend(result['new_alerts'])
                    now = monotonic()
                    if first_frame_at is None:
                        first_frame_at = now
                    refresh = now >= next_preview or frame_count == frame_limit
                    if refresh or writer is not None:
                        frame = result['annotated']
                        if frame.shape[1::-1] != output_size:
                            frame = cv2.resize(frame, output_size, interpolation=cv2.INTER_AREA)
                        if writer is not None:
                            writer.write(frame.tobytes())
                        if refresh:
                            preview.image(frame, channels='BGR', width='stretch', alt='Khung hình với hộp nhận diện phương tiện')
                            status.caption(f"{pipeline.device} · {frame_count / (now - started):.1f} FPS xử lý · "
                                           f"{len(events)} lượt qua vạch · {len(alerts)+len(analytics.alerts)} cảnh báo · "
                                           + ' / '.join(f"{z['zone']}: {z['total']} xe" for z in measurement['zones']))
                            next_preview = now + 0.25
                    complete_candles = int(result['time_s'] // 10)
                    if complete_candles > candles_drawn:
                        render_demo_candles(chart, events, result['time_s'])
                        candles_drawn = complete_candles
        if record and frame_count:
            recording = movie_path.read_bytes()
    if frame_count == 0:
        raise ValueError('Video không có khung hình đã xử lý.')
    processing_seconds = monotonic() - first_frame_at
    covered = min(limit, result['time_s'] + stride / fps)
    if candles_drawn == 0 or int(covered // 10) > candles_drawn:
        render_demo_candles(chart, events, covered)
    crossings = pd.DataFrame([
        {'timestamp': row['timestamp'], 'track_id': row['track_id'],
         'class_name': CLASSES[row['loai']], 'direction': row['huong']}
        for row in events
    ], columns=EVENT_FIELDS)
    return {'crossings': crossings, 'alerts': pd.DataFrame(alerts), 'device': pipeline.device,
            'frames': frame_count, 'elapsed': monotonic() - started,
            'processing_fps': (frame_count - 1) / max(processing_seconds, 1e-9),
            'sample_fps': fps / stride, 'stride': stride,
            'last_frame': cv2.resize(result['annotated'], output_size, interpolation=cv2.INTER_AREA),
            'position': covered, 'events': events, 'duration': duration,
            'visible_average': visible_total / frame_count, 'recording': recording,
            'calibrated': calibrated, 'zone_samples': zone_samples, 'motion_samples': motion_samples,
            'analytics_alerts': analytics.alerts, 'movements': analytics.movements,
            'quality_counts': dict(quality_counts), 'profile': profile}


def run_demo(package: Path, seconds: int | None, preview, status, chart, *, stride: int = 2,
             processing_height: int = 480, analytics_settings=None):
    return run_video(package, package / DEMO_VIDEO, seconds, preview, status, chart,
                     calibrated=True, record=False, clock0='2026-04-09 13:47:00', stride=stride,
                     processing_height=processing_height, analytics_settings=analytics_settings)


def select_stride(key):
    return st.selectbox('Bỏ qua khung hình', FRAME_STRIDES, index=2 if inference_device() != 'cpu' else 3,
                        format_func=lambda stride: (
                            'Bỏ 0 khung (xử lý mọi khung)' if stride == 1
                            else f'Bỏ {stride - 1} khung giữa hai lần nhận diện'
                        ),
                        help='Máy mạnh có thể chọn 0–1. Nếu xử lý chậm, hãy thử 2–3. '
                             'Bỏ nhiều khung có thể bỏ sót xe hoặc cảnh báo.',
                        key=key)


def render_upload(package, analytics_settings=None):
    processing_height = st.selectbox('Độ phân giải tối đa', PROCESSING_HEIGHTS,
                                     format_func=lambda value: f'{value}p', key='upload_processing_height')
    stride = select_stride('upload_stride')
    same_camera = st.checkbox('Video từ đúng góc camera 0511.vn đã hiệu chỉnh (1920 × 1080)')
    local_dir = os.environ.get('TRAFFIC_VIDEO_DIR')
    use_local = bool(local_dir) and st.toggle('Chọn video từ thư mục trên máy chạy ứng dụng')
    source = uploaded = None
    if use_local:
        try:
            folder = Path(local_dir).resolve(strict=True)
            videos = set()
            for path in folder.iterdir():
                if path.suffix.lower() not in VIDEO_SUFFIXES:
                    continue
                resolved = path.resolve()
                if resolved.is_relative_to(folder) and resolved.suffix.lower() in VIDEO_SUFFIXES and resolved.is_file():
                    videos.add(resolved)
            videos = sorted(videos, key=lambda path: str(path.relative_to(folder)).casefold())
            source = st.selectbox('Video trong thư mục', videos, index=None,
                                  format_func=lambda path: str(path.relative_to(folder)))
            if source is not None:
                stat = source.stat()
        except (OSError, RuntimeError):
            st.error('Không đọc được thư mục video hoặc tệp đã chọn.')
            return
        st.caption('Xử lý trực tiếp từ ổ đĩa và hiển thị khung hình cuối, biểu đồ và số liệu.')
        if source is None:
            if not videos:
                st.info('Thư mục chưa có video được hỗ trợ.')
            st.session_state.pop('upload_job', None)
            return
        name = source.name
        identity = ('local', source, stat.st_size, stat.st_mtime_ns)
        size = stat.st_size
    else:
        uploaded = st.file_uploader('Kéo thả video để bắt đầu nhận diện',
                                    type=sorted(VIDEO_SUFFIXES), key='handoff_upload')
        if uploaded is None:
            st.session_state.pop('upload_job', None)
            return
        name, size = uploaded.name, uploaded.size
        with uploaded.getbuffer() as content:
            identity = ('upload', name, sha256(content).hexdigest())
    st.subheader(name)
    suffix = Path(name).suffix.lower()
    if suffix not in VIDEO_SUFFIXES or size == 0:
        st.error('Video trống hoặc định dạng không được hỗ trợ.')
        return
    key = (identity, same_camera, processing_height, stride, json.dumps(analytics_settings, sort_keys=True))
    preview, status, chart = st.empty(), st.empty(), st.empty()
    job = st.session_state.get('upload_job', {})
    rerun = job.get('key') != key
    if rerun:
        job = {'key': key}
        st.session_state.pop('upload_job', None)
        try:
            with (TemporaryDirectory(prefix='traffic_upload_') if uploaded is not None else nullcontext()) as temp:
                if uploaded is not None:
                    source = Path(temp) / ('input' + suffix)
                    with uploaded.getbuffer() as content, source.open('wb') as target:
                        target.write(content)
                job['result'] = run_video(package, source, None, preview, status, chart,
                                          calibrated=same_camera, record=uploaded is not None, clock0='2000-01-01 00:00:00',
                                          processing_height=processing_height, stride=stride, analytics_settings=analytics_settings)
        except (ImportError, OSError, ValueError, RuntimeError, KeyError) as error:
            job['error'] = str(error)
        st.session_state.upload_job = job
    status.empty()
    if 'error' in job:
        st.error(f"Không xử lý được video: {job['error']}")
        if st.button('Thử lại', key='retry_video_upload'):
            st.session_state.pop('upload_job', None)
            st.rerun()
        return
    result = job.get('result')
    if result is None:
        return
    if result['recording']:
        preview.video(result['recording'], format='video/mp4', alt='Video đã xử lý với hộp nhận diện phương tiện')
    else:
        preview.image(result['last_frame'], channels='BGR', width='stretch', alt='Khung cuối với hộp nhận diện phương tiện')
    if not rerun:
        render_demo_candles(chart, result['events'], result['position'])

    st.caption(f"Thời lượng video {video_time(result['duration'])} · {result['device']} · "
               f"{result['processing_fps']:.1f} FPS xử lý sau khởi động · "
               f"{result['sample_fps']:.1f} FPS nhận diện để theo kịp video")
    recorded_minutes = result['position'] / 60
    a, b, c = st.columns(3)
    a.metric('Lượt qua vạch', len(result['events']))
    b.metric('Xe hiện diện trung bình toàn khung', f"{result['visible_average']:.1f} xe")
    c.metric('Lượt qua vạch dự báo 5 phút tới', f"{len(result['events']) * 5 / recorded_minutes:.0f}")
    st.caption('Dự báo lượt qua vạch giữ nguyên lưu lượng trung bình. Số xe hiện diện và lưu lượng qua vạch là hai phép đo riêng.')
    st.caption('Mỗi nến tóm tắt 10 giây qua các lượt đếm 2 giây. Vạch ngang nằm tại 55,6% chiều cao khung hình.')
    if not result['crossings'].empty:
        st.download_button('Tải sự kiện qua vạch', result['crossings'].to_csv(index=False).encode('utf-8'),
                           file_name='video_crossings.csv', mime='text/csv', key='upload_crossings')
    render_measurements(result, 'upload')



def render_demo_candles(container, events, covered):
    samples = counts_by_elapsed(events, covered, sample_seconds=2)
    if len(samples) < 5:
        container.info('Cần đủ 10 giây video để hiển thị nến đầu tiên.')
        return
    figure = flow_candles(samples, 5, elapsed_axis=True)
    figure.update_yaxes(title='Lượt qua vạch / 2 giây', rangemode='tozero')
    container.plotly_chart(figure, width='stretch', key=f'video_flow_{len(samples) // 5}')


@contextmanager
def closing_capture(path, cv2):
    capture = cv2.VideoCapture(str(path))
    try:
        yield capture
    finally:
        capture.release()


def render_handoff(root):
    package = root / 'data/goi_ban_giao_B'
    import torch
    device = inference_device()
    label = torch.cuda.get_device_name(0) if device != 'cpu' else 'CPU'
    st.caption(f'Thiết bị tự động: {label} · {"FP16" if device != "cpu" else "FP32"}')
    analytics_settings = render_settings()
    if analytics_settings is None:
        return
    upload, demo, recorded, gates = st.tabs(['Tải video', 'Chạy clip demo', 'Số liệu bàn giao', 'Đề xuất cửa vào / ra'])
    with upload:
        render_upload(package, analytics_settings)
    with demo:
        video = package / DEMO_VIDEO
        st.subheader(video.name)
        if video.is_file():
            try:
                fps, total_frames, _ = video_info(video)
                st.caption(f'Thời lượng video {video_time(total_frames / fps)}')
            except (ImportError, ValueError):
                st.caption('Thời lượng hiển thị trong trình phát.')
            st.video(str(video), format='video/mp4', alt=f'Video giao thông {video.name}')
        else:
            st.warning(f'Không tìm thấy video {video.name}.')
        stride = select_stride('demo_stride')
        height = st.selectbox('Độ phân giải tối đa', PROCESSING_HEIGHTS,
                              format_func=lambda value: f'{value}p', key='demo_processing_height')
        seconds = st.selectbox('Đoạn video cần xử lý', [None, 10, 30],
                               format_func=lambda value: 'Toàn bộ clip' if value is None else f'{value} giây đầu')
        run_requested = st.button('Chạy nhận diện', type='primary', disabled=not video.is_file())
        preview, status = st.empty(), st.empty()
        st.caption('Mỗi nến là 10 giây. Mở và đóng là lượt qua vạch trong 2 giây đầu và cuối, còn cao và thấp là giá trị lớn nhất và nhỏ nhất trong nến.')
        chart = st.empty()
        settings = (seconds, stride, height, json.dumps(analytics_settings, sort_keys=True))
        if st.session_state.get('handoff_demo_settings') != settings:
            st.session_state.pop('handoff_result', None)
            st.session_state.handoff_demo_settings = settings
        if run_requested:
            st.session_state.pop('handoff_result', None)
            try:
                st.session_state.handoff_result = run_demo(package, seconds, preview, status, chart, stride=stride,
                                                           processing_height=height,
                                                           analytics_settings=analytics_settings)
            except (ImportError, OSError, ValueError, RuntimeError, KeyError) as error:
                st.error(f'Không chạy được pipeline: {error}')
        if result := st.session_state.get('handoff_result'):
            crossings = result['crossings']
            preview.image(result['last_frame'], channels='BGR', width='stretch', alt='Khung hình cuối với hộp nhận diện phương tiện')
            status.empty()
            if not run_requested:
                render_demo_candles(chart, result['events'], result['position'])
            st.caption(f"Lần chạy gần nhất · {result['device']} · {result['frames']} khung hình · {result['elapsed']:.1f} giây xử lý")
            left, right = st.columns(2)
            left.metric('Lượt qua vạch', len(crossings))
            right.metric('Cảnh báo cần xác nhận', len(result['alerts']) + len(result['analytics_alerts']))
            if not crossings.empty:
                st.dataframe(crossings, hide_index=True)
                st.download_button('Tải sự kiện qua vạch', crossings.to_csv(index=False).encode('utf-8'),
                                   file_name='demo_video_crossings.csv', mime='text/csv')
            render_measurements(result, 'demo')
    with recorded:
        try:
            counts = pd.read_csv(package / 'data/counts_per_10s_full.csv', parse_dates=['bin_start'])
            history = pd.read_csv(package / 'data/wrongway_alerts_final.csv')
            elapsed = (counts.bin_start - counts.bin_start.iloc[0]).dt.total_seconds()
            samples = (pd.Series(counts.tong.to_numpy(), index=elapsed)
                       .where(counts.do_phu.eq(1).to_numpy())
                       .reindex(range(0, int(elapsed.max()) + 1, 10)))
            st.subheader('Lưu lượng trong bản ghi cam5')
            st.caption('Mỗi nến là một phút, tổng hợp từ sáu lượt đếm 10 giây. Chỉ hiển thị phút có đủ thời lượng.')
            figure = flow_candles(samples, 6, elapsed_axis=True)
            figure.update_yaxes(title='Lượt qua vạch / 10 giây', rangemode='tozero')
            st.plotly_chart(figure, width='stretch', key='recorded_flow')
            st.subheader('Lịch sử cảnh báo cần xác nhận')
            render_alert_table(history)
        except (OSError, ValueError, KeyError) as error:
            st.error(f'Không đọc được số liệu bàn giao: {error}')
    with gates:
        render_gate_proposals()
