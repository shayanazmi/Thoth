"""Dark drift-phonk for the Thoth reel, v2: 120 BPM half-time (hats at double-time), F minor, 18.0s (9 bars),
beat-locked to the video's cuts. Writes the full mix and an SFX-only stem.
usage: python3 -I music.py <out_full.wav> <out_sfx_only.wav>"""
import sys
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve, lfilter
from scipy.ndimage import minimum_filter1d

SR = 44100
DUR = 18.0
BEAT = 0.5
S16 = BEAT / 4
N = int(SR * DUR)
rng = np.random.default_rng(11)
tt = np.arange(N) / SR


def note(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def tvec(length):
    return np.arange(int(length * SR)) / SR


def place(buf, sig, at, gain=1.0):
    i = int(round(at * SR))
    if i >= buf.shape[0] or i + len(sig) <= 0:
        return
    s0 = max(0, -i); i = max(0, i)
    j = min(buf.shape[0], i + len(sig) - s0)
    buf[i:j] += sig[s0:s0 + j - i] * gain


def filt(x, kind, hz, order=2):
    return sosfilt(butter(order, hz, kind, fs=SR, output='sos'), x, axis=0)


def sat(x, drive):
    return np.tanh(x * drive) / np.tanh(drive)


# ---------- reverb: decaying stereo noise impulse ----------
def make_ir(length, decay, bright):
    t = tvec(length)
    ir = np.stack([filt(rng.standard_normal(len(t)), 'low', bright) for _ in range(2)], 1) * np.exp(-t / decay)[:, None]
    ir[: int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))[:, None]  # pre-delay-ish fade in
    return ir / np.sqrt((ir ** 2).sum(0))


def reverb(mono, ir, wet):
    out = np.stack([fftconvolve(mono, ir[:, c])[:N] for c in range(2)], 1)
    return out * wet


HALL = make_ir(2.4, 0.55, 5000)
ROOM = make_ir(0.6, 0.12, 7000)


# ---------- instruments ----------
def kick(punch=1.0):
    t = tvec(0.5)
    f = 45 + 140 * np.exp(-t / 0.028)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.26)
    click = filt(rng.standard_normal(len(t)), 'high', 3000) * np.exp(-t / 0.003) * 0.4
    return sat(body * punch + click, 2.5) * 0.95


def b808(midi, length, drive=3.0, slide_to=None):
    t = tvec(length)
    f0 = note(midi)
    semis = 3.0 * np.exp(-t / 0.03)
    if slide_to is not None:  # phonk 808 slide into the next note over the last third
        x = np.clip((t - length * 0.62) / (length * 0.3), 0, 1)
        semis = semis + (slide_to - midi) * (x * x * (3 - 2 * x))
    f = f0 * 2 ** (semis / 12)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) + 0.18 * np.sin(2 * ph)
    e = np.minimum(t / 0.004, 1) * np.clip(1 - (t / length) ** 3, 0, 1)
    return sat(s * e, drive) * 0.75


def snare():
    t = tvec(0.35)
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.05) * 0.5
    n = filt(filt(rng.standard_normal(len(t)), 'high', 1200), 'low', 9000) * np.exp(-t / 0.11)
    claps = sum(np.exp(-np.clip(t - d, 0, None) / 0.007) * (t >= d) for d in (0.0, 0.01, 0.021)) * 0.5
    return sat(body + n * (1 + claps), 1.6) * 0.6


def hat(open_=False):
    t = tvec(0.2 if open_ else 0.05)
    metal = sum(np.sign(np.sin(2 * np.pi * f * t)) for f in (3140, 4210, 5530, 6810)) * 0.12
    n = rng.standard_normal(len(t)) * 0.6
    return filt(metal + n, 'high', 7500) * np.exp(-t / (0.07 if open_ else 0.011)) * 0.28


def cowbell(midi, length=0.24, drive=2.0):
    t = tvec(length)
    f = note(midi)
    sq = lambda fr: np.sign(np.sin(2 * np.pi * fr * t))
    s = filt(sq(f) + 0.75 * sq(f * 1.4836), 'band', [480, 5200])
    e = np.exp(-t / 0.035) * 0.65 + np.exp(-t / 0.15) * 0.35
    return sat(s * e, drive) * 0.3


