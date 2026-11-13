"""Violet2 DEV launcher: malé okno jen pro přihlášení do hry.

Nestahuje žádné soubory, nekontroluje patch ani web, nic neaktualizuje. Umí jen:
  - uložit si účty (stejný soubor a šifrování jako velký launcher: config\\v2_accounts.dat),
  - vybrat kanál (CH1 až CH4, u každého ukáže, jestli server na jeho portu odpovídá),
  - předat přihlášení klientu (config\\v2_autologin.dat) a spustit hru.

Nastavení je v devlauncher.json vedle exe (dá se kdykoli přepsat, nic není zabalené natvrdo).
"""
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk

import v2accounts

VERSION = "1.0.0"
BASE = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Violet2DevLauncher")
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError:
    DATA_DIR = BASE
STATE_FILE = os.path.join(DATA_DIR, "state.json")
ERROR_LOG = os.path.join(DATA_DIR, "devlauncher_error.log")
CFG_FILE = os.path.join(BASE, "devlauncher.json")

DEFAULTS = {
    "game_dir": "",                    # prázdné = složka, ve které leží tento exe
    "game_exe": "metin2client.bin",
    "channels": 4,
    "host": "89.203.249.234",          # adresa serveru pro ukazatel stavu kanálů (prázdné = stav se nezjišťuje)
    "channel_ports": [11011, 11021, 11031, 11041],
    "close_on_play": True,
}

C = {"bg": "#05122a", "panel": "#081a32", "border": "#2f7fa6", "text": "#e1f1ff", "muted": "#8fc4e0",
     "accent": "#2ee6c0", "accent2": "#7fe3ff", "field": "#0b2240", "ok": "#3ddc84", "bad": "#ff5a6e",
     "play_text": "#04202a", "sel": "#0e3a5c"}
W, H = 420, 556


# ---------- nastavení a stav ----------
def clip(s, n):
    s = str(s)
    return s if len(s) <= n else s[:n - 1] + "…"


def load_cfg():
    """Vrací (nastavení, chyba). Chybný nebo chybějící soubor nikdy nezastaví start, platí výchozí hodnoty."""
    cfg, err = dict(DEFAULTS), ""
    try:
        with open(CFG_FILE, encoding="utf-8-sig") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
        else:
            err = "devlauncher.json má špatný tvar"
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as e:
        err = "devlauncher.json nejde přečíst: " + clip(e, 50)
    try:
        cfg["channels"] = max(1, min(8, int(cfg["channels"])))
    except (TypeError, ValueError):
        cfg["channels"] = 4
    ports = []
    for p in cfg.get("channel_ports") or []:
        try:
            ports.append(int(p))
        except (TypeError, ValueError):
            ports.append(0)
    cfg["channel_ports"] = ports
    return cfg, err


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(d):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except OSError:
        pass


def log_error(text):
    try:
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text))
    except OSError:
        pass


# ---------- logika (bez okna, dá se zkoušet samostatně) ----------
class Core:
    def __init__(self, cfg):
        self.cfg = cfg
        self.store = v2accounts.AccountStore(self.accounts_path()).load()

    def game_root(self):
        return os.path.realpath(self.cfg.get("game_dir") or BASE)

    def accounts_path(self):
        return os.path.join(self.game_root(), "config", "v2_accounts.dat")

    def autologin_path(self):
        return os.path.join(self.game_root(), "config", "v2_autologin.dat")

    def remember(self, login, pw):
        """Uloží účet do slotu se stejným loginem, jinak do prvního volného (když není, přepíše poslední). Vrací chybu nebo None."""
        slot = next((i for i, a in enumerate(self.store.slots) if a and a[0].lower() == login.lower()), -1)
        if slot < 0:
            slot = self.store.first_empty()
        if slot < 0:
            slot = len(self.store.slots) - 1
        return self.store.set(slot, login, pw)

    def run_game(self):
        root, exe = self.game_root(), self.cfg.get("game_exe") or ""
        full = os.path.realpath(os.path.join(root, exe))
        if not exe or os.path.commonpath([root, full]) != root or not os.path.isfile(full):
            return "Hra nenalezena:\n%s\n\nDej DEV launcher do složky s hrou, nebo nastav game_dir a game_exe v devlauncher.json." % full
        try:
            subprocess.Popen([full], cwd=os.path.dirname(full))
        except OSError as e:
            return "Hru se nepodařilo spustit:\n%s" % clip(e, 120)
        return None

    def start(self, login, pw, channel, handoff=True):
        """Předá přihlášení klientu (když handoff) a spustí hru. Vrací text chyby, nebo None."""
        if handoff:
            try:
                err = v2accounts.write_autologin(self.autologin_path(), login, pw, channel)
            except OSError as e:
                err = str(e)
            if err:
                return "Přihlášení nejde předat hře: " + clip(err, 80)
        else:
            try:
                os.remove(self.autologin_path())  # zbytek po minulém spuštění by hru přihlásil sám
            except OSError:
                pass
        err = self.run_game()
        if err and handoff:
            try:
                os.remove(self.autologin_path())
            except OSError:
                pass
        return err

    def probe(self):
        """Pro každý kanál True/False podle toho, jestli server odpovídá na jeho portu; None, když není co zjišťovat."""
        host, ports = str(self.cfg.get("host") or "").strip(), self.cfg["channel_ports"]
        n = self.cfg["channels"]
        res = [None] * n
        if not host:
            return res

        def one(i, port):
            try:
                with socket.create_connection((host, port), timeout=1.0):
                    res[i] = True
            except (OSError, ValueError, OverflowError):
                res[i] = False

        ts = [threading.Thread(target=one, args=(i, ports[i]), daemon=True) for i in range(min(n, len(ports))) if ports[i] > 0]
        for t in ts:
            t.start()
        for t in ts:
            t.join(2.5)
        return res


