"""Camera profiles, calibration proposals and traffic measurement results."""
import json
from pathlib import Path
import sys
import cv2
import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.traffic_analytics import TrafficAnalytics, validate_profile
from src.gate_discovery import propose_gates

ALERT_LABELS = {
    'calibrated_wrong_way': 'Có dấu hiệu đi ngược chiều',
    'zone_wrong_way': 'Có dấu hiệu đi ngược chiều',
    'abrupt_turn': 'Dangerous',
    'relative_speed': 'Nhanh bất thường so với xe lân cận',
    'relative_slow': 'Chậm bất thường so với xe lân cận',
}


def camera_profile(size, calibrated=False):
    if calibrated:
        return validate_profile(json.loads((ROOT/'results/cam5_density/zones.json').read_text()))
    w, h = map(int, size)
    return {'frame_size': [w, h], 'zones': {'visible_area': [[0, 0], [w-1, 0], [w-1, h-1], [0, h-1]]}}


def render_settings(*, realtime=False):
    with st.expander('Vùng đo và ngưỡng cảnh báo', expanded=False):
        if realtime:
            st.caption('Mặc định đếm xe trong toàn khung hình. Dán cấu hình camera để chia vùng đo.')
        else:
            st.caption('Cam5 có hai vùng đo theo hai hướng đường. Video từ camera khác mặc định đếm xe trong toàn khung hình.')
        profile_text = st.text_area(
            'Cấu hình camera JSON (tùy chọn)', key='camera_profile_json',
            placeholder='Mở tệp JSON và dán nội dung vào đây',
            help='Để trống để dùng vùng mặc định. frame_size là [chiều rộng, chiều cao] của video gốc; zones chứa các đa giác vùng đo theo tọa độ pixel.',
        )
        template = json.dumps(camera_profile((1920, 1080), True), indent=2)
        st.download_button('Tải mẫu cấu hình Cam5', template, file_name='camera_profile.json', mime='application/json')
        custom = None
        if profile_text.strip():
            try:
                custom = validate_profile(json.loads(profile_text.strip().removeprefix('\ufeff')))
                st.success(f"Đã đọc {len(custom['zones'])} vùng đo")
            except (ValueError, TypeError, KeyError) as exc:
                st.error(f'Cấu hình không hợp lệ: {exc}')
                return None
        min_peers = st.number_input(
            'Số xe cùng loại tối thiểu để so sánh', 3, 30, 5,
            help='Mặc định cần ít nhất 5 xe khác cùng loại, ở gần, cùng vùng và cùng hướng. Nếu thiếu xe phù hợp, hệ thống bỏ qua so sánh tốc độ.',
        )
        persistence = st.number_input(
            'Thời gian duy trì bất thường (giây)', .3, 5., 1., .1,
            help='Mặc định dấu hiệu phải kéo dài ít nhất 1 giây theo thời gian trong video. Áp dụng cho tốc độ tương đối và ngược chiều theo hướng khai báo trong vùng.',
        )
        ratio = st.number_input(
            'Tỷ lệ tốc độ so với trung vị', 1.2, 5., 1.8, .1,
            help='Trung vị là tốc độ ở giữa của nhóm so sánh. Với hệ số 1,8, hệ thống xét nhanh hơn 1,8 lần hoặc chậm hơn 1/1,8 lần, rồi kiểm tra thêm độ chênh lệch và độ phân tán.',
        )
        st.caption('Tốc độ được đo bằng pixel/giây. Sau khi hiệu chỉnh mặt đường bằng homography, tốc độ được ước tính bằng km/h.')
        with st.expander('Các trường tùy chọn trong JSON'):
            st.markdown(
                '- `homography` là ma trận 3 × 3 chuyển tọa độ ảnh sang mét trên mặt đường.\n'
                '- `directions` khai báo hướng hợp lệ cho từng vùng để kiểm tra ngược chiều. '
                'Chỉ nhập hướng đã đối chiếu với quy định tại vị trí camera.\n'
                '- `parking_zones` là các đa giác lề đường tính theo pixel, có cùng định dạng với `zones`. Xe đứng yên ít nhất 3 giây tại đó được đánh dấu PARKING.\n'
                '- `entry_gates` và `exit_gates` là các đa giác đánh dấu cổng vào và ra, '
                'dùng để đếm lượt xe đi từ cổng này sang cổng khác.'
            )
    return {'profile': custom, 'min_peers': int(min_peers), 'persistence': persistence, 'speed_ratio': ratio}


