using System;
using System.Collections.Generic;
using UnityEngine;
using Recoil.Client.Settings;
using Recoil.Shared.Weapons;

namespace Recoil.Client.Audio
{
    public enum Sfx
    {
        Hit,
        Headshot,
        Kill,
        DryFire,
        ReloadStart,
        ReloadEnd,
        RoundIn,
        Swap,
        Jump,
        Land,
        Slide,
        Mantle,
        Explosion,
        Bounce,
        Throw,
        KillHeadshot,
        Footstep,
        Hurt,
        HurtHead,
        Death,
        Heartbeat,
        Whiz,
        Spawn,
        Ricochet,
        BodyHit,
        Casing,
        ShellCasing,
        /// <summary>A shot of ours rang off someone's weapon.</summary>
        WeaponHit,
        /// <summary>A weapon broke: ours, or one we shot.</summary>
        WeaponBreak,
        // Interface: menus, countdowns, the objective.
        CountdownTick,
        CountdownGo,
        ZoneCaptured,
        ZoneLost,
        ZoneMoved,
        Promote,
        UiHover,
        UiClick,
        UiBack,
        UiToggle,
        UiError,
        MatchFound,
        ChallengeDone,
    }

    /// <summary>Which volume slider a sound answers to.</summary>
    public enum AudioBus
    {
        Effects,
        Music,
        Interface,
    }

    /// <summary>
    /// Every sound effect, made once and kept: the first time one is asked for it is loaded
    /// from its recordings where it has them (see <see cref="RecordedSounds"/>: every gun, reloads,
    /// footsteps, hits, explosions), and otherwise synthesised (see <see cref="SfxSynth"/>). <see cref="Prewarm"/> makes them all up front,
    /// behind a menu, so nothing is built in the middle of a fight.
    /// </summary>
    public static class SoundBank
    {
        const int FootstepVariants = 4;
        /// <summary>How many takes of each gunshot and impact there are, so a burst never repeats one sound exactly.</summary>
        public const int ShotTakes = 3;
        const int ImpactVariants = 4;

        static AudioClip[] _clips;
        static AudioClip[] _steps, _impacts;
        static int _lastImpact = -1;
        static readonly Dictionary<string, AudioClip> Shots = new Dictionary<string, AudioClip>();
        static int _lastStep = -1;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics()
        {
            _clips = null;
            _steps = null;
            _impacts = null;
            Shots.Clear();
        }

        public static AudioBus BusOf(Sfx sfx) => sfx >= Sfx.CountdownTick ? AudioBus.Interface : AudioBus.Effects;

        /// <summary>The slider setting for a bus, 0 to 1. The master slider is applied by the listener.</summary>
        public static float Volume(AudioBus bus)
        {
            switch (bus)
            {
                case AudioBus.Music: return GameSettings.MusicVolume;
                case AudioBus.Interface: return GameSettings.InterfaceVolume;
                default: return GameSettings.EffectsVolume;
            }
        }

        public static AudioClip Get(Sfx sfx)
        {
            if (_clips == null) _clips = new AudioClip[Enum.GetValues(typeof(Sfx)).Length];
            if (sfx == Sfx.Footstep) return Footstep();
            AudioClip[] recorded = RecordedSounds.Effect(sfx);
            if (recorded.Length > 0) return RecordedSounds.Pick(sfx, recorded);
            AudioClip clip = _clips[(int)sfx];
            if (clip == null) _clips[(int)sfx] = clip = Make(sfx);
            return clip;
        }

        /// <summary>One of several footsteps, never the same one twice running.</summary>
        public static AudioClip Footstep()
        {
            AudioClip[] recorded = RecordedSounds.Effect(Sfx.Footstep);
            if (recorded.Length > 0) return RecordedSounds.Pick(Sfx.Footstep, recorded);
            if (_steps == null)
            {
                _steps = new AudioClip[FootstepVariants];
                for (int i = 0; i < FootstepVariants; i++) _steps[i] = SfxSynth.Footstep(i);
            }
            int pick = UnityEngine.Random.Range(0, FootstepVariants - 1);
            if (pick >= _lastStep) pick++;
            _lastStep = pick % FootstepVariants;
            return _steps[_lastStep];
        }

        /// <summary>
        /// A weapon's firing sound, from its audio profile and class: one of several takes,
        /// close up or as heard from far away.
        /// </summary>
        public static AudioClip Shot(WeaponBuild build, int take = 0, bool distant = false)
        {
            bool suppressed = build.Suppressed;
            take = ((take % ShotTakes) + ShotTakes) % ShotTakes;
            string key = build.Weapon.weaponId + (suppressed ? "|s" : "") + (distant ? "|far" : "") + "|" + take;
            if (!Shots.TryGetValue(key, out AudioClip clip))
            {
                clip = RecordedSounds.Shot(build.Weapon.audio, suppressed, take, distant, key)
                       ?? SfxSynth.Shot(build.Weapon, suppressed, take, distant, key);
                Shots[key] = clip;
            }
            return clip;
        }

        /// <summary>Makes a loadout's gunshots now, so the first shot of a match does not have to wait for them.</summary>
        public static void PrewarmShots(WeaponBuild build)
        {
            if (build == null || build.Weapon == null) return;
            for (int take = 0; take < ShotTakes; take++) Shot(build, take);
        }

        /// <summary>A bullet striking the level: one of several, never the same twice running.</summary>
        public static AudioClip Impact()
        {
            if (_impacts == null)
            {
                _impacts = new AudioClip[ImpactVariants];
                for (int i = 0; i < ImpactVariants; i++) _impacts[i] = SfxSynth.FromSamples("Impact" + i, GunshotSynth.Impact(i));
            }
            int pick = UnityEngine.Random.Range(0, ImpactVariants - 1);
            if (pick >= _lastImpact) pick++;
            _lastImpact = pick % ImpactVariants;
            return _impacts[_lastImpact];
        }

