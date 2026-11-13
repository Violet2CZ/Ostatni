#!/usr/bin/env python3
"""Violet2 Launcher a patcher (proprietární software, všechna práva vyhrazena, viz LICENSE).
Jen standardní knihovna Pythonu 3.9+ (Tkinter). Žádná IP adresa ani heslo v launcheru není:
stav serveru a počty hráčů dodává web přes HTTPS, patche jsou podepsané (Ed25519)."""
import base64
import encodings.idna  # noqa: F401  (musí být zabalený v exe, jinak spojení s webem selže: unknown encoding idna)
import fnmatch
import hashlib
import io
import json
import math
import os
import random
import queue
import re
import ssl
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from tkinter import messagebox  # jen pro chyby před startem okna

import v2accounts
import v2cfg
import v2sig

try:  # volitelné: s Pillow launcher ukáže fotky novinek z webu, bez něj použije pevné obrázky
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = 40_000_000
except Exception:  # noqa: BLE001
    Image = None

VERSION = "2.3.0"
BASE = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
# Vlastní data launcheru (stav, hudba, logy) NEJSOU ve složce hry, ale v %APPDATA%\\Violet2Launcher
DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Violet2Launcher")
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError:
    DATA_DIR = BASE
UA = "Violet2Launcher/" + VERSION

FX_KINDS = ("snow", "leaves", "sakura", "sparks")
FX_COUNT = {"low": 10, "mid": 18, "high": 34}
LEAF_COLORS = ("#8e44ff", "#b66bff", "#6c2bd9", "#d7a8ff", "#a05cff", "#7a3fd0")


def season_fx():
    m = time.localtime().tm_mon
    return "snow" if m in (12, 1, 2) else "sakura" if 3 <= m <= 5 else "leaves" if 9 <= m <= 11 else "sparks"
MAX_JSON = 2 * 1024 * 1024
MAX_FILE = 4 * 1024 ** 3
# Soubory, které patcher nikdy nepřepíše ani nesmaže, pokud už na disku jsou (nastavení hráče). Stáhnou se jen když chybí.
# Dá se změnit v launcher.json ("keep") nebo v patchi (soubor _zachovat.txt).
DEFAULT_KEEP = ["metin2.cfg", "config.cfg", "config.ini", "config.exe", "config/*"]
SAFE_REL = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._- /")


def res(name):
    """Soubor vedle exe má přednost (dá se přepsat), jinak se vezme ten zabalený uvnitř exe."""
    ext = os.path.join(BASE, name)
    if getattr(sys, "frozen", False) and name in ("launcher.json", "theme.json"):
        return os.path.join(getattr(sys, "_MEIPASS", BASE), name)  # v exe je nastavení zabalené natvrdo, vedle exe se nehledá
    if os.path.isfile(ext):
        return ext
    return os.path.join(getattr(sys, "_MEIPASS", BASE), name)


def load_json(name):
    with open(res(name), encoding="utf-8") as f:
        return json.load(f)


DEFAULT_THEME = {
    "title": "Violet2", "tagline": "", "font": "Segoe UI", "effects": True, "bg": "#bfe6f7", "text": "#e6f4ea", "muted": "#8fb7a0",
    "accent": "#3fc17b", "accent2": "#ffe9a8", "title_text": "#0f3a4d", "title_btn": "#e4f5ff", "tagline_text": "#14506a",
    "panel_title": "#0f4f6b", "panel_text": "#1d4458", "event_text": "#7a3fd0", "bar_outline": "#e8c878", "bar_bg": "#103246",
    "bar_file": "#5ec4ff", "note_bg": "#0c1d33", "panel": "#081a32", "border": "#2f7fa6", "ok": "#2ecc71", "bad": "#e5484d", "field": "#05122a", "rail_on": "#0f3550", "play_text": "#04202a", "gold": "#e2bc6a", "play_fill": "#7b2fe0", "play_hover": "#9a52ff", "icon": "", "background": "", "panels": "", "logo": "", "buttons": {},
}
CFG = load_json("launcher.json")
THEME = dict(DEFAULT_THEME)
THEME.update(load_json("theme.json"))
for _k in ("play", "settings", "web", "support", "facebook", "discord", "check", "register"):
    THEME["buttons"].setdefault(_k, {"text": _k.capitalize(), "image": ""})
    THEME["buttons"][_k].setdefault("text", _k.capitalize())
    THEME["buttons"][_k].setdefault("image", "")


def register_fonts():
    """Zabalené písmo (Tektur, licence OFL) se na Windows načte jen pro tento program, nic se neinstaluje."""
    if os.name != "nt":
        return
    try:
        import ctypes
        d = res("assets/fonts")
        for n in os.listdir(d):
            if n.lower().endswith((".ttf", ".otf")):
                ctypes.windll.gdi32.AddFontResourceExW(os.path.join(d, n), 0x10, 0)
    except Exception:
        pass


def fatal(msg):
    """Chyba nastavení: ukáže okno (exe bez konzole by jinak mlčelo) a skončí."""
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Violet2 Launcher", msg)
    except Exception:
        pass
    sys.exit(msg)


def https_only(url, what):
    if not str(url).lower().startswith("https://"):
        fatal("%s v launcher.json musí začínat https://" % what)
    return str(url).rstrip("/")


SITE = https_only(CFG["site_url"], "site_url")
PATCH = https_only(CFG.get("patch_url") or SITE + "/patcher", "patch_url")
ALLOWED = {urllib.parse.urlparse(SITE).hostname, urllib.parse.urlparse(PATCH).hostname}
CTX = ssl.create_default_context()  # ověřuje certifikát i název serveru


# ---------- síť ----------
class OnlyHttps(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urllib.parse.urlparse(newurl)
        if u.scheme != "https" or u.hostname not in ALLOWED:
            raise urllib.error.URLError("Zakázané přesměrování")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(OnlyHttps, urllib.request.HTTPSHandler(context=CTX))


_net = {"last": 0.0, "until": 0.0, "fails": 0}
_net_lock = threading.Lock()


def _throttle(url):
    """Ochrana proti zahlcení: mezi dotazy je minimální odstup a po chybě serveru (429, 5xx, výpadek) se čeká se stoupající prodlevou.
    Launcher tak server nikdy nebombarduje, ani když běží tisíce klientů najednou. Stahování souborů patche není zdržováno."""
    now = time.time()
    with _net_lock:
        if "/api/" in url and now < _net["until"]:
            raise RuntimeError("Server je dočasně přetížený, zkusím to za %d s" % (_net["until"] - now))
        wait = _net["last"] + (0.25 if "/api/" in url else 0.02) - now
        _net["last"] = max(now, _net["last"]) + (0.25 if "/api/" in url else 0.02)
    if wait > 0:
        time.sleep(min(wait, 2.0))


def _net_fail(url, retry_after=0):
    if "/api/" not in url:
        return
    with _net_lock:
        _net["fails"] = min(_net["fails"] + 1, 8)
        delay = retry_after or min(300, 5 * 2 ** _net["fails"])
        _net["until"] = time.time() + delay * (0.8 + 0.4 * random.random())


def _net_ok():
    with _net_lock:
        _net["fails"] = 0
        _net["until"] = 0.0


def fetch(url, timeout=15):
    if urllib.parse.urlparse(url).hostname not in ALLOWED:
        raise ValueError("Cizí adresa zakázána")
    _throttle(url)
    try:
        r = OPENER.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout)
        _net_ok()
        return r
    except urllib.error.HTTPError as ex:
        if ex.code == 429 or ex.code >= 500:
            try:
                ra = int(ex.headers.get("Retry-After", "0") or 0)
            except (TypeError, ValueError):
                ra = 0
            _net_fail(url, min(ra, 600))
        raise RuntimeError("Server vrátil HTTP %s pro adresu %s" % (ex.code, url)) from None
    except (urllib.error.URLError, OSError):
        _net_fail(url)
        raise


def fetch_small(url):
    with fetch(url) as r:
        data = r.read(MAX_JSON + 1)
    if len(data) > MAX_JSON:
        raise ValueError("Odpověď je příliš velká")
    return data


MAX_IMG = 8 * 1024 * 1024
HERO_W, HERO_H = 758, 358


def fetch_bytes(url, limit=MAX_IMG):
    with fetch(url, timeout=20) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Obrázek je příliš velký")
    return data


def news_png_b64(raw):
    """Fotka novinky na PNG 758×358 (ořez na střed) s tmavým přechodem dole, aby šel číst text. Vrací base64, nebo None bez Pillow."""
    if Image is None:
        return None
    im = Image.open(io.BytesIO(raw))
    try:
        im.draft("RGB", (HERO_W * 2, HERO_H * 2))
    except Exception:  # noqa: BLE001
        pass
    im = im.convert("RGB")
    k = max(HERO_W / im.width, HERO_H / im.height)
    resample = getattr(Image, "Resampling", Image).LANCZOS
    im = im.resize((max(HERO_W, round(im.width * k)), max(HERO_H, round(im.height * k))), resample)
    left, top = (im.width - HERO_W) // 2, (im.height - HERO_H) // 2
    im = im.crop((left, top, left + HERO_W, top + HERO_H))
    gh = int(HERO_H * 0.72)
    mask = Image.linear_gradient("L").resize((HERO_W, gh)).point(lambda v: int(v * 0.93))
    im.paste(Image.new("RGB", (HERO_W, gh), (5, 18, 38)), (0, HERO_H - gh), mask)
    out = io.BytesIO()
    im.save(out, "PNG")
    return base64.b64encode(out.getvalue()).decode("ascii")


