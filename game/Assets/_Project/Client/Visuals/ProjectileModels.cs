using UnityEngine;
using Recoil.Shared.Weapons;

namespace Recoil.Client.Visuals
{
    /// <summary>
    /// Which model each projectile is drawn with (from Resources/Models/Projectiles.bytes),
    /// and how it turns in flight. Weapons and items without a model of their own get one by
    /// what they do: something that explodes on a fuse looks like a grenade, anything else
    /// that drops like a 40mm grenade, and the rest like a rocket.
    /// </summary>
    public static class ProjectileModels
    {
        public const string Set = "Projectiles";

        public static string For(string id, WeaponStats stats)
        {
            switch (id)
            {
                case "rl_rpg7": return "Rocket";
                case "gl_m32": return "Grenade40";
                case "m67_frag": return "FragGrenade";
                case "rgn_impact": return "ImpactGrenade";
                case "c4_charge": return "C4";
                case "mk3_concussion": return "ShockCharge";
            }
            if (stats == null) return null;
            if (stats.explosionRadius > 0f) return stats.fuseTime > 0f ? "FragGrenade" : "Rocket";
            if (stats.projectileGravity > 0f) return "Grenade40";
            return "Rocket";
        }

        /// <summary>Degrees a second about the model's own axes (x across, y up, z along the flight).</summary>
        public static Vector3 Spin(string model)
        {
            switch (model)
            {
                case "FragGrenade":
                case "ImpactGrenade":
                case "ShockCharge": return new Vector3(520f, 140f, 0f);
                case "C4": return new Vector3(300f, 220f, 0f);
                case "Grenade40": return new Vector3(0f, 0f, 900f);
                case "Rocket": return new Vector3(0f, 0f, 240f);
                default: return Vector3.zero;
            }
        }
    }
}
