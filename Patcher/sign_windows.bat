@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Podepsani exe kod-podpisovym certifikatem. Bez nej Windows ukaze "Neznamy vydavatel".
rem Vytvor soubor sign.cfg s jednim radkem: cesta k .pfx certifikatu, napr.   C:\cert\violet2.pfx
rem Heslo k certifikatu se zepta pri podepisovani (nikam se neuklada).
if not exist sign.cfg ( echo Chybi sign.cfg s cestou k .pfx & goto end )
set /p PFX=<sign.cfg
set /p PW=Heslo k certifikatu: 
where signtool >nul 2>nul
if errorlevel 1 ( echo CHYBA: signtool nenalezen. Nainstaluj Windows SDK ^(slozka Signing Tools^) a otevri "Developer Command Prompt". & goto end )
signtool sign /fd SHA256 /f "%PFX%" /p "%PW%" /tr http://timestamp.digicert.com /td SHA256 /d "Violet2 Launcher" release\Violet2Launcher.exe
if errorlevel 1 ( echo CHYBA: podpis selhal. ) else ( echo Exe je podepsano. )
:end
set PW=
pause
