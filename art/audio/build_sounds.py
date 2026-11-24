"""
Cuts the game's recorded sounds out of free sound libraries and writes them, ready for
Unity, under game/Assets/_Project/Resources/Audio.

    python3 art/audio/build_sounds.py --firearms "<Prepared SFX Library>" --foley <dir> --out game/Assets/_Project/Resources/Audio
    (add --only hits to rebuild just the sounds of a shot landing)

--firearms is the unpacked "The Free Firearm Sound Library" (CC0); --foley is a folder
holding the other downloads named in art/audio/README.md (all CC0). Needs numpy, scipy,
soundfile and ffmpeg (with libvorbis).

Each gun gets up to three close takes (near1..3) and two distant ones (far1..2), each a
single shot from the moment it goes off, cut before the next one and faded out, mono at
48 kHz. The game picks the set from the weapon's audio profile and pitches it for the
weapon (see SoundBank.Shot).
"""
import argparse, glob, hashlib, os, subprocess, tempfile
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly, butter, sosfilt

RATE = 48000

# set name: (library folder, close recording, distant recording, seconds of ring-out kept close up).
# A distant recording may name another folder ("Folder/File") where the gun's own is a burst.
GUNS = {
    "ar15":        ("AR-15", "D_32P", "D_24P", 1.2),
    "ak47":        ("AK-47", "C_28P", "C_31P", 1.2),
    "m45":         ("Carl Gustav M45", "G_31P", "G_20P", 0.9),
    "pump":        ("CD", "H_21P", "H_16P", 1.4),
    "model12":     ("Model 12", "K_22P", "K_17P", 1.4),
    "mossberg":    ("Mossberg", "N_30P", "N_26P", 1.4),
    "mosin":       ("Mosin Nagant", "M_21P", "M_26P", 1.7),
    "tikka":       ("Tikka", "W_29P", "W_24P", 1.6),
    "m1911":       ("1911", "A_42P", "A_34P", 1.0),
    "ppq":         ("Walther PPQ", "X_39P", "X_31P", 1.0),
    "revolver":    ("Smith & Wesson 642", "V_27P", "V_22P", 1.1),
    "bersa":       ("Bersa", "F_47P", "F_41P", 0.9),
}
FAR_SECONDS = 1.8

# Sfx name: list of (file under --foley, start s, end s or None)
FOLEY = {
    "ReloadStart": [("reload.wav", 0.05, 0.55), ("gunreload1.wav", 0.05, 0.9)],
    "ReloadEnd":   [("reload.wav", 0.55, None), ("clipload1.wav", 0.0, None), ("clipload2.wav", 0.0, None)],
    "RoundIn":     [("singlebullet1.wav", 0.0, None)],
    "DryFire":     [("equipment_clicks3.wav", 0.17, 0.42)],
    "Footstep":    [("Fantozzi-StoneL1.flac", 0, None), ("Fantozzi-StoneL2.flac", 0, None), ("Fantozzi-StoneL3.flac", 0, None),
                    ("Fantozzi-StoneR1.flac", 0, None), ("Fantozzi-StoneR2.flac", 0, None), ("Fantozzi-StoneR3.flac", 0, None)],
    "BodyHit":     [("qubodupImpactMeat01.flac", 0, None), ("qubodupImpactMeat02.flac", 0, None)],
    "Explosion":   [("Chunky Explosion.mp3", 0.0, 4.0), ("explosion3.ogg", 0.0, None)],
}