# ---------- okno ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg, cfg_err = load_cfg()
        self.core = Core(self.cfg)
        self.state = load_state()
        self.title("Violet2 DEV launcher")
        self.resizable(False, False)
        self.configure(bg=C["bg"])
        self.geometry("%dx%d+%d+%d" % (W, H, (self.winfo_screenwidth() - W) // 2, max((self.winfo_screenheight() - H) // 3, 0)))
        self.q = queue.Queue()
        self.report_callback_exception = self.on_exception
        self.c = tk.Canvas(self, width=W, height=H, highlightthickness=0, bg=C["bg"])
        self.c.pack()
        self.n = self.cfg["channels"]
        try:
            self.channel = min(max(int(self.state.get("channel", 0)), 0), self.n - 1)
        except (TypeError, ValueError):
            self.channel = 0
        self.remember = bool(self.state.get("remember", True))
        self.sel = -1
        self.up = [None] * self.n
        self.build()
        self.draw_slots()
        self.draw_channels()
        self.draw_remember()
        last = str(self.state.get("last_login") or "")
        slot = next((i for i, a in enumerate(self.core.store.slots) if a and a[0].lower() == last.lower()), -1) if last else -1
        if slot >= 0:
            self.pick(slot)
        elif last:
            self.e_login.insert(0, last)
        self.bind("<Return>", lambda e: self.on_play())
        if cfg_err:
            self.say(cfg_err, "bad")
        self.pump()
        self.poll()
        self.e_pw.focus_set() if self.e_login.get() else self.e_login.focus_set()

    # --- základ
    def font(self, size, bold=False):
        return ("Segoe UI Semibold" if bold else "Segoe UI", size)

    def ui(self, fn, *a):
        self.q.put(lambda: fn(*a))

    def pump(self):
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        self.after(100, self.pump)

    def on_exception(self, exc, val, tb):
        import traceback
        log_error("".join(traceback.format_exception(exc, val, tb)))
        self.say("Chyba: %s (podrobnosti v devlauncher_error.log)" % clip(val, 60), "bad")

    def button(self, x, y, w, h, text, cmd, tag, primary=False, size=11):
        c = self.c
        fill, out = (C["accent"], C["accent"]) if primary else (C["panel"], C["border"])
        c.create_rectangle(x, y, x + w, y + h, fill=fill, outline=out, tags=(tag, tag + "_r"))
        c.create_text(x + w // 2, y + h // 2, text=text, fill=C["play_text"] if primary else C["accent2"],
                      font=self.font(size, True), tags=(tag,))
        c.tag_bind(tag, "<Button-1>", lambda e: cmd())
        c.tag_bind(tag, "<Enter>", lambda e: (c.configure(cursor="hand2"), c.itemconfigure(tag + "_r", outline=C["accent2"])))
        c.tag_bind(tag, "<Leave>", lambda e: (c.configure(cursor=""), c.itemconfigure(tag + "_r", outline=out)))

    def entry(self, show=""):
        e = tk.Entry(self, bg=C["field"], fg=C["text"], insertbackground=C["accent2"], relief="flat", bd=0,
                     highlightthickness=1, highlightbackground=C["border"], highlightcolor=C["accent"],
                     font=self.font(11), show=show)
        return e

    def build(self):
        c = self.c
        c.create_text(24, 26, anchor="w", text="VIOLET2", fill=C["accent"], font=self.font(15, True))
        c.create_text(112, 28, anchor="w", text="DEV  ·  bez patcheru", fill=C["muted"], font=self.font(9))
        c.create_line(24, 50, W - 24, 50, fill=C["border"])
        c.create_text(24, 68, anchor="w", text="ULOŽENÉ ÚČTY", fill=C["accent2"], font=self.font(8, True))
        self.slot_items = []
        for i in range(v2accounts.SLOTS):
            y = 82 + i * 27
            r = c.create_rectangle(24, y, W - 24, y + 23, fill=C["panel"], outline=C["border"], tags=("slot%d" % i,))
            t = c.create_text(36, y + 12, anchor="w", text="", fill=C["text"], font=self.font(10), tags=("slot%d" % i,))
            x = c.create_text(W - 38, y + 12, text="×", fill=C["bad"], font=self.font(12, True), tags=("del%d" % i,), state="hidden")
            self.slot_items.append((r, t, x))
            c.tag_bind("slot%d" % i, "<Button-1>", lambda e, k=i: self.pick(k))
            c.tag_bind("slot%d" % i, "<Double-Button-1>", lambda e, k=i: (self.pick(k), self.on_play()))
            c.tag_bind("del%d" % i, "<Button-1>", lambda e, k=i: self.remove(k))
            c.tag_bind("slot%d" % i, "<Enter>", lambda e: c.configure(cursor="hand2"))
            c.tag_bind("slot%d" % i, "<Leave>", lambda e: c.configure(cursor=""))
        c.create_text(24, 262, anchor="w", text="LOGIN", fill=C["accent2"], font=self.font(8, True))
        self.e_login = self.entry()
        c.create_window(24, 274, anchor="nw", window=self.e_login, width=W - 48, height=30)
        c.create_text(24, 318, anchor="w", text="HESLO", fill=C["accent2"], font=self.font(8, True))
        self.e_pw = self.entry("•")
        c.create_window(24, 330, anchor="nw", window=self.e_pw, width=W - 48, height=30)
        self.rem_box = c.create_rectangle(24, 374, 40, 390, fill=C["field"], outline=C["border"], tags=("rem",))
        self.rem_tick = c.create_text(32, 382, text="✓", fill=C["accent"], font=self.font(10, True), tags=("rem",))
        c.create_text(48, 382, anchor="w", text="Zapamatovat účet na tomto počítači", fill=C["text"], font=self.font(10), tags=("rem",))
        c.tag_bind("rem", "<Button-1>", lambda e: self.toggle_remember())
        c.tag_bind("rem", "<Enter>", lambda e: c.configure(cursor="hand2"))
        c.tag_bind("rem", "<Leave>", lambda e: c.configure(cursor=""))
        c.create_text(24, 412, anchor="w", text="KANÁL", fill=C["accent2"], font=self.font(8, True))
        self.ch_items = []
        gap = 8
        bw = (W - 48 - gap * (self.n - 1)) // self.n
        for i in range(self.n):
            x = 24 + i * (bw + gap)
            r = c.create_rectangle(x, 424, x + bw, 456, fill=C["panel"], outline=C["border"], tags=("ch%d" % i,))
            t = c.create_text(x + bw // 2 - 6, 440, text="CH%d" % (i + 1), fill=C["text"], font=self.font(10, True), tags=("ch%d" % i,))
            d = c.create_oval(x + bw - 18, 436, x + bw - 10, 444, fill=C["muted"], outline="", tags=("ch%d" % i,))
            self.ch_items.append((r, t, d))
            c.tag_bind("ch%d" % i, "<Button-1>", lambda e, k=i: self.pick_channel(k))
            c.tag_bind("ch%d" % i, "<Enter>", lambda e: c.configure(cursor="hand2"))
            c.tag_bind("ch%d" % i, "<Leave>", lambda e: c.configure(cursor=""))
        self.button(24, 474, W - 48, 42, "HRÁT", self.on_play, "play", primary=True, size=14)
        self.button(24, 522, 190, 22, "Jen spustit hru", self.on_launch_only, "only", size=9)
        self.say_item = c.create_text(W - 24, 533, anchor="e", width=170, text="", fill=C["muted"], font=self.font(9))

    # --- vykreslení
    def say(self, text, kind="info"):
        col = {"bad": C["bad"], "ok": C["ok"]}.get(kind, C["muted"])
        self.c.itemconfigure(self.say_item, text=clip(text, 70), fill=col)

    def draw_slots(self):
        st = self.core.store
        for i, (r, t, x) in enumerate(self.slot_items):
            a = st.get(i)
            broken = i in st.broken
            self.c.itemconfigure(r, fill=C["sel"] if i == self.sel else C["panel"], outline=C["accent"] if i == self.sel else C["border"])
            if a:
                self.c.itemconfigure(t, text=a[0], fill=C["text"])
            elif broken:
                self.c.itemconfigure(t, text="(nejde přečíst: jiný počítač nebo uživatel)", fill=C["bad"])
            else:
                self.c.itemconfigure(t, text="— volné —", fill=C["muted"])
            self.c.itemconfigure(x, state="normal" if (a or broken) else "hidden")

    def draw_channels(self):
        for i, (r, t, d) in enumerate(self.ch_items):
            on = i == self.channel
            self.c.itemconfigure(r, fill=C["sel"] if on else C["panel"], outline=C["accent"] if on else C["border"])
            u = self.up[i]
            self.c.itemconfigure(d, fill=C["ok"] if u else C["bad"] if u is False else C["muted"])

    def draw_remember(self):
        self.c.itemconfigure(self.rem_tick, state="normal" if self.remember else "hidden")

    # --- akce
    def pick(self, i):
        self.sel = i
        a = self.core.store.get(i)
        self.e_login.delete(0, "end")
        self.e_pw.delete(0, "end")
        if a:
            self.e_login.insert(0, a[0])
            self.e_pw.insert(0, a[1])
        self.draw_slots()

    def remove(self, i):
        err = self.core.store.clear(i)
        if self.sel == i:
            self.sel = -1
            self.e_login.delete(0, "end")
            self.e_pw.delete(0, "end")
        self.draw_slots()
        self.say(err or "Účet smazán.", "bad" if err else "info")

    def pick_channel(self, i):
        self.channel = i
        self.state["channel"] = i
        save_state(self.state)
        self.draw_channels()

    def toggle_remember(self):
        self.remember = not self.remember
        self.state["remember"] = self.remember
        save_state(self.state)
        self.draw_remember()

    def on_play(self):
        login, pw = self.e_login.get().strip(), self.e_pw.get()
        if not login or not pw:
            self.say("Zadej login a heslo, nebo klikni na Jen spustit hru.", "bad")
            return
        if not v2accounts.valid_text(login, v2accounts.MAX_LOGIN) or not v2accounts.valid_text(pw, v2accounts.MAX_PASS):
            self.say("Login nebo heslo má neplatné znaky nebo je moc dlouhé.", "bad")
            return
        if self.remember:
            err = self.core.remember(login, pw)
            if err:
                self.say("Účet se neuložil: " + err, "bad")
            else:
                self.sel = next((i for i, a in enumerate(self.core.store.slots) if a and a[0].lower() == login.lower()), -1)
                self.draw_slots()
        self.state["last_login"] = login
        save_state(self.state)
        self.launch(login, pw, True)

    def on_launch_only(self):
        self.launch("", "", False)

    def launch(self, login, pw, handoff):
        err = self.core.start(login, pw, self.channel, handoff)
        if err:
            self.say(err.splitlines()[0], "bad")
            log_error(err.replace("\n", " "))
            return
        self.say("Spouštím hru…", "ok")
        if self.cfg.get("close_on_play", True):
            self.after(1500, self.destroy)

    # --- stav kanálů
    def poll(self):
        def work():
            res = self.core.probe()
            self.ui(self.set_up, res)
        threading.Thread(target=work, daemon=True).start()
        self.after(5000, self.poll)

    def set_up(self, res):
        if res != self.up:
            self.up = res
            self.draw_channels()


def main():
    try:
        App().mainloop()
    except Exception:  # noqa: BLE001
        import traceback
        log_error(traceback.format_exc())
        try:
            from tkinter import messagebox
            messagebox.showerror("Violet2 DEV launcher", "Launcher spadl. Podrobnosti jsou v:\n" + ERROR_LOG)
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
