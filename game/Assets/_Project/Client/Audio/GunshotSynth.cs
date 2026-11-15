using System;
using UnityEngine;
using Recoil.Shared.Weapons;

namespace Recoil.Client.Audio
{
    /// <summary>What goes into one weapon's report, worked out from its audio profile and class.</summary>
    public struct GunshotRecipe
    {
        /// <summary>Length of the muzzle blast's pressure pulse, in seconds. Longer is deeper and bigger.</summary>
        public float BlastLength;
        public float Blast;
        /// <summary>The supersonic bullet's crack, 0 for a subsonic round.</summary>
        public float Crack;
        /// <summary>The roar of the propellant gas leaving the muzzle, and how long it lasts.</summary>
        public float Gas, GasDecay, GasCutoff;
        /// <summary>The low punch felt in the chest, and where it sits.</summary>
        public float Body, BodyHz;
        /// <summary>The action cycling: a bolt or a slide slamming back and forward.</summary>
        public float Mechanism, MechanismDelay, MechanismHz;
        public bool SecondMechanism;
        /// <summary>How much of the arena answers back, and for how long.</summary>
        public float Room, RoomDecay;
        public float Drive;
        public bool Suppressed;
    }

    /// <summary>
    /// Gunshots, impacts and the small sounds around them, built the way the real ones are
    /// made rather than from a single burst of noise:
    ///
    ///  * the muzzle blast, a pressure pulse that leaps up and falls back past zero (a
    ///    Friedlander wave), whose length sets how big the gun sounds;
    ///  * for a rifle round, the bullet's own supersonic crack, a short N-shaped wave;
    ///  * the roar of the propellant gas, and a low punch that falls in pitch;
    ///  * the action cycling a moment later;
    ///  * the arena answering: a handful of early echoes off the nearest walls and a diffuse
    ///    tail, from four damped comb filters and two all-pass filters.
    ///
    /// Far away, the top end goes and the room takes over, and a rifle's crack arrives well
    /// before its boom, because the bullet outruns the sound of the gun.
    ///
    /// Everything here is plain arithmetic on arrays, so it is the same in the game and in
    /// tests.
    /// </summary>
    public static class GunshotSynth
    {
        public const int SampleRate = 44100;
        const float Tau = 2f * Mathf.PI;

        // ------------------------------------------------------------------ recipes

