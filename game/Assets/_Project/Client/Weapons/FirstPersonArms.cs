using UnityEngine;
using Recoil.Client.Visuals;
using Recoil.Shared.Cosmetics;
using Recoil.Shared.Weapons;

namespace Recoil.Client.Weapons
{
    /// <summary>
    /// The player's own gloves and sleeves on the weapon in the first-person view: the right
    /// hand round the pistol grip, the left cupping the handguard from below (or both on the
    /// grip, for a handgun), forearms running back out of the bottom of the screen. They are
    /// the soldier model's own segments, in the player's suit and trim, and they move with the
    /// weapon as it sways, kicks and comes up to aim.
    ///
    /// The numbers match art/blender/recoil_models.py, where the placement was checked.
    /// </summary>
    public static class FirstPersonArms
    {
        static readonly Vector3 RightWrist = new Vector3(0.012f, 0f, 0f);
        const float RightUpTheGrip = 0.05f;
        static readonly Vector3 RightElbow = new Vector3(0.4f, -0.55f, -1f);
        static readonly Vector3 LeftWrist = new Vector3(-0.035f, -0.045f, -0.015f);
        static readonly Vector3 LeftFingers = new Vector3(0.55f, 0.8f, 0.25f);
        static readonly Vector3 LeftElbow = new Vector3(-0.55f, -0.45f, -1f);

        /// <summary>Puts arms on a built weapon, in <paramref name="look"/>'s colours. Does nothing without the soldier model.</summary>
        public static void Attach(in ViewModelLayout layout, CharacterLook look)
        {
            if (layout.Root == null || layout.Grip == null || !SoldierView.Available) return;
            look = look ?? new CharacterLook();
            CosmeticItem uniformItem = look.Item(CosmeticSlot.SuitColor), gearItem = look.Item(CosmeticSlot.TrimColor);
            CosmeticItem pattern = look.Item(CosmeticSlot.Pattern);
            Material uniform = ModelMaterials.Cloth(pattern.Pattern, uniformItem.Color, Color.Lerp(uniformItem.Color * 0.7f, gearItem.Color, 0.25f));
            Material gear = ModelMaterials.Cloth(PatternKind.Plain, gearItem.Color, gearItem.Color);

            Material Zone(ModelZone zone)
            {
                switch (zone)
                {
                    case ModelZone.Dark: return ModelMaterials.Dark;
                    case ModelZone.Metal: return ModelMaterials.Metal;
                    case ModelZone.Trim: return gear;
                    case ModelZone.Primary: return uniform;
                    default: return ModelMaterials.Dark;
                }
            }

            Transform root = layout.Root;
            Vector3 grip = root.InverseTransformPoint(layout.Grip.position);
            if (layout.Kind == ViewModelKind.Blade || layout.Kind == ViewModelKind.Thrown)
            {
                // One hand round the handle.
                Arm(root, "R", grip + new Vector3(0.01f, 0.045f, -0.01f), Vector3.down, RightElbow, Zone);
                return;
            }
            // The pistol grip leans back 18 degrees; the right hand hangs down along it.
            Vector3 gripAxis = Quaternion.Euler(18f, 0f, 0f) * Vector3.down;
            Vector3 rightWrist = grip + RightWrist - gripAxis * RightUpTheGrip;
            Arm(root, "R", rightWrist, gripAxis, RightElbow, Zone);

            if (layout.Support != null)
            {
                Vector3 support = root.InverseTransformPoint(layout.Support.position);
                Arm(root, "L", support + LeftWrist, LeftFingers, LeftElbow, Zone);
            }
            else
            {
                // A handgun: the left hand wraps under the right.
                Arm(root, "L", rightWrist + new Vector3(-0.03f, -0.035f, 0.015f), gripAxis + new Vector3(0.5f, 0f, 0f), LeftElbow, Zone);
            }
        }

        static void Arm(Transform root, string side, Vector3 wrist, Vector3 fingers, Vector3 towardElbow, System.Func<ModelZone, Material> zone)
        {
            ModelMesh forearm = ModelLibrary.Get(SoldierView.Set, "FPForearm" + side);
            ModelMesh hand = ModelLibrary.Get(SoldierView.Set, "FPHand" + side);
            if (forearm == null || hand == null) return;

            Vector3 rest = hand.Pivot - forearm.Pivot;
            Vector3 elbow = wrist + towardElbow.normalized * rest.magnitude;

            var foreGo = new GameObject("Forearm " + side);
            foreGo.transform.SetParent(root, false);
            foreGo.transform.localPosition = elbow;
            foreGo.transform.localRotation = Quaternion.FromToRotation(rest, wrist - elbow);
            // The sleeves and gloves are cut from the uniform, and share its maps.
            ModelMaterials.ApplyMaps(ModelLibrary.Attach(foreGo, forearm, zone, castShadows: false), "Uniform", forearm.TexelScale);

            var handGo = new GameObject("Hand " + side);
            handGo.transform.SetParent(root, false);
            handGo.transform.localPosition = wrist;
            handGo.transform.localRotation = Quaternion.FromToRotation(Vector3.down, fingers.normalized);
            ModelMaterials.ApplyMaps(ModelLibrary.Attach(handGo, hand, zone, castShadows: false), "Uniform", hand.TexelScale);
        }
    }
}
