using System.Collections.Generic;
using UnityEngine;
using Recoil.Client.Loadouts;
using Recoil.Client.Online;
using Recoil.Client.Player;
using Recoil.Client.Settings;
using Recoil.Client.UI;
using Recoil.Shared.Combat;
using Recoil.Shared.Loadouts;
using Recoil.Shared.Match;
using Recoil.Shared.Movement;
using Recoil.Shared.Simulation;
using Recoil.Shared.Weapons;

namespace Recoil.Client.FiringRange
{
    /// <summary>
    /// Entry point of the firing range scene. Put this on one object in an otherwise empty
    /// scene and press Play: it builds the range, loads the player's saved loadouts, spawns
    /// the player with the equipped one, and puts up the HUD.
    ///
    /// The catalog decides what a loadout can be made from. Open the pause menu in play to
    /// pick, edit and save loadouts.
    /// </summary>
    [DefaultExecutionOrder(-100)]
    public sealed class FiringRangeBootstrap : MonoBehaviour
    {
        [SerializeField] MovementConfig movement;
        [SerializeField] LoadoutCatalog catalog;
        [Tooltip("Turn off if the scene already has its own directional light.")]
        [SerializeField] bool createSunLight = true;

        /// <summary>The scene with the main menu, if the build has one.</summary>
        public const string MenuScene = "Duel";

        PlayerRig _rig;
        RangeStats _stats;
        HudController _hud;
        LoadoutLibrary _library;
        RangeLayout _layout;

        void Awake()
        {
            if (movement == null)
            {
                Debug.LogWarning("FiringRangeBootstrap: no Movement Config assigned, using built-in defaults.", this);
                movement = ScriptableObject.CreateInstance<MovementConfig>();
            }
            if (catalog == null || catalog.weapons == null || catalog.weapons.weapons.Length == 0 || catalog.presets.Length == 0)
            {
                Debug.LogWarning("FiringRangeBootstrap: no usable Loadout Catalog assigned, using built-in stand-in equipment.", this);
                catalog = FallbackContent.BuildCatalog();
            }

            GameSettings.Load();
            GameLayers.ConfigureCollisionMatrix();
            RangeEnvironment.Apply(createSunLight);
            Visuals.GraphicsSetup.Initialize();
            Audio.SoundBank.Prewarm();
            Audio.MusicPlayer.SetMenu(false);
            Visuals.ScreenEffects.Calm();

            // Bodies a previous scene registered for hit checks are gone; start a clean list.
            ShapeTargets.Clear();
            RangeLayout layout = RangeLayout.Build(transform);
            _layout = layout;

            // The player's loadouts: on this computer, or on their account if they are signed in.
            GameServices services = GameServices.Get(catalog);
            _library = services.Library;
            if (services.Social != null) services.Social.Status = SocialClient.Range;

            _rig = PlayerRigFactory.Create(layout.PlayerSpawn, layout.SpawnYaw, movement, _library.ResolveEquipped(), new ProjectileSystem());
            _rig.Player.InfiniteReserve = true;
            _rig.Player.RechargeUtilities = true;
            RangeEnvironment.ConfigureCamera(_rig.Camera.Camera);

            // Whenever another loadout is equipped, or the equipped one is edited, hand it to the player.
            _library.EquippedChanged += OnEquippedChanged;

            _stats = new RangeStats();
            // A thrown utility item counts as a shot too, so accuracy stays a true fraction.
            _rig.Player.WeaponFired += _ => _stats.RecordShot();
            _rig.Player.UtilityThrown += _ => _stats.RecordShot();
            _rig.Player.ShotLanded += _stats.RecordShotLanded;
            _rig.Player.HitConfirmed += hit => _stats.RecordHit(hit);

            _hud = HudController.Create();
            _hud.Bind(_rig.Player, _rig.Camera.Camera, _stats, _library);
            _hud.ResetStatsRequested += _stats.Reset;
            _hud.SetPaused(false);

            // Reached from the main menu? Then the pause menu's last button goes back there.
            if (Application.CanStreamedLevelBeLoaded(MenuScene))
            {
                _hud.SetQuitLabel("Main menu");
                _hud.QuitRequested += () => UnityEngine.SceneManagement.SceneManager.LoadScene(MenuScene);
            }
        }

        void Start()
        {
            try
            {
                SelfCheck();
            }
            catch (System.Exception e)
            {
                Debug.LogWarning("Recoil self-check could not run: " + e.Message, this);
            }
        }