def draw_analytics(frame, engine, measurement):
    for name, poly in engine.polygons['zones'].items():
        cv2.polylines(frame, [poly.astype(np.int32)], True, (0, 210, 255), 2)
        xy = tuple(poly[0].astype(int))
        count = next(z['total'] for z in measurement['zones'] if z['zone'] == name)
        cv2.putText(frame, f'{name}: {count}', xy, cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 210, 255), 2)
    for kind, color in [('entry_gates', (80, 240, 80)), ('exit_gates', (255, 120, 80))]:
        for name, poly in engine.polygons[kind].items():
            cv2.polylines(frame, [poly.astype(np.int32)], True, color, 2)
    active = {a['track_id'] for a in engine.alerts if measurement['zones'][0]['time_s']-a['time_s'] <= 3}
    for row in measurement['tracks']:
        if row['parked'] or row['track_id'] in active:
            label = 'PARKING' if row['parked'] else 'CHECK'
            cv2.putText(frame, f"{label} #{row['track_id']}", (int(row['x']), int(row['y'])),
                        cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 0, 255), 2)
    return frame


def zone_forecast(zones):
    return zones[zones.time_s >= zones.time_s.max() - 60].groupby('zone').total.mean()


def render_measurements(result, key):
    st.subheader('Số xe hiện diện theo vùng')
    zones = pd.DataFrame(result.get('zone_samples', []))
    if zones.empty:
        st.info('Chưa có số liệu vùng.')
        return
    st.line_chart(zones.pivot(index='time_s', columns='zone', values='total'),
                  x_label='Giây từ đầu video', y_label='Xe hiện diện', alt='Số xe theo vùng qua thời gian')
    st.caption('Mẫu đầu tiên mỗi giây video; xe dừng vẫn được đếm. Đây là số xe quan sát được, chưa chuẩn hóa theo diện tích.')
    st.dataframe(zones.groupby('zone')[['total', 'stopped']].mean().rename(columns={
        'total': 'Xe hiện diện trung bình', 'stopped': 'Xe dừng ≥2 giây trung bình'}), alt='Trung bình số xe hiện diện và dừng')
    recent = zone_forecast(zones)
    st.write('Dự báo mật độ 5 phút tới theo số xe hiện diện trong mỗi vùng')
    st.dataframe(recent.rename('Xe hiện diện dự báo').to_frame(), alt='Dự báo cơ sở theo vùng')
    st.caption('Dự báo cơ sở giữ mức trung bình của tối đa 60 giây cuối video. Cần kiểm tra sai số trên dữ liệu thực có nhãn.')
    alerts = pd.DataFrame(result.get('analytics_alerts', []))
    calibrated_alerts = result.get('alerts', pd.DataFrame())
    if not calibrated_alerts.empty:
        alerts = pd.concat([alerts, calibrated_alerts[['time_s', 'track_id', 'loai']]
                            .assign(event='calibrated_wrong_way')], ignore_index=True)
    st.subheader('Cảnh báo hành vi cần xác nhận')
    if not result.get('calibrated') and not result.get('profile', {}).get('directions'):
        st.caption('Để phát hiện ngược chiều, chọn đúng góc Cam5 hoặc khai báo hướng hợp lệ trong cấu hình camera.')
    if alerts.empty:
        st.info('Không có cảnh báo đủ điều kiện. Thiếu xe so sánh không có nghĩa là tốc độ an toàn.')
    else:
        alerts = alerts.sort_values('time_s').assign(canh_bao=lambda rows: rows.event.map(ALERT_LABELS))
        st.dataframe(alerts.assign(event=alerts.event.replace('abrupt_turn', 'Dangerous')),
                     hide_index=True, alt='Cảnh báo hành vi từ video')
        st.download_button('Tải CSV cảnh báo', alerts.to_csv(index=False).encode('utf-8-sig'),
                           file_name='traffic_alerts.csv', mime='text/csv', key=f'{key}_alerts')
    quality = result.get('quality_counts', {})
    st.caption('Chất lượng mẫu quỹ đạo: ' + ', '.join(f'{name}: {count}' for name, count in quality.items()))
    for name, rows in [('zone_counts', result['zone_samples']), ('motion_samples', result.get('motion_samples', [])),
                       ('movements', result.get('movements', []))]:
        table = pd.DataFrame(rows)
        if not table.empty:
            st.download_button(f'Tải {name}.csv', table.to_csv(index=False).encode('utf-8-sig'),
                               file_name=f'{name}.csv', mime='text/csv', key=f'{key}_{name}')
    movements = pd.DataFrame(result.get('movements', []))
    if not movements.empty:
        st.dataframe(movements.groupby(['entry', 'exit']).size().rename('Lượt di chuyển').reset_index(),
                     alt='Lượt xe từ cửa vào đến cửa ra')


