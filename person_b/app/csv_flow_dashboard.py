"""Standalone CSV dashboard for one recording and one counting line."""
from pathlib import Path

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from components.flow_candles import flow_candles

ROOT = Path(__file__).resolve().parents[1]
CLASSES = {'motorbike': 'Xe máy', 'car': 'Ô tô', 'truck': 'Xe tải', 'bus': 'Xe buýt'}
DIRECTIONS = {'toward': 'Về phía camera', 'away': 'Ra xa camera'}
COLUMNS = ['timestamp', 'track_id', 'class_name', 'direction']


def read_events(source):
    events = pd.read_csv(source, dtype={'track_id': 'string'})
    if not set(COLUMNS).issubset(events.columns):
        raise ValueError('CSV cần các cột timestamp, track_id, class_name, direction.')
    events = events[COLUMNS].copy()
    if events.empty or events.isna().any().any():
        raise ValueError('CSV phải có sự kiện và đầy đủ bốn trường cho mỗi dòng.')
    events['timestamp'] = pd.to_datetime(events['timestamp'], format='mixed')
    if events.timestamp.isna().any() or events.timestamp.dt.tz is not None:
        raise ValueError('timestamp phải là ngày giờ địa phương, không kèm múi giờ.')
    events['track_id'] = events.track_id.str.strip()
    if events.track_id.eq('').any():
        raise ValueError('ID xe không được để trống.')
    if not events.class_name.isin(CLASSES).all() or not events.direction.isin(DIRECTIONS).all():
        raise ValueError('Loại xe hoặc hướng đi không thuộc danh sách hỗ trợ.')
    return events.drop_duplicates().sort_values('timestamp')


def render_csv_dashboard():
    st.title('Lưu lượng xe qua vạch')
    with st.container():
        upload = st.file_uploader('CSV sự kiện qua vạch', type=['csv'])
        direction = st.selectbox('Hướng đi', ['Tất cả', *DIRECTIONS], format_func=lambda d: DIRECTIONS.get(d, d))
        classes = st.multiselect('Loại xe', list(CLASSES), default=list(CLASSES), format_func=CLASSES.get)

    try:
        events = read_events(upload if upload is not None else ROOT / 'data/demo_crossings_5min.csv')
        if upload is None:
            start, minutes = pd.Timestamp('2026-11-11 08:00:00'), 5
            st.caption('Dữ liệu giả lập · Một camera · Một vạch đếm · 5 phút')
        else:
            with st.container():
                start_text = st.text_input('Bắt đầu ghi (giờ địa phương)', str(events.timestamp.min().floor('min')))
                minutes = st.selectbox('Số phút ghi liên tục', [3, 4, 5], index=2)
                confirmed = st.checkbox('Xác nhận thời gian ghi liên tục để tính dự báo')
            if not confirmed:
                st.info('Xác nhận thời điểm bắt đầu và số phút ghi liên tục ở trên.')
                return
            start = pd.Timestamp(start_text)
            if pd.isna(start) or start.tzinfo is not None or start != start.floor('min'):
                raise ValueError('Thời điểm bắt đầu phải là giờ địa phương và tròn phút.')
            st.caption(f'Nguồn CSV: {upload.name}')
        end = start + pd.Timedelta(minutes=minutes)
        if not events.timestamp.between(start, end, inclusive='left').all():
            raise ValueError('Có sự kiện nằm ngoài khoảng ghi đã chọn.')
    except (ValueError, TypeError, AttributeError, OSError) as error:
        st.error(str(error))
        return

    selected = events[events.class_name.isin(classes)]
    if direction != 'Tất cả':
        selected = selected[selected.direction.eq(direction)]
    index = pd.date_range(start, periods=minutes, freq='min', name='Phút')
    by_class = (selected.groupby([selected.timestamp.dt.floor('min'), 'class_name']).size().unstack(fill_value=0)
                .reindex(index=index, columns=list(CLASSES), fill_value=0).fillna(0).astype(int))
    rate = len(selected) / minutes
    future = pd.date_range(end, periods=5, freq='min', name='Phút')
    subintervals = pd.date_range(start, periods=minutes * 6, freq='10s')
    samples = selected.groupby(selected.timestamp.dt.floor('10s')).size().reindex(subintervals, fill_value=0)
    left, center, right = st.columns(3)
    left.metric('Lượt qua vạch', len(selected))
    center.metric('Trung bình mỗi phút', f'{rate:.1f}')
    right.metric('Dự báo 5 phút tới', f'{rate * 5:.1f} lượt')
    st.caption(f'Khoảng dự báo {end:%H:%M}–{end + pd.Timedelta(minutes=5):%H:%M}. Dự báo giữ nguyên lưu lượng trung bình của đoạn ghi, chưa có đánh giá độ chính xác.')
    st.caption('Mỗi nến là một phút, gồm sáu lượt đếm 10 giây. Mở và đóng là lượt đầu và cuối, cao và thấp là cực trị trong phút.')
    figure = flow_candles(samples, 6)
    figure.add_trace(go.Scatter(x=future, y=[rate / 6] * len(future), mode='lines+markers',
                                name='Dự báo cơ sở', line=dict(dash='dash', color='#5576b7')))
    figure.update_yaxes(title='Lượt qua vạch / 10 giây', rangemode='tozero')
    st.plotly_chart(figure, width='stretch')
    st.subheader('Lượt qua vạch theo loại xe')
    st.bar_chart(by_class.rename(columns=CLASSES), stack=True, y_label='Lượt qua vạch / phút')
    with st.expander('Chi tiết sự kiện'):
        st.dataframe(selected, hide_index=True, width='stretch')


if __name__ == "__main__":
    st.set_page_config(page_title="Lưu lượng xe qua vạch", layout="wide")
    render_csv_dashboard()
