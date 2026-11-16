"""Khung video (placeholder) - tuần 4 sẽ thay bằng luồng video tracking của Thành viên A."""
from PIL import Image, ImageDraw
import streamlit as st


def _placeholder(width: int = 1280, height: int = 720) -> Image.Image:
    img = Image.new("RGB", (width, height), (24, 28, 36))
    draw = ImageDraw.Draw(img)
    text = "Waiting for YOLO video stream..."
    box = draw.textbbox((0, 0), text)
    draw.text(((width - (box[2] - box[0])) / 2, (height - (box[3] - box[1])) / 2),
              text, fill=(200, 205, 215))
    return img


def render_video_panel() -> None:
    st.subheader("📹 Luồng Video Real-time (Tracking Placeholder)")
    st.image(_placeholder(), width="stretch")
    st.caption("Khung chờ video đếm xe từ Thành viên A (ByteTrack + YOLO).")
