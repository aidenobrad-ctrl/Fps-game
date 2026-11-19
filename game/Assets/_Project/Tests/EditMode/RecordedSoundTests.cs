using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using NUnit.Framework;
using Recoil.Client.Audio;

namespace Recoil.Tests
{
    public class RecordedSoundTests
    {
        const int Rate = 44100;

        static float[] Shot()
        {
            // A crack of noise over a falling 120 Hz boom, a second long.
            var random = new Random(5);
            var s = new float[Rate];
            for (int i = 0; i < s.Length; i++)
            {
                float t = (float)i / Rate;
                s[i] = (float)((random.NextDouble() * 2 - 1) * Math.Exp(-t / 0.01) * 0.7 + Math.Sin(2 * Math.PI * 120 * t) * Math.Exp(-t / 0.2) * 0.3);
            }
            return s;
        }

        /// <summary>How much of a sound is above a few kilohertz: what is left after subtracting a muffled copy.</summary>
        static double Treble(float[] s)
        {
            var low = (float[])s.Clone();
            RecordingProcessing.Muffle(low, 2000f, Rate);
            double sum = 0;
            for (int i = 0; i < s.Length; i++) sum += (s[i] - low[i]) * (s[i] - low[i]);
            return sum / s.Length;
        }

        [Test]
        public void Resampling_ChangesLength_AndKeepsTheSound()
        {
            float[] shot = Shot();
            float[] up = RecordingProcessing.Resample(shot, 2.0), down = RecordingProcessing.Resample(shot, 0.5);
            Assert.That(up.Length, Is.EqualTo((shot.Length - 1) / 2).Within(1), "twice the pitch, half as long");
            Assert.That(down.Length, Is.EqualTo((shot.Length - 1) * 2).Within(1), "half the pitch, twice as long");
            Assert.That(up[100], Is.EqualTo(shot[200]).Within(1e-6f), "every other sample");
            Assert.That(down[201], Is.EqualTo((shot[100] + shot[101]) / 2f).Within(1e-6f), "in between, interpolated");
            Assert.That(RecordingProcessing.ToMono(new[] { 0.2f, 0.4f, -1f, 1f }, 2), Is.EqualTo(new[] { 0.3f, 0f }).Within(1e-6f));
        }

        [Test]
        public void Suppressing_Muffles_Shortens_AndStaysInRange()
        {
            float[] shot = Shot();
            float[] quiet = RecordingProcessing.Suppress(shot, Rate);
            Assert.That(quiet.Length, Is.LessThanOrEqualTo((int)(0.55f * Rate)), "dies within about half a second");
            Assert.That(quiet.All(v => !float.IsNaN(v) && Math.Abs(v) <= 0.81f), "no NaN, under its ceiling");
            Assert.That(Math.Abs(quiet[quiet.Length - 1]), Is.LessThan(0.01f), "ends quietly");
            double before = Treble(shot) / shot.Take(quiet.Length).Max(v => Math.Abs(v)), after = Treble(quiet) / quiet.Max(v => Math.Abs(v));
            Assert.That(after, Is.LessThan(before * 0.5), "the crack is muffled");
        }

        static string Project()
        {
            string root = Environment.GetEnvironmentVariable("RECOIL_PROJECT") ?? "";
            foreach (string candidate in new[] { root, "." })
                if (Directory.Exists(Path.Combine(candidate, "Assets/_Project/Resources/Audio"))) return candidate;
            Assert.Fail("the project's Resources/Audio was not found");
            return null;
        }

        [Test]
        public void EveryRecordingAWeaponNames_IsThere_CloseAndFar_WithItsMeta()
        {
            string project = Project();
            var named = new HashSet<string>();
            foreach (string file in Directory.GetFiles(Path.Combine(project, "Assets/_Project/Content/Weapons"), "WPN_*.asset"))
            {
                string line = File.ReadLines(file).Select(l => l.Trim()).FirstOrDefault(l => l.StartsWith("recording:"));
                Assert.That(line, Is.Not.Null, Path.GetFileName(file) + " has a recording field");
                string set = line.Substring("recording:".Length).Trim();
                if (set.Length > 0) named.Add(set);
            }
            Assert.That(named.Count, Is.GreaterThan(10), "the guns name their recordings");
            foreach (string set in named)
            {
                string folder = Path.Combine(project, "Assets/_Project/Resources/Audio/Guns", set);
                foreach (string take in new[] { "near1", "near2", "far1" })
                {
                    string clip = Path.Combine(folder, take + ".ogg");
                    Assert.That(File.Exists(clip), set + "/" + take);
                    Assert.That(File.Exists(clip + ".meta"), set + "/" + take + " has its .meta");
                }
            }
            foreach (string clip in Directory.GetFiles(Path.Combine(project, "Assets/_Project/Resources/Audio"), "*.ogg", SearchOption.AllDirectories))
                Assert.That(File.Exists(clip + ".meta"), clip + " has its .meta");
        }
    }
}
