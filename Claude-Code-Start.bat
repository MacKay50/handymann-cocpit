@echo off
chcp 65001 >nul
setlocal EnableExtensions

set "APP_DIR=C:\Temp\Anton\haandvaerker-demo"
set "CLAUDE_PROJECT_DIR=C:\Temp\Anton\ai.starter-agent-harness-main"
set "CLAUDE_EXE="

for /f "delims=" %%I in ('where claude 2^>nul') do (
    if not defined CLAUDE_EXE set "CLAUDE_EXE=%%I"
)

if not defined CLAUDE_EXE if exist "%USERPROFILE%\.local\bin\claude.exe" set "CLAUDE_EXE=%USERPROFILE%\.local\bin\claude.exe"
if not defined CLAUDE_EXE if exist "C:\Users\ckl\.local\bin\claude.exe" set "CLAUDE_EXE=C:\Users\ckl\.local\bin\claude.exe"

echo.
echo ==========================================
echo  Claude Code Start
echo ==========================================
echo.
echo Claude projektmappe:
echo %CLAUDE_PROJECT_DIR%
echo.
echo App mappe:
echo %APP_DIR%
echo.

if not exist "%CLAUDE_PROJECT_DIR%" (
    echo FEJL: Claude projektmappen findes ikke:
    echo %CLAUDE_PROJECT_DIR%
    pause
    exit /b 1
)

if not exist "%APP_DIR%" (
    echo FEJL: App mappen findes ikke:
    echo %APP_DIR%
    pause
    exit /b 1
)

if not defined CLAUDE_EXE (
    echo FEJL: Claude Code blev ikke fundet.
    echo.
    echo Test manuelt:
    echo where claude
    echo claude --version
    pause
    exit /b 1
)

if not exist "%CLAUDE_EXE%" (
    echo FEJL: Claude exe findes ikke:
    echo %CLAUDE_EXE%
    pause
    exit /b 1
)

cd /d "%CLAUDE_PROJECT_DIR%"
if errorlevel 1 (
    echo FEJL: Kunne ikke skifte til Claude projektmappe.
    pause
    exit /b 1
)

set "MODE=%~1"

if /I "%MODE%"=="continue" goto CONTINUE
if /I "%MODE%"=="c" goto CONTINUE
if /I "%MODE%"=="resume" goto RESUME
if /I "%MODE%"=="r" goto RESUME
if /I "%MODE%"=="new" goto NEW
if /I "%MODE%"=="n" goto NEW

echo Vaelg Claude Code start:
echo.
echo   [1] Fortsaet sidste session
echo   [2] Vaelg session
echo   [3] Start ny session
echo   [0] Afslut
echo.
set /p "CHOICE=Valg [1]: "

if "%CHOICE%"=="" set "CHOICE=1"
if "%CHOICE%"=="1" goto CONTINUE
if "%CHOICE%"=="2" goto RESUME
if "%CHOICE%"=="3" goto NEW
if "%CHOICE%"=="0" exit /b 0

echo Ugyldigt valg.
pause
exit /b 1

:CONTINUE
echo.
echo Fortsaetter sidste Claude Code session...
echo.
echo Working directory:
echo %CD%
echo.
"%CLAUDE_EXE%" --add-dir "%APP_DIR%" --continue
goto END

:RESUME
echo.
echo Aabner Claude Code session picker...
echo.
echo Working directory:
echo %CD%
echo.
"%CLAUDE_EXE%" --add-dir "%APP_DIR%" --resume
goto END

:NEW
echo.
echo Starter ny Claude Code session...
echo.
echo Working directory:
echo %CD%
echo.
"%CLAUDE_EXE%" --add-dir "%APP_DIR%"
goto END

:END
echo.
echo Claude Code lukkede.
echo Exit code: %errorlevel%
pause
exit /b %errorlevel%