        /// <summary>
        /// Traces one test bullet (it does no damage) from where the player stands to the
        /// nearest target and says in the log what it met. If shots ever stop registering,
        /// this line says at once whether the physics engine can see the targets.
        /// </summary>
        void SelfCheck()
        {
            if (_layout == null || _layout.Targets.Count == 0) return;
            TargetDummy target = _layout.Targets[0];

            Vector3 eye = _layout.PlayerSpawn + Vector3.up * movement.standEyeHeight;
            Vector3 chest = target.transform.position + Vector3.up * 1.16f;
            float range = Vector3.Distance(eye, chest) + 5f;
            Vector3 direction = (chest - eye).normalized;

            Physics.SyncTransforms();
            HitscanHit hit = Hitscan.Trace(eye, direction, range);
            bool physics = hit.Hitbox != null && ReferenceEquals(hit.Hitbox.Owner, target.Health);
            bool geometry = ShapeTargets.Trace(eye, direction, range, null, out IShapeTarget seen, out float _, out HitZone _)
                            && ReferenceEquals(seen.Owner, target.Health);

            if (physics)
            {
                Debug.Log("Recoil self-check: a test bullet reached '" + target.name + "' (" + hit.Hitbox.zone + "). Hit detection is working.", this);
                return;
            }

            string met = !hit.HasHit ? "nothing"
                : hit.Collider == null ? "something" : "'" + hit.Collider.name + "' on layer " + hit.Collider.gameObject.layer;
            Debug.LogWarning("Recoil self-check: the physics engine did not report '" + target.name + "' on a test bullet's path; it met " + met +
                             " (shot mask " + GameLayers.ShotMask + "). " +
                             (geometry ? "Geometry finds the target, so hits will be counted that way." : "Geometry did not find it either, which should not happen: please report this line."), this);
        }

        void OnEquippedChanged() => _rig.Player.SetLoadout(_library.ResolveEquipped(), _rig.Player.Inventory.ActiveIndex);

        // The library outlives this scene, so let go of it on the way out.
        void OnDestroy()
        {
            if (_library != null) _library.EquippedChanged -= OnEquippedChanged;
        }
    }

    /// <summary>
    /// A minimal set of equipment built in code, so the range still works if the catalog
    /// asset is missing or empty. Never used when the real content loads.
    /// </summary>
    static class FallbackContent
    {
        public static LoadoutCatalog BuildCatalog()
        {
            var rifle = ScriptableObject.CreateInstance<WeaponDefinition>();
            rifle.weaponId = "fallback_rifle";
            rifle.displayName = "Fallback Rifle";

            var pistol = ScriptableObject.CreateInstance<WeaponDefinition>();
            pistol.weaponId = "fallback_pistol";
            pistol.displayName = "Fallback Pistol";
            pistol.weaponClass = WeaponClass.Pistol;
            pistol.slot = WeaponSlotType.Secondary;
            pistol.stats.fireMode = FireMode.SemiAuto;
            pistol.stats.roundsPerMinute = 400f;
            pistol.stats.magazineSize = 12;
            pistol.view.bodyLength = 0.18f;
            pistol.view.barrelLength = 0.04f;
            pistol.view.stockLength = 0f;
            pistol.view.bulk = 0.75f;

            var knife = ScriptableObject.CreateInstance<WeaponDefinition>();
            knife.weaponId = "fallback_knife";
            knife.displayName = "Fallback Knife";
            knife.weaponClass = WeaponClass.Melee;
            knife.slot = WeaponSlotType.Melee;
            knife.stats.ballistics = BallisticsType.Melee;
            knife.stats.fireMode = FireMode.SemiAuto;
            knife.stats.roundsPerMinute = 100f;
            knife.stats.damage = 55f;
            knife.stats.magazineSize = 0;
            knife.view.kind = ViewModelKind.Blade;
            knife.view.bodyLength = 0.2f;

            var weapons = ScriptableObject.CreateInstance<WeaponCatalog>();
            weapons.weapons = new[] { rifle, pistol, knife };

            var perks = ScriptableObject.CreateInstance<PerkSetDefinition>();
            perks.perkSetId = "fallback_perks";
            perks.displayName = "No Perks";

            var preset = ScriptableObject.CreateInstance<LoadoutPreset>();
            preset.presetId = "fallback_loadout";
            preset.displayName = "Fallback";
            preset.primary = rifle;
            preset.secondary = pistol;
            preset.melee = knife;
            preset.utility = Grenade("fallback_frag", "Fallback Frag", fuse: 2f);
            preset.perkSet = perks;

            var catalog = ScriptableObject.CreateInstance<LoadoutCatalog>();
            catalog.weapons = weapons;
            catalog.utilities = new[] { preset.utility };
            catalog.perkSets = new[] { perks };
            catalog.presets = new[] { preset };
            return catalog;
        }

        static UtilityDefinition Grenade(string id, string name, float fuse)
        {
            var grenade = ScriptableObject.CreateInstance<UtilityDefinition>();
            grenade.utilityId = id;
            grenade.displayName = name;
            grenade.charges = 2;
            grenade.projectile.damage = 100f;
            grenade.projectile.projectileSpeed = 22f;
            grenade.projectile.projectileGravity = 16f;
            grenade.projectile.projectileRadius = 0.08f;
            grenade.projectile.explosionRadius = 4f;
            grenade.projectile.fuseTime = fuse;
            grenade.projectile.bounces = fuse > 0f ? 12 : 0;
            grenade.projectile.falloffStart = 1000f;
            grenade.projectile.falloffEnd = 1000f;
            return grenade;
        }
    }
}
