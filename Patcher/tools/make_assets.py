#!/usr/bin/env python3
"""Vygeneruje panely a tlačítka launcheru (potřebuje Pillow: pip install pillow).
Obrázky můžeš místo toho kdykoli přepsat vlastními (Photoshop, PNG s průhledností)."""
import math, os, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
W, H = 1280, 720
FONT = None
for f in (os.path.join(OUT, "fonts", "Tektur-Medium.ttf"), "C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
    if os.path.isfile(f):
        FONT = f
        break


def font(n):
    return ImageFont.truetype(FONT, n) if FONT else ImageFont.load_default()


def rr(draw, box, r, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)


def panels():
    """Tmavé průsvitné sklo s azurovým svitem (noční styl)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    boxes = [(40, 250, 440, 505), (980, 62, 1240, 232), (980, 252, 1240, 545)]
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for b in boxes:
        rr(g, b, 22, outline=(80, 210, 255, 255), width=6)
    glow = glow.filter(ImageFilter.GaussianBlur(7))
    im.alpha_composite(glow)
    d = ImageDraw.Draw(im)
    for b in boxes:
        rr(d, b, 22, fill=(6, 18, 36, 175), outline=(120, 225, 255, 255), width=2)
        rr(d, (b[0] + 6, b[1] + 6, b[2] - 6, b[3] - 6), 17, outline=(120, 225, 255, 55), width=1)
    bar = Image.new("RGBA", (W, 170), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bar)
    for y in range(170):
        bd.line([(0, y), (W, y)], fill=(3, 10, 24, int(225 * (y / 170) ** 0.7)))
    im.alpha_composite(bar, (0, H - 170))
    d = ImageDraw.Draw(im)
    d.line([(0, 58), (W, 58)], fill=(120, 225, 255, 70), width=1)
    d.rectangle((0, 0, W, 57), fill=(3, 10, 24, 120))
    im.save(os.path.join(OUT, "panels.png"))


def glyph(d, kind, cx, cy, s, col):
    if kind == "gear":
        for a in range(0, 360, 45):
            x, y = cx + math.cos(math.radians(a)) * s, cy + math.sin(math.radians(a)) * s
            d.ellipse((x - s * .28, y - s * .28, x + s * .28, y + s * .28), fill=col)
        d.ellipse((cx - s * .8, cy - s * .8, cx + s * .8, cy + s * .8), fill=col)
        d.ellipse((cx - s * .35, cy - s * .35, cx + s * .35, cy + s * .35), fill=(0, 0, 0, 0))
    elif kind == "globe":
        d.ellipse((cx - s, cy - s, cx + s, cy + s), outline=col, width=2)
        d.ellipse((cx - s * .45, cy - s, cx + s * .45, cy + s), outline=col, width=2)
        d.line((cx - s, cy, cx + s, cy), fill=col, width=2)
    elif kind == "help":
        d.ellipse((cx - s, cy - s, cx + s, cy + s), outline=col, width=2)
        d.text((cx, cy), "?", fill=col, font=font(int(s * 1.5)), anchor="mm")
    elif kind == "chat":
        rr(d, (cx - s, cy - s * .7, cx + s, cy + s * .55), 6, fill=col)
        d.polygon([(cx - s * .4, cy + s * .5), (cx - s * .8, cy + s), (cx, cy + s * .5)], fill=col)
    elif kind == "people":
        d.ellipse((cx - s * .35, cy - s, cx + s * .35, cy - s * .3), fill=col)
        d.pieslice((cx - s * .8, cy - s * .1, cx + s * .8, cy + s * 1.5), 180, 360, fill=col)
    elif kind == "folder":
        rr(d, (cx - s, cy - s * .55, cx + s, cy + s * .8), 4, fill=col)
        d.rectangle((cx - s, cy - s * .85, cx - s * .1, cy - s * .5), fill=col)
    elif kind == "check":
        d.line([(cx - s * .9, cy + s * .05), (cx - s * .3, cy + s * .7), (cx + s, cy - s * .8)], fill=col, width=4)
    elif kind == "bag":
        rr(d, (cx - s * .85, cy - s * .35, cx + s * .85, cy + s), 5, fill=col)
        d.arc((cx - s * .5, cy - s * 1.05, cx + s * .5, cy + s * .1), 180, 360, fill=col, width=3)
    elif kind == "play":
        d.polygon([(cx - s * .6, cy - s), (cx - s * .6, cy + s), (cx + s, cy)], fill=col)


def button(name, text, w, h, c1, c2, kind=None, fs=17, glow=(80, 210, 255), border=(150, 235, 255, 255)):
    sc = 2
    pad = 5
    W2, H2 = (w + 2 * pad) * sc, (h + 2 * pad) * sc
    im = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    r = (h // 2 if h < 60 else 30) * sc
    box = (pad * sc, pad * sc, (w + pad) * sc - 1, (h + pad) * sc - 1)
    gl = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(gl).rounded_rectangle(box, r, outline=glow + (255,), width=5 * sc)
    im.alpha_composite(gl.filter(ImageFilter.GaussianBlur(4 * sc)))
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, r, fill=255)
    grad = Image.new("RGBA", im.size)
    gd = ImageDraw.Draw(grad)
    hh = box[3] - box[1]
    for y in range(box[1], box[3] + 1):
        k = (y - box[1]) / max(hh, 1)
        gd.line([(0, y), (W2, y)], fill=tuple(int(c1[i] * (1 - k) + c2[i] * k) for i in range(3)) + (235,))
    im.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle(box, r, outline=border, width=2 * sc)
    d.rounded_rectangle((box[0] + 10 * sc, box[1] + 3 * sc, box[2] - 10 * sc, box[1] + hh // 2), r // 2, fill=(255, 255, 255, 38))
    f = font(fs * sc)
    cx, cy = W2 / 2, H2 / 2
    tw = d.textlength(text, font=f)
    if kind:
        gs = (h * 0.24) * sc
        x0 = cx - (gs * 2 + 10 * sc + tw) / 2
        glyph(d, kind, x0 + gs, cy, gs, (235, 250, 255, 255))
        d.text((x0 + gs * 2 + 10 * sc, cy), text, fill=(240, 252, 255, 255), font=f, anchor="lm")
    else:
        d.text((cx, cy), text, fill=(240, 252, 255, 255), font=f, anchor="mm")
    im.resize((w + 2 * pad, h + 2 * pad), Image.LANCZOS).save(os.path.join(OUT, name))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    panels()
    button("btn_play.png", "HRÁT", 300, 76, (20, 150, 140), (10, 80, 120), "play", 30, glow=(60, 240, 200), border=(170, 255, 235, 255))
    button("btn_settings.png", "Nastavení", 168, 46, (14, 36, 66), (8, 22, 44), "gear", 15)
    button("btn_web.png", "Web", 120, 46, (14, 36, 66), (8, 22, 44), "globe", 15)
    button("btn_support.png", "Podpora", 148, 46, (14, 36, 66), (8, 22, 44), "help", 15)
    button("btn_facebook.png", "Facebook", 160, 46, (22, 60, 130), (10, 32, 84), "people", 15)
    button("btn_discord.png", "Discord", 150, 46, (50, 56, 140), (26, 30, 90), "chat", 15)
    button("btn_check.png", "Kontrola", 135, 42, (22, 110, 120), (10, 62, 88), "check", 14, glow=(60, 240, 200), border=(170, 255, 235, 255))
    button("btn_register.png", "Registrace", 135, 42, (118, 84, 20), (70, 46, 10), "people", 14, glow=(255, 205, 90), border=(255, 232, 170, 255))
    print("hotovo")
