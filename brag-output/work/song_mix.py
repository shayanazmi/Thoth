"""Song cut for the Thoth reel: YE "PREACHER MAN" from 0:47.99 (160 BPM, drop at video 12.0s) with SFX on the cuts.
usage: python3 -I song_mix.py <track.wav> <out_song.wav> <out_sfx_only.wav>"""
import sys
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt, fftconvolve, resample_poly

SR = 44100
START, DUR = 47.99, 18.0
N = int(SR * DUR)
rng = np.random.default_rng(5)

sr0, song = wavfile.read(sys.argv[1])
song = song.astype(np.float32) / (32768.0 if song.dtype == np.int16 else 1.0)
if song.ndim == 1:
    song = np.stack([song, song], 1)
if sr0 != SR:
    song = resample_poly(song, SR, sr0, axis=0)
seg = song[int(START * SR): int(START * SR) + N].copy()


def tvec(length):
    return np.arange(int(length * SR)) / SR


def filt(x, kind, hz):
    return sosfilt(butter(2, hz, kind, fs=SR, output='sos'), x, axis=0)


def place(buf, sig, at, gain=1.0):
    i = int(round(at * SR)); j = min(len(buf), i + len(sig))
    if 0 <= i < len(buf):
        buf[i:j] += sig[: j - i] * gain


def impact(size=1.0):
    # Mid-heavy so it reads on phone speakers without fighting the song's sub.
    t = tvec(1.2)
    thump = np.sin(2 * np.pi * np.cumsum(70 + 90 * np.exp(-t / 0.05)) / SR) * np.exp(-t / 0.25)
    crack = filt(rng.standard_normal(len(t)), 'band', [400, 4000]) * np.exp(-t / 0.07) * 0.7
    return np.tanh((thump + crack) * 1.8) * 0.8 * size


def whoosh(length, rev=False):
    t = tvec(length); x = t / length
    n = rng.standard_normal(len(t))
    out = (filt(n, 'low', 900) * (1 - x) + filt(n, 'high', 2500) * x) * 0.5 * x ** 2
    return out[::-1] if rev else out


def tick():
    t = tvec(0.03)
    return filt(rng.standard_normal(len(t)), 'band', [2500, 7000]) * np.exp(-t / 0.004) * 0.5


def key():
    t = tvec(0.025)
    return filt(rng.standard_normal(len(t)), 'band', [1500, 5000]) * np.exp(-t / 0.003) * 0.4


sfx = np.zeros(N)
place(sfx, impact(1.0), 1.5)                         # gold slam, as the beat drops out
place(sfx, whoosh(0.5, rev=True), 2.5, 0.6)
place(sfx, impact(0.8), 3.0)                         # reveal
for k in range(36):                                  # typing 4.6–5.65
    place(sfx, key(), 4.6 + k * (1.05 / 36) + rng.uniform(-0.006, 0.006), rng.uniform(.6, 1))
place(sfx, tick() * 2, 6.0, 0.8)                     # send
for at, g in ((7.5, 0.5), (7.875, 0.6), (9.0, 0.6), (10.5, 0.4)):
    place(sfx, impact(g), at)
for i in range(15):                                  # one tick per paper
    place(sfx, tick(), 10.55 + i * 0.045, 0.9)
place(sfx, impact(1.2), 12.0)                        # drop
place(sfx, impact(0.7), 12.375)                      # stamp
place(sfx, impact(0.5), 15.0)

# Short room so the SFX sit in a space rather than on top.
ir_t = tvec(0.5)
ir = rng.standard_normal(len(ir_t)) * np.exp(-ir_t / 0.09)
ir /= np.sqrt((ir ** 2).sum())
sfx = sfx + fftconvolve(sfx, ir)[:N] * 0.25
sfx_st = np.stack([sfx, sfx], 1)

fade_in, fade_out = int(0.01 * SR), int(0.03 * SR)


def edge(x):
    x = x.copy()
    x[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    x[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    return x


song_mix = seg / (np.max(np.abs(seg)) + 1e-9) * 0.9 + sfx_st * 0.28     # SFX tucked well under the track
song_mix = edge(song_mix / np.max(np.abs(song_mix)) * 0.95)
sfx_only = edge(sfx_st / np.max(np.abs(sfx_st)) * 0.6)
wavfile.write(sys.argv[2], SR, (song_mix * 32767).astype(np.int16))
wavfile.write(sys.argv[3], SR, (sfx_only * 32767).astype(np.int16))
print('wrote', sys.argv[2], 'and', sys.argv[3])
