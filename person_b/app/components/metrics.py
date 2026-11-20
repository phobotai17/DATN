"""Các thẻ số liệu nhanh (KPI) phía trên biểu đồ."""
import pandas as pd
import streamlit as st


def render_kpis(df: pd.DataFrame) -> None:
    latest = df.iloc[-1]
    peak = df.loc[df["total_vehicles"].idxmax()]
    c1, c2, c3 = st.columns(3)
    c1.metric("Mới nhất", f"{int(latest['total_vehicles'])} xe", help=str(latest["timestamp"]))
    c2.metric("Đỉnh trong ngày", f"{int(peak['total_vehicles'])} xe",
              help=f"Lúc {peak['timestamp']:%H:%M}")
    c3.metric("Trung bình", f"{df['total_vehicles'].mean():.0f} xe")
