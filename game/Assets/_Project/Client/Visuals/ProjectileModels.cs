using UnityEngine;
using Recoil.Shared.Weapons;

namespace Recoil.Client.Visuals
{
    /// <summary>
    /// Which model each projectile is drawn with (from Resources/Models/Projectiles.bytes),
    /// and how it turns in flight. Weapons and items without a model of their own get one by
    /// what they do: something that explodes on a fuse looks like a grenade, something that
    /// explodes on impact like a rocket, something that drops like a bolt, anything else like
    /// plasma.
    /// </summary>
    public static class ProjectileModels
    {
        public const string Set = "Projectiles";

        public static string For(string id, WeaponStats stats)
        {
            switch (id)
            {
                case "rl_kiln": return "Rocket";
                case "gl_pitcher": return "Grenade40";
                case "sp_bow": return "Arrow";
                case "sp_volley": return "Bolt";
                case "sp_flicker": return "ThrowingKnife";
                case "sp_slingshot": return "Pellet";
                case "sp_paintball": return "Paintball";
                case "sp_flare_gun": return "Flare";
                case "sp_stinger": return "Plasma";
                case "sp_carom": return "Spark";
                case "frag_grenade": return "FragGrenade";
                case "impact_grenade": return "ImpactGrenade";
                case "sticky_grenade": return "StickyGrenade";
                case "shock_charge": return "ShockCharge";
                case "ricochet_disc": return "Disc";
            }
            if (IsFlame(id) || stats == null) return null;
            if (stats.explosionRadius > 0f) return stats.fuseTime > 0f ? "FragGrenade" : "Rocket";
            if (stats.projectileGravity > 0f) return "Bolt";
            return "Plasma";
        }

        /// <summary>Drawn as fire, not as an object.</summary>
        public static bool IsFlame(string id) => id == "sp_flamethrower";

        /// <summary>Degrees a second about the model's own axes (x across, y up, z along the flight).</summary>
        public static Vector3 Spin(string model)
        {
            switch (model)
            {
                case "ThrowingKnife": return new Vector3(1260f, 0f, 0f);
                case "Disc": return new Vector3(0f, 1440f, 0f);
                case "FragGrenade":
                case "StickyGrenade":
                case "ImpactGrenade":
                case "ShockCharge": return new Vector3(520f, 140f, 0f);
                case "Grenade40": return new Vector3(0f, 0f, 900f);
                case "Rocket": return new Vector3(0f, 0f, 240f);
                case "Arrow":
                case "Bolt": return new Vector3(0f, 0f, 360f);
                case "Plasma":
                case "Spark": return new Vector3(0f, 0f, 720f);
                default: return Vector3.zero;
            }
        }
    }
}
