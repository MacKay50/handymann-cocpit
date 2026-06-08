@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ==========================================
echo  Starter Haandvaerker lokalt
echo ==========================================
echo.
echo App mappe:
echo %CD%
echo.

set "APP_DIR=%CD%"
set "PYTHON=%APP_DIR%\.venv\Scripts\python.exe"
set "PYTHONPATH=%APP_DIR%\src"
set "CLAUDE_START=%APP_DIR%\Claude-Code-Start.bat"

if not exist "%PYTHON%" (
    echo FEJL: .venv blev ikke fundet.
    echo.
    echo Koer setup_once.bat foerst.
    pause
    exit /b 1
)

echo [1/4] Tjekker app-import...
"%PYTHON%" -c "import haandvaerker.main; print('haandvaerker.main import OK')"
if errorlevel 1 (
    echo.
    echo FEJL: Python kan ikke importere haandvaerker.main.
    echo Kontroller at appen ligger i src\haandvaerker\main.py
    pause
    exit /b 1
)

set "CLAUDE_MODE=ask"

if /I "%~1"=="continue" set "CLAUDE_MODE=continue"
if /I "%~1"=="c" set "CLAUDE_MODE=continue"
if /I "%~1"=="resume" set "CLAUDE_MODE=resume"
if /I "%~1"=="r" set "CLAUDE_MODE=resume"
if /I "%~1"=="noclaude" set "CLAUDE_MODE=none"
if /I "%~1"=="serveronly" set "CLAUDE_MODE=none"

echo.
echo [2/4] Claude Code...

if not exist "%CLAUDE_START%" (
    echo Claude-Code-Start.bat blev ikke fundet:
    echo %CLAUDE_START%
    echo Springer Claude over.
    set "CLAUDE_MODE=none"
    goto AFTER_CLAUDE
)

if /I "%CLAUDE_MODE%"=="ask" goto CLAUDE_ASK
goto CLAUDE_RUN

:CLAUDE_ASK
echo.
echo Vaelg Claude Code:
echo.
echo   [F] Fortsaet sidste Claude Code session
echo   [R] Vaelg session
echo   [N] Start ikke Claude
echo.
set /p "ANS=Valg [F]: "

if "%ANS%"=="" set "ANS=F"
if /I "%ANS%"=="F" set "CLAUDE_MODE=continue"
if /I "%ANS%"=="R" set "CLAUDE_MODE=resume"
if /I "%ANS%"=="N" set "CLAUDE_MODE=none"

:CLAUDE_RUN
if /I "%CLAUDE_MODE%"=="continue" goto START_CLAUDE_CONTINUE
if /I "%CLAUDE_MODE%"=="resume" goto START_CLAUDE_RESUME
if /I "%CLAUDE_MODE%"=="none" goto SKIP_CLAUDE

echo Ugyldigt Claude-valg. Springer Claude over.
goto AFTER_CLAUDE

:START_CLAUDE_CONTINUE
echo Starter Claude Code og fortsaetter sidste session...
start "Claude Code" /D "%APP_DIR%" cmd /k call "%CLAUDE_START%" continue
goto AFTER_CLAUDE

:START_CLAUDE_RESUME
echo Starter Claude Code session picker...
start "Claude Code" /D "%APP_DIR%" cmd /k call "%CLAUDE_START%" resume
goto AFTER_CLAUDE

:SKIP_CLAUDE
echo Springer Claude Code over.

:AFTER_CLAUDE
echo.
echo [3/4] Starter server...
start "Haandvaerker Server" /D "%APP_DIR%" cmd /k ""%PYTHON%" -m uvicorn haandvaerker.main:app --app-dir src --reload --host 127.0.0.1 --port 8000"

echo.
echo [4/4] Venter og aabner browser...
timeout /t 5 /nobreak >nul
start "" "http://127.0.0.1:8000"

echo.
echo Startkommandoer sendt.
echo.
echo Server:
echo   http://127.0.0.1:8000
echo.
echo Claude projektmappe:
echo   C:\Temp\Anton\ai.starter-agent-harness-main
echo.
echo App mappe:
echo   %APP_DIR%
echo.
pause
exit /b 0