def pad(midis, length):
    # Dark detuned-saw chord, low-passed: the cinematic bed under the phonk.
    t = tvec(length)
    s = np.zeros(len(t))
    for m in midis:
        for d in (-0.11, 0.0, 0.12):
            f = note(m) * 2 ** (d / 12)
            s += 2 * ((f * t + rng.random()) % 1) - 1
    s = filt(s / (len(midis) * 3), 'low', 1100)
    e = np.minimum(t / 0.25, 1) * np.minimum((length - t) / 0.2, 1)
    return s * np.clip(e, 0, 1) * 0.5


def impact(size=1.0):
    t = tvec(1.8)
    sub = np.sin(2 * np.pi * np.cumsum(34 + 70 * np.exp(-t / 0.07)) / SR) * np.exp(-t / 0.7)
    crack = filt(rng.standard_normal(len(t)), 'low', 3500) * np.exp(-t / 0.09) * 0.6
    return sat(sub + crack, 2.0) * 0.8 * size


def riser(length, rev=False):
    t = tvec(length)
    x = t / length
    n = rng.standard_normal(len(t))
    s = filt(n, 'low', 700) * (1 - x) + filt(n, 'high', 2500) * x
    tone = np.sin(2 * np.pi * np.cumsum(110 * 2 ** (3 * x)) / SR) * 0.3
    out = (s * 0.45 + tone) * x ** 2.2
    return out[::-1] if rev else out


def tick():
    t = tvec(0.03)
    return filt(rng.standard_normal(len(t)), 'band', [2500, 7000]) * np.exp(-t / 0.004) * 0.5


def key():
    t = tvec(0.025)
    return filt(rng.standard_normal(len(t)), 'band', [1500, 5000]) * np.exp(-t / 0.003) * 0.35


# ---------- song ----------
# Bars (2s each): Fm Db Bbm C | Fm Db Bbm C | Fm
CHORDS = [(53, 56, 60), (49, 53, 56), (46, 49, 53), (48, 52, 55)]
ROOTS = [29, 25, 34 - 12, 24]          # F1, Db1, Bb0, C1
RIFF = {  # phonk cowbell riff (16ths), adjusted per chord
    0: [77, None, 77, 80, None, 77, 75, None, 77, None, 72, None, 73, None, 72, 68],
    1: [77, None, 77, 80, None, 77, 73, None, 77, None, 72, None, 73, None, 72, 68],
    2: [77, None, 77, 78, None, 77, 73, None, 77, None, 70, None, 73, None, 72, 70],
    3: [76, None, 76, 79, None, 76, 72, None, 76, None, 72, None, 74, None, 72, 67],
}
BASS_STEPS = [(0, 0.72), (6, 0.34), (8, 0.7), (11, 0.33), (14, 0.25)]
KICKS = [0, 6, 8, 11]


def section(t):
    for end, name in ((3.0, 'hook'), (4.0, 'reveal'), (7.0, 'hunch'), (10.5, 'argue'), (11.5, 'papers'),
                      (12.0, 'gasp'), (15.0, 'drop'), (99, 'outro')):
        if t < end:
            return name


drums = np.zeros(N); snr = np.zeros(N); bass = np.zeros(N); bell = np.zeros(N); pads = np.zeros(N); sfx = np.zeros(N)

for bar in range(9):
    b0 = bar * 2.0
    ci = bar % 4
    place(pads, pad(CHORDS[ci], 2.0), b0)
    for step in range(16):
        t = b0 + step * S16
        sec = section(t)
        if sec == 'gasp':
            continue
        full = sec in ('hook', 'argue', 'drop', 'outro')
        m = RIFF[ci][step]
        if m is not None and sec not in ('reveal',):
            up = 12 if sec == 'drop' and step in (0, 3, 8) else 0
            place(bell, cowbell(m + up, drive=3.0 if sec == 'drop' else 2.0), t)
        if full and step in KICKS:
            place(drums, kick(1.2 if sec == 'drop' else 1.0), t)
        if full and step == 8:
            place(snr, snare(), t)
        # double-time hats with 32nd rolls: the drift-phonk engine
        if sec not in ('reveal', 'hunch'):
            place(drums, hat(open_=(step == 14)), t, 0.8 if step % 2 == 0 else 0.5)
            if sec in ('argue', 'drop') and step in (7, 15):
                for r in range(1, 4):
                    place(drums, hat(), t + r * S16 / 4, 0.32 + 0.08 * r)
        elif sec == 'hunch' and step % 4 == 2:
            place(drums, hat(), t, 0.35)
    for k, (st, ln) in enumerate(BASS_STEPS):
        t = b0 + st * S16
        sec = section(t)
        if sec in ('hunch', 'papers', 'gasp', 'reveal'):
            continue
        root = ROOTS[ci]
        nxt = ROOTS[(ci + 1) % 4] if k == len(BASS_STEPS) - 1 else None
        midi = root + (12 if st == 6 else 0)
        place(bass, b808(midi, ln * 2 * BEAT, drive=5.0 if sec == 'drop' else 3.2, slide_to=nxt), t)

