using System.Collections.Generic;

namespace Recoil.Shared.Weapons
{
    /// <summary>
    /// Checks weapon and attachment data for mistakes that would otherwise only show up as odd
    /// behaviour in play. The Project Doctor runs it in the Editor, and a test runs it over
    /// every asset in the catalog.
    /// </summary>
    public static class WeaponValidator
    {
        /// <summary>Problems with one weapon. Empty when it is fine.</summary>
        /// <summary>What one bullet or pellet deals up close on a part of the body, rounded as dealt.</summary>
        public static float OneHit(WeaponStats stats, Recoil.Shared.Combat.HitZone zone) =>
            DamageCalculator.Standardize(DamageCalculator.Compute(stats, 0f, zone));

        /// <summary>The most one trigger pull can deal to one target: every pellet on its worst part, or the full blast.</summary>
        public static float OneShot(WeaponStats stats, bool bodyOnly)
        {
            if (stats.explosionRadius > 0f) return DamageCalculator.Standardize(stats.damage);
            float worst = OneHit(stats, Recoil.Shared.Combat.HitZone.Body);
            if (!bodyOnly)
            {
                worst = System.Math.Max(worst, OneHit(stats, Recoil.Shared.Combat.HitZone.Head));
                worst = System.Math.Max(worst, OneHit(stats, Recoil.Shared.Combat.HitZone.Limb));
            }
            return worst * System.Math.Max(1, stats.pellets);
        }

        public static List<string> Validate(WeaponDefinition weapon)
        {
            var problems = new List<string>();
            string name = string.IsNullOrEmpty(weapon.weaponId) ? weapon.name : weapon.weaponId;
            void Problem(string message) => problems.Add(name + ": " + message);

            if (!IsValidId(weapon.weaponId)) Problem("weaponId must be lower-case letters, digits and underscores.");
            if (string.IsNullOrEmpty(weapon.displayName)) Problem("displayName is empty.");

            WeaponStats s = weapon.stats;
            if (s == null)
            {
                Problem("has no stats.");
                return problems;
            }

            if (s.roundsPerMinute <= 0f) Problem("roundsPerMinute must be above 0.");
            if (s.damage <= 0f) Problem("damage must be above 0.");
            if (s.pellets < 1) Problem("pellets must be at least 1.");
            if (s.falloffEnd < s.falloffStart) Problem("falloffEnd is nearer than falloffStart.");

            // Only a sniper rifle kills from full health with one shot, and only with a hit to the head,
            // which deals exactly the standard health at any range. Nothing else reaches it in one trigger pull.
            float standard = Recoil.Shared.Combat.HealthRules.Standard;
            if (weapon.weaponClass == WeaponClass.Sniper)
            {
                if (OneHit(s, Recoil.Shared.Combat.HitZone.Head) != standard)
                    Problem("a sniper rifle's hit to the head must deal exactly " + standard + " (it deals " + OneHit(s, Recoil.Shared.Combat.HitZone.Head) + ").");
                if (DamageCalculator.FalloffMultiplier(s, s.maxRange) < 1f) Problem("a sniper rifle must not lose damage with range, or a far head shot would not kill.");
                if (OneShot(s, bodyOnly: true) >= standard) Problem("a sniper rifle may kill in one shot only to the head.");
            }
            else if (OneShot(s, bodyOnly: false) >= standard)
            {
                Problem("one shot can deal " + OneShot(s, bodyOnly: false) + ", enough to kill from full health (" + standard + "); only a sniper's head shot may.");
            }
            if (s.fireMode == FireMode.Burst && s.burstCount < 2) Problem("a burst weapon needs burstCount of 2 or more.");
            if (s.fireMode == FireMode.Charge && s.chargeTime <= 0f) Problem("a charge weapon needs a chargeTime.");

            if (s.recoilPattern == null || s.recoilPattern.Length == 0) Problem("recoilPattern is empty.");
            else if (s.recoilLoopStart >= s.recoilPattern.Length) Problem("recoilLoopStart is past the end of the pattern.");

            if (s.UsesAmmo)
            {
                if (s.reloadTime <= 0f) Problem("reloadTime must be above 0.");
                if (s.reloadStyle == ReloadStyle.Magazine && s.emptyReloadTime <= 0f) Problem("emptyReloadTime must be above 0.");
            }

            switch (s.ballistics)
            {
                case BallisticsType.Projectile:
                    if (s.projectileSpeed <= 0f) Problem("projectileSpeed must be above 0.");
                    if (s.projectileLifetime <= 0f) Problem("projectileLifetime must be above 0.");
                    if (s.fuseTime > s.projectileLifetime) Problem("fuseTime is longer than projectileLifetime, so the fuse never finishes.");
                    if (s.fuseTime > 0f && s.explosionRadius <= 0f) Problem("has a fuse but no explosionRadius.");
                    break;
                case BallisticsType.Melee:
                    if (s.UsesAmmo) Problem("a melee weapon should have magazineSize 0.");
                    if (weapon.slot != WeaponSlotType.Melee) Problem("a melee weapon should go in the Melee slot.");
                    if (s.meleeRange <= 0f) Problem("meleeRange must be above 0.");
                    break;
            }
            if (s.ballistics != BallisticsType.Melee && weapon.slot == WeaponSlotType.Melee)
                Problem("only melee weapons can go in the Melee slot.");

            var seen = new HashSet<AttachmentDefinition>();
            if (weapon.attachments != null)
            {
                foreach (AttachmentDefinition attachment in weapon.attachments)
                {
                    if (attachment == null) Problem("has an empty entry in its attachments list.");
                    else if (!seen.Add(attachment)) Problem("lists attachment '" + attachment.attachmentId + "' twice.");
                }
            }

            return problems;
        }

