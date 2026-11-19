using System;
using System.Collections.Generic;
using UnityEngine;
using Recoil.Shared.Weapons;

namespace Recoil.Client.Audio
{
    /// <summary>
    /// Real recordings, kept under Resources/Audio: each gun's shots in Guns/&lt;set&gt;
    /// (near1, near2.. up close, far1, far2.. from a distance) and some effects in Sfx
    /// (Footstep1.., ReloadStart1.., Explosion1.. and so on). art/audio/build_sounds.py cuts
    /// them from free (CC0) libraries; art/audio/README.md says which.
    ///
    /// Every clip is turned into the synthesiser's own format here (one channel, its sample
    /// rate), pitched for the weapon and muffled or suppressed as asked, so the code that plays
    /// sounds cannot tell a recording from a synthesised one. Whatever has no recording, or
    /// fails to load, is synthesised as before.
    /// </summary>
    public static class RecordedSounds
    {
        const string GunFolder = "Audio/Guns/", EffectFolder = "Audio/Sfx/";
        const int MaxTakes = 8;

        /// <summary>How loud each recorded effect plays, matched to the synthesised sounds around it.</summary>
        static readonly Dictionary<Sfx, float> EffectVolume = new Dictionary<Sfx, float>
        {
            { Sfx.Footstep, 0.45f },
            { Sfx.ReloadStart, 0.6f },
            { Sfx.ReloadEnd, 0.65f },
            { Sfx.RoundIn, 0.55f },
            { Sfx.DryFire, 0.5f },
            { Sfx.BodyHit, 0.7f },
            { Sfx.Explosion, 1f },
        };

        static readonly Dictionary<string, float[][]> Takes = new Dictionary<string, float[][]>();
        static readonly Dictionary<Sfx, AudioClip[]> Effects = new Dictionary<Sfx, AudioClip[]>();
        static readonly Dictionary<Sfx, int> LastPicked = new Dictionary<Sfx, int>();
        static bool _warned;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics()
        {
            Takes.Clear();
            Effects.Clear();
            LastPicked.Clear();
            _warned = false;
        }

        /// <summary>
        /// A weapon's shot from its recordings, or null when it has none (launchers, melee, and
        /// any weapon whose profile names no recording).
        /// </summary>
        public static AudioClip Shot(WeaponAudioProfile profile, bool suppressed, int take, bool distant, string name)
        {
            if (profile == null || string.IsNullOrEmpty(profile.recording)) return null;
            suppressed |= profile.recordingSuppressed;
            float[][] takes = distant ? Load(GunFolder + profile.recording + "/far") : null;
            bool fromClose = takes == null || takes.Length == 0;
            if (fromClose) takes = Load(GunFolder + profile.recording + "/near");
            if (takes.Length == 0) return null;

            // More takes asked for than were recorded: a repeat is pitched a hair apart, so a burst never repeats a sound exactly.
            float pitch = Mathf.Clamp(profile.recordingPitch, 0.3f, 3f) * (1f + 0.02f * (take / takes.Length));
            float[] samples = RecordingProcessing.Resample(takes[take % takes.Length], pitch);
            if (suppressed) samples = RecordingProcessing.Suppress(samples, GunshotSynth.SampleRate);
            else if (distant && fromClose) RecordingProcessing.Muffle(samples, 2500f, GunshotSynth.SampleRate);
            return SfxSynth.FromSamples(name, samples);
        }

        /// <summary>The recorded takes of an effect, or none, in which case it is synthesised.</summary>
        public static AudioClip[] Effect(Sfx sfx)
        {
            if (Effects.TryGetValue(sfx, out AudioClip[] clips)) return clips;
            clips = Array.Empty<AudioClip>();
            if (EffectVolume.TryGetValue(sfx, out float volume))
            {
                float[][] takes = Load(EffectFolder + sfx);
                clips = new AudioClip[takes.Length];
                for (int i = 0; i < takes.Length; i++)
                {
                    RecordingProcessing.Gain(takes[i], volume);
                    clips[i] = SfxSynth.FromSamples(sfx + "Recorded" + (i + 1), takes[i]);
                }
            }
            Effects[sfx] = clips;
            return clips;
        }

        /// <summary>One of an effect's takes, never the same one twice running.</summary>
        public static AudioClip Pick(Sfx sfx, AudioClip[] clips)
        {
            if (clips.Length == 1) return clips[0];
            LastPicked.TryGetValue(sfx, out int last);
            int pick = UnityEngine.Random.Range(0, clips.Length - 1);
            if (pick >= last) pick++;
            LastPicked[sfx] = pick % clips.Length;
            return clips[LastPicked[sfx]];
        }

        /// <summary>prefix1, prefix2.. until one is missing, each as samples at the synthesiser's rate.</summary>
        static float[][] Load(string prefix)
        {
            if (Takes.TryGetValue(prefix, out float[][] cached)) return cached;
            var found = new List<float[]>();
            for (int n = 1; n <= MaxTakes; n++)
            {
                AudioClip clip = Resources.Load<AudioClip>(prefix + n);
                if (clip == null) break;
                float[] samples = Samples(clip);
                if (samples != null) found.Add(samples);
            }
            float[][] takes = found.ToArray();
            Takes[prefix] = takes;
            return takes;
        }

        static float[] Samples(AudioClip clip)
        {
            try
            {
                if (clip.loadState != AudioDataLoadState.Loaded) clip.LoadAudioData();
                var data = new float[clip.samples * clip.channels];
                if (data.Length == 0 || !clip.GetData(data, 0)) throw new InvalidOperationException("no samples could be read");
                float[] mono = RecordingProcessing.ToMono(data, clip.channels);
                return clip.frequency == GunshotSynth.SampleRate ? mono
                    : RecordingProcessing.Resample(mono, (double)clip.frequency / GunshotSynth.SampleRate);
            }
            catch (Exception e)
            {
                if (!_warned)
                {
                    _warned = true;
                    Debug.LogWarning("Recoil: the recorded sound " + clip.name + " could not be read (" + e.Message +
                                     "); its synthesised sound plays instead. Its import settings need Load Type: Decompress On Load.");
                }
                return null;
            }
        }
    }
}
