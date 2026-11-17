using NUnit.Framework;
using UnityEngine;
using Recoil.Shared.Combat;
using Recoil.Shared.Match;
using Recoil.Shared.Weapons;

namespace Recoil.Tests
{
    /// <summary>The weapon in someone's hands as a thing to shoot: where it is, and what a shot on it does.</summary>
    public class WeaponBreakTests
    {
        const float StandEye = 1.62f;

        static WeaponDefinition Weapon(string id, ViewModelKind kind, float body, float barrel, float stock, float bulk = 1f)
        {
            var weapon = ScriptableObject.CreateInstance<WeaponDefinition>();
            weapon.weaponId = id;
            weapon.view.kind = kind;
            weapon.view.bodyLength = body;
            weapon.view.barrelLength = barrel;
            weapon.view.stockLength = stock;
            weapon.view.bulk = bulk;
            return weapon;
        }

        static WeaponDefinition Rifle => Weapon("ar_test", ViewModelKind.Gun, 0.3f, 0.36f, 0.2f);
        static WeaponDefinition Pistol => Weapon("pistol_test", ViewModelKind.Gun, 0.16f, 0.06f, 0f, 0.7f);

        /// <summary>Someone at the origin facing +z, holding <paramref name="weapon"/>, looking <paramref name="pitch"/> down.</summary>
        static BodyPose Holding(WeaponDefinition weapon, float pitch = 0f) => new BodyPose
        {
            Position = Vector3.zero,
            Yaw = 0f,
            EyeHeight = StandEye,
            Pitch = pitch,
            Held = BodyShapes.Held(weapon),
        };

        /// <summary>Where the middle of the weapon is, from the side, for aiming at it.</summary>
        static Vector3 WeaponMiddle(in BodyPose pose)
        {
            BodyShapes.WeaponFrame(pose.EyeHeight, StandEye, pose.Pitch, pose.Held, out Vector3 pocket, out float turn);
            return pocket + BodyShapes.RotateX(pose.Held.Centre, turn);
        }

        static bool Shoot(in BodyPose pose, Vector3 from, Vector3 at, out HitZone zone)
        {
            Vector3 direction = (at - from).normalized;
            return BodyShapes.Raycast(pose, StandEye, from, direction, 100f, 0f, null, out _, out zone);
        }

        [Test]
        public void EveryWeaponButBareHands_IsSomethingToShoot()
        {
            Assert.That(BodyShapes.Held(Rifle).Present);
            Assert.That(BodyShapes.Held(Pistol).Present);
            Assert.That(BodyShapes.Held(Weapon("knife", ViewModelKind.Blade, 0.18f, 0f, 0f)).Present);
            Assert.That(BodyShapes.Held(Weapon(BodyShapes.FistsId, ViewModelKind.Blade, 0.08f, 0.3f, 0.2f)).Present, Is.False);
            Assert.That(BodyShapes.Held(null).Present, Is.False);

            // A rifle reaches well out in front; a pistol is short and held out at arm's length.
            HeldWeapon rifle = BodyShapes.Held(Rifle), pistol = BodyShapes.Held(Pistol);
            Assert.That(rifle.Size.z, Is.GreaterThan(0.7f));
            Assert.That(pistol.Size.z, Is.LessThan(0.3f));
            Assert.That(pistol.Centre.z, Is.GreaterThan(0.3f));
        }

        [Test]
        public void AShotFromTheSide_AtTheRifle_HitsTheWeapon_NotTheBody()
        {
            BodyPose pose = Holding(Rifle);
            Vector3 middle = WeaponMiddle(pose);
            // The weapon sticks out in front of the chest, where nothing else is.
            Assert.That(middle.z, Is.GreaterThan(0.3f));
            Assert.That(Shoot(pose, middle + Vector3.right * 10f, middle, out HitZone zone));
            Assert.That(zone, Is.EqualTo(HitZone.Weapon));

            // The chest, from straight ahead, is still the body.
            Assert.That(Shoot(pose, new Vector3(0f, 1.1f, 10f), new Vector3(-0.1f, 1.1f, 0f), out zone));
            Assert.That(zone, Is.EqualTo(HitZone.Body));
        }

