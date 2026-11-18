using UnityEngine;
using Recoil.Client.Audio;
using Recoil.Client.Visuals;
using Recoil.Client.Weapons;
using Recoil.Shared.Combat;
using Recoil.Shared.Cosmetics;
using Recoil.Shared.Match;
using Recoil.Shared.Movement;
using Recoil.Shared.Weapons;

namespace Recoil.Client.Net
{
    /// <summary>
    /// Another player, as drawn on this client: a body made of the same parts the server
    /// shoots at, dressed in the look they chose, holding a block in their weapon's skin.
    /// Shoulder pads show the side they are on (blue for a teammate, red for anyone else), and
    /// teammates have a marker over their heads so they are easy to pick out.
    ///
    /// It never simulates anything. Each frame it asks the session where that player was a
    /// moment ago and stands the body there.
    /// </summary>
    [DefaultExecutionOrder(10)]
    public sealed class RemotePlayerView : MonoBehaviour, IShapeTarget
    {
        const float FlashTime = 0.12f;
        static readonly Color MarkerColor = new Color(0.55f, 0.85f, 1f);

        ClientSession _session;
        int _playerId;
        UnityCharacterBody _body;
        RemoteTarget _target;
        Transform _gun, _gunMuzzle;
        float _standEyeHeight;
        CharacterLookView _look;
        Transform _weapon;
        MeshRenderer _weaponRenderer;
        Material _weaponMaterial, _markerMaterial;
        Transform _marker;
        bool _friendly;
        float _flash;
        readonly FootstepTimer _steps = new FootstepTimer();
        float _lastFallSpeed;
        Stance _lastStance;
        bool _wasVisible;
        int _shownSlot = -1;
        byte _shownSpawn;
        /// <summary>The weapon in their hands as a box to shoot at, matching the server's.</summary>
        HeldWeapon _held;
        CharacterLook _shownLook;

        public int PlayerId => _playerId;
        public bool Visible { get; private set; }

        // For the check of our bullets by plain geometry (ShapeTargets). Teammates are passed by.
        BodyPose _pose;
        IDamageable IShapeTarget.Owner => _target;
        bool IShapeTarget.Hittable => Visible && _target != null && !_target.Friendly;
        BodyPose IShapeTarget.Pose => _pose;
        float IShapeTarget.StandEyeHeight => _standEyeHeight;

        /// <summary>The middle of the weapon in their hands, for the sparks when it is hit or breaks.</summary>
        public Vector3 WeaponCentre => _gun != null ? _gun.position + _gun.forward * 0.25f : Muzzle;

        /// <summary>The front of the weapon, where tracers start.</summary>
        public Vector3 Muzzle => _gunMuzzle != null ? _gunMuzzle.position : _weapon.TransformPoint(new Vector3(0f, 0f, 0.5f));

        /// <summary>Where they stand, as last drawn.</summary>
        public Vector3 Feet => _body.Root.position;

        /// <summary>Whether a point is on or close to their body, as last drawn.</summary>
        public bool Covers(Vector3 point) =>
            Visible && new Vector2(point.x - Feet.x, point.z - Feet.z).sqrMagnitude < 0.6f * 0.6f && point.y > Feet.y - 0.2f && point.y < Feet.y + 2.1f;

        public static RemotePlayerView Create(ClientSession session, int playerId, MovementConfig movement)
        {
            var view = new GameObject("Remote Player " + playerId).AddComponent<RemotePlayerView>();
            view._session = session;
            view._playerId = playerId;
            view.Build(movement);
            return view;
        }

