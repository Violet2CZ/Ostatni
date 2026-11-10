#!/usr/bin/env python3
"""Nástroj pro přípravu podepsaného patche (spouštěj na SVÉM počítači, ne na serveru).

  python tools/patch_tool.py keygen                 vytvoří dvojici klíčů, veřejný vloží do launcher.json
  python tools/patch_tool.py build PATCH_ZDROJ VYSTUP   vytvoří VYSTUP/manifest.json, manifest.sig a VYSTUP/files/...

Obsah složky VYSTUP nahraj na server do /usr/local/www/web/patcher/.
Privátní klíč (keys/private.key) NIKDY nenahrávej na server ani nikomu neposílej."""
import fnmatch, hashlib, json, os, re, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import v2sig  # noqa: E402

KEY = os.path.join(ROOT, "keys", "private.key")
REL = re.compile(r"^[A-Za-z0-9._\- ]+(?:/[A-Za-z0-9._\- ]+)*$")


def keygen():
    if os.path.exists(KEY):
        sys.exit("Klíč už existuje (%s). Smazáním přijdeš o možnost podepisovat existující launcher." % KEY)
    os.makedirs(os.path.dirname(KEY), exist_ok=True)
    seed = os.urandom(32)
    with open(KEY, "w") as f:
        f.write(seed.hex())
    try:
        os.chmod(KEY, 0o600)
    except OSError:
        pass
    pub = v2sig.public_key(seed).hex()
    cfgp = os.path.join(ROOT, "launcher.json")
    cfg = json.load(open(cfgp, encoding="utf-8"))
    cfg["public_key"] = pub
    json.dump(cfg, open(cfgp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("Hotovo. Veřejný klíč byl zapsán do launcher.json:\n  " + pub)
    print("Privátní klíč: " + KEY + "  (ZAZÁLOHUJ ho a nikam ho nenahrávej!)")
    print("Teď znovu vytvoř exe (build_windows.bat), aby klíč byl uvnitř.")


def build(src, out):
    if not os.path.isfile(KEY):
        sys.exit("Chybí klíč. Nejdřív spusť: python tools/patch_tool.py keygen")
    seed = bytes.fromhex(open(KEY).read().strip())
    src, out = os.path.abspath(src), os.path.abspath(out)
    if os.path.exists(out):
        shutil.rmtree(out)
    files, remove, keep, launcher = [], [], [], None
    kp = os.path.join(src, "_neprepisovat.txt")
    if os.path.isfile(kp):
        keep = [l.strip().replace("\\", "/").lower() for l in open(kp, encoding="utf-8") if l.strip() and not l.startswith("#")]

    def is_kept(rel):
        r = rel.lower()
        return any(r.startswith(k) if k.endswith("/") else fnmatch.fnmatch(r, k) for k in keep)

    for root, _, names in os.walk(src):
        for n in names:
            full = os.path.join(root, n)
            rel = os.path.relpath(full, src).replace("\\", "/")
            if rel == "_neprepisovat.txt":
                continue
            lr = rel.lower()
            if lr.startswith("log/") or lr.endswith(".log") or lr.rsplit("/", 1)[-1].startswith("syserr") or lr.endswith(".part"):
                print("Preskakuji (log/docasny soubor):", rel)
                continue
            if rel.lower() == "violet2launcher.exe":
                launcher = full  # nová verze launcheru: nejde mezi běžné soubory, hráčům se vymění sama
                continue
            if rel == "_zachovat.txt":
                keep = [l.strip() for l in open(full, encoding="utf-8") if l.strip() and not l.startswith("#")]
                continue
            if rel.lower() == "violet2launcher.exe":
                launcher_src = full  # nový launcher: nejde mezi běžné soubory, aktualizuje se zvlášť a sám
                continue
            if rel == "_odstranit.txt":
                remove = [l.strip() for l in open(full, encoding="utf-8") if l.strip() and not l.startswith("#")]
                continue
            if not REL.match(rel) or ".." in rel.split("/") or rel.lower().endswith((".php", ".phtml", ".phar")):
                sys.exit("Nepovolený název souboru: " + rel)
            h = hashlib.sha256()
            with open(full, "rb") as f:
                for c in iter(lambda: f.read(1 << 20), b""):
                    h.update(c)
            dest = os.path.join(out, "files", rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(full, dest)
            item = {"path": rel, "size": os.path.getsize(full), "sha256": h.hexdigest()}
            if is_kept(rel):
                item["keep"] = True
            files.append(item)
    for r in remove:
        if not REL.match(r) or ".." in r.split("/"):
            sys.exit("Nepovolená cesta v _odstranit.txt: " + r)
    files.sort(key=lambda x: x["path"])
    man = {"version": int(time.time()), "files": files, "remove": remove}
    if keep:
        man["keep"] = keep
    if launcher:
        h = hashlib.sha256()
        with open(launcher, "rb") as f:
            for c in iter(lambda: f.read(1 << 20), b""):
                h.update(c)
        dest = os.path.join(out, "launcher", "Violet2Launcher.exe")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(launcher, dest)
        man["launcher"] = {"size": os.path.getsize(launcher), "sha256": h.hexdigest()}
        print("Nový launcher je součástí patche (hráčům se vymění sám).")
    nk = sum(1 for f in files if f.get("keep"))
    if nk:
        print("Nepřepisovat: %d souborů (stáhnou se jen, když ve hře chybí)." % nk)
    data = json.dumps(man, indent=1).encode("utf-8")
    open(os.path.join(out, "manifest.json"), "wb").write(data)
    open(os.path.join(out, "manifest.sig"), "w").write(v2sig.sign(seed, data).hex())
    print("Hotovo: %d souborů, %d k odstranění. Nahraj obsah složky %s na server." % (len(files), len(remove), out))


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "keygen":
        keygen()
    elif len(sys.argv) == 4 and sys.argv[1] == "build":
        build(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
