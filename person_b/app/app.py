"""One traffic dashboard for video analysis, historical records and forecasts."""
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from components.alerts_panel import render_alerts
from components.forecast_panel import render_forecast
from csv_flow_dashboard import render_csv_dashboard
from components.realtime_panel import render_realtime

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ['motorbike', 'car', 'truck', 'bus']


def render_history():
    st.subheader('Giám sát lưu lượng giao thông')

    with st.container():
        source = st.selectbox('Nguồn dữ liệu', ['Log thực tế của thành viên A', 'Dữ liệu mô phỏng'])
        by_class = st.toggle('Hiển thị theo loại xe', value=True)

    real = source == 'Log thực tế của thành viên A'
    if real:
        with st.container():
            measure = st.selectbox('Phương pháp đếm', ['Xe qua vạch', 'Xe xuất hiện trong khung hình'])
            seconds = st.selectbox('Khoảng thời gian (giây)', [10, 60, 300])
            include_partial = st.checkbox('Hiển thị khoảng chưa đủ thời lượng', value=True)
        prefix = 'crossings' if measure == 'Xe qua vạch' else 'observed'
        path = ROOT / 'data/person_a_prepared' / f'{prefix}_{seconds}s.csv'
    else:
        with st.container():
            minutes = st.selectbox('Khoảng thời gian (phút)', [5, 15, 30])
        path = ROOT / 'data/mock_traffic_data.csv'

    if not path.exists():
        st.info('Chưa có dữ liệu đã chuẩn bị. Chạy scripts/prepare_person_a.py cho log thực tế hoặc scripts/generate_mock.py cho dữ liệu mô phỏng.')
        return
    try:
        # Read small prepared tables on each rerun so replaced files are reflected immediately.
        df = pd.read_csv(path)
        if real:
            partial = int((~df.complete_interval).sum())
            st.caption('Log đã hiệu chỉnh của thành viên A · Thời gian tính từ đầu video · Chưa biết ngày giờ ghi hình.')
            if prefix == 'observed':
                st.info('Mỗi ID chỉ được đếm một lần trong từng khoảng. Một xe có thể xuất hiện ở nhiều khoảng; không cộng các khoảng để tính số xe duy nhất của toàn video.')
            else:
                st.caption('Mỗi sự kiện qua vạch được đếm một lần. Hướng toward/away mô tả chuyển động; không tự động đồng nghĩa với vi phạm ngược chiều.')
            if partial:
                st.warning(f'{partial} khoảng chưa đủ thời lượng. Cột thời lượng chỉ là giới hạn dưới suy ra từ lần phát hiện cuối; cần metadata video để xác nhận.')
            view = df if include_partial else df[df.complete_interval]
            x, xlabel = 'time_s', 'Giây từ đầu video'
            st.info('Video khoảng 2 phút chưa đủ một khoảng 5 phút hoàn chỉnh. Chưa có dự báo được huấn luyện trên dữ liệu này.')
        else:
            st.warning('Dữ liệu mô phỏng — chỉ dùng thử giao diện, không phải kết quả đo giao thông thực tế.')
            df['timestamp'] = pd.to_datetime(df.timestamp)
            view = df.set_index('timestamp')[CLASSES + ['total_vehicles']].resample(f'{minutes}min').sum().reset_index()
            x, xlabel = 'timestamp', 'Thời gian mô phỏng'
    except (ValueError, KeyError, OSError) as error:
        st.error(f'Không đọc được dữ liệu: {error}')
        return

    if view.empty:
        st.info('Không có khoảng hoàn chỉnh ở độ dài đã chọn. Chọn khoảng ngắn hơn hoặc bật hiển thị khoảng chưa đủ thời lượng.')
        return

    c1, c2, c3 = st.columns(3)
    c1.metric('Số khoảng hiển thị', len(view))
    c2.metric('Số xe ở khoảng cuối', int(view.iloc[-1].total_vehicles))
    c3.metric('Số xe cao nhất / khoảng', int(view.total_vehicles.max()))
    fig = px.bar(view, x=x, y=CLASSES if by_class else 'total_vehicles',
                 title='Số xe theo khoảng thời gian', barmode='stack')
    fig.update_layout(xaxis_title=xlabel, yaxis_title='Số xe / khoảng', legend_title_text='Loại xe')
    st.plotly_chart(fig, width='stretch')
    if real and prefix == 'crossings':
        events_path = ROOT / 'data/person_a_prepared/crossing_events_relative.csv'
        if events_path.exists():
            events = pd.read_csv(events_path)
            st.subheader('Hướng qua vạch trong toàn video')
            st.dataframe(events.groupby(['direction', 'class_name']).size().unstack(fill_value=0), width='stretch')
    st.subheader('Dữ liệu đang hiển thị')
    st.dataframe(view, hide_index=True, width='stretch')
    st.download_button('Tải CSV đang hiển thị', view.to_csv(index=False).encode('utf-8-sig'),
                       file_name=('real_' + prefix if real else 'mock') + '_counts.csv', mime='text/csv')


st.set_page_config(page_title='Giám sát giao thông', layout='wide')
st.title('Giám sát giao thông')
live, csv_flow = st.tabs(['Thời gian thực', 'Phân tích CSV'])
with live:
    render_realtime(ROOT)
    with st.expander('Dữ liệu đã lưu và thử nghiệm dự báo'):
        history, alerts, forecast = st.tabs(['Lưu lượng lịch sử', 'Cảnh báo đã ghi', 'Thử nghiệm dự báo'])
        with history:
            render_history()
        with alerts:
            render_alerts(ROOT)
        with forecast:
            render_forecast(ROOT)
with csv_flow:
    render_csv_dashboard()
