using System.Collections.Generic;
using UnityEngine;
using Recoil.Shared.Movement;

namespace Recoil.Client.Visuals
{
    /// <summary>What a body is doing this frame, for <see cref="SoldierView.Animate"/>.</summary>
    public struct SoldierMotion
    {
        /// <summary>World velocity, m/s.</summary>
        public Vector3 Velocity;
        /// <summary>Where they are looking, in degrees; positive pitch is down.</summary>
        public float Yaw, Pitch;
        public float EyeHeight, StandEyeHeight;
        public Stance Stance;
        public bool Grounded;
    }

    /// <summary>
    /// A player's body as the Blender-made armoured soldier: rigid segments (pelvis, torso,
    /// head, two-part arms and legs, hands and boots) hung from each other at their joints,
    /// and posed every frame from how the player is moving.
    ///
    /// The legs walk and run with the speed, step sideways when strafing, bend to crouch,
    /// tuck in the air and stretch out in a slide. The torso and head share the view's pitch,
    /// and the gun turns with them. With a gun in hand, each arm is solved to its grip: the
    /// right hand on the pistol grip, the left under the handguard, elbows down and out.
    ///
    /// Purely for looking at: no colliders, and the hitboxes are a separate, fixed set of
    /// shapes, so no pose makes anyone easier or harder to hit.
    /// </summary>
    public sealed class SoldierView
    {
        public const string Set = "Soldier";

        /// <summary>The model file is there and readable.</summary>
        public static bool Available => ModelLibrary.Has(Set);

        /// <summary>Every segment the soldier is made of, as named in the model file.</summary>
        public static readonly string[] Names =
        {
            "Pelvis", "Torso", "Head", "ThighL", "ShinL", "FootL", "ThighR", "ShinR", "FootR",
            "UpperArmL", "ForearmL", "HandL", "UpperArmR", "ForearmR", "HandR",
        };

        readonly Transform _root;
        readonly Dictionary<string, Transform> _bones = new Dictionary<string, Transform>();
        readonly Dictionary<string, ModelMesh> _models = new Dictionary<string, ModelMesh>();
        readonly List<(MeshRenderer Renderer, ModelZone[] Zones)> _renderers = new List<(MeshRenderer, ModelZone[])>();
        readonly Vector3 _pelvisRest;
        readonly float _thigh, _shin, _upperArm, _forearm;
        readonly Vector3 _upperRestL, _upperRestR, _foreRestL, _foreRestR;

        Material _suit, _trim, _helmet, _glow, _team;
        float _phase, _gait, _air, _slide;
        Transform _grip, _support;

        public Transform Root => _root;
        /// <summary>At the centre of the helmet, turning with the head: for headgear.</summary>
        public Transform HeadAnchor { get; }
        /// <summary>At the middle of the back plate, moving with the torso: for back items.</summary>
        public Transform BackAnchor { get; }
        /// <summary>Where a gun's origin goes. It turns with the view's pitch.</summary>
        public Transform WeaponMount { get; }
        readonly Transform _weaponPivot;

