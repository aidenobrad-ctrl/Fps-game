using UnityEngine;
using Recoil.Client.Visuals;
using Recoil.Shared.Cosmetics;

namespace Recoil.Client.Weapons
{
    /// <summary>
    /// The player's own gloved hands and sleeves on the weapon in the first-person view. Each
    /// hand is a model posed for what it holds (art/blender/hands.py) and is put on the
    /// weapon's own hold point, so it closes round that weapon's grip, handguard or foregrip
    /// and moves with it as it sways, kicks and comes up to aim. The forearms run from each
    /// wrist to an elbow worked out every frame from a shoulder fixed beside the camera, so
    /// the arms stay attached wherever the weapon goes, and never come up into the sight line.
    /// The sleeves are the soldier's own, in the player's uniform.
    /// </summary>
    public sealed class FirstPersonArms
    {
        // Shoulders, in the camera's space, and the arm's upper length. The elbows hang down
        // and out from them.
        static readonly Vector3 RightShoulder = new Vector3(0.2f, -0.26f, -0.12f);
        static readonly Vector3 LeftShoulder = new Vector3(-0.18f, -0.28f, -0.06f);
        static readonly Vector3 RightPole = new Vector3(0.7f, -1f, -0.2f);
        static readonly Vector3 LeftPole = new Vector3(-0.6f, -1f, 0.2f);
        const float UpperArm = 0.29f;

        struct Arm
        {
            public Transform Hand, Forearm;
            public Vector3 Wrist, Rest, Shoulder, Pole;
            public float Lower;
        }

        readonly Transform _camera;
        readonly Arm[] _arms = new Arm[2];
        int _count;

        FirstPersonArms(Transform camera)
        {
            _camera = camera;
        }

        /// <summary>
        /// Puts the arms on a built weapon, in <paramref name="look"/>'s colours. Returns null
        /// (and the weapon is shown without arms) if the hand or soldier models are missing.
        /// </summary>
        /// <param name="camera">The transform the weapon's pose is given in: the view model's.</param>
        public static FirstPersonArms Attach(in ViewModelLayout layout, CharacterLook look, Transform camera)
        {
            if (layout.Root == null || layout.Grip == null || camera == null || !SoldierView.Available) return null;
            if (ModelLibrary.Get(ViewModelBuilder.WeaponSet, "HandGripR") == null) return null;
            look = look ?? new CharacterLook();
            CosmeticItem uniformItem = look.Item(CosmeticSlot.SuitColor), gearItem = look.Item(CosmeticSlot.TrimColor);
            CosmeticItem pattern = look.Item(CosmeticSlot.Pattern);
            Material uniform = ModelMaterials.Cloth(pattern.Pattern, uniformItem.Color, Color.Lerp(uniformItem.Color * 0.7f, gearItem.Color, 0.25f));
            Material gear = ModelMaterials.Cloth(PatternKind.Plain, gearItem.Color, gearItem.Color);

            Material Zone(ModelZone zone)
            {
                switch (zone)
                {
                    case ModelZone.Metal: return ModelMaterials.Metal;
                    case ModelZone.Trim: return gear;
                    case ModelZone.Primary: return uniform;
                    default: return ModelMaterials.Dark;
                }
            }

            var arms = new FirstPersonArms(camera);
            arms.Add(layout.Root, "R", HandModel(layout.RightHand, right: true), layout.Grip, RightShoulder, RightPole, Zone);
            if (layout.LeftHand == HandPose.Pistol)
                arms.Add(layout.Root, "L", "HandPistolL", layout.Grip, LeftShoulder, LeftPole, Zone);
            else if (layout.LeftHand != HandPose.None && layout.Support != null)
                arms.Add(layout.Root, "L", HandModel(layout.LeftHand, right: false), layout.Support, LeftShoulder, LeftPole, Zone);
            arms.Update();
            return arms;
        }

