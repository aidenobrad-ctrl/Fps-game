using UnityEngine;
using UnityEngine.Rendering;
using Recoil.Client.Cosmetics;
using Recoil.Client.Visuals;
using Recoil.Client.Weapons;
using Recoil.Shared.Cosmetics;
using Recoil.Shared.Movement;
using Recoil.Shared.Weapons;

namespace Recoil.Client.Player
{
    /// <summary>
    /// The player's own body, the same soldier everyone else sees, in the player's own look.
    /// Look down and there are your chest, belt, legs and boots, walking, crouching and sliding
    /// as you do; on the ground is your whole shadow, head, arms and gun included.
    ///
    /// It is two soldiers posed alike. The one you see has its head (with the hair and
    /// headgear on it) and its arms folded away to nothing: the camera sits where the head
    /// would be, and the arms you see are the first-person ones on the weapon. It stands a
    /// little behind the eye, further the more you look down, so the camera never ends up
    /// inside the chest. The other is all there but drawn only as a shadow, holding your
    /// weapon. Neither has a collider, so nothing about it can be hit or block a shot.
    /// </summary>
    [DefaultExecutionOrder(50)]
    public sealed class LocalBodyView : MonoBehaviour
    {
        // How far the seen body stands behind the eye: a little looking ahead, more looking down.
        const float BackLevel = 0.08f, BackDown = 0.3f;
        // Folded away rather than removed, so the skin round the neck and shoulders closes up.
        static readonly Vector3 Folded = Vector3.one * 0.001f;

        LocalPlayerController _player;
        float _standEyeHeight;
        Transform _seenRoot, _shadowRoot;
        CharacterLookView _seen, _shadow;
        Transform _gun;
        WeaponBuild _held;
        CharacterLook _look;
        bool _shown = true;

        /// <summary>Gives <paramref name="player"/> a body. Returns null (and the player has hands only, as before) if the soldier model is missing.</summary>
        public static LocalBodyView Attach(LocalPlayerController player, float standEyeHeight)
        {
            if (player == null || !SoldierView.Available) return null;
            var view = player.gameObject.AddComponent<LocalBodyView>();
            view._player = player;
            view._standEyeHeight = standEyeHeight;
            try
            {
                view.Build();
            }
            catch (System.Exception e)
            {
                Debug.LogError("Recoil: the player's own body could not be built; playing with hands only. The cause follows.");
                Debug.LogException(e);
                Destroy(view);
                return null;
            }
            return view;
        }

        void Build()
        {
            _seenRoot = new GameObject("Own Body").transform;
            _seen = new CharacterLookView(_seenRoot, ShadowCastingMode.Off);
            _shadowRoot = new GameObject("Own Body Shadow").transform;
            _shadow = new CharacterLookView(_shadowRoot, ShadowCastingMode.ShadowsOnly);
            if (_seen.Soldier == null || _shadow.Soldier == null) throw new System.InvalidOperationException("the soldier model could not be built");

            SoldierView seen = _seen.Soldier;
            seen.Bone("Head").localScale = Folded;
            seen.Bone("UpperArmL").localScale = Folded;
            seen.Bone("UpperArmR").localScale = Folded;
            _seen.SetSide(false, false);
            _shadow.SetSide(false, false);
            Dress();
        }

        /// <summary>The player's look, as chosen on the Customize screen; again whenever it changes.</summary>
        void Dress()
        {
            CharacterLook look = CosmeticsLibrary.Local?.Look ?? _look ?? new CharacterLook();
            if (ReferenceEquals(look, _look)) return;
            _look = look;
            _seen.Apply(look);
            _shadow.Apply(look);
            _held = null;     // the weapon skin may have changed with it
        }

        /// <summary>The weapon in the shadow's hands, in the player's skin: rebuilt when the weapon in hand changes.</summary>
        void Arm()
        {
            WeaponBuild build = _player.Simulation != null ? _player.ActiveBuild : null;
            if (ReferenceEquals(build, _held)) return;
            _held = build;
            SoldierView soldier = _shadow.Soldier;
            if (_gun != null) Destroy(_gun.gameObject);
            _gun = null;
            soldier.Hold(null, null);
            if (build == null) return;

            ViewModelLayout layout = ViewModelBuilder.Build(soldier.WeaponMount, build, _look?.SkinFor(build.Weapon.weaponId), castShadows: true);
            _gun = layout.Root;
            if (_gun == null) return;
            _gun.localPosition = layout.Handgun ? new Vector3(-0.14f, -0.06f, 0.36f) : new Vector3(0f, 0f, -layout.RearZ - 0.03f);
            _gun.localRotation = layout.Kind == ViewModelKind.Blade || layout.Kind == ViewModelKind.Thrown ? Quaternion.Euler(-60f, 0f, 0f) : Quaternion.identity;
            foreach (Renderer renderer in _gun.GetComponentsInChildren<Renderer>(true))
                renderer.shadowCastingMode = ShadowCastingMode.ShadowsOnly;
            soldier.Hold(layout.Grip, layout.Support);
        }

        void LateUpdate()
        {
            if (_player == null || _seen == null) return;
            bool show = _player.Alive && _player.isActiveAndEnabled;
            if (show != _shown)
            {
                _shown = show;
                _seenRoot.gameObject.SetActive(show);
                _shadowRoot.gameObject.SetActive(show);
            }
            if (!show) return;

            Dress();
            Arm();

            MotorState motor = _player.MotorState;
            float yaw = _player.ViewYaw, pitch = _player.ViewPitch;
            Quaternion facing = Quaternion.Euler(0f, yaw, 0f);
            Vector3 feet = _player.ViewFeet;
            var motion = new SoldierMotion
            {
                Velocity = motor.Velocity,
                Yaw = yaw,
                Pitch = pitch,
                EyeHeight = _player.ViewEyeHeight,
                StandEyeHeight = _standEyeHeight,
                Stance = motor.Stance,
                Grounded = motor.Grounded,
            };

            // The shadow stands exactly where the player is, aiming where they aim.
            _shadowRoot.SetPositionAndRotation(feet, facing);
            _shadow.Animate(motion, Time.deltaTime);

            // The body you see stays upright under you (only looking up leans it back), a step behind the eye.
            float down = Mathf.Clamp01(pitch / 70f);
            _seenRoot.SetPositionAndRotation(feet - facing * Vector3.forward * Mathf.Lerp(BackLevel, BackDown, down), facing);
            motion.Pitch = Mathf.Min(pitch, 0f) * 0.5f;
            _seen.Animate(motion, Time.deltaTime);
        }

        // A player switched off (between rounds, say) takes their body with them; LateUpdate brings it back.
        void OnDisable()
        {
            _shown = false;
            if (_seenRoot != null) _seenRoot.gameObject.SetActive(false);
            if (_shadowRoot != null) _shadowRoot.gameObject.SetActive(false);
        }

        void OnDestroy()
        {
            _seen?.Destroy();
            _shadow?.Destroy();
            if (_seenRoot != null) Destroy(_seenRoot.gameObject);
            if (_shadowRoot != null) Destroy(_shadowRoot.gameObject);
        }
    }
}
