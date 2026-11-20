# Checklist triển khai pipeline giao thông tại nút giao

Thiết kế tham chiếu nằm trong [INTERSECTION_PIPELINE.md](../docs/INTERSECTION_PIPELINE.md). Checklist này dành cho phiên bản một camera, ưu tiên độ trễ thấp. Đánh dấu hoàn thành khi có đầu ra và bằng chứng kiểm tra tương ứng.

## 1. Chốt dữ liệu và phép thử

- [ ] Chọn một camera thấy được nhánh vào và các nhánh ra cần đánh giá.
- [ ] Kiểm tra trọn clip để xác định vùng bị che, chuyển góc, mất hình và timestamp.
- [ ] Ghi metadata gồm nguồn, thời lượng, độ phân giải, FPS và điều kiện quan sát.
- [ ] Loại tệp trùng khỏi phép chia dữ liệu, đặc biệt hai thư mục Láng Hạ – Thái Hà đã phát hiện trùng.
- [ ] Chia clip hoặc phiên thành tập chỉnh cấu hình và tập kiểm thử giữ riêng.
- [ ] Xác minh hướng đi được phép, làn dùng chung và điều kiện rẽ phải của camera đã chọn.
- [ ] Chốt loại cảnh báo đầu tiên và cách gán nhãn sự kiện.
- [ ] Chọn thiết bị đích và ghi cấu hình CPU, GPU, RAM cùng phiên bản thư viện.

**Đầu ra cần có** gồm danh sách clip theo vai trò, metadata và bản mô tả quy định hướng đi đã xác minh.

## 2. Đo pipeline hiện tại

- [ ] Chạy YOLOv8s và ByteTrack trên video đã chọn, xử lý mọi khung sẵn có trước khi thử bỏ khung.
- [ ] Kiểm tra ánh xạ bốn lớp và tọa độ hộp về ảnh nguồn.
- [ ] Xuất quỹ đạo có ID, thời điểm và điểm chân xe.
- [ ] Đo FPS, P50/P95 worker, khung rơi và mức sử dụng bộ nhớ.
- [ ] Lưu cấu hình và kết quả cơ sở để so sánh về sau.

**Điều kiện hoàn thành** là đối chiếu được bản ghi với đúng xe và đúng thời điểm trên video.

## 3. Cấu hình làn, vùng và vạch

- [ ] Tạo hồ sơ camera có phiên bản và kích thước ảnh nguồn.
- [ ] Vẽ vùng tiếp cận của từng làn trong nhánh được chọn.
- [ ] Vẽ vạch vào và các vạch ra có hướng.
- [ ] Định nghĩa vùng giao cắt, vùng chồng lấn và vùng chưa rõ làn.
- [ ] Tạo bảng hướng đi được phép từ làn lúc vào tới nhánh ra.
- [ ] Kiểm tra overlay trên nhiều thời điểm và lưu ảnh minh họa cấu hình.

**Đầu ra cần có** là cấu hình camera và video hoặc ảnh xác nhận vùng/vạch khớp góc quay.

## 4. Gán làn và ghi hành trình

- [ ] Lưu `origin_lane`, `current_lane`, `lane_at_entry` và tập làn khả dĩ theo ID.
- [ ] Thêm điều kiện duy trì theo thời gian để giảm dao động ở ranh giới làn.
- [ ] Ghi cắt đoạn vạch hữu hạn và chiều cắt từ hai quan sát đủ chất lượng.
- [ ] Chống ghi lặp khi xe rung quanh vạch hoặc đứng trên vạch.
- [ ] Ghi nhánh ra khi có đủ bằng chứng qua vạch ra.
- [ ] Đánh dấu vết mới xuất hiện giữa nút, mất quan sát và bước nhảy tọa độ.
- [ ] Chặn sự kiện qua vạch tạo từ khoảng mất vết quá dài.
- [ ] Xuất hành trình và trạng thái chất lượng để rà soát.

**Điều kiện hoàn thành** là đối chiếu được làn lúc vào, thứ tự qua vạch và nhánh ra trên các xe gán nhãn, bao gồm các trường hợp chưa rõ.

