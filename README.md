# Recoil

A fast, competitive multiplayer FPS for PC, built in Unity 6.

Eleven phases are built so far: **movement and a firing range**, **the weapon system with 40 weapons and 21 attachments**, **loadouts**, **online play** on a server that owns the match, **accounts** on a backend of their own, **every game mode, bots and matchmaking**, **character customization with weapon skins**, **progression, challenges and ranked**, **sound, effects, settings and performance**, **friends, parties, chat, reports and ranked seasons**, and **three more maps, private-match rules and smarter bots**. Accounts are switched back on; see [Accounts](#accounts). The plan for everything after is in [docs/ROADMAP.md](docs/ROADMAP.md), and how the code is organised is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

> **Developed without a Unity Editor.** The code is written and checked outside the engine: the C# is compiled against Unity's reference assemblies and checked against the Unity 6000.6, URP 17.6 and Input System 1.20 sources, and the simulation, the weapon data and the netcode are tested there, including whole matches between a real server and real clients on a simulated bad connection, every game mode, bots playing full matches, and the game's account and matchmaking code against the real backend. It is then opened and played in Unity 6000.6.9f1, and what that turns up is fixed from the Console's messages. If something looks wrong, [Troubleshooting](#troubleshooting) says what to check and what to send.

## Open and play

1. Install **Unity 6000.6.9f1** through Unity Hub. The project is set up for that version: URP 17.6, Input System 1.20. A different Unity 6 version may work, but expect errors from older or newer packages.
2. In Unity Hub choose **Add ▸ Add project from disk** and pick the `game` folder inside your copy of this repository (for example `fps-game\game`).
3. Let the first import finish. The firing range scene opens by itself. If it does not, use **Recoil ▸ Open Firing Range** in the menu bar.
4. Press **Play** and click inside the Game view to capture the mouse.

That is the offline range. The main menu and online play are in a second scene: **Recoil ▸ Open Duel (Main Menu)**. See [Play online](#play-online).

On first open Unity creates several settings files and one asset (`Resources/UI/HudPanel.asset`). Commit them; they are part of the project.

## Accounts

**On again.** Sign in (or create an account) from the top of the main menu. An account keeps your loadouts, settings, level, weapon levels, challenges and ranks, and they follow you to any computer. Ranked needs a verified email; the menu tells you how to verify.

Without an account you can still do everything offline, host and join private matches, and play casual matchmaking as a guest, but nothing you play is saved to your progress and you carry only the starter weapons in matchmaking.

The backend has to be running for any of this: see [backend/README.md](backend/README.md). Turning accounts off again is one line: `AccountsEnabled` in `Client/Online/Unity/GameServices.cs`.

## Play online

Online play is in the duel scene (**Recoil ▸ Open Duel (Main Menu)**), which is also the main menu. It fills the screen: your account, level and challenges are on the home screen with **Play**, **Customize**, **Firing range**, **Settings** and **Quit**; friends and your party are down the right. **Play** opens the play page, where you pick a **mode** from the tiles, then:

- **Find match** puts you in that mode's queue on the backend, and drops you into a match on a dedicated server when one is found. Tick **Ranked** (Duel and Elimination) to play for rating. See [Matchmaking](#matchmaking) and [Progress and ranked](#progress-and-ranked).
- **Host a private match** runs the match on your own computer with the rules you pick: map, team size, what wins it, whether bots take the empty places (and how good they are), the time limit (or round time), health, how soon people respawn, and which weapons are allowed (any, sidearms only, snipers only, shotguns only, no explosives, melee only). With bots on, you can play any mode on your own straight away.
- **Join by address** (Direct connect) connects to someone else's private match or to a dedicated server.

**Esc** or **Back** returns to the home screen.

Hits count the way you saw them: when your bullet visibly lands on someone, your game tells the server, which checks it against where that player really was (and that no wall was in the way) before it counts.

### The modes

| Mode | Teams | Respawns | Wins |
| --- | --- | --- | --- |
| Duel | 1 v 1 | No, rounds | First to 5 rounds (best of nine) |
| Team Deathmatch | up to 5 v 5 | Yes | First team to 5 kills |
| Free-for-All | Everyone for themselves, up to 12 | Yes | First to 5 kills |
| Elimination | up to 5 v 5 | No, rounds | Wipe the other team out; first to 5 rounds |
| Domination | up to 5 v 5 | Yes | Hold zones A, B and C; each zone held scores a point a second |
| Hardpoint | up to 5 v 5 | Yes | One zone at a time, moving every minute; hold it alone to score |
| Gun Game | Everyone for themselves | Yes | Every kill hands you the next weapon; a kill with the last one (the knife) wins. Being knifed sets you back one |

Five maps. The menu offers only the maps that suit the chosen mode, and matchmaking picks a different suitable one each match.

| Map | Size | For | What it is |
| --- | --- | --- | --- |
| Relay Yard | 38 × 26 m | Duel, small fights | A walled yard: a block in the middle, two lanes, raised decks at each end |
| Kiln | 32 × 24 m | Duel, 2v2, small Free-for-All | A pillar ringed by knee-high walls, long walls making two lanes, a ledge with stairs at each start |
| Saltworks | 50 × 40 m | Up to 4v4, every mode | Two roofed sheds (zones A and C) across a square of shallow pans (B), raised gantries along the north and south walls |
| Crossroads | 64 × 48 m | Up to 5v5, every mode | Three lanes, a central square, raised decks at each end |
| Lattice | 66 × 50 m | Up to 5v5, every mode | A grid of tall blocks with streets between; the centre lane runs through two hollow blocks (A and C) to a raised plaza (B) |

Teammates are drawn blue with a marker over their heads; everyone else is red. Teammates cannot hurt each other.

### Bots

Bots fill any place nobody has taken, and step aside the moment a person joins. They find their way round the map (including up steps and onto ledges), fall back to cover when they are badly hurt or caught reloading and then peek back out, tell their team where they saw an enemy (teammate bots head there, and people on their team see it in team chat: "Enemy on B"), react after a short delay, aim with a little error that settles while they track you, control recoil, strafe at their weapon's best range, reload and switch weapons, throw grenades, and go for the zones in Domination and Hardpoint. Easy, Normal and Hard differ in reaction time, aim and how fast they turn.

### The quickest test: on your own

1. Open the duel scene and press **Play**.
2. Pick a mode, open **Host a private match**, leave **Empty places** on **Normal bots**, and press **Start private match**.

You are in a match against bots a few seconds later.

### Two people

You need two copies of the game running. The Editor is one; a build is the other.

1. Make a build: **File ▸ Build Profiles** (Build Settings in older versions), check that **Duel** is the first scene in the list and **FiringRange** the second, and press **Build**. If the list is wrong, run **Recoil ▸ Run Project Doctor** first.
2. One copy hosts a private match. The banner shows the address others should use, something like `192.168.1.20` (on one computer, `127.0.0.1`).
3. The other types that address and chooses **Join by address**.

Both copies keep running when their window is not in front, so you can click between them. If the second computer gets "No answer from the server", the host's firewall is the usual cause: allow the game through it, or allow UDP port 7777. Over the internet the host also has to forward UDP port 7777 on their router; matchmaking does away with that.

### A dedicated server

Start a build with no window and no player:

```
Recoil.exe -batchmode -nographics -server -mode tdm -map crossroads -bots
```

`-mode` is one of `duel`, `tdm`, `ffa`, `elimination`, `domination`, `hardpoint`, `gungame`; `-bots` fills empty places. Players **Join by address**. Add `-logFile server.log` to choose where the log goes.

### Matchmaking

**Find match** needs the backend running (see [backend/README.md](backend/README.md)) and at least one dedicated server offered to it:

```
set RECOIL_FLEET_KEY=development-only-fleet-key-do-not-use-anywhere-real
set RECOIL_TICKET_KEY=development-only-ticket-key-do-not-use-anywhere-real
Recoil.exe -batchmode -nographics -server -fleet http://localhost:5080 -public-address 127.0.0.1
```

(Those are the development keys from the backend's settings; use your own anywhere real.) The server registers and checks in every few seconds. Signed-in players queue as themselves, everyone else as a guest. A full queue starts a match at once; otherwise, after 20 seconds, a casual match starts with whoever is waiting and bots take the other places (a Duel always waits for two people; ranked always waits for a full match). The server switches to the match's mode and map, lets in only the players matchmaking sent it, plays **one** match, reports it to the backend and sends everyone back to the menu, where a line says what the match earned. Run several servers on different `-port`s to host several matches.

### In a match

- **Warm-up** until there is someone on each side. Ammunition and utility never run out. Once there are enough players, a short "Starting in" wait lets anyone on their way arrive.
- **Countdown.** You can look around and swap weapons; movement and fire unlock when it ends.
- **Play.** Round modes end a round when one side is wiped out (or on time: more players left, then more health). Respawning modes bring you back a few seconds after you go down, away from enemies, and end at the score limit or when time runs out.
- **Changing loadout:** **B** or **Esc**. It is used from your next spawn (next round in round modes). Gun Game hands out its own weapons.
- **Shoot their gun.** A shot that lands on the weapon in someone's hands, not on them, does them no harm but may break it: the harder the shot, the likelier (a pistol round about one in five, a rifle round one in four, a sniper round two in three). You see sparks and hear it ring off; your hit marker turns pale blue. A broken weapon is gone until you are placed again (next round, or your next life), and you switch to the best one you have left. With all three broken you fight with your **fists**, which cannot break. Broken slots show red on the HUD.
- **Take their gun.** Taking someone out takes the weapon they were holding: it goes into the same slot of your loadout, new and full, in place of yours. If you were on fists, or it replaces the one in your hands, it goes straight into your hands. It is yours until you go down, so a round won carries it into the next round. Not in Gun Game, where the ladder decides what everyone carries.
- A new match starts by itself a few seconds after the result. If everyone on one side leaves, the other side wins.

On screen: scores, clock and zones at the top; your **weapons along the bottom centre** (the one in hand lit up), with the loadout's name above them; health at the bottom left; ammunition and your grenade at the bottom right; eliminations at the top right; and at the top left your ping, packet loss and a count of corrections (**F3** hides it). Hold **Tab** for the scoreboard. **Esc ▸ Leave match** returns to the menu; **Esc ▸ Settings** changes settings without leaving.

### Trying it with a bad connection

To feel the game at a given ping, make your own connection worse on purpose. Each value applies in both directions, so 60 ms of delay adds about 120 ms to your ping.

- In the Editor: select the **Duel** object in the duel scene and set **Testing ▸ Simulated Connection** before pressing Play.
- In a build: start it with, for example, `-lag 60 -jitter 10 -loss 2`.

### Command line

| Option | Effect |
| --- | --- |
| `-server` | Run only the server. `-batchmode` implies it |
| `-port N` | Port to host on. Default 7777 |
| `-mode ID`, `-map ID`, `-bots` | The rules a server started from the command line plays by |
| `-fleet URL`, `-public-address HOST` | Offer this dedicated server to matchmaking at that backend, telling players to connect to that address |
| `-host` | Go straight to hosting a match (with `-mode`, `-map`, `-bots` if given) |
| `-connect ADDRESS` | Go straight to joining, for example `-connect 192.168.1.20` |
| `-name NAME` | Player name, instead of the one in the menu |
| `-lag MS`, `-jitter MS`, `-loss PERCENT` | Make this copy's connection worse on purpose |

### What I would most like to hear about

- **The bots.** Too easy, too hard, stuck anywhere, doing anything silly?
- **The corrections counter.** It should jump a little when a round starts and then sit still while you run around. If it climbs steadily, Unity's physics is giving the client and the server different answers, and I need to know how fast it climbs and whether you can feel it.
- **Hits.** Whether shots that looked on target count, especially on a moving opponent with simulated lag on.
- **The other player.** Smooth, or jittery? Do their shots come from their weapon?
- **Anything on screen** that overlaps, is missing or reads wrong.

## Friends, parties and chat

Signed in, the **Social** panel sits beside the main menu:

- **Add a friend** by their username. They see the request and accept or decline it. Friends show whether they are offline, in the menu, in a match or on the range.
- **Parties:** invite a friend who is online; they see the invite in their panel and join. Up to five. The leader finds matches for everyone (the button says **Find match for the party**); the others follow the search automatically and land in the same match, on the same side. A party can play any casual mode whose teams are big enough for it (not Duel). **Ranked is played alone.** Cancel, for a member, leaves the party.
- **Party chat** in the panel, **match chat** in play: **Enter** or **T** to everyone, **Y** to your team. Strong language is shown as asterisks unless you turn **Filter strong language** off (Settings ▸ Gameplay); **Show chat** turns it all off.
- **Players** in the pause menu during a match lists everyone: **Mute** someone's chat for the match, **Add friend**, **Block** (hides them for good, ends any friendship, and stops their requests and invites) or **Report**: pick a reason, add a few words, and their recent chat goes with it. Reports go to a person to review.

Ranked runs in **seasons** of eight weeks. When one ends, ratings move halfway back to 1000 and the five placement matches are played again; where you finished each season is kept on the Progress screen, and the leaderboards show the current season.

## Progress and ranked

Only matches found through **Find match** count, because only a matchmade server's report is trusted. Private matches, the range and LAN games are for practice and fun.

- **XP and levels.** A match pays for finishing it (100), winning (150, or 75 for a draw), each kill (25) and headshot kill (10), each round won (30) and objective points (a quarter of them). Leaving early forfeits the finishing and winning parts. Ranked pays a quarter more. Levels go to 50; everything in the game is unlocked by level 30, about 50 good matches.
- **Unlocks.** New players carry a starter set in matchmaking: the M4A1, MP5, M17, Combat Knife and Fists, plus the first utility item and perk set. Other weapons, utility items and perk sets open with your level; attachments with the level of the weapon they fit (kills with a weapon level it up). The loadout screen marks locked items with the level they open at. You can still pick them: **on the range and in private matches everything is unlocked**, and in matchmaking a locked item is swapped for a starter.
- **Challenges.** Three a day and three a week, different for each player: kills with a kind of weapon, headshots, wins, objective points, rounds and so on. Finishing one pays extra XP straight away. Days reset at midnight UTC, weeks on Monday.
- **Ranked.** **Ranked Duel** and **Ranked Elimination (3v3)**, for accounts with a verified email. Matches are full, people only, with players near your rating (the range widens the longer you wait) and teams balanced by rating. Your rank shows after five placement matches: **Spark, Pulse, Surge, Arc, Flux, Nova, Zenith**, each but the top in three divisions. Leaving a ranked match, or not turning up, is a loss.
- **The Progress screen** (from the menu, signed in) shows your level and XP, today's and this week's challenges, what unlocks next, every weapon's level, your ranks with each ranked playlist's leaderboard, and your last ten matches.

## Sound, effects and settings

Every sound and the menu music are generated by the game itself; there are no audio files. Gunshots are built like real ones: the muzzle blast, a rifle round's supersonic crack, the gas, a low punch, the action cycling and the arena's echo, with a few takes of each so a burst never repeats. Far-off gunfire is dull and echoing, and a distant rifle's crack arrives before its boom. Bullets crack and scatter grit where they land, spent cases ring on the floor, and reloads have the magazine sliding out and seating home. Other players' shots and footsteps come from where they are, muffled behind walls, so headphones help: sprinting is loud, running is clear, and crouch-walking is nearly silent. Bullets that just miss crack past your head.

When you are hit, a red arc round the crosshair points to where it came from and keeps pointing there as you turn. Low on health, the screen edges stay red and a heartbeat plays. When you go down, a line says who got you, with what, and how much health they had left.

**Settings** (in the main menu, and in the pause menu during a match):

| Tab | What is there |
| --- | --- |
| Gameplay | Sensitivity, aim sensitivity, field of view, damage numbers, toggle sprint, camera shake |
| Video | Quality (Low, Medium, High, Ultra), display mode, frame rate limit, VSync, render scale, show frame rate |
| Audio | Master, effects, music and interface volume |

Gameplay and audio settings follow a signed-in account; video settings stay on the computer. **Low** turns off bloom, uses hard shadows and no anti-aliasing, for the most frames; **Ultra** adds high-quality bloom and SMAA. Render scale below 1 draws the world at a lower resolution while the interface stays sharp.

## Customize

**Customize** is on the main menu and in the Esc menu (on the range and in a match). Everything is free to pick for now.

Every player is a realistic soldier modelled in Blender (the scripts that build the models are in `art/blender`): a human body and face from the MakeHuman base mesh (CC0), with real eyes, eyelashes, a hairstyle of their choice (crew cut, buzz cut, shaved, side part, slicked back, mohawk, curly top or bun) and a painted skin texture (brows, lips, stubble, pores) in the chosen skin tone, dressed in a fitted combat uniform with folds, cuffs, a collar, pocket flaps and team armbands, a plate carrier with webbing, magazine, admin, radio and medical pouches and padded shoulder straps, a belt with pouches, gloves, knee and elbow pads and laced boots, with the chosen headgear and pack. Every surface has baked texture maps: the weave of the cloth with a ripstop grid and stitched hems and seams, leather boots, neoprene gloves, nylon pouches and twill webbing (from CC0 Poly Haven materials), and soft shade in the folds and under the straps and pouches. The body, uniform and kit are skinned to one skeleton, so soldiers walk, run, strafe, crouch, slide and jump without seams at the joints, aim where they look, and hold their gun in both hands. Every weapon is a real one, modelled whole at its real size (see [Weapons](#weapons)), and in first person you see your own sleeves and gloved hands closed round its grip and handguard.

- **Uniform**: the colour of your shirt and trousers. Field colours (olive drab, ranger green, coyote, khaki, graphite, black...) and brighter ones.
- **Gear**: the colour of your plate carrier, pouches, knee pads, helmet or hat, and pack.
- **Pattern** printed on the uniform: Splinter, Digital, Tiger Stripe, Diagonal, Chevrons, Honeycomb, Dotwork, Weave or Circuit.
- **Headgear**: Combat Helmet, Bare Head, Field Cap, Beanie, Headset, Boonie Hat, Helmet and Headset, or Bandana.
- **Hair**: Crew Cut, Buzz Cut, Shaved, Side Part, Slicked Back, Mohawk, Curly Top or Bun. It shows bare-headed and under a headset or bandana; helmets and hats cover it.
- **Skin tone**: nine to pick from.
- **Back**: Assault Pack, Hydration Pack, Radio Pack, Rucksack, Pack and Bedroll, or a Scarf.
- **Mix your own colour**: under the uniform, gear and skin-tone lists, three sliders (hue, saturation, brightness) make any colour at all, and you wear it as you mix it.
- **Weapon skins**: twelve (Carbon, Arctic, Woodland, Sandstorm, Tiger, Gilded, Mirror, Neon Grid, Magma, Nebula, Bubblegum, Redline) plus the factory finish. Pick **Every weapon** to skin them all, or a single weapon to give it a skin of its own. You see your skins on your own weapon in first person; others see them in your hands.

The preview in the middle shows the result and turns by itself; drag it to turn it yourself. **Randomize** rolls a new outfit (keeping your weapon skins), and **Reset to default** starts over. Choices are saved as you make them, in `cosmetics.json` beside your loadouts.

In a match everyone sees your look, and a change shows up for them straight away. Bots wear random looks. **Looks never change how anyone plays:** helmets and back items are not part of the body that bullets hit, so everyone is exactly as easy to hit whatever they wear. Coloured armbands on every player (blue for your team, red for the other) keep sides readable whatever the outfit.

## Controls

| Input | Action |
| --- | --- |
| W A S D | Move |
| Mouse | Look |
| Shift | Sprint (hold it, or set **Toggle sprint** in Settings to press once) |
| Space | Jump |
| Ctrl or C | Crouch |
| Crouch while sprinting | Slide |
| Hold Space + W at a ledge | Mantle |
| Right mouse button | Aim down sights |
| Left mouse button | Fire (hold to charge on charge weapons) |
| R | Reload |
| 1 / 2 / 3 or mouse wheel | Switch to primary / secondary / melee |
| G | Throw your grenade (or other utility item) |
| B | Quick swap: pick another loadout by number |
| Tab (hold) | Scoreboard (in a match) |
| Esc | Pause: loadouts and settings; in a match, also where you leave it |
| F5 | Reset session stats (firing range) |
| F1 | Hide or show the controls panel (firing range) |
| F3 | Shot info: what your last bullet did, and any effect or sound that failed. In a match, also the connection readout |

## Loadouts

A loadout is four things to carry and a perk set:

| Slot | What goes there |
| --- | --- |
| Primary | Assault rifles, submachine guns, shotguns, light machine guns, battle and marksman rifles, sniper rifles |
| Secondary | Pistols and machine pistols, the Sawed-Off, the RPG-7 and the M32 grenade launcher |
| Melee | Combat Knife, Machete, E-Tool, Tomahawk, Fists |
| Utility | One grenade or charge, thrown with **G** |
| Perk set | A passive bonus, such as faster reloads or a little more speed |

Press **Esc** in play to open the loadout screen. Items locked for matchmaking show the level they open at; see [Progress and ranked](#progress-and-ranked).

- **Pick one.** The list on the left is your loadouts. Each entry shows what it carries. Clicking one selects it. The first time you play there is one, ready to change.
- **Deploy** puts you back in the game carrying the selected loadout. On the range you have it at once, with full ammunition; in a match, from your next spawn.
- **Make another.** Press **New** to copy the selected loadout, then change the copy. You can keep up to ten.
- **Edit it.** The tabs across the top are Primary, Secondary, Melee, Utility and Perks. Each lists what fits that slot, grouped by class. For a weapon you can cycle its attachments.
- **Compare.** The stat bars put each weapon against the others for the same slot: the weakest primary at something sits at the left of that bar, the strongest at the right. Green and red show what attachments and the perk set add or cost.
- **Rename it** by typing in the name box and pressing Enter. **Delete** removes it (you always keep at least one).
- **Nothing to save.** Every change is written straight away and is there the next time you start the game.

Press **B** in play for the quick swap list: your loadouts, numbered, with each one's primary and secondary. Press the number and you carry it, straight away on the range and from your next spawn in a match.

Loadouts are kept in a file called `loadouts.json` in the game's save folder (your look is in `cosmetics.json` beside it); **Recoil ▸ Open Saved Loadouts Folder** in the Editor takes you to it. Delete the file to start over. If it ever becomes unreadable, the game keeps it under another name and starts over with one loadout.

Loadouts are saved on your computer. In a match the server checks the loadout you bring against its own content and replaces anything you could not have.

## What to try

The range has three areas. You spawn at the firing line facing downrange.

- **Centre: shooting lanes.** Targets at 10, 20, 35, 50 and 75 m, two of them moving, and a tight group of three off to the right for explosives and piercing shots. Each target has head, body and limb hitboxes, 100 health, and stands back up after it drops. The panel at the top right tracks accuracy, headshot rate and the time your last kill took.
- **West: movement course.** Crates to mantle (0.9 m, 1.5 m, then a 2.6 m platform that needs a jump first), a ramp to slide down, a tunnel too low to walk through, and two jump gaps, the second of which needs a sprint.
- **East: the perch.** A raised platform reached by stairs, for long shots.

Utility and perks:

- The **M67 Frag** bounces and rolls, then bursts on a 3.5-second fuse; the **RGN Impact** bursts the moment it touches anything; the **C4 Charge** sticks to the first thing it hits and goes off two seconds later; the **MK3A2 Concussion** is a wide, weaker blast. In a private match with **No explosives**, nobody carries one.
- On the range, used utility items come back after a few seconds.
- Perk sets are passive: try **Skirmisher** and watch the speed readout, or **Demolitionist** for one more grenade.

Things worth a look among the weapons:

- **Damage numbers** show what each hit did. Body hits are small and white, head hits big and gold, and the hit that finishes a target is red. A shotgun blast shows one total. Every number is a multiple of five.
- The **Remington 870**, **M1014**, **M24** and **M32** load a round at a time; fire mid-reload to cut it short. Magazine weapons drop the old magazine and seat a new one; the **RPG-7** shows no grenade until it is loaded again.
- The rifles kill with one shot to the head up close; the **M24**, **L115A3** and **M107** with one to the body, and their rounds (and the **P90**'s, the **PKM**'s and the 7.62mm rifles') carry on into a second target.
- The **M24**, **L115A3**, **M107** and **SVD Dragunov** have full-screen scopes. Fit another optic on the loadout screen to swap one for it.
- Fit a **Suppressor** and the shot goes quiet and loses its muzzle flash; the **MP5SD** is built quiet.
- Fit an optic and the iron sights fold away under it; fit an extended magazine and it is longer, a drum and it is a drum; fit a foregrip and your left hand moves to it.

## Weapons

Every weapon is a real one, with its real calibre, rate of fire, magazine and handling, and damage that follows the cartridge. Every target has 100 health. Damage below is to the body up close, then to the head; arms and legs take three quarters.

| Class | Weapons |
| --- | --- |
| Assault rifles | M4A1 (5.56mm, 35 / 105, 800 rpm, 30 rounds), AK-47 (7.62x39mm, 40 / 120, 600 rpm, 30), M16A4 (5.56mm, 35 / 105, three-round bursts, 30), FAMAS F1 (5.56mm bullpup, 35 / 105, 1,000 rpm, 25) |
| Submachine guns | MP5 (9mm, 25 / 50, 800 rpm, 30), MP5SD (suppressed 9mm, 25 / 50, 700 rpm, 30), UMP45 (.45 ACP, 35 / 70, 600 rpm, 25), P90 (5.7mm, 25 / 50, 900 rpm, 50, goes through), MAC-10 (.45 ACP, 35 / 70, 1,090 rpm, 30) |
| Shotguns | Remington 870 (pump, 9 pellets x 15, 7 shells), M1014 (semi-automatic, 9 x 15, 7), AA-12 (automatic, 9 x 10, 8), Double-Barrel (9 x 15, 2), Sawed-Off (9 x 15, 2, a secondary) |
| Light machine guns | M249 (5.56mm, 35 / 105, 800 rpm, 100-round belt), PKM (7.62x54mmR, 45 / 135, 650 rpm, 100) |
| Battle and marksman rifles | M14 EBR (7.62x51mm, 60 / 180, semi-automatic, 20), SVD Dragunov (7.62x54mmR, 65 / 195, semi-automatic, 10, 4x scope), Mk 17 SCAR-H (7.62x51mm, 45 / 135, 600 rpm, 20) |
| Sniper rifles | M24 (7.62x51mm, 100 / 200, bolt action, 5), L115A3 (.338 Lapua, 125 / 250, bolt action, 5), M107 (.50 BMG, 150 everywhere, semi-automatic, 10) |
| Pistols | M17 (9mm, 25 / 50, 17), M1911A1 (.45 ACP, 35 / 70, 7), .357 Revolver (55 / 110, 6, speedloader), Beretta 93R (9mm, 25 / 50, three-round bursts, 20), Skorpion vz. 61 (.32 ACP, 20 / 40, 850 rpm, 20) |
| Launchers | RPG-7 (150 blast, one grenade), M32 MGL (40mm, 110 blast, six rounds) |
| Melee | Combat Knife (55), Machete (70), E-Tool (80, longest reach), Tomahawk (100, slowest), Fists (35) |

Each weapon is modelled whole in Blender at its real size, from code (`art/blender/guns.py`): receivers, rails, handguards, sights, bolts and furniture, wood where the real one has wood. A model carries named points for where it is held, where the eye goes to aim, where its rail, muzzle and magazine are, so the hands (`art/blender/hands.py`) close round its grip and handguard and the attachments go where they would on the real thing. Weapon skins cover a weapon's main finish in their pattern and its grips and controls in their darker colour, at the same scale on every weapon; bare steel stays steel.

The RPG-7's grenade, 40mm grenades and the thrown items fly as their own models (in `Resources/Models/Projectiles.bytes`): rockets roll and trail smoke, grenades tumble.

Damage drops off with range for most guns (an M4A1 hit is 25 beyond about 80 m). Explosions deal less the further from the centre. Whatever reduces it, what lands is always a multiple of five.

Attachments come in six slots: sights (Red Dot, Holo, 3x Optic, 6x Scope, 10x Scope), barrels (Suppressor, Long Barrel, Compensator, Muzzle Brake, Choke), magazines (Extended, Drum, Quick), grips (Vertical, Angled, Stubby), stocks (Light, Heavy, None) and lasers (Laser Sight, Tactical Laser). Each weapon accepts what would fit the real one.

## Changing and adding content

Everything is data. Select an asset in the Project window and edit it in the Inspector. All of it lives under `Assets/_Project/Content/`.

| Folder | Assets | What they are |
| --- | --- | --- |
| `Movement/` | `DefaultMovement` | Speeds, jump, slide, mantle |
| `Weapons/` | `WPN_*`, `WeaponCatalog` | One per weapon; the catalog lists weapons and attachments |
| `Attachments/` | `ATT_*` | A slot and a list of stat changes |
| `Utilities/` | `UTL_*` | A throwable: how many, how it is thrown, what the thrown object does |
| `Perks/` | `PRK_*` | A perk set: weapon stat changes, move speed, utility bonuses |
| `Loadouts/` | `LDT_*`, `LoadoutCatalog` | Default loadouts; the catalog lists utility, perks and defaults |

To add something, create the asset from **Assets ▸ Create ▸ Recoil**, give it a unique lower-case id, and add it to the right catalog list:

- **Weapon:** add to `WeaponCatalog` ▸ Weapons, and drag the attachments it accepts into its own Attachments list.
- **Attachment:** add to `WeaponCatalog` ▸ Attachments, then to each weapon that should accept it.
- **Utility item, perk set or default loadout:** add to the matching list on `LoadoutCatalog`.

Then run **Recoil ▸ Validate Content**, which checks all of it and logs anything wrong.

A weapon or utility item needs code only if it behaves in a way none of the existing ones do. The existing behaviours are: automatic, semi-automatic, burst and charge fire; instant bullets with optional piercing; multi-pellet blasts; projectiles with optional gravity, bounces, fuse and explosion; and melee.

Removing or renaming content is safe for saved loadouts: anything a save refers to that no longer exists is swapped for a default when it loads.

## Tests

Open **Window ▸ General ▸ Test Runner**, select **EditMode** and run all. The tests cover fire rate and timing, every fire mode, both reload styles, weapon switching, attachment maths, damage, the movement maths, loadout rules, the utility belt, creating, editing and saving loadouts, the real content assets (including every Gun Game weapon), the netcode's lower layers (packet reading and writing, the connection on a line that drops, reorders and repeats packets, every message), the maps and the modes' shared rules, and cosmetics (the catalog, the rules for a look, how it is sent and saved).

The tests that play whole matches (every mode, bots, matchmaking end to end) need a stand-in for Unity's physics, so they live outside the project and were run before each commit. [ARCHITECTURE.md](docs/ARCHITECTURE.md#how-it-is-tested) says what they cover.

The backend has its own tests; see [backend/README.md](backend/README.md#tests).

## Troubleshooting

**Shots do not seem to register.** Press **F3**. The line that appears says what your last bullet did: `hit body at 10.2 m for 25`, `stopped by 'Wall North'`, or `met nothing`, and under it `fault:` if an effect, a sound or the HUD threw an error (the game carries on without it, and the Console has the details as a yellow line starting `Recoil:`). On the firing range the Console also has a `Recoil self-check:` line from the moment the scene started, saying whether a test bullet reached the nearest target. Those lines are what to send with a report.

**Red errors while playing.** The first errors of each session, each written once with where it came from, are kept in `Logs/Recoil-errors.txt` in the `game` folder (in a built game, `Recoil-errors.txt` in its save folder), and a note in the bottom corner of the screen gives the first one and the file's path. That file is the thing to send: the first error in it is usually the cause of all the others. Parts that fail to build (a soldier, the weapon effects, the arms) are left out and the game carries on without them.

**My loadout's weapons changed.** The arcade weapons were replaced by real ones. A saved loadout that names one that is gone gets the first weapon for that slot instead; pick what you want on the loadout screen. Weapon skins you chose for a removed weapon are dropped the same way.

**Hundreds of red errors, many inside `Packages/`, right after opening.** The project and your Unity version disagree about package versions. It is set up for Unity 6000.6.9f1 (see `game/Packages/manifest.json`). Open it with that version; if you already opened it with another one, close Unity, delete the `game/Library` folder and open it again with 6000.6.9f1.

**Everything is pink, or the scene looks flat and unlit.** The render pipeline did not get assigned. Run **Recoil ▸ Run Project Doctor** and read the Console. If it reports that the URP asset could not be loaded, create one with **Assets ▸ Create ▸ Rendering ▸ URP Asset (with Universal Renderer)** and assign it under **Project Settings ▸ Graphics**. The game is built to run without it too, on the Built-in pipeline.

**Pressing Play shows an empty scene.** Use **Recoil ▸ Rebuild Firing Range Scene**, or **Rebuild Duel Scene** if it was the duel scene.

**A build starts on the firing range, with no menu.** The duel scene is not first in the build. Run **Recoil ▸ Run Project Doctor**, or drag **Duel** to the top under **File ▸ Build Profiles**.

**"Could not open port 7777" when hosting.** Another copy of the game on this computer is already hosting. Join that one at `127.0.0.1`, or close it.

**No sign-in on the menu, or "Could not reach the account server".** The backend is not running, or the game is looking for it somewhere else. Start it (see [backend/README.md](backend/README.md)), or start the game with `-backend URL`. Everything offline works without it.

**The Ranked box is greyed out.** Ranked is for Duel and Elimination, signed in, with a verified email; the line beside the box says which is missing.

**A match did not count.** Only matchmade matches count, and only once the server has reported them; the menu says "still being counted" if that takes a moment. Private matches never count.

**"Could not reach matchmaking."** The backend is not running, or the game is looking for it somewhere else. Start it (see [backend/README.md](backend/README.md)), or start the game with `-backend URL`. Hosting and joining by address work without it.

**Find match searches for ever.** No dedicated server is offered to matchmaking, or they are all busy, or they were built from different code than your copy. Start one as in [Matchmaking](#matchmaking) and check its log for "Registered".

**"No answer from the server" when joining.** Nothing is hosting at that address, or a firewall is in the way. Check the address against the one on the host's screen, and allow the game (or UDP port 7777) through the host's firewall.

**"This copy of the game is a different version from the server's."** The two copies were built from different code. Rebuild so both match; the Editor counts as a copy.

**The other player stutters, or you keep being pulled back.** Look at the readout at the top left. High ping or loss means the connection (or a simulated one left switched on). A corrections count that keeps climbing on a good connection is a bug I want to hear about.

**My loadouts lost their second grenade.** Loadouts now carry one utility item. Saved loadouts keep working; pick the grenade you want on the Utility tab.

**There is only one loadout, called "Fallback".** The scene lost its link to the loadout catalog. Run **Recoil ▸ Run Project Doctor**, which reconnects it.

**A loadout changed by itself.** Something it used was removed or no longer fits, and it was repaired on load. That is by design; pick the item again.

**Keys and mouse do nothing.** Go to **Project Settings ▸ Player ▸ Other Settings ▸ Active Input Handling**, set it to **Both**, and let the Editor restart.

**No HUD, or HUD text is missing.** Check the Console for a message starting "Recoil HUD" or "Recoil Project Doctor"; it names the file that failed to load.

**A package fails to resolve.** Open **Window ▸ Package Manager** and update the package it names to the version your Editor offers.

**Compile errors.** Please send them to me as they appear in the Console. A single error stops the whole project from running, and they are quick to fix once seen.


**Effects look like plain white or coloured squares.** The effects shader (`Assets/_Project/Resources/Shaders/RecoilEffect.shader`) did not load or compile; the Console says which. The game falls back to plain colours rather than pink.

**No music in the menu.** Check the Music slider in Settings → Audio. Music only plays in the menus; in a match there are only stingers at the start and end.

**The frame rate is low.** Settings → Video: try Medium or Low, or a render scale of 0.8. Tick "Show frame rate" to see the effect.

**Sound seems to come from the wrong side.** Unity's audio follows the camera; make sure no other Audio Listener is active in the scene.


**The Social panel says to sign in, or stays empty.** Friends and parties need an account and the backend running. Party members follow the leader's search only while their game is in the main menu.

**A party member did not get into the match.** They follow the search from the menu, and their game checks in every few seconds; if they were in a match or on the range when it started, they wait for the next one. Leaving the party (or Cancel while following) ends the party's search.

## Layout

```
fps-game/
├── docs/        Architecture and roadmap
├── backend/     Accounts and matchmaking (ASP.NET Core, PostgreSQL, Redis)
└── game/        The Unity project
    └── Assets/_Project/
        ├── Shared/    Gameplay rules: movement, weapons, projectiles, damage, loadouts, maps, match rules,
        │              playlists, the cosmetic catalog, and the network layer. Runs on client and server.
        ├── Server/    The authority for a match: runs every player's inputs, judges every shot, runs the
        │              mode (Modes/) and the bots (Bots/), and offers itself to matchmaking.
        ├── Client/    Input, camera, weapon models, effects, audio, HUD, loadout screen and saves, the firing
        │              range, online play (menu, prediction, other players, zones, scoreboard), the
        │              Customize screen and how looks are drawn, and the account and matchmaking clients.
        ├── Editor/    Project Doctor.
        ├── Content/   Weapons, attachments, utility items, perk sets, default loadouts, movement.
        └── Tests/     Unit tests.
```