        public SoldierView(Transform parent, bool castShadows)
        {
            _root = new GameObject("Soldier").transform;
            _root.SetParent(parent, false);

            foreach (string name in Names)
            {
                ModelMesh model = ModelLibrary.Get(Set, name);
                _models[name] = model;
                var bone = new GameObject(name).transform;
                _bones[name] = bone;
                if (model == null) continue;
                MeshRenderer renderer = ModelLibrary.Attach(bone.gameObject, model, Zone, castShadows);
                _renderers.Add((renderer, model.Zones));
            }

            // Each segment hangs from the one it is jointed to, at its own pivot.
            Hang("Pelvis", null);
            Hang("Torso", "Pelvis");
            Hang("Head", "Torso");
            foreach (string side in new[] { "L", "R" })
            {
                Hang("Thigh" + side, "Pelvis");
                Hang("Shin" + side, "Thigh" + side);
                Hang("Foot" + side, "Shin" + side);
                Hang("UpperArm" + side, "Torso");
                Hang("Forearm" + side, "UpperArm" + side);
                Hang("Hand" + side, "Forearm" + side);
            }
            _pelvisRest = _bones["Pelvis"].localPosition;

            _thigh = Length("ThighL", "ShinL");
            _shin = Length("ShinL", "FootL");
            _upperArm = Length("UpperArmL", "ForearmL");
            _forearm = Length("ForearmL", "HandL");
            _upperRestL = Pivot("ForearmL") - Pivot("UpperArmL");
            _upperRestR = Pivot("ForearmR") - Pivot("UpperArmR");
            _foreRestL = Pivot("HandL") - Pivot("ForearmL");
            _foreRestR = Pivot("HandR") - Pivot("ForearmR");

            Transform head = _bones["Head"], torso = _bones["Torso"];
            HeadAnchor = new GameObject("Head Anchor").transform;
            HeadAnchor.SetParent(head, false);
            HeadAnchor.localPosition = new Vector3(0f, 0.165f, 0f);
            BackAnchor = new GameObject("Back Anchor").transform;
            BackAnchor.SetParent(torso, false);
            BackAnchor.localPosition = new Vector3(0f, 0.15f, 0f);
            // The gun's pivot is the right shoulder pocket.
            _weaponPivot = new GameObject("Weapon Pivot").transform;
            _weaponPivot.SetParent(torso, false);
            _weaponPivot.localPosition = new Vector3(0.13f, 0.36f, 0.05f);
            WeaponMount = new GameObject("Weapon Mount").transform;
            WeaponMount.SetParent(_weaponPivot, false);
        }

        Vector3 Pivot(string name) => _models[name] != null ? _models[name].Pivot : Vector3.zero;
        float Length(string from, string to) => Mathf.Max(0.05f, (Pivot(to) - Pivot(from)).magnitude);

        void Hang(string name, string parent)
        {
            Transform bone = _bones[name];
            bone.SetParent(parent == null ? _root : _bones[parent], false);
            bone.localPosition = Pivot(name) - (parent == null ? Vector3.zero : Pivot(parent));
        }

        Material Zone(ModelZone zone)
        {
            switch (zone)
            {
                case ModelZone.Dark: return ModelMaterials.Dark;
                case ModelZone.Metal: return ModelMaterials.Metal;
                case ModelZone.Glow: return _glow ?? GreyboxMaterials.Unlit(new Color(0.2f, 0.9f, 1f));
                case ModelZone.Trim: return _trim ?? ModelMaterials.Metal;
                case ModelZone.Team: return _team ?? ModelMaterials.Dark;
                case ModelZone.Helmet: return _helmet ?? ModelMaterials.Dark;
                default: return _suit ?? ModelMaterials.Dark;
            }
        }

        /// <summary>Dresses the soldier: the suit's colour and pattern, its trim, the helmet, and the visor's glow.</summary>
        public void SetMaterials(Material suit, Material trim, Material helmet, Material glow)
        {
            _suit = suit;
            _trim = trim;
            _helmet = helmet;
            _glow = glow;
            Refresh();
        }

        /// <summary>The shoulder pads' colour: the team's, or null for plain dark pads.</summary>
        public void SetTeam(Material team)
        {
            if (ReferenceEquals(team, _team)) return;
            _team = team;
            Refresh();
        }

        void Refresh()
        {
            foreach ((MeshRenderer renderer, ModelZone[] zones) in _renderers)
            {
                var materials = new Material[zones.Length];
                for (int i = 0; i < zones.Length; i++) materials[i] = Zone(zones[i]);
                renderer.sharedMaterials = materials;
            }
        }

        public void SetVisible(bool visible)
        {
            if (_root.gameObject.activeSelf != visible) _root.gameObject.SetActive(visible);
        }

        /// <summary>Points for the hands to hold: the pistol grip and the handguard. Null for empty hands.</summary>
        public void Hold(Transform grip, Transform support)
        {
            _grip = grip;
            _support = support;
        }

        // ------------------------------------------------------------------ posing

