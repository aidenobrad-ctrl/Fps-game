using UnityEngine;
using Recoil.Client.Visuals;
using Recoil.Shared.Cosmetics;
using Recoil.Shared.Match;
using Recoil.Shared.Weapons;

namespace Recoil.Client.Weapons
{
    /// <summary>How a hand holds a weapon (the hand models in the Guns set).</summary>
    public enum HandPose
    {
        None,
        /// <summary>The right hand round a pistol grip, its finger on the trigger.</summary>
        Grip,
        /// <summary>Closed round a handle or a vertical foregrip; a fist.</summary>
        Hold,
        /// <summary>The left hand under a handguard or a pump.</summary>
        Support,
        /// <summary>The left hand wrapped round the right on a handgun.</summary>
        Pistol,
    }

    /// <summary>A built first-person weapon model and how to hold it.</summary>
    public struct ViewModelLayout
    {
        public Transform Root;
        public Transform Muzzle;
        public ViewModelKind Kind;
        /// <summary>Resting pose, in camera space.</summary>
        public Vector3 HipPosition;
        public Vector3 HipEuler;
        /// <summary>Aimed pose: puts the sight line through the centre of the screen.</summary>
        public Vector3 AdsPosition;
        /// <summary>Where the hands go: the pistol grip, and the handguard (null for a one-handed weapon).</summary>
        public Transform Grip, Support;
        /// <summary>How far behind the weapon's origin its back end is: the butt of the stock. Negative.</summary>
        public float RearZ;
        /// <summary>How each hand holds: the right on Grip; the left on Support, or round the right hand.</summary>
        public HandPose RightHand, LeftHand;
        /// <summary>Held out in front (a pistol, anything without a stock) rather than against the shoulder.</summary>
        public bool Handgun;
        /// <summary>The magazine (or loaded rocket), which comes out during a reload; null if none shows.</summary>
        public Transform Magazine;
        /// <summary>The way the magazine comes out, in the model's space.</summary>
        public Vector3 MagazineOut;
    }

    /// <summary>
    /// Builds a weapon's model with the attachments fitted to it. Every real weapon is modelled
    /// whole at its real size (the "Guns" models, from art/blender/guns.py), with named points
    /// for where it is held, where its muzzle and rails are and where the eye sits to aim;
    /// optics go on its rail, suppressors and brakes on its muzzle, grips under its handguard,
    /// an extended magazine lengthens its own and a drum replaces it, and the iron sights fold
    /// away under an optic. A weapon without a model of its own is put together from the
    /// "GunParts" pieces, stretched to the proportions in its <see cref="WeaponViewProfile"/>.
    ///
    /// A skin covers the weapon's main finish (receivers, handguards, stocks, magazines) in its
    /// pattern and its secondary finish (grips, rails, controls) in its darker colour; bare
    /// steel stays steel. The models' texture coordinates are laid at one scale over their real
    /// surfaces, so a pattern comes out the same size on every part and every weapon.
    ///
    /// The same model serves the first-person view and, at the same scale, the gun in other
    /// players' hands.
    /// </summary>
    public static class ViewModelBuilder
    {
        // The skin of the model being built. Building happens all at once on the main thread,
        // so it is set for the length of one Build call.
        static CosmeticItem _skin;
        static Material _dark, _accent;
        static bool _shadows;

        /// <param name="skin">The weapon skin to wear, or null (or the factory skin) for the weapon's own colours.</param>
        /// <param name="castShadows">True for a gun out in the world; the first-person view casts none.</param>
        public static ViewModelLayout Build(Transform parent, WeaponBuild build, CosmeticItem skin = null, bool castShadows = false)
        {
            _skin = skin;
            _shadows = castShadows;
            _dark = DarkMaterial(build.Weapon.view);
            _accent = AccentMaterial(build.Weapon.view);
            try
            {
                return BuildModel(parent, build);
            }
            finally
            {
                _skin = null;
                _dark = _accent = null;
                _shadows = false;
            }
        }

        static Material BodyMaterial(WeaponViewProfile p) => LookMaterials.SkinBody(_skin) ?? GreyboxMaterials.Flat(p.bodyColor);
        static Material DarkMaterial(WeaponViewProfile p) => LookMaterials.SkinDark(_skin) ?? GreyboxMaterials.Flat(p.DarkColor);
        static Material AccentMaterial(WeaponViewProfile p) => LookMaterials.SkinAccent(_skin) ?? GreyboxMaterials.Unlit(p.accentColor);

