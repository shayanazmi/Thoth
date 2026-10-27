"""Tempo, beat grid and energy profile of a track (numpy/scipy only).
usage: python3 -I analyze.py <track.wav> <out.json>"""
import json, sys
import numpy as np
from scipy.io import wavfile
from scipy.signal import stft, butter, sosfilt, resample_poly

sr0, x = wavfile.read(sys.argv[1])
x = x.astype(np.float32)
if x.ndim > 1:
    x = x.mean(1)
x /= np.max(np.abs(x)) + 1e-9
SR = 22050
x = resample_poly(x, SR, sr0)
HOP = 256

f, t, Z = stft(x, SR, nperseg=1024, noverlap=1024 - HOP, boundary=None)
mag = np.log1p(np.abs(Z) * 50)
flux = np.maximum(0, np.diff(mag, axis=1)).sum(0)
flux = np.concatenate([[0], flux])
flux -= np.convolve(flux, np.ones(16) / 16, 'same')       # local mean removal
flux = np.maximum(flux, 0)
fps = SR / HOP
times = np.arange(len(flux)) / fps

# Tempo: autocorrelation of the onset envelope, 70–180 BPM, with a mild preference near 120.
ac = np.correlate(flux, flux, 'full')[len(flux) - 1:]
lags = np.arange(len(ac))
bpm_of = lambda lag: 60 * fps / lag
cands = [(lag, ac[lag] * np.exp(-0.5 * (np.log2(bpm_of(lag) / 120) / 0.9) ** 2))
         for lag in range(int(60 * fps / 180), int(60 * fps / 70))]
lag = max(cands, key=lambda c: c[1])[0]
# refine with parabolic interpolation
a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]
lag_f = lag + 0.5 * (a - c) / (a - 2 * b + c)
bpm = bpm_of(lag_f)
period = 60 / bpm

# Beat phase: comb that best matches the onsets over the whole song.
best = None
for ph in np.linspace(0, period, 200, endpoint=False):
    beats = np.arange(ph, times[-1], period)
    idx = np.clip(np.round(beats * fps).astype(int), 0, len(flux) - 1)
    score = flux[idx].sum()
    if best is None or score > best[0]:
        best = (score, ph)
phase = best[1]
beats = np.arange(phase, times[-1], period)

# Energy per beat: full band and sub band (the drop lives in the low end).
low = sosfilt(butter(4, 150, 'low', fs=SR, output='sos'), x)
def rms(sig, a, b):
    s = sig[int(a * SR):int(b * SR)]
    return float(np.sqrt(np.mean(s ** 2))) if len(s) else 0.0
beat_rows = [{'t': round(float(b0), 3), 'rms': rms(x, b0, b0 + period), 'low': rms(low, b0, b0 + period),
              'onset': float(flux[min(len(flux) - 1, int(round(b0 * fps)))])} for b0 in beats]

# Drop candidates: biggest jump in low-band energy, 4 beats after vs 4 beats before.
lows = np.array([r['low'] for r in beat_rows]); full = np.array([r['rms'] for r in beat_rows])
drops = []
for i in range(4, len(beat_rows) - 4):
    before = lows[i - 4:i].mean() + full[i - 4:i].mean()
    after = lows[i:i + 4].mean() + full[i:i + 4].mean()
    drops.append((after - before, i))
drops.sort(reverse=True)
top = []
for score, i in drops:
    if all(abs(i - j) > 8 for _, j in top):
        top.append((score, i))
    if len(top) == 6:
        break

out = {'bpm': round(bpm, 2), 'period': period, 'phase': phase, 'duration': len(x) / SR,
       'drops': [{'beat': i, 't': beat_rows[i]['t'], 'score': round(s, 4)} for s, i in top], 'beats': beat_rows}
json.dump(out, open(sys.argv[2], 'w'))
print(f"BPM {bpm:.2f}  beat {period:.4f}s  phase {phase:.3f}s  duration {out['duration']:.1f}s")
for d in out['drops']:
    print(f"drop cand @ {d['t']:7.2f}s (beat {d['beat']})  score {d['score']}")
# coarse energy map: one row per 4 beats
print('\n t(s)   full  low')
for i in range(0, len(beat_rows), 4):
    r = beat_rows[i:i + 4]
    fm = np.mean([q['rms'] for q in r]); lm = np.mean([q['low'] for q in r])
    print(f"{r[0]['t']:6.1f}  {'#' * int(fm * 60):<24} {'=' * int(lm * 80)}")
