# Checkpoint nhận diện phương tiện cho bản demo

App dùng YOLOv8s `best_v2.pt` từ gói bàn giao với bốn lớp theo thứ tự `xe_hoi, xe_may, xe_tai, bus`. SHA-256 trùng với `data/tuan1/weights/best.pt`. Theo nhật ký huấn luyện, checkpoint được chọn ở epoch 18 và đạt mAP50–95 55,1% trên validation của đợt huấn luyện. Epoch cuối là 33 và đạt 47,0%. [Nhật ký huấn luyện](../data/tuan1/bao_cao/results.csv)

## Kết quả đo lại

Đo bằng Ultralytics 8.4.172 trên RTX 4050 Laptop, batch 8 và chế độ resize theo tỷ lệ ảnh. Sử dụng bộ ảnh 4 lớp phiên bản v1 có sẵn tại `legacy/data`. Nhãn được sao chép và đổi chỉ số theo tên lớp trong bản dùng để chấm. Tập validation có 37 ảnh và 416 hộp. Các phép đo chỉ xét detector trên ảnh.

| Checkpoint | imgsz | mAP50 | mAP50–95 | Recall |
| --- | ---: | ---: | ---: | ---: |
| best_v2 | 640 | 74,5% | **59,0%** | **76,9%** |
| last | 640 | 71,1% | 53,4% | 66,7% |
| best_v2 | 960 | 65,4% | 47,7% | 65,2% |

Chọn `best_v2.pt` và giữ cấu hình realtime hiện tại với cạnh dài tối đa 640 pixel. Kích thước 640 trong phép đo ảnh chỉ xấp xỉ phép tiền xử lý realtime 640 × 384. Chỉ số thời gian suy luận theo batch không dùng thay cho FPS của dashboard. [Kết quả detector](runs/detector-review/report.json) · [FPS pipeline](PILOT_RESULTS.md)

Sau khi chọn checkpoint, chạy riêng tập test v1 gồm 18 ảnh và 202 hộp. mAP50 là **52,2%** và mAP50–95 là **40,2%**.

| Lớp | Số hộp test | mAP50–95 | Recall |
| --- | ---: | ---: | ---: |
| Ô tô | 104 | 70,0% | 73,1% |
| Xe máy | 84 | 62,5% | 81,0% |
| Xe tải | 13 | 28,4% | 38,5% |
| Xe buýt | 1 | 0,0% | 0,0% |

Xe buýt duy nhất bị phân loại thành xe tải trong ma trận nhầm lẫn. Một mẫu quá ít để ước lượng recall lớp xe buýt. Không có ảnh trùng khớp SHA-256 giữa các split trong bản v1, nhưng chưa đối chiếu với dữ liệu huấn luyện trên Colab và chưa rà trùng các khung liền kề. Dùng số liệu này để chẩn đoán, chưa dùng để tuyên bố khả năng tổng quát hóa sang camera mới. [Ma trận nhầm lẫn tập test](runs/detector-review/locked-best-640-test/confusion_matrix.png)

## Chạy lại

Từ thư mục dự án với môi trường ứng dụng đã kích hoạt:

```powershell
yolo detect val model=data/goi_ban_giao_B/models/best_v2.pt data=evals/runs/detector-review/probe.yaml split=val imgsz=640 batch=8 device=0 workers=0 rect=True
yolo detect val model=data/goi_ban_giao_B/models/best_v2.pt data=evals/runs/detector-review/probe.yaml split=test imgsz=640 batch=8 device=0 workers=0 rect=True
python -m unittest discover -s tests
python -m unittest discover -s evals
```

Để hoàn thiện bản nhận diện bốn lớp, ưu tiên xác minh bộ ảnh đã huấn luyện và bổ sung ảnh xe tải, xe buýt từ các camera đường thẳng. Chia tập theo video hoặc camera, giữ riêng tập test có đủ xe của cả bốn lớp. Đánh giá mỗi checkpoint mới theo từng lớp tại kích thước triển khai, rồi đo lại FPS và độ trễ qua worker realtime trước khi thay checkpoint trong app.