        static ViewModelLayout BuildModel(Transform parent, WeaponBuild build)
        {
            var root = new GameObject("Model " + build.Weapon.weaponId).transform;
            root.SetParent(parent, false);

            WeaponViewProfile profile = build.Weapon.view;
            var layout = new ViewModelLayout { Root = root, Kind = profile.kind };

            if (build.Weapon.weaponId == BodyShapes.FistsId)
            {
                BuildFists(ref layout);
                return layout;
            }
            ModelMesh model = ModelLibrary.Get(WeaponSet, build.Weapon.weaponId);
            if (model != null)
            {
                BuildWhole(ref layout, model, build);
                return layout;
            }

            layout.RightHand = profile.kind == ViewModelKind.Blade || profile.kind == ViewModelKind.Thrown ? HandPose.Hold : HandPose.Grip;
            switch (profile.kind)
            {
                case ViewModelKind.Launcher: BuildLauncher(ref layout, profile); break;
                case ViewModelKind.Blade: BuildBlade(ref layout, profile); break;
                case ViewModelKind.Thrown: BuildThrown(ref layout, profile); break;
                default: BuildGun(ref layout, profile, build); break;
            }
            return layout;
        }

        // ------------------------------------------------------------------ whole models

        public const string WeaponSet = "Guns";

        /// <summary>
        /// Where a long gun's aiming eye point sits when it is carried at the hip, relative to
        /// the camera, and how it is canted there: low and to the right, turned a little so the
        /// right hand on the grip shows (checked in first-person renders at the default field
        /// of view).
        /// </summary>
        static readonly Vector3 HipEye = new Vector3(0.12f, -0.05f, 0.16f);
        static readonly Vector3 HipCant = new Vector3(4f, -4f, -10f);
        /// <summary>And for a handgun, held out in front.</summary>
        static readonly Vector3 HipEyeHandgun = new Vector3(0.1f, -0.09f, 0.04f);
        static readonly Vector3 HipCantHandgun = new Vector3(0f, -2f, -4f);
        /// <summary>A blade's (and a fist's) resting place and angle.</summary>
        static readonly Vector3 BladeHip = new Vector3(0.2f, -0.2f, 0.3f);
        static readonly Vector3 BladeEuler = new Vector3(-38f, -14f, 22f);

