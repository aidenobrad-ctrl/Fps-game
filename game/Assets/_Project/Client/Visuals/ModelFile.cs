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
        /// <summary>A helmet: the suit's colour, darker.</summary>
        Helmet = 6,
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
    }

    /// <summary>
    /// Reads the model files made by art/blender/recoil_models.py:
    ///
    ///   "RCM1"; uint16 mesh count; then per mesh: name (uint8 length, UTF-8), pivot (3
    ///   floats), uint16 vertex count, vertices (position 3 floats, normal 3 floats, uv 2
    ///   floats), uint8 submesh count, then per submesh: uint8 zone, uint32 index count,
    ///   uint16 indices.
    ///
    /// All little-endian, positions in metres relative to the pivot, in the game's frame,
    /// triangles wound for Unity. Plain C#, so it can be checked outside Unity.
    /// </summary>
    public static class ModelFile
    {
        public static List<ModelData> Parse(byte[] bytes)
        {
            var models = new List<ModelData>();
            using var reader = new BinaryReader(new MemoryStream(bytes));
            if (Encoding.ASCII.GetString(reader.ReadBytes(4)) != "RCM1") throw new InvalidDataException("Not a Recoil model file.");

            int count = reader.ReadUInt16();
            for (int m = 0; m < count; m++)
            {
                var model = new ModelData();
                model.Name = Encoding.UTF8.GetString(reader.ReadBytes(reader.ReadByte()));
                model.Pivot = new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());

                int vertices = reader.ReadUInt16();
                model.Positions = new Vector3[vertices];
                model.Normals = new Vector3[vertices];
                model.Uvs = new Vector2[vertices];
                for (int v = 0; v < vertices; v++)
                {
                    model.Positions[v] = new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());
                    model.Normals[v] = new Vector3(reader.ReadSingle(), reader.ReadSingle(), reader.ReadSingle());
                    model.Uvs[v] = new Vector2(reader.ReadSingle(), reader.ReadSingle());
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
                models.Add(model);
            }
            return models;
        }
    }
}
