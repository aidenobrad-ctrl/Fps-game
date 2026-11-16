using System.Collections.Generic;
using UnityEngine;

namespace Recoil.Client.Visuals
{
    /// <summary>A model's mesh, ready to draw, and which material each of its submeshes takes.</summary>
    public sealed class ModelMesh
    {
        public string Name;
        public Vector3 Pivot;
        public Mesh Mesh;
        public ModelZone[] Zones;
    }

    /// <summary>
    /// The game's Blender-made models (Resources/Models/*.bytes), read once and kept. Sets:
    /// "Soldier", a player's skinned body and skeleton (and the first-person sleeves and
    /// gloves); "Gear", headgear and back items; "GunParts", the detailed parts weapons are
    /// built from.
    ///
    /// If a file is missing or unreadable the game carries on with its simple shapes: callers
    /// get null and fall back.
    /// </summary>
    public static class ModelLibrary
    {
        static readonly Dictionary<string, Dictionary<string, ModelMesh>> Sets = new Dictionary<string, Dictionary<string, ModelMesh>>();
        static readonly Dictionary<string, List<ModelBone>> Skeletons = new Dictionary<string, List<ModelBone>>();

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics()
        {
            Sets.Clear();
            Skeletons.Clear();
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
                    ModelSet file = ModelFile.ParseSet(asset.bytes);
                    Skeletons[set] = file.Bones;
                    foreach (ModelData data in file.Models) models[data.Name] = ToMesh(data, file.Bones);
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
            return new ModelMesh { Name = data.Name, Pivot = data.Pivot, Mesh = mesh, Zones = data.Zones };
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
    public static class ModelMaterials
    {
        static Material _metal, _dark, _hair, _eye, _iris, _boots;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics() => _metal = _dark = _hair = _eye = _iris = _boots = null;

        public static Material Metal => Make(ref _metal, "Model Metal", new Color(0.42f, 0.43f, 0.45f), 0.75f, 0.58f);
        public static Material Dark => Make(ref _dark, "Model Dark", new Color(0.075f, 0.08f, 0.088f), 0f, 0.3f);
        public static Material Hair => Make(ref _hair, "Model Hair", new Color(0.07f, 0.05f, 0.035f), 0f, 0.3f);
        public static Material EyeWhite => Make(ref _eye, "Model Eye", new Color(0.86f, 0.85f, 0.81f), 0f, 0.75f);
        public static Material Iris => Make(ref _iris, "Model Iris", new Color(0.09f, 0.06f, 0.04f), 0f, 0.85f);
        public static Material Boots => Make(ref _boots, "Model Boots", new Color(0.12f, 0.09f, 0.065f), 0f, 0.38f);

        static Material Make(ref Material cache, string name, Color colour, float metallic, float smoothness)
        {
            if (cache != null) return cache;
            cache = new Material(GreyboxMaterials.Flat(colour)) { name = name };
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
