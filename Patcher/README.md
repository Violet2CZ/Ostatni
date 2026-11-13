# Violet2 Launcher a patcher (proprietární software, všechna práva vyhrazena)

Launcher má vlastní okno (bez systémového rámu, minimalizace a zavření), efekty (padající lístky, tečky, třpyt), stav serveru ONLINE/OFFLINE, počet hráčů online a za 24 h, novinky a event z webu, dvě lišty stahování (soubor a celkem) a tlačítka Hrát, Nastavení, Web, Podpora, Facebook a Discord.
Kompletní postup nasazení: **NAVOD-NASAZENI.txt**.

## Co kam měnit
| Co | Kde |
|---|---|
| Adresa webu, adresa patche, název hry a config.exe, veřejný klíč, **odkazy Discord / Facebook / Podpora / Web** (`links`) | `launcher.json` |
| Texty, barvy, cesty k obrázkům, vypnutí efektů (`"effects": false`) | `theme.json` |
| Pozadí 1280x720 (full HD master je v `assets/background_fullhd_master.png`) | `assets/background.png` |
| Průhledné panely a lišta | `assets/panels.png` (1280x720 PNG s průhledností) |
| Logo | `assets/logo.png` (420 px) |
| Tlačítka | `assets/btn_*.png` (rozměry viz `tools/make_assets.py`) |
| Ikona okna a exe | `assets/icon.ico` |
Obrázky přepiš stejnými názvy (PNG), např. ve Photoshopu. Po buildu mají soubory vedle exe přednost před zabalenými, takže jde vzhled měnit i bez nového buildu.
Tlačítka Facebook a Discord jsou vlastní obecné ikony v barvách služeb, oficiální loga si můžeš nahrát podle pravidel těchto služeb.

## Zabezpečení
- **Žádná IP ani hesla v launcheru.** Stav serveru zjišťuje web (`/api/launcher.php`), IP a port hry jsou jen v `config.php` na serveru.
- **Podepsané patche (Ed25519).** Launcher stáhne `manifest.json` a `manifest.sig` a ověří podpis veřejným klíčem z `launcher.json`. Privátní klíč zůstává u tebe (`keys/private.key`), nikdy na serveru. Bez platného podpisu se nic nestáhne.
- Pouze HTTPS s ověřením certifikátu, přesměrování jen na povolené domény, limity velikosti odpovědí a souborů.
- Každý soubor se kontroluje velikostí a SHA-256, stahuje se do `.part` a až potom se přesune na místo.
- Cesty z patche jsou přísně omezené na složku hry (žádné `..`, absolutní cesty, `:`, přepsání launcheru). Spouští se jen soubory ve složce hry. Odkazy se otevírají jen jako https.
- Data z webu se zobrazují jen jako text a jsou zkrácená.
- Prakticky: kdo získá přístup k tvému privátnímu klíči nebo k tvému počítači, může podepsat škodlivý patch. Chraň klíč a PC.

## Automatická aktualizace launcheru
Od verze 1.1.0 se launcher aktualizuje sám: nová verze je v podepsaném manifestu, ověří se podpis i SHA-256 a pak se exe vymění. Postup vydání a nastavení antiviru je v `NAVOD-ANTIVIRUS-A-AKTUALIZACE.txt`.

## Exe a antivirus
`build_windows.bat` vytvoří `release\Violet2Launcher.exe` (ikona, údaje „Violet2" ve vlastnostech, vše zabalené uvnitř). Aby Windows a antivirus neukazovaly „neznámý vydavatel", musí být exe **podepsané kód-podpisovým certifikátem** vydaným na jméno Violet2 (nebo tvoje). To nejde obejít: koupíš ho (Azure Artifact Signing, Sectigo, DigiCert, SSL.com), dáš cestu k `.pfx` do `sign.cfg` a `sign_windows.bat` exe podepíše. Hotové exe pošli také Microsoftu jako falešný poplach: https://www.microsoft.com/wdsi/filesubmission. Licenční text je v `LICENSE`.

## Build
Python 3.9+ z python.org (Add to PATH, tcl/tk), pak `build_windows.bat` (pravým tlačítkem Spustit jako správce, pokud ti to Windows vyžaduje). Zip nejdřív rozbal do složky bez diakritiky, např. `C:\launcher`. Při chybě se výpis ukáže v okně.
Znovu vygenerovat panely a tlačítka: `pip install pillow` a `python tools/make_assets.py`.

## Písmo a tlačítka
- Písmo je **Tektur** (licence SIL OFL, text je v `assets/fonts/Tektur-OFL.txt`). Launcher ho načte jen pro sebe, nic se do Windows neinstaluje. Jiné písmo: dej `.ttf` do `assets/fonts/` a v `theme.json` přepiš `font` a `font_bold` (název písma). Obrázky tlačítek a logo mají písmo „zapečené", ty přegeneruješ příkazem `python tools/make_assets.py` (Pillow) nebo nahradíš vlastními.
- Tlačítka: Hrát, Nastavení, Web, Podpora, Facebook, Discord, Kontrola (znovu ověří a opraví soubory hry) a Registrace (odkaz je v `launcher.json` v `links.register`).
