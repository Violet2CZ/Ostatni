@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=py -3
where py >nul 2>nul
if errorlevel 1 set PY=python
%PY% tools\patch_tool.py keygen
echo.
pause