        static void BuildWhole(ref ViewModelLayout layout, ModelMesh model, WeaponBuild build)
        {
            Transform root = layout.Root;
            WeaponDefinition weapon = build.Weapon;
            WeaponViewProfile p = weapon.view;
            Material body = BodyMaterial(p), dark = _dark, accent = _accent;
            Material Zone(ModelZone zone)
            {
                switch (zone)
                {
                    case ModelZone.Dark: return dark;
                    case ModelZone.Metal: return ModelMaterials.Metal;
                    case ModelZone.Glow: return accent;
                    default: return body;
                }
            }

            AttachmentVisual sight = VisualOf(build, AttachmentSlot.Sight);
            AttachmentVisual barrel = VisualOf(build, AttachmentSlot.Barrel);
            AttachmentVisual magazine = VisualOf(build, AttachmentSlot.Magazine);
            AttachmentVisual grip = VisualOf(build, AttachmentSlot.Grip);
            AttachmentVisual stock = VisualOf(build, AttachmentSlot.Stock);
            bool laser = VisualOf(build, AttachmentSlot.Laser) == AttachmentVisual.Laser;
            bool optic = sight == AttachmentVisual.RedDot || sight == AttachmentVisual.Holo || sight == AttachmentVisual.Scope;

            Whole(root, model, Zone);
            // The pieces that come and go with the attachments.
            if (!optic) Piece(root, model.Name + ".Irons", Zone);
            else Piece(root, model.Name + ".Mount", Zone);
            Transform stockPiece = stock == AttachmentVisual.NoStock ? null : Piece(root, model.Name + ".Stock", Zone);
            if (stockPiece != null && stock == AttachmentVisual.LightStock) stockPiece.localScale = new Vector3(0.8f, 0.86f, 1f);
            else if (stockPiece != null && stock == AttachmentVisual.HeavyStock) stockPiece.localScale = new Vector3(1.12f, 1.08f, 1f);

            Vector3 Point(string name, Vector3 fallback) => model.TryPoint(name, out ModelPoint point) ? point.Position : fallback;
            Vector3 Direction(string name, Vector3 fallback) => model.TryPoint(name, out ModelPoint point) ? point.Direction : fallback;

            Vector3 eye = Point("Eye", new Vector3(0f, 0.05f, -0.2f));
            Vector3 rail = Point("Rail", new Vector3(0f, eye.y - 0.03f, eye.z + 0.15f));
            Vector3 under = Point("Under", new Vector3(0f, -0.04f, 0.2f));
            Vector3 side = Point("Side", under + new Vector3(0.03f, 0.02f, 0f));
            Vector3 butt = Point("Butt", new Vector3(0f, 0f, -0.3f));
            bool blade = layout.Kind == ViewModelKind.Blade || layout.Kind == ViewModelKind.Thrown;

            // The magazine: lengthened, swapped for a drum, or as it comes.
            if (model.TryPoint("Mag", out ModelPoint well))
            {
                Vector3 inward = well.Direction.normalized;
                Transform mag = magazine == AttachmentVisual.DrumMagazine ? null : Piece(root, model.Name + ".Mag", Zone);
                if (mag != null && magazine == AttachmentVisual.ExtendedMagazine && Mathf.Abs(inward.y) > 0.6f)
                {
                    // Stretched along its own length from the bottom of the well.
                    var stretch = new GameObject("Extended").transform;
                    stretch.SetParent(root, false);
                    stretch.localPosition = well.Position;
                    stretch.localRotation = Quaternion.FromToRotation(Vector3.up, inward);
                    mag.SetParent(stretch, true);
                    stretch.localScale = new Vector3(1f, 1.4f, 1f);
                    mag = stretch;
                }
                else if (magazine == AttachmentVisual.DrumMagazine)
                {
                    mag = Part(root, "Drum", well.Position - inward * 0.045f, new Vector3(0.085f, 0.09f, 0.075f), dark);
                }
                layout.Magazine = mag;
                layout.MagazineOut = -inward;
            }

            // An optic on the rail sets the eye line; without one, the iron sights do.
            float eyeHeight = eye.y;
            switch (sight)
            {
                case AttachmentVisual.RedDot:
                    eyeHeight = WindowSight(root, rail.y, rail.z, 0.034f, 0.028f, 0.05f, dark);
                    break;
                case AttachmentVisual.Holo:
                    eyeHeight = WindowSight(root, rail.y, rail.z, 0.046f, 0.034f, 0.07f, dark);
                    break;
                case AttachmentVisual.Scope:
                    eyeHeight = WindowSight(root, rail.y, rail.z, 0.04f, 0.04f, 0.17f, dark);
                    break;
            }

            // Whatever is screwed on the muzzle.
            Vector3 muzzle = Point("Muzzle", new Vector3(0f, 0f, 0.4f));
            float bore = MuzzleRadius(weapon.weaponClass);
            if (barrel == AttachmentVisual.Suppressor)
            {
                float length = weapon.weaponClass == WeaponClass.Pistol ? 0.13f : weapon.weaponClass == WeaponClass.Sniper ? 0.2f : 0.17f;
                Part(root, "Suppressor", muzzle + Vector3.forward * (length * 0.5f - 0.01f), new Vector3(bore * 3.6f, bore * 3.6f, length), dark);
                muzzle += Vector3.forward * (length - 0.01f);
            }
            else if (barrel == AttachmentVisual.MuzzleDevice)
            {
                Part(root, "MuzzleDevice", muzzle + Vector3.forward * 0.02f, new Vector3(bore * 2.9f, bore * 2.9f, 0.045f), dark);
                muzzle += Vector3.forward * 0.042f;
            }
            else if (barrel == AttachmentVisual.LongBarrel)
            {
                Part(root, "Barrel", muzzle + Vector3.forward * 0.045f, new Vector3(bore * 2.2f, bore * 2.2f, 0.09f), ModelMaterials.Metal);
                muzzle += Vector3.forward * 0.09f;
            }

            // Hands: the right on the grip; the left where the weapon says, or on a foregrip.
            layout.Grip = HoldAnchor(root, "Grip Hold", Point("Grip", Vector3.zero), Direction("Grip", Vector3.up));
            layout.RightHand = blade ? HandPose.Hold : HandPose.Grip;
            layout.Handgun = !blade && butt.z > -0.12f;
            if (grip == AttachmentVisual.VerticalGrip)
            {
                Part(root, "VerticalGrip", under + new Vector3(0f, -0.04f, 0f), new Vector3(0.028f, 0.08f, 0.03f), dark);
                layout.Support = HoldAnchor(root, "Support Hold", under + new Vector3(0f, -0.046f, 0f), Vector3.up);
                layout.LeftHand = HandPose.Hold;
            }
            else
            {
                if (grip == AttachmentVisual.AngledGrip)
                {
                    Part(root, "AngledGrip", under + new Vector3(0f, -0.016f, 0.01f), new Vector3(0.03f, 0.03f, 0.09f), dark)
                        .localRotation = Quaternion.Euler(-22f, 0f, 0f);
                }
                if (model.TryPoint("Foregrip", out ModelPoint foregrip))
                {
                    layout.Support = HoldAnchor(root, "Support Hold", foregrip.Position, foregrip.Direction);
                    layout.LeftHand = HandPose.Hold;
                }
                else if (model.TryPoint("Support", out ModelPoint support))
                {
                    layout.Support = HoldAnchor(root, "Support Hold", support.Position, support.Direction);
                    layout.LeftHand = HandPose.Support;
                }
                else
                {
                    layout.LeftHand = blade ? HandPose.None : HandPose.Pistol;
                }
            }
            if (laser)
            {
                Vector3 at = side + new Vector3(0.012f, 0f, 0f);
                Part(root, "Laser", at, new Vector3(0.022f, 0.022f, 0.055f), dark);
                Part(root, "LaserLens", at + new Vector3(0f, 0f, 0.029f), new Vector3(0.01f, 0.01f, 0.004f), GreyboxMaterials.Unlit(new Color(1f, 0.15f, 0.1f)));
            }

            layout.Muzzle = Anchor(root, "Muzzle", muzzle);
            layout.RearZ = butt.z;
            var aim = new Vector3(0f, eyeHeight, eye.z);
            if (blade)
            {
                layout.HipPosition = BladeHip;
                layout.HipEuler = BladeEuler;
                layout.AdsPosition = BladeHip;
                return;
            }
            layout.AdsPosition = -aim;
            layout.HipPosition = (layout.Handgun ? HipEyeHandgun : HipEye) - aim;
            layout.HipEuler = layout.Handgun ? HipCantHandgun : HipCant;
        }