# What you hear when your shot lands: each sound's takes, each take its layers, as (file, pitch,
# gain in dB, delay in ms, seconds kept). "@tick" is a crisp synthesised click on the moment of
# impact and "@thump" a short low thud, so a hit reads clearly over gunfire. Every recording is
# from the CC0 packs listed in README.md: Independent.nu's hits and punches, qubodup's impacts,
# StarNinjas' metal dings.
HITS = {
    # A body hit: a punch's thud and a tick on top.
    "Hit": [
        [("hit29.mp3.flac", 1.15, 0, 0, 0.16), ("@tick", 1.0, -7, 0, 0.03)],
        [("hit23.mp3.flac", 1.15, 0, 0, 0.16), ("@tick", 1.08, -7, 0, 0.03)],
        [("hit31.mp3.flac", 1.2, 0, 0, 0.16), ("@tick", 0.94, -7, 0, 0.03)],
        [("hit22.mp3.flac", 1.15, 0, 0, 0.16), ("@tick", 1.04, -7, 0, 0.03)],
    ],
    # A head shot: a sharper crack and a bright metal tink, as off a helmet.
    "Headshot": [
        [("hit28.mp3.flac", 1.3, -2, 0, 0.14), ("ding.4.ogg", 1.45, -3, 0, 0.22), ("@tick", 1.25, -5, 0, 0.03)],
        [("hit10.mp3.flac", 1.3, -2, 0, 0.14), ("ding.3.ogg", 1.6, -3, 0, 0.22), ("@tick", 1.3, -5, 0, 0.03)],
        [("hit11.mp3.flac", 1.3, -2, 0, 0.14), ("ding.4.ogg", 1.55, -3, 0, 0.22), ("@tick", 1.2, -5, 0, 0.03)],
    ],
    # A kill: a heavy, wet impact with a deep thud under it.
    "Kill": [
        [("qubodupImpactMeat02.flac", 0.85, 0, 0, 0.18), ("hit17.mp3.flac", 0.9, -3, 0, 0.25), ("@thump", 1.0, -4, 0, 0.16)],
        [("qubodupImpactMeat02.flac", 0.8, 0, 0, 0.18), ("hit22.mp3.flac", 0.85, -3, 0, 0.25), ("@thump", 0.9, -4, 0, 0.16)],
        [("qubodupImpactMeat02.flac", 0.9, 0, 0, 0.18), ("hit31.mp3.flac", 0.9, -3, 0, 0.25), ("@thump", 1.1, -4, 0, 0.16)],
    ],
    # A kill with a head shot: the heavy impact and a ringing ding.
    "KillHeadshot": [
        [("qubodupImpactMeat02.flac", 0.85, -1, 0, 0.18), ("ding.3.ogg", 1.2, -3, 0, 0.6), ("@thump", 1.0, -5, 0, 0.16)],
        [("qubodupImpactMeat02.flac", 0.8, -1, 0, 0.18), ("ding.4.ogg", 1.1, -3, 0, 0.45), ("@thump", 0.9, -5, 0, 0.16)],
    ],
}


def guid(rel):
    return hashlib.md5(("pulsebreak:" + rel).encode()).hexdigest()


def meta(path, folder=False):
    """The .meta beside a new asset, with the project's stable GUID; Unity fills in the importer."""
    rel = "Assets/" + path.replace(os.sep, "/").split("/Assets/", 1)[1]
    text = "fileFormatVersion: 2\nguid: %s\n" % guid(rel)
    if folder:
        text += "folderAsset: yes\nDefaultImporter:\n  externalObjects: {}\n  userData: \n  assetBundleName: \n  assetBundleVariant: \n"
    with open(path + ".meta", "w", newline="\n") as f:
        f.write(text)


def folder(path):
    os.makedirs(path, exist_ok=True)
    meta(path, folder=True)