def render_gate_proposals():
    st.subheader('Đề xuất cửa vào / cửa ra từ quỹ đạo')
    st.caption('Học ngoại tuyến từ log. Đây là đề xuất hình học để xem lại; không tự xác định hướng hợp pháp hay thay đổi vùng đo.')
    upload = st.file_uploader('Tracking CSV (bỏ trống để dùng Cam5)', type=['csv'], key='gate_log')
    w = st.number_input('Chiều rộng video nguồn', 100, 10000, 1920)
    h = st.number_input('Chiều cao video nguồn', 100, 10000, 1080)
    k = st.number_input('Số cửa cho mỗi nhóm vào / ra', 2, 9, 2)
    if st.button('Tạo đề xuất cửa'):
        try:
            log = pd.read_csv(upload if upload is not None else ROOT/'data/tuan4/data/tracking_log_full.csv',
                              dtype={'track_id': str})
            proposal = propose_gates(log, [w, h], int(k))
            p = camera_profile((w, h), upload is None and (w, h) == (1920, 1080))
            p.update({name: proposal[name] for name in ('entry_gates', 'exit_gates')})
            st.session_state.gate_proposal = {'profile': validate_profile(p), 'summary': proposal}
        except (ValueError, OSError, KeyError) as exc:
            st.error(str(exc))
    if saved := st.session_state.get('gate_proposal'):
        p = saved['profile']
        st.write(f"{saved['summary']['usable_tracks']} quỹ đạo được dùng")
        canvas = np.full((int(p['frame_size'][1]), int(p['frame_size'][0]), 3), 35, np.uint8)
        for kind, color in [('zones', (100, 100, 100)), ('entry_gates', (80, 230, 80)), ('exit_gates', (250, 150, 80))]:
            for name, vertices in p.get(kind, {}).items():
                poly = np.array(vertices, np.int32)
                cv2.polylines(canvas, [poly], True, color, 4)
                cv2.putText(canvas, name, tuple(poly[0]), cv2.FONT_HERSHEY_SIMPLEX, .8, color, 2)
        st.image(canvas, channels='BGR', alt='Sơ đồ cửa vào xanh lá và cửa ra xanh dương', width='stretch')
        st.warning('Kiểm tra các cửa trên video trước khi sử dụng. Không nối ID từ các đoạn ghi khác nhau; log có thể thêm segment_id.')
        st.download_button('Tải cấu hình đề xuất để kiểm tra', json.dumps(p, indent=2),
                           file_name='proposed_camera_profile.json', mime='application/json')
