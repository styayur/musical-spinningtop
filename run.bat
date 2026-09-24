@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [SpinningTop] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 goto :err
)

".venv\Scripts\python.exe" -c "import flask, requests" >nul 2>&1
if errorlevel 1 (
    echo [SpinningTop] Installing dependencies...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 goto :err
)

".venv\Scripts\python.exe" app.py %*
if errorlevel 1 goto :err
goto :eof

:err
echo.
echo Could not start Spinning Top. Check Python 3.9+ and the messages above.
pause
exit /b 1
