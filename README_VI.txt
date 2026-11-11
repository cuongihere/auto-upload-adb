TRÌNH QUẢN LÝ ANDROID SCRCPY v1.2 - HƯỚNG DẪN NHANH
====================================================

Mục đích
--------
App quản lý nhiều điện thoại Android cắm vào PC.
Mỗi điện thoại được gán 1 cửa sổ scrcpy riêng để điều khiển.

Chức năng đã có
---------------
1. Quét nhiều máy Android bằng ADB.
2. Hiện serial, model, trạng thái device/unauthorized/offline.
3. Lưu profile riêng theo serial máy.
4. Mở scrcpy cho từng máy.
5. Mở scrcpy tất cả máy online.
6. Tắt scrcpy từng máy / tắt tất cả.
7. Tự xếp cửa sổ scrcpy theo lưới.
8. Preset chất lượng: Thấp - nhiều máy / Cân bằng / Cao / Tùy chỉnh.
9. Mở app theo package name.
10. Tắt cưỡng bức app.
11. Khởi động lại app.
12. Reboot máy.
13. Nút Home / Back.
14. Chụp màn hình về thư mục screenshots.
15. Chạy lệnh ADB shell nhanh.
16. Tắt/bật màn hình điện thoại ngay bằng ADB keyevent.
17. Tắt màn hình khi bắt đầu điều khiển bằng scrcpy.
18. Giữ màn hình tắt sau khi thoát scrcpy bằng --power-off-on-close.
19. Khi app tự tắt scrcpy, app gửi thêm KEYCODE_SLEEP trước/sau khi đóng để tránh màn sáng lại.
20. Toàn bộ giao diện chính đã đổi sang tiếng Việt có dấu.
21. Tự tải scrcpy portable vào tools/scrcpy nếu máy có Internet.

Cách chạy bản portable
----------------------
1. Copy NGUYÊN thư mục AndroidScrcpyManager vào USB hoặc máy khác.
2. Bấm đúp run.vbs để mở app không hiện cửa sổ CMD.
3. Nếu cần xem lỗi chi tiết, chạy run.bat.

Không cần cài Python, pip, PySide6 hoặc scrcpy. Tất cả đã nằm trong thư mục app:
- runtime\python\            Python Embedded 3.12
- runtime\site-packages\     PySide6 và thư viện Python
- tools\scrcpy\              scrcpy, adb và các DLL đi kèm
- config\                    cấu hình riêng của app
- logs\                      log scrcpy
- screenshots\               ảnh chụp từ điện thoại

Có thể chạy KIEM_TRA_PORTABLE.bat trước khi mang đi để kiểm tra đủ file.

Lưu ý khi dùng USB:
- Copy toàn bộ thư mục, không copy riêng run.vbs hoặc main.py.
- Nên thoát app và các cửa sổ scrcpy trước khi rút USB.
- Máy Windows vẫn có thể cần driver USB của hãng điện thoại để ADB nhận thiết bị.
- Nếu Windows chặn file tải từ máy khác, chọn Properties > Unblock cho file ZIP trước khi giải nén.

Nếu thiếu scrcpy
---------------
Điều đó có nghĩa thư mục app đã được copy thiếu. Hãy copy lại nguyên thư mục từ bản gốc.
Hai file tối thiểu phải có:
tools\scrcpy\scrcpy.exe
tools\scrcpy\adb.exe

Cần bật gì trên điện thoại?
---------------------------
1. Bật Developer options.
2. Bật USB debugging.
3. Cắm cáp USB vào PC.
4. Trên điện thoại bấm Allow USB debugging khi hiện thông báo RSA.

Trạng thái thiết bị
-------------------
device:
- Máy sẵn sàng dùng.

unauthorized:
- Điện thoại chưa bấm Allow USB debugging.

offline:
- Kết nối ADB lỗi, rút cắm lại cáp hoặc tắt/bật USB debugging.