        /// <summary>Problems with one attachment. Empty when it is fine.</summary>
        public static List<string> Validate(AttachmentDefinition attachment)
        {
            var problems = new List<string>();
            string name = string.IsNullOrEmpty(attachment.attachmentId) ? attachment.name : attachment.attachmentId;
            void Problem(string message) => problems.Add(name + ": " + message);

            if (!IsValidId(attachment.attachmentId)) Problem("attachmentId must be lower-case letters, digits and underscores.");
            if (string.IsNullOrEmpty(attachment.displayName)) Problem("displayName is empty.");

            if (attachment.modifiers != null)
            {
                foreach (StatModifier modifier in attachment.modifiers)
                {
                    if (modifier.op == ModifierOp.Multiply && modifier.value <= 0f)
                        Problem("multiplies " + modifier.stat + " by " + modifier.value + ", which would zero it out.");
                }
            }

            if (attachment.slot != AttachmentSlot.Sight && (attachment.sightZoom > 0f || attachment.reticle != ReticleStyle.None))
                Problem("sets a zoom or reticle but is not a sight.");

            return problems;
        }

        /// <summary>Problems across the whole catalog, including every weapon and attachment in it.</summary>
        public static List<string> Validate(WeaponCatalog catalog)
        {
            var problems = new List<string>();
            var weaponIds = new HashSet<string>();
            var attachmentIds = new HashSet<string>();
            var knownAttachments = new HashSet<AttachmentDefinition>();

            foreach (AttachmentDefinition attachment in catalog.attachments)
            {
                if (attachment == null)
                {
                    problems.Add("catalog: empty entry in the attachments list.");
                    continue;
                }
                knownAttachments.Add(attachment);
                if (!attachmentIds.Add(attachment.attachmentId))
                    problems.Add("catalog: attachment id '" + attachment.attachmentId + "' is used more than once.");
                problems.AddRange(Validate(attachment));
            }

            foreach (WeaponDefinition weapon in catalog.weapons)
            {
                if (weapon == null)
                {
                    problems.Add("catalog: empty entry in the weapons list.");
                    continue;
                }
                if (!weaponIds.Add(weapon.weaponId))
                    problems.Add("catalog: weapon id '" + weapon.weaponId + "' is used more than once.");
                problems.AddRange(Validate(weapon));

                if (weapon.attachments == null) continue;
                foreach (AttachmentDefinition attachment in weapon.attachments)
                {
                    if (attachment != null && !knownAttachments.Contains(attachment))
                        problems.Add(weapon.weaponId + ": uses attachment '" + attachment.attachmentId + "', which is not in the catalog.");
                }
            }

            return problems;
        }

        static bool IsValidId(string id)
        {
            if (string.IsNullOrEmpty(id)) return false;
            foreach (char c in id)
            {
                bool ok = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_';
                if (!ok) return false;
            }
            return true;
        }
    }
}
