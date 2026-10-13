@echo off
setlocal
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
    echo Backend Python environment is missing.
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo Frontend dependencies are missing. Run npm.cmd install first.
    pause
    exit /b 1
)

start "LearnPilot Backend" /D "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000"

start "LearnPilot Frontend" /D "%~dp0frontend" cmd /k "npm.cmd run dev -- --port 5173 --strictPort"

timeout /t 5 /nobreak >nul
start "" "http://localhost:5173"

endlocal