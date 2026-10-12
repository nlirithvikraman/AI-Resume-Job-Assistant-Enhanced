@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto fail
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
pause
exit /b
:fail
echo Setup failed. Install Python 3.11 or newer and check your internet connection.
pause
exit /b 1