        /// <summary>Poses the body for this frame.</summary>
        public void Animate(in SoldierMotion motion, float dt)
        {
            dt = Mathf.Clamp(dt, 0f, 0.1f);
            Vector3 flat = new Vector3(motion.Velocity.x, 0f, motion.Velocity.z);
            float speed = flat.magnitude;
            // Movement in the body's own frame: z forward, x to the right.
            float r = -motion.Yaw * Mathf.Deg2Rad;
            float localX = flat.x * Mathf.Cos(r) + flat.z * Mathf.Sin(r);
            float localZ = -flat.x * Mathf.Sin(r) + flat.z * Mathf.Cos(r);

            bool sliding = motion.Stance == Stance.Sliding;
            bool airborne = !motion.Grounded && !sliding;
            _gait = Mathf.MoveTowards(_gait, sliding || airborne ? 0f : Mathf.Clamp01(speed / 0.8f), dt * 6f);
            _air = Mathf.MoveTowards(_air, airborne ? 1f : 0f, dt * 6f);
            _slide = Mathf.MoveTowards(_slide, sliding ? 1f : 0f, dt * 8f);

            // A full stride every 1.6 m at a run; a sprint's is longer.
            float stride = Mathf.Lerp(1.4f, 2.1f, Mathf.InverseLerp(5.6f, 8.6f, speed));
            _phase = Mathf.Repeat(_phase + speed * dt * (2f * Mathf.PI / stride), 2f * Mathf.PI);
            float amplitude = Mathf.Clamp(speed / 5.6f, 0f, 1.3f) * _gait;
            float forward = speed > 0.05f ? localZ / speed : 1f;
            float sideways = speed > 0.05f ? localX / speed : 0f;

            // Crouching lowers the hips; the legs bend to keep the feet on the floor.
            float stand = Mathf.Max(0.5f, motion.StandEyeHeight);
            float drop = Mathf.Clamp(stand - motion.EyeHeight, 0f, 0.9f) * 0.62f;
            drop = Mathf.Lerp(drop, 0.48f, _slide);
            float bob = amplitude * 0.035f * Mathf.Abs(Mathf.Cos(_phase));
            Transform pelvis = _bones["Pelvis"];
            pelvis.localPosition = _pelvisRest - new Vector3(0f, drop + bob, 0f);
            float hipHeight = _pelvisRest.y - 0.03f - drop - bob;
            LegBend(hipHeight, out float thighBase, out float kneeBase);

            Leg("L", _phase, thighBase, kneeBase, amplitude, forward, sideways, front: false);
            Leg("R", _phase + Mathf.PI, thighBase, kneeBase, amplitude, forward, sideways, front: true);

            // The upper body: a lean into a run, back in a slide, and a share of the view's pitch.
            float pitch = Mathf.Clamp(motion.Pitch, -80f, 80f);
            float lean = amplitude * 7f * Mathf.Clamp01(forward) - _slide * 18f;
            _bones["Torso"].localRotation = Quaternion.Euler(pitch * 0.4f + lean, -_slide * 15f, 0f);
            _bones["Head"].localRotation = Quaternion.Euler(pitch * 0.35f - lean * 0.6f, _slide * 15f, 0f);
            _weaponPivot.localRotation = Quaternion.Euler(pitch * 0.6f - lean, _slide * 15f, 0f);

            Arms();
        }

        /// <summary>Hip and knee angles that put the ankle straight under a hip at this height.</summary>
        void LegBend(float hipHeight, out float thigh, out float knee)
        {
            const float ankle = 0.09f;
            float reach = Mathf.Clamp(hipHeight - ankle, 0.25f, _thigh + _shin - 0.005f);
            float hip = Mathf.Acos(Mathf.Clamp((_thigh * _thigh + reach * reach - _shin * _shin) / (2f * _thigh * reach), -1f, 1f));
            float inner = Mathf.Acos(Mathf.Clamp((_thigh * _thigh + _shin * _shin - reach * reach) / (2f * _thigh * _shin), -1f, 1f));
            // The thigh swings forward (negative about x) and the shin folds back.
            thigh = -hip * Mathf.Rad2Deg;
            knee = (Mathf.PI - inner) * Mathf.Rad2Deg;
        }

