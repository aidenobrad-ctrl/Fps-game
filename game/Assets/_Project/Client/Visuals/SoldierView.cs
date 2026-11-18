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
    /// A player's body as the Blender-made soldier: a realistic body and face (Body), the
    /// uniform, gloves and boots (Uniform) and the plate carrier and belt kit (Kit), each a
    /// skinned mesh over one fifteen-bone skeleton, posed every frame from how the player is
    /// moving. Near the joints the skin follows two bones, so elbows, knees, shoulders and
    /// hips bend smoothly.
    ///
    /// The legs walk and run with the speed, step sideways when strafing, bend to crouch,
    /// tuck in the air and stretch out in a slide. The torso and head share the view's pitch,
    /// and the gun turns with them. With a gun in hand, each arm is solved to its grip: the
    /// right hand on the pistol grip, the left under the handguard, elbows down and out.
    ///
    /// Purely for looking at: no colliders, and the hitboxes are a separate, fixed set of
    /// shapes, so no pose or outfit makes anyone easier or harder to hit.
    /// </summary>
    public sealed class SoldierView
    {
        public const string Set = "Soldier";

        /// <summary>The bones the animation drives, as named in the model file.</summary>
        public static readonly string[] Names =
        {
            "Pelvis", "Torso", "Head", "ThighL", "ShinL", "FootL", "ThighR", "ShinR", "FootR",
            "UpperArmL", "ForearmL", "HandL", "UpperArmR", "ForearmR", "HandR",
        };

        /// <summary>The model file is there, readable, and has the body and every bone.</summary>
        public static bool Available
        {
            get
            {
                if (ModelLibrary.Get(Set, "Body") == null) return false;
                var present = new HashSet<string>();
                foreach (ModelBone bone in ModelLibrary.Bones(Set)) present.Add(bone.Name);
                foreach (string name in Names)
                {
                    if (!present.Contains(name)) return false;
                }
                return true;
            }
        }

        readonly Transform _root;
        readonly Dictionary<string, Transform> _bones = new Dictionary<string, Transform>();
        readonly Dictionary<string, Vector3> _pivots = new Dictionary<string, Vector3>();
        readonly List<(SkinnedMeshRenderer Renderer, ModelZone[] Zones)> _parts = new List<(SkinnedMeshRenderer, ModelZone[])>();
        readonly Vector3 _pelvisRest;
        readonly float _thigh, _shin, _upperArm, _forearm, _ankle, _hipDrop;
        readonly Vector3 _upperRestL, _upperRestR, _foreRestL, _foreRestR;

        Material _uniform, _gear, _skin, _lips, _team;
        float _phase, _gait, _air, _slide, _sprint, _time;
        Transform _grip, _support;

        public Transform Root => _root;
        /// <summary>Where a gun's origin goes. It turns with the view's pitch.</summary>
        public Transform WeaponMount { get; }
        readonly Transform _weaponPivot;

        public SoldierView(Transform parent, bool castShadows)
        {
            _root = new GameObject("Soldier").transform;
            _root.SetParent(parent, false);
            try
            {
                // The skeleton, from the file: each bone at its joint, hanging from its parent.
                IReadOnlyList<ModelBone> skeleton = ModelLibrary.Bones(Set);
                var transforms = new Transform[skeleton.Count];
                for (int i = 0; i < skeleton.Count; i++)
                {
                    ModelBone bone = skeleton[i];
                    var t = new GameObject(bone.Name).transform;
                    Transform holder = bone.Parent < 0 ? _root : transforms[bone.Parent];
                    t.SetParent(holder, false);
                    t.localPosition = bone.Pivot - (bone.Parent < 0 ? Vector3.zero : skeleton[bone.Parent].Pivot);
                    transforms[i] = t;
                    _bones[bone.Name] = t;
                    _pivots[bone.Name] = bone.Pivot;
                }

                // Every skinned mesh in the file, all on the one skeleton.
                foreach (ModelMesh model in ModelLibrary.All(Set))
                {
                    if (!model.Skinned) continue;
                    var meshObject = new GameObject(model.Name);
                    meshObject.transform.SetParent(_root, false);
                    var renderer = meshObject.AddComponent<SkinnedMeshRenderer>();
                    renderer.sharedMesh = model.Mesh;
                    renderer.bones = transforms;
                    renderer.rootBone = _bones["Pelvis"];
                    // Generous, so a crouch or a slide never takes the body outside its bounds.
                    renderer.localBounds = new Bounds(Vector3.zero, new Vector3(2.4f, 2.8f, 2.4f));
                    renderer.shadowCastingMode = castShadows ? UnityEngine.Rendering.ShadowCastingMode.On : UnityEngine.Rendering.ShadowCastingMode.Off;
                    renderer.receiveShadows = castShadows;
                    // The uniform's and the kit's baked maps: the cloth's weave and stitching, and the shade in its folds.
                    ModelMaterials.ApplyMaps(renderer, model.Name, model.TexelScale);
                    _parts.Add((renderer, model.Zones));
                }
                Refresh();

                _pelvisRest = _bones["Pelvis"].localPosition;
                _thigh = Length("ThighL", "ShinL");
                _shin = Length("ShinL", "FootL");
                _upperArm = Length("UpperArmL", "ForearmL");
                _forearm = Length("ForearmL", "HandL");
                _ankle = _pivots["FootL"].y;
                _hipDrop = _pivots["Pelvis"].y - _pivots["ThighL"].y;
                _upperRestL = _pivots["ForearmL"] - _pivots["UpperArmL"];
                _upperRestR = _pivots["ForearmR"] - _pivots["UpperArmR"];
                _foreRestL = _pivots["HandL"] - _pivots["ForearmL"];
                _foreRestR = _pivots["HandR"] - _pivots["ForearmR"];

                // The gun's pivot is the right shoulder pocket.
                _weaponPivot = new GameObject("Weapon Pivot").transform;
                _weaponPivot.SetParent(_bones["Torso"], false);
                _weaponPivot.localPosition = new Vector3(0.13f, 0.36f, 0.05f);
                WeaponMount = new GameObject("Weapon Mount").transform;
                WeaponMount.SetParent(_weaponPivot, false);
            }
            catch
            {
                // Leave nothing half built behind for whoever handles the failure.
                Object.Destroy(_root.gameObject);
                throw;
            }
        }

        float Length(string from, string to) => Mathf.Max(0.05f, (_pivots[to] - _pivots[from]).magnitude);

        /// <summary>A bone of the skeleton, for hanging things on.</summary>
        public Transform Bone(string name) => _bones[name];

        /// <summary>Where a bone's joint is in the model's rest pose.</summary>
        public Vector3 Pivot(string name) => _pivots[name];

        /// <summary>The material a zone of the soldier, or of anything they wear, takes.</summary>
        public Material ZoneMaterial(ModelZone zone)
        {
            switch (zone)
            {
                case ModelZone.Dark: return ModelMaterials.Dark;
                case ModelZone.Metal: return ModelMaterials.Metal;
                case ModelZone.Trim:
                case ModelZone.Helmet: return _gear ?? ModelMaterials.Dark;
                case ModelZone.Team: return _team ?? ModelMaterials.Dark;
                case ModelZone.Skin: return _skin ?? ModelMaterials.Dark;
                case ModelZone.Lips: return _lips ?? _skin ?? ModelMaterials.Dark;
                case ModelZone.Hair: return ModelMaterials.Hair;
                case ModelZone.Eye: return ModelMaterials.EyeWhite;
                case ModelZone.Iris: return ModelMaterials.Iris;
                case ModelZone.Boots: return ModelMaterials.Boots;
                case ModelZone.Glow: return ModelMaterials.Dark;
                default: return _uniform ?? ModelMaterials.Dark;
            }
        }

        /// <summary>Dresses the soldier: the uniform's colour and pattern, the gear's colour, and the skin tone.</summary>
        public void SetMaterials(Material uniform, Material gear, Material skin, Material lips)
        {
            _uniform = uniform;
            _gear = gear;
            _skin = skin;
            _lips = lips;
            Refresh();
        }

        /// <summary>The armbands' colour: the team's, or null for plain dark ones.</summary>
        public void SetTeam(Material team)
        {
            if (ReferenceEquals(team, _team)) return;
            _team = team;
            Refresh();
        }

        void Refresh()
        {
            foreach ((SkinnedMeshRenderer renderer, ModelZone[] zones) in _parts)
            {
                var materials = new Material[zones.Length];
                for (int i = 0; i < zones.Length; i++) materials[i] = ZoneMaterial(zones[i]);
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

            // A full stride every 1.4 m at a walk, 1.6 m at a run; a sprint's is longer.
            float stride = Mathf.Lerp(1.4f, 2.1f, Mathf.InverseLerp(5.6f, 8.6f, speed));
            _phase = Mathf.Repeat(_phase + speed * dt * (2f * Mathf.PI / stride), 2f * Mathf.PI);
            _time += dt;
            float amplitude = Mathf.Clamp(speed / 5.6f, 0f, 1.3f) * _gait;
            float forward = speed > 0.05f ? localZ / speed : 1f;
            float sideways = speed > 0.05f ? localX / speed : 0f;
            _sprint = Mathf.MoveTowards(_sprint, !airborne && !sliding && speed > 6.6f && forward > 0.7f ? 1f : 0f, dt * 5f);

            // Crouching lowers the hips; the legs bend to keep the feet on the floor.
            float stand = Mathf.Max(0.5f, motion.StandEyeHeight);
            float drop = Mathf.Clamp(stand - motion.EyeHeight, 0f, 0.9f) * 0.62f;
            drop = Mathf.Lerp(drop, 0.48f, _slide);
            // The hips are lowest as each foot lands at a run, highest over the standing foot at a walk.
            float running = Mathf.InverseLerp(2.5f, 4.5f, speed);
            float landing = Mathf.Abs(Mathf.Cos(_phase));
            float bob = amplitude * 0.035f * Mathf.Lerp(1f - landing, landing, running);
            // And they shift over whichever foot is down, and turn with the stride.
            float shift = amplitude * 0.022f * Mathf.Cos(_phase) * (1f - 0.5f * running);
            float twist = amplitude * 8f * Mathf.Sin(_phase) * Mathf.Clamp(forward, -1f, 1f);
            Transform pelvis = _bones["Pelvis"];
            pelvis.localPosition = _pelvisRest + new Vector3(shift, -drop - bob, 0f);
            pelvis.localRotation = Quaternion.Euler(0f, twist, amplitude * 3f * Mathf.Cos(_phase) * (1f - running));
            float hipHeight = _pelvisRest.y - _hipDrop - drop - bob;
            LegBend(hipHeight, out float thighBase, out float kneeBase);

            Leg("L", _phase, thighBase, kneeBase, amplitude, forward, sideways, front: false);
            Leg("R", _phase + Mathf.PI, thighBase, kneeBase, amplitude, forward, sideways, front: true);

            // The upper body: a lean into a run (more at a sprint), back in a slide, and a share
            // of the view's pitch. The shoulders turn against the hips so the gun stays steady,
            // and standing still the chest rises and falls.
            float pitch = Mathf.Clamp(motion.Pitch, -80f, 80f);
            float lean = amplitude * 7f * Mathf.Clamp01(forward) + _sprint * 8f - _slide * 18f;
            float breath = (1f - Mathf.Clamp01(amplitude)) * Mathf.Sin(_time * 1.7f) * 1.2f;
            _bones["Torso"].localRotation = Quaternion.Euler(pitch * 0.4f + lean + breath, -twist - _slide * 15f, 0f);
            _bones["Head"].localRotation = Quaternion.Euler(pitch * 0.35f - lean * 0.6f - breath, _slide * 15f, 0f);
            // At a sprint the gun comes down and across the chest.
            _weaponPivot.localRotation = Quaternion.Euler(pitch * 0.6f * (1f - _sprint) - lean + _sprint * 28f, _slide * 15f - _sprint * 30f, _sprint * -12f);

            Arms(amplitude);
        }

        /// <summary>Hip and knee angles that put the ankle straight under a hip at this height.</summary>
        void LegBend(float hipHeight, out float thigh, out float knee)
        {
            float reach = Mathf.Clamp(hipHeight - _ankle, 0.25f, _thigh + _shin - 0.005f);
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
            // Heel first as the leg comes down in front, rolling off the toes behind.
            float roll01 = amplitude * (-12f * Mathf.Max(0f, swing) + 18f * Mathf.Max(0f, -swing) * Mathf.Max(0f, -Mathf.Cos(phase)));

            // In the air the knees come up; in a slide one leg leads and the other folds under.
            pitch = Mathf.Lerp(pitch, front ? -38f : -12f, _air);
            knee = Mathf.Lerp(knee, front ? 58f : 32f, _air);
            pitch = Mathf.Lerp(pitch, front ? -78f : -18f, _slide);
            knee = Mathf.Lerp(knee, front ? 8f : 100f, _slide);

            _bones["Thigh" + side].localRotation = Quaternion.Euler(pitch, 0f, roll);
            _bones["Shin" + side].localRotation = Quaternion.Euler(knee, 0f, 0f);
            // Keep the sole flat on the floor, toes lifting a little through the swing.
            _bones["Foot" + side].localRotation = Quaternion.Euler(-(pitch + knee) - lift * 0.2f + roll01 * (1f - _air) * (1f - _slide), 0f, -roll);
        }

        void Arms(float amplitude)
        {
            Quaternion body = _root.rotation;
            if (_grip == null)
            {
                // Empty hands: the arms hang a little away from the kit and swing against the legs.
                float swing = Mathf.Sin(_phase) * amplitude * 24f;
                _bones["UpperArmL"].localRotation = Quaternion.Euler(swing, 0f, -3f);
                _bones["UpperArmR"].localRotation = Quaternion.Euler(-swing, 0f, 3f);
                _bones["ForearmL"].localRotation = Quaternion.Euler(-4f - amplitude * 30f + Mathf.Max(0f, swing) * 0.6f, 0f, 0f);
                _bones["ForearmR"].localRotation = Quaternion.Euler(-4f - amplitude * 30f + Mathf.Max(0f, -swing) * 0.6f, 0f, 0f);
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
