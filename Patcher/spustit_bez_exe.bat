@echo off
cd /d "%~dp0"
where pyw >nul 2>nul && ( start "" pyw -3 violet2_launcher.py & exit /b )
where pythonw >nul 2>nul && ( start "" pythonw violet2_launcher.py & exit /b )
echo Python nenalezen. Nainstaluj ho z python.org (Add to PATH + tcl/tk).
pause
