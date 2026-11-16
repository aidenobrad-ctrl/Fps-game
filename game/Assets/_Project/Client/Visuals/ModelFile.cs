using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;

namespace Recoil.Client.Visuals
{
    /// <summary>Which material a part of a model takes. The numbers are the file's.</summary>
    public enum ModelZone : byte
    {
        /// <summary>A suit's colour and pattern, or a gun part's own material.</summary>
        Primary = 0,
        /// <summary>Rubber, webbing, gloves, grips.</summary>
        Dark = 1,
        /// <summary>Bare metal: buckles, screws, rails.</summary>
        Metal = 2,
        /// <summary>Lights: a visor, an accent strip, a lens.</summary>
        Glow = 3,
        /// <summary>A suit's trim colour.</summary>
        Trim = 4,
        /// <summary>The side a player is on: shoulder pads.</summary>
        Team = 5,
        /// <summary>A helmet: the suit's colour, darker. No longer used by the soldier.</summary>
        Helmet = 6,
        /// <summary>Skin, in the player's skin tone.</summary>
        Skin = 7,
        Hair = 8,
        /// <summary>The whites of the eyes.</summary>
        Eye = 9,
        Iris = 10,
        Lips = 11,
        Boots = 12,
    }

    /// <summary>One bone of a skinned model: its name, the bone it hangs from (-1 for none), and its joint.</summary>
    public struct ModelBone
    {
        public string Name;
        public int Parent;
        public Vector3 Pivot;
    }

    /// <summary>One mesh read from a model file, before it becomes a Unity mesh.</summary>
    public sealed class ModelData
    {
        public string Name;
        /// <summary>Where the mesh's origin sits in the model it came from: a joint, for a body segment.</summary>
        public Vector3 Pivot;
        public Vector3[] Positions, Normals;
        public Vector2[] Uvs;
        public ModelZone[] Zones;
        public int[][] Indices;
        /// <summary>For a skinned mesh: each vertex's two bones and the second one's share. Null for a rigid mesh.</summary>
        public byte[] Bone0, Bone1;
        public float[] Weight1;
        public bool Skinned => Bone0 != null;
    }

    /// <summary>Everything in a model file: its skeleton (empty for rigid parts) and its meshes.</summary>
    public sealed class ModelSet
    {
        public readonly List<ModelBone> Bones = new List<ModelBone>();
        public readonly List<ModelData> Models = new List<ModelData>();
    }

    /// <summary>
    /// Reads the model files made by art/blender/recoil_models.py. Two versions:
    ///
    ///   RCM1 (rigid parts): "RCM1"; uint16 mesh count; then per mesh: name (uint8 length,
    ///   UTF-8), pivot (3 floats), uint16 vertex count, vertices (position 3 floats, normal 3
    ///   floats, uv 2 floats), uint8 submesh count, then per submesh: uint8 zone, uint32 index
    ///   count, uint16 indices.
    ///
    ///   RCM2 (a skeleton and skinned meshes): "RCM2"; uint8 bone count; per bone: name, int8
    ///   parent, pivot; then as RCM1, except that each mesh has a flags byte after its pivot
    ///   (1: skinned), and a skinned mesh's vertices each end with two uint8 bones and the
    ///   float weight of the second.
    ///
    /// All little-endian, positions in metres relative to the pivot (a skinned mesh: in the
    /// model's rest pose), in the game's frame, triangles wound for Unity. Plain C#, so it can
    /// be checked outside Unity.
    /// </summary>
    public static class ModelFile
    {
        public static List<ModelData> Parse(byte[] bytes) => ParseSet(bytes).Models;

        public static ModelSet ParseSet(byte[] bytes)
        {
            var set = new ModelSet();
            using var reader = new BinaryReader(new MemoryStream(bytes));
            string magic = Encoding.ASCII.GetString(reader.ReadBytes(4));
            bool v2 = magic == "RCM2";
            if (!v2 && magic != "RCM1") throw new InvalidDataException("Not a Recoil model file.");

            if (v2)
            {
                int bones = reader.ReadByte();
                for (int b = 0; b < bones; b++)
                {
                    var bone = new ModelBone { Name = ReadName(reader), Parent = reader.ReadSByte() };
                    bone.Pivot = new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());
                    if (bone.Parent >= b) throw new InvalidDataException(bone.Name + ": a bone must come after its parent.");
                    set.Bones.Add(bone);
                }
            }

            int count = reader.ReadUInt16();
            for (int m = 0; m < count; m++)
            {
                var model = new ModelData();
                model.Name = ReadName(reader);
                model.Pivot = new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());
                bool skinned = v2 && (reader.ReadByte() & 1) != 0;

                int vertices = reader.ReadUInt16();
                model.Positions = new Vector3[vertices];
                model.Normals = new Vector3[vertices];
                model.Uvs = new Vector2[vertices];
                if (skinned)
                {
                    model.Bone0 = new byte[vertices];
                    model.Bone1 = new byte[vertices];
                    model.Weight1 = new float[vertices];
                }
                for (int v = 0; v < vertices; v++)
                {
                    model.Positions[v] = new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());
                    model.Normals[v] = new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());
                    model.Uvs[v] = new Vector2(reader.ReadSingle(), reader.ReadSingle());
                    if (!skinned) continue;
                    model.Bone0[v] = reader.ReadByte();
                    model.Bone1[v] = reader.ReadByte();
                    model.Weight1[v] = reader.ReadSingle();
                    if (model.Bone0[v] >= set.Bones.Count || model.Bone1[v] >= set.Bones.Count)
                        throw new InvalidDataException(model.Name + ": a vertex names a bone that is not there.");
                }

                int submeshes = reader.ReadByte();
                model.Zones = new ModelZone[submeshes];
                model.Indices = new int[submeshes][];
                for (int s = 0; s < submeshes; s++)
                {
                    model.Zones[s] = (ModelZone)reader.ReadByte();
                    int indexCount = (int)reader.ReadUInt32();
                    if (indexCount % 3 != 0) throw new InvalidDataException(model.Name + ": a submesh is not made of triangles.");
                    var indices = new int[indexCount];
                    for (int i = 0; i < indexCount; i++)
                    {
                        indices[i] = reader.ReadUInt16();
                        if (indices[i] >= vertices) throw new InvalidDataException(model.Name + ": an index points past the vertices.");
                    }
                    model.Indices[s] = indices;
                }
                set.Models.Add(model);
            }
            return set;
        }

        static string ReadName(BinaryReader reader) => Encoding.UTF8.GetString(reader.ReadBytes(reader.ReadByte()));
    }
}
