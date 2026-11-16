"""Live dashboard backed by a session-owned processing worker."""
from io import StringIO
from pathlib import Path
import pandas as pd
import streamlit as st
from components.analytics_panel import ALERT_LABELS, render_gate_proposals, render_settings
from components.flow_candles import video_time
from src.realtime import RealtimeSession
from src.forecast_truth import read_count_labels


@st.fragment(run_every=.5)
def live_status():
    worker = st.session_state.get("realtime_worker")
    if worker is None:
        return
    state = worker.snapshot()
    st.write(state["status"])
    st.caption(f'Thời gian từ đầu nguồn: {video_time(state["time_s"])}')
    if state.get("error"):
        st.error(state["error"])
    if st.button("Dừng xử lý", key="stop_realtime"):
        worker.stop()
    if "frame" in state:
        st.image(state["frame"], channels="BGR", width="stretch")
        a, b, c = st.columns(3)
        a.metric("FPS phân tích", f'{state["processed_fps"]:.1f}')
        b.metric("Trễ sau nhận frame", f'{state["latency_ms"]:.0f} ms')
        c.metric("Trễ P95", f'{state["p95_ms"]:.0f} ms')
        skip = state["frame_skip"]
        sampling = (f'lấy mẫu thích ứng {state["sampling_fps"]:.1f} FPS' if skip is None
                    else f'lấy 1 mỗi {skip + 1} khung nguồn')
        st.caption(f'{state["device"]} · {state["processed"]} frame đã xử lý · '
                   f'{state["skipped"]} frame bỏ theo chế độ · {state["dropped"]} frame rơi do xử lý chậm · {sampling}')
        st.subheader("Lưu lượng và số xe hiện diện")
        crossings = state["crossings"]
        left, right = st.columns(2)
        left.metric("Lượt qua vạch về phía camera", crossings.get("toward", 0))
        right.metric("Lượt qua vạch ra xa camera", crossings.get("away", 0))
        history = pd.DataFrame(state["zone_history"])
        st.line_chart(history.pivot(index="time_s", columns="zone", values="total"),
                      x_label="Giây từ đầu video", y_label="Số xe hiện diện")
        st.dataframe(pd.DataFrame(state["zones"]), hide_index=True)
        st.subheader("Cảnh báo trong phiên")
        events = pd.DataFrame(state["alerts"])
        if not events.empty:
            events["canh_bao"] = events.event.map(ALERT_LABELS)
            events["event"] = events.event.replace("abrupt_turn", "Dangerous")
            events.insert(0, "Thời điểm trong video", events.time_s.map(video_time))
            st.dataframe(events, hide_index=True)
        else:
            st.caption("Chưa có cảnh báo trong phiên.")
        forecast = state.get("forecast")
        if forecast:
            st.write("Dự báo số xe hiện diện sau 5 phút")
            st.dataframe(pd.Series(forecast["values"], name="Số xe dự báo").to_frame())
            st.caption("Dự báo dùng trung bình 60 giây gần nhất.")
            if state.get("forecast_samples"):
                st.metric("MAE so với nhãn độc lập", f'{state["forecast_mae"]:.2f} xe')
                st.caption(f'{state["forecast_samples"]} cặp vùng và mốc thời gian đã đối chiếu.')
            else:
                st.caption("Chưa có nhãn độc lập khớp với mốc dự báo đã đến.")
        st.caption(f'Nhật ký và thư mục clips của phiên: {state["log_dir"]}')
    if state.get("evidence_csv") and state["status"] == "Đã dừng":
        csv_path = Path(state["evidence_csv"])
        st.download_button("Tải CSV cảnh báo", csv_path.read_bytes(),
                           "violations.csv", "text/csv", on_click="ignore")
        exported = pd.read_csv(csv_path)
        saved = exported.loc[exported["clip_status"] == "saved", ["time_s", "track_id", "event", "clip"]].copy()
        if not saved.empty:
            saved.insert(0, "Thời điểm trong video", saved.time_s.map(video_time))
            saved["event"] = saved.event.replace("abrupt_turn", "Dangerous")
            saved["Đường dẫn clip"] = saved["clip"].map(lambda path: str((csv_path.parent / path).resolve()))
            st.dataframe(saved.drop(columns=["time_s", "clip"]), hide_index=True)
            selection = st.selectbox("Clip cảnh báo theo ID xe", saved["clip"].tolist(), index=None)
            if selection:
                clip = (csv_path.parent / selection).resolve()
                st.code(str(clip), language=None)
                if clip.is_file():
                    st.download_button("Tải clip đã chọn", clip.read_bytes(), clip.name,
                                       "video/mp4", on_click="ignore")