        void Build(MovementConfig movement)
        {
            // Hitboxes only: our own bullets are traced against them to draw where they stop.
            // Whether a shot really hit is decided on the server.
            _body = new UnityCharacterBody("Remote " + _playerId, movement, withController: false, server: false);
            _body.Root.SetParent(transform, false);
            _target = new RemoteTarget(_playerId);
            _body.SetOwner(_target);
            _look = new CharacterLookView(_body);
            _standEyeHeight = movement.standEyeHeight;

            _weaponMaterial = new Material(GreyboxMaterials.Flat(new Color(0.2f, 0.2f, 0.22f)));
            GameObject weapon = GreyboxKit.Visual(_body.Root, "Weapon", PrimitiveType.Cube, Vector3.zero, new Vector3(0.07f, 0.1f, 0.6f), _weaponMaterial);
            _weapon = weapon.transform;
            _weaponRenderer = weapon.GetComponent<MeshRenderer>();
            // The soldier carries a full model of the gun instead of a block.
            if (_look.Soldier != null) weapon.SetActive(false);

            _markerMaterial = new Material(GreyboxMaterials.Unlit(MarkerColor));
            _marker = GreyboxKit.Visual(_body.Root, "Team Marker", PrimitiveType.Cube, Vector3.zero,
                new Vector3(0.18f, 0.18f, 0.18f), _markerMaterial, castShadows: false).transform;
            _marker.localRotation = Quaternion.Euler(45f, 0f, 45f);
            _marker.gameObject.SetActive(false);

            _body.Root.gameObject.SetActive(false);
            ShapeTargets.Add(this);
        }

        /// <summary>Lights the body up for a moment. Called when one of our shots is confirmed.</summary>
        public void Flash() => _flash = FlashTime;

        void Update()
        {
            RemoteView view = default;
            Visible = _session != null && _session.TryGetView(_playerId, out view);
            if (_body.Root.gameObject.activeSelf != Visible) _body.Root.gameObject.SetActive(Visible);
            if (!Visible)
            {
                _wasVisible = false;
                return;
            }
            PlayMovementSounds(view);

            ClientPlayer player = _session.Players[_playerId];
            _look.Apply(player.Look);
            ShowWeapon(view.ActiveSlot);
            BodyPose pose = view.Pose;
            pose.Pitch = view.Pitch;
            pose.Held = _held;
            _body.SetPose(pose);
            _pose = pose;
            _look.Follow();
            UpdateSide(view.Pose.EyeHeight);
            _look.Animate(new SoldierMotion
            {
                Velocity = view.Velocity,
                Yaw = view.Pose.Yaw,
                Pitch = view.Pitch,
                EyeHeight = view.Pose.EyeHeight,
                StandEyeHeight = _standEyeHeight,
                Stance = view.Stance,
                Grounded = Mathf.Abs(view.Velocity.y) < 0.6f,
            }, Time.deltaTime);

            // Without the soldier, a block at the right shoulder that tips with where they are looking.
            if (_look.Soldier == null)
            {
                _weapon.localPosition = new Vector3(0.2f, view.Pose.EyeHeight - 0.22f, 0.3f);
                _weapon.localRotation = Quaternion.Euler(view.Pitch, 0f, 0f);
            }

            if (_flash > 0f)
            {
                _flash -= Time.unscaledDeltaTime;
                _look.Flash(Mathf.Clamp01(_flash / FlashTime));
                if (_flash <= 0f) _look.Flash(0f);
            }
        }

        /// <summary>Their footsteps, jumps, landings and slides, from where they are.</summary>
        void PlayMovementSounds(in RemoteView view)
        {
            SfxPlayer sfx = SfxPlayer.Current;
            Vector3 velocity = view.Velocity;
            Vector3 feet = view.Pose.Position;
            if (sfx != null)
            {
                bool grounded = Mathf.Abs(velocity.y) < 0.6f;
                float loudness = _steps.Advance(velocity, grounded, view.Stance, Time.deltaTime);
                if (loudness > 0f) sfx.PlayAt(Sfx.Footstep, feet, loudness, 0.08f, 1.5f, 34f);
                if (_wasVisible)
                {
                    if (velocity.y > 3f && _lastFallSpeed > -1f && _lastFallSpeed < 1f) sfx.PlayAt(Sfx.Jump, feet, 0.6f, 0.05f, 1.5f, 25f);
                    if (_lastFallSpeed < -4f && velocity.y > -1f) sfx.PlayAt(Sfx.Land, feet, Mathf.Clamp01(-_lastFallSpeed / 12f), 0.05f, 1.5f, 30f);
                    if (view.Stance == Stance.Sliding && _lastStance != Stance.Sliding) sfx.PlayAt(Sfx.Slide, feet, 0.8f, 0.05f, 1.5f, 30f);
                }
            }
            _lastFallSpeed = velocity.y;
            _lastStance = view.Stance;
            _wasVisible = true;
        }