        /// <summary>No weapon at all: two fists up in front, for the hands to close.</summary>
        static void BuildFists(ref ViewModelLayout layout)
        {
            Transform root = layout.Root;
            layout.Grip = HoldAnchor(root, "Right Fist", new Vector3(0.11f, -0.02f, 0.03f), new Vector3(0f, 1f, 0.3f));
            layout.Support = HoldAnchor(root, "Left Fist", new Vector3(-0.13f, 0.0f, -0.02f), new Vector3(0f, 1f, 0.3f));
            layout.Muzzle = Anchor(root, "Tip", new Vector3(0.11f, -0.02f, 0.08f));
            layout.RightHand = HandPose.Hold;
            layout.LeftHand = HandPose.Hold;
            layout.Handgun = true;
            layout.HipPosition = new Vector3(0.02f, -0.17f, 0.3f);
            layout.AdsPosition = layout.HipPosition;
        }

        /// <summary>The radius of a weapon's muzzle, for sizing what screws on to it.</summary>
        static float MuzzleRadius(WeaponClass weaponClass)
        {
            switch (weaponClass)
            {
                case WeaponClass.Pistol: return 0.0075f;
                case WeaponClass.Smg: return 0.0095f;
                case WeaponClass.Shotgun: return 0.012f;
                case WeaponClass.Sniper: return 0.013f;
                default: return 0.011f;
            }
        }

        /// <summary>A whole model hung on the root, in the zone materials.</summary>
        static Transform Whole(Transform root, ModelMesh model, System.Func<ModelZone, Material> zone)
        {
            var go = new GameObject(model.Name);
            go.transform.SetParent(root, false);
            ModelLibrary.Attach(go, model, zone, _shadows);
            return go.transform;
        }

        /// <summary>One of a model's separate pieces (its magazine, stock, iron sights, mount), if it has it.</summary>
        static Transform Piece(Transform root, string name, System.Func<ModelZone, Material> zone)
        {
            ModelMesh piece = ModelLibrary.Get(WeaponSet, name);
            return piece != null ? Whole(root, piece, zone) : null;
        }

