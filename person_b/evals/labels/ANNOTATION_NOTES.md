# Nhật ký gán nhãn hành vi

Mốc thời gian tính từ đầu tệp video. Đọc khung hình gốc, tự đặt ID cho từng xe và đánh dấu vị trí trước khi chạy bộ chấm. Tọa độ CSV tính theo pixel của từng video nguồn. Hộp bao và điểm chạm đường là ước lượng từ ảnh.

| Video | Khoảng đã xem | Nhãn và quyết định |
| --- | --- | --- |
| `data/goi_ban_giao_B/demo/clip_ngc.mp4` | 12,25–15,25 giây, bước 0,25 giây. Cửa sổ chấm là [12,75; 15,25). | `D01` là xe máy có người lái mặc áo tối, đổi từ hướng ra xa camera sang hướng ngang về bên trái. Mốc tham chiếu là 13,75 giây. Đây là nhãn đổi hướng rõ trên quỹ đạo ảnh theo nghĩa của lớp Dangerous. |
| `data/pilot_camera.mp4` | Xem từ 162 đến 167,5 giây, bước 0,5 giây. Đánh dấu 22 điểm trên 6 xe ở các mốc 165–166,5 giây. | `S01`, xe máy chở vật dài, là ứng viên nhanh tương đối do đi qua vùng nhanh hơn một số xe lân cận trên ảnh. Tại 165 giây, `S05` và `S06` đã cách `S01` hơn 0,15 chiều rộng ảnh trên trục ngang. Chưa xác nhận được nhóm 5 xe đối chiếu đủ gần, cùng vùng và cùng hướng trong ít nhất một giây. Đoạn này cũng chưa đủ bằng chứng để xác nhận xe chạy chậm tương đối. |

Tệp [sự kiện Dangerous](demo_dangerous_events.csv) và [hộp bao D01](demo_dangerous_anchors.csv) dùng được với `evals.score_realtime` và `--anchors-only`. Trong phiên GPU tự động đã lưu, bộ chấm ghép cảnh báo lúc 13,45 giây với D01 tại mốc 13,75 giây. [Kết quả trong cửa sổ chấm](../runs/realtime-demo-annotated/cuda0-skip-auto-1/dangerous_accuracy.json)

Tệp [điểm quỹ đạo camera thử nghiệm](pilot_camera_relative_review_points.csv) lưu quan sát để xây dựng bộ nhãn tốc độ tương đối. Hai điểm bị che khuất hoặc khó tách được bỏ trống bằng cách không tạo dòng cho xe ở thời điểm đó. Chỉ chuyển một trường hợp thành nhãn sự kiện khi xác nhận được quỹ đạo của xe đang xét và nhóm xe đủ điều kiện so sánh trong cùng khoảng thời gian.

## Sàng lọc video Hà Nội

Đã xem 9 khung lấy đều trên mỗi clip của bốn nút giao. Ưu tiên Giảng Võ – Láng Hạ ở giây 29–33 vì một nhóm xe máy cùng đi ra xa camera sau khi rời vạch dừng. Láng Hạ – Thái Hà ở giây 22–27 là đoạn ứng viên thứ hai. Hàng Bông – Hàng Trống có hướng xe dễ phân biệt hơn nhưng ít xe đi sát cùng lúc trong các khung đã xem. Lý Thường Kiệt – Hàng Bài có giao cắt nhiều hướng và phản sáng trên mặt đường. [Danh sách tệp nguồn](../runs/annotation-preview/hanoi-screen-sources.json)

Tại Giảng Võ – Láng Hạ, dùng clip `16h30.25.9.22.mp4` (640 × 480) và đánh dấu điểm chạm đường của 7 xe máy từ khung 176 đến 192, mỗi 4 khung một mẫu. CSV lưu cả số khung và PTS đọc từ video (29,352–31,992 giây). Khi đối chiếu với lượt replay tạo thời gian theo số khung chia FPS trung bình, dùng số khung để quy đổi về cùng hệ thời gian. [35 điểm quỹ đạo](giang_vo_lang_ha_peer_points.csv)

Phép kiểm tra sơ bộ dùng tốc độ dịch chuyển giữa hai điểm liền kề, bán kính chuẩn hóa 0,15 và cosin hướng lớn hơn 0,85. Trong nhóm đã đánh dấu, những mẫu có đủ 5 xe đối chiếu cho tỷ lệ tốc độ so với trung vị từ 0,78 đến 1,42. Các tỷ lệ này chưa vượt ngưỡng mặc định 1,8 hoặc thấp hơn 1/1,8. Đây là mẫu quan sát nhóm xe, chưa phải nhãn sự kiện nhanh/chậm. Để chấm một ca, cần đánh dấu cả đối tượng và các xe đối chiếu qua một khoảng đủ dài để kiểm tra điều kiện duy trì.
