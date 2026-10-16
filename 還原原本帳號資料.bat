@echo off
setlocal
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
    echo Python environment is missing. Run the package installer first.
    pause
    exit /b 1
)
echo Close all LearnPilot backend windows before restoring data.
"backend\.venv\Scripts\python.exe" "backend\restore_local_data.py"
if errorlevel 1 pause
endlocal
