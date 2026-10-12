@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist ".venv\Scripts\pythonw.exe" (
    echo Missing .venv. Follow README.zh-CN.md to install the Python environment.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -c "from PySide6.QtWidgets import QApplication" >nul 2>&1
if errorlevel 1 (
    echo Launcher dependency missing. Run:
    echo .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" launcher.py
exit