def log_exc():
    """Zapíše poslední chybu s tracebackem do launcher_error.log vedle exe (pro hledání příčin)."""
    import traceback
    try:
        with open(os.path.join(DATA_DIR, "launcher_error.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + traceback.format_exc() + "\n")
    except OSError:
        pass


def clip(v, n=120):
    return str(v)[:n] if v is not None else ""


# ---------- hudba na pozadí ----------
MAX_MUSIC = 20 * 1024 ** 2
STATE_FILE = os.path.join(DATA_DIR, "launcher_state.json")
MUSIC_DIR = os.path.join(DATA_DIR, "launcher_music")


def _cleanup_old():
    """Smaže pozůstatky ze starých verzí ze složky hry (teď jsou v %APPDATA%)."""
    if getattr(sys, "frozen", False):
        for n in ("launcher.json", "theme.json"):
            try:
                os.remove(os.path.join(BASE, n))
            except OSError:
                pass
    if DATA_DIR == BASE:
        return
    import shutil
    for n in ("launcher_state.json", "launcher_error.log", "patcher.log"):
        try:
            os.remove(os.path.join(BASE, n))
        except OSError:
            pass
    shutil.rmtree(os.path.join(BASE, "launcher_music"), ignore_errors=True)


_cleanup_old()


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(d):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except OSError:
        pass


def looks_like_audio(data):
    """Jen mp3 (ID3 nebo MPEG rámec) a wav (RIFF). Cokoli jiného se nepřehrává."""
    return data[:3] == b"ID3" or data[:4] == b"RIFF" or (len(data) > 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0)


class Music:
    """Hudba na pozadí přes Windows MCI (winmm.dll). Žádná další knihovna; mimo Windows nedělá nic.
    Na všechno kolem je try/except, hudba nikdy nesmí shodit launcher."""
    ALIAS = "v2bgm"

    def __init__(self):
        self.ok = os.name == "nt"
        self.vol = 0.35
        self.on = True
        self.path = None
        self.opened = False

    def _mci(self, cmd):
        if not self.ok:
            return -1, ""
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(128)
            err = ctypes.windll.winmm.mciSendStringW(cmd, buf, 127, 0)
            return err, buf.value
        except Exception:
            return -1, ""

    def load(self, path):
        self.close()
        if not self.ok or not path or not os.path.isfile(path) or '"' in path:
            return False
        err, _ = self._mci('open "%s" type mpegvideo alias %s' % (path, self.ALIAS))
        if err:
            err, _ = self._mci('open "%s" alias %s' % (path, self.ALIAS))
        self.opened = not err
        self.path = path if self.opened else None
        if self.opened:
            self.set_volume(self.vol)
        return self.opened

    def play(self):
        if self.opened and self.on:
            self._mci("play %s" % self.ALIAS)

    def pause(self):
        if self.opened:
            self._mci("pause %s" % self.ALIAS)

    def set_volume(self, v):
        self.vol = min(1.0, max(0.0, v))
        if self.opened:
            self._mci("setaudio %s volume to %d" % (self.ALIAS, int(self.vol * 1000)))

    def toggle(self):
        self.on = not self.on
        if self.on:
            self.play()
        else:
            self.pause()

    def tick(self):
        """Smyčka: když skladba dohraje, pustí se znovu."""
        if not (self.opened and self.on):
            return
        err, mode = self._mci("status %s mode" % self.ALIAS)
        if not err and mode == "stopped":
            self._mci("seek %s to start" % self.ALIAS)
            self._mci("play %s" % self.ALIAS)

    def close(self):
        if self.opened:
            self._mci("stop %s" % self.ALIAS)
            self._mci("close %s" % self.ALIAS)
        self.opened = False


def own_music():
    """Vlastní hudba vedle exe (music.mp3 / music.wav) má přednost před vším ostatním."""
    for name in ("music.mp3", "music.wav"):
        p = os.path.join(BASE, name)
        if os.path.isfile(p):
            return p
    return None


def cached_music(url):
    """Stažená hudba z webu (jen z vlastní domény přes HTTPS). Vrací cestu k souboru nebo None."""
    ext = ".wav" if url.lower().endswith(".wav") else ".mp3"
    if not url.lower().endswith((".mp3", ".wav")):
        return None
    path = os.path.join(MUSIC_DIR, hashlib.sha256(url.encode()).hexdigest()[:16] + ext)
    if os.path.isfile(path):
        return path
    with fetch(url, timeout=30) as r:
        data = r.read(MAX_MUSIC + 1)
    if len(data) > MAX_MUSIC or not looks_like_audio(data):
        raise ValueError("Hudba má špatný formát nebo je příliš velká")
    os.makedirs(MUSIC_DIR, exist_ok=True)
    for old in os.listdir(MUSIC_DIR):  # drží se jen poslední skladba
        try:
            os.remove(os.path.join(MUSIC_DIR, old))
        except OSError:
            pass
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return path


# ---------- bezpečné cesty a spouštění ----------
def game_root():
    return os.path.realpath(CFG.get("game_dir") or BASE)


def safe_rel(rel):
    if not rel or len(rel) > 200 or rel[0] == "/" or any(c not in SAFE_REL for c in rel):
        raise ValueError("Nebezpečná cesta v patchi: " + clip(rel, 60))
    parts = rel.split("/")
    if any(p in ("", ".", "..") or p.endswith((" ", ".")) for p in parts):
        raise ValueError("Nebezpečná cesta v patchi: " + clip(rel, 60))
    root = game_root()
    full = os.path.realpath(os.path.join(root, rel))
    if os.path.commonpath([root, full]) != root:
        raise ValueError("Cesta mimo složku hry")
    if os.path.normcase(full) == os.path.normcase(os.path.realpath(sys.executable if getattr(sys, "frozen", False) else __file__)):
        raise ValueError("Patch nesmí přepsat launcher")
    return full


def run_local(exe):
    """Spustí program ze složky hry. Vrací text chyby nebo None (žádná modální okna, ta by se skryla za oknem bez rámu)."""
    root = game_root()
    full = os.path.realpath(os.path.join(root, exe or ""))
    if not exe or os.path.commonpath([root, full]) != root or not os.path.isfile(full):
        return "Soubor nenalezen ve složce hry:\n%s\n\nDej launcher do hlavní složky hry, nebo oprav název v launcher.json." % exe
    try:
        subprocess.Popen([full], cwd=os.path.dirname(full))
    except OSError as e:
        return "Nepodařilo se spustit %s:\n%s" % (exe, clip(e, 120))
    return None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------- patchování (podepsaný manifest) ----------
def get_manifest():
    data = fetch_small(PATCH + "/manifest.json")
    key = (CFG.get("public_key") or "").strip()
    if key:
        sig = bytes.fromhex(fetch_small(PATCH + "/manifest.sig").decode("ascii").strip())
        if not v2sig.verify(bytes.fromhex(key), data, sig):
            raise ValueError("Podpis patche nesedí! Aktualizace zastavena.")
    elif not CFG.get("allow_unsigned"):
        raise ValueError("V launcher.json chybí public_key (podepisování patchů je povinné).")
    return json.loads(data.decode("utf-8"))


def cleanup_old():
    """Po aktualizaci zbyde vedle exe starý soubor (.old). Starý proces ho ještě chvíli drží zamčený,
    proto se smazání zkouší na pozadí, dokud se nepodaří (max. ~60 s). Je to jediné, co po aktualizaci ve složce zbude."""
    if not getattr(sys, "frozen", False):
        return

    def job():
        left = [sys.executable + ".old", sys.executable + ".new"]
        for _ in range(120):
            for p in list(left):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                    left.remove(p)
                except OSError:
                    pass
            if not left:
                return
            time.sleep(0.5)

    threading.Thread(target=job, daemon=True).start()


def self_update(man, cb):
    """Samoaktualizace launcheru. Nová verze je v PODEPSANÉM manifestu (velikost, SHA-256), takže ji nejde podvrhnout.
    Aktualizuje se, kdykoli se SHA-256 vlastního exe liší od manifestu (číslo verze se hlídat nemusí). Běžící exe se na Windows smí přejmenovat, proto žádný skript ani druhý proces.
    Vrací True, když se exe vyměnilo a je potřeba restart."""
    info = man.get("launcher")
    if not isinstance(info, dict) or not getattr(sys, "frozen", False):
        return False
    try:
        size, want = int(info["size"]), str(info["sha256"]).lower()
        if size <= 0 or size > MAX_FILE or not re.fullmatch(r"[0-9a-f]{64}", want):
            raise ValueError("Neplatné údaje o nové verzi")
        if os.path.getsize(sys.executable) == size and sha256_file(sys.executable) == want:
            return False  # už běží aktuální launcher
        exe = sys.executable
        new, old = exe + ".new", exe + ".old"
        h, got, t0 = hashlib.sha256(), 0, time.time()
        with fetch(PATCH + "/launcher/Violet2Launcher.exe", 60) as r, open(new, "wb") as out:
            while True:
                b = r.read(1 << 16)
                if not b:
                    break
                got += len(b)
                if got > size:
                    raise ValueError("Soubor je větší, než uvádí manifest")
                h.update(b)
                out.write(b)
                cb(got * 100 // size, got * 100 // size, "Stahuji novou verzi launcheru  (%.1f MB/s)" % (got / max(time.time() - t0, 0.1) / 1048576))
        if got != size or h.hexdigest() != want:
            os.remove(new)
            raise ValueError("Kontrolní součet nesedí")
        try:
            os.remove(old)
        except OSError:
            pass
        os.replace(exe, old)
        try:
            os.replace(new, exe)
        except OSError:
            os.replace(old, exe)
            raise
        return True
    except Exception as e:
        try:
            os.remove(sys.executable + ".new")
        except OSError:
            pass
        cb(0, 0, "Nová verze launcheru se nenainstalovala: %s" % clip(e, 60))
        return False


def is_kept(rel, pats):
    r = rel.lower()
    base = r.rsplit("/", 1)[-1]
    for p in pats:
        p = str(p).lower()
        # vzor bez lomítka platí pro soubor s tímto názvem v kterékoli složce (metin2.cfg i config/metin2.cfg)
        if fnmatch.fnmatch(r, p) or ("/" not in p and fnmatch.fnmatch(base, p)):
            return True
    return False


def check_and_patch(cb):
    """cb(file_pct, total_pct, text) – hlásí postup. Vrací počet stažených souborů, nebo "restart"."""
    cb(0, 0, "Kontroluji soubory…")
    man = get_manifest()
    if self_update(man, cb):
        cb(100, 100, "Launcher byl aktualizován, restartuji…")
        return "restart"
    keep = list(CFG.get("keep", DEFAULT_KEEP)) + [str(x) for x in man.get("keep", [])]
    for rel in man.get("remove", []):
        p = safe_rel(rel)
        if is_kept(rel, keep):
            continue
        if os.path.isfile(p):
            os.remove(p)
    todo = []
    for item in man.get("files", []):
        lp = item["path"].lower()
        if lp.startswith("log/") or lp.endswith(".log") or lp.rsplit("/", 1)[-1].startswith("syserr") or lp in ("config/v2_accounts.dat", "config/v2_autologin.dat"):
            continue  # logy hry a osobní soubory hráče (uložené účty) se nikdy nestahují
        dest = safe_rel(item["path"])
        if (item.get("keep") or is_kept(item["path"], keep)) and os.path.isfile(dest):
            continue  # nastavení hráče (config/*, metin2.cfg...) se nikdy nepřepisuje: stáhne se jen, když ve hře chybí
        if not os.path.isfile(dest) or os.path.getsize(dest) != int(item["size"]) or sha256_file(dest) != item["sha256"].lower():
            todo.append((item, dest))
    if not todo:
        cb(100, 100, "Hra je aktuální.")
        return 0
    total = sum(int(i["size"]) for i, _ in todo) or 1
    done = 0
    t0 = time.time()
    for n, (item, dest) in enumerate(todo, 1):
        size = int(item["size"])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".part"
        h = hashlib.sha256()
        got = 0
        url = PATCH + "/files/" + urllib.parse.quote(item["path"])
        try:
            resp = fetch(url, 60)
        except RuntimeError as ex:
            if (item.get("keep") or is_kept(item["path"], keep)) and "HTTP 404" in str(ex):
                continue  # soubor "nepřepisovat" (nastavení hráče) chybí na serveru: není důvod kvůli němu zastavit celou aktualizaci
            raise
        with resp as r, open(tmp, "wb") as out:
            while True:
                b = r.read(1 << 16)
                if not b:
                    break
                got += len(b)
                if got > size or got > MAX_FILE:
                    raise ValueError("Soubor je větší, než uvádí manifest")
                h.update(b)
                out.write(b)
                el = max(time.time() - t0, 0.1)
                cb(got * 100 // max(size, 1), (done + got) * 100 // total,
                   "Stahuji %d/%d  %s  (%.1f MB/s)" % (n, len(todo), item["path"], (done + got) / el / 1048576))
        if got != size or h.hexdigest() != item["sha256"].lower():
            os.remove(tmp)
            raise ValueError("Kontrolní součet nesedí: " + item["path"])
        os.replace(tmp, dest)
        done += size
    cb(100, 100, "Aktualizace dokončena (%d souborů)." % len(todo))
    return len(todo)


# ---------- okno ----------
class App(tk.Tk):
    W, H = 1280, 720

    def __init__(self):
        super().__init__()
        t = self.t = THEME
        self.overrideredirect(True)
        self.title(t.get("title", "Violet2"))
        self.resizable(False, False)
        self.geometry("%dx%d+%d+%d" % (self.W, self.H, (self.winfo_screenwidth() - self.W) // 2, max((self.winfo_screenheight() - self.H) // 2, 0)))
        self.configure(bg=t["bg"])
        try:  # okno není obdélník: barva KEY je průhledná (seříznuté rohy a zářezy jsou vypálené v pozadí)
            self.attributes("-transparentcolor", self.KEY)
        except Exception:
            pass
        self.pick_fonts()
        if os.path.isfile(res(t.get("icon", ""))):
            try:
                self.iconbitmap(res(t["icon"]))
            except tk.TclError:
                pass
        self.q = queue.Queue()
        self.imgs, self.busy, self._drag = {}, True, None
        c = self.c = tk.Canvas(self, width=self.W, height=self.H, highlightthickness=0, bg=self.KEY)
        c.pack()
        self.bg_top = None
        for key in ("background", "panels"):
            im = self.img(t.get(key))
            if im:
                self.bg_top = c.create_image(0, 0, anchor="nw", image=im)
        self.particles = []
        self.fx_kind, self.fx_level = "off", ""
        if t.get("effects", True):
            self.fx_set("auto", "mid")  # dokud se nenačte nastavení z webu, platí roční období
        self.build_ui()
        self.music_start()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after(150, self.taskbar_entry)
        self.perf_watch()
        self.bind("<Map>", self.on_map)
        self.pump()
        self.refresh_loop()
        self.after(30000, self.event_tick)
        self.after(1000, self.hero_loop)
        self.animate()
        self.start_patch()

    # --- pomocné ---
    def img(self, name):
        if not name or not os.path.isfile(res(name)):
            return None
        im = tk.PhotoImage(file=res(name))
        self.imgs[name] = im
        return im

    def pick_fonts(self):
        from tkinter import font as tkfont
        have = set(tkfont.families(self))
        norm = next((f for f in (self.t["font"], "Bahnschrift", "Segoe UI") if f in have), "TkDefaultFont")
        bold = next((f for f in (self.t.get("font_bold"), norm) if f and f in have), norm)
        self.f_norm, self.f_bold = norm, bold

    def font(self, size, bold=False):
        return (self.f_bold, size) if bold else (self.f_norm, size)

    def ui(self, fn, *a, **k):
        """Z jiných vláken se do okna nesahá přímo, úkoly jdou přes frontu do hlavního vlákna."""
        self.q.put(lambda: fn(*a, **k))

    def pump(self):
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        self.after(50, self.pump)

    def perf_watch(self):
        """Zapisuje do launcher_perf.log, co okno zdržuje (jen když něco trvá déle než 80 ms)."""
        def wrap(name):
            fn = getattr(self, name, None)
            if not fn:
                return

            def w(*a, **k):
                t0 = time.time()
                try:
                    return fn(*a, **k)
                finally:
                    dt = time.time() - t0
                    if dt > 0.08:
                        self.perf_log("%s %d ms" % (name, dt * 1000))
            setattr(self, name, w)
        for n in ("rail_enter", "rail_leave", "show_info", "show_hero", "set_top", "draw_top", "draw_online", "draw_accounts", "fx_set", "show_gms", "show_event", "toggle_mode", "apply_mode"):
            wrap(n)
        if self.hover_level < 4:
            orig_cf = self.c.configure

            def cf(*a, **k):
                k.pop("cursor", None)
                if not a and not k:
                    return orig_cf()
                return orig_cf(*a, **k)
            self.c.configure = cf
            self.c.config = cf
        self._lag_last = time.time()
        self.perf_log("start launcher %s  hover_level=%d" % (VERSION, self.hover_level))
        try:  # když okno stojí déle než 4 s, uloží se do logu, kde program právě vázne
            import faulthandler
            self._fh = open(os.path.join(DATA_DIR, "launcher_perf.log"), "a", encoding="utf-8")
            self._faulthandler = faulthandler
        except Exception:
            self._faulthandler = None

        def lag():
            if self._faulthandler:
                try:
                    self._faulthandler.cancel_dump_traceback_later()
                    self._faulthandler.dump_traceback_later(4, file=self._fh)
                except Exception:
                    pass
            now = time.time()
            if now - self._lag_last > 0.6:
                self.perf_log("okno stálo %d ms" % ((now - self._lag_last - 0.2) * 1000))
            self._lag_last = now
            self.after(200, lag)
        self.after(200, lag)

    def perf_log(self, text):
        try:
            with open(os.path.join(DATA_DIR, "launcher_perf.log"), "a", encoding="utf-8") as f:
                f.write("%s  %s\n" % (time.strftime("%H:%M:%S"), text))
        except OSError:
            pass

    def report_callback_exception(self, exc, val, tb):
        import traceback
        try:
            with open(os.path.join(DATA_DIR, "launcher_error.log"), "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + "".join(traceback.format_exception(exc, val, tb)) + "\n")
        except OSError:
            pass

    # --- sestavení ---
    # Rozložení (1280x720): ilustrace přes celé okno. Dole stav stahování a aktuální novinka, vpravo přihlášení, kanály a HRÁT,
    # vlevo dole menu, vlevo nahoře odkazy. Novinky, GM tým, event, server a žebříček jsou na stránce přes celé okno.
    HERO = (68, 74, 828, 434)
    CARDS = ((68, 450, 308, 560), (328, 450, 568, 560), (588, 450, 828, 560))
    RANK = (852, 74, 1212, 560)
    DOCK_R = (924, 348, 1256, 702)
    KEY = "#010203"
    PAGE_DY = 3000  # položky stránky jsou mimo okno, dokud se stránka neotevře
    CHIPS = (("web", "Web", "web"), ("discord", "Discord", "discord"), ("facebook", "Facebook", "facebook"), ("help", "Podpora", "support"))
    BAR_X0, BAR_X1 = 470, 888

    def build_ui(self):
        t, c = self.t, self.c
        txt, mut, acc = t["text"], t["muted"], t["accent"]
        self.pstate = load_state()
        try:  # 0 = bez efektů, 1 = zvýraznění, 2 = + ikony, 3 = + popisky, 4 = + změna kurzoru
            self.hover_level = int(self.pstate.get("hover_level", CFG.get("hover_level", 4)))
        except (TypeError, ValueError):
            self.hover_level = 4
        self.news, self.hero_i, self.hero_tick = [], 0, 0
        self.pg_open, self.pg_dy = False, self.PAGE_DY
        self.channel = int(self.pstate.get("channel", 0) or 0)
        self.remember = bool(self.pstate.get("remember", True))
        self.n_channels = max(1, min(8, int(CFG.get("channels", 4) or 4)))
        self.mode, self.sel_slot, self.logging = "login", -1, False
        self.store = v2accounts.AccountStore(self.accounts_path()).load()
        if any(self.store.slots):
            self.mode = "saved"
            last = self.pstate.get("last_login", "")
            for i, a in enumerate(self.store.slots):
                if a and a[0] == last:
                    self.sel_slot = i
            if self.sel_slot < 0:
                self.sel_slot = next(i for i, a in enumerate(self.store.slots) if a)
        # tlačítka okna vpravo nahoře (okno nemá systémový rám)
        self.sub_id = c.create_text(0, 0, text="", state="hidden")
        for tag, x, label in (("btn_min", self.W - 86, "—"), ("btn_close", self.W - 46, "×")):
            c.create_polygon(self.skew_poly(x, 14, x + 34, 42, 3, 10), fill=t["title_btn"], outline=t["accent"], width=1, tags=(tag, tag + "_bg"))
            c.create_text(x + 17, 28, text=label, fill=t["title_text"], font=self.font(12, True), tags=(tag,))
        for tag, x, label in (("btn_mus", self.W - 126, "♪"), ("btn_vup", self.W - 166, "+"), ("btn_vdn", self.W - 206, "−")):
            c.create_polygon(self.skew_poly(x, 14, x + 34, 42, 3, 10), fill=t["title_btn"], outline=t["accent"], width=1, tags=(tag, tag + "_bg"))
            item = c.create_text(x + 17, 28, text=label, fill=t["title_text"], font=self.font(12, True), tags=(tag,))
            if tag == "btn_mus":
                self.mus_txt = item
        self.vol_id = c.create_text(self.W - 214, 28, anchor="e", text="", fill=t["title_text"], font=self.font(9, True))
        self.hot("btn_mus", self.music_toggle, bg=True, col=acc)
        self.hot("btn_vup", lambda: self.music_volume(0.1), bg=True, col=acc)
        self.hot("btn_vdn", lambda: self.music_volume(-0.1), bg=True, col=acc)
        self.hot("btn_min", self.minimize, bg=True, col=acc)
        self.hot("btn_close", self.destroy, bg=True, col="#e5484d")
        c.bind("<ButtonPress-1>", self.drag_start)
        c.bind("<B1-Motion>", self.drag_move)
        c.bind("<ButtonRelease-1>", lambda e: setattr(self, "_sl", None))
        c.bind("<MouseWheel>", self.on_wheel)
        self.bind("<Escape>", lambda e: self.close_settings() if getattr(self, "_set_open", False) else self.close_page())
        # hlavní scéna
        self.build_rail()
        self.build_chips()
        self.build_login()
        self.build_channels()
        self.build_play()
        self.build_progress()
        # stránka přes celé okno (novinky, GM tým, event, server, žebříček)
        self.build_page()
        for tag in ("btn_min", "btn_close", "btn_mus", "btn_vup", "btn_vdn"):
            c.tag_raise(tag)
        c.tag_raise(self.vol_id)
        self.tip_bg = c.create_rectangle(0, 0, 1, 1, fill=t["note_bg"], outline=t["border"], state="hidden")
        self.tip_tx = c.create_text(0, 0, anchor="w", text="", fill="#ffffff", font=self.font(10, True), state="hidden")

    # --- stránka přes celé okno
    def build_page(self):
        c, t = self.c, self.t
        pg_img = self.img(t.get("bg_page"))
        if pg_img:
            self.bg_page = c.create_image(0, 0, anchor="nw", image=pg_img, state="hidden")
        else:
            self.bg_page = c.create_rectangle(0, 0, self.W, self.H, fill=t["bg"], outline="", state="hidden")
        mark = set(c.find_all())
        self.build_hero()
        self.build_side()
        pts = self.skew_poly(540, 618, 740, 664, 6, 20)
        c.create_polygon(pts, fill=t.get("play_fill", "#7b2fe0"), outline=t["gold"], width=2, tags=("pg_back", "pg_back_bg"))
        c.create_text(640, 641, text="ZPĚT", fill="#ffffff", font=self.font(13, True), tags=("pg_back",))
        c.tag_bind("pg_back", "<Button-1>", lambda e: self.close_page())
        c.tag_bind("pg_back", "<Enter>", lambda e: (c.configure(cursor="hand2"), c.itemconfigure("pg_back_bg", fill=t.get("play_hover", "#9a52ff"))))
        c.tag_bind("pg_back", "<Leave>", lambda e: (c.configure(cursor=""), c.itemconfigure("pg_back_bg", fill=t.get("play_fill", "#7b2fe0"))))
        for i in c.find_all():
            if i not in mark:
                c.addtag_withtag("pg", i)
        c.move("pg", 0, self.PAGE_DY)

    @staticmethod
    def skew_poly(x1, y1, x2, y2, a, b):
        """Nesouměrné seříznutí: vlevo nahoře a vpravo dole velký zub, ostatní rohy jen malý."""
        return [x1 + b, y1, x2 - a, y1, x2, y1 + a, x2, y2 - b, x2 - b, y2, x1 + a, y2, x1, y2 - a, x1, y1 + b]

    @staticmethod
    def cut_poly(x1, y1, x2, y2, k):
        """Obdélník se seříznutými rohy (jako tlačítka ve hrách)."""
        return [x1 + k, y1, x2 - k, y1, x2, y1 + k, x2, y2 - k, x2 - k, y2, x1 + k, y2, x1, y2 - k, x1, y1 + k]

    def open_page(self):
        if self.pg_open or getattr(self, "_set_open", False):
            return
        c = self.c
        self.pg_open = True
        self.entries_visible(False)
        c.itemconfigure(self.bg_page, state="normal")
        c.move("pg", 0, -self.pg_dy)
        self.pg_dy = 0
        self.hero_tick = 0
        self.hover_set(None)
        c.configure(cursor="")

    def close_page(self):
        if not self.pg_open:
            return
        c = self.c
        self.pg_open = False
        c.move("pg", 0, self.PAGE_DY - self.pg_dy)
        self.pg_dy = self.PAGE_DY
        c.itemconfigure(self.bg_page, state="hidden")
        c.configure(cursor="")
        self.entries_visible(True)

    # --- odkazy vlevo nahoře a menu vlevo dole
    def build_rail(self):
        c, t = self.c, self.t
        self.rail_imgs = {}
        self.rail_items, self._hov = [], None
        c.bind("<Motion>", self.on_motion, add="+")
        c.bind("<Leave>", lambda e: self.hover_set(None), add="+")
        for i, (label, cmd) in enumerate((("NOVINKY A ŽEBŘÍČEK", self.open_page), ("NASTAVENÍ HRY", self.open_settings))):
            y = 644 + i * 34
            tag = "nav%d" % i
            c.create_polygon(self.skew_poly(36, y - 15, 238, y + 15, 4, 14), fill=t["field"], outline=t["border"], width=1, tags=(tag, tag + "_bg"))
            c.create_polygon(36, y - 6, 41, y - 6, 41, y + 6, 36, y + 6, fill=t["accent"], outline="", tags=(tag,))
            c.create_text(54, y, text="◆", fill=t["gold"], font=self.font(8, True), tags=(tag,))
            tx = c.create_text(70, y, anchor="w", text=label, fill=t["text"], font=self.font(11, True), tags=(tag,))
            c.tag_bind(tag, "<Button-1>", lambda e, f=cmd: f())
            c.tag_bind(tag, "<Enter>", lambda e, it=tx, tg=tag: (c.configure(cursor="hand2"), c.itemconfigure(it, fill="#ffffff"), c.itemconfigure(tg + "_bg", fill=t["rail_on"], outline=t["accent"])))
            c.tag_bind(tag, "<Leave>", lambda e, it=tx, tg=tag: (c.configure(cursor=""), c.itemconfigure(it, fill=t["text"]), c.itemconfigure(tg + "_bg", fill=t["field"], outline=t["border"])))

    def build_chips(self):
        """Odkazy (Web, Discord, Facebook, Podpora) jsou v hlavním okně nahoře vlevo."""
        c, t = self.c, self.t
        for i, (ic, label, key) in enumerate(self.CHIPS):
            x, y = 84 + i * 44, 50
            tag = "rail_" + ic
            self.rail_imgs[ic] = (self.img("assets/ic_%s.png" % ic), self.img("assets/ic_%s_on.png" % ic))
            c.create_polygon(self.skew_poly(x - 17, y - 17, x + 17, y + 17, 4, 11), fill=t["title_btn"], outline=t["border"], width=2, tags=(tag, tag + "_box"))
            c.create_image(x, y, image=self.rail_imgs[ic][0], tags=(tag, tag + "_ic"))
            c.tag_bind(tag, "<Button-1>", lambda e, k=key: self.open(self.link(k)))
            self.rail_items.append((ic, label, x, y))

    def on_motion(self, e):
        """Jedno sledování myši místo událostí jednotlivých tlačítek: mění se jen při přechodu na jiné tlačítko."""
        idx = None
        if not self.pg_open and not getattr(self, "_set_open", False) and e.y <= 76:
            for k, (ic, label, x, y) in enumerate(self.rail_items):
                if abs(e.x - x) <= 19 and abs(e.y - y) <= 19:
                    idx = k
                    break
        if idx != self._hov:
            self.hover_set(idx)

    def hover_set(self, idx):
        if getattr(self, "_hov_busy", False):
            return
        self._hov_busy = True
        try:
            old = self._hov
            self._hov = idx
            if old is not None:
                self.rail_leave(self.rail_items[old][0])
            if idx is not None:
                ic, label, x, y = self.rail_items[idx]
                self.rail_enter(ic, label, x, y)
        finally:
            self._hov_busy = False

    def rail_enter(self, ic, label, x, y):
        lv = self.hover_level
        if lv < 1:
            return
        c = self.c
        self._hover_pause = time.time() + 0.6
        if lv >= 4:
            c.configure(cursor="hand2")
        c.itemconfigure("rail_%s_box" % ic, outline=self.t["accent"])
        if lv >= 2:
            c.itemconfigure("rail_%s_ic" % ic, image=self.rail_imgs[ic][1])
        if lv < 3:
            return
        c.itemconfigure(self.tip_tx, text=label, state="normal")
        x1, y1, x2, y2 = c.bbox(self.tip_tx) if c.bbox(self.tip_tx) else (0, 0, 80, 14)
        c.coords(self.tip_tx, x - 14, y - 34)
        c.coords(self.tip_bg, x - 20, y - 48, x - 14 + (x2 - x1) + 10, y - 20)
        c.itemconfigure(self.tip_bg, state="normal")
        c.tag_raise(self.tip_bg)
        c.tag_raise(self.tip_tx)

    def rail_leave(self, ic):
        lv = self.hover_level
        if lv < 1:
            return
        c = self.c
        if lv >= 4:
            c.configure(cursor="")
        c.itemconfigure("rail_%s_box" % ic, outline=self.t["border"])
        if lv >= 2:
            c.itemconfigure("rail_%s_ic" % ic, image=self.rail_imgs[ic][0])
        if lv >= 3:
            c.itemconfigure(self.tip_tx, state="hidden")
            c.itemconfigure(self.tip_bg, state="hidden")

    # --- hlavní novinka (střídají se všechny novinky) a spodní karty: GM tým, event, Discord
    MAX_NEWS = 8
    GM_ROWS = 4

    def build_hero(self):
        c, t = self.c, self.t
        x0, y0, x1, y1 = self.HERO
        self.hero_imgs = [self.img("assets/hero%d.png" % i) for i in (1, 2, 3)]
        self.news_img, self._img_try = {}, {}
        self.hero_pic = c.create_image(x0 + 1, y0 + 1, anchor="nw", image=self.hero_imgs[0], tags=("hero_click",))
        self.hero_tag = c.create_text(x0 + 26, 300, anchor="sw", text="NOVINKY", fill=t["accent"], font=self.font(10, True))
        self.hero_title = c.create_text(x0 + 26, 346, anchor="sw", width=700, text="Načítám novinky…", fill="#ffffff", font=self.font(23, True), tags=("hero_click",))
        self.hero_text = c.create_text(x0 + 26, 354, anchor="nw", width=660, text="", fill="#d9d0f2", font=self.font(11))
        c.create_rectangle(x0 + 26, 398, x0 + 214, 424, fill=t["panel"], outline=t["accent"], tags=("hero_btn", "hero_btn_bg"))
        c.create_text(x0 + 120, 411, text="ČÍST DÁL NA WEBU  →", fill="#ffffff", font=self.font(9, True), tags=("hero_btn",))
        self.dots = []
        for i in range(self.MAX_NEWS):
            self.dots.append(c.create_oval(0, 410, 10, 420, fill=t["muted"], outline="", tags=("dot%d" % i,), state="hidden"))
            c.tag_bind("dot%d" % i, "<Button-1>", lambda e, k=i: self.hero_go(k))
        for tg, x, label in (("hero_prev", x0 + 12, "◀"), ("hero_next", x1 - 40, "▶")):
            c.create_rectangle(x, 168, x + 28, 212, fill=t["panel"], outline=t["border"], tags=(tg, tg + "_bg"), state="hidden")
            c.create_text(x + 14, 190, text=label, fill=t["accent"], font=self.font(10, True), tags=(tg, tg + "_tx"), state="hidden")
            c.tag_bind(tg, "<Enter>", lambda e, g=tg: (c.configure(cursor="hand2"), c.itemconfigure(g + "_bg", outline=t["accent"])))
            c.tag_bind(tg, "<Leave>", lambda e, g=tg: (c.configure(cursor=""), c.itemconfigure(g + "_bg", outline=t["border"])))
        c.tag_bind("hero_prev", "<Button-1>", lambda e: self.hero_go(self.hero_i - 1))
        c.tag_bind("hero_next", "<Button-1>", lambda e: self.hero_go(self.hero_i + 1))
        for tg in ("hero_click", "hero_btn"):
            c.tag_bind(tg, "<Button-1>", lambda e: self.open_news(self.hero_i))
            c.tag_bind(tg, "<Enter>", lambda e: c.configure(cursor="hand2"))
            c.tag_bind(tg, "<Leave>", lambda e: c.configure(cursor=""))
        # karta 1: GM tým (online/offline, posun kolečkem nebo šipkami)
        gx, gy = self.CARDS[0][0], self.CARDS[0][1]
        c.create_text(gx + 16, gy + 18, anchor="w", text="GM TÝM", fill=t["accent"], font=self.font(8, True))
        self.gm_cnt = c.create_text(gx + 190, gy + 18, anchor="e", text="", fill=t["muted"], font=self.font(8, True))
        self.gm_up = c.create_text(gx + 204, gy + 18, text="▲", fill=t["accent"], font=self.font(8, True), state="hidden", tags=("gm_up",))
        self.gm_dn = c.create_text(gx + 222, gy + 18, text="▼", fill=t["accent"], font=self.font(8, True), state="hidden", tags=("gm_dn",))
        self.gm_rows = []
        for i in range(self.GM_ROWS):
            y = gy + 40 + i * 17
            dot = c.create_oval(gx + 16, y - 4, gx + 24, y + 4, fill=t["muted"], outline="", state="hidden")
            nm = c.create_text(gx + 32, y, anchor="w", text="", fill=t["panel_text"], font=self.font(9), state="hidden")
            st = c.create_text(gx + 224, y, anchor="e", text="", fill=t["panel_text"], font=self.font(8, True), state="hidden")
            self.gm_rows.append((dot, nm, st))
        self.gm_empty = c.create_text(gx + 16, gy + 40, anchor="nw", width=208, text="Načítám…", fill=t["muted"], font=self.font(9))
        self.gm_all, self.gm_off = [], 0
        for tg, step in (("gm_up", -1), ("gm_dn", 1)):
            c.tag_bind(tg, "<Button-1>", lambda e, k=step: self.gm_scroll(k))
            c.tag_bind(tg, "<Enter>", lambda e: c.configure(cursor="hand2"))
            c.tag_bind(tg, "<Leave>", lambda e: c.configure(cursor=""))
        # karta 2: aktuální event
        ex, ey = self.CARDS[1][0], self.CARDS[1][1]
        c.create_text(ex + 16, ey + 18, anchor="w", text="AKTUÁLNÍ EVENT", fill=t["accent"], font=self.font(8, True))
        self.ev_title = c.create_text(ex + 16, ey + 40, anchor="w", width=208, text="", fill=t["event_text"], font=self.font(13, True))
        self.ev_text = c.create_text(ex + 16, ey + 56, anchor="nw", width=208, text="", fill=t["panel_text"], font=self.font(9))
        self.ev_left = c.create_text(ex + 16, ey + 96, anchor="w", width=208, text="", fill=t["accent2"], font=self.font(10, True))
        self.ev_data = {}
        # karta 3: server a hráči online
        dx, dy = self.CARDS[2][0], self.CARDS[2][1]
        c.create_text(dx + 16, dy + 18, anchor="w", text="SERVER", fill=t["accent"], font=self.font(8, True))
        self.on_val = c.create_text(dx + 16, dy + 50, anchor="w", text="…", fill="#ffffff", font=self.font(20, True))
        self.on_sub = c.create_text(dx + 16, dy + 74, anchor="w", width=208, text="Zjišťuji stav serveru", fill=t["panel_text"], font=self.font(9))
        self.on_extra = c.create_text(dx + 16, dy + 96, anchor="w", width=208, text="", fill=t["accent2"], font=self.font(9, True))
        self.stats = (None, None)

    def hero_go(self, i):
        """Ruční přepnutí novinky; automatické střídání se na chvíli zdrží."""
        if not self.news:
            return
        self.show_hero(i)
        self.hero_tick = -4

    def show_hero(self, i):
        c = self.c
        m = len(self.news)
        self.hero_i = i = i % max(1, m)
        self.hero_tick = 0
        n = self.news[i] if i < m else None
        img = self.news_img.get((n or {}).get("image")) or self.hero_imgs[i % 3]
        c.itemconfigure(self.hero_pic, image=img)
        x1 = self.HERO[2]
        for k, d in enumerate(self.dots):
            if k < m and m > 1:
                cx = x1 - 30 - (m - 1 - k) * 18
                c.coords(d, cx - 5, 410 + self.pg_dy, cx + 5, 420 + self.pg_dy)
                c.itemconfigure(d, state="normal", fill=self.t["accent"] if k == i else self.t["muted"])
            else:
                c.itemconfigure(d, state="hidden")
        for tg in ("hero_prev", "hero_next"):
            c.itemconfigure(tg, state="normal" if m > 1 else "hidden")
        c.itemconfigure(self.hero_title, text=clip(n.get("title"), 90) if n else "Zatím žádné novinky")
        c.itemconfigure(self.hero_text, text=clip(n.get("excerpt"), 200) if n else "Sleduj web, brzy se tu objeví novinky a aktualizace.")
        cat = str((n or {}).get("category") or "Novinky").upper()
        c.itemconfigure(self.hero_tag, text=(cat + "  ·  " + self.cz_date(n.get("date"))) if n else "NOVINKY")
        bb = c.bbox(self.hero_title)
        if bb:
            c.coords(self.hero_tag, self.HERO[0] + 26, bb[1] - 8)
        c.itemconfigure(self.tk_cat, text=(cat + "  ·  " + self.cz_date(n.get("date"))) if n else "NOVINKY")
        c.itemconfigure(self.tk_title, text=clip(n.get("title"), 60) if n else "Zatím žádné novinky")

    def load_news_images(self, news):
        """Stáhne fotky novinek z webu (jen z vlastní domény), upraví je na velikost panelu a uloží do cache vedle nastavení."""
        cache = os.path.join(DATA_DIR, "newscache")
        for n in news:
            url = str(n.get("image") or "")
            if not url or url in self.news_img or time.time() - self._img_try.get(url, 0) < 300:
                continue
            self._img_try[url] = time.time()
            key = os.path.join(cache, hashlib.sha1(url.encode("utf-8")).hexdigest()[:24] + ".b64")
            try:
                if os.path.isfile(key):
                    with open(key, "r", encoding="ascii") as f:
                        b64 = f.read()
                else:
                    if not url.lower().startswith("https://"):
                        continue
                    b64 = news_png_b64(fetch_bytes(url))
                    if not b64:
                        return  # bez Pillow fotky nejdou, zůstanou pevné obrázky
                    try:
                        os.makedirs(cache, exist_ok=True)
                        old = sorted((os.path.join(cache, x) for x in os.listdir(cache)), key=os.path.getmtime)
                        for x in old[:-30]:
                            os.remove(x)
                        with open(key, "w", encoding="ascii") as f:
                            f.write(b64)
                    except OSError:
                        pass
                self.ui(self.set_news_image, url, b64)
            except Exception:  # noqa: BLE001
                log_exc()

    def set_news_image(self, url, b64):
        try:
            self.news_img[url] = tk.PhotoImage(data=b64)
        except tk.TclError:
            return
        cur = self.news[self.hero_i] if self.hero_i < len(self.news) else None
        if cur and cur.get("image") == url:
            keep = self.hero_tick
            self.show_hero(self.hero_i)
            self.hero_tick = keep

    @staticmethod
    def cz_date(d):
        try:
            y, m, dd = str(d)[:10].split("-")
            return "%d. %d. %s" % (int(dd), int(m), y)
        except (ValueError, TypeError):
            return str(d or "")

    def open_news(self, i):
        n = self.news[i] if i < len(self.news) else None
        self.open((n or {}).get("url") or self.link("web"))

    # --- přihlášení (pole + uložené účty)
    def accounts_path(self):
        return os.path.join(game_root(), "config", "v2_accounts.dat")

    def autologin_path(self):
        return os.path.join(game_root(), "config", "v2_autologin.dat")

    def make_entry(self, show=""):
        t = self.t
        e = tk.Entry(self, bg=t["field"], fg=t["text"], insertbackground=t["accent2"], relief="flat", bd=0, highlightthickness=1,
                     highlightbackground=t["border"], highlightcolor=t["accent"], font=self.font(11), show=show)
        e.bind("<Return>", lambda ev: self.on_play())
        return e

    def build_login(self):
        c, t = self.c, self.t
        self.lg_title = c.create_text(944, 364, anchor="w", text="PŘIHLÁŠENÍ", fill=t["accent2"], font=self.font(10, True))
        self.lg_switch = c.create_text(1236, 364, anchor="e", text="", fill=t["accent"], font=self.font(9, True), tags=("lg_switch",))
        c.tag_bind("lg_switch", "<Button-1>", lambda e: self.toggle_mode())
        c.tag_bind("lg_switch", "<Enter>", lambda e: c.configure(cursor="hand2"))
        c.tag_bind("lg_switch", "<Leave>", lambda e: c.configure(cursor=""))
        self.e_id, self.e_pw = self.make_entry(), self.make_entry("•")
        self.w_id = c.create_window(944, 402, anchor="nw", window=self.e_id, width=292, height=28)
        self.w_pw = c.create_window(944, 450, anchor="nw", window=self.e_pw, width=292, height=28)
        c.create_text(944, 392, anchor="w", text="PŘEZDÍVKA NEBO E-MAIL", fill=t["muted"], font=self.font(8, True), tags=("lg_login",))
        c.create_text(944, 440, anchor="w", text="HESLO", fill=t["muted"], font=self.font(8, True), tags=("lg_login",))
        c.create_text(1236, 440, anchor="e", text="ukázat", fill=t["accent"], font=self.font(8, True), tags=("lg_login", "lg_show"))
        c.tag_bind("lg_show", "<Button-1>", lambda e: self.e_pw.configure(show="" if self.e_pw.cget("show") else "•"))
        c.tag_bind("lg_show", "<Enter>", lambda e: c.configure(cursor="hand2"))
        c.tag_bind("lg_show", "<Leave>", lambda e: c.configure(cursor=""))
        self.chk_box = c.create_rectangle(944, 490, 958, 504, outline=t["accent"], fill="", tags=("lg_login", "lg_chk"))
        self.chk_mark = c.create_text(951, 497, text="✓", fill="#ffffff", font=self.font(9, True), tags=("lg_login", "lg_chk"))
        c.create_text(966, 497, anchor="w", text="Zapamatovat heslo na tomto počítači", fill=t["text"], font=self.font(9), tags=("lg_login", "lg_chk"))
        c.tag_bind("lg_chk", "<Button-1>", lambda e: self.set_remember(not self.remember))
        c.tag_bind("lg_chk", "<Enter>", lambda e: c.configure(cursor="hand2"))
        c.tag_bind("lg_chk", "<Leave>", lambda e: c.configure(cursor=""))
        for x, label, key, tag in ((944, "Zapomenuté heslo", "forgot", "lg_forgot"), (1078, "Založit účet na webu", "register", "lg_reg")):
            c.create_text(x, 523, anchor="w", text=label, fill=t["accent"], font=self.font(9), tags=("lg_login", tag))
            c.tag_bind(tag, "<Button-1>", lambda e, k=key: self.open(self.link(k)))
            c.tag_bind(tag, "<Enter>", lambda e: c.configure(cursor="hand2"))
            c.tag_bind(tag, "<Leave>", lambda e: c.configure(cursor=""))
        self.set_remember(self.remember, save=False)
        self.apply_mode()

    def set_remember(self, v, save=True):
        self.remember = bool(v)
        self.c.itemconfigure(self.chk_mark, state="normal" if v else "hidden")
        if save:
            self.pstate["remember"] = self.remember
            save_state(self.pstate)

    def toggle_mode(self):
        if self.mode == "saved":
            self.mode = "login"
        elif any(self.store.slots):
            self.mode = "saved"
        else:
            self.mode = "login"
            self.e_id.focus_set()
        self.apply_mode()

    def apply_mode(self):
        c = self.c
        login = self.mode == "login"
        c.itemconfigure("lg_login", state="normal" if login else "hidden")
        c.itemconfigure(self.w_id, state="normal" if login else "hidden")
        c.itemconfigure(self.w_pw, state="normal" if login else "hidden")
        c.itemconfigure(self.lg_title, text="PŘIHLÁŠENÍ" if login else "ULOŽENÉ ÚČTY")
        c.itemconfigure(self.lg_switch, text=("Uložené účty ▸" if any(self.store.slots) else "") if login else "Jiný účet ▸")
        if not login:
            self.draw_accounts()
        else:
            c.delete("lg_saved")
            self.set_remember(self.remember, save=False)
        self.update_caption()

    def draw_accounts(self):
        c, t = self.c, self.t
        c.delete("lg_saved")
        slots = [(i, a) for i, a in enumerate(self.store.slots) if a]
        for row, (i, a) in enumerate(slots):
            y = 402 + row * 25
            on = i == self.sel_slot
            tg = "lg_saved"
            c.create_rectangle(944, y - 11, 1236, y + 11, fill=t["rail_on"] if on else t["field"], outline=t["accent"] if on else t["border"], tags=(tg, "acc%d" % i))
            c.create_rectangle(950, y - 7, 964, y + 7, fill=t["accent"], outline="", tags=(tg, "acc%d" % i))
            c.create_text(957, y, text=(a[0][:1] or "?").upper(), fill=t.get("play_text", "#ffffff"), font=self.font(8, True), tags=(tg, "acc%d" % i))
            c.create_text(974, y, anchor="w", text=clip(a[0], 26), fill="#ffffff" if on else t["text"], font=self.font(10, True), tags=(tg, "acc%d" % i))
            c.create_text(1224, y, text="×", fill=t["bad"], font=self.font(13, True), tags=(tg, "del%d" % i))
            c.tag_bind("acc%d" % i, "<Button-1>", lambda e, k=i: self.pick_account(k))
            c.tag_bind("del%d" % i, "<Button-1>", lambda e, k=i: self.delete_account(k))
            for tg2 in ("acc%d" % i, "del%d" % i):
                c.tag_bind(tg2, "<Enter>", lambda e: c.configure(cursor="hand2"))
                c.tag_bind(tg2, "<Leave>", lambda e: c.configure(cursor=""))
        c.create_text(944, 402 + len(slots) * 25 + 8, anchor="w", text="+  Přidat další účet", fill=t["accent"], font=self.font(9, True), tags=("lg_saved", "lg_add"))
        c.tag_bind("lg_add", "<Button-1>", lambda e: self.toggle_mode())
        c.tag_bind("lg_add", "<Enter>", lambda e: c.configure(cursor="hand2"))
        c.tag_bind("lg_add", "<Leave>", lambda e: c.configure(cursor=""))
        self.keep_under_page("lg_saved")

    def keep_under_page(self, tag):
        """Položky, které se kreslí znovu za běhu, nesmí skončit nad stránkou novinek."""
        if getattr(self, "bg_page", None):
            self.c.tag_lower(tag, self.bg_page)

    def pick_account(self, i):
        self.sel_slot = i
        self.draw_accounts()
        self.update_caption()

    def delete_account(self, i):
        self.store.clear(i)
        if self.sel_slot == i:
            self.sel_slot = next((k for k, a in enumerate(self.store.slots) if a), -1)
        if not any(self.store.slots):
            self.mode = "login"
            self.apply_mode()
        else:
            self.draw_accounts()
            self.update_caption()

    # --- kanály
    def build_channels(self):
        c, t = self.c, self.t
        self.draw_channels()

    def draw_channels(self):
        c, t = self.c, self.t
        c.delete("chn")
        n = self.n_channels
        self.channel = min(self.channel, n - 1)
        gap, wtot = 8, 292
        w = (wtot - gap * (n - 1)) / n
        api = getattr(self, "api", {})
        up = bool(api.get("server_online", True)) if isinstance(api, dict) else True
        cho = api.get("channels_on") if isinstance(api, dict) else None
        self.ch_up = [bool(up and (cho[i] if isinstance(cho, list) and i < len(cho) else True)) for i in range(n)]
        if not self.ch_up[self.channel] and any(self.ch_up):
            self.channel = self.ch_up.index(True)
        for i in range(n):
            x = 944 + i * (w + gap)
            on = i == self.channel
            cup = self.ch_up[i]
            tg = "ch%d" % i
            c.create_polygon(self.skew_poly(x, 556, x + w, 594, 4, 11), fill=t["rail_on"] if on else t["field"], outline=t["accent"] if on else t["border"], width=2 if on else 1, tags=("chn", tg))
            c.create_text(x + w / 2, 569, text="CH%d" % (i + 1), fill="#ffffff" if on else (t["text"] if cup else t["muted"]), font=self.font(10, True), tags=("chn", tg))
            c.create_text(x + w / 2, 584, text="Volno" if cup else "Offline", fill=t["ok"] if cup else t["bad"], font=self.font(8), tags=("chn", tg))
            c.tag_bind(tg, "<Button-1>", lambda e, k=i: self.pick_channel(k))
            c.tag_bind(tg, "<Enter>", lambda e: c.configure(cursor="hand2"))
            c.tag_bind(tg, "<Leave>", lambda e: c.configure(cursor=""))
        c.tag_raise("note")
        self.keep_under_page("chn")

    def pick_channel(self, i):
        if not getattr(self, "ch_up", [True] * 8)[i]:
            self.say("Kanál CH%d je vypnutý." % (i + 1), "bad")
            return
        self.channel = i
        self.pstate["channel"] = i
        save_state(self.pstate)
        self.draw_channels()
        self.update_caption()

    # --- tlačítko Hrát a zpráva pod ním
    def build_play(self):
        c, t = self.c, self.t
        fill, hov = t.get("play_fill", "#7b2fe0"), t.get("play_hover", "#9a52ff")
        c.create_polygon(self.skew_poly(944, 604, 1236, 654, 6, 22), fill=fill, outline=t["gold"], width=2, tags=("play", "play_bg"))
        self.play_txt = c.create_text(1090, 629, text="PŘIHLÁSIT A HRÁT", fill="#ffffff", font=self.font(15, True), tags=("play",))
        self.play_cap = c.create_text(1090, 676, text="", fill=t["muted"], font=self.font(9), width=300, justify="center")
        c.tag_bind("play", "<Button-1>", lambda e: self.on_play())
        c.tag_bind("play", "<Enter>", lambda e: (c.configure(cursor="hand2"), c.itemconfigure("play_bg", fill=hov)))
        c.tag_bind("play", "<Leave>", lambda e: (c.configure(cursor=""), c.itemconfigure("play_bg", fill=fill)))
        self.update_caption()

    def say(self, text, kind="info"):
        col = {"info": self.t["muted"], "bad": self.t["bad"], "ok": self.t["ok"]}[kind]
        self.c.itemconfigure(self.play_cap, text=text, fill=col)

    def update_caption(self):
        if getattr(self, "logging", False) or not hasattr(self, "play_txt"):
            return
        who = ""
        if self.mode == "saved" and self.sel_slot >= 0 and self.store.get(self.sel_slot):
            who = self.store.get(self.sel_slot)[0] + "  ·  "
        self.c.itemconfigure(self.play_txt, text="HRÁT" if who else "PŘIHLÁSIT A HRÁT")
        self.say("%sCH%d  ·  přihlášení přes launcher" % (who, self.channel + 1))

    # --- žebříček (hráči / cechy) na stránce, listuje se kolečkem myši nebo šipkami
    TOP_ROWS = 15

    def build_side(self):
        c, t = self.c, self.t
        rx0, ry0, rx1, ry1 = self.RANK
        # stav serveru je vidět u kanálů a v kartách, tyto položky zůstávají jen skryté kvůli zbytku kódu
        self.dot = c.create_oval(0, 0, 1, 1, state="hidden")
        self.state_id = c.create_text(0, 0, text="", state="hidden")
        self.vals = {}
        self.top_tab, self.top_off = "players", 0
        self.top_data = {"players": [], "guilds": []}
        self.top_tabs = {}
        for key, label, x in (("players", "HRÁČI", rx0 + 18), ("guilds", "CECHY", rx0 + 90)):
            tg = "toptab_" + key
            it = c.create_text(x, ry0 + 19, anchor="w", text=label, fill=t["muted"], font=self.font(10, True), tags=(tg,))
            bb = c.bbox(it) or (x, ry0 + 12, x + 50, ry0 + 26)
            ul = c.create_line(bb[0], ry0 + 32, bb[2], ry0 + 32, fill=t["accent"], width=2, state="hidden")
            self.top_tabs[key] = (it, ul)
            c.tag_bind(tg, "<Button-1>", lambda e, k=key: self.set_top_tab(k))
            c.tag_bind(tg, "<Enter>", lambda e: c.configure(cursor="hand2"))
            c.tag_bind(tg, "<Leave>", lambda e: c.configure(cursor=""))
        self.top_cnt = c.create_text(rx1 - 48, ry0 + 19, anchor="e", text="", fill=t["muted"], font=self.font(8, True))
        self.top_up = c.create_text(rx1 - 32, ry0 + 19, text="▲", fill=t["accent"], font=self.font(8, True), state="hidden", tags=("top_up",))
        self.top_dn = c.create_text(rx1 - 14, ry0 + 19, text="▼", fill=t["accent"], font=self.font(8, True), state="hidden", tags=("top_dn",))
        for tg, step in (("top_up", -1), ("top_dn", 1)):
            c.tag_bind(tg, "<Button-1>", lambda e, k=step: self.top_scroll(k))
            c.tag_bind(tg, "<Enter>", lambda e: c.configure(cursor="hand2"))
            c.tag_bind(tg, "<Leave>", lambda e: c.configure(cursor=""))
        self.top_rows = []
        for i in range(self.TOP_ROWS):
            y = ry0 + 62 + i * 28
            rk = c.create_text(rx0 + 18, y, anchor="w", text="", fill=t["accent"], font=self.font(9, True), state="hidden", tags=("top_click",))
            nm = c.create_text(rx0 + 52, y, anchor="w", text="", fill="#ffffff", font=self.font(10), state="hidden", tags=("top_click",))
            lv = c.create_text(rx1 - 16, y, anchor="e", text="", fill=t["accent2"], font=self.font(9, True), state="hidden", tags=("top_click",))
            self.top_rows.append((rk, nm, lv))
        self.top_empty = c.create_text(rx0 + 16, ry0 + 52, anchor="nw", width=320, text="Načítám žebříček…", fill=t["muted"], font=self.font(9))
        c.tag_bind("top_click", "<Button-1>", lambda e: self.open(self.link("ranking") or self.link("web")))
        c.tag_bind("top_click", "<Enter>", lambda e: c.configure(cursor="hand2"))
        c.tag_bind("top_click", "<Leave>", lambda e: c.configure(cursor=""))
        self.set_top_tab("players")

    # --- stahování a aktuální novinka (dolní panel uprostřed)
    def build_progress(self):
        c, t = self.c, self.t
        x0, x1 = self.BAR_X0, self.BAR_X1
        self.status_id = c.create_text(392, 520, anchor="w", width=500, text="", fill="#ffffff", font=self.font(11, True))
        self.tk_cat = c.create_text(392, 554, anchor="w", text="NOVINKY", fill=t["accent"], font=self.font(8, True))
        self.tk_title = c.create_text(392, 574, anchor="w", width=380, text="Načítám novinky…", fill="#ffffff", font=self.font(11, True), tags=("tk_click",))
        self.tk_more = c.create_text(888, 574, anchor="e", text="VŠE  ▸", fill=t["accent"], font=self.font(9, True), tags=("tk_more",))
        for tg in ("tk_click",):
            c.tag_bind(tg, "<Button-1>", lambda e: self.open_news(self.hero_i))
        c.tag_bind("tk_more", "<Button-1>", lambda e: self.open_page())
        for tg in ("tk_click", "tk_more"):
            c.tag_bind(tg, "<Enter>", lambda e: c.configure(cursor="hand2"))
            c.tag_bind(tg, "<Leave>", lambda e: c.configure(cursor=""))
        self.bars = []
        for (bx0, by0, bx1, by1), label, col in zip(((x0, 599, x1, 609), (x0, 625, x1, 635)), ("Soubor", "Celkem"), (t["bar_file"], t["accent"])):
            c.create_text(392, (by0 + by1) / 2, anchor="w", text=label, fill=t["muted"], font=self.font(8, True))
            self.bars.append(c.create_rectangle(bx0 + 1, by0, bx0 + 1, by1, outline="", fill=col))
        c.create_text(392, 678, anchor="w", text="© Violet2  ·  v%s  ·  licence" % VERSION, fill=t["muted"], font=self.font(8), tags=("about",))
        self.hot("about", self.about)
        c.create_text(888, 678, anchor="e", text="Zkontrolovat soubory hry", fill=t["accent"], font=self.font(8, True), tags=("check_btn",))
        c.tag_bind("check_btn", "<Button-1>", lambda e: self.start_patch())
        c.tag_bind("check_btn", "<Enter>", lambda e: c.configure(cursor="hand2"))
        c.tag_bind("check_btn", "<Leave>", lambda e: c.configure(cursor=""))

    # --- nastavení hry (okno uvnitř launcheru, zapisuje config/metin2.cfg) ---
    def settings_path(self):
        return safe_rel(CFG.get("settings_file") or "config/metin2.cfg")

    def open_settings(self):
        if CFG.get("use_config_exe"):  # starý config.exe, jen když si ho někdo výslovně zapne v launcher.json
            self.run(CFG["config_exe"])
            return
        if getattr(self, "_set_open", False):
            return
        try:
            self.set_path = self.settings_path()
            cfg = v2cfg.read_cfg(self.set_path)
        except (OSError, ValueError) as e:
            self.notify("Nastavení nejde načíst:\n%s" % clip(e, 120))
            return
        self.set_model = v2cfg.SettingsModel(cfg, (self.winfo_screenwidth(), self.winfo_screenheight()))
        self._set_open = True
        self.entries_visible(False)
        self.draw_settings()

    def close_settings(self):
        self.c.delete("set")
        self._set_open = False
        self.entries_visible(True)

    def rrect(self, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.c.create_polygon(pts, smooth=True, **kw)

    def draw_settings(self):
        c, t, m = self.c, self.t, self.set_model
        c.delete("set")
        self._wheel = []
        txt, ttl, acc, mut = t["panel_text"], t["panel_title"], t["accent"], t["muted"]
        if not hasattr(self, "set_bg_img"):
            self.set_bg_img = self.img("assets/bg_set.png")
        if self.set_bg_img:  # celé okno překryje jen ztmavená ilustrace, aby byl vidět pouze dialog
            c.create_image(0, 0, anchor="nw", image=self.set_bg_img, tags=("set",))
        else:
            c.create_rectangle(0, 0, self.W, self.H, fill=t["bg"], outline="", tags=("set",))
        c.create_polygon(self.cut_poly(250, 96, 1030, 626, 26), fill=t["note_bg"], outline=t["accent"], width=2, tags=("set",))
        c.create_polygon(self.cut_poly(258, 104, 1022, 618, 22), fill="", outline=t["bar_outline"], width=1, tags=("set",))
        c.create_text(640, 128, text="NASTAVENÍ HRY", fill=ttl, font=self.font(15, True), tags=("set",))
        c.create_line(280, 152, 1000, 152, fill=t["bar_outline"], tags=("set",))
        for x, head, rows in ((280, "OBRAZ", (("res", "Rozlišení"), ("freq", "Frekvence"), ("gamma", "Gama"), ("windowed", "Režim"),
                                                ("swcursor", "Kurzor myši"), ("ime", "Zadávání textu"))),
                              (660, "GRAFIKA A ZVUK", (("fog", "Dohlednost (mlha)"), ("shadow", "Stíny"), ("tiling", "Výpočet grafiky"),
                                                       ("music", "Hudba"), ("sfx", "Zvuky")))):
            c.create_text(x, 178, anchor="w", text=head, fill=acc, font=self.font(11, True), tags=("set",))
            for i, (key, label) in enumerate(rows):
                y = 218 + i * 48
                c.create_text(x, y, anchor="w", text=label, fill=txt, font=self.font(11), tags=("set",))
                if key in ("music", "sfx"):
                    self.draw_slider(key, x + 160, y)
                else:
                    self.draw_choice(key, x + 160, y)
        for cx, label, cmd, main in ((440, "Uložit", self.save_settings, True), (640, "Výchozí", self.default_settings, False), (840, "Zrušit", self.close_settings, False)):
            tag = "set_btn_" + label
            c.create_polygon(self.cut_poly(cx - 80, 560, cx + 80, 602, 12), fill=acc if main else t["bar_bg"], outline=t["accent"] if not main else t["gold"], width=2, tags=("set", tag))
            c.create_text(cx, 581, text=label, fill="#ffffff" if main else txt, font=self.font(12, True), tags=("set", tag))
            c.tag_bind(tag, "<Button-1>", lambda e, f=cmd: f())
            c.tag_bind(tag, "<Enter>", lambda e: c.configure(cursor="hand2"))
            c.tag_bind(tag, "<Leave>", lambda e: c.configure(cursor=""))
        c.create_text(640, 612, text="Nastavení se ukládá do config/metin2.cfg a aktualizace ho nepřepíše.", fill=mut, font=self.font(9), tags=("set",))
        for tg in ("btn_min", "btn_close", "btn_mus", "btn_vup", "btn_vdn"):
            c.tag_raise(tg)
        c.tag_raise(self.vol_id)

    def draw_choice(self, key, x, y):
        c, m, txt, acc = self.c, self.set_model, self.t["panel_text"], self.t["accent"]
        tag = "set_c_" + key
        c.create_polygon(self.cut_poly(x, y - 17, x + 180, y + 17, 8), fill=self.t["bar_bg"], outline=self.t["bar_outline"], tags=("set", tag))
        c.create_text(x + 90, y, text=m.label(key), fill=txt, font=self.font(11, True), tags=("set", tag))
        for dx, ch, d in ((14, "\u2039", -1), (166, "\u203a", 1)):
            at = "%s_%d" % (tag, d)
            c.create_text(x + dx, y - 1, text=ch, fill=acc, font=self.font(16, True), tags=("set", tag, at))
            c.tag_bind(at, "<Button-1>", lambda e, k=key, dd=d: self.step_setting(k, dd))
        self._wheel.append((x, y - 17, x + 180, y + 17, key))  # kolečko myši se řeší na úrovni plátna (on_wheel)
        c.tag_bind(tag, "<Enter>", lambda e: c.configure(cursor="hand2"))
        c.tag_bind(tag, "<Leave>", lambda e: c.configure(cursor=""))

    def draw_slider(self, key, x, y):
        c, m, txt, acc = self.c, self.set_model, self.t["panel_text"], self.t["accent"]
        tag, w = "set_s_" + key, 120
        v = m.st[key]
        c.create_rectangle(x, y - 3, x + w, y + 3, fill=self.t["bar_bg"], outline=self.t["bar_outline"], tags=("set", tag))
        c.create_rectangle(x, y - 3, x + w * v, y + 3, fill=acc, outline="", tags=("set", tag))
        c.create_oval(x + w * v - 8, y - 8, x + w * v + 8, y + 8, fill=self.t["accent2"], outline=self.t["bar_outline"], tags=("set", tag))
        c.create_text(x + w + 14, y, anchor="w", text="%d %%" % round(v * 100), fill=txt, font=self.font(10, True), tags=("set", tag))
        def press(e):
            self._sl = (key, x, w)  # tažení řeší okno (drag_move), protože při překreslení položky zanikají
            self.slider_move(e)
        c.tag_bind(tag, "<Button-1>", press)
        c.tag_bind(tag, "<Enter>", lambda e: c.configure(cursor="hand2"))
        c.tag_bind(tag, "<Leave>", lambda e: c.configure(cursor=""))

    def on_wheel(self, e):
        if not getattr(self, "_set_open", False):
            if not self.pg_open:
                return
            cx0, cy0, cx1, cy1 = self.CARDS[0]
            rx0, ry0, rx1, ry1 = self.RANK
            if cx0 <= e.x <= cx1 and cy0 <= e.y <= cy1:
                self.gm_scroll(-1 if e.delta > 0 else 1)
            elif rx0 <= e.x <= rx1 and ry0 <= e.y <= ry1:
                self.top_scroll(-1 if e.delta > 0 else 1)
            return
        for x1, y1, x2, y2, key in getattr(self, "_wheel", []):
            if x1 <= e.x <= x2 and y1 <= e.y <= y2:
                self.step_setting(key, -1 if e.delta > 0 else 1)
                return

    def slider_move(self, e):
        key, x, w = self._sl
        self.set_model.st[key] = min(1.0, max(0.0, (e.x - x) / w))
        self.draw_settings()

    def step_setting(self, key, d):
        self.set_model.step(key, d)
        self.draw_settings()

    def default_settings(self):
        self.set_model.reset()
        self.draw_settings()

    def save_settings(self):
        try:
            v2cfg.write_cfg(self.set_path, self.set_model.to_cfg())
        except OSError as e:
            self.close_settings()
            self.notify("Nastavení se nepodařilo uložit:\n%s" % clip(e, 120))
            return
        self.close_settings()
        self.notify("Nastavení uloženo.\nPlatí při příštím spuštění hry.")

    def button(self, name, x, y, cmd):
        im = self.img(self.t["buttons"][name]["image"])
        tag = "b_" + name
        if im:
            self.c.create_image(x, y, anchor="nw", image=im, tags=(tag,))
        else:
            self.c.create_rectangle(x, y, x + 150, y + 46, fill=self.t["accent"], outline="", tags=(tag,))
            self.c.create_text(x + 75, y + 23, text=self.t["buttons"][name]["text"], fill="#fff", font=self.font(12, True), tags=(tag,))
        self.hot(tag, cmd)

    def hot(self, tag, cmd, lift=False, bg=False, col=None):
        c = self.c
        c.tag_bind(tag, "<Button-1>", lambda e: cmd())
        def enter(e):
            c.configure(cursor="hand2")
            if lift:
                c.move(tag, 0, -2)
            if bg:
                c.itemconfigure(tag + "_bg", fill=col)
        def leave(e):
            c.configure(cursor="")
            if lift:
                c.move(tag, 0, 2)
            if bg:
                c.itemconfigure(tag + "_bg", fill=self.t["title_btn"])
        c.tag_bind(tag, "<Enter>", enter)
        c.tag_bind(tag, "<Leave>", leave)

    def link(self, key):
        """Odkaz z launcher.json má přednost; web je jen záloha."""
        local = (CFG.get("links") or {}).get(key, "")
        if local:
            return local
        paths = {"register": "register", "forgot": "forgot", "ranking": "ranking", "web": "home"}
        if key in paths:
            return SITE + "/index.php?p=" + paths[key]
        return (self.api.get("links") or {}).get(key, "") if isinstance(self.api, dict) else ""

    # --- hudba na pozadí ---
    def music_start(self):
        st = load_state()
        try:
            vol = min(1.0, max(0.0, float(st.get("volume", 0.35))))
        except (TypeError, ValueError):
            vol = 0.35
        self.music = Music()
        self.music.on = st.get("music", True) is not False
        self.music.vol = vol
        self._music_url = None
        path = own_music() or self.cached_or_bundled()
        if path:
            self.music.load(path)
        self.music_label()
        self.after(700, self.music.play)
        self.after(1500, self.music_loop)

    def cached_or_bundled(self):
        try:
            if os.path.isdir(MUSIC_DIR):
                files = [os.path.join(MUSIC_DIR, f) for f in os.listdir(MUSIC_DIR) if f.endswith((".mp3", ".wav"))]
                if files:
                    return files[0]
        except OSError:
            pass
        p = res("assets/theme.mp3")
        return p if os.path.isfile(p) else None

    def music_loop(self):
        # MCI dotazy mohou na některých Windows trvat i sekundy, proto běží mimo okno
        if not getattr(self, "_mus_busy", False):
            self._mus_busy = True

            def job():
                try:
                    self.music.tick()
                except Exception:
                    pass
                finally:
                    self._mus_busy = False
            threading.Thread(target=job, daemon=True).start()
        self.after(3000, self.music_loop)

    def music_label(self):
        on = self.music.on
        self.c.itemconfigure(self.vol_id, text=("%d %%" % round(self.music.vol * 100)) if on else "ticho")
        self.c.itemconfigure(self.mus_txt, text="\u266a" if on else "\u00d7")

    def music_save(self):
        d = load_state()
        d["music"] = bool(self.music.on)
        d["volume"] = round(self.music.vol, 2)
        save_state(d)

    def music_toggle(self):
        self.music.toggle()
        self.music_label()
        self.music_save()

    def music_volume(self, d):
        self.music.set_volume(self.music.vol + d)
        if not self.music.on and d > 0:
            self.music.toggle()
        self.music_label()
        self.music_save()

    def music_from_api(self, d):
        """Web může nastavit vlastní hudbu (jen z vlastní domény) nebo ji vypnout („off“)."""
        want = d.get("music") if isinstance(d, dict) else None
        if not isinstance(want, str) or want == self._music_url or own_music():
            return
        self._music_url = want
        if want == "off":
            self.music.close()
            return
        if want == "":  # výchozí skladba: zruší dřív stažený vlastní soubor a vrátí přibalenou
            had = False
            try:
                for f in os.listdir(MUSIC_DIR):
                    os.remove(os.path.join(MUSIC_DIR, f))
                    had = True
            except OSError:
                pass
            bundled = res("assets/theme.mp3")
            if (had or not self.music.opened) and os.path.isfile(bundled):
                self.music_swap(bundled)
            return
        if not want.lower().startswith("https://"):
            return

        def job():
            try:
                path = cached_music(want)
            except Exception:
                log_exc()
                return
            if path and path != self.music.path:
                self.ui(self.music_swap, path)
        threading.Thread(target=job, daemon=True).start()

    def music_swap(self, path):
        if self.music.load(path):
            self.music.play()

    def destroy(self):
        try:
            self.music.close()
        except Exception:
            pass
        super().destroy()

    # --- okno bez systémového rámu ---
    def drag_start(self, e):
        self._drag = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y()) if e.y < 58 and e.x < self.W - 290 else None

    def drag_move(self, e):
        if getattr(self, "_sl", None):
            self.slider_move(e)
        elif self._drag:
            self.geometry("+%d+%d" % (e.x_root - self._drag[0], e.y_root - self._drag[1]))

    def minimize(self):
        self.overrideredirect(False)
        self.iconify()

    def on_map(self, _e=None):
        if self.state() == "normal" and not self.overrideredirect():
            self.after(10, lambda: (self.overrideredirect(True), self.taskbar_entry()))

    def taskbar_entry(self):
        if os.name != "nt":
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, (style & ~0x80) | 0x40000)
            self.withdraw()
            self.after(10, self.deiconify)
        except Exception:
            pass

    # --- efekty: padající okvětní lístky, tečky a třpyt ---
    # --- sezónní efekt (sníh, listí, sakura, jiskry), řídí se nastavením na webu ---
    def fx_set(self, kind, level="mid"):
        if kind == "auto":
            kind = season_fx()
        if kind not in FX_KINDS or not self.t.get("effects", True):
            kind = "off"
        if level not in FX_COUNT:
            level = "mid"
        if (kind, level) == (self.fx_kind, self.fx_level):
            return
        for p in self.particles:
            self.c.delete(p["id"])
        self.particles = []
        self.fx_kind, self.fx_level = kind, level
        self.tick = getattr(self, "tick", 0)
        if kind == "off":
            return
        for _ in range(FX_COUNT[level]):
            self.particles.append(self.new_particle(True))

    def new_particle(self, initial):
        rnd, c, kind = random, self.c, self.fx_kind
        p = {"x": rnd.uniform(0, self.W), "y": rnd.uniform(-self.H, self.H) if initial else -20.0, "ph": rnd.uniform(0, 6.28),
             "sw": rnd.uniform(0.4, 1.2), "rot": rnd.uniform(0, 6.28), "vr": rnd.uniform(-0.07, 0.07), "s": rnd.uniform(0.7, 1.3)}
        if kind == "snow":
            p["r"], p["v"] = rnd.uniform(1.8, 4.8), rnd.uniform(0.8, 2.0)
            p["id"] = c.create_oval(0, 0, 1, 1, fill=rnd.choice(("#ffffff", "#f2f9ff", "#e3f2ff")), outline="")
        elif kind == "leaves":
            p["r"], p["v"] = rnd.uniform(6, 11), rnd.uniform(1.0, 2.2)
            p["id"] = c.create_polygon(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, fill=rnd.choice(LEAF_COLORS), outline="")
        elif kind == "sakura":
            p["r"], p["v"] = rnd.uniform(4, 8), rnd.uniform(0.8, 1.7)
            p["id"] = c.create_polygon(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, fill=rnd.choice(("#ffc1d9", "#ff9fc4", "#ffd9e8")), outline="")
        else:
            p["r"], p["v"] = rnd.uniform(1.4, 3.2), -rnd.uniform(0.3, 1.0)
            if initial:
                p["y"] = rnd.uniform(0, self.H)
            else:
                p["y"] = self.H + 20.0
            p["id"] = c.create_polygon(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, fill=rnd.choice(("#fff3c4", "#ffd98a", "#cfeaff")), outline="")
        if getattr(self, "bg_top", None):
            c.tag_raise(p["id"], self.bg_top)  # nad pozadím, pod ovládacími prvky
        return p

    @staticmethod
    def rot_pts(pts, ang, sx, x, y):
        ca, sa = math.cos(ang), math.sin(ang)
        out = []
        for px, py in pts:
            px *= sx
            out += [x + px * ca - py * sa, y + px * sa + py * ca]
        return out

    def animate(self):
        t0 = time.time()
        if self.state() != "iconic" and self.particles and not getattr(self, "_hover_pause", 0) > t0:
            self.tick += 1
            c, kind = self.c, self.fx_kind
            for i, p in enumerate(self.particles):
                p["y"] += p["v"]
                p["rot"] += p["vr"]
                p["x"] += math.sin(self.tick * 0.03 * p["sw"] + p["ph"]) * (0.5 if kind == "snow" else 0.9) * p["sw"] + (0.15 if kind != "sparks" else 0)
                if (p["y"] < -24) if kind == "sparks" else (p["y"] > self.H + 24):
                    self.particles[i] = np = self.new_particle(False)
                    c.delete(p["id"])
                    p = np
                if p["x"] > self.W + 30:
                    p["x"] = -20.0
                elif p["x"] < -30:
                    p["x"] = self.W + 20.0
                x, y, r, s = p["x"], p["y"], p["r"], p["s"]
                if kind == "snow":
                    c.coords(p["id"], x - r, y - r, x + r, y + r)
                elif kind == "leaves":
                    fl = math.cos(self.tick * 0.06 * p["sw"] + p["ph"])
                    pts = ((0, -r), (0.8 * r, -0.45 * r), (0.8 * r, 0.45 * r), (0, r), (-0.8 * r, 0.45 * r), (-0.8 * r, -0.45 * r))
                    c.coords(p["id"], *self.rot_pts(pts, p["rot"], 0.25 + 0.75 * abs(fl), x, y))
                elif kind == "sakura":
                    fl = math.cos(self.tick * 0.05 * p["sw"] + p["ph"])
                    pts = ((0, r), (0.8 * r, 0.1 * r), (0.5 * r, -0.8 * r), (0, -0.45 * r), (-0.5 * r, -0.8 * r), (-0.8 * r, 0.1 * r))
                    c.coords(p["id"], *self.rot_pts(pts, p["rot"], 0.35 + 0.65 * abs(fl), x, y))
                else:
                    a = (1.5 + 5 * abs(math.sin(self.tick * 0.07 + p["ph"]))) * s * (r / 2.2)
                    b = a * 0.28
                    c.coords(p["id"], x, y - a, x + b, y - b, x + a, y, x + b, y + b, x, y + a, x - b, y + b, x - a, y, x - b, y - b)
        # když je překreslování pomalé, animace se sama přibrzdí a uvolní okno myši
        took = time.time() - t0
        d = getattr(self, "_anim_delay", 50)
        d = min(200, d + 20) if took > 0.02 else max(50, d - 5)
        self._anim_delay = d
        self.after(int(d), self.animate)

    # --- data z webu ---
    api = {}
    _sig = {}

    def load_info(self, full=True):
        """full = celá odpověď (novinky, statistiky, žebříček); jinak lehká se stavem serveru, kanály, GM a eventem."""
        try:
            d = json.loads(fetch_small(SITE + "/api/launcher.php" + ("" if full else "?fast=1")).decode("utf-8"))
        except Exception:  # noqa: BLE001
            d = None
        finally:
            self._poll_busy = False
        self.ui(self.show_info, d)

    def show_info(self, d):
        c = self.c
        if not isinstance(d, dict):
            c.itemconfigure(self.state_id, text="Web nedostupný", fill=self.t["bad"])
            if not self.news:
                c.itemconfigure(self.hero_text, text="Informace z webu se nepodařilo načíst. Zkontroluj připojení k internetu.")
            return
        full = not d.get("fast")
        self.api = d if full or not self.api else {**self.api, **d}
        sig = self._sig
        self.music_from_api(d)
        fx = d.get("fx")
        if isinstance(fx, dict):
            self.fx_set(str(fx.get("mode") or "off"), str(fx.get("level") or "mid"))
        up = bool(d.get("server_online"))
        c.itemconfigure(self.dot, fill=self.t["ok"] if up else self.t["bad"])
        c.itemconfigure(self.state_id, text="SERVER ONLINE" if up else "SERVER OFFLINE", fill=self.t["ok"] if up else self.t["bad"])
        self.draw_online(d, up)
        for key, item in self.vals.items():
            v = d.get(key)
            if v is None and not full and key != "online":
                continue  # rychlá odpověď neobsahuje celkové statistiky, ponecháme poslední hodnotu
            c.itemconfigure(item, text="–" if v is None else "{:,}".format(int(v)).replace(",", " "))
        gms = json.dumps(d.get("gms"), sort_keys=True)
        if gms != sig.get("gms"):
            sig["gms"] = gms
            self.show_gms(d.get("gms"))
        if full:
            news = [n for n in (d.get("news") or []) if isinstance(n, dict)][:self.MAX_NEWS]
            if news != self.news or not getattr(self, "_news_ok", False):
                self._news_ok = True
                self.news = news
                self.hero_i = min(self.hero_i, max(0, len(news) - 1))
                self.show_hero(self.hero_i)
                keep = {n.get("image") for n in news}
                for u in [u for u in self.news_img if u not in keep]:
                    del self.news_img[u]
                threading.Thread(target=self.load_news_images, args=(list(news),), daemon=True).start()
            self.set_top(d.get("top"), d.get("top_guilds"))
            self.stats = (d.get("players_24h"), d.get("accounts"))
        chs = json.dumps([d.get("channels"), d.get("channels_on"), up])
        if chs != sig.get("ch"):
            sig["ch"] = chs
            try:
                nch = max(1, min(8, int(d.get("channels") or CFG.get("channels") or 4)))
            except (TypeError, ValueError):
                nch = 4
            if nch != self.n_channels:
                self.n_channels = nch
            self.draw_channels()
        ev = d.get("event") or {}
        now = time.time()
        self.ev_data = {
            "title": clip(ev.get("title"), 60), "text": clip(ev.get("text"), 90),
            "ends": now + max(0, int(ev.get("ends_in") or 0)) if ev.get("title") else 0,
            "next_title": clip(ev.get("next_title"), 40), "next_at": now + max(0, int(ev.get("starts_in") or 0)) if ev.get("next_title") else 0,
        }
        self.show_event()
        self.c.tag_raise("note")  # okénko se zprávou zůstává nad vším, i když se obsah překreslí

    def set_top(self, players, guilds):
        ok = lambda v: [r for r in (v or []) if isinstance(r, dict)][:20]
        self.top_data = {"players": ok(players), "guilds": ok(guilds)}
        self.draw_top()

    def set_top_tab(self, key):
        self.top_tab, self.top_off = key, 0
        for k, (it, ul) in self.top_tabs.items():
            self.c.itemconfigure(it, fill=self.t["accent2"] if k == key else self.t["muted"])
            self.c.itemconfigure(ul, state="normal" if k == key else "hidden")
        self.draw_top()

    def top_scroll(self, step):
        n, k = len(self.top_data[self.top_tab]), len(self.top_rows)
        if n > k:
            self.top_off = min(max(0, self.top_off + step), n - k)
            self.draw_top()

    def draw_top(self, *_):
        c = self.c
        rows = self.top_data[self.top_tab]
        n, k = len(rows), len(self.top_rows)
        self.top_off = min(max(0, self.top_off), max(0, n - k))
        c.itemconfigure(self.top_empty, text="" if n else "Žebříček zatím není k dispozici.")
        for i, (rk, nm, lv) in enumerate(self.top_rows):
            idx = self.top_off + i
            if idx < n:
                r = rows[idx]
                right = "Lv %s" % r.get("level", "?")
                if self.top_tab == "guilds" and r.get("points"):
                    right += "  ·  %s b." % r.get("points")
                c.itemconfigure(rk, state="normal", text="%d." % (idx + 1))
                c.itemconfigure(nm, state="normal", text=clip(r.get("name"), 24))
                c.itemconfigure(lv, state="normal", text=right)
            else:
                for it in (rk, nm, lv):
                    c.itemconfigure(it, state="hidden")
        more = n > k
        for it in (self.top_up, self.top_dn):
            c.itemconfigure(it, state="normal" if more else "hidden")
        c.itemconfigure(self.top_cnt, text="%d–%d / %d" % (self.top_off + 1, min(n, self.top_off + k), n) if more else "")

    def draw_online(self, d, up):
        c = self.c
        n = d.get("online")
        if up:
            c.itemconfigure(self.on_val, text="–" if n is None else "%s online" % "{:,}".format(int(n)).replace(",", " "), fill="#ffffff")
            c.itemconfigure(self.on_sub, text="hráčů právě ve hře")
        else:
            c.itemconfigure(self.on_val, text="OFFLINE", fill=self.t["bad"])
            c.itemconfigure(self.on_sub, text="Server je teď vypnutý")
        day, acc = self.stats
        fmt = lambda v: "–" if v is None else "{:,}".format(int(v)).replace(",", " ")
        c.itemconfigure(self.on_extra, text="Za 24 h: %s  ·  Účtů: %s" % (fmt(day), fmt(acc)) if up else "")

    @staticmethod
    def left_text(sec):
        sec = max(0, int(sec))
        d, h, m = sec // 86400, sec % 86400 // 3600, sec % 3600 // 60
        return "%d d %d h" % (d, h) if d else ("%d h %d min" % (h, m) if h else "%d min" % max(1, m))

    def show_event(self):
        c, e = self.c, getattr(self, "ev_data", {})
        if e.get("title") and e.get("ends", 0) > time.time():
            c.itemconfigure(self.ev_title, text=e["title"])
            c.itemconfigure(self.ev_text, text=e["text"])
            c.itemconfigure(self.ev_left, text="Končí za " + self.left_text(e["ends"] - time.time()))
        elif e.get("next_title"):
            c.itemconfigure(self.ev_title, text="Žádný event právě neběží")
            c.itemconfigure(self.ev_text, text="Další: " + e["next_title"])
            c.itemconfigure(self.ev_left, text="Začíná za " + self.left_text(max(0, e.get("next_at", 0) - time.time())))
        else:
            c.itemconfigure(self.ev_title, text="Žádný event právě neběží")
            c.itemconfigure(self.ev_text, text="Sleduj novinky, další event se brzy objeví.")
            c.itemconfigure(self.ev_left, text="")

    def show_gms(self, gms):
        self.gm_all = [g for g in (gms or []) if isinstance(g, dict)][:60]
        self.draw_gms()

    def gm_scroll(self, step):
        n, k = len(self.gm_all), len(self.gm_rows)
        if n <= k:
            return
        self.gm_off = min(max(0, self.gm_off + step), n - k)
        self.draw_gms()

    def draw_gms(self):
        c = self.c
        n, k = len(self.gm_all), len(self.gm_rows)
        self.gm_off = min(max(0, self.gm_off), max(0, n - k))
        c.itemconfigure(self.gm_empty, text="" if n else "Seznam GM týmu zatím není nastaven.")
        for i, (dot, nm, st) in enumerate(self.gm_rows):
            idx = self.gm_off + i
            if idx < n:
                g = self.gm_all[idx]
                on = bool(g.get("online"))
                c.itemconfigure(dot, state="normal", fill=self.t["ok"] if on else self.t["bad"])
                c.itemconfigure(nm, state="normal", text=clip(g.get("name"), 20), fill=self.t["panel_text"] if on else self.t["muted"])
                c.itemconfigure(st, state="normal", text="online" if on else "offline", fill=self.t["ok"] if on else self.t["bad"])
            else:
                for it in (dot, nm, st):
                    c.itemconfigure(it, state="hidden")
        more = n > k
        for it in (self.gm_up, self.gm_dn):
            c.itemconfigure(it, state="normal" if more else "hidden")
        on_n = sum(1 for g in self.gm_all if g.get("online"))
        c.itemconfigure(self.gm_cnt, text="%d online" % on_n if n else "")
        c.coords(self.gm_cnt, self.CARDS[0][0] + (190 if more else 224), self.CARDS[0][1] + 18 + self.pg_dy)

    def hero_loop(self):
        self.hero_tick += 1
        if self.hero_tick >= 8 and len(self.news) > 1 and not getattr(self, "_set_open", False):
            self.show_hero((self.hero_i + 1) % len(self.news))
        self.after(1000, self.hero_loop)

    def refresh_loop(self):
        """Každé 3 s lehký dotaz (GM, kanály, stav serveru), každých 30 s celý (novinky, statistiky, žebříček)."""
        self._poll_n = getattr(self, "_poll_n", 0) + 1
        if not getattr(self, "_poll_busy", False):
            self._poll_busy = True
            threading.Thread(target=self.load_info, args=(self._poll_n % 10 == 1,), daemon=True).start()
        self.after(3000, self.refresh_loop)

    def event_tick(self):
        try:
            self.show_event()
        except Exception:
            pass
        self.after(30000, self.event_tick)

    # --- patch ---
    def progress(self, f, t, text):
        def apply():
            c = self.c
            c.itemconfigure(self.status_id, text=text + ("   ·   %d %%" % t if 0 < t < 100 else ""))
            c.coords(self.bars[0], self.BAR_X0 + 1, 599, self.BAR_X0 + 1 + (self.BAR_X1 - self.BAR_X0 - 2) * f / 100, 609)
            c.coords(self.bars[1], self.BAR_X0 + 1, 625, self.BAR_X0 + 1 + (self.BAR_X1 - self.BAR_X0 - 2) * t / 100, 635)
        self.ui(apply)

    def start_patch(self):
        if getattr(self, "_running", False):
            return
        self._running, self.busy = True, True

        def job():
            try:
                if check_and_patch(self.progress) == "restart":
                    self.ui(self.after, 900, self.restart)
            except Exception as e:
                log_exc()
                self.progress(0, 0, "Aktualizace selhala: %s" % clip(e, 90))
            finally:
                self._running, self.busy = False, False
        threading.Thread(target=job, daemon=True).start()

    def restart(self):
        env = dict(os.environ)
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"  # nový proces si vybalí vlastní soubory, nepoužije složku starého
        try:
            subprocess.Popen([sys.executable], cwd=BASE, env=env)
        except OSError as e:
            self.notify("Launcher byl aktualizován. Zavři ho a spusť znovu.\n\n%s" % clip(e, 100))
            return
        self.destroy()

    def entries_visible(self, vis):
        """Pole pro přihlášení jsou skutečné prvky okna, a ty by zůstaly nad okénky (nastavení, zprávy). Proto se schovávají."""
        try:
            state = "normal" if (vis and self.mode == "login" and not self.pg_open) else "hidden"
            self.c.itemconfigure(self.w_id, state=state)
            self.c.itemconfigure(self.w_pw, state=state)
        except Exception:
            pass

    def current_creds(self):
        if self.mode == "saved" and self.sel_slot >= 0 and self.store.get(self.sel_slot):
            lg, pw = self.store.get(self.sel_slot)
            return lg, pw, True
        return self.e_id.get().strip(), self.e_pw.get(), False

    def on_play(self):
        if self.busy:
            self.progress(0, 0, "Počkej, dokud se nedokončí aktualizace.")
            return
        if self.logging:
            return
        login, pw, saved = self.current_creds()
        if not login and not pw:  # nic nevyplněno: hra se spustí a přihlásíš se v ní
            self.start_game(None, None)
            return
        if not login or not pw:
            self.say("Vyplň jméno i heslo.", "bad")
            return
        self.logging = True
        self.say("Ověřuji přihlášení…")
        threading.Thread(target=self.login_job, args=(login, pw, saved), daemon=True).start()

    def login_job(self, login, pw, saved):
        """Web jen ověří jméno/e-mail, heslo a stav účtu. Přihlášení do hry dělá klient."""
        res_ = None
        try:
            body = urllib.parse.urlencode({"login": login, "password": pw}).encode("utf-8")
            req = urllib.request.Request(SITE + "/api/login_check.php", data=body, headers={"User-Agent": UA})
            with OPENER.open(req, timeout=15) as r:
                res_ = json.loads(r.read(MAX_JSON).decode("utf-8"))
        except urllib.error.HTTPError as ex:
            try:
                res_ = json.loads(ex.read(MAX_JSON).decode("utf-8"))
            except Exception:
                res_ = None
        except Exception:
            res_ = None
        self.ui(self.login_done, login, pw, res_)

    def login_done(self, login, pw, res_):
        self.logging = False
        if not isinstance(res_, dict):
            if "@" in login:
                self.say("Web teď nejde ověřit. Přihlas se jménem, ne e-mailem, nebo to zkus později.", "bad")
                return
            self.say("Web nedostupný, přihlášení ověří až hra.", "info")
            self.start_game(login, pw)
            return
        if not res_.get("ok"):
            self.say(clip(res_.get("message") or "Přihlášení se nepovedlo.", 120), "bad")
            return
        self.start_game(str(res_.get("login") or login), pw)

    def start_game(self, login, pw):
        """Uloží účet (je-li zapnuto zapamatování), předá přihlášení klientu a spustí hru."""
        if login:
            if self.mode == "login" and self.remember:
                slot = next((i for i, a in enumerate(self.store.slots) if a and a[0].lower() == login.lower()), -1)
                if slot < 0:
                    slot = self.store.first_empty()
                if slot < 0:
                    slot = len(self.store.slots) - 1
                err = self.store.set(slot, login, pw)
                if err:
                    self.say("Účet se nepodařilo uložit: " + err, "bad")
                else:
                    self.sel_slot = slot
            self.pstate["last_login"] = login
            save_state(self.pstate)
            try:
                err = v2accounts.write_autologin(self.autologin_path(), login, pw, self.channel)
            except OSError as e:
                err = str(e)
            if err:
                self.say("Přihlášení nejde předat hře (%s). Přihlas se ve hře." % clip(err, 60), "bad")
        self.music.pause()  # ať hudba launcheru nehraje přes hudbu ve hře
        err = run_local(CFG["game_exe"])
        if err:
            try:
                os.remove(self.autologin_path())
            except OSError:
                pass
            self.notify(err)
            return
        self.say("Spouštím hru…", "ok")
        if CFG.get("close_on_play", True):
            self.after(2500, self.destroy)

    def run(self, exe):
        err = run_local(exe)
        if err:
            self.notify(err)

    def open(self, url):
        if str(url).lower().startswith("https://") and "DOPLN" not in url:
            webbrowser.open(url)
        else:
            self.notify("Odkaz není nastavený. Doplň ho v launcher.json v části \"links\" (adresa musí začínat https://).")

    def notify(self, text):
        """Vlastní okénko uvnitř launcheru, zavře se kliknutím."""
        c = self.c
        c.delete("note")
        self.entries_visible(False)
        c.create_rectangle(300, 220, 980, 470, fill=self.t["note_bg"], outline=self.t["bar_outline"], width=3, tags=("note",))
        c.create_text(640, 340, text=text, width=620, justify="center", fill=self.t["panel_text"], font=self.font(13), tags=("note",))
        c.create_text(640, 445, text="(klikni pro zavření)", fill=self.t["muted"], font=self.font(10), tags=("note",))
        c.tag_bind("note", "<Button-1>", lambda e: (c.delete("note"), self.entries_visible(not getattr(self, "_set_open", False))))

    def about(self):
        self.notify("Violet2 Launcher %s\n\n\u00a9 Violet2. Všechna práva vyhrazena. Proprietární software: kopírování, úpravy a šíření bez písemného souhlasu provozovatele jsou zakázány. Název Violet2, logo a grafika jsou majetkem provozovatele.\n\nZabezpečení: šifrované spojení (HTTPS) jen s ověřeným serverem, digitálně podepsané patche, ochrana proti zahlcení (anti-DDoS) omezováním počtu dotazů v launcheru i na serveru. Launcher neobsahuje IP adresu serveru ani hesla." % VERSION)


if __name__ == "__main__":
    cleanup_old()
    register_fonts()
    App().mainloop()
