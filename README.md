# Android Scrcpy Manager

Ứng dụng Windows quản lý nhiều điện thoại Android qua ADB và scrcpy, giao diện tiếng Việt dùng PySide6.

## Chạy từ mã nguồn

Yêu cầu Windows 10/11 và Python 3.10 trở lên. Trong thư mục dự án, chạy:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools\download_scrcpy_windows.py
.\.venv\Scripts\python.exe main.py
```

Bật USB debugging trên điện thoại, cắm USB và chấp nhận yêu cầu cấp quyền ADB.

## Chức năng

- Quét thiết bị, lưu profile và mở/tắt scrcpy cho từng máy hoặc nhiều máy.
- Xếp cửa sổ theo lưới, chọn chất lượng và điều khiển màn hình.
- Mở/tắt ứng dụng theo package, reboot, Home/Back, chạy ADB shell.
- Chụp màn hình và ghi log tại máy.

## Bản portable tại máy

Các launcher `run.bat`, `run.vbs`, `setup_and_run.bat` và phần hướng dẫn portable trong `README_VI.txt` yêu cầu bộ runtime đi kèm bản local. Repository chỉ lưu mã nguồn: không kèm `runtime/`, `tools/scrcpy/`, cấu hình thiết bị, log hoặc ảnh chụp. Clone repo mới thì dùng các lệnh cài đặt phía trên.

Ứng dụng tự tạo thư mục cấu hình và dữ liệu khi chạy. Xem `README_VI.txt` để biết thêm cách sử dụng.


## Auto Upload TikTok và lịch sử chống đăng trùng

1. Kết nối điện thoại, mở khóa, đăng nhập TikTok và chọn máy online.
2. Thêm video, nhập caption và nhấn **Bắt đầu thao tác trên điện thoại**.
3. App tính SHA-256 và kiểm tra lịch sử trước khi copy. Cùng nội dung video trên cùng nền tảng bị chặn trên mọi điện thoại, kể cả đổi tên hoặc chuyển thư mục. Video được mã hóa lại có nội dung byte khác nên chưa nhận diện là bản trùng.
4. App copy tới `/sdcard/DCIM/Camera/`, kiểm tra kích thước, cập nhật MediaStore, mở TikTok, bấm **Quay → thư viện → Video → chọn video → Tiếp → caption**. Nếu không thấy icon, app mở đúng package qua Android launcher. Việc chọn thumbnail đầu tiên chỉ diễn ra khi video vừa copy đứng đầu cả thứ tự ID và thời gian sửa trong MediaStore, trong tab Video.
5. Mặc định dừng ở màn hình Đăng. Bạn kiểm tra và đăng trên điện thoại, sau đó nhấn **Đã đăng thành công**. App lưu kết quả và mới chuyển sang video tiếp theo.
6. Tùy chọn **Tự bấm Đăng cuối cùng** ghi trạng thái bền vững trước khi chạm Đăng, sau đó chờ thông báo thành công rõ ràng. Nếu không đọc được thông báo, app dừng để bạn kiểm tra; không coi việc trở về trang chủ là bằng chứng đăng thành công.

**Khi dừng giữa luồng:** xử lý màn hình đang vướng rồi bấm **Tiếp tục bước đang dở** để thử lại chính bước đó. Không nhấn nút xác nhận đã đăng nếu chưa kiểm tra bài thật. Caption tiếng Việt/emoji cần nhập trên điện thoại/scrcpy; app đối chiếu đúng nội dung sau khi bạn nhấn Tiếp tục.

**Lịch sử:** bảng ngay trong tab Auto Upload, lưu trong `data/upload_history.sqlite3`, không bị mất khi đóng app. Trạng thái `published` là thông báo thành công đọc được từ ứng dụng; `published_manual` là người dùng xác nhận. Các trạng thái đang dở, chuẩn bị đăng, đã bấm Đăng chưa xác minh và cần kiểm tra đều chặn đăng lại. Bấm Dừng hay mất kết nối sau nút Đăng không gỡ chặn. Sau khi đối chiếu trên điện thoại, chọn dòng lịch sử và **Xác nhận bài đã đăng** hoặc **Xác nhận chưa đăng / Cho thử lại**. Lượt cũ không bị xóa; bản ghi mới được tạo nếu thử lại.

Lịch sử JSONL cũ được nhập một lần với trạng thái cần kiểm tra khi còn tìm được file gốc; các file cũ đã chuyển/xóa cần được kiểm tra thủ công. Các bài đăng bên ngoài app không tự được nhập. Sao lưu cả thư mục `data/` khi đổi máy; không xóa lịch sử nếu muốn giữ chống trùng. Nhật ký chi tiết vẫn ở `logs/auto_upload_history.jsonl`; ảnh lỗi ở `logs/upload_screens/`. Danh sách video/caption được giữ ở `config/upload_queue.json`. Dữ liệu này được Git bỏ qua.

Đã kiểm tra trên Samsung SM-N960F tới màn hình Đăng với video người dùng chọn; chưa xác thực một lượt xuất bản thật hoặc Facebook trên máy này. Giao diện TikTok/Android thay đổi có thể cần bổ sung selector. Quyền truy cập, đăng nhập, CAPTCHA và màn hình lạ cần người dùng xử lý. Tắt đồng bộ thao tác máy chính → máy con trước khi chạy Auto Upload.

Kiểm tra:

```powershell
python -m compileall -q main.py upload_engine.py upload_history.py tap_flow.py auto_upload_tab.py tests
python -m unittest discover -s tests -v
```

## Nhúng màn hình scrcpy vào ứng dụng (Windows)

- App mở **phóng to cửa sổ (Maximized)** theo kích thước màn hình Windows.
- Bên phải là khung **Màn hình điện thoại - scrcpy trực tiếp**. Khung này luôn hiện khi chuyển sang **Auto Upload**, giúp quan sát và click/thao tác lên màn hình điện thoại bằng chuột/bàn phím.
- Chọn hoặc tick **một** máy ở bảng thiết bị, bấm **Nhúng scrcpy đã chọn** (thanh công cụ hoặc nút trong khung bên phải). Máy đã chạy scrcpy ngoài app cũng có thể được nhúng nếu phiên scrcpy do ứng dụng quản lý.
- **Tách ra**: trả scrcpy về cửa sổ Windows riêng, giữ nguyên process/ADB. **Dừng scrcpy**: đóng phiên scrcpy đang nhúng. **Home/Back**: gửi phím tới điện thoại đang nhúng.
- **Mở tất cả (cửa sổ riêng)** vẫn giữ chế độ cũ để quản lý nhiều máy cùng lúc. Chỉ **một** máy hiển thị trong khung nhúng tại một thời điểm.
- Phóng to/thu nhỏ cửa sổ ứng dụng sẽ co giãn khung điện thoại. Không truyền hình ảnh qua Python; scrcpy tự render và nhận thao tác trong cửa sổ con.

### Lưu ý tương thích

Nhúng native HWND qua Win32 `SetParent` cần Windows 10/11, Qt/PySide6 và scrcpy đang chạy trong process do app quản lý. Một số phiên bản scrcpy/driver GPU/DPI có thể khiến việc nhúng không thành công: ứng dụng ghi lỗi, scrcpy vẫn mở ngoài để có thể điều khiển thủ công. Kiểm thử tự động bao gồm Windows UI smoke test, nhưng **chưa xác thực trực tiếp trên điện thoại Samsung hoặc Windows của người sử dụng**. Nếu khung đen, thử **Tách ra** rồi **Nhúng scrcpy** lại và gửi ảnh chụp cùng log.

Khi đang chạy Auto Upload, hãy giữ khung bên phải để kiểm tra thao tác trên TikTok/Facebook. Nút tự nhấn Đăng vẫn là tính năng thử nghiệm; có màn hình scrcpy không tự động đồng nghĩa với đăng video đã thành công.
