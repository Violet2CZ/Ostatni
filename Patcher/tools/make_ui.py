#!/usr/bin/env python3
"""Vygeneruje grafiku nového rozložení launcheru (fialový styl): ui_bg.png, ikony, hero obrázky a náhledy.
Potřebuje Pillow (pip install pillow). Obrázky můžeš přepsat vlastními se stejnými názvy a rozměry."""
import math, os
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

A = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
W, H = 1280, 720
BG, PANEL, BORDER, ACC, ACC2 = (5, 18, 38), (8, 26, 50), (47, 127, 166), (46, 230, 192), (127, 227, 255)

# rozložení (musí sedět s launcherem)
RAIL = (0, 58, 76, 720)
HERO = (96, 74, 856, 434)
CARDS = [(96, 450, 336, 560), (356, 450, 596, 560), (616, 450, 856, 560)]
LOGIN = (880, 74, 1240, 300)
CHAN = (880, 308, 1240, 388)
STATS = (880, 476, 1240, 538)
GMS = (880, 546, 1240, 696)
PROG = (96, 576, 856, 696)


def font(n):
    return ImageFont.truetype(os.path.join(A, "fonts", "Tektur-Medium.ttf"), n)


def ss_draw(size, fn, scale=4):
    im = Image.new("RGBA", (size[0] * scale, size[1] * scale), (0, 0, 0, 0))
    fn(ImageDraw.Draw(im), scale)
    return im.resize(size, Image.LANCZOS)


def ui_bg():
    im = Image.new("RGB", (W, H), BG)
    # jemná záře za hero a vpravo nahoře
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse((300, 40, 1000, 460), fill=(10, 50, 90))
    g.ellipse((900, -120, 1400, 260), fill=(8, 60, 80))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    im = ImageChops.add(im, glow)
    d = ImageDraw.Draw(im, "RGBA")
    d.rectangle((0, 0, W, 57), fill=(4, 14, 30, 255))
    d.line([(0, 57), (W, 57)], fill=BORDER + (255,), width=1)
    d.rectangle(RAIL, fill=(4, 14, 30, 255))
    d.line([(RAIL[2], 58), (RAIL[2], H)], fill=(20, 62, 92, 255), width=1)

    def box(b, fill=PANEL, r=3, line=BORDER):
        d.rounded_rectangle(b, r, fill=fill + (255,), outline=line + (255,), width=1)
        # rohové značky
        for x, y, sx, sy in ((b[0], b[1], 1, 1), (b[2], b[1], -1, 1), (b[0], b[3], 1, -1), (b[2], b[3], -1, -1)):
            d.line([(x, y), (x + 9 * sx, y)], fill=ACC + (255,), width=2)
            d.line([(x, y), (x, y + 9 * sy)], fill=ACC + (255,), width=2)

    box(HERO, fill=(4, 14, 30))
    for b in CARDS:
        box(b)
    for b in (LOGIN, CHAN, STATS, GMS):
        box(b)
        d.line([(b[0] + 14, b[1] + 30), (b[2] - 14, b[1] + 30)], fill=(24, 74, 108, 255), width=1)
    # lišta stahování
    d.line([(PROG[0], PROG[1] - 6), (PROG[2], PROG[1] - 6)], fill=(20, 62, 92, 255), width=1)
    for y in (610, 636):
        d.rectangle((150, y, 856, y + 12), fill=(5, 18, 34, 255), outline=BORDER + (255,))
    # kosočtverec pod hero (dekor)
    d.polygon([(476, 440), (484, 446), (476, 452), (468, 446)], fill=ACC + (255,))
    im.save(os.path.join(A, "ui_bg.png"))


