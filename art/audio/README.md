# Recorded sounds

The game's gunshots, reloads, footsteps, body hits and explosions are real recordings, cut
by `build_sounds.py` into `game/Assets/_Project/Resources/Audio`:

- `Guns/<set>/near1..3.ogg`: single shots up close, from the moment the shot goes off.
- `Guns/<set>/far1..2.ogg`: the same gun from a distance.
- `Sfx/<Effect>1..n.ogg`: takes of an effect, named after the `Sfx` it replaces.

Each weapon names its set and a pitch in its audio profile (`recording` and `recordingPitch` in
`WPN_*.asset`, authored in the roster). `RecordedSounds` loads them and turns them into the
synthesiser's format. Whatever has no recording, such as launchers, melee swings, casings,
ricochets and the interface, is still synthesised.

Everything here is CC0 (public domain), so no credit is required. It is credited anyway.

| Used for | Source | Author | Licence |
|---|---|---|---|
| Every gunshot (12 sets: AR-15, AK-47, Carl Gustav M45, three shotguns, Mosin-Nagant, Tikka T3, 1911, Walther PPQ, S&W 642, Bersa) | [The Free Firearm Sound Library](https://opengameart.org/content/the-free-firearm-sound-library) ("Prepared SFX Library.7z") | The Free Firearm Sound Library team (freefirearmsfx.com), posted by bart | CC0 |
| Reload start and end (handgun) | [Handgun Reload Sound Effect](https://opengameart.org/content/handgun-reload-sound-effect) (`reload.wav`) | zer0_sol | CC0 |
| Reload end, round in | [Gun Reload Sound Effects](https://opengameart.org/content/gun-reload-sound-effects) (`clipload1.wav`, `clipload2.wav`, `singlebullet1.wav`) | BMacZero | CC0 |
| Reload start | [Gun reload sounds](https://opengameart.org/content/gun-reload-sounds) (`gunreload1.wav`) | SpringySpringo | CC0 |
| Dry fire click | [equipment clicks III](https://opengameart.org/content/equipment-clicks-iii) (`equipment_clicks3.wav`) | LFA | CC0 |
| Footsteps | [Fantozzi's Footsteps (Grass/Sand & Stone)](https://opengameart.org/content/fantozzis-footsteps-grasssand-stone) (`Fantozzi-Stone*.flac`) | Fantozzi, sliced by qubodup | CC0 |
| Body hits | [Impact](https://opengameart.org/content/impact) (`qubodupImpactMeat01/02.flac`) | qubodup | CC0 |
| Explosions | [Chunky Explosion](https://opengameart.org/content/chunky-explosion) (`Chunky Explosion.mp3`), [explosions](https://opengameart.org/content/explosions-4) (`explosion3.ogg`) | Joth; EZduzziteh | CC0 |

Which game weapon fires which recording, and at what pitch, is in `RECORDINGS` in the roster,
for example: the M4A1 fires the AR-15, the AK-47 fires the AK-47, the PKM and SVD fire the
Mosin-Nagant (the same 7.62x54R cartridge), the M1911A1 fires the 1911, the M17 fires the
Walther PPQ (9 mm), and the Desert Eagle fires the S&W 642, pitched down.

Pixabay's sound effects were the first choice, but its site turns away scripted downloads.

## Rebuilding

1. Download the sources above into one folder (`--foley`). Unpack "Prepared SFX Library.7z"
   somewhere (`--firearms`).
2. Run:

   ```
   python3 art/audio/build_sounds.py --firearms "<...>/Prepared SFX Library" --foley <folder> --out game/Assets/_Project/Resources/Audio
   ```

   It needs numpy, scipy, soundfile and ffmpeg built with libvorbis.

The script finds each shot by its rise and cuts it before the next one (echoes are skipped).
Close takes are compressed gently, so the boom and ring-out sit under the crack as in a game
mix, and faded out. Everything is mono at 48 kHz.
