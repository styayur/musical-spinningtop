@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [SpinningTop] First run: creating virtual environment and installing dependencies...
    python -m venv .venv
    if errorlevel 1 goto :err
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 goto :err
)

".venv\Scripts\python.exe" app.py %*
goto :eof

:err
echo.
echo Failed to set up the environment. Please check that Python 3.9+ is installed and on PATH.
pause
exit /b 1
