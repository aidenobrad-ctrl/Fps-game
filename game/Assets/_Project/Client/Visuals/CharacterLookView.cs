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
            _uniform = Own(ModelMaterials.Cloth(pattern.Pattern, uniform.Color, Shade(uniform.Color, gear.Color)));
            _gear = Own(ModelMaterials.Cloth(PatternKind.Plain, gear.Color, gear.Color));
            _skin = Keep(ModelMaterials.Lit(_skinBase));
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
            var headgear = (HeadgearKind)look.Item(CosmeticSlot.Headgear).Shape;
            string hair = HairShows(headgear) ? HairModel((HairKind)look.Item(CosmeticSlot.Hair).Shape) : null;
            if (hair != null) Wear(hair, "Head");
            foreach (string model in HeadgearModels(headgear)) Wear(model, "Head");
            string back = BackModel((BackKind)look.Item(CosmeticSlot.Back).Shape);
            if (back != null) Wear(back, "Torso");
        }

        /// <summary>The models that make up a piece of headgear (the hairstyle is worn as well where <see cref="HairShows"/> says).</summary>
        public static string[] HeadgearModels(HeadgearKind kind)
        {
            switch (kind)
            {
                case HeadgearKind.Cap: return new[] { "Cap" };
                case HeadgearKind.Helmet: return new[] { "Helmet" };
                case HeadgearKind.Beanie: return new[] { "Beanie" };
                case HeadgearKind.Headset: return new[] { "Headset" };
                case HeadgearKind.Boonie: return new[] { "Boonie" };
                case HeadgearKind.HelmetHeadset: return new[] { "Helmet", "HelmetHeadset" };
                case HeadgearKind.Bandana: return new[] { "Bandana" };
                default: return new string[0];
            }
        }

        /// <summary>Whether the hairstyle shows under this headgear: with nothing on, a headset or a bandana.</summary>
        public static bool HairShows(HeadgearKind kind) =>
            kind == HeadgearKind.None || kind == HeadgearKind.Headset || kind == HeadgearKind.Bandana;

        /// <summary>The model for a hairstyle, or null for none (shaved: the scalp's own stubble).</summary>
        public static string HairModel(HairKind kind)
        {
            switch (kind)
            {
                case HairKind.Buzz: return "HairBuzz";
                case HairKind.Shaved: return null;
                case HairKind.SidePart: return "HairSidePart";
                case HairKind.SlickBack: return "HairSlickBack";
                case HairKind.Mohawk: return "HairMohawk";
                case HairKind.Curly: return "HairCurly";
                case HairKind.Bun: return "HairBun";
                default: return "HairCrew";
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
            MeshRenderer renderer = ModelLibrary.Attach(go, model, _soldier.ZoneMaterial, castShadows: true);
            // A hairstyle's strands, and any other maps the model was baked with.
            ModelMaterials.ApplyMaps(renderer, name, model.TexelScale);
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

        Material Own(Material shared) => Keep(new Material(shared));

        /// <summary>A material made for this view alone, destroyed with it.</summary>
        Material Keep(Material material)
        {
            _owned.Add(material);
            return material;
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
