@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo.
echo ==========================================
echo  Setup Haandvaerker lokalt
echo ==========================================
echo.
echo Projektmappe:
echo %CD%
echo.

set "PYTHON=C:\Program Files\Python39\python.exe"

if not exist "%PYTHON%" (
    echo FEJL: Python blev ikke fundet her:
    echo %PYTHON%
    pause
    exit /b 1
)

echo [0/6] Rydder gammel .venv...
if exist ".venv" (
    rmdir /s /q ".venv"
    if exist ".venv" (
        echo.
        echo FEJL: Kunne ikke slette .venv.
        echo Luk alle terminaler/servervinduer der bruger projektet og proev igen.
        pause
        exit /b 1
    )
)

echo.
echo [1/6] Opretter virtual environment...
"%PYTHON%" -m venv .venv
if errorlevel 1 goto FAIL

echo.
echo [2/6] Opgraderer pip, setuptools og wheel...
".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto FAIL

echo.
echo [3/6] Skriver lokal constraint for greenlet...
(
    echo greenlet==3.1.1
) > constraints-local.txt

echo.
echo [4/6] Installerer greenlet som prebuilt wheel...
".venv\Scripts\python.exe" -m pip install --only-binary=:all: "greenlet==3.1.1"
if errorlevel 1 (
    echo.
    echo FEJL: Kunne ikke installere greenlet==3.1.1 som binary wheel.
    echo Det betyder typisk at Python-arkitektur eller pip-platform ikke matcher.
    pause
    exit /b 1
)

echo.
echo [5/6] Installerer projektet lokalt...
".venv\Scripts\python.exe" -m pip install --prefer-binary -e . -c constraints-local.txt
if errorlevel 1 goto FAIL

echo.
echo [6/6] Tester installation...
".venv\Scripts\python.exe" -c "import greenlet, uvicorn, fastapi; import haandvaerker; print('Installation OK')"
if errorlevel 1 goto FAIL

echo.
echo ==========================================
echo  Setup OK
echo ==========================================
echo.
echo Koer nu start.bat
echo.
pause
exit /b 0

:FAIL
echo.
echo FEJL: Setup fejlede.
echo Se fejlteksten ovenfor.
pause
exit /b 1