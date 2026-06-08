@echo off
chcp 65001 >nul
cd /d "%~dp0"

set PYTHON="C:\Program Files\Python39\python.exe"

echo.
echo  Seeder demo-data til PLL Malerfirma ApS...
echo  (Kraever at serveren korer - start.bat)
echo.
%PYTHON% seed_demo.py
echo.
pause