        /// <summary>Makes every effect now, rather than the first time each is heard.</summary>
        public static void Prewarm()
        {
            foreach (Sfx sfx in (Sfx[])Enum.GetValues(typeof(Sfx))) Get(sfx);
            Impact();
        }

        static AudioClip Make(Sfx sfx)
        {
            switch (sfx)
            {
                case Sfx.Hit: return SfxSynth.Hit();
                case Sfx.Headshot: return SfxSynth.Headshot();
                case Sfx.Kill: return SfxSynth.Kill();
                case Sfx.KillHeadshot: return SfxSynth.Chime("KillHeadshot", 0.07f, 0.22f, 0.32f, 1350f, 1800f, 2700f);
                case Sfx.DryFire: return SfxSynth.FromSamples("DryFire", GunshotSynth.DryFire(), 0.5f);
                case Sfx.ReloadStart: return SfxSynth.FromSamples("ReloadStart", GunshotSynth.MagazineOut(), 0.6f);
                case Sfx.ReloadEnd: return SfxSynth.FromSamples("ReloadEnd", GunshotSynth.MagazineIn(), 0.65f);
                case Sfx.RoundIn: return SfxSynth.FromSamples("RoundIn", GunshotSynth.RoundIn(), 0.55f);
                case Sfx.Swap: return SfxSynth.Whoosh("Swap", 0.16f, 0.16f);
                case Sfx.Jump: return SfxSynth.Thump("Jump", 0.1f, 45f, 0.25f, 0f);
                case Sfx.Land: return SfxSynth.Thump("Land", 0.16f, 28f, 0.6f, 0.5f);
                case Sfx.Slide: return SfxSynth.Whoosh("Slide", 0.45f, 0.3f);
                case Sfx.Mantle: return SfxSynth.Whoosh("Mantle", 0.2f, 0.2f);
                case Sfx.Explosion: return SfxSynth.Explosion();
                case Sfx.Bounce: return SfxSynth.Click("Bounce", 1200f, 0.05f, 0.3f);
                case Sfx.Throw: return SfxSynth.Whoosh("Throw", 0.22f, 0.3f);
                case Sfx.Hurt: return SfxSynth.Hurt(false);
                case Sfx.HurtHead: return SfxSynth.Hurt(true);
                case Sfx.Death: return SfxSynth.Death();
                case Sfx.Heartbeat: return SfxSynth.Heartbeat();
                case Sfx.Whiz: return SfxSynth.Whiz();
                case Sfx.Spawn: return SfxSynth.Spawn();
                case Sfx.Ricochet: return SfxSynth.FromSamples("Ricochet", GunshotSynth.Ricochet(0), 0.7f);
                case Sfx.BodyHit: return SfxSynth.FromSamples("BodyHit", GunshotSynth.BodyHit(0), 0.8f);
                case Sfx.Casing: return SfxSynth.FromSamples("Casing", GunshotSynth.Casing(0, false), 0.5f);
                case Sfx.ShellCasing: return SfxSynth.FromSamples("ShellCasing", GunshotSynth.Casing(0, true), 0.5f);
                case Sfx.WeaponHit: return SfxSynth.FromSamples("WeaponHit", GunshotSynth.WeaponHit(0), 0.75f);
                case Sfx.WeaponBreak: return SfxSynth.FromSamples("WeaponBreak", GunshotSynth.WeaponBreak(), 0.9f);
                case Sfx.CountdownTick: return SfxSynth.Beep("CountdownTick", 880f, 0.14f, 0.45f);
                case Sfx.CountdownGo: return SfxSynth.Beep("CountdownGo", 1320f, 0.45f, 0.5f);
                case Sfx.ZoneCaptured: return SfxSynth.Chime("ZoneCaptured", 0.1f, 0.5f, 0.35f, SfxSynth.Note(15), SfxSynth.Note(22));
                case Sfx.ZoneLost: return SfxSynth.Chime("ZoneLost", 0.12f, 0.5f, 0.35f, SfxSynth.Note(10), SfxSynth.Note(3));
                case Sfx.ZoneMoved: return SfxSynth.Chime("ZoneMoved", 0.09f, 0.4f, 0.3f, SfxSynth.Note(12), SfxSynth.Note(12), SfxSynth.Note(19));
                case Sfx.Promote: return SfxSynth.Chime("Promote", 0.06f, 0.3f, 0.3f, SfxSynth.Note(12), SfxSynth.Note(16), SfxSynth.Note(19));
                case Sfx.UiHover: return SfxSynth.Tick("UiHover", 2600f, 0.03f, 0.12f);
                case Sfx.UiClick: return SfxSynth.Chime("UiClick", 0.03f, 0.08f, 0.25f, 1200f, 1800f);
                case Sfx.UiBack: return SfxSynth.Chime("UiBack", 0.03f, 0.08f, 0.25f, 1500f, 1000f);
                case Sfx.UiToggle: return SfxSynth.Tick("UiToggle", 1500f, 0.05f, 0.3f);
                case Sfx.UiError: return SfxSynth.Buzz("UiError");
                case Sfx.MatchFound: return SfxSynth.Chime("MatchFound", 0.11f, 0.7f, 0.35f, SfxSynth.Note(5), SfxSynth.Note(12), SfxSynth.Note(17));
                case Sfx.ChallengeDone: return SfxSynth.Chime("ChallengeDone", 0.08f, 0.6f, 0.3f, SfxSynth.Note(7), SfxSynth.Note(11), SfxSynth.Note(14), SfxSynth.Note(19));
                default: return null;
            }
        }
    }
}
