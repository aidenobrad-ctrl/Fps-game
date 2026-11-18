using UnityEngine;
using Recoil.Client.Cosmetics;
using Recoil.Shared.Weapons;

namespace Recoil.Client.Weapons
{
    /// <summary>What the first-person weapon model needs for one rendered frame.</summary>
    public struct ViewModelInput
    {
        public float AdsAmount;
        public bool Sprinting;
        /// <summary>Hands are busy (mantling, or putting the weapon away): drop it out of view.</summary>
        public bool Lowered;
        public bool Reloading;
        public float ReloadProgress;
        /// <summary>Charge weapons: 0..1 while the trigger is held.</summary>
        public float Charge;
        /// <summary>Do not draw the model at all (a full-screen scope is up).</summary>
        public bool Hidden;
        /// <summary>0 = standing still, 1 = sprint speed. 0 while airborne.</summary>
        public float MoveAmount;
        public float Yaw;
        public float Pitch;
        /// <summary>Nothing left in the magazine: a launcher shows no rocket.</summary>
        public bool MagazineEmpty;
        /// <summary>Reloads by changing the magazine, rather than a round at a time.</summary>
        public bool SwapsMagazine;
        public bool Airborne;
    }

    /// <summary>
    /// The weapon you see in first person. Purely cosmetic: it is posed from weapon and
    /// movement state each frame and never feeds back into the simulation. The model itself
    /// comes from <see cref="ViewModelBuilder"/>, and all motion is procedural, so no art or
    /// animation clips are needed yet.
    /// </summary>
    public sealed class WeaponViewModel : MonoBehaviour
    {
        static readonly Vector3 SprintOffset = new Vector3(-0.06f, -0.035f, -0.05f);
        static readonly Vector3 SprintEuler = new Vector3(14f, -32f, 12f);
        static readonly Vector3 HandgunSprintOffset = new Vector3(-0.02f, -0.07f, -0.06f);
        static readonly Vector3 HandgunSprintEuler = new Vector3(32f, -8f, 4f);
        static readonly Vector3 ReloadOffset = new Vector3(0f, -0.09f, -0.02f);
        static readonly Vector3 ReloadEuler = new Vector3(-22f, 8f, 22f);
        static readonly Vector3 LoweredOffset = new Vector3(0f, -0.34f, -0.05f);
        static readonly Vector3 LoweredEuler = new Vector3(28f, 0f, 0f);
        const float SwingTime = 0.3f;

        ViewModelLayout _layout;
        FirstPersonArms _arms;
        Transform _muzzleAnchor;
        Vector3 _magazineRest;

        float _kick, _kickVelocity;
        float _sprintBlend, _reloadBlend, _lowerBlend = 1f;
        float _swing;
        Vector2 _sway;
        float _bobTime, _breathTime, _air, _landing;
        bool _wasAirborne;
        float _lastYaw, _lastPitch;
        bool _hasLastAngles;

        /// <summary>
        /// Follows the muzzle of whichever weapon is shown. It outlives weapon switches, so
        /// effects can stay parented to it.
        /// </summary>
        public Transform Muzzle
        {
            get
            {
                if (_muzzleAnchor == null)
                {
                    _muzzleAnchor = new GameObject("MuzzleAnchor").transform;
                    _muzzleAnchor.SetParent(transform, false);
                }
                return _muzzleAnchor;
            }
        }

        WeaponBuild _shownBuild;

        void OnEnable()
        {
            if (CosmeticsLibrary.Local != null) CosmeticsLibrary.Local.Changed += OnLookChanged;
        }

        void OnDisable()
        {
            if (CosmeticsLibrary.Local != null) CosmeticsLibrary.Local.Changed -= OnLookChanged;
        }

        /// <summary>A new skin chosen while this weapon is out: put it on straight away.</summary>
        void OnLookChanged()
        {
            if (_shownBuild != null) Show(_shownBuild);
        }