# Reveal and hunch keep a sub bed so the energy never fully dies.
place(bass, b808(29, 0.95, drive=2.0), 3.0, 0.8)
place(bass, b808(25, 2.9, drive=1.6), 4.05, 0.45)

# ---------- SFX on the cuts ----------
place(sfx, impact(1.0), 1.0)
place(sfx, riser(0.6, rev=True), 2.4, 0.7)
place(sfx, impact(0.9), 3.0)
for k in range(36):
    place(sfx, key(), 4.15 + k * (1.05 / 36) + rng.uniform(-0.006, 0.006), rng.uniform(.6, 1))
place(sfx, tick() * 2, 5.4, 0.8)
for at, g in ((7.0, 0.5), (7.5, 0.6), (9.0, 0.6)):
    place(sfx, impact(g), at)
for i in range(15):
    place(sfx, tick(), 10.55 + i * 0.062, 0.9)
place(sfx, riser(1.0), 10.5, 0.85)
place(sfx, impact(1.5), 12.0)
place(sfx, impact(0.7), 12.5)
place(sfx, impact(0.6), 15.0)
place(sfx, riser(1.0), 17.0, 0.6)

# ---------- mix ----------
muffle = ((tt >= 3.0) & (tt < 7.0)) | ((tt >= 10.5) & (tt < 12.0))
bell = np.where(muffle, filt(bell, 'low', 850), bell)
pads = np.where((tt >= 11.5) & (tt < 12.0), 0, pads)

# Sidechain pump: everything melodic ducks on each kick.
kick_times = [b * 2.0 + s * S16 for b in range(9) for s in KICKS if section(b * 2.0 + s * S16) in ('hook', 'argue', 'drop', 'outro')]
pump = np.ones(N)
for k in kick_times:
    m = tt >= k
    pump[m] = np.minimum(pump[m], 1 - 0.55 * np.exp(-(tt[m] - k) / 0.11))

mono_music = drums + snr * 0.9 + bass * pump * 0.9 + bell * pump * 0.7 + pads * pump * 0.55
stereo = np.stack([mono_music, mono_music], 1)
stereo += reverb(bell * 0.7 + pads * 0.3, HALL, 0.35)   # the cowbell lives in a dark hall
stereo += reverb(snr, ROOM, 0.45)
stereo[:, 0] += np.roll(bell, 260) * 0.12               # Haas widening on the riff
stereo[:, 1] += np.roll(bell, -260) * 0.12

outro = np.clip((tt - 15.5) / 2.0, 0, 1)[:, None]
stereo = stereo * (1 - outro * 0.7) + filt(stereo, 'low', 1000) * (outro * 0.7)

sfx_st = np.stack([sfx, sfx], 1) + reverb(sfx, HALL, 0.25)


def master(x, ceiling=0.89):
    x = filt(x, 'high', 28)
    x = x / np.max(np.abs(x)) * 1.6                     # push into the limiter
    peak = np.max(np.abs(x), axis=1)
    gain = np.minimum(1.0, ceiling / np.maximum(peak, 1e-9))
    gain = minimum_filter1d(gain, int(0.004 * SR))       # ~4ms look-ahead hold
    a = np.exp(-1 / (0.06 * SR))                          # 60ms release
    gain = lfilter([1 - a], [1, -a], gain)
    gain = np.minimum(gain, ceiling / np.maximum(peak, 1e-9))
    y = x * gain[:, None]
    f = int(0.004 * SR)
    y[:f] *= np.linspace(0, 1, f)[:, None]; y[-f:] *= np.linspace(1, 0, f)[:, None]
    return np.clip(y, -1, 1)


def write(path, x):
    from scipy.io import wavfile
    wavfile.write(path, SR, (x * 32767).astype(np.int16))
    print('wrote', path)


# The held breath: near-silence from 11.55s until the drop at 12.0s.
gasp = 1 - 0.94 * (np.clip((tt - 11.52) / 0.03, 0, 1) * np.clip((11.995 - tt) / 0.005, 0, 1))
stereo *= gasp[:, None]; sfx_st *= gasp[:, None]

write(sys.argv[1], master(stereo + sfx_st * 0.55))
write(sys.argv[2], master(sfx_st, ceiling=0.6))
