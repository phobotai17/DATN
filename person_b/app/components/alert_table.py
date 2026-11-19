"""Shared display for wrong-way alert tables."""
import streamlit as st

HIDDEN_COLUMNS = ['gio_canh_bao', 'giờ cảnh báo', 'gio_bat_dau', 'timestamp', 'recorded_timestamp', 'vung', 'vùng']
FIELD_HELP = {
    'cao_px': 'Chiều cao trung vị của hộp bao phương tiện trong các khung gần thời điểm cảnh báo, tính bằng pixel.',
    'wh': 'Trung vị của tỷ lệ chiều rộng chia chiều cao của hộp bao. Giá trị trên 1 nghĩa là hộp rộng hơn cao.',
    'vung': 'Vị trí tương đối trong ảnh. Với camera 0511.vn, điểm chân xe có y < 225 được gắn nhãn xa, còn lại là gần.',
}


def render_alert_table(alerts):
    table = alerts.drop(columns=HIDDEN_COLUMNS, errors='ignore')
    st.dataframe(table, hide_index=True, width='stretch',
                 column_config={field: st.column_config.NumberColumn(field, help=FIELD_HELP[field])
                                for field in ('cao_px', 'wh') if field in table},
                 alt='Danh sách cảnh báo cần xác nhận')
    with st.expander('Giải thích cao_px, wh và vùng'):
        for field, description in FIELD_HELP.items():
            st.markdown(f'**{field}** — {description}')
    return table
