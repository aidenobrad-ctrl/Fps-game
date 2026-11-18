using UnityEngine;
using Recoil.Client.Visuals;
using Recoil.Shared.Combat;
using Recoil.Shared.Cosmetics;
using Recoil.Shared.Match;
using Recoil.Shared.Movement;
using Recoil.Shared.Simulation;

namespace Recoil.Client.FiringRange
{
    /// <summary>
    /// A practice target: the same soldier a player is, in a bright training uniform, with a
    /// player's hitboxes (head, body, limbs). It takes damage like a real opponent, flashes
    /// when hit, drops when its health runs out and stands back up a moment later. One that
    /// is being moved along a line walks as it goes.
    ///
    /// The model is only looked at. What a bullet meets is the standard set of hitboxes
    /// (<see cref="UnityCharacterBody"/>), so practice here carries over to a match.
    /// </summary>
    public sealed class TargetDummy : MonoBehaviour, IShapeTarget
    {
        const float FlashTime = 0.12f;
        const float BarWidth = 0.6f;
        /// <summary>Targets face back up the range, towards the firing line.</summary>
        const float Facing = 180f;

        // So a row of targets is not a row of twins.
        static readonly string[] Headgear = { "none", "cap", "helmet", "beanie", "headset", "bandana" };
        static readonly string[] SkinTones = { "medium", "fair", "tan", "light", "brown", "olive", "deep", "porcelain" };
        static readonly string[] Hairstyles = { "crew", "side_part", "buzz", "curly", "slick_back", "bun", "mohawk", "shaved", "crew" };
        static MovementConfig _shape;
        static int _made;

        public float respawnDelay = 1.5f;

        UnityCharacterBody _body;
        CharacterLookView _look;
        Health _health;
        Collider _blocker;
        Material _barMaterial;
        Transform _healthBar;
        Renderer _barRenderer;
        float _standEyeHeight;
        float _flash;
        float _respawnTimer;
        bool _present = true;
        Vector3 _lastPosition, _velocity;

        public Health Health => _health;

        // For the check of bullets by plain geometry (ShapeTargets).
        IDamageable IShapeTarget.Owner => _health;
        bool IShapeTarget.Hittable => _present;
        BodyPose IShapeTarget.Pose => new BodyPose { Position = transform.position, Yaw = transform.eulerAngles.y + Facing, EyeHeight = _standEyeHeight };
        float IShapeTarget.StandEyeHeight => _standEyeHeight;

        public static TargetDummy Create(Transform parent, string name, Vector3 position, float maxHealth = 100f)
        {
            var go = new GameObject(name) { layer = GameLayers.Character };
            go.transform.SetParent(parent, false);
            go.transform.localPosition = position;

            var dummy = go.AddComponent<TargetDummy>();
            dummy.Build(maxHealth);
            return dummy;
        }

        void Build(float maxHealth)
        {
            _health = gameObject.AddComponent<Health>();
            _health.maxHealth = maxHealth;
            _health.Revive();
            _health.Damaged += OnDamaged;
            _health.Died += OnDied;

            // Kinematic body: lets the target be moved around without rebuilding static colliders.
            var body = gameObject.AddComponent<Rigidbody>();
            body.isKinematic = true;
            body.useGravity = false;

            // Blocks movement. On the Character layer, so bullets pass through it to the hitboxes.
            var blocker = gameObject.AddComponent<CapsuleCollider>();
            blocker.radius = 0.3f;
            blocker.height = 1.8f;
            blocker.center = new Vector3(0f, 0.9f, 0f);
            _blocker = blocker;

            // A player's hitboxes, standing, and the soldier drawn over them.
            if (_shape == null) _shape = ScriptableObject.CreateInstance<MovementConfig>();
            _standEyeHeight = _shape.standEyeHeight;
            _body = new UnityCharacterBody(name, _shape, withController: false, server: false);
            _body.Root.SetParent(transform, false);
            _body.Root.localPosition = Vector3.zero;
            _body.Root.localRotation = Quaternion.Euler(0f, Facing, 0f);
            _body.SetOwner(_health);

            _look = new CharacterLookView(_body);
            _look.Apply(new CharacterLook
            {
                // Training orange over dark gear: nobody mistakes one for a player.
                suitColor = "#D9662B",
                trimColor = "#2B2E34",
                pattern = "plain",
                headgear = Headgear[_made % Headgear.Length],
                skin = SkinTones[_made % SkinTones.Length],
                hair = Hairstyles[_made % Hairstyles.Length],
                back = "none",
            });
            _look.SetSide(true, friendly: false);
            _made++;

            _barMaterial = new Material(GreyboxMaterials.Unlit(Color.green));
            GameObject bar = GreyboxKit.Visual(transform, "HealthBar", PrimitiveType.Cube,
                new Vector3(0f, 2.02f, 0f), new Vector3(BarWidth, 0.05f, 0.03f), _barMaterial, castShadows: false);
            _healthBar = bar.transform;
            _barRenderer = bar.GetComponent<Renderer>();
            RefreshHealthBar();

            _lastPosition = transform.position;
            ShapeTargets.Add(this);
        }

        void OnDamaged(DamageInfo info, DamageResult result)
        {
            _flash = FlashTime;
            RefreshHealthBar();
        }

        void OnDied(DamageInfo info)
        {
            SetPresent(false);
            _respawnTimer = respawnDelay;
        }

        void Update()
        {
            float dt = Time.deltaTime;

            // How fast it is being moved, smoothed, so the legs walk at the pace it travels.
            if (dt > 0f)
            {
                Vector3 moved = (transform.position - _lastPosition) / dt;
                _velocity = Vector3.Lerp(_velocity, moved, 1f - Mathf.Exp(-12f * dt));
            }
            _lastPosition = transform.position;

            if (_present)
            {
                _look.Animate(new SoldierMotion
                {
                    Velocity = _velocity,
                    Yaw = transform.eulerAngles.y + Facing,
                    Pitch = 0f,
                    EyeHeight = _standEyeHeight,
                    StandEyeHeight = _standEyeHeight,
                    Stance = Stance.Standing,
                    Grounded = true,
                }, dt);
            }

            if (_flash > 0f)
            {
                _flash -= dt;
                _look.Flash(Mathf.Clamp01(_flash / FlashTime));
            }

            if (_respawnTimer > 0f)
            {
                _respawnTimer -= dt;
                if (_respawnTimer <= 0f)
                {
                    _health.Revive();
                    SetPresent(true);
                    RefreshHealthBar();
                }
            }
        }

        void SetPresent(bool present)
        {
            _present = present;
            _blocker.enabled = present;
            _body.SetHittable(present);
            _body.Root.gameObject.SetActive(present);
            _barRenderer.enabled = present;
            if (present)
            {
                _flash = 0f;
                _look.Flash(0f);
            }
        }

        void RefreshHealthBar()
        {
            float fraction = _health.Fraction;
            _healthBar.localScale = new Vector3(BarWidth * Mathf.Max(fraction, 0.001f), 0.05f, 0.03f);
            GreyboxMaterials.SetColor(_barMaterial, Color.Lerp(new Color(1f, 0.25f, 0.2f), new Color(0.3f, 1f, 0.45f), fraction));
        }

        void OnDestroy()
        {
            ShapeTargets.Remove(this);
            // The body's root is our child and goes with us; the materials are ours to clean up.
            _look?.Destroy();
            if (_barMaterial != null) Destroy(_barMaterial);
        }
    }
}
