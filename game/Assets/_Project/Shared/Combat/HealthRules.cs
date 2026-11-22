namespace Recoil.Shared.Combat
{
    /// <summary>
    /// How much health everyone has: players, bots and the firing range's targets alike.
    /// Weapons are balanced round it: a sniper rifle's hit to the head deals exactly this much,
    /// the one shot in the game that kills from full health; nothing else reaches it in a single
    /// shot (the weapon tests check every weapon, attachment and grenade against it).
    /// A private match's host can still choose another figure.
    /// </summary>
    public static class HealthRules
    {
        public const float Standard = 150f;
    }
}