        void Leg(string side, float phase, float thighBase, float kneeBase, float amplitude, float forward, float sideways, bool front)
        {
            float swing = Mathf.Sin(phase);
            // The knee folds most while the leg swings through.
            float lift = Mathf.Max(0f, Mathf.Cos(phase)) * amplitude * 42f;
            float pitch = thighBase - swing * amplitude * 30f * forward - lift * 0.4f;
            float roll = swing * amplitude * 16f * sideways;
            float knee = kneeBase + lift;

            // In the air the knees come up; in a slide one leg leads and the other folds under.
            pitch = Mathf.Lerp(pitch, front ? -38f : -12f, _air);
            knee = Mathf.Lerp(knee, front ? 58f : 32f, _air);
            pitch = Mathf.Lerp(pitch, front ? -78f : -18f, _slide);
            knee = Mathf.Lerp(knee, front ? 8f : 100f, _slide);

            _bones["Thigh" + side].localRotation = Quaternion.Euler(pitch, 0f, roll);
            _bones["Shin" + side].localRotation = Quaternion.Euler(knee, 0f, 0f);
            // Keep the sole flat on the floor, toes lifting a little through the swing.
            _bones["Foot" + side].localRotation = Quaternion.Euler(-(pitch + knee) - lift * 0.2f, 0f, -roll);
        }

        void Arms()
        {
            Quaternion body = _root.rotation;
            if (_grip == null)
            {
                // Empty hands: arms a little away from the sides, elbows soft.
                _bones["UpperArmL"].localRotation = Quaternion.Euler(-6f, 0f, -7f);
                _bones["UpperArmR"].localRotation = Quaternion.Euler(-6f, 0f, 7f);
                _bones["ForearmL"].localRotation = Quaternion.Euler(-14f, 0f, 0f);
                _bones["ForearmR"].localRotation = Quaternion.Euler(-14f, 0f, 0f);
                return;
            }

            Transform gun = WeaponMount;
            Vector3 up = gun.up, right = gun.right;
            // The wrist sits above and behind the grip, the support hand cups the handguard.
            Vector3 rightWrist = _grip.position + up * 0.055f - gun.forward * 0.02f;
            Transform supportPoint = _support != null ? _support : _grip;
            Vector3 leftWrist = supportPoint.position - up * 0.02f - right * 0.025f + (_support == null ? gun.forward * 0.08f : Vector3.zero);
            Reach("R", rightWrist, body * new Vector3(0.7f, -1f, -0.3f), body);
            Reach("L", leftWrist, body * new Vector3(-0.8f, -1f, -0.1f), body);
        }

        /// <summary>Solves an arm so its wrist reaches <paramref name="target"/>, the elbow bending towards <paramref name="pole"/>.</summary>
        void Reach(string side, Vector3 target, Vector3 pole, Quaternion body)
        {
            Transform upper = _bones["UpperArm" + side], fore = _bones["Forearm" + side], hand = _bones["Hand" + side];
            Vector3 upperRest = side == "L" ? _upperRestL : _upperRestR;
            Vector3 foreRest = side == "L" ? _foreRestL : _foreRestR;

            Vector3 shoulder = upper.position;
            Vector3 toTarget = target - shoulder;
            float distance = Mathf.Clamp(toTarget.magnitude, 0.05f, _upperArm + _forearm - 0.002f);
            Vector3 direction = toTarget.sqrMagnitude > 1e-6f ? toTarget.normalized : body * Vector3.forward;
            float cosA = Mathf.Clamp((_upperArm * _upperArm + distance * distance - _forearm * _forearm) / (2f * _upperArm * distance), -1f, 1f);
            float sinA = Mathf.Sqrt(1f - cosA * cosA);
            Vector3 bend = Vector3.ProjectOnPlane(pole, direction);
            bend = bend.sqrMagnitude > 1e-6f ? bend.normalized : body * Vector3.down;
            Vector3 elbow = shoulder + direction * (cosA * _upperArm) + bend * (sinA * _upperArm);
            Vector3 wrist = shoulder + direction * distance;

            upper.rotation = Quaternion.FromToRotation(body * upperRest, elbow - shoulder) * body;
            fore.rotation = Quaternion.FromToRotation(body * foreRest, wrist - elbow) * body;
            hand.rotation = fore.rotation;
        }

        public void Destroy()
        {
            if (_root != null) Object.Destroy(_root.gameObject);
        }
    }
}