def read(path):
    """Mono at RATE. Of a stereo pair it keeps the louder side: the mics are spaced, so a mix would comb."""
    if not path.endswith((".wav", ".flac")):
        tmp = tempfile.mktemp(suffix=".wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, tmp], check=True)
        path = tmp
    data, rate = sf.read(path, always_2d=True)
    side = int(np.argmax((data ** 2).sum(axis=0)))
    mono = data[:, side]
    if rate != RATE:
        g = np.gcd(rate, RATE)
        mono = resample_poly(mono, RATE // g, rate // g)
    # Rumble and DC off.
    return sosfilt(butter(2, 25, "highpass", fs=RATE, output="sos"), mono)


def shots(signal):
    """Where each shot goes off (sample index): loud rises at least a second after the last, echoes skipped."""
    window = RATE // 200
    n = len(signal) // window
    env = np.abs(signal[:n * window]).reshape(n, window).max(axis=1)
    found = []
    for i in range(4, n):
        if env[i] < 0.5 * env.max() or env[i - 4:i].max() > env[i] * 0.5:
            continue
        if found and (i - found[-1]) * window < RATE * 1.0:
            continue
        found.append(i)
    starts = []
    for i in found:
        chunk = signal[max(0, (i - 4) * window):(i + 2) * window]
        rise = int(np.argmax(np.abs(chunk) > 0.2 * np.abs(chunk).max()))
        starts.append(max(0, (i - 4) * window + rise - RATE // 500))
    return starts


def compress(clip, threshold=0.18, ratio=3.0):
    """Brings the boom and ring-out of a shot up under its first crack, as a game mix does:
    the gain falls above threshold (of the peak) by ratio, following a 2 ms peak, 70 ms release envelope."""
    from scipy.ndimage import maximum_filter1d
    from scipy.signal import lfilter
    level = maximum_filter1d(np.abs(clip), RATE // 500)
    a = np.exp(-1.0 / (0.07 * RATE))
    level = np.maximum(level, lfilter([1 - a], [1, -a], level))
    over = np.maximum(level / (threshold * np.abs(clip).max()), 1.0)
    return clip * over ** (1.0 / ratio - 1.0)


def shape(clip, fade_from=0.6):
    """A millisecond's fade in, and from fade_from of the way through, a curve down to silence."""
    clip = clip.copy()
    attack = RATE // 1000
    clip[:attack] *= np.linspace(0, 1, attack)
    start = int(len(clip) * fade_from)
    tail = len(clip) - start
    clip[start:] *= np.cos(np.linspace(0, np.pi / 2, tail)) ** 2
    peak = np.abs(clip).max()
    return clip * (0.95 / peak) if peak > 0 else clip


def write(clip, path):
    tmp = tempfile.mktemp(suffix=".wav")
    sf.write(tmp, clip.astype(np.float32), RATE, subtype="FLOAT")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-c:a", "libvorbis", "-q:a", "6", "-ar", str(RATE), "-ac", "1", path], check=True)
    os.remove(tmp)
    meta(path)


def cut_shots(signal, seconds, count):
    out = []
    starts = shots(signal)
    for k, s in enumerate(starts[:count]):
        end = s + int(seconds * RATE)
        if k + 1 < len(starts):
            end = min(end, starts[k + 1] - RATE // 20)
        out.append(shape(compress(signal[s:end])))
    return out


def build_guns(library, out):
    root = os.path.join(out, "Guns")
    folder(root)
    for name, (sub, near, far, seconds) in GUNS.items():
        d = os.path.join(root, name)
        folder(d)
        close = cut_shots(read(os.path.join(library, sub, near + ".wav")), seconds, 3)
        far_path = os.path.join(library, far + ".wav") if "/" in far else os.path.join(library, sub, far + ".wav")
        distant = cut_shots(read(far_path), FAR_SECONDS, 2)
        for i, c in enumerate(close):
            write(c, os.path.join(d, "near%d.ogg" % (i + 1)))
        for i, c in enumerate(distant):
            write(c, os.path.join(d, "far%d.ogg" % (i + 1)))
        print("%-12s %d close, %d distant" % (name, len(close), len(distant)))


def find(foley, name):
    hits = glob.glob(os.path.join(foley, "**", name), recursive=True)
    if not hits:
        raise SystemExit("missing %s under %s" % (name, foley))
    return hits[0]


def build_foley(foley, out):
    root = os.path.join(out, "Sfx")
    folder(root)
    for sfx, parts in FOLEY.items():
        for i, (name, start, end) in enumerate(parts):
            signal = read(find(foley, name))
            clip = signal[int(start * RATE):int(end * RATE) if end else len(signal)]
            # Trim leading silence so the sound lands on its event.
            above = np.nonzero(np.abs(clip) > 0.05 * np.abs(clip).max())[0]
            clip = clip[max(0, above[0] - RATE // 500):] if len(above) else clip
            write(shape(clip, 0.85), os.path.join(root, "%s%d.ogg" % (sfx, i + 1)))
        print("%-12s %d" % (sfx, len(parts)))


def tick(pitch):
    """A few milliseconds of bright click: noise above 2.5 kHz and a 3.4 kHz ring, gone at once."""
    n = int(0.03 * RATE)
    t = np.arange(n) / RATE
    noise = sosfilt(butter(2, 2500, "highpass", fs=RATE, output="sos"), np.random.default_rng(7).standard_normal(n))
    ring = np.sin(2 * np.pi * 3400 * pitch * t)
    return (0.6 * noise * np.exp(-t / 0.0012) + ring * np.exp(-t / 0.004)) * 0.8


def thump(pitch):
    """A short, low thud: a falling 85 Hz tone."""
    n = int(0.16 * RATE)
    t = np.arange(n) / RATE
    freq = 85 * pitch * (1 + 0.6 * np.exp(-t / 0.02))
    return np.sin(2 * np.pi * np.cumsum(freq) / RATE) * np.exp(-t / 0.045)


def layer(foley, name, pitch, seconds):
    """One layer: from the moment it starts, pitched (faster and higher above 1), cut to length and faded out."""
    if name == "@tick":
        clip = tick(pitch)
    elif name == "@thump":
        clip = thump(pitch)
    else:
        clip = read(find(foley, name))
        # From the impact itself (the first sample at a third of the peak), not any lead-in before it.
        above = np.nonzero(np.abs(clip) > 0.33 * np.abs(clip).max())[0]
        clip = clip[max(0, above[0] - RATE // 1000):] if len(above) else clip
        if abs(pitch - 1) > 1e-3:
            up, down = int(round(1000 / pitch)), 1000
            g = np.gcd(up, down)
            clip = resample_poly(clip, up // g, down // g)
        clip = clip / max(np.abs(clip).max(), 1e-9)
    clip = clip[:int(seconds * RATE)]
    tail = len(clip) // 2
    clip = clip.copy()
    clip[-tail:] *= np.cos(np.linspace(0, np.pi / 2, tail)) ** 2
    return clip


def build_hits(foley, out):
    root = os.path.join(out, "Sfx")
    folder(root)
    for sfx, takes in HITS.items():
        for i, layers in enumerate(takes):
            parts = []
            for name, pitch, gain, delay, seconds in layers:
                clip = layer(foley, name, pitch, seconds) * 10 ** (gain / 20)
                parts.append(np.concatenate([np.zeros(int(delay / 1000 * RATE)), clip]))
            mix = np.zeros(max(len(p) for p in parts))
            for p in parts:
                mix[:len(p)] += p
            write(shape(mix, 0.7), os.path.join(root, "%s%d.ogg" % (sfx, i + 1)))
        print("%-12s %d" % (sfx, len(takes)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--firearms", help="the unpacked Free Firearm Sound Library; without it the guns are left as they are")
    ap.add_argument("--foley", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", choices=["guns", "foley", "hits"], help="build just one part")
    a = ap.parse_args()
    folder(a.out)
    if a.firearms and a.only in (None, "guns"):
        build_guns(a.firearms, a.out)
    if a.only in (None, "foley"):
        build_foley(a.foley, a.out)
    if a.only in (None, "hits"):
        build_hits(a.foley, a.out)