## 5. Ước lượng hành vi nhóm cùng hướng

- [ ] Xác định vùng hàng chờ và nhóm hướng cần so sánh.
- [ ] Chọn xe tham chiếu gần vạch, đủ lịch sử và cùng hướng dự kiến.
- [ ] Loại xe đang được chấm khỏi nhóm tham chiếu.
- [ ] Tính số xe, tỷ lệ dừng, tốc độ trung vị và lượt qua vạch theo cửa sổ quá khứ.
- [ ] Triển khai trạng thái chờ, giải phóng và chưa rõ.
- [ ] Thêm thời gian duy trì và ngưỡng vào/thoát để giảm nhấp nháy.
- [ ] Hiệu chỉnh ngưỡng trên tập chỉnh cấu hình rồi cố định trước khi kiểm thử.
- [ ] Kiểm tra riêng chuyển pha, ùn tắc, làn rẽ phải và nhóm xe cùng đi qua.

**Đầu ra cần có** là chuỗi trạng thái nhóm kèm số xe tham chiếu và lý do chuyển trạng thái.

## 6. Kết hợp luật và tạo sự kiện

- [ ] Tích hợp luật ngược chiều hiện có với hướng của nhánh đã cấu hình.
- [ ] Đối chiếu làn lúc vào và nhánh ra để gắn cờ nghi rẽ sai hướng.
- [ ] Gắn cờ qua vạch khi dòng cùng hướng đang chờ.
- [ ] Kiểm tra quy định rẽ phải theo cấu hình và chất lượng bằng chứng.
- [ ] Giữ trạng thái cần xem lại khi các làn khả dĩ dẫn tới kết luận khác nhau.
- [ ] Tạo khóa chống trùng và cho phép cập nhật sự kiện khi có thêm bằng chứng.
- [ ] Lưu thời điểm phát ban đầu, thời điểm đủ bằng chứng, ID và lý do.
- [ ] Nếu đánh giá nghi vượt đèn đỏ, gán nhãn tín hiệu đúng hướng độc lập với thuật toán.

**Điều kiện hoàn thành** là mỗi cảnh báo truy được tới xe, quỹ đạo, cấu hình luật và đoạn video liên quan.

## 7. Dashboard và bằng chứng

- [ ] Hiển thị ID, làn, vùng và vạch trên video.
- [ ] Hiển thị trạng thái nhóm, cảnh báo và lý do cần xem lại.
- [ ] Cho mở clip bằng chứng theo sự kiện.
- [ ] Hiển thị timestamp nguồn và tuổi snapshot.
- [ ] Hiển thị trạng thái mất nguồn và dữ liệu cũ.
- [ ] Đưa ghi CSV và mã hóa clip qua worker nền có hàng đợi giới hạn.
- [ ] Ghi lỗi, clip bị bỏ vì bận và bản ghi mất nếu có.
- [ ] Kiểm tra dừng phiên, đổi nguồn và hoàn tất tệp đầu ra.

## 8. Dữ liệu dài và dự báo GRU

- [ ] Thu hoặc chọn video liên tục đủ dài cho lịch sử và đích sau 5 phút.
- [ ] Tổng hợp số xe hiện diện theo vùng trên khoảng lấy mẫu đều.
- [ ] Ghi riêng số xe dừng và lượt vào–ra để thử làm đặc trưng bổ sung.
- [ ] Đánh dấu thiếu dữ liệu và độ phủ của từng mẫu.
- [ ] Tách phiên hoặc thời gian trước khi tạo cửa sổ huấn luyện.
- [ ] Fit scaler trên train và dùng cùng scaler cho validation/test.
- [ ] Huấn luyện GRU cơ sở từ số xe của vùng đích.
- [ ] So với giữ giá trị cuối và trung bình 60 giây trên cùng mốc đích.
- [ ] Thử GRU bổ sung đặc trưng khi có đủ dữ liệu.
- [ ] Lưu mô hình, scaler, cấu hình, MAE/RMSE và số mốc chấm.
- [ ] Chạy suy luận GRU theo lịch từ bản sao lịch sử có timestamp.

