"""Biểu đồ mật độ giao thông theo thời gian (Plotly)."""
import pandas as pd
import plotly.express as px
import streamlit as st

CLASSES = ["motorbike", "car", "truck", "bus"]


def resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Gộp dữ liệu 5 phút thành khung lớn hơn (tổng số xe)."""
    if minutes == 5:
        return df
    out = (df.set_index("timestamp")[CLASSES + ["total_vehicles"]]
             .resample(f"{minutes}min").sum().reset_index())
    return out


def render_density_chart(df: pd.DataFrame, by_class: bool = False) -> None:
    if by_class:
        fig = px.area(df, x="timestamp", y=CLASSES, title="Lưu lượng theo loại xe (Mock Data)")
    else:
        fig = px.line(df, x="timestamp", y="total_vehicles", title="Lưu lượng xe (Mock Data)")
    fig.update_layout(xaxis_title="Thời gian", yaxis_title="Số xe / khung",
                      legend_title_text="", margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, width="stretch")
