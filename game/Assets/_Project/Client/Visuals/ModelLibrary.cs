using System.Collections.Generic;
using UnityEngine;
using Recoil.Shared.Cosmetics;

namespace Recoil.Client.Visuals
{
    /// <summary>A model's mesh, ready to draw, and which material each of its submeshes takes.</summary>
    public sealed class ModelMesh
    {
        public string Name;
        public Vector3 Pivot;
        public Mesh Mesh;
        public ModelZone[] Zones;
        /// <summary>Bound to the set's skeleton, in its rest pose, rather than hung on one bone.</summary>
        public bool Skinned;
        /// <summary>Metres of surface per unit of texture coordinates: how big a pattern laid over its UVs comes out.</summary>
        public float TexelScale;
        /// <summary>The model's named points: where a weapon is held, fitted and fired from.</summary>
        public IReadOnlyList<ModelPoint> Points = System.Array.Empty<ModelPoint>();

        /// <summary>A named point of the model, if it has one.</summary>
        public bool TryPoint(string name, out ModelPoint point)
        {
            foreach (ModelPoint candidate in Points)
            {
                if (candidate.Name != name) continue;
                point = candidate;
                return true;
            }
            point = default;
            return false;
        }
    }

    /// <summary>
    /// The game's Blender-made models (Resources/Models/*.bytes), read once and kept. Sets:
    /// "Soldier", a player's skinned body and skeleton (and the first-person sleeves and
    /// gloves); "Gear", headgear and back items; "Guns", every weapon modelled whole at its
    /// real size, with the points that say how to hold it, and the first-person hands;
    /// "GunParts", the parts a weapon without a model of its own is built from.
    ///
    /// If a file is missing or unreadable the game carries on with its simple shapes: callers
    /// get null and fall back.
    /// </summary>
    public static class ModelLibrary
    {
        static readonly Dictionary<string, Dictionary<string, ModelMesh>> Sets = new Dictionary<string, Dictionary<string, ModelMesh>>();
        static readonly Dictionary<string, List<ModelBone>> Skeletons = new Dictionary<string, List<ModelBone>>();
        static readonly Dictionary<string, List<ModelMesh>> InOrder = new Dictionary<string, List<ModelMesh>>();

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics()
        {
            Sets.Clear();
            Skeletons.Clear();
            InOrder.Clear();
        }

        /// <summary>A set's skeleton, in order (a bone always after its parent), or an empty list.</summary>
        public static IReadOnlyList<ModelBone> Bones(string set)
        {
            Load(set);
            return Skeletons.TryGetValue(set, out List<ModelBone> bones) ? bones : (IReadOnlyList<ModelBone>)new ModelBone[0];
        }

        /// <summary>A model from a set, or null if there is no such model.</summary>
        public static ModelMesh Get(string set, string name)
        {
            Dictionary<string, ModelMesh> models = Load(set);
            return models != null && models.TryGetValue(name, out ModelMesh model) ? model : null;
        }

        public static bool Has(string set) => Load(set) != null && Load(set).Count > 0;

        /// <summary>Every model in a set, in the order the file lists them; empty if the set could not be read.</summary>
        public static IReadOnlyList<ModelMesh> All(string set)
        {
            Load(set);
            return InOrder.TryGetValue(set, out List<ModelMesh> models) ? models : (IReadOnlyList<ModelMesh>)new ModelMesh[0];
        }

        static Dictionary<string, ModelMesh> Load(string set)
        {
            if (Sets.TryGetValue(set, out Dictionary<string, ModelMesh> loaded)) return loaded;
            Dictionary<string, ModelMesh> models = null;
            var asset = Resources.Load<TextAsset>("Models/" + set);
            if (asset == null)
            {
                Debug.LogWarning("Recoil: Resources/Models/" + set + ".bytes is missing; using simple shapes instead.");
            }
            else
            {
                try
                {
                    models = new Dictionary<string, ModelMesh>();
                    var ordered = new List<ModelMesh>();
                    ModelSet file = ModelFile.ParseSet(asset.bytes);
                    Skeletons[set] = file.Bones;
                    foreach (ModelData data in file.Models)
                    {
                        ModelMesh mesh = ToMesh(data, file.Bones);
                        models[data.Name] = mesh;
                        ordered.Add(mesh);
                    }
                    InOrder[set] = ordered;
                }
                catch (System.Exception e)
                {
                    Debug.LogWarning("Recoil: could not read the " + set + " models (" + e.Message + "); using simple shapes instead.");
                    models = null;
                }
                Resources.UnloadAsset(asset);
            }
            Sets[set] = models;
            return models;
        }

