#!/usr/bin/env python3
"""Vlastní hudební smyčka (syntetizovaná, bez cizích autorských práv): orientální pentatonika, pad, trsaná struna, bubny.
Spuštění: python make_music.py vystup.wav   (pak ffmpeg -i vystup.wav -b:a 160k theme.mp3). Potřebuje numpy a scipy."""
import sys, numpy as np
from scipy.signal import lfilter, fftconvolve, butter, sosfilt
from scipy.io import wavfile
SR = 44100
rng = np.random.default_rng(7)
BPM = 68
beat = 60.0 / BPM
bars = 24
T = bars * 4 * beat
N = int(T * SR)
L = np.zeros(N); R = np.zeros(N)

def hz(m): return 440.0 * 2 ** ((m - 69) / 12)
def add(buf, x, t0, pan=0.0, g=1.0):
    idx = (int(t0 * SR) + np.arange(len(x))) % N      # smyčka: konec přetéká na začátek
    np.add.at(buf[0], idx, x * g * (1 - max(pan, 0)))
    np.add.at(buf[1], idx, x * g * (1 + min(pan, 0)))
dry = (L, R)

def pluck(f, dur=3.0, bright=0.5):
    n = int(dur * SR); p = int(SR / f); buf = rng.uniform(-1, 1, p) * np.hanning(p) ** 0.3
    out = np.zeros(n); out[:p] = buf
    d = 0.9965 - 0.0004 * (f / 400)
    for i in range(p, n):
        out[i] = d * (bright * out[i - p] + (1 - bright) * out[i - p + 1 if i - p + 1 < i else i - p])
    return out

def pluck_fast(f, dur=3.0):
    n = int(dur * SR); t = np.arange(n) / SR
    x = np.zeros(n)
    for k, a in ((1, 1), (2, .5), (3, .33), (4, .18), (5, .1)):
        x += a * np.sin(2 * np.pi * f * k * t) * np.exp(-t * (1.6 + 1.3 * k) * (f / 300) ** 0.3)
    x *= np.minimum(1, t * 400)
    return x

def pad(freqs, dur):
    n = int(dur * SR); t = np.arange(n) / SR; x = np.zeros(n)
    for f in freqs:
        for det in (-0.07, 0.0, 0.06):
            ff = f * 2 ** (det / 12); x += np.sin(2 * np.pi * ff * t + rng.uniform(0, 6.28)) + 0.4 * np.sin(4 * np.pi * ff * t) + 0.15 * np.sin(6 * np.pi * ff * t)
    env = np.minimum(1, t / 2.2) * np.minimum(1, (dur - t) / 2.5)
    return x * env / (len(freqs) * 3)

def taiko(f0=70, dur=1.6):
    n = int(dur * SR); t = np.arange(n) / SR
    f = f0 * (1 + 1.6 * np.exp(-t * 12))
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)
    x += 0.2 * rng.normal(size=n) * np.exp(-t * 40)
    return x

def bell(f, dur=5.0):
    n = int(dur * SR); t = np.arange(n) / SR
    return sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t * d) for r, a, d in ((1, 1, .8), (2.76, .5, 1.2), (5.4, .3, 1.8))) * np.minimum(1, t * 600)

# akordy (MIDI): d moll / B dur / F / C ... pentatonika D F G A C
prog = [((38, 50, 57, 62, 65), 0), ((34, 46, 53, 58, 62), 1), ((41, 53, 57, 60, 65), 2), ((36, 48, 55, 60, 64), 3)]
bar_len = 4 * beat
for b in range(0, bars, 2):
    ch, _ = prog[(b // 2) % 4]
    add(dry, pad([hz(m) for m in ch], 2 * bar_len + 2.0), b * bar_len, 0, 0.55)
# bubny: každé 2 takty hluboký úder, v druhé půlce přidaný puls
for b in range(bars):
    add(dry, taiko(62), b * bar_len, 0, 0.55 if b % 2 == 0 else 0.3)
    if b >= 8 and b % 2 == 1:
        add(dry, taiko(88, 0.9), b * bar_len + 2 * beat, 0.2, 0.28); add(dry, taiko(88, 0.9), b * bar_len + 3 * beat, -0.2, 0.22)
# melodie: trsaná struna, pentatonika D F G A C (MIDI 62 65 67 69 72 74 77 79)
scale = [62, 65, 67, 69, 72, 74, 77, 79]
motifs = [[0, 2, 3, 4, 3, 2], [1, 3, 4, 5, 4, 3, 2], [4, 3, 2, 3, 1, 0], [0, 1, 2, 4, 3, 2, 1, 0]]
for b in range(4, bars):
    if b % 2 == 1 and b < 22: continue
    m = motifs[(b // 2) % 4]; t0 = b * bar_len
    pos = 0.0
    for k, idx in enumerate(m):
        dur = beat * (1.0 if k % 3 == 0 else 0.5)
        add(dry, pluck_fast(hz(scale[idx])) if False else pluck(hz(scale[idx]), 3.0, 0.5), t0 + pos, (k % 3 - 1) * 0.25, 0.42)
        pos += dur
# zvonky
for b in range(0, bars, 4):
    add(dry, bell(hz(81)), b * bar_len + beat, 0.3, 0.12); add(dry, bell(hz(74)), b * bar_len + 3.5 * beat, -0.3, 0.1)
# nízký bas
for b in range(0, bars, 2):
    ch, _ = prog[(b // 2) % 4]; f = hz(ch[0]); n = int(2 * bar_len * SR); t = np.arange(n) / SR
    add(dry, np.sin(2 * np.pi * f * t) * np.minimum(1, t) * np.minimum(1, (2 * bar_len - t) / 1.5) * 0.35, b * bar_len, 0, 0.5)
# reverb (konvoluce se šumem s doznívajícím průběhem), cirkulárně kvůli smyčce
def reverb(x, wet=0.38):
    n = int(2.8 * SR); t = np.arange(n) / SR
    ir = rng.normal(size=n) * np.exp(-t * 2.3)
    ir = lfilter([1], [1, -0.55], ir)
    y = fftconvolve(np.concatenate([x, x[:n]]), ir)[n:n + len(x)] if False else fftconvolve(np.concatenate([x[-n:], x]), ir)[n:n + len(x)]
    return x * (1 - wet) + y * wet * 0.045
Lr, Rr = reverb(L), reverb(R)
sos = butter(2, 9500, 'low', fs=SR, output='sos'); Lr = sosfilt(sos, Lr); Rr = sosfilt(sos, Rr)
m = max(np.abs(Lr).max(), np.abs(Rr).max()); out = np.stack([Lr, Rr], 1) / m * 0.85
# plynulý okraj pro smyčku
f = int(0.05 * SR); w = np.linspace(0, 1, f)[:, None]
out[:f] = out[:f] * w + out[-f:] * (1 - w) * 0 ; out[-f:] *= w[::-1]
wavfile.write(sys.argv[1] if len(sys.argv) > 1 else 'theme.wav', SR, (out * 32767).astype(np.int16))
print('%.1f s' % T)