        /// <summary>Replaces the model with the one for this weapon and its attachments, in the player's skin for it.</summary>
        public void Show(WeaponBuild build)
        {
            if (_layout.Root != null) Destroy(_layout.Root.gameObject);

            _shownBuild = build;
            _layout = ViewModelBuilder.Build(transform, build, CosmeticsLibrary.SkinFor(build.Weapon.weaponId));
            if (_layout.Magazine != null) _magazineRest = _layout.Magazine.localPosition;
            try
            {
                _arms = FirstPersonArms.Attach(_layout, CosmeticsLibrary.Local?.Look, transform);
            }
            catch (System.Exception e)
            {
                // The weapon is still there to shoot with; only the arms are missing.
                _arms = null;
                Debug.LogException(e, this);
            }
            _kick = _kickVelocity = 0f;
            _swing = 0f;
            _reloadBlend = 0f;
            // Start lowered so the new weapon rises into view.
            _lowerBlend = 1f;
            _layout.Root.localPosition = _layout.HipPosition + LoweredOffset;
            _layout.Root.localRotation = Quaternion.Euler(_layout.HipEuler);
        }

        /// <summary>Call once for every shot fired or swing started.</summary>
        public void OnFired(WeaponBuild build)
        {
            if (_layout.Kind == ViewModelKind.Blade)
            {
                _swing = SwingTime;
                return;
            }

            // Heavier-hitting weapons kick the model harder.
            WeaponStats stats = build.Weapon.stats;
            float punch = stats.damage * Mathf.Max(1, stats.pellets);
            _kickVelocity += Mathf.Lerp(12f, 34f, Mathf.InverseLerp(15f, 130f, punch));
        }