        [Test]
        public void TheWeapon_TurnsWithWhereTheyLook()
        {
            BodyPose level = Holding(Rifle), down = Holding(Rifle, pitch: 45f);
            Vector3 levelMiddle = WeaponMiddle(level), downMiddle = WeaponMiddle(down);
            Assert.That(downMiddle.y, Is.LessThan(levelMiddle.y - 0.15f), "aimed down, the muzzle end drops");

            // Where the weapon is when level is empty air once they look down.
            BodyShapes.WeaponFrame(level.EyeHeight, StandEye, level.Pitch, level.Held, out Vector3 pocket, out float turn);
            Vector3 muzzleEnd = pocket + BodyShapes.RotateX(level.Held.Centre + new Vector3(0f, 0f, level.Held.Size.z * 0.4f), turn);
            Assert.That(Shoot(level, muzzleEnd + Vector3.right * 10f, muzzleEnd, out HitZone zone) && zone == HitZone.Weapon);
            Assert.That(Shoot(down, muzzleEnd + Vector3.right * 10f, muzzleEnd, out zone) && zone == HitZone.Weapon, Is.False);
            // And it is found where it went.
            Assert.That(Shoot(down, downMiddle + Vector3.right * 10f, downMiddle, out zone));
            Assert.That(zone, Is.EqualTo(HitZone.Weapon));
        }

        [Test]
        public void ANamedZone_OnlyFindsThatZone()
        {
            BodyPose pose = Holding(Rifle);
            Vector3 middle = WeaponMiddle(pose), from = middle + Vector3.right * 10f, direction = (middle - from).normalized;
            Assert.That(BodyShapes.Raycast(pose, StandEye, from, direction, 100f, 0f, HitZone.Body, out _, out _), Is.False);
            Assert.That(BodyShapes.Raycast(pose, StandEye, from, direction, 100f, 0f, HitZone.Weapon, out _, out HitZone zone));
            Assert.That(zone, Is.EqualTo(HitZone.Weapon));
        }

        [Test]
        public void BreakingIsLikelierTheHarderTheShot()
        {
            Assert.That(WeaponBreaking.Chance(0f), Is.EqualTo(0.1f).Within(1e-4f));
            Assert.That(WeaponBreaking.Chance(25f), Is.GreaterThan(WeaponBreaking.Chance(15f)));
            Assert.That(WeaponBreaking.Chance(25f), Is.InRange(0.2f, 0.3f), "a rifle round");
            Assert.That(WeaponBreaking.Chance(95f), Is.InRange(0.6f, 0.75f), "a sniper round");
            Assert.That(WeaponBreaking.Chance(1000f), Is.EqualTo(0.75f).Within(1e-4f), "never certain");
        }

        [Test]
        public void AShotOnTheWeapon_DoesNoHarm_ButMayBreakIt()
        {
            var vitals = new PlayerVitals(3) { Max = 100f };
            vitals.Revive();
            int asked = 0;
            vitals.WeaponStruck = (who, info) => { asked++; return info.Amount >= 50f; };

            DamageResult light = vitals.ApplyDamage(new DamageInfo { Amount = 25f, Zone = HitZone.Weapon });
            Assert.That(light.WeaponStruck && !light.WeaponBroken);
            DamageResult heavy = vitals.ApplyDamage(new DamageInfo { Amount = 90f, Zone = HitZone.Weapon });
            Assert.That(heavy.WeaponStruck && heavy.WeaponBroken);
            Assert.That(asked, Is.EqualTo(2));
            Assert.That(vitals.Current, Is.EqualTo(100f), "no harm done to them");
            Assert.That(light.Applied + heavy.Applied, Is.Zero);

            // Someone who cannot be hurt by the shooter (a teammate) is not touched at all.
            vitals.CanBeHurtBy = attacker => false;
            DamageResult friendly = vitals.ApplyDamage(new DamageInfo { Amount = 90f, Zone = HitZone.Weapon, Attacker = new PlayerVitals(4) });
            Assert.That(friendly.WeaponStruck, Is.False);
            Assert.That(asked, Is.EqualTo(2));
        }
    }
}