        public static GunshotRecipe Recipe(WeaponAudioProfile profile, WeaponClass weaponClass, FireMode fireMode, bool suppressed)
        {
            float pitch = Mathf.Clamp(profile.pitch, 0.4f, 2f);
            float weight = Mathf.Clamp(profile.weight, 0f, 1.5f);
            float size = 1f / pitch;

            var r = new GunshotRecipe
            {
                BlastLength = 0.00075f * Mathf.Pow(size, 1.4f) * (0.75f + 0.25f * weight),
                Blast = 1f,
                Gas = 0.55f,
                GasDecay = 0.018f + 0.02f * weight * size,
                GasCutoff = Mathf.Clamp(5200f * pitch, 2400f, 9000f),
                Body = 0.35f + 0.35f * weight,
                BodyHz = Mathf.Clamp(95f * pitch, 55f, 150f),
                Room = 0.55f,
                RoomDecay = Mathf.Clamp(0.55f + profile.tail * 1.4f, 0.5f, 1.5f),
                Drive = 1.6f + 0.6f * weight,
                Suppressed = suppressed,
            };

            switch (weaponClass)
            {
                case WeaponClass.AssaultRifle: r.Crack = 0.7f; break;
                case WeaponClass.Lmg: r.Crack = 0.8f; r.Body *= 1.1f; break;
                case WeaponClass.Marksman: r.Crack = 0.9f; break;
                case WeaponClass.Sniper: r.Crack = 1f; r.Body *= 1.2f; r.RoomDecay *= 1.15f; break;
                case WeaponClass.Shotgun:
                    // A wide bore and a big charge: a long, round blast and no crack.
                    r.BlastLength *= 1.5f;
                    r.Gas = 0.8f;
                    r.GasDecay *= 1.4f;
                    r.GasCutoff *= 0.75f;
                    r.Body *= 1.25f;
                    break;
                case WeaponClass.Pistol:
                    r.Crack = pitch < 0.9f ? 0.35f : 0f;   // a magnum cracks a little
                    r.Room *= 0.9f;
                    break;
                case WeaponClass.Smg:
                    r.Gas *= 0.9f;
                    break;
            }

            // The action: bolts on automatics, slides on pistols, little else on the rest.
            switch (weaponClass)
            {
                case WeaponClass.Pistol:
                    r.Mechanism = 0.22f; r.MechanismDelay = 0.011f; r.MechanismHz = 2600f;
                    break;
                case WeaponClass.Shotgun:
                    r.Mechanism = fireMode == FireMode.Automatic ? 0.2f : 0.1f; r.MechanismDelay = 0.03f; r.MechanismHz = 1500f;
                    break;
                case WeaponClass.Sniper:
                    r.Mechanism = 0.06f; r.MechanismDelay = 0.03f; r.MechanismHz = 1800f;
                    break;
                default:
                    r.Mechanism = fireMode == FireMode.Automatic || fireMode == FireMode.Burst ? 0.2f : 0.14f;
                    r.MechanismDelay = 0.024f + 0.01f * size;
                    r.MechanismHz = 2100f * Mathf.Sqrt(pitch);
                    r.SecondMechanism = true;
                    break;
            }

            if (suppressed)
            {
                // The can swallows the blast and the gas; what is left is a dull cough, the
                // action clattering, and the bullet's crack if it is still supersonic.
                r.Blast = 0.32f;
                r.BlastLength *= 1.8f;
                r.Gas *= 0.35f;
                r.GasDecay *= 0.6f;
                r.GasCutoff = 1500f;
                r.Body *= 0.45f;
                r.Crack *= 0.35f;
                r.Mechanism = Mathf.Max(r.Mechanism, 0.16f) * 1.6f;
                r.Room *= 0.45f;
                r.RoomDecay *= 0.7f;
                r.Drive = 1.2f;
            }
            return r;
        }

        // ------------------------------------------------------------------ the shot

        /// <summary>Renders a report. <paramref name="seed"/> picks one of several takes, so repeated shots never sound identical.</summary>
        /// <param name="distant">As heard from far off: dull, mostly room, the crack well ahead of the boom.</param>
        public static float[] Render(in GunshotRecipe recipe, int seed, bool distant)
        {
            var random = new System.Random(1009 + seed * 7919);
            float Vary(float amount) => 1f + ((float)random.NextDouble() * 2f - 1f) * amount;

            float rt60 = recipe.RoomDecay * (distant ? 1.35f : 1f);
            float seconds = Mathf.Clamp(rt60 * 0.85f + (distant ? 0.12f : 0.04f), 0.3f, 1.8f);
            int count = Mathf.RoundToInt(seconds * SampleRate);
            var dry = new float[count];

            // Far off, the bullet's crack arrives first and the gun's boom some way behind it.
            float blastAt = 0.0004f + (distant && recipe.Crack > 0f ? 0.07f : 0f);

            AddCrack(dry, recipe.Crack * (distant ? 0.7f : 0.85f), 0.0002f, 0.00032f * Vary(0.1f));
            AddBlast(dry, recipe.Blast * 1.7f, blastAt, recipe.BlastLength * Vary(0.08f));
            AddGas(dry, random, recipe.Gas, blastAt, recipe.GasDecay * Vary(0.1f), recipe.GasCutoff);
            AddBody(dry, recipe.Body, blastAt, recipe.BodyHz * Vary(0.05f));
            if (recipe.Mechanism > 0f && !distant)
            {
                float at = blastAt + recipe.MechanismDelay * Vary(0.12f);
                AddClack(dry, random, recipe.Mechanism, at, recipe.MechanismHz * Vary(0.06f));
                if (recipe.SecondMechanism) AddClack(dry, random, recipe.Mechanism * 0.6f, at + 0.022f * Vary(0.15f), recipe.MechanismHz * 1.27f * Vary(0.06f));
            }

            if (recipe.Suppressed) OnePoleLowPass(dry, 2600f, 0, count);
            if (distant)
            {
                // Air and distance take the top off everything but the crack's first instant.
                int keep = Mathf.RoundToInt((blastAt - 0.01f) * SampleRate);
                OnePoleLowPass(dry, 1300f, Mathf.Max(0, keep), count);
                OnePoleLowPass(dry, 1300f, Mathf.Max(0, keep), count);
                for (int i = 0; i < count; i++) dry[i] *= 0.6f;
            }

            float[] wet = Room(dry, distant ? recipe.Room * 1.6f : recipe.Room, rt60, random);
            Finish(wet, recipe.Drive);
            return wet;
        }

