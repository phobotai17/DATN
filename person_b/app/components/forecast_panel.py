"""Display saved synthetic forecast experiments without retraining on reruns."""
import hashlib
import json
import pandas as pd
import plotly.express as px
import streamlit as st


def render_forecast(root):
    st.title('Thử nghiệm dự báo lưu lượng')
    st.warning('Kết quả trên dữ liệu mô phỏng. Đây không phải dự báo từ video thực tế của thành viên A.')
    folder = root / 'results/mock_forecast'
    required = ['experiment.json', 'metrics.csv', 'test_predictions.csv', 'demo_future_forecast.csv', 'training_loss.csv']
    if any(not (folder/name).exists() for name in required):
        st.info('Chưa có kết quả đầy đủ. Chạy scripts/train_forecast.py để tạo thử nghiệm.')
        return
    try:
        report = json.loads((folder/'experiment.json').read_text(encoding='utf-8-sig'))
        metrics = pd.read_csv(folder/'metrics.csv')
        predictions = pd.read_csv(folder/'test_predictions.csv', parse_dates=['target_timestamp', 'origin_timestamp'])
        future = pd.read_csv(folder/'demo_future_forecast.csv', parse_dates=['timestamp'])
        losses = pd.read_csv(folder/'training_loss.csv')
        if metrics.empty or predictions.empty or future.empty:
            raise ValueError('Bảng kết quả trống')
        source = root/'data/mock_traffic_data.csv'
        if source.exists() and hashlib.sha256(source.read_bytes()).hexdigest() != report['source_sha256']:
            st.warning('Dữ liệu mô phỏng hiện tại đã thay đổi từ lần huấn luyện. Biểu đồ bên dưới là kết quả đã lưu của lần chạy cũ.')
        st.caption(f"Dữ liệu huấn luyện: {report['train_rows']} khoảng · Kiểm tra: {report['test_rows']} khoảng · Bước thời gian: {report['interval_minutes']} phút · Seed: {report['seed']}")
        st.caption('Các mô hình dùng cùng thời điểm dự báo; chỉ dùng lịch sử trước thời điểm đó. Các cửa sổ kiểm tra chồng lấn, không phải mẫu độc lập.')
        horizon = st.selectbox('Tầm dự báo (phút)', [15, 30], key='forecast_horizon')
        selected = metrics[metrics.horizon_minutes == horizon].copy()
        st.subheader('So sánh mô hình trên tập kiểm tra')
        st.dataframe(selected[['model', 'samples', 'MAE', 'RMSE', 'MAPE']], hide_index=True, width='stretch')
        st.caption('MAE và RMSE: số xe mỗi khoảng 5 phút; MAPE: %. Đây là sai số tại bước +15 hoặc +30 phút, không phải tổng số xe trong cả tầm dự báo.')
        model = st.selectbox('Mô hình để xem dự đoán', sorted(predictions.model.unique()), key='forecast_model')
        subset = predictions[(predictions.model == model) & (predictions.horizon_minutes == horizon)].sort_values('target_timestamp')
        st.plotly_chart(px.line(subset, x='target_timestamp', y=['actual', 'prediction'],
                               labels={'target_timestamp':'Thời gian mô phỏng', 'value':'Số xe / 5 phút'},
                               title=f'{model}: thực tế mô phỏng và dự đoán +{horizon} phút'), width='stretch')
        st.download_button('Tải dự đoán kiểm tra đang xem', subset.to_csv(index=False).encode('utf-8-sig'),
                           file_name=f'mock_{model.replace(" ", "_")}_{horizon}min.csv', mime='text/csv')
        st.subheader('Dự báo minh họa sau cuối chuỗi mô phỏng')
        future_model = st.selectbox('Mô hình dự báo minh họa', sorted(future.model.unique()), key='future_model')
        demo = future[future.model == future_model].sort_values('timestamp')
        st.caption('Sáu khoảng 5 phút sau cuối dữ liệu mô phỏng. Chưa có giá trị thực tế để đánh giá các điểm này; không phải dự báo thời gian hiện tại.')
        st.plotly_chart(px.line(demo, x='timestamp', y='prediction', markers=True,
                               labels={'timestamp':'Thời gian mô phỏng', 'prediction':'Số xe / 5 phút'}), width='stretch')
        st.dataframe(demo[['timestamp', 'horizon_minutes', 'prediction']], hide_index=True, width='stretch')
        st.download_button('Tải bảng so sánh đầy đủ', metrics.to_csv(index=False).encode('utf-8-sig'),
                           file_name='mock_forecast_metrics.csv', mime='text/csv')
        with st.expander('Quá trình huấn luyện và giới hạn'):
            st.plotly_chart(px.line(losses, x='epoch', y='training_mse_scaled', color='model',
                                   labels={'epoch':'Epoch', 'training_mse_scaled':'MSE trên dữ liệu đã chuẩn hóa'}), width='stretch')
            st.write('Chỉ có một ngày dữ liệu giả lập. Cần chuỗi thực tế dài hơn để đánh giá khả năng dự báo và chọn mô hình.')
            st.json(report)
    except (OSError, ValueError, KeyError) as error:
        st.error(f'Không đọc được kết quả thử nghiệm: {error}')
