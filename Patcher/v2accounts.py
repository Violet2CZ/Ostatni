# -*- coding: ascii -*-
"""Violet2: ulozene ucty na prihlasovaci obrazovce (6 slotu). Pro Python 2.7 klienta (funguje i v py3).

Jak se heslo chrani:
  * D1 = Windows DPAPI (CryptProtectData pres ctypes). Sifrovani je navazane na prihlaseni uzivatele
    ve Windows, soubor zkopirovany na jiny pocitac nebo jinemu uzivateli nejde precist. DOPORUCENO.
  * X1 = zaloha, kdyz ctypes v klientu chybi: zamichani klicem z nazvu pocitace a uzivatele + nahodna sul
    a kontrolni soucet. Je to jen obfuskace, ne skutecne silne sifrovani (kdo ma soubor i znalosti, rozlusti ho).
Heslo se nikdy nelogguje ani neposila nikam jinam nez do prihlaseni do hry.
"""
import os
import binascii

SLOTS = 6
MAX_LOGIN = 30
MAX_PASS = 40
DEFAULT_PATH = "config/v2_accounts.dat"


def _b(s):
    if isinstance(s, bytes):
        return s
    return s.encode("utf-8")


def _s(b):
    if isinstance(b, bytes):
        try:
            return b.decode("utf-8")
        except Exception:
            return b.decode("latin-1")
    return b


def _hex(b):
    return binascii.hexlify(b).decode("ascii")


def _unhex(h):
    return binascii.unhexlify(h.encode("ascii"))


# ---------------------------------------------------------------- DPAPI (Windows)
def _dpapi(data, protect):
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def mk(b):
        buf = ctypes.create_string_buffer(b, len(b))
        return BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    inb, keep1 = mk(data)
    ent, keep2 = mk(b"Violet2-accounts-v1")
    out = BLOB()
    if protect:
        ok = ctypes.windll.crypt32.CryptProtectData(ctypes.byref(inb), u"Violet2", ctypes.byref(ent), None, None, 0, ctypes.byref(out))
    else:
        ok = ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(inb), None, ctypes.byref(ent), None, None, 0, ctypes.byref(out))
    if not ok:
        raise ValueError("dpapi")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def dpapi_available():
    if os.name != "nt":
        return False
    try:
        import ctypes  # noqa: F401
        from ctypes import wintypes  # noqa: F401
        return _dpapi(b"t", True) is not None
    except Exception:
        return False


# ---------------------------------------------------------------- zaloha X1
def _machine_key(salt):
    # _b() nechava bajty (py2) beze zmeny, takze nazev PC s diakritikou nezpusobi chybu
    seed = _b(os.environ.get("COMPUTERNAME", "")) + b"|" + _b(os.environ.get("USERNAME", os.environ.get("USER", ""))) + b"|Violet2"
    return seed + salt


def _stream(key, n):
    try:
        import hashlib
        out = b""
        i = 0
        while len(out) < n:
            out += hashlib.sha256(key + str(i).encode("ascii")).digest()
            i += 1
        return out[:n]
    except ImportError:  # velmi holy klient bez hashlib: jednoduchy generator
        x = 0
        for ch in bytearray(key):
            x = (x * 131 + ch) & 0xFFFFFFFF
        res = bytearray()
        for _ in range(n):
            x = (x * 1103515245 + 12345) & 0x7FFFFFFF
            res.append((x >> 16) & 0xFF)
        return bytes(res)


def _mac(key, data):
    try:
        import hashlib
        return hashlib.sha256(key + b"mac" + data).digest()[:8]
    except ImportError:
        return bytes(bytearray([sum(bytearray(data)) & 0xFF] * 8))


def _x1_protect(data):
    salt = _b(_hex(os.urandom(8)))
    key = _machine_key(salt)
    ks = _stream(key, len(data))
    body = bytes(bytearray(a ^ b for a, b in zip(bytearray(data), bytearray(ks))))
    return salt + b":" + _b(_hex(_mac(key, body))) + b":" + _b(_hex(body))


def _x1_unprotect(blob):
    salt, mac, body = blob.split(b":")
    key = _machine_key(salt)
    body = _unhex(_s(body))
    if _unhex(_s(mac)) != _mac(key, body):
        raise ValueError("x1 mac")
    ks = _stream(key, len(body))
    return bytes(bytearray(a ^ b for a, b in zip(bytearray(body), bytearray(ks))))


def protect(data):
    """Vrati text 'D1:hex' nebo 'X1:blob'."""
    if os.name == "nt":
        try:
            return "D1:" + _hex(_dpapi(data, True))
        except Exception:
            pass
    return "X1:" + _s(_x1_protect(data))


def unprotect(text):
    kind, _, rest = text.partition(":")
    if kind == "D1":
        return _dpapi(_unhex(rest), False)
    if kind == "X1":
        return _x1_unprotect(_b(rest))
    raise ValueError("format")