        /// <summary>The supersonic crack: a pressure jump that falls straight through zero and snaps back, a fraction of a millisecond long.</summary>
        static void AddCrack(float[] into, float amount, float at, float length)
        {
            if (amount <= 0f) return;
            int start = Mathf.RoundToInt(at * SampleRate);
            int samples = Mathf.Max(4, Mathf.RoundToInt(length * SampleRate));
            // Rendered on its own and softened a little: a real crack is sharp, but its energy sits below about 10 kHz.
            var crack = new float[samples + 64];
            for (int i = 0; i <= samples; i++) crack[i] = amount * 1.4f * (1f - 2f * i / (float)samples);
            OnePoleLowPass(crack, 9000f, 0, crack.Length);
            OnePoleLowPass(crack, 9000f, 0, crack.Length);
            for (int i = 0; i < crack.Length && start + i < into.Length; i++) into[start + i] += crack[i];
        }

        /// <summary>
        /// The muzzle blast as a Friedlander wave: an instant rise, a fall past zero after
        /// <paramref name="length"/>, then a long shallow suck back.
        /// </summary>
        static void AddBlast(float[] into, float amount, float at, float length)
        {
            if (amount <= 0f) return;
            int start = Mathf.RoundToInt(at * SampleRate);
            int samples = Mathf.Min(into.Length - start, Mathf.RoundToInt(length * 14f * SampleRate));
            for (int i = 0; i < samples; i++)
            {
                float tau = i / (float)SampleRate / length;
                into[start + i] += amount * (1f - tau) * Mathf.Exp(-1.8f * tau);
            }
        }

        /// <summary>The propellant gas: noise with a quick swell and a fast fall, strongest in the middle of the range.</summary>
        static void AddGas(float[] into, System.Random random, float amount, float at, float decay, float cutoff)
        {
            if (amount <= 0f) return;
            int start = Mathf.RoundToInt(at * SampleRate);
            int samples = Mathf.Min(into.Length - start, Mathf.RoundToInt(decay * 7f * SampleRate));
            float low = 0f, low2 = 0f, under = 0f, slow = 0f, slow2 = 0f;
            float a = Coefficient(cutoff), b = Coefficient(220f), c = Coefficient(420f);
            for (int i = 0; i < samples; i++)
            {
                float t = i / (float)SampleRate;
                float noise = (float)random.NextDouble() * 2f - 1f;
                low += (noise - low) * a;
                low2 += (low - low2) * a;            // two poles: the top falls away properly
                under += (low2 - under) * b;         // and the very bottom is left to the punch
                slow += (noise - slow) * c;
                slow2 += (slow - slow2) * c;         // a darker roar underneath, around 150-400 Hz
                float swell = Mathf.Min(1f, t / 0.0006f);
                float envelope = swell * Mathf.Exp(-t / decay);
                float roar = slow2 * 5f * swell * Mathf.Exp(-t / (decay * 1.6f));
                into[start + i] += amount * ((low2 - under) * 2.4f * envelope + roar);
            }
        }

