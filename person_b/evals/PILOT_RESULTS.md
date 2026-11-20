# Kết quả đánh giá thử hệ thống

Thử nghiệm dùng video ghi sẵn phát theo nhịp nguồn. Kết quả gồm hai đoạn từ cùng góc camera, mỗi cấu hình chạy một lần. Các phép chấm dưới đây dùng các nhãn lấy bằng cách xem video gốc và đối chiếu với vùng đã vẽ.

## FPS, độ trễ và frame skip

Đo trên 20 giây đầu camera thử nghiệm, nguồn 1920 × 1080 ở 60 FPS. Mỗi phiên chạy giải mã, YOLOv8s, ByteTrack, đếm xe, phân tích chuyển động, dự báo và xuất bằng chứng khi phát sinh cảnh báo. Hồ sơ camera thử nghiệm dùng trong ma trận này có hai vùng đo. Hồ sơ clip ngược chiều bên dưới có thêm hướng hợp lệ. Các benchmark này chưa dùng cổng vào/ra và vùng parking được hiệu chỉnh tại hiện trường.

| Thiết bị | Frame skip | FPS xử lý | P95 (ms) | Bỏ chủ động | Rơi | Clip lưu / cảnh báo |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| CPU | 0 | 3,18 | 907 | 0 | 1.135 | 2/2 |
| CPU | 1 | 4,48 | 360 | 600 | 509 | 1/1 |
| CPU | 2 | 1,86 | 1.375 | 800 | 362 | 0/0 |
| CPU | 3 | 4,51 | 343 | 900 | 208 | 1/1 |
| CPU | Tự động | 4,56 | 335 | 1.107 | 1 | 1/1 |
| RTX 4050 Laptop | 0 | 18,19 | 79 | 0 | 832 | 1/1 |
| RTX 4050 Laptop | 1 | 18,20 | 94 | 600 | 232 | 1/1 |
| RTX 4050 Laptop | 2 | 19,18 | 94 | 800 | 14 | 1/1 |
| RTX 4050 Laptop | 3 | 13,05 | 156 | 900 | 37 | 2/2 |
| RTX 4050 Laptop | Tự động | 13,61 | 63 | 914 | 12 | 2/2 |

P95 đến lúc frame được chuẩn bị cho dashboard và được chuyển vào bộ xuất bằng chứng. Tổng thời gian phiên bao gồm cả khởi động mô hình và chờ mã hóa clip. CSV chứa thêm P50, RAM tiến trình, VRAM tensor PyTorch, số lượt qua vạch và đối chiếu tổng frame. [Ma trận đầy đủ](runs/realtime-matrix/comparison.csv)

## Tracking và đếm xe

Nhãn camera thử nghiệm gồm 11 hộp xe tại các giây 0, 2, 3, 4 trong ROI `[400, 360, 1480, 880]` và 8 cặp vùng/giây được đếm độc lập. Một phần khung ở đầu video lặp hình do video nguồn tạm dừng. IDF1 dưới đây chỉ áp dụng cho các khung và ROI đã chấm.

| Thiết bị | Skip | IDF1 | ID switches quan sát | Khung có dự đoán | MAE đếm (xe) |
| --- | ---: | ---: | ---: | ---: | ---: |
| CPU | 0 | 0,80 | 0 | 4/4 | 0,25 |
| CPU | 1 | 0,90 | 0 | 4/4 | 0,38 |
| CPU | 2 | 0,84 | 0 | 4/4 | 0,38 |
| CPU | 3 | 0,78 | 0 | 3/4 | 0,17 (6/8 nhãn) |
| CPU | Tự động | 0,86 | 0 | 4/4 | 0,12 |
| GPU | 0 | 1,00 | 0 | 4/4 | 0,00 |
| GPU | 1 | 1,00 | 0 | 4/4 | 0,00 |
| GPU | 2 | 0,91 | 1 | 4/4 | 0,00 |
| GPU | 3 | 1,00 | 0 | 4/4 | 0,00 |
| GPU | Tự động | 1,00 | 0 | 4/4 | 0,00 |

## Cảnh báo theo đúng xe

Clip demo có hai ô tô được đánh dấu đi về camera trên phần đường đi xa camera trong đoạn 46–53 giây. Trên lần chạy GPU tự động dài 56 giây, trong đoạn được gán nhãn có 2 TP, 0 FP và 0 FN. Sai lệch thời điểm tuyệt đối trung bình là 0,70 giây theo mốc đánh dấu. Phiên lưu 8/8 clip cảnh báo, tính cả các sự kiện nằm ngoài đoạn chấm. [Kết quả chấm](runs/realtime-demo-annotated/cuda0-skip-auto-1/accuracy.json) · [Kết quả xuất clip](runs/realtime-demo-annotated/comparison.csv)

Chạy lại các mức skip 0–3 và tự động trên GPU với bản cắt 42–56 giây của cùng clip, dịch nhãn theo 42 giây. Cả năm chế độ khớp 2/2 ca trong khoảng đã gán nhãn; sai lệch thời điểm tuyệt đối trung bình dao động 0,65–0,83 giây. Tỷ lệ cảnh báo sai bằng 0 trong khoảng chấm 7 giây. Kết quả này chỉ kiểm tra độ nhạy với frame skip trên hai ca đó. [So sánh theo frame skip](runs/realtime-wrongway-ablation/alert_comparison.csv)

Một ca đổi hướng (Dangerous) được gán nhãn trên clip demo tại 13,75 giây. Phiên GPU tự động ghép đúng xe và cảnh báo sớm hơn mốc gán nhãn 0,30 giây. Cửa sổ chấm 2,5 giây có 1 TP, 0 FP và 0 FN. Cần thêm ca thật để ước lượng độ chính xác của lớp này. Với nhanh/chậm tương đối, đã đánh dấu các điểm quỹ đạo trên video thử nghiệm để kiểm tra nhóm xe so sánh. Chưa có nhãn sự kiện đủ điều kiện để tính precision và recall cho hai lớp đó. [Nhật ký gán nhãn](labels/ANNOTATION_NOTES.md)

## Dự báo sau 5 phút

So sánh trên video thử nghiệm với 9 số đếm độc lập tại đích dự báo, trải trên 5 mốc thời gian. Các mô hình dùng số xe YOLO/ByteTrack làm lịch sử đầu vào. GRU huấn luyện trên các cửa sổ có đích trước giây 840; mỗi dự báo trên tập chấm dùng 60 giây lịch sử từ sau mốc chia và đích cách mốc dự báo 300 giây.

| Phương pháp | MAE (xe) | RMSE (xe) |
| --- | ---: | ---: |
| Giữ giá trị cuối | 1,89 | 2,03 |
| Trung bình 60 giây | 1,03 | 1,14 |
| GRU | 1,15 | 1,30 |

Giữ trung bình 60 giây cho dashboard. So sánh này dùng một video, các cửa sổ huấn luyện chồng lấp và chỉ một lượt khởi tạo GRU. [Nhãn đếm](labels/pilot_camera_forecast_counts.csv) · [Kết quả từng dự báo](runs/pilot_camera-forecast-pilot/predictions.csv)
