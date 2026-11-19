# Trình diễn pipeline realtime

Mở PowerShell tại `D:/code/DATN/person_b` và chạy bằng môi trường Python đã cài thư viện. Ví dụ nếu dùng môi trường có sẵn ở thư mục cha:

```powershell
..\.venv\Scripts\python.exe -m streamlit run app/app.py --server.address=127.0.0.1
```

1. Mở URL Streamlit in ra. Trong **Thời gian thực**, chọn **Đường dẫn video trên máy** rồi nhập `data/goi_ban_giao_B/demo/clip_ngc.mp4`.
2. Mở **Vùng đo và ngưỡng cảnh báo** và dán nội dung [cấu hình demo](../evals/demo_profile.json). Cấu hình này dùng hai vùng đo và bật kiểm tra ngược chiều trong vùng `away_side` của góc camera mẫu.
3. Giữ **Bỏ qua khung hình → Tự động** và bấm **Bắt đầu xử lý thời gian thực**. Đồng hồ bắt đầu ở 0:00. Khi xuất hiện khung đầu tiên, chỉ ra thiết bị được chọn, FPS phân tích, độ trễ P95, số khung bỏ theo chế độ và số khung rơi do quá tải.
4. Xem video có hộp xe, số lượt qua vạch, số xe hiện diện theo vùng và bảng cảnh báo. Bảng dự báo đưa ra số xe ước tính sau 5 phút. Clip demo chỉ dài khoảng một phút nên không có đủ thời gian để đối chiếu tại đích dự báo.
5. Chờ clip chạy hết và đợi trạng thái **Đã dừng**. Bấm **Tải CSV cảnh báo**. Chọn một clip trong **Clip cảnh báo theo ID xe**, kiểm tra đường dẫn rồi bấm **Tải clip đã chọn**.

Nếu cần dự phòng để trình chiếu, giữ sẵn [CSV của một phiên đã chạy](../evals/runs/realtime-demo-annotated/cuda0-skip-auto-1/violations.csv) và [một clip bằng chứng](../evals/runs/realtime-demo-annotated/cuda0-skip-auto-1/clips/track_105_000007.mp4). Số cảnh báo trong từng lần phát có thể thay đổi do frame skip thích ứng và tốc độ xử lý của máy.

Để kiểm tra nhanh trước buổi bảo vệ, dùng `evals/runs/demo-window-source/demo_42s_56s.mp4`, giữ cùng cấu hình vùng và chọn **Bỏ 3 khung**. Đây là đoạn cắt 14 giây của clip mẫu. Trong lần chạy thử bằng trình duyệt, phiên này tự chọn GPU, đạt 12,23 FPS phân tích và tạo 3 clip. Mốc trên dashboard được tính từ đầu đoạn cắt. [CSV chạy thử](../results/realtime/20261117-015511-310676/violations.csv)

So sánh ba lần mỗi chế độ trên cùng đoạn 14 giây và RTX 4050 cho kết quả trung vị **14,83 FPS** với **Bỏ 3 khung** và **14,26 FPS** với **Tự động**. P95 trung vị của cả hai là **94 ms**. Cả hai đều phát hiện đúng hai xe ngược chiều có nhãn trong mỗi lần chạy. Phép đo dùng worker realtime và có mã hóa clip, chưa tính phần hiển thị của Streamlit và trình duyệt. Kết quả củng cố lựa chọn **Bỏ 3 khung** cho đoạn demo ngắn này. [CSV sáu lần chạy](../evals/runs/demo-mode-comparison/comparison.csv)
