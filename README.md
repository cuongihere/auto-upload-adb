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


## Auto Upload (bản thử nghiệm)

Ứng dụng giữ nguyên quản lý nhiều điện thoại qua ADB/scrcpy và bổ sung tab **Auto Upload**.

**Cách dùng:**
1. Kết nối điện thoại bằng USB, bật USB debugging, cấp quyền ADB và đăng nhập TikTok/Facebook trên điện thoại.
2. Trong bảng thiết bị của ứng dụng, chọn dòng hoặc tick các máy có trạng thái `device`.
3. Mở tab **Auto Upload**, kéo thả video MP4/MOV/M4V/3GP từ PC.
4. Chọn TikTok/Facebook và nhập caption cho từng nền tảng.
5. Nhấn **Bắt đầu chuyển video / đăng**. App copy video tới `/sdcard/DCIM/Camera`, đối chiếu kích thước tệp, thử tra MediaStore và gửi qua Android Share Intent vào app đã cài.
6. **Chế độ mặc định:** hoàn tất phần biên tập/đăng trên điện thoại rồi nhấn **Đã xử lý / Tiếp tục** để chuyển sang nền tảng hoặc video tiếp theo.

**Chế độ tự nhấn Đăng (thử nghiệm):** có thể bật bằng checkbox và xác nhận riêng. Chế độ này thử đọc XML giao diện Android bằng UIAutomator, tìm nút **Next/Đăng/Post** theo nhãn chính xác và nhập caption ASCII; chỉ thử bấm nút Đăng khi đã xác định được luồng. Do TikTok/Facebook thường cập nhật giao diện, không thể bảo đảm chạy hết mọi màn hình. Caption có dấu tiếng Việt/emoji sẽ chuyển sang thao tác thủ công để không làm hỏng nội dung. Facebook Reels, Facebook Page và đăng đa tài khoản **chưa được xác thực** trong bản này.

**Các trạng thái:**
- `prepared`: đã gửi video tới Android Share, chưa đăng.
- `manual_required`: cần thao tác trực tiếp trên điện thoại.
- `submitted_unverified`: đã thử nhấn nút Đăng, **không đồng nghĩa đăng thành công**.
- `error`: bước thao tác lỗi; kiểm tra nhật ký.

**Giới hạn cần biết:**
- MediaStore có thể không cập nhật ngay hoặc Android ROM có thể không xử lý Share Intent; khi đó app mở TikTok/Facebook và yêu cầu chọn video đã copy thủ công.
- Không root, không lưu mật khẩu. Không can thiệp API riêng tư của TikTok/Facebook.
- Đã kiểm tra tĩnh và có unit test; **chưa thử trên thiết bị thật**. Hãy thử bằng tài khoản và video riêng trước khi bật tự đăng.
- Lịch sử tiến trình nằm ở `logs/auto_upload_history.jsonl`, không chứa mật khẩu. Tệp video đã copy sẽ vẫn ở trên điện thoại để người dùng tự quản lý dung lượng.
- Khi đang dùng chế độ đồng bộ thao tác máy chính → máy con, nên tắt đồng bộ trước khi chạy Auto Upload để tránh tác động nhầm thiết bị.

Chạy kiểm tra cú pháp và unit test:

```powershell
python -m compileall -q main.py upload_engine.py auto_upload_tab.py
python -m unittest discover -s tests -v
```