        /// <summary>The punch: a low tone that drops in pitch as it dies.</summary>
        static void AddBody(float[] into, float amount, float at, float hz)
        {
            if (amount <= 0f) return;
            int start = Mathf.RoundToInt(at * SampleRate);
            int samples = Mathf.Min(into.Length - start, Mathf.RoundToInt(0.22f * SampleRate));
            float phase = 0f;
            for (int i = 0; i < samples; i++)
            {
                float t = i / (float)SampleRate;
                float f = hz * (1f + 1.2f * Mathf.Exp(-t / 0.01f));
                phase += Tau * f / SampleRate;
                into[start + i] += amount * 0.3f * Mathf.Sin(phase) * Mathf.Exp(-t / 0.035f) * Mathf.Min(1f, t / 0.0015f);
            }
        }

        /// <summary>Metal on metal: a click of noise and a few inharmonic partials ringing briefly.</summary>
        static void AddClack(float[] into, System.Random random, float amount, float at, float hz)
        {
            int start = Mathf.RoundToInt(at * SampleRate);
            if (start >= into.Length) return;
            int samples = Mathf.Min(into.Length - start, Mathf.RoundToInt(0.06f * SampleRate));
            float[] ratios = { 1f, 1.59f, 2.43f, 3.71f };
            float[] decays = { 0.014f, 0.01f, 0.007f, 0.005f };
            float high = 0f;
            for (int i = 0; i < samples; i++)
            {
                float t = i / (float)SampleRate;
                float noise = (float)random.NextDouble() * 2f - 1f;
                high += (noise - high) * 0.5f;
                float click = (noise - high) * Mathf.Exp(-t / 0.0012f) * 0.9f;
                float ring = 0f;
                for (int p = 0; p < ratios.Length; p++)
                    ring += Mathf.Sin(Tau * hz * ratios[p] * t) * Mathf.Exp(-t / decays[p]) / (p + 1f);
                into[start + i] += amount * (click + ring * 0.6f);
            }
        }

        // ------------------------------------------------------------------ the arena

        /// <summary>
        /// Adds the space the shot happens in: early echoes off the nearest walls, then a
        /// diffuse tail lasting <paramref name="rt60"/> seconds (the time to fall by 60 dB).
        /// </summary>
        public static float[] Room(float[] dry, float mix, float rt60, System.Random random)
        {
            int count = dry.Length;
            var output = new float[count];
            Array.Copy(dry, output, count);
            if (mix <= 0f) return output;

            // Early reflections, each a little duller than the last.
            float[] dull = (float[])dry.Clone();
            OnePoleLowPass(dull, 3500f, 0, count);
            float[] delays = { 0.0093f, 0.0131f, 0.0187f, 0.0262f, 0.0339f, 0.0468f };
            float[] gains = { 0.36f, 0.29f, 0.22f, 0.17f, 0.13f, 0.1f };
            for (int tap = 0; tap < delays.Length; tap++)
            {
                int delay = Mathf.RoundToInt(delays[tap] * (0.92f + 0.16f * (float)random.NextDouble()) * SampleRate);
                float gain = gains[tap] * mix * (tap % 2 == 0 ? 1f : -1f);
                for (int i = delay; i < count; i++) output[i] += dull[i - delay] * gain;
            }

            // The tail: four damped combs in parallel, then two all-passes to smear them.
            int preDelay = Mathf.RoundToInt(0.014f * SampleRate);
            int[] combs = { 1116, 1188, 1277, 1356 };
            var tail = new float[count];
            foreach (int length in combs)
            {
                float feedback = Mathf.Pow(10f, -3f * length / (rt60 * SampleRate));
                var line = new float[length];
                int index = 0;
                float store = 0f;
                const float damp = 0.32f;
                for (int i = 0; i < count; i++)
                {
                    float input = i >= preDelay ? dull[i - preDelay] : 0f;
                    float delayed = line[index];
                    store = Flush(delayed * (1f - damp) + store * damp);
                    line[index] = input + store * feedback;
                    if (++index == length) index = 0;
                    tail[i] += delayed;
                }
            }
            AllPass(tail, 556, 0.5f);
            AllPass(tail, 441, 0.5f);
            float level = mix * 0.2f;
            for (int i = 0; i < count; i++) output[i] += tail[i] * level;
            return output;
        }