        /// <summary>
        /// Where a hand closes: at the point, its up along the given direction and its front
        /// facing forward across it (the frame the hand models are made in).
        /// </summary>
        static Transform HoldAnchor(Transform root, string name, Vector3 position, Vector3 up)
        {
            Transform anchor = Anchor(root, name, position);
            anchor.localRotation = HoldRotation(up);
            return anchor;
        }

        public static Quaternion HoldRotation(Vector3 up)
        {
            up = up.sqrMagnitude > 1e-6f ? up.normalized : Vector3.up;
            Vector3 forward = Vector3.Cross(Vector3.right, up);
            if (forward.sqrMagnitude < 1e-6f) forward = Vector3.forward;
            return Quaternion.LookRotation(forward.normalized, up);
        }

        // ------------------------------------------------------------------ guns from parts

        static void BuildGun(ref ViewModelLayout layout, WeaponViewProfile p, WeaponBuild build)
        {
            Transform root = layout.Root;
            float b = p.bulk, length = p.bodyLength;
            Material body = BodyMaterial(p);
            Material dark = DarkMaterial(p);
            Material accent = AccentMaterial(p);

            AttachmentVisual barrel = VisualOf(build, AttachmentSlot.Barrel);
            AttachmentVisual magazine = VisualOf(build, AttachmentSlot.Magazine);
            AttachmentVisual grip = VisualOf(build, AttachmentSlot.Grip);
            AttachmentVisual stock = VisualOf(build, AttachmentSlot.Stock);
            AttachmentVisual sight = VisualOf(build, AttachmentSlot.Sight);
            bool laser = VisualOf(build, AttachmentSlot.Laser) == AttachmentVisual.Laser;

            float top = 0.0375f * b;      // top surface of the receiver
            float front = length * 0.5f;  // front face of the receiver
            Part(root, "Receiver", Vector3.zero, new Vector3(0.055f * b, 0.075f * b, length), body);

            // Barrel: a handguard, then exposed barrel, then whatever is screwed on the end.
            float handguard = p.barrelLength * 0.55f;
            float exposed = p.barrelLength * 0.45f + (barrel == AttachmentVisual.LongBarrel ? 0.09f : 0f);
            float barrelY = 0.008f * b;
            if (handguard > 0.01f)
            {
                Part(root, "Handguard", new Vector3(0f, 0.004f * b, front + handguard * 0.5f),
                    new Vector3(0.046f * b, 0.052f * b, handguard), dark);
                Part(root, "Accent", new Vector3(0f, 0.004f * b + 0.027f * b, front + handguard * 0.5f),
                    new Vector3(0.03f * b, 0.004f, handguard * 0.6f), accent);
            }
            else
            {
                Part(root, "Accent", new Vector3(0f, top * 0.3f, 0f), new Vector3(0.057f * b, 0.008f, length * 0.4f), accent);
            }
            if (exposed > 0.01f)
            {
                Part(root, "Barrel", new Vector3(0f, barrelY, front + handguard + exposed * 0.5f),
                    new Vector3(0.022f * b, 0.022f * b, exposed), dark);
            }

            float muzzleZ = front + handguard + exposed;
            if (barrel == AttachmentVisual.Suppressor)
            {
                Part(root, "Suppressor", new Vector3(0f, barrelY, muzzleZ + 0.07f), new Vector3(0.04f, 0.04f, 0.14f), dark);
                muzzleZ += 0.14f;
            }
            else if (barrel == AttachmentVisual.MuzzleDevice)
            {
                Part(root, "MuzzleDevice", new Vector3(0f, barrelY, muzzleZ + 0.02f), new Vector3(0.034f, 0.034f, 0.04f), dark);
                muzzleZ += 0.04f;
            }

            // Stock.
            if (p.stockLength > 0.01f && stock != AttachmentVisual.NoStock)
            {
                Vector3 size = new Vector3(0.045f * b, 0.065f * b, p.stockLength);
                if (stock == AttachmentVisual.LightStock) size = new Vector3(0.02f * b, 0.045f * b, p.stockLength);
                else if (stock == AttachmentVisual.HeavyStock) size = new Vector3(0.056f * b, 0.082f * b, p.stockLength * 1.1f);
                Part(root, "Stock", new Vector3(0f, -0.012f * b, -front - size.z * 0.5f), size, body);
            }

            // Grip and magazine.
            Part(root, "Grip", new Vector3(0f, -0.075f * b, -length * 0.28f), new Vector3(0.034f * b, 0.09f, 0.045f), dark)
                .localRotation = Quaternion.Euler(18f, 0f, 0f);

            if (p.magazineLength > 0.01f)
            {
                float magazineZ = length * 0.12f;
                if (magazine == AttachmentVisual.DrumMagazine)
                {
                    Part(root, "Drum", new Vector3(0f, -top - 0.05f, magazineZ), new Vector3(0.085f, 0.09f, 0.075f), dark);
                }
                else
                {
                    float magazineLength = p.magazineLength * (magazine == AttachmentVisual.ExtendedMagazine ? 1.45f : 1f);
                    Part(root, "Magazine", new Vector3(0f, -top - magazineLength * 0.5f, magazineZ),
                            new Vector3(0.034f * b, magazineLength, 0.06f), dark)
                        .localRotation = Quaternion.Euler(-8f, 0f, 0f);
                }
            }

            // Things hung under and beside the handguard.
            float underY = 0.004f * b - 0.026f * b;
            float underZ = front + Mathf.Max(handguard, 0.04f) * 0.5f;
            if (grip == AttachmentVisual.VerticalGrip)
            {
                Part(root, "VerticalGrip", new Vector3(0f, underY - 0.04f, underZ), new Vector3(0.028f, 0.08f, 0.03f), dark);
            }
            else if (grip == AttachmentVisual.AngledGrip)
            {
                Part(root, "AngledGrip", new Vector3(0f, underY - 0.018f, underZ), new Vector3(0.03f, 0.03f, 0.09f), dark)
                    .localRotation = Quaternion.Euler(-22f, 0f, 0f);
            }
            if (laser)
            {
                float side = 0.023f * b + 0.011f;
                Part(root, "Laser", new Vector3(side, 0.004f * b, underZ), new Vector3(0.022f, 0.022f, 0.055f), dark);
                Part(root, "LaserLens", new Vector3(side, 0.004f * b, underZ + 0.03f), new Vector3(0.01f, 0.01f, 0.004f),
                    GreyboxMaterials.Unlit(new Color(1f, 0.15f, 0.1f)));
            }

            // Sights decide where the eye lines up when aiming.
            float sightZ = -length * 0.05f;
            float sightLine;
            switch (sight)
            {
                case AttachmentVisual.RedDot:
                    sightLine = WindowSight(root, top, sightZ, 0.034f, 0.028f, 0.05f, dark);
                    break;
                case AttachmentVisual.Holo:
                    sightLine = WindowSight(root, top, sightZ, 0.046f, 0.034f, 0.07f, dark);
                    break;
                case AttachmentVisual.Scope:
                    sightLine = WindowSight(root, top, sightZ, 0.04f, 0.04f, 0.17f, dark);
                    break;
                default:
                    if (build.Weapon.reticle == ReticleStyle.Scope)
                    {
                        // A built-in scope. It is swapped for the full-screen scope view when aiming.
                        Part(root, "ScopeMount", new Vector3(0f, top + 0.006f, sightZ), new Vector3(0.02f, 0.012f, 0.12f), dark);
                        Part(root, "Scope", new Vector3(0f, top + 0.037f, sightZ), new Vector3(0.05f, 0.05f, 0.26f), dark);
                        sightLine = top + 0.037f;
                    }
                    else
                    {
                        float rearZ = -length * 0.3f;
                        float frontZ = handguard > 0.01f ? front + handguard - 0.02f : front - 0.02f;
                        Part(root, "RearSightL", new Vector3(-0.012f, top + 0.01f, rearZ), new Vector3(0.007f, 0.02f, 0.012f), dark);
                        Part(root, "RearSightR", new Vector3(0.012f, top + 0.01f, rearZ), new Vector3(0.007f, 0.02f, 0.012f), dark);
                        Part(root, "FrontSight", new Vector3(0f, top + 0.01f, frontZ), new Vector3(0.005f, 0.02f, 0.005f), dark);
                        sightLine = top + 0.022f;
                    }
                    break;
            }

            layout.Muzzle = Anchor(root, "Muzzle", new Vector3(0f, barrelY, muzzleZ));
            layout.Grip = Anchor(root, "Grip Hold", new Vector3(0f, -0.075f * b, -length * 0.28f));
            bool oneHanded = p.stockLength <= 0.01f && length < 0.22f;
            layout.Support = oneHanded ? null : Anchor(root, "Support Hold", new Vector3(0f, underY, underZ + (grip == AttachmentVisual.None ? 0.02f : 0f)));
            layout.LeftHand = oneHanded ? HandPose.Pistol : HandPose.Support;
            layout.Handgun = oneHanded;
            layout.RearZ = -front - (p.stockLength > 0.01f && stock != AttachmentVisual.NoStock ? p.stockLength : 0f);

            // Handguns are held out at arm's length; long guns sit against the shoulder.
            bool handgun = p.stockLength <= 0.01f && length < 0.22f;
            layout.HipPosition = handgun
                ? new Vector3(0.15f, -0.15f, 0.44f)
                : new Vector3(0.17f, -0.17f, 0.3f + length * 0.2f);
            layout.AdsPosition = new Vector3(0f, -sightLine - 0.0015f, handgun ? 0.4f : 0.18f + length * 0.2f);
        }

