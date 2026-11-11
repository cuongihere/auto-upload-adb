@echo off
setlocal
cd /d "%~dp0"

echo ==============================================
echo KIEM TRA ANDROID SCRCPY MANAGER PORTABLE
echo ==============================================

set "FAILED=0"

if not exist "runtime\python\python.exe" (
    echo [THIEU] runtime\python\python.exe
    set "FAILED=1"
)
if not exist "runtime\site-packages\PySide6\__init__.py" (
    echo [THIEU] runtime\site-packages\PySide6
    set "FAILED=1"
)
if not exist "tools\scrcpy\adb.exe" (
    echo [THIEU] tools\scrcpy\adb.exe
    set "FAILED=1"
)
if not exist "tools\scrcpy\scrcpy.exe" (
    echo [THIEU] tools\scrcpy\scrcpy.exe
    set "FAILED=1"
)
if not exist "main.py" (
    echo [THIEU] main.py
    set "FAILED=1"
)

if "%FAILED%"=="1" goto :failed

"runtime\python\python.exe" -c "import PySide6, main; assert main.adb_path(); assert main.scrcpy_path(); print('[OK] Python, PySide6, main.py, ADB va scrcpy')"
if errorlevel 1 goto :failed

"tools\scrcpy\adb.exe" version
if errorlevel 1 goto :failed

"tools\scrcpy\scrcpy.exe" --version
if errorlevel 1 goto :failed

echo.
echo [HOAN TAT] Folder app da san sang de copy sang USB.
pause
exit /b 0

:failed
echo.
echo [LOI] Ban portable dang thieu file hoac runtime khong chay duoc.
echo Hay copy lai NGUYEN thu muc app.
pause
exit /b 1
