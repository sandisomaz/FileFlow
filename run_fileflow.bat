@echo off
set "VENV_PATH=.venv"
if exist "%VENV_PATH%\Scripts\python.exe" (
    echo [FileFlow] Using virtual environment...
    "%VENV_PATH%\Scripts\python.exe" desktop_app.py
) else (
    echo [FileFlow] Virtual environment not found. Running with global python...
    python desktop_app.py
)
pause
