"""Nastavení hry (config/metin2.cfg): čtení, zápis a model voleb pro okno Nastavení v launcheru.
Jen standardní knihovna. Řádky, které launcher nezná, zůstávají v souboru beze změny."""
import os
import sys

FALLBACK_MODES = {(800, 600): [60], (1024, 768): [60], (1280, 720): [60], (1280, 1024): [60], (1366, 768): [60],
                  (1600, 900): [60], (1920, 1080): [60], (1920, 1200): [60], (2560, 1440): [60]}
FREQS = [50, 60, 75, 100, 120, 144, 165, 240]


# ---------- soubor ----------
def read_cfg(path):
    """Vrátí {KLÍČ: hodnota (text)}. Chybějící soubor = prázdný slovník."""
    out = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                p = line.strip().split(None, 1)
                if len(p) == 2:
                    out[p[0].upper()] = p[1].strip()
    except FileNotFoundError:
        pass
    return out


def write_cfg(path, updates):
    """Přepíše jen uvedené klíče, ostatní řádky nechá. Zápis je atomický (nejdřív dočasný soubor)."""
    lines = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        pass
    done = set()
    for i, line in enumerate(lines):
        p = line.strip().split(None, 1)
        if p and p[0].upper() in updates:
            k = p[0].upper()
            lines[i] = "%s\t%s" % (k, updates[k])
            done.add(k)
    for k, v in updates.items():
        if k not in done:
            lines.append("%s\t%s" % (k, v))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, path)