        static string HandModel(HandPose pose, bool right)
        {
            switch (pose)
            {
                case HandPose.Grip: return right ? "HandGripR" : "HandHoldL";
                case HandPose.Support: return right ? "HandHoldR" : "HandSupportL";
                case HandPose.Pistol: return "HandPistolL";
                default: return right ? "HandHoldR" : "HandHoldL";
            }
        }

        void Add(Transform root, string side, string handName, Transform hold, Vector3 shoulder, Vector3 pole, System.Func<ModelZone, Material> zone)
        {
            ModelMesh hand = ModelLibrary.Get(ViewModelBuilder.WeaponSet, handName);
            ModelMesh forearm = ModelLibrary.Get(SoldierView.Set, "FPForearm" + side);
            ModelMesh restHand = ModelLibrary.Get(SoldierView.Set, "FPHand" + side);
            if (hand == null || forearm == null || restHand == null) return;

            var handGo = new GameObject("Hand " + side);
            handGo.transform.SetParent(hold, false);
            ModelLibrary.Attach(handGo, hand, zone, castShadows: false);
            Vector3 wrist = hand.TryPoint("Wrist", out ModelPoint point) ? point.Position : Vector3.zero;

            var foreGo = new GameObject("Forearm " + side);
            foreGo.transform.SetParent(root, false);
            // The sleeves are cut from the uniform, and share its maps.
            ModelMaterials.ApplyMaps(ModelLibrary.Attach(foreGo, forearm, zone, castShadows: false), "Uniform", forearm.TexelScale);

            Vector3 rest = restHand.Pivot - forearm.Pivot;
            _arms[_count++] = new Arm
            {
                Hand = handGo.transform, Forearm = foreGo.transform, Wrist = wrist, Rest = rest,
                Shoulder = shoulder, Pole = pole, Lower = rest.magnitude,
            };
        }

        /// <summary>Lays each forearm from its wrist to its elbow. Call after the weapon has been posed for the frame.</summary>
        public void Update()
        {
            for (int i = 0; i < _count; i++)
            {
                ref Arm arm = ref _arms[i];
                if (arm.Hand == null || arm.Forearm == null) continue;
                Vector3 wrist = arm.Hand.TransformPoint(arm.Wrist);
                Vector3 shoulder = _camera.TransformPoint(arm.Shoulder);
                Vector3 pole = _camera.TransformDirection(arm.Pole);
                Vector3 elbow = Elbow(shoulder, wrist, UpperArm, arm.Lower, pole);
                Vector3 along = wrist - elbow;
                if (along.sqrMagnitude < 1e-8f) continue;
                arm.Forearm.SetPositionAndRotation(elbow, Quaternion.FromToRotation(arm.Rest, along));
            }
        }

        /// <summary>
        /// Where the elbow goes for a hand at <paramref name="wrist"/>: two bones from the
        /// shoulder, bent towards the pole. Out of reach, the arm is simply straight.
        /// </summary>
        public static Vector3 Elbow(Vector3 shoulder, Vector3 wrist, float upper, float lower, Vector3 pole)
        {
            Vector3 toWrist = wrist - shoulder;
            float reach = Mathf.Clamp(toWrist.magnitude, Mathf.Abs(upper - lower) + 1e-4f, upper + lower - 1e-4f);
            Vector3 along = toWrist.sqrMagnitude > 1e-8f ? toWrist.normalized : Vector3.forward;
            float a = (upper * upper - lower * lower + reach * reach) / (2f * reach);
            float h = Mathf.Sqrt(Mathf.Max(upper * upper - a * a, 0f));
            Vector3 bend = pole - along * Vector3.Dot(pole, along);
            bend = bend.sqrMagnitude > 1e-8f ? bend.normalized : Vector3.down;
            Vector3 elbow = shoulder + along * a + bend * h;
            // Too far to reach: the forearm still ends at the wrist, the elbow drawn in behind it.
            return toWrist.magnitude > upper + lower ? wrist - (wrist - elbow).normalized * lower : elbow;
        }
    }
}