        static ModelMesh ToMesh(ModelData data, List<ModelBone> bones)
        {
            var mesh = new Mesh { name = data.Name };
            mesh.vertices = data.Positions;
            mesh.normals = data.Normals;
            mesh.uv = data.Uvs;
            mesh.subMeshCount = data.Indices.Length;
            for (int i = 0; i < data.Indices.Length; i++) mesh.SetTriangles(data.Indices[i], i, false);
            // Tangents, for the normal maps the soldier's meshes are lit through.
            mesh.RecalculateTangents();
            if (data.Skinned)
            {
                // Each vertex follows one bone, or two near a joint. The bones rest at their
                // joints, unturned, so the bind pose only moves the joint to the origin.
                var weights = new BoneWeight[data.Positions.Length];
                for (int v = 0; v < weights.Length; v++)
                {
                    float second = data.Bone1[v] == data.Bone0[v] ? 0f : data.Weight1[v];
                    weights[v] = new BoneWeight
                    {
                        boneIndex0 = data.Bone0[v], weight0 = 1f - second,
                        boneIndex1 = data.Bone1[v], weight1 = second,
                    };
                }
                mesh.boneWeights = weights;
                var bindposes = new Matrix4x4[bones.Count];
                for (int b = 0; b < bones.Count; b++) bindposes[b] = Matrix4x4.Translate(-bones[b].Pivot);
                mesh.bindposes = bindposes;
            }
            mesh.RecalculateBounds();
            mesh.UploadMeshData(true);
            return new ModelMesh
            {
                Name = data.Name, Pivot = data.Pivot, Mesh = mesh, Zones = data.Zones, Skinned = data.Skinned,
                TexelScale = TexelScale(data), Points = data.Points.ToArray(),
            };
        }

        /// <summary>The square root of the surface's area over its area in texture space.</summary>
        static float TexelScale(ModelData data)
        {
            double world = 0.0, uv = 0.0;
            foreach (int[] triangles in data.Indices)
            {
                for (int i = 0; i + 2 < triangles.Length; i += 3)
                {
                    int a = triangles[i], b = triangles[i + 1], c = triangles[i + 2];
                    world += Vector3.Cross(data.Positions[b] - data.Positions[a], data.Positions[c] - data.Positions[a]).magnitude;
                    Vector2 u = data.Uvs[b] - data.Uvs[a], v = data.Uvs[c] - data.Uvs[a];
                    uv += System.Math.Abs(u.x * v.y - u.y * v.x);
                }
            }
            return uv > 1e-12 ? (float)System.Math.Sqrt(world / uv) : 0f;
        }

        /// <summary>Hangs a model on <paramref name="parent"/>, with one material per zone from <paramref name="materials"/>.</summary>
        public static MeshRenderer Attach(GameObject go, ModelMesh model, System.Func<ModelZone, Material> materials, bool castShadows)
        {
            go.AddComponent<MeshFilter>().sharedMesh = model.Mesh;
            var renderer = go.AddComponent<MeshRenderer>();
            var assigned = new Material[model.Zones.Length];
            for (int i = 0; i < assigned.Length; i++) assigned[i] = materials(model.Zones[i]);
            renderer.sharedMaterials = assigned;
            renderer.shadowCastingMode = castShadows ? UnityEngine.Rendering.ShadowCastingMode.On : UnityEngine.Rendering.ShadowCastingMode.Off;
            renderer.receiveShadows = castShadows;
            return renderer;
        }
    }

    /// <summary>The fixed materials models share: bare metal, dark rubber and webbing, hair, eyes, boot leather.</summary>
    /// <summary>
    /// The materials the soldier and their kit are drawn with. All are lit through a normal
    /// map, which a mesh with baked maps (the uniform, the kit, the face, each hairstyle)
    /// supplies through <see cref="ApplyMaps"/>; elsewhere the map is flat. The uniform's
    /// pattern is a detail layer over the colour, laid at the same size on every mesh.
    /// </summary>
    public static class ModelMaterials
    {
        static Material _metal, _dark, _hair, _eye, _iris, _boots;
        static Texture2D _skinTexture, _eyeTexture, _skinNormal;
        static bool _texturesLooked;
        static Material _litBase, _patternBase;
        static bool _basesLooked;
        static readonly Dictionary<string, Material> Cloths = new Dictionary<string, Material>();
        static readonly Dictionary<string, (Texture2D Normal, Texture2D Shade)> Maps = new Dictionary<string, (Texture2D, Texture2D)>();

