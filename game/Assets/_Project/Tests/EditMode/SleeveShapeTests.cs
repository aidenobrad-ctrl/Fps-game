using NUnit.Framework;
using UnityEngine;
using Recoil.Client.Weapons;

namespace Recoil.Tests
{
    public class SleeveShapeTests
    {
        static void IsClosedAndFacesOut(SleeveShape.Geometry g, float length, string what)
        {
            int outward = 0, inward = 0;
            for (int i = 0; i + 2 < g.Triangles.Length; i += 3)
            {
                Vector3 a = g.Vertices[g.Triangles[i]], b = g.Vertices[g.Triangles[i + 1]], c = g.Vertices[g.Triangles[i + 2]];
                Vector3 normal = g.Normals[g.Triangles[i]] + g.Normals[g.Triangles[i + 1]] + g.Normals[g.Triangles[i + 2]];
                float facing = Vector3.Dot(Vector3.Cross(b - a, c - a), normal);
                if (facing > 1e-12f) outward++;
                else if (facing < -1e-12f) inward++;
            }
            Assert.That(inward, Is.EqualTo(0), what + ": every triangle faces out, as Unity draws them");
            Assert.That(outward, Is.GreaterThan(200), what);
            foreach (Vector3 n in g.Normals) Assert.That(Mathf.Abs(n.magnitude - 1f), Is.LessThan(1e-3f), what + " normals");

            // Closed at both ends: the profile starts and ends on the axis.
            float minZ = float.MaxValue, maxZ = float.MinValue;
            foreach (Vector3 v in g.Vertices)
            {
                minZ = Mathf.Min(minZ, v.z);
                maxZ = Mathf.Max(maxZ, v.z);
            }
            Vector3 first = g.Vertices[0], last = g.Vertices[g.Vertices.Length - 1];
            Assert.That(new Vector2(first.x, first.y).magnitude, Is.LessThan(1e-5f), what + " closed at its start");
            Assert.That(new Vector2(last.x, last.y).magnitude, Is.LessThan(1e-5f), what + " closed at its end");
            Assert.That(minZ, Is.LessThan(0f), what + " rounded past its start joint");
            Assert.That(maxZ, Is.GreaterThanOrEqualTo(length), what + " reaches its end joint");
        }

        [Test]
        public void TheSleeves_AreClosedRoundedTubes_FacingOut()
        {
            IsClosedAndFacesOut(SleeveShape.Forearm(), SleeveShape.ForearmLength, "forearm");
            IsClosedAndFacesOut(SleeveShape.UpperArm(), SleeveShape.UpperArmLength, "upper arm");

            // For looking at outside Unity: RECOIL_SLEEVE_OBJ=folder writes each as an .obj there.
            string folder = System.Environment.GetEnvironmentVariable("RECOIL_SLEEVE_OBJ");
            if (string.IsNullOrEmpty(folder)) return;
            Write(System.IO.Path.Combine(folder, "forearm.obj"), SleeveShape.Forearm());
            Write(System.IO.Path.Combine(folder, "upperarm.obj"), SleeveShape.UpperArm());
        }

        static void Write(string path, SleeveShape.Geometry g)
        {
            var text = new System.Text.StringBuilder();
            var culture = System.Globalization.CultureInfo.InvariantCulture;
            foreach (Vector3 v in g.Vertices) text.AppendLine(string.Format(culture, "v {0} {1} {2}", v.x, v.y, v.z));
            for (int i = 0; i + 2 < g.Triangles.Length; i += 3)
                text.AppendLine("f " + (g.Triangles[i] + 1) + " " + (g.Triangles[i + 1] + 1) + " " + (g.Triangles[i + 2] + 1));
            System.IO.File.WriteAllText(path, text.ToString());
        }
    }
}
