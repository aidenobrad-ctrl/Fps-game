using System;
using System.Linq;
using NUnit.Framework;
using Recoil.Client.Audio;
using Recoil.Shared.Match;
using Recoil.Shared.Weapons;
using UnityEngine;

namespace Recoil.Tests
{
    public class SoundSynthTests
    {
        static WeaponAudioProfile Profile(float pitch, float weight, float tail) =>
            new WeaponAudioProfile { pitch = pitch, weight = weight, tail = tail };

        static void Clean(string name, float[] samples)
        {
            Assert.That(samples.All(s => !float.IsNaN(s) && Mathf.Abs(s) <= 1f), name + ": no NaN, never past full scale");
            Assert.That(samples.Max(s => Mathf.Abs(s)), Is.GreaterThan(0.5f), name + " is loud enough");
            Assert.That(Mathf.Abs(samples.Average()), Is.LessThan(0.01f), name + " has no offset");
            Assert.That(Mathf.Abs(samples[samples.Length - 1]), Is.LessThan(0.01f), name + " ends quietly");
        }

        static float Rms(float[] s, float fromSeconds, float toSeconds)
        {
            int from = (int)(fromSeconds * GunshotSynth.SampleRate), to = Math.Min(s.Length, (int)(toSeconds * GunshotSynth.SampleRate));
            double sum = 0;
            for (int i = from; i < to; i++) sum += s[i] * s[i];
            return (float)Math.Sqrt(sum / Math.Max(1, to - from));
        }

        [Test]
        public void Gunshots_AreClean_DifferEachTake_AndTheArenaAnswers()
        {
            foreach (WeaponClass weaponClass in new[] { WeaponClass.AssaultRifle, WeaponClass.Sniper, WeaponClass.Shotgun, WeaponClass.Pistol, WeaponClass.Smg })
            {
                GunshotRecipe recipe = GunshotSynth.Recipe(Profile(1f, 1f, 0.3f), weaponClass, FireMode.Automatic, false);
                float[] first = GunshotSynth.Render(recipe, 0, false), second = GunshotSynth.Render(recipe, 1, false);
                Clean(weaponClass.ToString(), first);
                Clean(weaponClass + " far", GunshotSynth.Render(recipe, 0, true));
                Clean(weaponClass + " suppressed", GunshotSynth.Render(GunshotSynth.Recipe(Profile(1f, 1f, 0.3f), weaponClass, FireMode.Automatic, true), 0, false));
                Assert.That(first.SequenceEqual(second), Is.False, weaponClass + ": takes differ");
                Assert.That(Rms(first, 0.25f, 0.5f), Is.GreaterThan(0.002f), weaponClass + ": a tail of echo");
            }
        }

        [Test]
        public void FarAway_ARiflesCrack_ComesWellBeforeItsBoom()
        {
            float[] far = GunshotSynth.Render(GunshotSynth.Recipe(Profile(1f, 1f, 0.25f), WeaponClass.AssaultRifle, FireMode.Automatic, false), 0, true);
            Assert.That(Rms(far, 0.07f, 0.12f), Is.GreaterThan(Rms(far, 0.02f, 0.06f) * 2f));
        }

        [Test]
        public void TheSoundsAroundAShot_AreClean()
        {
            Clean("impact", GunshotSynth.Impact(0));
            Clean("ricochet", GunshotSynth.Ricochet(0));
            Clean("body hit", GunshotSynth.BodyHit(0));
            Clean("casing", GunshotSynth.Casing(0, false));
            Clean("shell", GunshotSynth.Casing(0, true));
            Clean("magazine out", GunshotSynth.MagazineOut());
            Clean("magazine in", GunshotSynth.MagazineIn());
            Clean("round in", GunshotSynth.RoundIn());
            Clean("dry fire", GunshotSynth.DryFire());
        }
    }
}
