@echo off
setlocal
set "TARGET_DIR=%~1"
if not defined TARGET_DIR set "TARGET_DIR=%USERPROFILE%\Downloads\learnpilot-react-gemini-fix\learnpilot-react"
for %%I in ("%TARGET_DIR%") do set "TARGET_DIR=%%~fI"
for %%I in ("%~dp0.") do set "SOURCE_DIR=%%~fI"
if /I "%TARGET_DIR%"=="%SOURCE_DIR%" goto samefolder
if not exist "%TARGET_DIR%\backend\main.py" goto missing
if not exist "%TARGET_DIR%\frontend\src\main.jsx" goto missing
if not exist "%SOURCE_DIR%\backend\password_reset.py" goto incomplete
if not exist "%SOURCE_DIR%\frontend\src\PasswordRecovery.jsx" goto incomplete
if not exist "%SOURCE_DIR%\frontend\src\GoalProgress.jsx" goto incomplete

echo Updating: %TARGET_DIR%
echo Close ALL LearnPilot backend and frontend windows before continuing.
echo Your .env, backend/data, .venv and node_modules will be preserved.
pause
set "BACKUP_DIR=%TARGET_DIR%\update-backup\full-update-%RANDOM%-%RANDOM%"
mkdir "%BACKUP_DIR%" >nul 2>nul
if errorlevel 1 goto failed
for %%F in ("%SOURCE_DIR%\backend\*.py") do (
    call :copyfile "backend\%%~nxF"
    if errorlevel 1 goto failed
)
for %%F in ("%SOURCE_DIR%\backend\tests\*.py") do (
    call :copyfile "backend\tests\%%~nxF"
    if errorlevel 1 goto failed
)
for %%F in ("%SOURCE_DIR%\frontend\src\*.jsx" "%SOURCE_DIR%\frontend\src\*.css") do (
    call :copyfile "frontend\src\%%~nxF"
    if errorlevel 1 goto failed
)
for %%F in (backend\requirements.txt backend\.env.example frontend\package.json frontend\package-lock.json frontend\.env.example README.md VALIDATION.md) do (
    call :copyfile "%%F"
    if errorlevel 1 goto failed
)
for %%F in ("%SOURCE_DIR%\*.bat") do (
    call :copyfile "%%~nxF"
    if errorlevel 1 goto failed
)
echo Update completed. Previous files: %BACKUP_DIR%
echo Refresh dependencies before restarting:
echo   backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
echo   cd frontend
echo   npm.cmd ci
echo Run those commands from the TARGET project folder, then restart LearnPilot.
echo Open http://localhost:5173 and press Ctrl+F5. The login page has a forgot-password button.
echo Email delivery requires Resend settings described in README.md.
pause
exit /b 0

:copyfile
set "RELATIVE_FILE=%~1"
if not exist "%SOURCE_DIR%\%RELATIVE_FILE%" exit /b 1
for %%D in ("%BACKUP_DIR%\%RELATIVE_FILE%" "%TARGET_DIR%\%RELATIVE_FILE%") do (
    if not exist "%%~dpD" mkdir "%%~dpD" >nul 2>nul
    if not exist "%%~dpD" exit /b 1
)
if exist "%TARGET_DIR%\%RELATIVE_FILE%" (
    copy /Y "%TARGET_DIR%\%RELATIVE_FILE%" "%BACKUP_DIR%\%RELATIVE_FILE%" >nul
    if errorlevel 1 exit /b 1
)
copy /Y "%SOURCE_DIR%\%RELATIVE_FILE%" "%TARGET_DIR%\%RELATIVE_FILE%" >nul
exit /b %errorlevel%

:missing
echo Target project not found: %TARGET_DIR%
echo Drag your EXISTING project folder onto this batch file to choose the correct target.
pause
exit /b 1
:samefolder
echo This folder already contains the new files. No copy is needed.
echo Update dependencies here, close old servers, then run the launcher in THIS folder.
pause
exit /b 0
:incomplete
echo The update source is incomplete. Download and extract the latest full GitHub ZIP.
pause
exit /b 1
:failed
echo Update failed. Do not restart until the update is completed or restored.
echo Previously overwritten files were backed up at: %BACKUP_DIR%
pause
exit /b 1
