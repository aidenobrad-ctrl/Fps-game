using System.Collections.Generic;
using UnityEngine;
using Recoil.Shared.Combat;
using Recoil.Shared.Cosmetics;
using Recoil.Shared.Match;

namespace Recoil.Client.Visuals
{
    /// <summary>
    /// Dresses a character body in a <see cref="CharacterLook"/>. The body is the Blender-made
    /// soldier (<see cref="SoldierView"/>): the uniform in its colour and pattern, the plate
    /// carrier, pads, helmet and pack in the gear colour, the face and neck in the skin tone,
    /// and the chosen headgear and back item from the "Gear" models. If the model files are
    /// missing, the hitbox shapes themselves are coloured instead.
    ///
    /// Everything added here is for looking at only. It has no colliders, so it can never be
    /// hit or block a shot, and nobody is harder or easier to hit for what they wear. Team
    /// armbands (blue for a teammate, red for anyone else) are on every outfit, so a player
    /// can always be told apart from the other side.
    /// </summary>
    public sealed class CharacterLookView
    {
        public const string GearSet = "Gear";

        readonly SoldierView _soldier;
        readonly List<(MeshRenderer Renderer, HitZone Zone)> _boxes = new List<(MeshRenderer, HitZone)>();
        readonly List<Material> _owned = new List<Material>();
        readonly List<GameObject> _worn = new List<GameObject>();
        Material _uniform, _gear, _skin, _lips;
        Color _uniformTint = Color.white, _gearBase = Color.white, _skinBase = Color.white;
        CharacterLook _shown;

        /// <summary>The animated soldier, or null when the model files are missing and the simple shapes are shown.</summary>
        public SoldierView Soldier => _soldier;

        public CharacterLookView(UnityCharacterBody body)
        {
            if (SoldierView.Available)
            {
                _soldier = new SoldierView(body.Root, castShadows: true);
            }
            else
            {
                foreach (UnityCharacterBody.Part part in body.Parts)
                {
                    GameObject go = part.Transform.gameObject;
                    go.AddComponent<MeshFilter>().sharedMesh = GreyboxKit.PrimitiveMesh(part.Round ? PrimitiveType.Sphere : PrimitiveType.Cube);
                    _boxes.Add((go.AddComponent<MeshRenderer>(), part.Zone));
                }
            }
            Apply(new CharacterLook());
        }

        /// <summary>Dresses the body. Asking again for the look already shown does nothing.</summary>
        public void Apply(CharacterLook look)
        {
            look = look ?? new CharacterLook();
            if (ReferenceEquals(look, _shown)) return;
            _shown = look;

            CosmeticItem uniform = look.Item(CosmeticSlot.SuitColor), gear = look.Item(CosmeticSlot.TrimColor);
            CosmeticItem pattern = look.Item(CosmeticSlot.Pattern), skin = look.Item(CosmeticSlot.Skin);
            _uniformTint = pattern.Pattern == PatternKind.Plain ? uniform.Color : Color.white;
            _gearBase = gear.Color;
            // The soldier's face is painted: its material takes a tint that brings the paint to this tone.
            _skinBase = _soldier != null ? ModelMaterials.SkinTint(skin.Color) : skin.Color;

            // Each view has its own copies, so a hit flash on one player does not light up another.
            Release();
            _uniform = Own(LookMaterials.Patterned(pattern.Pattern, uniform.Color, Shade(uniform.Color, gear.Color)));
            _gear = Own(LookMaterials.Patterned(PatternKind.Plain, gear.Color, gear.Color));
            _skin = Own(GreyboxMaterials.Flat(_skinBase));
            GreyboxMaterials.SetColor(_skin, _skinBase);
            if (_soldier != null) ModelMaterials.TextureSkin(_skin);
            _lips = Own(GreyboxMaterials.Flat(Lips(skin.Color)));
            // Cloth is matte, gear a little less so, skin has a soft sheen.
            ModelMaterials.Tune(_uniform, 0f, 0.14f);
            ModelMaterials.Tune(_gear, 0f, 0.24f);
            ModelMaterials.Tune(_skin, 0f, 0.36f);
            ModelMaterials.Tune(_lips, 0f, 0.45f);

            if (_soldier == null)
            {
                foreach ((MeshRenderer renderer, HitZone zone) in _boxes)
                    renderer.sharedMaterial = zone == HitZone.Head ? _skin : zone == HitZone.Limb ? _gear : _uniform;
                return;
            }

            _soldier.SetMaterials(_uniform, _gear, _skin, _lips);
            foreach (GameObject worn in _worn)
            {
                if (worn != null) Object.Destroy(worn);
            }
            _worn.Clear();
            foreach (string model in HeadgearModels((HeadgearKind)look.Item(CosmeticSlot.Headgear).Shape)) Wear(model, "Head");
            string back = BackModel((BackKind)look.Item(CosmeticSlot.Back).Shape);
            if (back != null) Wear(back, "Torso");
        }

