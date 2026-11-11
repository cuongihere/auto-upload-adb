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


## Auto Upload kiểu thao tác trên điện thoại (Tap Flow)

Từ bản này, tab **Auto Upload** không dùng Android Share Intent để chuyển tới TikTok/Facebook nữa. App hoạt động giống người dùng thao tác trên màn hình thật (có thể quan sát trên khung scrcpy nhúng):

1. Copy và kiểm tra video PC → `/sdcard/DCIM/Camera/`.
2. **Bấm Home**, tìm icon TikTok/Facebook ở Home hoặc ngăn ứng dụng rồi **bấm icon**.
3. Tìm **Add post / Tạo video / Tạo reel**, bấm mở màn tạo nội dung.
4. Bấm **Upload / Tải lên**, mở album.
5. Chọn video vừa copy (ưu tiên tên tệp). Nếu album chỉ hiện hình thumbnail và người dùng bật lựa chọn thử nghiệm, chỉ thử chọn thumbnail đầu tiên **khi MediaStore xác nhận chính xác video đó là video mới nhất**.
6. Bấm **Next / Tiếp** tới màn hình caption.
7. Nhập caption ASCII được hỗ trợ; caption có dấu tiếng Việt, emoji hoặc ký tự đặc biệt chưa được nhập tự động bằng ADB an toàn.
8. Mặc định **dừng ở bước Đăng** để người dùng kiểm tra. Tùy chọn **Tự bấm Đăng cuối cùng** phải được bật và xác nhận trước khi chạy. Bấm Đăng không đồng nghĩa đã xuất bản thành công.

Nếu UI TikTok/Facebook thay đổi, quyền Android xuất hiện, không tìm được icon/nút/video hoặc bộ chọn file khác phiên bản đang hỗ trợ, app **dừng an toàn**, không chọn bừa. Ảnh chụp màn hình lỗi ở `logs/upload_screens/*.png`; mô tả các node UI (không lưu nội dung caption) ở `logs/upload_screens/*.txt`. Bật scrcpy nhúng để quan sát và thao tác thủ công khi app dừng. Nhấn **Đã xử lý / Tiếp tục** để tiếp tục hàng đợi.

**Hạn chế:** Luồng TikTok và Facebook vẫn phụ thuộc phiên bản ứng dụng, Android launcher và ROM; chưa kiểm nghiệm trực tiếp trên điện thoại Samsung SM-N960F của người dùng. Album Reel của Facebook, TikTok có nhiều tài khoản, chế độ ảnh/bài Story và xác minh bài đã xuất bản chưa được bảo đảm. Không cài APK phụ; chỉ dùng ADB, UIAutomator và thao tác chạm thật.