        /// <summary>An open frame you look through. Returns the height of its centre above the weapon's origin.</summary>
        static float WindowSight(Transform root, float top, float z, float width, float height, float depth, Material material)
        {
            const float baseHeight = 0.012f, wall = 0.005f;
            float bottom = top + baseHeight;
            if (ModelLibrary.Get(GunSet, "SightFrame") != null)
            {
                // One piece: the base, the posts and the top, hollow in the middle.
                Vector3 size = new Vector3(width + wall * 2f, baseHeight + height + wall, depth);
                Part(root, "SightFrame", new Vector3(0f, top + size.y * 0.5f, z), size, material);
                return bottom + height * 0.5f;
            }
            float pillarX = width * 0.5f + wall * 0.5f;
            Part(root, "SightBase", new Vector3(0f, top + baseHeight * 0.5f, z), new Vector3(width + wall * 2f, baseHeight, depth), material);
            Part(root, "SightL", new Vector3(-pillarX, bottom + height * 0.5f, z), new Vector3(wall, height, depth), material);
            Part(root, "SightR", new Vector3(pillarX, bottom + height * 0.5f, z), new Vector3(wall, height, depth), material);
            Part(root, "SightTop", new Vector3(0f, bottom + height + wall * 0.5f, z), new Vector3(width + wall * 2f, wall, depth), material);
            return bottom + height * 0.5f;
        }

