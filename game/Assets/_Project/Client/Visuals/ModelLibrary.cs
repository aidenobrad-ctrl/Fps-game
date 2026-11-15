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
    /// "Soldier", the segments of a player's body; "GunParts", the detailed parts weapons are
    /// built from.
    ///
    /// If a file is missing or unreadable the game carries on with its simple shapes: callers
    /// get null and fall back.
    /// </summary>
    public static class ModelLibrary
    {
        static readonly Dictionary<string, Dictionary<string, ModelMesh>> Sets = new Dictionary<string, Dictionary<string, ModelMesh>>();

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics() => Sets.Clear();

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
                    foreach (ModelData data in ModelFile.Parse(asset.bytes)) models[data.Name] = ToMesh(data);
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

        static ModelMesh ToMesh(ModelData data)
        {
            var mesh = new Mesh { name = data.Name };
            mesh.vertices = data.Positions;
            mesh.normals = data.Normals;
            mesh.uv = data.Uvs;
            mesh.subMeshCount = data.Indices.Length;
            for (int i = 0; i < data.Indices.Length; i++) mesh.SetTriangles(data.Indices[i], i, false);
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

    /// <summary>The fixed materials models share: bare metal, dark rubber and webbing.</summary>
    public static class ModelMaterials
    {
        static Material _metal, _dark;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void ResetStatics() => _metal = _dark = null;

        public static Material Metal
        {
            get
            {
                if (_metal != null) return _metal;
                _metal = new Material(GreyboxMaterials.Flat(new Color(0.42f, 0.43f, 0.45f))) { name = "Model Metal" };
                Tune(_metal, metallic: 0.75f, smoothness: 0.58f);
                return _metal;
            }
        }

        public static Material Dark
        {
            get
            {
                if (_dark != null) return _dark;
                _dark = new Material(GreyboxMaterials.Flat(new Color(0.075f, 0.08f, 0.088f))) { name = "Model Dark" };
                Tune(_dark, metallic: 0f, smoothness: 0.32f);
                return _dark;
            }
        }

        public static void Tune(Material material, float metallic, float smoothness)
        {
            if (material.HasProperty("_Metallic")) material.SetFloat("_Metallic", metallic);
            if (material.HasProperty("_Smoothness")) material.SetFloat("_Smoothness", smoothness);
            if (material.HasProperty("_Glossiness")) material.SetFloat("_Glossiness", smoothness);
        }
    }
}