        /// <summary>
        /// Pads in the colour of their side, and a marker over teammates. Checked every frame:
        /// teams can change between matches.
        /// </summary>
        void UpdateSide(float eyeHeight)
        {
            ClientPlayer local = _session.Local;
            ClientPlayer player = _session.Players[_playerId];
            bool friendly = local != null && _session.Settings.TeamBased && player.Team != Teams.None && player.Team == local.Team;
            _target.Friendly = friendly;
            if (friendly != _friendly || !_marker.gameObject.activeSelf && friendly)
            {
                _friendly = friendly;
                _marker.gameObject.SetActive(friendly);
            }
            _look.SetSide(true, friendly);
            if (friendly) _marker.localPosition = new Vector3(0f, eyeHeight + 0.6f + Mathf.Sin(Time.time * 3f) * 0.05f, 0f);
        }

        /// <summary>Sizes the weapon block to hint at what they are holding, in that weapon's skin.</summary>
        void ShowWeapon(int slot)
        {
            ClientPlayer player = _session.Players[_playerId];
            if (slot == _shownSlot && player.SpawnCount == _shownSpawn && ReferenceEquals(player.Look, _shownLook)) return;
            _shownSlot = slot;
            _shownSpawn = player.SpawnCount;
            _shownLook = player.Look;

            WeaponBuild build = player.Loadout != null && slot >= 0 && slot < player.Loadout.Weapons.Length ? player.Loadout.Weapons[slot] : null;
            _held = BodyShapes.Held(build?.Weapon);
            if (build == null) return;

            SoldierView soldier = _look.Soldier;
            if (soldier != null)
            {
                // The real thing, in their skin, butt against the shoulder (or held out, for a handgun).
                if (_gun != null) Destroy(_gun.gameObject);
                ViewModelLayout layout = ViewModelBuilder.Build(soldier.WeaponMount, build, player.Look.SkinFor(build.Weapon.weaponId), castShadows: true);
                _gun = layout.Root;
                _gunMuzzle = layout.Muzzle;
                bool handgun = layout.Handgun;
                _gun.localPosition = handgun ? new Vector3(-0.14f, -0.06f, 0.36f) : new Vector3(0f, 0f, -layout.RearZ - 0.03f);
                _gun.localRotation = layout.Kind == ViewModelKind.Blade || layout.Kind == ViewModelKind.Thrown
                    ? Quaternion.Euler(-60f, 0f, 0f) : Quaternion.identity;
                soldier.Hold(layout.Grip, layout.Support);
                return;
            }

            WeaponViewProfile look = build.Weapon.view;
            float length = Mathf.Clamp(look.bodyLength + look.barrelLength + look.stockLength, 0.2f, 1.1f);
            _weapon.localScale = new Vector3(0.07f, 0.1f, length);

            Material skin = LookMaterials.SkinBody(player.Look.SkinFor(build.Weapon.weaponId));
            if (skin != null)
            {
                _weaponRenderer.sharedMaterial = skin;
                return;
            }
            GreyboxMaterials.SetColor(_weaponMaterial, look.bodyColor);
            _weaponRenderer.sharedMaterial = _weaponMaterial;
        }

        void OnDestroy()
        {
            ShapeTargets.Remove(this);
            // The body's root is our child and goes with us; the materials are ours to clean up.
            _look?.Destroy();
            if (_weaponMaterial != null) Destroy(_weaponMaterial);
            if (_markerMaterial != null) Destroy(_markerMaterial);
        }
    }

    /// <summary>
    /// Who a drawn body belongs to, so a bullet traced on this client knows whom it struck. It
    /// never takes damage itself: the server decides that.
    /// </summary>
    public sealed class RemoteTarget : IDamageable
    {
        public readonly int PlayerId;
        /// <summary>On our side: our bullets pass them by, as they do on the server.</summary>
        public bool Friendly;

        public RemoteTarget(int playerId)
        {
            PlayerId = playerId;
        }

        public bool IsAlive => true;
        public DamageResult ApplyDamage(in DamageInfo info) => default;
    }
}
