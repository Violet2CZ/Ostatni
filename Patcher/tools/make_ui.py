#!/usr/bin/env python3
"""Vygeneruje grafiku launcheru z ilustrace: bg_idle.png (hlavní scéna), bg_page.png (stránka novinek), ikony a hero obrázky.
Potřebuje Pillow + numpy (pip install pillow numpy).

Ilustraci vyměníš tak, že přepíšeš art_zdroj/art_clean.png (jakýkoli poměr 16:9, bez vypáleného UI) a spustíš tento skript.
Rozměry panelů níže musí sedět s launcherem (violet2_launcher.py, třída App)."""
import math, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

A = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
Z = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "art_zdroj")  # zdrojová ilustrace, do exe se nebalí
W, H = 1280, 720
GLASS = (20, 8, 42)          # barva skla
LINE = (150, 96, 226)        # okraj panelů
GOLD = (226, 188, 106)       # rohové značky
ACC = (182, 107, 255)

# rozložení (musí sedět s launcherem)
DOCK_C = (372, 500, 908, 702)     # stav stahování + aktuální novinka
DOCK_R = (924, 348, 1256, 702)    # přihlášení, kanály, HRÁT
NAV = (24, 612, 250, 702)         # menu vlevo dole
PAGE = (40, 52, 1240, 580)        # stránka novinek a žebříčku
HERO = (68, 74, 828, 434)
CARDS = [(68, 450, 308, 560), (328, 450, 568, 560), (588, 450, 828, 560)]
RANK = (852, 74, 1212, 560)
BARS = ((470, 598, 888, 610), (470, 624, 888, 636))


def font(n):
    return ImageFont.truetype(os.path.join(A, "fonts", "Tektur-Medium.ttf"), n)


def ss_draw(size, fn, scale=4):
    im = Image.new("RGBA", (size[0] * scale, size[1] * scale), (0, 0, 0, 0))
    fn(ImageDraw.Draw(im), scale)
    return im.resize(size, Image.LANCZOS)


