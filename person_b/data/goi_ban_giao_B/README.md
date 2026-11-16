# Gói bàn giao từ Thành viên A (Computer Vision) cho Thành viên B

## 1. Nội dung
    src/       traffic_pipeline.py, traffic_pipeline_fast.py   (mô-đun xử lý video)
    models/    best_v2.pt                                      (YOLOv8s, 4 lớp: xe_hoi, xe_may, xe_tai, bus)
    demo/      clip_ngc.mp4                                    (clip 60 giây, có xe đi ngược chiều)
    data/      counts_per_minute_full.csv, counts_per_10s_full.csv, count_events_full.csv,
               wrongway_alerts_final.csv, wrongway_config_final.json
    examples/  demo_run.py
    requirements_freeze.txt                                    (phiên bản chính xác trên máy A, để đối chiếu)

## 2. Cài đặt (Windows, PowerShell)
    python -m venv traffic_env
    .\traffic_env\Scripts\Activate.ps1
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
    pip install -r requirements.txt
    python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
Lệnh trên dùng bản PyTorch CUDA cho máy NVIDIA. Với máy chỉ dùng CPU, thay dòng cài torch bằng `pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu`. Cài torch trước ultralytics. Pipeline chọn `cuda:0` khi PyTorch báo CUDA khả dụng, hoặc `cpu` khi CUDA không khả dụng. Demo in thiết bị được chọn khi xử lý khung đầu tiên.

## 3. Chạy thử
    python examples\demo_run.py
Mong đợi: 5 cảnh báo ngược chiều (khoảng 13:47:18, 13:47:25, 13:47:45, 13:47:48, 13:47:49),
khoảng 44 đến 45 xe qua vạch trong 60 giây, và file demo_alert.jpg.

## 4. Dùng trong Dashboard
    from traffic_pipeline_fast import FastPipeline
    pipe = FastPipeline("models/best_v2.pt", clock0="2026-04-09 13:41:50")
    for out in pipe.run("video.mp4", annotate=True):
        out["annotated"]    # ảnh BGR (numpy) đã vẽ khung, ID, vạch đếm, bộ đếm, cảnh báo
        out["counts"]       # {"toward": {...}, "away": {...}} cộng dồn từ đầu video
        out["new_events"]   # xe vừa cắt vạch ở khung này (frame, timestamp, track_id, loai, nhom, huong)
        out["new_alerts"]   # cảnh báo ngược chiều mới (gio_canh_bao, track_id, loai, x, y, vung, ...)
        out["timestamp"]    # giờ camera của khung này
- run() là generator, mỗi lần trả về một khung đã xử lý (video 60 FPS được xử lý 1 khung trên 2).
- Nên chạy vòng for trong một luồng hoặc tiến trình riêng, rồi đẩy kết quả sang giao diện qua hàng đợi hoặc file,
  để giao diện không bị khựng. Có thể truyền annotate=False nếu Dashboard tự vẽ.
- pipe.counts, pipe.events, pipe.alerts giữ kết quả tích lũy từ đầu video.
- clock0 là giờ camera ở giây 0 của video. Video 25 phút gốc: "2026-04-09 13:41:50". clip_ngc: "2026-04-09 13:47:00".

## 5. Lưu ý quan trọng
1. Cấu hình (vạch đếm y=600, đường tâm làn, ngưỡng) chỉ đúng cho camera 0511.vn, ảnh 1920x1080 trong video này.
   Dùng video khác thì phải hiệu chỉnh lại. Đừng đổi ngưỡng khi chưa trao đổi với A.
2. File .engine (TensorRT) chỉ chạy trên đúng loại card đã xuất ra nó. Gói này chỉ có .pt, chạy trên mọi card NVIDIA.
   Cần .engine cho máy B: báo A để có hướng dẫn xuất.
3. Cảnh báo ngược chiều là "CẢNH BÁO CẦN XÁC NHẬN", không phải kết luận vi phạm. Trên 21 cảnh báo ngoài clip kiểm tra đã
   được duyệt tay: 17 đúng, 4 sai (khoảng 81%). Ở clip có xe đi ngược: bắt 5/7 ca thật.
4. Dữ liệu thật rất phẳng (28 đến 51 xe/phút, không có đợt ùn tắc), chỉ 25 phút. Không đủ để huấn luyện dự báo 15 đến 30 phút:
   huấn luyện bằng dữ liệu giả lập dài hơn, dùng dữ liệu thật để minh họa luồng chạy.
5. counts_per_minute_full.csv: bin_start, toward_/away_ x {xe_may, xe_hoi, xe_lon}, tong_ve_camera, tong_ra_xa, tong,
   so_xe_trung_binh (mật độ vùng y>=300), toc_do_tuong_doi (chiều cao xe/giây), ti_le_dung (khoảng 0.37 là mức nền do xe đỗ),
   do_phu (hãy bỏ dòng do_phu < 1), canh_bao_nguoc_chieu.
   toward = xe đi về phía camera, away = xe đi ra xa. xe_lon = xe tải + bus.

## 6. Số liệu tham khảo (clip_ngc, 60 giây, imgsz 960)
    Colab T4:   PyTorch 22 FPS | TensorRT FP16 30 đến 41 FPS (tùy cách đọc video)
    RTX 5060:   PyTorch FP32 khoảng 76 FPS
    RTX 4050:   chưa đo (B chạy examples\demo_run.py và báo lại FPS)