# ---------- rozlišení monitoru ----------
def display_modes():
    """{(šířka, výška): [frekvence, ...]} podle grafické karty (Windows). Jinak výchozí sada."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import c_long, c_short, c_ulong, c_ushort, c_wchar

            class DEVMODEW(ctypes.Structure):
                _fields_ = [("dmDeviceName", c_wchar * 32), ("dmSpecVersion", c_ushort), ("dmDriverVersion", c_ushort),
                            ("dmSize", c_ushort), ("dmDriverExtra", c_ushort), ("dmFields", c_ulong),
                            ("dmPositionX", c_long), ("dmPositionY", c_long), ("dmDisplayOrientation", c_ulong),
                            ("dmDisplayFixedOutput", c_ulong), ("dmColor", c_short), ("dmDuplex", c_short),
                            ("dmYResolution", c_short), ("dmTTOption", c_short), ("dmCollate", c_short),
                            ("dmFormName", c_wchar * 32), ("dmLogPixels", c_ushort), ("dmBitsPerPel", c_ulong),
                            ("dmPelsWidth", c_ulong), ("dmPelsHeight", c_ulong), ("dmDisplayFlags", c_ulong),
                            ("dmDisplayFrequency", c_ulong), ("dmICMMethod", c_ulong), ("dmICMIntent", c_ulong),
                            ("dmMediaType", c_ulong), ("dmDitherType", c_ulong), ("dmReserved1", c_ulong),
                            ("dmReserved2", c_ulong), ("dmPanningWidth", c_ulong), ("dmPanningHeight", c_ulong)]

            if ctypes.sizeof(DEVMODEW) == 220:
                dm = DEVMODEW()
                dm.dmSize = 220
                modes, i = {}, 0
                while ctypes.windll.user32.EnumDisplaySettingsW(None, i, ctypes.byref(dm)) and i < 5000:
                    i += 1
                    if dm.dmBitsPerPel >= 32 and dm.dmPelsWidth >= 800 and dm.dmPelsHeight >= 600:
                        fl = modes.setdefault((int(dm.dmPelsWidth), int(dm.dmPelsHeight)), [])
                        if 30 <= dm.dmDisplayFrequency <= 360 and int(dm.dmDisplayFrequency) not in fl:
                            fl.append(int(dm.dmDisplayFrequency))
                if modes:
                    return {k: sorted(v) or [60] for k, v in modes.items()}
        except Exception:
            pass
    return {k: list(v) for k, v in FALLBACK_MODES.items()}


# ---------- model voleb ----------
CHOICES = {
    "windowed": [(1, "Okno"), (0, "Celá obrazovka")],
    "swcursor": [(0, "Systémový"), (1, "Softwarový")],
    "ime": [(0, "Herní"), (1, "Externí")],
    "fog": [(0, "Blízká"), (1, "Střední"), (2, "Daleká")],
    "shadow": [(0, "Vypnuto"), (1, "Terén"), (2, "Terén a postavy"), (3, "Vše")],
    "tiling": [(2, "Automaticky"), (0, "Grafická karta"), (1, "Procesor")],
    "gamma": [(i, str(i)) for i in range(1, 6)],
}
# klíč modelu -> klíč v metin2.cfg
CFG_KEYS = {"windowed": "WINDOWED", "swcursor": "SOFTWARE_CURSOR", "ime": "USE_DEFAULT_IME", "fog": "FOG_LEVEL",
            "shadow": "SHADOW_LEVEL", "tiling": "SOFTWARE_TILING", "gamma": "GAMMA", "freq": "FREQUENCY"}


def _num(v, cast, default):
    try:
        return cast(float(v)) if cast is int else cast(v)
    except (TypeError, ValueError):
        return default


class SettingsModel:
    def __init__(self, cfg, screen=(1920, 1080)):
        self.cfg = dict(cfg)
        self.screen = screen
        self.modes = display_modes()
        self.st = {}
        self.load(cfg)

    def defaults(self):
        w, h = self.screen if tuple(self.screen) in self.modes else sorted(self.modes)[-1]
        return {"res": (w, h), "freq": 60, "gamma": 3, "windowed": 1, "swcursor": 0, "ime": 0,
                "fog": 2, "shadow": 3, "tiling": 2, "music": 1.0, "sfx": 1.0}

    def load(self, cfg):
        d = self.defaults()
        st = {
            "res": (_num(cfg.get("WIDTH"), int, d["res"][0]), _num(cfg.get("HEIGHT"), int, d["res"][1])),
            "freq": _num(cfg.get("FREQUENCY"), int, d["freq"]),
            "music": min(1.0, max(0.0, _num(cfg.get("MUSIC_VOLUME"), float, d["music"]))),
            "sfx": min(1.0, max(0.0, _num(cfg.get("VOICE_VOLUME"), float, d["sfx"]))),
        }
        for k, ck in CFG_KEYS.items():
            if k != "freq":
                v = _num(cfg.get(ck), int, d[k])
                st[k] = v if v in [o[0] for o in CHOICES[k]] else d[k]
        self.st = st
        fl = self.modes.setdefault(st["res"], [])  # aktuální nastavení zůstane na výběr, i když ho karta nehlásí
        if st["freq"] not in fl:
            fl.append(st["freq"])
            fl.sort()
        self._fix_freq()

    def reset(self):
        self.st = self.defaults()
        self._fix_freq()

    def opts(self, key):
        if key == "res":
            return [(r, "%d x %d" % r) for r in sorted(self.modes)]
        if key == "freq":
            fl = self.modes.get(self.st["res"]) or FREQS
            return [(f, "%d Hz" % f) for f in fl]
        return CHOICES[key]

    def _fix_freq(self):
        vals = [o[0] for o in self.opts("freq")]
        if self.st["freq"] not in vals:
            self.st["freq"] = min(vals, key=lambda f: abs(f - 60))

    def label(self, key):
        for v, l in self.opts(key):
            if v == self.st[key]:
                return l
        return str(self.st[key])

    def step(self, key, d):
        vals = [o[0] for o in self.opts(key)]
        i = vals.index(self.st[key]) if self.st[key] in vals else 0
        self.st[key] = vals[(i + d) % len(vals)]
        if key == "res":
            self._fix_freq()

    def to_cfg(self):
        s = self.st
        out = {"WIDTH": s["res"][0], "HEIGHT": s["res"][1], "BPP": 32,
               "MUSIC_VOLUME": "%.3f" % s["music"], "VOICE_VOLUME": "%.3f" % s["sfx"]}
        for k, ck in CFG_KEYS.items():
            out[ck] = s[k]
        return {k: str(v) for k, v in out.items()}
