using NUnit.Framework;
using UnityEngine;
using Recoil.Shared.Combat;
using Recoil.Shared.Match;

namespace Recoil.Tests
{
    /// <summary>
    /// The check of a bullet against bodies by plain geometry: the second opinion that makes
    /// a shot count when the physics engine reports nothing on its path.
    /// </summary>
    public class ShapeTargetTests
    {
        const float StandEye = 1.62f;

        sealed class Body : IDamageable, IShapeTarget
        {
            public Vector3 Feet;
            public float Yaw;
            public bool Up = true, Present = true;
            public float Taken;

            public bool IsAlive => Up;
            public DamageResult ApplyDamage(in DamageInfo info)
            {
                Taken += info.Amount;
                return new DamageResult { Applied = info.Amount };
            }

            public IDamageable Owner => this;
            public bool Hittable => Present;
            public BodyPose Pose => new BodyPose { Position = Feet, Yaw = Yaw, EyeHeight = StandEye };
            public float StandEyeHeight => StandEye;
        }

        static readonly Vector3 Eye = new Vector3(0f, 1.62f, 0f);

        [SetUp]
        public void Clear() => ShapeTargets.Clear();

        [TearDown]
        public void ClearAfter() => ShapeTargets.Clear();

        static Body Stand(float x, float z, float yaw = 180f)
        {
            var body = new Body { Feet = new Vector3(x, 0f, z), Yaw = yaw };
            ShapeTargets.Add(body);
            return body;
        }

        static Vector3 Towards(Vector3 point) => (point - Eye).normalized;

        [Test]
        public void AShotAtTheChest_HitsTheBody_AndOneAtTheHead_TheHead()
        {
            Body target = Stand(0f, 10f);

            Assert.That(ShapeTargets.Trace(Eye, Towards(new Vector3(0f, 1.16f, 10f)), 100f, null, out IShapeTarget hit, out float distance, out HitZone zone), Is.True);
            Assert.That(hit, Is.SameAs(target));
            Assert.That(zone, Is.EqualTo(HitZone.Body));
            Assert.That(distance, Is.EqualTo(10f).Within(0.3f));

            Assert.That(ShapeTargets.Trace(Eye, Towards(new Vector3(0f, 1.64f, 10f)), 100f, null, out hit, out distance, out zone), Is.True);
            Assert.That(zone, Is.EqualTo(HitZone.Head));

            Assert.That(ShapeTargets.Trace(Eye, Towards(new Vector3(0.1f, 0.4f, 10f)), 100f, null, out hit, out distance, out zone), Is.True);
            Assert.That(zone, Is.EqualTo(HitZone.Limb));
        }

        [Test]
        public void AShotPastTheBody_Misses()
        {
            Stand(0f, 10f);
            Assert.That(ShapeTargets.Trace(Eye, Towards(new Vector3(1.2f, 1.16f, 10f)), 100f, null, out _, out _, out _), Is.False, "wide");
            Assert.That(ShapeTargets.Trace(Eye, Towards(new Vector3(0f, 2.3f, 10f)), 100f, null, out _, out _, out _), Is.False, "over the head");
            Assert.That(ShapeTargets.Trace(Eye, Vector3.back, 100f, null, out _, out _, out _), Is.False, "the other way");
        }

        [Test]
        public void TheNearestBodyOnTheLine_IsTheOneHit_UnlessItIsToBePassed()
        {
            Body near = Stand(0f, 8f);
            Body far = Stand(0f, 14f);
            Vector3 direction = Towards(new Vector3(0f, 1.2f, 14f));

            Assert.That(ShapeTargets.Trace(Eye, direction, 100f, null, out IShapeTarget hit, out float distance, out _), Is.True);
            Assert.That(hit, Is.SameAs(near));
            Assert.That(distance, Is.LessThan(9f));

            Assert.That(ShapeTargets.Trace(Eye, direction, 100f, near, out hit, out distance, out _), Is.True);
            Assert.That(hit, Is.SameAs(far));
            Assert.That(distance, Is.GreaterThan(13f));
        }

        [Test]
        public void ABodyThatIsDown_Hidden_OrBehindWhereTheBulletStopped_IsNotHit()
        {
            Body target = Stand(0f, 10f);
            Vector3 direction = Towards(new Vector3(0f, 1.16f, 10f));

            // A wall at six metres stopped the bullet: the search goes no further than that.
            Assert.That(ShapeTargets.Trace(Eye, direction, 6f, null, out _, out _, out _), Is.False, "behind a wall");

            target.Up = false;
            Assert.That(ShapeTargets.Trace(Eye, direction, 100f, null, out _, out _, out _), Is.False, "down");

            target.Up = true;
            target.Present = false;
            Assert.That(ShapeTargets.Trace(Eye, direction, 100f, null, out _, out _, out _), Is.False, "not in the world");

            target.Present = true;
            ShapeTargets.Remove(target);
            Assert.That(ShapeTargets.Trace(Eye, direction, 100f, null, out _, out _, out _), Is.False, "gone");
            Assert.That(ShapeTargets.Count, Is.EqualTo(0));
        }

        [Test]
        public void ABodyIsFoundWhereItStandsNow_WhicheverWayItFaces()
        {
            Body target = Stand(0f, 10f, yaw: 37f);
            Assert.That(ShapeTargets.Trace(Eye, Towards(new Vector3(0f, 1.16f, 10f)), 100f, null, out _, out _, out _), Is.True);

            // A target sliding along its lane.
            target.Feet = new Vector3(4f, 0f, 20f);
            Assert.That(ShapeTargets.Trace(Eye, Towards(new Vector3(0f, 1.16f, 10f)), 100f, null, out _, out _, out _), Is.False, "where it was");
            Assert.That(ShapeTargets.Trace(Eye, Towards(new Vector3(4f, 1.16f, 20f)), 100f, null, out IShapeTarget hit, out float distance, out _), Is.True);
            Assert.That(hit, Is.SameAs(target));
            Assert.That(distance, Is.EqualTo(Vector3.Distance(Eye, new Vector3(4f, 1.16f, 20f))).Within(0.4f));
        }

        [Test]
        public void TheSameBodyIsNeverListedTwice()
        {
            Body target = Stand(0f, 10f);
            ShapeTargets.Add(target);
            ShapeTargets.Add(null);
            Assert.That(ShapeTargets.Count, Is.EqualTo(1));
        }
    }
}