# ---------------------------------------------------------------- uloziste
def valid_text(s, maxlen):
    return 0 < len(s) <= maxlen and not any(c in s for c in "\r\n\t\x00")


class AccountStore(object):
    """6 slotu: kazdy bud prazdny, nebo (login, heslo). Soubor je v textove podobe, hesla zasifrovana."""

    def __init__(self, path=None):
        self.path = path or DEFAULT_PATH
        self.slots = [None] * SLOTS
        self.broken = set()  # sloty, ktere nejdou precist (jiny pocitac / uzivatel / poskozeny soubor)

    def load(self):
        self.slots = [None] * SLOTS
        self.broken = set()
        try:
            with open(self.path, "rb") as f:
                lines = _s(f.read()).splitlines()
        except (IOError, OSError):
            return self
        for line in lines:
            parts = line.strip().split("\t", 1)
            if len(parts) != 2 or not parts[0].isdigit():
                continue
            i = int(parts[0])
            if not 0 <= i < SLOTS:
                continue
            try:
                raw = _s(unprotect(parts[1]))
                login, _, pw = raw.partition("\n")
                if valid_text(login, MAX_LOGIN):
                    self.slots[i] = (login, pw)
                else:
                    self.broken.add(i)
            except Exception:
                self.broken.add(i)
        return self

    def save(self):
        lines = []
        for i, acc in enumerate(self.slots):
            if acc:
                lines.append("%d\t%s" % (i, protect(_b(acc[0] + "\n" + acc[1]))))
        d = os.path.dirname(self.path)
        if d and not os.path.isdir(d):
            try:
                os.makedirs(d)
            except OSError:
                pass
        tmp = self.path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(_b("\n".join(lines) + ("\n" if lines else "")))
        try:
            if os.path.exists(self.path):
                os.remove(self.path)
            os.rename(tmp, self.path)
        except OSError:
            # nejhorsi pripad: zapis primo
            with open(self.path, "wb") as f:
                f.write(_b("\n".join(lines) + ("\n" if lines else "")))

    def get(self, i):
        return self.slots[i] if 0 <= i < SLOTS else None

    def set(self, i, login, password):
        """Vrati None pri uspechu, jinak text chyby (bez diakritiky, pro zobrazeni ve hre)."""
        if not 0 <= i < SLOTS:
            return "Neplatny slot"
        if not valid_text(login, MAX_LOGIN):
            return "Login je prazdny nebo moc dlouhy"
        if not valid_text(password, MAX_PASS):
            return "Heslo je prazdne nebo moc dlouhe"
        self.slots[i] = (login, password)
        self.broken.discard(i)
        try:
            self.save()
        except (IOError, OSError):
            return "Soubor s ucty se nepodarilo ulozit"
        return None

    def clear(self, i):
        if 0 <= i < SLOTS:
            self.slots[i] = None
            self.broken.discard(i)
            try:
                self.save()
            except (IOError, OSError):
                return "Soubor s ucty se nepodarilo ulozit"
        return None

    def first_empty(self):
        for i, a in enumerate(self.slots):
            if a is None:
                return i
        return -1

    def label(self, i):
        a = self.get(i)
        if a:
            return a[0]
        return ""


# ---------------------------------------------------------------- predani z launcheru (prihlaseni jednim kliknutim)
AUTOLOGIN_PATH = "config/v2_autologin.dat"
AUTOLOGIN_MAX_AGE = 120  # sekund; starsi soubor se zahodi


def write_autologin(path, login, password, channel):
    """Launcher zapise login, heslo (sifrovane stejne jako ulozene ucty) a kanal. Klient soubor hned smaze."""
    import time
    if not valid_text(login, MAX_LOGIN) or not valid_text(password, MAX_PASS):
        return "Neplatny login nebo heslo"
    body = "V2AL1\n%d\n%d\n%s\n" % (int(time.time()), int(channel), protect(_b(login + "\n" + password)))
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "wb") as f:
        f.write(_b(body))
    return None


def pop_autologin(path=None):
    """Prectene a smazane predani z launcheru. Vrati (login, heslo, kanal) nebo None. Soubor se smaze vzdy."""
    import time
    path = path or AUTOLOGIN_PATH
    try:
        with open(path, "rb") as f:
            lines = _s(f.read()).splitlines()
    except (IOError, OSError):
        return None
    try:
        os.remove(path)
    except OSError:
        pass
    try:
        if len(lines) < 4 or lines[0] != "V2AL1":
            return None
        if abs(time.time() - int(lines[1])) > AUTOLOGIN_MAX_AGE:
            return None
        channel = int(lines[2])
        login, _, pw = _s(unprotect(lines[3])).partition("\n")
        if not valid_text(login, MAX_LOGIN) or not valid_text(pw, MAX_PASS) or not 0 <= channel < 16:
            return None
        return (login, pw, channel)
    except Exception:
        return None
