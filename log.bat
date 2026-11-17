@echo off
rem ============================================================
rem  Viet Tieu Thuyet - XEM LOG (30 dong cuoi moi dich vu)
rem  Log nam trong ..\runtime\logs
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stack.ps1" logs
echo.
echo File log: %~dp0..\runtime\logs
pause
