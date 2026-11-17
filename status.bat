@echo off
rem ============================================================
rem  Viet Tieu Thuyet - KIEM TRA ung dung dang chay hay dung
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stack.ps1" status
pause
