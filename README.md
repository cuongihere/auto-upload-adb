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
