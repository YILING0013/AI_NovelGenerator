@echo off
REM Quick helper to create venv, install dev deps and run offline draft test
if not exist .venv (
  echo Creating virtual environment .venv
  python -m venv .venv
)
echo Activating virtual environment
call .venv\Scripts\activate.bat
echo Upgrading pip
python -m pip install --upgrade pip
echo Installing dev requirements
python -m pip install -r dev-requirements.txt
echo Running offline draft test
python tools_run_draft_test.py
echo Done.
pause
