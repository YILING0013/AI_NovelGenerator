@echo off
rem ============================================================
rem  Viet Tieu Thuyet - TAT toan bo ung dung
rem  Du lieu truyen (MongoDB) van nam trong thu muc mongodata, khong bi xoa.
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stack.ps1" stop
pause
