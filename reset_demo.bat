@echo off
chcp 65001 >nul
cd /d "%~dp0"

set PYTHON="C:\Program Files\Python39\python.exe"

echo.
echo  ================================================================
echo   RESET DEMO  -  Haandvaerker Business System
echo  ================================================================
echo.

echo  [1/4]  Stopper server paa port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "127.0.0.1:8000" 2^>nul') do (
    taskkill /f /pid %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul
echo         OK

echo  [2/4]  Sletter database...
if exist haandvaerker.db (
    del /f haandvaerker.db
    echo         haandvaerker.db slettet
) else (
    echo         Ingen database fundet - OK
)

echo  [3/4]  Starter server...
start "Haandvaerker Server" /d "%~dp0src" %PYTHON% -m uvicorn haandvaerker.main:app --reload --host 127.0.0.1 --port 8000
timeout /t 10 /nobreak >nul
echo         Server klar

echo  [4/4]  Seeder demo-data...
echo.
%PYTHON% seed_demo.py

start "" http://127.0.0.1:8000/ui
pause
