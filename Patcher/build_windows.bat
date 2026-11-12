@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Violet2 launcher: vytvoreni exe ===
echo Slozka: %CD%
echo.

set PY=
where py >nul 2>nul
if %errorlevel%==0 set PY=py -3
if "%PY%"=="" where python >nul 2>nul
if "%PY%"=="" if %errorlevel%==0 set PY=python
if "%PY%"=="" goto nopython

echo Pouzivam Python:
%PY% -c "import sys;print(sys.executable, sys.version)"
echo.

%PY% -c "import tkinter" >nul 2>nul
if errorlevel 1 goto notk

echo [1/3] Instaluji/aktualizuji PyInstaller a Pillow (fotky novinek)...
%PY% -m pip install --upgrade pyinstaller pillow
echo.

if not exist assets\icon.ico goto noicon
findstr /c:"\"public_key\": \"\"" launcher.json >nul
if %errorlevel%==0 echo UPOZORNENI: v launcher.json je prazdny public_key. Nejdriv spust 1_vytvor_klice.bat, jinak launcher nebude chtit stahovat patche.


echo [2/3] Stavim exe (chvili to trva, nezavirej okno)...
%PY% -m PyInstaller --noconsole --onefile --noupx --hidden-import encodings.idna --hidden-import encodings.utf_8 --clean --noconfirm --icon assets\icon.ico --version-file version_info.txt --add-data "assets;assets" --add-data "launcher.json;." --add-data "theme.json;." --name Violet2Launcher violet2_launcher.py
echo.
if not exist dist\Violet2Launcher.exe goto failed

echo [3/3] Kopiruji vysledek...
if exist release rmdir /s /q release
mkdir release
copy /y dist\Violet2Launcher.exe release\ >nul
echo.
if exist sign.cfg call "%~dp0sign_windows.bat"
echo ======================================================
echo HOTOVO. Soubor pro slozku s hrou:
echo     %CD%\release\Violet2Launcher.exe
echo ======================================================
start "" explorer "%CD%\release"
goto end

:nopython
echo CHYBA: Python nebyl nalezen. Nainstaluj ho z https://www.python.org/downloads/
echo a zaskrtni "Add python.exe to PATH" a "tcl/tk and IDLE".
goto end

:notk
echo CHYBA: tento Python nema Tkinter (okenni knihovnu).
echo Nainstaluj oficialni Python z python.org (zaskrtni "tcl/tk and IDLE").
echo Pokud mas vic Pythonu (napr. ten z Visual Studia), odinstaluj ho nebo ho dej v PATH za novy.
goto end

:noicon
echo CHYBA: chybi soubor assets\icon.ico
goto end

:failed
echo CHYBA: Violet2Launcher.exe nevznikl. Prectete vypis vyse nad timto radkem.
echo Casta pricina: antivirus soubor smazal. Pridej tuto slozku do vyjimek Windows Security a zkus znovu.

:end
echo.
pause