        public void Tick(in ViewModelInput input, float deltaTime)
        {
            if (_layout.Root == null) return;
            float dt = Mathf.Min(deltaTime, 1f / 30f);

            if (_layout.Root.gameObject.activeSelf == input.Hidden) _layout.Root.gameObject.SetActive(!input.Hidden);

            _sprintBlend = Mathf.MoveTowards(_sprintBlend, input.Sprinting ? 1f : 0f, dt / 0.16f);
            _lowerBlend = Mathf.MoveTowards(_lowerBlend, input.Lowered ? 1f : 0f, dt / (input.Lowered ? 0.12f : 0.24f));

            // Dips into the reload pose, holds, and comes back up as the reload completes.
            float reloadTarget = input.Reloading
                ? Mathf.Clamp01(Mathf.Sin(Mathf.Clamp01(input.ReloadProgress) * Mathf.PI) * 2.5f)
                : 0f;
            _reloadBlend = Mathf.Lerp(_reloadBlend, reloadTarget, 1f - Mathf.Exp(-16f * dt));

            // Recoil kick: an impulse per shot, pulled back by a damped spring.
            const float stiffness = 260f, damping = 26f;
            _kickVelocity += (-stiffness * _kick - damping * _kickVelocity) * dt;
            _kick += _kickVelocity * dt;

            // Sway: the weapon lags slightly behind the view as it turns.
            if (!_hasLastAngles)
            {
                _lastYaw = input.Yaw;
                _lastPitch = input.Pitch;
                _hasLastAngles = true;
            }
            float yawRate = Mathf.DeltaAngle(_lastYaw, input.Yaw) / Mathf.Max(deltaTime, 0.0001f);
            float pitchRate = (input.Pitch - _lastPitch) / Mathf.Max(deltaTime, 0.0001f);
            _lastYaw = input.Yaw;
            _lastPitch = input.Pitch;
            var swayTarget = new Vector2(
                Mathf.Clamp(-yawRate * 0.00012f, -0.025f, 0.025f),
                Mathf.Clamp(pitchRate * 0.00012f, -0.025f, 0.025f));
            _sway = Vector2.Lerp(_sway, swayTarget, 1f - Mathf.Exp(-12f * dt));

            float ads = Mathf.SmoothStep(0f, 1f, input.AdsAmount);

            // Steps: the weapon dips as each foot lands and swings a little from side to side,
            // more at a run, much less when aiming. Two steps to each cycle of _bobTime.
            float move = input.Airborne ? 0f : input.MoveAmount;
            _bobTime += dt * Mathf.Lerp(7.5f, 12.5f, move) * (move > 0.02f ? 1f : 0f);
            float stride = move * (1f - 0.85f * ads) * (1f + 0.6f * _sprintBlend);
            float dip = Mathf.Abs(Mathf.Sin(_bobTime));
            var bob = new Vector3(Mathf.Sin(_bobTime) * 0.009f, -dip * 0.009f + 0.0045f, 0f) * stride;
            var bobTurn = new Vector3(dip * 1.2f, Mathf.Sin(_bobTime) * 1.1f, Mathf.Sin(_bobTime) * -1.8f) * stride;

            // Breathing while standing still: a slow rise and fall, smaller when aiming.
            _breathTime += dt * 1.6f;
            float breath = (1f - move) * (1f - 0.7f * ads);
            bob += new Vector3(0f, Mathf.Sin(_breathTime) * 0.0016f, 0f) * breath;
            bobTurn += new Vector3(Mathf.Sin(_breathTime) * 0.35f, Mathf.Sin(_breathTime * 0.5f) * 0.2f, 0f) * breath;

            // In the air the weapon floats up a little; landing knocks it down.
            if (_wasAirborne && !input.Airborne) _landing = 1f;
            _wasAirborne = input.Airborne;
            _air = Mathf.MoveTowards(_air, input.Airborne ? 1f : 0f, dt * 5f);
            _landing = Mathf.MoveTowards(_landing, 0f, dt * 4f);
            float land = Mathf.Sin(_landing * Mathf.PI) * (1f - 0.6f * ads);
            bob += new Vector3(0f, 0.008f * _air - 0.018f * land, 0f);
            bobTurn += new Vector3(-2f * _air + 4f * land, 0f, 0f);

            Vector3 position = Vector3.Lerp(_layout.HipPosition, _layout.AdsPosition, ads);
            // A gun is canted at the hip and comes level as it is raised to aim; a blade only turns a little.
            Quaternion rotation = Quaternion.Slerp(Quaternion.Euler(_layout.HipEuler), Quaternion.identity,
                _layout.Kind == ViewModelKind.Gun || _layout.Kind == ViewModelKind.Launcher ? ads : ads * 0.3f);

            float sprint = _sprintBlend * (1f - ads);
            position += (_layout.Handgun ? HandgunSprintOffset : SprintOffset) * sprint;
            rotation *= Quaternion.Euler((_layout.Handgun ? HandgunSprintEuler : SprintEuler) * sprint);

            position += ReloadOffset * _reloadBlend + LoweredOffset * _lowerBlend;
            rotation *= Quaternion.Euler(ReloadEuler * _reloadBlend + LoweredEuler * _lowerBlend);

            float kickScale = Mathf.Lerp(1f, 0.5f, ads);
            position += new Vector3(_sway.x, _sway.y, 0f) * (1f - 0.7f * ads) + bob;
            position += Vector3.back * (_kick * 0.06f * kickScale);
            rotation *= Quaternion.Euler(-_kick * 3.2f * kickScale + bobTurn.x, bobTurn.y, bobTurn.z);

            // Charging: the weapon draws back and trembles harder as power builds.
            if (input.Charge > 0f)
            {
                float tremble = input.Charge * 0.004f;
                position += new Vector3(Random.Range(-tremble, tremble), Random.Range(-tremble, tremble), -0.03f * input.Charge);
            }

            // A blade sweeps across the view from right to left.
            if (_swing > 0f)
            {
                _swing -= dt;
                float t = 1f - Mathf.Clamp01(_swing / SwingTime);
                float arc = Mathf.Sin(t * Mathf.PI);
                position += new Vector3(Mathf.Lerp(0.08f, -0.32f, t), 0.06f * arc, 0.12f * arc);
                rotation *= Quaternion.Euler(Mathf.Lerp(-10f, 35f, t), Mathf.Lerp(40f, -75f, t), -30f * arc);
            }

            _layout.Root.localPosition = position;
            _layout.Root.localRotation = rotation;

            // The magazine drops out and the new one goes in during a reload; a launcher
            // shows no rocket once it has fired one.
            if (_layout.Magazine != null)
            {
                float out01 = 0f;
                if (input.Reloading && input.SwapsMagazine)
                {
                    float t = Mathf.Clamp01(input.ReloadProgress);
                    out01 = t < 0.45f ? Mathf.SmoothStep(0f, 1f, t / 0.25f) : Mathf.SmoothStep(1f, 0f, (t - 0.45f) / 0.3f);
                }
                _layout.Magazine.localPosition = _magazineRest + _layout.MagazineOut * (0.16f * out01);
                bool show = out01 < 0.95f;
                if (_layout.Kind == ViewModelKind.Launcher && input.MagazineEmpty && !(input.Reloading && input.ReloadProgress > 0.5f)) show = false;
                if (_layout.Magazine.gameObject.activeSelf != show) _layout.Magazine.gameObject.SetActive(show);
            }
            _arms?.Update();

            Transform anchor = Muzzle;
            anchor.SetPositionAndRotation(_layout.Muzzle.position, _layout.Muzzle.rotation);
        }
    }
}