        /// <summary>The painted skin is a neutral grey this bright; a tone is divided by it to colour it.</summary>
        const float SkinTextureGrey = 0.75f;
        /// <summary>How often the uniform's pattern repeats, per metre of cloth.</summary>
        public const float PatternRepeatsPerMetre = 2f;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics()
        {
            _metal = _dark = _hair = _eye = _iris = _boots = null;
            _skinTexture = _eyeTexture = _skinNormal = null;
            _texturesLooked = false;
            _litBase = _patternBase = null;
            _basesLooked = false;
            Cloths.Clear();
            Maps.Clear();
        }

        public static Material Metal => Make(ref _metal, "Model Metal", new Color(0.42f, 0.43f, 0.45f), 0.75f, 0.58f);
        public static Material Dark => Make(ref _dark, "Model Dark", new Color(0.075f, 0.08f, 0.088f), 0f, 0.3f);
        public static Material Hair => Make(ref _hair, "Model Hair", new Color(0.07f, 0.05f, 0.035f), 0f, 0.36f);
        public static Material Iris => Make(ref _iris, "Model Iris", new Color(0.09f, 0.06f, 0.04f), 0f, 0.85f);
        public static Material Boots => Make(ref _boots, "Model Boots", new Color(0.12f, 0.09f, 0.065f), 0f, 0.38f);

        /// <summary>
        /// A new lit material in one colour, ready for a normal map. The caller owns it. The
        /// material assets it starts from (Resources/Materials/SoldierLit and SoldierPattern)
        /// are what keep these shader variants in a built game.
        /// </summary>
        public static Material Lit(Color colour)
        {
            LoadBases();
            Material material = _litBase != null ? new Material(_litBase) : new Material(GreyboxMaterials.Flat(colour));
            GreyboxMaterials.SetColor(material, colour);
            if (material.HasProperty("_BumpMap"))
            {
                material.EnableKeyword("_NORMALMAP");
                material.SetTexture("_BumpMap", null);
            }
            return material;
        }

        /// <summary>
        /// Cloth in a colour and pattern, shared: the colour plain, or the pattern (in the colour
        /// and its shade) as a detail layer over a white base, so the shade map under it still shows.
        /// </summary>
        public static Material Cloth(PatternKind pattern, Color a, Color b)
        {
            string key = (int)pattern + ":" + ColorUtility.ToHtmlStringRGB(a) + ":" + ColorUtility.ToHtmlStringRGB(b);
            if (Cloths.TryGetValue(key, out Material cached) && cached != null) return cached;
            Material material;
            if (pattern == PatternKind.Plain)
            {
                material = Lit(a);
            }
            else
            {
                LoadBases();
                material = _patternBase != null ? new Material(_patternBase) : Lit(Color.white);
                GreyboxMaterials.SetColor(material, Color.white);
                if (material.HasProperty("_BumpMap"))
                {
                    material.EnableKeyword("_NORMALMAP");
                    material.SetTexture("_BumpMap", null);
                }
                if (material.HasProperty("_DetailAlbedoMap"))
                {
                    material.EnableKeyword("_DETAIL_MULX2");
                    material.SetTexture("_DetailAlbedoMap", LookMaterials.DetailTexture(pattern, a, b));
                    material.SetFloat("_DetailAlbedoMapScale", 1f);
                }
                else if (material.HasProperty("_MainTex"))
                {
                    // The Built-in pipeline's fallback: the pattern as the main texture.
                    material.SetTexture("_MainTex", LookMaterials.Texture(pattern, a, b));
                }
            }
            material.name = "Cloth " + pattern + " " + key;
            Cloths[key] = material;
            return material;
        }

        /// <summary>
        /// Lays a mesh's baked maps (Resources/Models/[maps]Normal and [maps]Shade, where there
        /// are any) over a renderer, and sizes the uniform's pattern to the mesh's texture
        /// coordinates (texelScale metres per unit; 0 leaves it as the material has it).
        /// </summary>
        public static void ApplyMaps(Renderer renderer, string maps, float texelScale)
        {
            if (renderer == null || string.IsNullOrEmpty(maps)) return;
            (Texture2D normal, Texture2D shade) = MapsFor(maps);
            if (normal == null && shade == null) return;
            var block = new MaterialPropertyBlock();
            renderer.GetPropertyBlock(block);
            if (normal != null) block.SetTexture("_BumpMap", normal);
            if (shade != null) block.SetTexture("_BaseMap", shade);
            if (texelScale > 0f)
            {
                float repeats = PatternRepeatsPerMetre * texelScale;
                block.SetVector("_DetailAlbedoMap_ST", new Vector4(repeats, repeats, 0f, 0f));
            }
            renderer.SetPropertyBlock(block);
        }

