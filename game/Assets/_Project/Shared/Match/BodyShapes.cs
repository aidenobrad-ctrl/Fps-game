using UnityEngine;
using Recoil.Shared.Combat;

namespace Recoil.Shared.Match
{
    /// <summary>
    /// The shape of a character for shooting at: a head, a torso, two arms and two legs. The
    /// physics hitboxes on the server and the client, the firing range's dummies and the
    /// server's own check of a hit a client reports are all built from this one table, so
    /// they can never disagree.
    ///
    /// The parts are a little larger than the bare body: they cover what a character wears,
    /// so a shot that visibly lands on a helmet or a shoulder pad counts.
    /// </summary>
    public static class BodyShapes
    {
        public struct Part
        {
            public string Name;
            public HitZone Zone;
            /// <summary>A sphere, sized by the largest of <see cref="Size"/>; otherwise a box.</summary>
            public bool Round;
            /// <summary>Centre and size when standing upright, from the feet, facing +Z.</summary>
            public Vector3 Offset, Size;
        }

        public static readonly Part[] Parts =
        {
            new Part { Name = "Head", Zone = HitZone.Head, Round = true, Offset = new Vector3(0f, 1.64f, 0f), Size = new Vector3(0.3f, 0.3f, 0.3f) },
            new Part { Name = "Torso", Zone = HitZone.Body, Offset = new Vector3(0f, 1.16f, 0f), Size = new Vector3(0.5f, 0.66f, 0.32f) },
            new Part { Name = "ArmL", Zone = HitZone.Limb, Offset = new Vector3(-0.33f, 1.16f, 0f), Size = new Vector3(0.16f, 0.64f, 0.18f) },
            new Part { Name = "ArmR", Zone = HitZone.Limb, Offset = new Vector3(0.33f, 1.16f, 0f), Size = new Vector3(0.16f, 0.64f, 0.18f) },
            new Part { Name = "LegL", Zone = HitZone.Limb, Offset = new Vector3(-0.12f, 0.42f, 0f), Size = new Vector3(0.2f, 0.84f, 0.22f) },
            new Part { Name = "LegR", Zone = HitZone.Limb, Offset = new Vector3(0.12f, 0.42f, 0f), Size = new Vector3(0.2f, 0.84f, 0.22f) },
        };

        /// <summary>How far down a crouch or slide squashes the body: the eye height as a share of standing.</summary>
        public static float Squash(float eyeHeight, float standEyeHeight) =>
            Mathf.Clamp(standEyeHeight > 0f ? eyeHeight / standEyeHeight : 1f, 0.3f, 1.2f);

        /// <summary>A part's centre, from the feet, for a body squashed by <paramref name="squash"/>.</summary>
        public static Vector3 LocalCentre(in Part part, float squash) =>
            new Vector3(part.Offset.x, part.Offset.y * squash, part.Offset.z);

        /// <summary>A part's size for a body squashed by <paramref name="squash"/>. Round parts keep their size.</summary>
        public static Vector3 LocalSize(in Part part, float squash) =>
            part.Round ? part.Size : new Vector3(part.Size.x, part.Size.y * squash, part.Size.z);

        /// <summary>
        /// Where a ray first meets a body standing in <paramref name="pose"/>, worked out with
        /// plain geometry rather than the physics engine. Every part is grown by
        /// <paramref name="slack"/> on every side.
        /// </summary>
        /// <param name="zone">Only parts of this zone count; null for any part.</param>
        /// <returns>True if the ray meets a part within <paramref name="maxDistance"/>.</returns>
        public static bool Raycast(in BodyPose pose, float standEyeHeight, Vector3 origin, Vector3 direction, float maxDistance,
            float slack, HitZone? zone, out float distance, out HitZone hitZone)
        {
            distance = float.MaxValue;
            hitZone = HitZone.Body;

            // Into the body's own frame: feet at the origin, facing +Z.
            Vector3 o = ToLocal(origin - pose.Position, pose.Yaw);
            Vector3 d = ToLocal(direction, pose.Yaw);
            float squash = Squash(pose.EyeHeight, standEyeHeight);

            bool found = false;
            foreach (Part part in Parts)
            {
                if (zone.HasValue && part.Zone != zone.Value) continue;
                Vector3 centre = LocalCentre(part, squash);
                Vector3 size = LocalSize(part, squash);
                float t;
                bool hit = part.Round
                    ? RaySphere(o, d, centre, Mathf.Max(size.x, Mathf.Max(size.y, size.z)) * 0.5f + slack, out t)
                    : RayBox(o, d, centre, size * 0.5f + Vector3.one * slack, out t);
                if (!hit || t > maxDistance || t >= distance) continue;
                distance = t;
                hitZone = part.Zone;
                found = true;
            }
            return found;
        }

        /// <summary>Turns a world-space offset into the frame of a body facing <paramref name="yaw"/> degrees.</summary>
        static Vector3 ToLocal(Vector3 v, float yaw)
        {
            // The body's right is (cos, 0, -sin) and its forward (sin, 0, cos) for a yaw in degrees.
            float r = yaw * Mathf.Deg2Rad;
            float sin = Mathf.Sin(r), cos = Mathf.Cos(r);
            return new Vector3(v.x * cos - v.z * sin, v.y, v.x * sin + v.z * cos);
        }

        /// <summary>Entry distance of a ray into a sphere. A ray that starts inside does not count, as with the physics engine.</summary>
        static bool RaySphere(Vector3 o, Vector3 d, Vector3 centre, float radius, out float t)
        {
            t = 0f;
            Vector3 oc = o - centre;
            float b = Vector3.Dot(oc, d);
            float c = oc.sqrMagnitude - radius * radius;
            if (c <= 0f) return false;
            float disc = b * b - c;
            if (disc < 0f) return false;
            t = -b - Mathf.Sqrt(disc);
            return t >= 0f;
        }

        /// <summary>Entry distance of a ray into an axis-aligned box. A ray that starts inside does not count.</summary>
        static bool RayBox(Vector3 o, Vector3 d, Vector3 centre, Vector3 half, out float t)
        {
            t = 0f;
            float near = float.MinValue, far = float.MaxValue;
            if (!Slab(o.x, d.x, centre.x - half.x, centre.x + half.x, ref near, ref far)) return false;
            if (!Slab(o.y, d.y, centre.y - half.y, centre.y + half.y, ref near, ref far)) return false;
            if (!Slab(o.z, d.z, centre.z - half.z, centre.z + half.z, ref near, ref far)) return false;
            if (near < 0f) return false;
            t = near;
            return true;
        }

        static bool Slab(float origin, float dir, float min, float max, ref float near, ref float far)
        {
            if (Mathf.Abs(dir) < 1e-8f) return origin >= min && origin <= max;
            float t1 = (min - origin) / dir, t2 = (max - origin) / dir;
            if (t1 > t2) { float swap = t1; t1 = t2; t2 = swap; }
            if (t1 > near) near = t1;
            if (t2 < far) far = t2;
            return near <= far;
        }
    }
}
