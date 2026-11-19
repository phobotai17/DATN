"""Recorded wrong-way detector alerts with session-deduplicated notifications."""
import json
import pandas as pd
import streamlit as st
from components.alert_table import render_alert_table


def render_alerts(root):
    st.title('Cảnh báo phương tiện đi ngược chiều')
    st.caption('Phát lại kết quả bộ phát hiện của thành viên A. Các cảnh báo tự động chưa được xác nhận thủ công; đây không phải luồng camera trực tiếp.')
    path=root/'data/tuan4/data/wrongway_alerts_final.csv'
    meta_path=root/'data/tuan4/data/seg/meta.json'
    if not path.exists() or not meta_path.exists():
        st.info('Chưa có log cảnh báo hoặc metadata ghi hình.')
        return
    try:
        data=pd.read_csv(path)
        meta=json.loads(meta_path.read_text())
        required={'track_id','time_s','loai'}
        if not required.issubset(data):
            raise ValueError('Thiếu cột cảnh báo bắt buộc')
        for c in ['track_id','time_s']:
            data[c]=pd.to_numeric(data[c],errors='raise')
            if data[c].isna().any() or not data[c].between(0,float('inf'),inclusive='left').all():
                raise ValueError('ID hoặc thời gian không hợp lệ')
        if (data.track_id%1!=0).any() or (data.time_s>meta['duration_s']).any():
            raise ValueError('ID không nguyên hoặc thời gian ngoài video')
        data=data.sort_values('time_s').drop_duplicates(['track_id','time_s']).reset_index(drop=True)
        start=pd.Timestamp(meta['video_start'])
        st.caption(f"Bắt đầu ghi hình: {start} · Thời lượng: {meta['duration_s']:.1f} giây · Múi giờ theo metadata chưa được xác minh.")
        position=st.slider('Thời điểm phát lại (giây)',0,int(meta['duration_s'])+1,0,key='alert_position')
        notify=st.checkbox('Thông báo khi phát lại tới cảnh báo mới',value=True,key='alert_notify')
        visible=data[data.time_s<=position].copy()
        # IDs include the source session. Rewinds and UI reruns never re-toast
        # events already delivered in this dashboard session.
        seen=st.session_state.setdefault('wrongway_seen_events',set())
        keys=[f'pilot_camera_20260409:{int(r.track_id)}:{r.time_s}' for r in visible.itertuples()]
        unseen=[k for k in keys if k not in seen]
        if notify and unseen:
            st.toast(f'{len(unseen)} cảnh báo mới trong bản phát lại',icon='⚠️')
            seen.update(unseen)
        a,b,c=st.columns(3)
        a.metric('Tổng cảnh báo trong log',len(data))
        b.metric('Đã tới trong bản phát lại',len(visible))
        c.metric('ID đã cảnh báo',visible.track_id.nunique())
        if visible.empty:
            st.info('Chưa tới cảnh báo nào. Di chuyển thanh thời gian để kiểm tra thông báo.')
        else:
            st.warning(f'Có {len(visible)} cảnh báo tự động tới thời điểm này. Cần kiểm tra video để xác nhận vi phạm.')
            vehicle=st.selectbox('Lọc loại xe',['Tất cả']+sorted(visible.loai.dropna().unique().tolist()),key='alert_vehicle')
            shown=visible if vehicle=='Tất cả' else visible[visible.loai==vehicle]
            shown=render_alert_table(shown)
            st.download_button('Tải lịch sử cảnh báo đang xem',shown.to_csv(index=False).encode('utf-8-sig'),file_name='pilot_camera_recorded_alerts.csv',mime='text/csv')
        st.caption('Nhãn đánh giá ở các clip thử nghiệm khác không được gán tự động cho log này: ID có thể được dùng lại giữa các phiên.')
    except (ValueError,KeyError,OSError) as error:
        st.error(f'Không đọc được cảnh báo: {error}')