        static void AllPass(float[] signal, int length, float gain)
        {
            var line = new float[length];
            int index = 0;
            for (int i = 0; i < signal.Length; i++)
            {
                float delayed = line[index];
                float input = signal[i];
                line[index] = Flush(input + delayed * gain);
                signal[i] = delayed - input * gain;
                if (++index == length) index = 0;
            }
        }

        // ------------------------------------------------------------------ around the shot

        /// <summary>A bullet striking concrete: a hard snap, then grit and chips scattering.</summary>
        public static float[] Impact(int seed)
        {
            var random = new System.Random(311 + seed * 37);
            int count = Mathf.RoundToInt(0.32f * SampleRate);
            var dry = new float[count];

            // The snap: a short burst, strongest between about 1 and 6 kHz.
            float top = 0f, bottom = 0f;
            float ta = Coefficient(6000f), tb = Coefficient(900f);
            for (int i = 0; i < Mathf.RoundToInt(0.008f * SampleRate); i++)
            {
                float t = i / (float)SampleRate;
                float noise = (float)random.NextDouble() * 2f - 1f;
                top += (noise - top) * ta;
                bottom += (top - bottom) * tb;
                dry[i] += (top - bottom) * 3f * Mathf.Exp(-t / 0.0022f);
            }
            AddBody(dry, 0.3f, 0f, 240f + 80f * (float)random.NextDouble());

            // Debris: many tiny grains, thick at first and thinning out.
            int grains = 26 + random.Next(14);
            for (int g = 0; g < grains; g++)
            {
                float u = (float)random.NextDouble();
                float at = 0.002f + 0.14f * u * u;
                float amount = 0.6f * (1f - u) * (0.4f + 0.6f * (float)random.NextDouble());
                int start = Mathf.RoundToInt(at * SampleRate);
                int length = Mathf.RoundToInt((0.0008f + 0.0025f * (float)random.NextDouble()) * SampleRate);
                float hi = 0f, lo = 0f;
                float ga = Coefficient(8000f), gb = Coefficient(1500f);
                for (int i = 0; i < length && start + i < count; i++)
                {
                    float noise = (float)random.NextDouble() * 2f - 1f;
                    hi += (noise - hi) * ga;
                    lo += (hi - lo) * gb;
                    dry[start + i] += (hi - lo) * amount * 2f * Mathf.Exp(-i / (length * 0.35f));
                }
            }

            float[] wet = Room(dry, 0.35f, 0.45f, random);
            Finish(wet, 1.4f);
            return wet;
        }

        /// <summary>A round glancing off: a short snap and a falling whine.</summary>
        public static float[] Ricochet(int seed)
        {
            var random = new System.Random(733 + seed * 13);
            int count = Mathf.RoundToInt(0.55f * SampleRate);
            var dry = new float[count];
            AddCrack(dry, 0.5f, 0f, 0.0003f);
            float from = 3600f + 1400f * (float)random.NextDouble(), to = from * (0.45f + 0.1f * (float)random.NextDouble());
            float phase = 0f;
            for (int i = 0; i < count; i++)
            {
                float t = i / (float)SampleRate;
                float progress = t / 0.45f;
                float f = Mathf.Lerp(from, to, Mathf.Sqrt(Mathf.Clamp01(progress))) * (1f + 0.012f * Mathf.Sin(Tau * 38f * t));
                phase += Tau * f / SampleRate;
                float envelope = Mathf.Min(1f, t / 0.012f) * Mathf.Exp(-t / 0.16f);
                float noise = ((float)random.NextDouble() * 2f - 1f) * 0.15f;
                dry[i] += (Mathf.Sin(phase) + noise) * 0.32f * envelope;
            }
            float[] wet = Room(dry, 0.3f, 0.5f, random);
            Finish(wet, 1.2f);
            return wet;
        }