Tùy chọn tắt màn hình
---------------------
Có 3 chức năng riêng:

1. "Tắt màn hình điện thoại khi điều khiển"
- Thêm option --turn-screen-off khi mở scrcpy.
- Chỉ có hiệu lực lúc scrcpy bắt đầu chạy.

2. "Giữ màn hình tắt sau khi thoát scrcpy"
- Thêm option --power-off-on-close khi mở scrcpy.
- Khi đóng cửa sổ scrcpy theo cách bình thường, scrcpy sẽ cố giữ màn hình điện thoại ở trạng thái tắt.
- Khi tắt scrcpy bằng nút trong app hoặc thoát app, app sẽ gửi thêm lệnh KEYCODE_SLEEP để ép màn hình tắt lại.

3. "Tắt màn hình ngay"
- Gửi lệnh ADB:
  adb shell input keyevent KEYCODE_SLEEP
- Dùng khi scrcpy đang chạy rồi mới muốn tắt màn hình.

Nếu điện thoại vẫn tự sáng lại
------------------------------
Kiểm tra trên điện thoại:
Developer options > Stay awake > OFF

Hoặc chạy trong ô ADB shell nhanh:
settings put global stay_on_while_plugged_in 0

Ghi chú: một số máy/ROM có cơ chế tự bật màn hình khi cắm USB, khi nhận thông báo, hoặc khi app nền gọi wake lock. Khi đó cần tắt thêm các cơ chế đánh thức màn hình trên máy.

Package name là gì?
-------------------
Ví dụ:
com.facebook.katana
com.zhiliaoapp.musically
com.android.settings

Dùng nút "Mở app package" để mở app.
Dùng "Khởi động lại app" để force-stop rồi mở lại app.

Gợi ý nếu chạy nhiều máy
------------------------
Dùng preset Thấp hoặc Cân bằng:
- Thấp: nhẹ máy, hợp với 10+ điện thoại.
- Cân bằng: ổn định, hình ảnh vừa đủ.
- Cao: đẹp hơn nhưng tốn CPU/RAM hơn.

Nên đặt kích thước cửa sổ:
- 300 x 600 nếu nhiều máy.
- 360 x 720 nếu màn hình PC rộng.
- 420 x 840 nếu cần thao tác chi tiết.

File cấu hình
-------------
config\device_profiles.json
config\app_settings.json

Ảnh chụp màn hình
-----------------
screenshots\

Log scrcpy
----------
logs\

Ghi chú kỹ thuật
----------------
Bản MVP này không nhúng màn hình scrcpy vào UI.
Lý do: ổn định hơn khi chạy nhiều điện thoại.
Mỗi scrcpy là 1 process riêng, app chỉ quản lý scan/mở/tắt/xếp cửa sổ/điều khiển nhanh.

Nếu cần nâng cấp tiếp:
- Gán từng máy vào nhóm kèo/node.
- Auto restart app theo lịch.
- Watchdog: nếu máy mất kết nối thì cảnh báo.
- Kết nối Wi-Fi ADB.
- Dashboard nhúng scrcpy vào trong UI bằng Win32 SetParent.

============================================================
CHẠY BẰNG RUN.VBS
============================================================

File run.vbs đã được thêm vào thư mục gốc của app.

Cách dùng:
- Mở thư mục AndroidScrcpyManager.
- Bấm đúp run.vbs.

Ưu điểm:
- Không phụ thuộc thư mục đang mở CMD/Explorer.
- Tự lấy đúng đường dẫn thư mục chứa app.
- Luôn dùng runtime Python portable trong chính thư mục app.
- Không phụ thuộc Python hay thư viện đã cài trên máy Windows.

Lưu ý:
- Không tách riêng run.vbs ra khỏi thư mục app.
- Nếu muốn để ngoài Desktop, hãy tạo Shortcut trỏ tới run.vbs, không copy riêng file run.vbs.