def render_realtime(root):
    st.caption("Một lượt YOLO + ByteTrack dùng chung cho đếm xe, hành vi và dự báo. "
               "Thời gian trễ đo từ lúc OpenCV nhận frame đến kết quả xử lý.")
    local_video = "Đường dẫn video trên máy"
    kind = st.selectbox("Nguồn thời gian thực",
                        [local_video, "Video demo phát đúng tốc độ", "Camera RTSP/HTTP", "Webcam"])
    source = str(root / "data/goi_ban_giao_B/demo/clip_ngc.mp4")
    if kind == local_video:
        source = st.text_input("Đường dẫn tệp video",
                               placeholder=r"D:\code\DATN\person_b\data\cam5.mp4",
                               help="Dán đường dẫn tuyệt đối hoặc tương đối trong thư mục dự án. Nếu đặt TRAFFIC_VIDEO_DIR, dùng thư mục đó.")
        st.caption("Video được đọc trực tiếp từ ổ đĩa theo tốc độ gốc. Kết quả cập nhật khi đang xử lý.")
    elif kind == "Camera RTSP/HTTP":
        source = st.text_input("URL camera", type="password")
    elif kind == "Webcam":
        source = int(st.number_input("Số webcam", min_value=0, value=0))
    frame_skip = st.selectbox(
        "Bỏ qua khung hình", [None, 0, 1, 2, 3],
        format_func=lambda skip: "Tự động" if skip is None else f"Bỏ {skip} khung sau mỗi khung được chọn",
        help="Ví dụ, bỏ 2 nghĩa là chọn 1 trong mỗi 3 khung nguồn. Nếu xử lý chậm, hệ thống vẫn ưu tiên khung mới nhất.",
    )
    settings = render_settings(realtime=True)
    st.caption("Khai báo hướng hợp lệ trong JSON để phát hiện ngược chiều trong phiên.")
    labels = None
    if kind in (local_video, "Video demo phát đúng tốc độ"):
        labels = st.file_uploader("Nhãn đếm xe độc lập cho dự báo (tùy chọn)", type="csv",
                                  help="CSV có second,zone,total. Dùng đúng video, mốc từ 0:00 và vùng của phiên.")
    worker = st.session_state.get("realtime_worker")
    running = worker is not None and worker.thread.is_alive()
    if st.button("Bắt đầu xử lý thời gian thực", disabled=running or settings is None or not str(source).strip()):
        try:
            options = dict(settings)
            profile = options.pop("profile")
            counts = read_count_labels(StringIO(labels.getvalue().decode("utf-8-sig"))) if labels else None
            if kind == "Camera RTSP/HTTP" and not source.startswith(("rtsp://", "rtsps://", "http://", "https://")):
                raise ValueError("Cần URL RTSP hoặc HTTP hợp lệ.")
            if kind == local_video:
                worker = RealtimeSession.from_local_video(source, root, profile=profile,
                                                         analytics_options=options, frame_skip=frame_skip, count_labels=counts)
            else:
                worker = RealtimeSession(source, root, replay=kind == "Video demo phát đúng tốc độ",
                                         profile=profile, analytics_options=options, frame_skip=frame_skip, count_labels=counts)
            st.session_state.realtime_worker = worker.start()
        except (ValueError, TypeError, KeyError) as error:
            st.error(str(error))
    live_status()
    with st.expander("Hiệu chỉnh cổng vào / ra từ quỹ đạo"):
        render_gate_proposals()