        /// <summary>A round striking someone: a dull, wet smack.</summary>
        public static float[] BodyHit(int seed)
        {
            var random = new System.Random(911 + seed * 29);
            int count = Mathf.RoundToInt(0.16f * SampleRate);
            var dry = new float[count];
            AddBody(dry, 0.9f, 0f, 105f + 20f * (float)random.NextDouble());
            float low = 0f, lower = 0f;
            for (int i = 0; i < count; i++)
            {
                float t = i / (float)SampleRate;
                float noise = (float)random.NextDouble() * 2f - 1f;
                low += (noise - low) * Coefficient(1900f);
                lower += (low - lower) * Coefficient(380f);
                dry[i] += (low - lower) * 2.2f * Mathf.Min(1f, t / 0.0008f) * Mathf.Exp(-t / 0.018f);
            }
            Finish(dry, 1.5f);
            return dry;
        }

        /// <summary>A spent case hitting the floor and bouncing: brass rings, a shotgun hull thuds.</summary>
        public static float[] Casing(int seed, bool shell)
        {
            var random = new System.Random(1301 + seed * 53);
            int count = Mathf.RoundToInt(0.5f * SampleRate);
            var dry = new float[count];
            float[] bounces = { 0f, 0.105f, 0.18f, 0.235f, 0.272f, 0.298f };
            float baseHz = shell ? 1150f : 3100f + 600f * (float)random.NextDouble();
            float[] ratios = shell ? new[] { 1f, 1.83f } : new[] { 1f, 1.93f, 2.71f, 3.32f };
            float ringFor = shell ? 0.012f : 0.05f;
            for (int b = 0; b < bounces.Length; b++)
            {
                float amount = 0.5f * Mathf.Pow(0.62f, b) * (0.8f + 0.4f * (float)random.NextDouble());
                int start = Mathf.RoundToInt((bounces[b] + 0.008f * (float)random.NextDouble()) * SampleRate);
                int length = Mathf.RoundToInt(ringFor * 5f * SampleRate);
                float detune = 1f + 0.02f * ((float)random.NextDouble() - 0.5f);
                for (int i = 0; i < length && start + i < count; i++)
                {
                    float t = i / (float)SampleRate;
                    float ring = 0f;
                    for (int p = 0; p < ratios.Length; p++)
                        ring += Mathf.Sin(Tau * baseHz * ratios[p] * detune * t) * Mathf.Exp(-t / (ringFor / (1f + p * 0.6f))) / (p + 1f);
                    float tick = ((float)random.NextDouble() * 2f - 1f) * Mathf.Exp(-t / 0.0006f);
                    dry[start + i] += amount * (ring * 0.7f + tick * 0.5f);
                }
            }
            Finish(dry, 1.1f);
            for (int i = 0; i < count; i++) dry[i] *= 0.7f;
            return dry;
        }

        /// <summary>Magazine out: the release clicks, the magazine slides free.</summary>
        public static float[] MagazineOut()
        {
            var random = new System.Random(1601);
            int count = Mathf.RoundToInt(0.3f * SampleRate);
            var dry = new float[count];
            AddClack(dry, random, 0.45f, 0f, 2400f);
            Friction(dry, random, 0.02f, 0.12f, 0.22f, 2200f);
            AddClack(dry, random, 0.18f, 0.15f, 1700f);
            Finish(dry, 1.3f);
            return dry;
        }

        /// <summary>Magazine in and the charging handle: a slide, a firm seat, then back and forward.</summary>
        public static float[] MagazineIn()
        {
            var random = new System.Random(1607);
            int count = Mathf.RoundToInt(0.42f * SampleRate);
            var dry = new float[count];
            Friction(dry, random, 0f, 0.07f, 0.16f, 2000f);
            AddClack(dry, random, 0.7f, 0.075f, 1500f);
            AddBody(dry, 0.25f, 0.075f, 180f);
            AddClack(dry, random, 0.5f, 0.24f, 2300f);
            Friction(dry, random, 0.25f, 0.05f, 0.1f, 3000f);
            AddClack(dry, random, 0.75f, 0.31f, 2000f);
            Finish(dry, 1.4f);
            return dry;
        }