        static (Texture2D Normal, Texture2D Shade) MapsFor(string maps)
        {
            if (Maps.TryGetValue(maps, out (Texture2D, Texture2D) known)) return known;
            var found = (NormalMap("Models/" + maps + "Normal"), Resources.Load<Texture2D>("Models/" + maps + "Shade"));
            Maps[maps] = found;
            return found;
        }

        /// <summary>
        /// A normal map, or null if there is none or it was imported as a colour picture
        /// (decoded as colour it would light everything wrongly, so it is better left off).
        /// </summary>
        static Texture2D NormalMap(string path)
        {
            Texture2D map = Resources.Load<Texture2D>(path);
            if (map == null || !map.isDataSRGB) return map;
            Debug.LogWarning("Recoil: Resources/" + path + " is imported as a colour picture, not a normal map, so it is left off. " +
                             "Select it in the Project window and set Texture Type to Normal map.");
            return null;
        }

        static void LoadBases()
        {
            if (_basesLooked) return;
            _basesLooked = true;
            if (UnityEngine.Rendering.GraphicsSettings.currentRenderPipeline == null) return;
            _litBase = Usable(Resources.Load<Material>("Materials/SoldierLit"));
            _patternBase = Usable(Resources.Load<Material>("Materials/SoldierPattern"));
        }

        static Material Usable(Material material) =>
            material != null && material.shader != null && material.shader.isSupported ? material : null;

        /// <summary>The eyes: the eye texture (white, iris and pupil) where there is one, else plain white.</summary>
        public static Material EyeWhite
        {
            get
            {
                if (_eye != null) return _eye;
                LoadTextures();
                Material eye = Make(ref _eye, "Model Eye", _eyeTexture != null ? Color.white : new Color(0.86f, 0.85f, 0.81f), 0f, 0.75f);
                if (_eyeTexture != null && eye.HasProperty("_BaseMap")) eye.SetTexture("_BaseMap", _eyeTexture);
                return eye;
            }
        }

        /// <summary>
        /// The colour to give a skin material for a skin tone. The face's texture is painted in
        /// neutral grey (brows, stubble, lips and the scalp darker); this scales it so its grey
        /// comes out as the tone. Without the texture, the tone itself.
        /// </summary>
        public static Color SkinTint(Color tone)
        {
            LoadTextures();
            if (_skinTexture == null) return tone;
            Color linear = tone.linear * (1f / SkinTextureGrey);
            linear.a = 1f;
            return linear.gamma;
        }

        /// <summary>Puts the painted face, and its pores and lines, on a skin material (one made with <see cref="SkinTint"/>'s colour).</summary>
        public static void TextureSkin(Material skin)
        {
            LoadTextures();
            if (_skinTexture != null && skin.HasProperty("_BaseMap")) skin.SetTexture("_BaseMap", _skinTexture);
            if (_skinNormal != null && skin.HasProperty("_BumpMap"))
            {
                skin.EnableKeyword("_NORMALMAP");
                skin.SetTexture("_BumpMap", _skinNormal);
                // Pores and fine lines, not a rough surface: at full strength a low sun grains the face.
                if (skin.HasProperty("_BumpScale")) skin.SetFloat("_BumpScale", 0.55f);
            }
        }

        static void LoadTextures()
        {
            if (_texturesLooked) return;
            _texturesLooked = true;
            _skinTexture = Resources.Load<Texture2D>("Models/SkinAlbedo");
            _skinNormal = NormalMap("Models/SkinNormal");
            _eyeTexture = Resources.Load<Texture2D>("Models/EyeAlbedo");
        }

        static Material Make(ref Material cache, string name, Color colour, float metallic, float smoothness)
        {
            if (cache != null) return cache;
            cache = Lit(colour);
            cache.name = name;
            Tune(cache, metallic, smoothness);
            return cache;
        }

        public static void Tune(Material material, float metallic, float smoothness)
        {
            if (material.HasProperty("_Metallic")) material.SetFloat("_Metallic", metallic);
            if (material.HasProperty("_Smoothness")) material.SetFloat("_Smoothness", smoothness);
            if (material.HasProperty("_Glossiness")) material.SetFloat("_Glossiness", smoothness);
        }
    }
}
