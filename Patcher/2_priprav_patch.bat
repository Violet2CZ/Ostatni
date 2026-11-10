@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=py -3
where py >nul 2>nul
if errorlevel 1 set PY=python
if not exist patch_zdroj mkdir patch_zdroj
echo Soubory patche (tak jak maji byt ve hre) dej do slozky patch_zdroj.
echo Napr. patch_zdroj\pack\novy.epk  nebo  patch_zdroj\config.exe
echo Novy launcher: dej Violet2Launcher.exe primo do patch_zdroj (zvys VERSION v violet2_launcher.py).
echo Soubory, ktere se nesmi prepisovat (nastaveni hrace): vypis do patch_zdroj\_zachovat.txt (jeden na radek, napr. metin2.cfg).
echo Stare soubory ke smazani vypis do patch_zdroj\_odstranit.txt (jeden na radek).
echo.
pause
%PY% tools\patch_tool.py build patch_zdroj patch_vystup
echo.
echo Obsah slozky patch_vystup nahraj na server do /usr/local/www/web/patcher/
pause
