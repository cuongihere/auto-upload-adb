@echo off
setlocal
cd /d "%~dp0"

if not exist "runtime\python\python.exe" (
    echo [LOI] Khong tim thay runtime\python\python.exe
    echo Hay copy lai day du toan bo thu muc app.
    pause
    exit /b 1
)

if not exist "tools\scrcpy\scrcpy.exe" (
    echo [LOI] Khong tim thay tools\scrcpy\scrcpy.exe
    echo Hay copy lai day du toan bo thu muc app.
    pause
    exit /b 1
)

"runtime\python\python.exe" main.py
if errorlevel 1 pause
