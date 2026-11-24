using System.Collections.Generic;
using UnityEngine;

namespace Recoil.Client.Weapons
{
    /// <summary>
    /// The first-person sleeves, made in code: closed, rounded tubes of cloth along +z, one for
    /// the forearm (elbow at 0, wrist at <see cref="ForearmLength"/>, with a rolled cuff that
    /// tucks into the glove) and one for the upper arm (shoulder at 0, elbow at
    /// <see cref="UpperArmLength"/>). They replace sleeves cut from the soldier's uniform,
    /// whose open, ragged ends showed as a loose flap at the elbow and looked hollow from some
    /// angles. Plain geometry, so it can be checked outside Unity.
    /// </summary>
    public static class SleeveShape
    {
        public const float UpperArmLength = 0.29f;
        public const float ForearmLength = 0.265f;
        const int Segments = 18;
        /// <summary>Metres round the sleeve that the texture's u runs across (about its girth).</summary>
        const float Girth = 0.28f;

        public struct Geometry
        {
            public Vector3[] Vertices, Normals;
            public Vector2[] Uvs;
            public int[] Triangles;
        }

        /// <summary>The forearm: rounded at the elbow, slimmer to the wrist, a rolled cuff, closed under the glove.</summary>
        public static Geometry Forearm()
        {
            var profile = new List<Vector2>();
            Dome(profile, 0f, 0.046f, start: true);
            profile.Add(new Vector2(0.035f, 0.047f));
            profile.Add(new Vector2(0.095f, 0.045f));
            profile.Add(new Vector2(0.165f, 0.040f));
            profile.Add(new Vector2(0.222f, 0.036f));
            profile.Add(new Vector2(0.232f, 0.0405f));
            profile.Add(new Vector2(0.256f, 0.041f));
            profile.Add(new Vector2(ForearmLength, 0.037f));
            profile.Add(new Vector2(ForearmLength + 0.006f, 0.026f));
            profile.Add(new Vector2(ForearmLength + 0.008f, 0f));
            return Lathe(profile);
        }

        /// <summary>The upper arm: rounded at both ends, thickest below the shoulder.</summary>
        public static Geometry UpperArm()
        {
            var profile = new List<Vector2>();
            Dome(profile, 0f, 0.053f, start: true);
            profile.Add(new Vector2(0.06f, 0.055f));
            profile.Add(new Vector2(0.15f, 0.052f));
            profile.Add(new Vector2(0.235f, 0.048f));
            Dome(profile, UpperArmLength, 0.047f, start: false);
            return Lathe(profile);
        }

        /// <summary>A quarter circle in (z, radius): closing a tube's start (from its tip up to the full radius at z) or its end.</summary>
        static void Dome(List<Vector2> profile, float z, float radius, bool start)
        {
            const int steps = 5;
            for (int k = 0; k <= steps; k++)
            {
                float a = Mathf.PI * 0.5f * k / steps;
                // The tips exactly on the axis: Cos(pi/2) is not quite zero in floats, which would leave a tiny ring turned inside out.
                float across = k == 0 ? 0f : k == steps ? 1f : Mathf.Sin(a);
                float along = k == 0 ? 1f : k == steps ? 0f : Mathf.Cos(a);
                profile.Add(start
                    ? new Vector2(z - radius * along, radius * across)
                    : new Vector2(z + radius * across, radius * along));
            }
        }

        /// <summary>
        /// Turns a profile of (z, radius) points, tip to tip, round the z axis. Triangles are
        /// wound as Unity draws them: seen from outside, so the cross of their edges points out.
        /// </summary>
        public static Geometry Lathe(IList<Vector2> profile)
        {
            int rings = profile.Count, columns = Segments + 1;
            var g = new Geometry
            {
                Vertices = new Vector3[rings * columns],
                Normals = new Vector3[rings * columns],
                Uvs = new Vector2[rings * columns],
                Triangles = new int[(rings - 1) * Segments * 6],
            };
            for (int i = 0; i < rings; i++)
            {
                Vector2 before = profile[Mathf.Max(i - 1, 0)], after = profile[Mathf.Min(i + 1, rings - 1)];
                Vector2 along = after - before;
                // Out from the axis in the profile's plane: the tangent turned a quarter towards +radius.
                var outward = new Vector2(-along.y, along.x);
                outward = outward.sqrMagnitude > 1e-12f ? outward.normalized : new Vector2(0f, 1f);
                for (int j = 0; j < columns; j++)
                {
                    // The texture's seam runs along -y, which the arms turn to the outside of the elbow, out of sight.
                    float a = 2f * Mathf.PI * j / Segments - 0.5f * Mathf.PI;
                    float c = Mathf.Cos(a), s = Mathf.Sin(a);
                    int v = i * columns + j;
                    g.Vertices[v] = new Vector3(profile[i].y * c, profile[i].y * s, profile[i].x);
                    g.Normals[v] = new Vector3(outward.y * c, outward.y * s, outward.x).normalized;
                    g.Uvs[v] = new Vector2(Girth * j / Segments, profile[i].x);
                }
            }
            int t = 0;
            for (int i = 0; i + 1 < rings; i++)
            {
                for (int j = 0; j < Segments; j++)
                {
                    int a = i * columns + j, b = (i + 1) * columns + j, c = a + 1, d = b + 1;
                    // a to c turns round the axis, a to b runs along it: (a, c, b) faces out.
                    g.Triangles[t++] = a; g.Triangles[t++] = c; g.Triangles[t++] = b;
                    g.Triangles[t++] = c; g.Triangles[t++] = d; g.Triangles[t++] = b;
                }
            }
            return g;
        }
    }
}
