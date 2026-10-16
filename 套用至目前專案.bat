@echo off
setlocal
set "TARGET_DIR=%~1"
if not defined TARGET_DIR set "TARGET_DIR=%USERPROFILE%\Downloads\learnpilot-react-gemini-fix\learnpilot-react"
echo Updating: %TARGET_DIR%
echo Please close the LearnPilot backend and frontend windows before updating.
if not exist "%TARGET_DIR%\backend\chat_planner.py" goto missing
if not exist "%TARGET_DIR%\frontend\src\main.jsx" goto missing
set "BACKUP_DIR=%TARGET_DIR%\update-backup\chat-reservations-%RANDOM%"
mkdir "%BACKUP_DIR%\frontend\src" >nul 2>nul
mkdir "%BACKUP_DIR%\backend" >nul 2>nul
if errorlevel 1 goto failed
for %%F in (main.jsx PlanningChat.jsx features.jsx style.css) do (
    copy /Y "%TARGET_DIR%\frontend\src\%%F" "%BACKUP_DIR%\frontend\src\%%F" >nul
    if errorlevel 1 goto failed
)
for %%F in (chat_planner.py planning.py) do (
    copy /Y "%TARGET_DIR%\backend\%%F" "%BACKUP_DIR%\backend\%%F" >nul
    if errorlevel 1 goto failed
)
for %%F in (main.jsx PlanningChat.jsx features.jsx style.css) do (
    copy /Y "%~dp0frontend\src\%%F" "%TARGET_DIR%\frontend\src\%%F" >nul
    if errorlevel 1 goto failed
)
for %%F in (chat_planner.py planning.py) do (
    copy /Y "%~dp0backend\%%F" "%TARGET_DIR%\backend\%%F" >nul
    if errorlevel 1 goto failed
)
echo Update completed. Restart LearnPilot from the existing project folder.
echo Previous code backup: %BACKUP_DIR%
pause
exit /b 0
:missing
echo Target project folder was not found.
echo Drag your existing learnpilot-react folder onto this batch file to select another target.
pause
exit /b 1
:failed
echo Update failed. Please send a screenshot of this window.
echo Code backup directory: %BACKUP_DIR%
pause
exit /b 1