**Đầu ra cần có** là tập chuỗi có nguồn rõ ràng, mô hình tái nạp được và bảng so sánh trên cùng nhãn đích.

## 9. Phân bổ tài nguyên và tối ưu realtime

- [ ] Thử YOLO trên GPU và GRU nhỏ trên CPU trên thiết bị đích.
- [ ] Giữ hàng đợi khung tối đa một khung chờ.
- [ ] Giới hạn GRU ở một công việc chạy và tối đa một yêu cầu chờ mới nhất.
- [ ] Tránh giữ khóa snapshot trong lúc suy luận, ghi đĩa hoặc mã hóa.
- [ ] Gắn kết quả dự báo với đúng phiên, thời điểm gốc và thời điểm đích.
- [ ] So tracking/cảnh báo cơ sở với chế độ bật thêm GRU.
- [ ] Đo tiếp khi bật đủ dashboard, CSV và clip.
- [ ] Chốt ngân sách P95 và tần suất cập nhật từ kết quả cơ sở.
- [ ] Nếu detector là nút thắt, thử model nhỏ hoặc TensorRT/OpenVINO và đo lại chất lượng.
- [ ] Nếu worker nền gây tranh chấp, thử giới hạn luồng CPU hoặc tách tiến trình rồi đo lại.

**Điều kiện hoàn thành** là có bảng so P95, FPS, khung rơi, tuổi snapshot, CPU và bộ nhớ của các cấu hình được chọn.

## 10. Gán nhãn và đánh giá đóng góp

- [ ] Hoàn thiện hộp và ID theo chuỗi trên các đoạn đánh giá tracking.
- [ ] Gán nhãn làn lúc vào, mốc qua vạch và nhánh ra.
- [ ] Gán nhãn sự kiện và quy định cửa sổ ghép cảnh báo theo đúng xe.
- [ ] Chấm luật góc hiện tại làm mốc cho ngược chiều.
- [ ] Chấm luật hành trình gán cứng một làn.
- [ ] Chấm luật hành trình có tập làn khả dĩ và trạng thái cần xem lại.
- [ ] Giữ cùng đầu ra tracking khi so các bộ luật.
- [ ] Báo cáo precision, recall, F1, số TP/FP/FN, gán đúng xe và tỷ lệ chưa kết luận.
- [ ] Báo cáo IDF1, IDSW, MOTA/MOTP với quy ước MOTP được ghi rõ.
- [ ] Tách thời gian đợi bằng chứng khỏi thời gian thực thi thuật toán.
- [ ] Phân tích riêng rẽ hợp lệ, rẽ sai, ngược chiều, mất ID, sát biên làn và ùn tắc.
- [ ] Tổng hợp kết quả theo clip và camera để thể hiện phạm vi khái quát.

## 11. Hoàn thiện báo cáo và demo

- [ ] Cập nhật kiến trúc và định nghĩa các loại cảnh báo theo chức năng đã hoàn thành.
- [ ] Đưa ví dụ đúng, sai và chưa đủ bằng chứng vào báo cáo.
- [ ] Trình bày cải tiến bằng phép so sánh bộ luật trên cùng dữ liệu.
- [ ] Công bố giới hạn về FPS nguồn, số camera, số nhãn và dữ liệu dự báo.
- [ ] Ghi lại hướng dẫn tái chạy cùng phiên bản mô hình và cấu hình.
- [ ] Chuẩn bị demo một camera, cảnh báo có clip và dự báo có mốc đích rõ.
- [ ] Đối chiếu bảng số liệu, hình và kết luận với kết quả đã lưu.

## Thứ tự thực hiện

Ưu tiên mục 1–4 để có dữ liệu hành trình đáng tin. Tiếp theo làm mục 5–7 để hoàn thiện cảnh báo và bằng chứng. Mục 8 tiến hành khi đã có video dài. Mục 9 được đo từ mức cơ sở và cập nhật khi thêm thành phần. Mục 10 dùng tập giữ riêng để kết luận, sau đó hoàn thiện mục 11.