        // ------------------------------------------------------------------ everything else

        static void BuildLauncher(ref ViewModelLayout layout, WeaponViewProfile p)
        {
            Transform root = layout.Root;
            float b = p.bulk, length = p.bodyLength;
            Material body = BodyMaterial(p);
            Material dark = DarkMaterial(p);
            Material accent = AccentMaterial(p);

            Part(root, "Tube", Vector3.zero, new Vector3(0.11f * b, 0.11f * b, length), body);
            Part(root, "Mouth", new Vector3(0f, 0f, length * 0.5f), new Vector3(0.135f * b, 0.135f * b, 0.05f), dark);
            Part(root, "Tail", new Vector3(0f, 0f, -length * 0.5f), new Vector3(0.125f * b, 0.125f * b, 0.06f), dark);
            Part(root, "Band", new Vector3(0f, 0f, length * 0.2f), new Vector3(0.115f * b, 0.115f * b, 0.02f), accent);
            Part(root, "Grip", new Vector3(0f, -0.1f * b, -length * 0.05f), new Vector3(0.035f, 0.1f, 0.045f), dark)
                .localRotation = Quaternion.Euler(14f, 0f, 0f);
            Part(root, "Sight", new Vector3(-0.07f * b, 0.07f * b, 0f), new Vector3(0.008f, 0.05f, 0.06f), dark);

            layout.Muzzle = Anchor(root, "Muzzle", new Vector3(0f, 0f, length * 0.5f + 0.03f));
            layout.Grip = Anchor(root, "Grip Hold", new Vector3(0f, -0.1f * b, -length * 0.05f));
            layout.Support = Anchor(root, "Support Hold", new Vector3(0f, -0.06f * b, length * 0.25f));
            layout.LeftHand = HandPose.Support;
            layout.RearZ = -length * 0.5f;
            layout.HipPosition = new Vector3(0.2f, -0.15f, 0.28f + length * 0.15f);
            // A launcher stays on the shoulder when aimed; the crosshair does the aiming.
            layout.AdsPosition = new Vector3(0.12f, -0.11f, 0.24f + length * 0.15f);
        }