def base_art():
    src = Image.open(os.path.join(Z, "art_ext.png")).convert("RGB")
    sw, sh = src.size
    r = W / H
    if sw / sh > r:
        nw = int(sh * r)
        src = src.crop(((sw - nw) // 2, 0, (sw - nw) // 2 + nw, sh))
    else:
        nh = int(sw / r)
        src = src.crop((0, (sh - nh) // 2, sw, (sh - nh) // 2 + nh))
    return src.resize((W, H), Image.LANCZOS)


def vignette(im, bottom=0.12):
    a = np.asarray(im).astype(np.float32)
    y = np.linspace(0, 1, H)[:, None]
    x = np.linspace(-1, 1, W)[None, :]
    f = np.ones((H, W), np.float32)
    f *= 1 - 0.55 * np.clip((90 - np.arange(H)) / 90.0, 0, 1)[:, None]            # nahoře
    f *= 1 - bottom * np.clip((np.arange(H) - 420) / 300.0, 0, 1)[:, None] ** 1.3   # dole
    f *= 1 - 0.25 * np.clip((np.abs(x) - 0.7) / 0.3, 0, 1)                        # okraje
    return Image.fromarray(np.clip(a * f[..., None], 0, 255).astype(np.uint8))


KEY = (1, 2, 3)  # průhledná barva okna (Windows): oříznuté rohy a zářezy


def chamfer(box, kk=(18, 6, 18, 6), bite=None):
    """Polygon se seříznutými rohy: kk = (vlevo nahoře, vpravo nahoře, vpravo dole, vlevo dole).
    bite = ("b" nebo "t", x od levého okraje, šířka, hloubka): lichoběžníkový zářez v dolní/horní hraně (nesouměrný, jako ukousnutý)."""
    x0, y0, x1, y1 = box
    a, b, c, d = kk
    top = [(x0 + a, y0), (x1 - b, y0)]
    right = [(x1, y0 + b), (x1, y1 - c)]
    bot = [(x1 - c, y1), (x0 + d, y1)]
    left = [(x0, y1 - d), (x0, y0 + a)]
    if bite:
        side, bx, bw, bd = bite
        bx += x0
        if side == "b":
            bot = [(x1 - c, y1), (bx + bw + bd, y1), (bx + bw, y1 - bd), (bx, y1 - bd), (bx - bd, y1), (x0 + d, y1)]
        else:
            top = [(x0 + a, y0), (bx - bd, y0), (bx, y0 + bd), (bx + bw, y0 + bd), (bx + bw + bd, y0), (x1 - b, y0)]
    return top + right + bot + left


def poly_mask(size, pts, ss=4):
    m = Image.new("L", (size[0] * ss, size[1] * ss), 0)
    ImageDraw.Draw(m).polygon([(x * ss, y * ss) for x, y in pts], fill=255)
    return m.resize(size, Image.LANCZOS)


CLASSIC = True   # původní podoba panelů: zaoblené rohy a krátké zlaté značky


def glass_classic(im, box, alpha, tint, r, corners, line, blur):
    x0, y0, x1, y1 = box
    reg = im.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(blur))
    reg = Image.blend(reg, Image.new("RGB", reg.size, tint), alpha)
    g = Image.new("L", reg.size, 0)
    gd = ImageDraw.Draw(g)
    for yy in range(min(46, reg.size[1])):
        gd.line([(0, yy), (reg.size[0], yy)], fill=int(34 * (1 - yy / 46.0)))
    reg = Image.composite(Image.new("RGB", reg.size, (120, 70, 200)), reg, g)
    m = Image.new("L", (reg.size[0] * 4, reg.size[1] * 4), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, m.size[0] - 1, m.size[1] - 1), r * 4, fill=255)
    im.paste(reg, (x0, y0), m.resize(reg.size, Image.LANCZOS))
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle((x0, y0, x1, y1), r, outline=line + (255,), width=1)
    if corners:
        for x, y, sx, sy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            d.line([(x, y), (x + 12 * sx, y)], fill=GOLD + (255,), width=2)
            d.line([(x, y), (x, y + 12 * sy)], fill=GOLD + (255,), width=2)
    return im


def glass(im, box, alpha=0.74, tint=GLASS, r=7, corners=True, line=LINE, blur=7, kk=(18, 6, 18, 6), bite=None, head=0):
    if CLASSIC:
        return glass_classic(im, box, alpha, tint, r, corners, line, blur)
    return glass_new(im, box, alpha, tint, r, corners, line, blur, kk, bite, head)


def glass_new(im, box, alpha=0.74, tint=GLASS, r=7, corners=True, line=LINE, blur=7, kk=(18, 6, 18, 6), bite=None, head=0):
    """Průhledný panel se seříznutými rohy: rozmazaný obraz pod ním, ztmavený do fialova, dvojitý okraj a zlaté rohy."""
    x0, y0, x1, y1 = box
    reg = im.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(blur))
    reg = Image.blend(reg, Image.new("RGB", reg.size, tint), alpha)
    g = Image.new("L", reg.size, 0)
    gd = ImageDraw.Draw(g)
    for yy in range(min(46, reg.size[1])):
        gd.line([(0, yy), (reg.size[0], yy)], fill=int(34 * (1 - yy / 46.0)))
    reg = Image.composite(Image.new("RGB", reg.size, (120, 70, 200)), reg, g)
    pts = chamfer((0, 0, x1 - x0, y1 - y0), kk, bite)
    im.paste(reg, (x0, y0), poly_mask(reg.size, pts))
    d = ImageDraw.Draw(im, "RGBA")
    P = [(x + x0, y + y0) for x, y in pts]
    d.line(P + [P[0]], fill=line + (255,), width=1)
    if not bite:
        inner = chamfer((x0 + 4, y0 + 4, x1 - 4, y1 - 4), tuple(max(2, k - 3) for k in kk))
        d.line(inner + [inner[0]], fill=line + (70,), width=1)
    if head:  # světlejší hlavička panelu s fialovou zarážkou
        d.polygon([(x0 + kk[0] + 1, y0 + 1), (x1 - kk[1] - 1, y0 + 1), (x1 - 1, y0 + kk[1] + 1), (x1 - 1, y0 + head), (x0 + 1, y0 + head), (x0 + 1, y0 + kk[0] + 1)], fill=(150, 100, 230, 26))
        d.rectangle((x0 + kk[0] + 6, y0 + head - 1, x0 + kk[0] + 64, y0 + head), fill=ACC + (255,))
    if corners:
        a, b, c, dd = kk
        dm = lambda x, y, r, col: d.polygon([(x, y - r), (x + r, y), (x, y + r), (x - r, y)], fill=col)
        # zlaté dvojité držáky na velkých rozích a kosočtverce na koncích
        for pts_ in ([(x0, y0 + a + 22), (x0, y0 + a), (x0 + a, y0), (x0 + a + 22, y0)],
                     [(x1 - c - 22, y1), (x1 - c, y1), (x1, y1 - c), (x1, y1 - c - 22)]):
            d.line(pts_, fill=GOLD + (255,), width=3)
            d.line([(px + (2 if i % 2 else 3), py + (3 if i % 2 else 2)) for i, (px, py) in enumerate(pts_)] if False else [], fill=GOLD + (0,))
        dm(x0 + a + 28, y0 + 1, 3, GOLD + (255,)); dm(x0 + 1, y0 + a + 28, 3, GOLD + (255,))
        dm(x1 - c - 28, y1 - 1, 3, GOLD + (255,)); dm(x1 - 1, y1 - c - 28, 3, GOLD + (255,))
        d.line([(x1 - b - 18, y0), (x1 - b, y0), (x1, y0 + b), (x1, y0 + b + 14)], fill=GOLD + (190,), width=2)
        d.line([(x0, y1 - dd - 14), (x0, y1 - dd), (x0 + dd, y1), (x0 + dd + 18, y1)], fill=GOLD + (190,), width=2)
    return im


def window_shape(im):
    if CLASSIC:  # obdélníkové okno s obrysem a zlatými rohy jako ostatní panely
        w, h = im.size
        d = ImageDraw.Draw(im, "RGBA")
        d.rectangle((0, 0, w - 1, h - 1), outline=LINE + (255,), width=2)
        d.rectangle((6, 6, w - 7, h - 7), outline=LINE + (80,), width=1)
        for x, y, sx, sy in ((0, 0, 1, 1), (w - 1, 0, -1, 1), (0, h - 1, 1, -1), (w - 1, h - 1, -1, -1)):
            d.line([(x, y), (x + 46 * sx, y)], fill=GOLD + (255,), width=4)
            d.line([(x, y), (x, y + 46 * sy)], fill=GOLD + (255,), width=4)
            d.line([(x + 8 * sx, y + 8 * sy), (x + 26 * sx, y + 8 * sy)], fill=GOLD + (200,), width=2)
            d.line([(x + 8 * sx, y + 8 * sy), (x + 8 * sx, y + 26 * sy)], fill=GOLD + (200,), width=2)
        return im
    """Okno není obdélník: krkatý obrys s přesnými 45° seříznutími, schody a zářezy. Vně je průhledná barva KEY."""
    w, h = im.size
    pts = [(60, 0), (360, 0), (372, 12), (610, 12), (622, 0), (905, 0), (917, 12), (1090, 12), (1102, 0), (w - 30, 0), (w, 30),
           (w, 250), (w - 12, 262), (w - 12, 420), (w, 432), (w, h - 64), (w - 40, h - 24), (w - 40, h - 8), (w - 48, h),
           (900, h), (888, h - 12), (700, h - 12), (688, h), (300, h), (288, h - 12), (120, h - 12), (108, h), (28, h), (0, h - 28),
           (0, 500), (10, 490), (10, 300), (0, 290), (0, 60)]
    m = Image.new("L", im.size, 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    mm = m.point(lambda v: 255 if v > 127 else 0)
    inner = mm.filter(ImageFilter.MinFilter(7))                     # okraj o tloušťce 3 px
    ring = ImageChops.subtract(mm, inner)
    glow = ImageChops.subtract(mm, mm.filter(ImageFilter.MinFilter(3))).filter(ImageFilter.GaussianBlur(7)).point(lambda v: min(255, v * 3))
    base = np.asarray(im.convert("RGB")).astype(np.float32)
    g = np.asarray(glow).astype(np.float32)[..., None] / 255.0 * 0.55
    base = base * (1 - g) + np.array(LINE, np.float32) * g
    out = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    out.paste(Image.new("RGB", im.size, (170, 120, 240)), (0, 0), ring)
    d = ImageDraw.Draw(out)
    d.line([(0, 60), (60, 0)], fill=GOLD, width=3)
    d.line([(w, h - 64), (w - 40, h - 24)], fill=GOLD, width=3)
    d.line([(917, 12), (1090, 12)], fill=GOLD, width=2)
    d.line([(372, 12), (610, 12)], fill=GOLD, width=2)
    a = np.asarray(out).copy()
    a[(a == KEY).all(axis=2)] = (2, 2, 3)
    k = Image.new("RGB", im.size, KEY)
    return Image.composite(Image.fromarray(a), k, mm)


def rule(im, x0, x1, y):
    ImageDraw.Draw(im, "RGBA").line([(x0, y), (x1, y)], fill=LINE + (110,), width=1)


def track(im, b):
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle(b, 6, fill=(10, 4, 22, 255), outline=(120, 80, 190, 255), width=1)


def ui_bg():
    art = vignette(base_art())  # spodek už není tmavý (mlha v art_ext.png)
    # --- hlavní scéna
    im = art.copy()
    glass(im, DOCK_C, 0.78, kk=(28, 5, 12, 20), bite=("b", 150, 150, 9))
    glass(im, DOCK_R, 0.80, kk=(10, 24, 30, 6), bite=("t", 150, 90, 8), head=30)
    glass(im, NAV, 0.72, kk=(6, 16, 10, 22))
    for b in (DOCK_C,):
        rule(im, b[0] + 20, b[2] - 20, 538)
        rule(im, b[0] + 20, b[2] - 20, 588)
        rule(im, b[0] + 20, b[2] - 20, 652)
    rule(im, DOCK_R[0] + 20, DOCK_R[2] - 20, 378)
    for b in BARS:
        track(im, b)
    window_shape(im).save(os.path.join(A, "bg_idle.png"), optimize=True)
    # --- stránka (novinky, GM, event, server, žebříček): ilustrace potemnělá a rozostřená
    pg = ImageChops.multiply(vignette(base_art(), 0.10), Image.new("RGB", art.size, (205, 190, 225)))  # stejná ilustrace jako hlavní okno, jen lehce ztlumená
    glass(pg, PAGE, 0.80, r=9, blur=2, kk=(34, 8, 26, 14), bite=("b", 520, 160, 10))
    d = ImageDraw.Draw(pg, "RGBA")
    d.rectangle(HERO, fill=(8, 3, 18, 255), outline=LINE + (255,))
    fr = chamfer((HERO[0] - 6, HERO[1] - 6, HERO[2] + 6, HERO[3] + 6), (16, 4, 16, 4))
    d.line(fr + [fr[0]], fill=GOLD + (170,), width=1)
    for x, y, sx, sy in ((HERO[0], HERO[1], 1, 1), (HERO[2], HERO[1], -1, 1), (HERO[0], HERO[3], 1, -1), (HERO[2], HERO[3], -1, -1)):
        d.line([(x, y), (x + 12 * sx, y)], fill=GOLD + (255,), width=2)
        d.line([(x, y), (x, y + 12 * sy)], fill=GOLD + (255,), width=2)
    for b in CARDS:
        glass(pg, b, 0.55, tint=(34, 14, 66), r=5, blur=1, kk=(12, 4, 14, 6), head=28)
    glass(pg, RANK, 0.55, tint=(34, 14, 66), r=5, blur=1, kk=(6, 22, 8, 18), head=36)
    rule(pg, RANK[0] + 14, RANK[2] - 14, RANK[1] + 36)
    window_shape(pg).save(os.path.join(A, "bg_page.png"), optimize=True)
    # --- pozadí nastavení: jen rozmazaná tmavá ilustrace, bez panelů
    st = ImageChops.multiply(art.copy(), Image.new("RGB", art.size, (120, 100, 150)))
    window_shape(st).save(os.path.join(A, "bg_set.png"), optimize=True)


def icons():
    def mk(kind, col, name):
        def draw(d, s):
            L = lambda *xy: [v * s for v in xy]
            w = 2 * s
            if kind == "discord":
                d.rounded_rectangle(L(5, 8, 27, 22), 5 * s, outline=col, width=w)
                d.polygon(L(11, 22, 11, 27, 16, 22), fill=col)
                d.ellipse(L(11, 13, 14, 17), fill=col)
                d.ellipse(L(18, 13, 21, 17), fill=col)
            elif kind == "facebook":
                d.ellipse(L(5, 5, 27, 27), outline=col, width=w)
                d.line(L(18, 27, 18, 15), fill=col, width=w)
                d.arc(L(16, 7, 24, 15), 200, 360, fill=col, width=w)
                d.line(L(14, 15, 22, 15), fill=col, width=w)
            elif kind == "web":
                d.ellipse(L(5, 5, 27, 27), outline=col, width=w)
                d.ellipse(L(11, 5, 21, 27), outline=col, width=w)
                d.line(L(5, 16, 27, 16), fill=col, width=w)
            elif kind == "help":
                d.ellipse(L(5, 5, 27, 27), outline=col, width=w)
                d.arc(L(12, 10, 20, 17), 180, 400, fill=col, width=w)
                d.line(L(16, 17, 16, 19), fill=col, width=w)
                d.ellipse(L(15, 22, 17, 24), fill=col)
        ss_draw((32, 32), draw).save(os.path.join(A, "ic_%s%s.png" % (kind, name)))

    for kind in ("discord", "facebook", "web", "help"):
        mk(kind, (205, 176, 250, 255), "")
        mk(kind, (255, 255, 255, 255), "_on")


def art():
    """Záložní obrázky pro novinky bez fotky (výřezy z ilustrace)."""
    src = Image.open(os.path.join(Z, "art_clean.png")).convert("RGB")
    sw, sh = src.size
    k = sw / 1280.0
    crops = [(330, 150, 950, 560), (20, 100, 520, 560), (760, 60, 1260, 520)]
    for i, (x0, y0, x1, y1) in enumerate(crops, 1):
        w, h = HERO[2] - HERO[0] - 2, HERO[3] - HERO[1] - 2
        c = src.crop((int(x0 * k), int(y0 * k), int(x1 * k), int(y1 * k)))
        r = w / h
        cw, ch = c.size
        if cw / ch > r:
            nw = int(ch * r)
            c = c.crop(((cw - nw) // 2, 0, (cw - nw) // 2 + nw, ch))
        else:
            nh = int(cw / r)
            c = c.crop((0, 0, cw, nh))
        c = c.resize((w, h), Image.LANCZOS)
        shade = Image.new("L", c.size, 0)
        sd = ImageDraw.Draw(shade)
        for y in range(h):
            sd.line([(0, y), (w, y)], fill=int(235 * max(0, (y - h * 0.30) / (h * 0.70)) ** 1.1))
        c = Image.composite(Image.new("RGB", c.size, (8, 3, 18)), c, shade)
        c.save(os.path.join(A, "hero%d.png" % i))


def small_logo():
    im = Image.open(os.path.join(A, "icon_512.png")).convert("RGBA").resize((40, 40), Image.LANCZOS)
    im.save(os.path.join(A, "logo_small.png"))


if __name__ == "__main__":
    ui_bg(); icons(); art(); small_logo()
    print("hotovo")
