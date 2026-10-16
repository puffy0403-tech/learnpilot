@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3.10 or later and enable Add Python to PATH.
    goto fail
)
where npm.cmd >nul 2>nul
if errorlevel 1 (
    echo Node.js was not found. Install a supported Node.js LTS version, then reopen this window.
    goto fail
)
if not exist "backend\.venv\Scripts\python.exe" (
    python -m venv backend\.venv
    if errorlevel 1 goto fail
)
"backend\.venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
if errorlevel 1 goto fail
pushd frontend
call npm.cmd install
if errorlevel 1 (
    popd
    goto fail
)
popd
if not exist "backend\.env" copy "backend\.env.example" "backend\.env" >nul
if not exist "frontend\.env" if exist "frontend\.env.example" copy "frontend\.env.example" "frontend\.env" >nul
echo Setup completed. Configure backend/.env for AI and then run the launcher.
pause
exit /b 0
:fail
echo Setup failed. Please send a screenshot of the error above.
pause
exit /b 1