        /// <summary>The models that make up a piece of headgear. Hair shows under anything that leaves the head bare.</summary>
        public static string[] HeadgearModels(HeadgearKind kind)
        {
            switch (kind)
            {
                case HeadgearKind.Cap: return new[] { "Cap" };
                case HeadgearKind.Helmet: return new[] { "Helmet" };
                case HeadgearKind.Beanie: return new[] { "Beanie" };
                case HeadgearKind.Headset: return new[] { "Hair", "Headset" };
                case HeadgearKind.Boonie: return new[] { "Boonie" };
                case HeadgearKind.HelmetHeadset: return new[] { "Helmet", "HelmetHeadset" };
                case HeadgearKind.Bandana: return new[] { "Hair", "Bandana" };
                default: return new[] { "Hair" };
            }
        }

        /// <summary>The model for a back item, or null for nothing.</summary>
        public static string BackModel(BackKind kind)
        {
            switch (kind)
            {
                case BackKind.AssaultPack: return "AssaultPack";
                case BackKind.HydrationPack: return "HydrationPack";
                case BackKind.RadioPack: return "RadioPack";
                case BackKind.Rucksack: return "Rucksack";
                case BackKind.BedrollPack: return "BedrollPack";
                case BackKind.Scarf: return "Scarf";
                default: return null;
            }
        }

        void Wear(string name, string bone)
        {
            ModelMesh model = ModelLibrary.Get(GearSet, name);
            if (model == null) return;
            var go = new GameObject(name);
            go.transform.SetParent(_soldier.Bone(bone), false);
            go.transform.localPosition = model.Pivot - _soldier.Pivot(bone);
            ModelLibrary.Attach(go, model, _soldier.ZoneMaterial, castShadows: true);
            _worn.Add(go);
        }

        /// <summary>Team armbands: blue for a teammate, red for an opponent, or plain (the preview, or nobody to tell apart).</summary>
        public void SetSide(bool show, bool friendly)
        {
            if (_soldier == null) return;
            _soldier.SetTeam(show ? GreyboxMaterials.Unlit(friendly ? new Color(0.25f, 0.6f, 1f) : new Color(1f, 0.25f, 0.2f)) : null);
        }

        /// <summary>0 for normal colours, 1 for white: the flash when a shot lands.</summary>
        public void Flash(float amount)
        {
            // A patterned uniform is tinted white already; brightening it means lifting the pattern towards white.
            GreyboxMaterials.SetColor(_uniform, Color.Lerp(_uniformTint, Color.white * 2f, amount));
            GreyboxMaterials.SetColor(_gear, Color.Lerp(_gearBase, Color.white, amount));
            // The painted face is a mid grey, so its flash goes past white to show as bright.
            GreyboxMaterials.SetColor(_skin, Color.Lerp(_skinBase, _soldier != null ? Color.white * 1.6f : Color.white, amount));
        }

        /// <summary>Poses the soldier for how its player is moving. Nothing to do for the simple shapes.</summary>
        public void Animate(in SoldierMotion motion, float dt) => _soldier?.Animate(motion, dt);

        /// <summary>Kept for callers that pose the body and then ask the look to catch up; the soldier's gear moves with its bones.</summary>
        public void Follow() { }

        public void Destroy()
        {
            Release();
            _soldier?.Destroy();
        }

        // ------------------------------------------------------------------ helpers

        /// <summary>The pattern's second colour: a shade of the uniform, leaning a little towards the gear.</summary>
        static Color Shade(Color uniform, Color gear)
        {
            Color.RGBToHSV(uniform, out float h, out float s, out float v);
            Color darker = Color.HSVToRGB(h, s, v > 0.5f ? v - 0.28f : v + 0.18f);
            return Color.Lerp(darker, gear, 0.25f);
        }

        /// <summary>Lips: the skin a shade darker and redder.</summary>
        static Color Lips(Color skin) => new Color(skin.r * 0.86f, skin.g * 0.68f, skin.b * 0.66f);

        Material Own(Material shared)
        {
            var copy = new Material(shared);
            _owned.Add(copy);
            return copy;
        }

        void Release()
        {
            foreach (Material material in _owned)
            {
                if (material != null) Object.Destroy(material);
            }
            _owned.Clear();
        }
    }
}