def icons():
    def mk(kind, col, name):
        def draw(d, s):
            c = 16 * s
            L = lambda *xy: [v * s for v in xy]
            w = 2 * s
            if kind == "news":
                d.rounded_rectangle(L(7, 6, 25, 26), 2 * s, outline=col, width=w)
                d.line(L(11, 11, 21, 11), fill=col, width=w)
                d.line(L(11, 16, 21, 16), fill=col, width=w)
                d.line(L(11, 21, 17, 21), fill=col, width=w)
            elif kind == "rank":
                d.polygon(L(10, 7, 22, 7, 21, 15, 16, 19, 11, 15), outline=col, width=w)
                d.arc(L(4, 8, 11, 15), 90, 270, fill=col, width=w)
                d.arc(L(21, 8, 28, 15), 270, 90, fill=col, width=w)
                d.line(L(16, 19, 16, 24), fill=col, width=w)
                d.line(L(11, 25, 21, 25), fill=col, width=w)
            elif kind == "discord":
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
            elif kind == "user":
                d.ellipse(L(11, 6, 21, 16), outline=col, width=w)
                d.arc(L(6, 17, 26, 33), 180, 360, fill=col, width=w)
            elif kind == "gear":
                for a in range(0, 360, 45):
                    x, y = 16 + math.cos(math.radians(a)) * 9, 16 + math.sin(math.radians(a)) * 9
                    d.ellipse(L(x - 2, y - 2, x + 2, y + 2), fill=col)
                d.ellipse(L(8, 8, 24, 24), outline=col, width=w)
                d.ellipse(L(13, 13, 19, 19), outline=col, width=w)
        ss_draw((32, 32), draw).save(os.path.join(A, "ic_%s%s.png" % (kind, name)))

    for kind in ("news", "rank", "discord", "facebook", "web", "help", "user", "gear"):
        mk(kind, (143, 196, 224, 255), "")
        mk(kind, (255, 255, 255, 255), "_on")


def art():
    src = Image.open(os.path.join(A, "background_fullhd_master.png")).convert("RGB")
    sw, sh = src.size
    k = sw / 1280.0
    crops = [(380, 120, 1180, 600), (60, 60, 700, 420), (300, 240, 1000, 640)]
    for i, (x0, y0, x1, y1) in enumerate(crops, 1):
        w, h = HERO[2] - HERO[0] - 2, HERO[3] - HERO[1] - 2
        c = src.crop((int(x0 * k), int(y0 * k), int(x1 * k), int(y1 * k)))
        # zachovat poměr stran hero
        r = w / h
        cw, ch = c.size
        if cw / ch > r:
            nw = int(ch * r)
            c = c.crop(((cw - nw) // 2, 0, (cw - nw) // 2 + nw, ch))
        else:
            nh = int(cw / r)
            c = c.crop((0, 0, cw, nh))
        c = c.resize((w, h), Image.LANCZOS)
        c = ImageChops.multiply(c, Image.new("RGB", c.size, (225, 238, 250)))
        shade = Image.new("L", c.size, 0)
        sd = ImageDraw.Draw(shade)
        for y in range(h):
            sd.line([(0, y), (w, y)], fill=int(235 * max(0, (y - h * 0.30) / (h * 0.70)) ** 1.1))
        c = Image.composite(Image.new("RGB", c.size, (4, 12, 26)), c, shade)
        c.save(os.path.join(A, "hero%d.png" % i))
        t = src.crop((int(x0 * k), int(y0 * k), int(x1 * k), int(y1 * k)))
        tw, th = t.size
        m = min(tw, th)
        t = t.crop(((tw - m) // 2, (th - m) // 2, (tw - m) // 2 + m, (th - m) // 2 + m)).resize((86, 86), Image.LANCZOS)
        t = ImageChops.multiply(t, Image.new("RGB", t.size, (225, 238, 250)))
        t.save(os.path.join(A, "thumb%d.png" % i))


def small_logo():
    im = Image.open(os.path.join(A, "icon_512.png")).convert("RGBA").resize((40, 40), Image.LANCZOS)
    im.save(os.path.join(A, "logo_small.png"))


if __name__ == "__main__":
    ui_bg(); icons(); art(); small_logo()
    print("hotovo")
