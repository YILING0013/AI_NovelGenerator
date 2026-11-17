@echo off
rem ============================================================
rem  Viet Tieu Thuyet - BAT toan bo ung dung (MongoDB + backend + website)
rem  Chay 1 cua so nay, mo trinh duyet tai http://127.0.0.1:3300
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stack.ps1" start
echo.
echo (Gate lay cua so nay de xem log. Dong cua so khong lam dung ung dung.)
pause