        /// <summary>A single round or shell pushed home.</summary>
        public static float[] RoundIn()
        {
            var random = new System.Random(1613);
            int count = Mathf.RoundToInt(0.12f * SampleRate);
            var dry = new float[count];
            Friction(dry, random, 0f, 0.03f, 0.12f, 1800f);
            AddClack(dry, random, 0.45f, 0.03f, 1300f);
            AddBody(dry, 0.18f, 0.03f, 220f);
            Finish(dry, 1.3f);
            return dry;
        }

        /// <summary>The hammer falling on nothing.</summary>
        public static float[] DryFire()
        {
            var random = new System.Random(1619);
            int count = Mathf.RoundToInt(0.08f * SampleRate);
            var dry = new float[count];
            AddClack(dry, random, 0.6f, 0f, 2900f);
            Finish(dry, 1.2f);
            return dry;
        }

        /// <summary>Metal sliding on metal: band-limited noise under a short envelope.</summary>
        static void Friction(float[] into, System.Random random, float at, float length, float amount, float hz)
        {
            int start = Mathf.RoundToInt(at * SampleRate);
            int samples = Mathf.RoundToInt(length * SampleRate);
            float low = 0f, lower = 0f;
            float a = Coefficient(hz * 1.8f), b = Coefficient(hz * 0.5f);
            for (int i = 0; i < samples && start + i < into.Length; i++)
            {
                float noise = (float)random.NextDouble() * 2f - 1f;
                low += (noise - low) * a;
                lower += (low - lower) * b;
                float envelope = Mathf.Sin(Mathf.PI * i / samples);
                into[start + i] += (low - lower) * amount * 2.5f * envelope * (0.7f + 0.3f * Mathf.Sin(i * 0.013f));
            }
        }

        // ------------------------------------------------------------------ finishing

        /// <summary>Takes out any DC, saturates gently for loudness, and scales to just under full.</summary>
        public static void Finish(float[] signal, float drive)
        {
            // DC blocker: a blast's pressure pulse does not sum to zero, and a speaker cannot hold an offset.
            float previousIn = 0f, previousOut = 0f;
            const float pole = 0.9975f;
            for (int i = 0; i < signal.Length; i++)
            {
                float input = signal[i];
                float output = Flush(input - previousIn + pole * previousOut);
                previousIn = input;
                previousOut = output;
                signal[i] = output;
            }

            float peak = 0f;
            for (int i = 0; i < signal.Length; i++) peak = Mathf.Max(peak, Mathf.Abs(signal[i]));
            if (peak <= 1e-6f) return;
            float norm = (float)Math.Tanh(drive);
            for (int i = 0; i < signal.Length; i++) signal[i] = (float)Math.Tanh(drive * signal[i] / peak) / norm * 0.95f;

            // A short fade so nothing ends on a click.
            int fade = Mathf.Min(256, signal.Length);
            for (int i = 0; i < fade; i++) signal[signal.Length - 1 - i] *= i / (float)fade;
        }

        static void OnePoleLowPass(float[] signal, float cutoff, int from, int to)
        {
            float a = Coefficient(cutoff);
            float state = from > 0 ? signal[from - 1] : 0f;
            for (int i = from; i < to; i++)
            {
                state = Flush(state + (signal[i] - state) * a);
                signal[i] = state;
            }
        }

        /// <summary>
        /// Zero for anything vanishingly small. A filter's memory decays towards zero forever,
        /// and once it is tiny enough the processor slows to a crawl working with it.
        /// </summary>
        static float Flush(float x) => x > -1e-20f && x < 1e-20f ? 0f : x;

        /// <summary>The smoothing factor of a one-pole low-pass at <paramref name="cutoff"/> Hz.</summary>
        static float Coefficient(float cutoff) => 1f - Mathf.Exp(-Tau * cutoff / SampleRate);
    }
}
