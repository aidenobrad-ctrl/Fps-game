"""
Cuts the game's recorded sounds out of free sound libraries and writes them, ready for
Unity, under game/Assets/_Project/Resources/Audio.

    python3 art/audio/build_sounds.py --firearms "<Prepared SFX Library>" --foley <dir> --out game/Assets/_Project/Resources/Audio

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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--firearms", required=True)
    ap.add_argument("--foley", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    folder(a.out)
    build_guns(a.firearms, a.out)
    build_foley(a.foley, a.out)
