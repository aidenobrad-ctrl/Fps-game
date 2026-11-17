using System.Collections.Generic;
using UnityEngine;
using Recoil.Shared.Combat;

namespace Recoil.Shared.Match
{
    /// <summary>A body that a bullet can be tested against with plain geometry.</summary>
    public interface IShapeTarget
    {
        /// <summary>Who takes the damage.</summary>
        IDamageable Owner { get; }
        /// <summary>False while our bullets pass it by: not in the world, down, or on our side.</summary>
        bool Hittable { get; }
        /// <summary>Where it stands now.</summary>
        BodyPose Pose { get; }
        float StandEyeHeight { get; }
    }

    /// <summary>
    /// The bodies on this client that our bullets can meet: practice targets, other players.
    ///
    /// A bullet is traced with the physics engine first. This is the second opinion: the
    /// same body shapes (<see cref="BodyShapes"/>), tested with arithmetic alone, so a shot
    /// that crosses a body still counts if the physics engine reports nothing there. The
    /// two agree whenever the physics engine is doing its job, and then this adds nothing.
    /// </summary>
    public static class ShapeTargets
    {
        static readonly List<IShapeTarget> All = new List<IShapeTarget>(32);

        public static int Count => All.Count;

        public static void Add(IShapeTarget target)
        {
            if (target != null && !All.Contains(target)) All.Add(target);
        }

        public static void Remove(IShapeTarget target) => All.Remove(target);

        /// <summary>Forgets every body. Call when a scene starts, in case the last one left some behind.</summary>
        public static void Clear() => All.Clear();

        /// <summary>The first body a ray meets within <paramref name="maxDistance"/>, if any.</summary>
        /// <param name="direction">Unit length.</param>
        /// <param name="ignore">A body the ray passes through: one it has already hit. May be null.</param>
        public static bool Trace(Vector3 origin, Vector3 direction, float maxDistance, IDamageable ignore,
            out IShapeTarget target, out float distance, out HitZone zone)
        {
            target = null;
            distance = maxDistance;
            zone = HitZone.Body;

            for (int i = 0; i < All.Count; i++)
            {
                IShapeTarget candidate = All[i];
                if (!candidate.Hittable) continue;
                IDamageable owner = candidate.Owner;
                if (owner == null || owner == ignore || !owner.IsAlive) continue;

                if (!BodyShapes.Raycast(candidate.Pose, candidate.StandEyeHeight, origin, direction, distance, 0f, null,
                        out float at, out HitZone part))
                    continue;
                target = candidate;
                distance = at;
                zone = part;
            }
            return target != null;
        }
    }
}
