@echo off
chcp 65001 >nul
cd /d %~dp0
start "" ".venv\Scripts\pythonw.exe" launcher.py
exit