        static void BuildBlade(ref ViewModelLayout layout, WeaponViewProfile p)
        {
            Transform root = layout.Root;
            float length = p.bodyLength;

            Part(root, "Handle", Vector3.zero, new Vector3(0.028f, 0.032f, 0.15f), DarkMaterial(p));
            Part(root, "Guard", new Vector3(0f, 0f, 0.08f), new Vector3(0.012f, 0.075f, 0.012f), AccentMaterial(p));
            Part(root, "Blade", new Vector3(0f, 0f, 0.085f + length * 0.5f), new Vector3(0.006f, 0.036f * p.bulk, length), BodyMaterial(p));

            layout.Muzzle = Anchor(root, "Tip", new Vector3(0f, 0f, 0.085f + length));
            layout.Grip = Anchor(root, "Grip Hold", Vector3.zero);
            layout.HipPosition = new Vector3(0.2f, -0.2f, 0.3f);
            layout.HipEuler = new Vector3(-38f, -14f, 22f);
            layout.AdsPosition = layout.HipPosition;
        }

        static void BuildThrown(ref ViewModelLayout layout, WeaponViewProfile p)
        {
            Transform root = layout.Root;
            float length = p.bodyLength;

            Part(root, "Handle", Vector3.zero, new Vector3(0.018f, 0.024f, 0.09f), DarkMaterial(p));
            Part(root, "Blade", new Vector3(0f, 0f, 0.045f + length * 0.5f), new Vector3(0.005f, 0.03f, length), BodyMaterial(p));
            Part(root, "Ring", new Vector3(0f, 0f, -0.05f), new Vector3(0.006f, 0.022f, 0.012f), AccentMaterial(p));

            layout.Muzzle = Anchor(root, "Tip", new Vector3(0f, 0f, 0.045f + length));
            layout.Grip = Anchor(root, "Grip Hold", Vector3.zero);
            layout.HipPosition = new Vector3(0.19f, -0.13f, 0.36f);
            layout.HipEuler = new Vector3(-58f, -6f, 8f);
            layout.AdsPosition = new Vector3(0.15f, -0.1f, 0.36f);
        }

        // ------------------------------------------------------------------ helpers

        static AttachmentVisual VisualOf(WeaponBuild build, AttachmentSlot slot)
        {
            AttachmentDefinition attachment = build.Get(slot);
            return attachment != null ? attachment.visual : AttachmentVisual.None;
        }

        public const string GunSet = "GunParts";

        /// <summary>Which detailed model each part of the layout uses. Anything not listed is a bevelled box.</summary>
        public static string ModelFor(string part)
        {
            switch (part)
            {
                case "Receiver": case "Handguard": case "Barrel": case "Suppressor": case "MuzzleDevice": case "Stock":
                case "Grip": case "Magazine": case "Drum": case "VerticalGrip": case "AngledGrip": case "Laser":
                case "SightFrame": case "Scope": case "ScopeMount": case "Tube": case "Mouth": case "Tail": case "Band":
                case "Blade": case "Handle":
                    return part;
                case "RearSightL": case "RearSightR": case "FrontSight": case "Sight":
                    return "Post";
                case "Ring":
                    return "Band";
                default:
                    return "Box";
            }
        }

        /// <summary>One part of the weapon, a detailed model stretched to <paramref name="size"/>, in <paramref name="material"/>.</summary>
        static Transform Part(Transform root, string name, Vector3 position, Vector3 size, Material material)
        {
            ModelMesh model = ModelLibrary.Get(GunSet, ModelFor(name));
            if (model == null)
                return GreyboxKit.Visual(root, name, PrimitiveType.Cube, position, size, material, castShadows: _shadows).transform;

            var go = new GameObject(name);
            go.transform.SetParent(root, false);
            go.transform.localPosition = position;
            go.transform.localScale = size;
            Material dark = _dark != null ? _dark : material;
            Material accent = _accent != null ? _accent : material;
            ModelLibrary.Attach(go, model, zone =>
            {
                switch (zone)
                {
                    case ModelZone.Dark: return dark;
                    case ModelZone.Metal: return ModelMaterials.Metal;
                    case ModelZone.Glow: return accent;
                    default: return material;
                }
            }, _shadows);
            return go.transform;
        }

        static Transform Anchor(Transform root, string name, Vector3 position)
        {
            var anchor = new GameObject(name).transform;
            anchor.SetParent(root, false);
            anchor.localPosition = position;
            return anchor;
        }
    }
}
