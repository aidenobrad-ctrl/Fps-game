using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using NUnit.Framework;
using Recoil.Client.Visuals;
using Recoil.Client.Weapons;
using UnityEngine;

namespace Recoil.Tests
{
    /// <summary>The Blender-made model files: readable, complete, and the right size.</summary>
    public class ModelTests
    {
        static ModelSet LoadSet(string set)
        {
            string root = Environment.GetEnvironmentVariable("RECOIL_PROJECT") ?? "";
            foreach (string candidate in new[] { Path.Combine(root, "Assets/_Project/Resources/Models", set + ".bytes"), "Assets/_Project/Resources/Models/" + set + ".bytes" })
            {
                if (File.Exists(candidate)) return ModelFile.ParseSet(File.ReadAllBytes(candidate));
            }
            Assert.Fail("Resources/Models/" + set + ".bytes was not found. Make it with art/blender/recoil_models.py.");
            return null;
        }

        static List<ModelData> Load(string set) => LoadSet(set).Models;

        static void WellFormed(ModelData model)
        {
            Assert.That(model.Positions.Length, Is.GreaterThan(8), model.Name);
            Assert.That(model.Normals.Length, Is.EqualTo(model.Positions.Length), model.Name);
            Assert.That(model.Normals.All(n => Mathf.Abs(n.magnitude - 1f) < 0.02f), model.Name + ": normals are unit length");
            Assert.That(model.Indices.Sum(i => i.Length), Is.GreaterThan(30), model.Name);
            Assert.That(model.Zones.Distinct().Count(), Is.EqualTo(model.Zones.Length), model.Name + ": one submesh per zone");
        }

        [Test]
        public void TheSoldier_IsSkinnedBodyUniformAndKit_OnASkeletonOfEveryBone()
        {
            ModelSet soldier = LoadSet(SoldierView.Set);
            var bones = soldier.Bones.Select(b => b.Name).ToList();
            foreach (string name in SoldierView.Names) Assert.That(bones, Does.Contain(name));
            Assert.That(soldier.Bones[bones.IndexOf("Head")].Pivot.y, Is.InRange(1.4f, 1.6f), "the neck");
            Assert.That(soldier.Bones[bones.IndexOf("ThighL")].Pivot.x, Is.LessThan(0f), "left is -x");

            List<ModelData> skinned = soldier.Models.Where(m => m.Skinned).ToList();
            Assert.That(skinned.Select(m => m.Name), Is.EquivalentTo(new[] { "Body", "Uniform", "Kit" }));
            foreach (ModelData part in skinned)
            {
                WellFormed(part);
                Assert.That(part.Weight1.All(w => w >= 0f && w <= 0.5f), part.Name + ": the nearer bone always leads");
            }
            Assert.That(skinned.Sum(m => m.Weight1.Count(w => w > 0.05f)), Is.GreaterThan(500), "the skin and cloth blend between bones at the joints");
            // Standing, the top of the head is about 1.75 m up and the soles touch the floor.
            Assert.That(skinned.Max(m => m.Positions.Max(p => p.y)), Is.InRange(1.7f, 1.85f));
            Assert.That(skinned.Min(m => m.Positions.Min(p => p.y)), Is.InRange(-0.01f, 0.02f));

            // A face with eyes, mapped onto their textures.
            ModelData body = skinned.Single(m => m.Name == "Body");
            foreach (ModelZone zone in new[] { ModelZone.Skin, ModelZone.Eye })
            {
                int slot = Array.IndexOf(body.Zones, zone);
                Assert.That(slot, Is.GreaterThanOrEqualTo(0), zone.ToString());
                Assert.That(body.Indices[slot].All(i => body.Uvs[i].x >= -0.001f && body.Uvs[i].x <= 1.001f && body.Uvs[i].y >= -0.001f && body.Uvs[i].y <= 1.001f),
                    zone + ": texture coordinates inside the texture");
            }
            // A uniform and kit in the player's colours, armbands for the team, boots, and no glowing visor.
            var zones = skinned.SelectMany(m => m.Zones).ToList();
            foreach (ModelZone zone in new[] { ModelZone.Primary, ModelZone.Trim, ModelZone.Team, ModelZone.Dark, ModelZone.Boots, ModelZone.Metal })
                Assert.That(zones, Has.Member(zone), zone.ToString());
            Assert.That(zones, Has.No.Member(ModelZone.Glow));

            foreach (string side in new[] { "L", "R" })
            {
                WellFormed(soldier.Models.Single(m => m.Name == "FPForearm" + side));
                WellFormed(soldier.Models.Single(m => m.Name == "FPHand" + side));
            }
        }

        [Test]
        public void TheBakedTextures_AreThere()
        {
            string root = Environment.GetEnvironmentVariable("RECOIL_PROJECT") ?? "";
            var textures = new List<string> { "SkinAlbedo.png", "SkinNormal.jpg", "EyeAlbedo.png", "UniformNormal.jpg", "UniformShade.jpg", "KitNormal.jpg", "KitShade.jpg" };
            foreach (Recoil.Shared.Cosmetics.HairKind kind in Enum.GetValues(typeof(Recoil.Shared.Cosmetics.HairKind)))
            {
                string model = CharacterLookView.HairModel(kind);
                if (model != null) textures.Add(model + "Normal.jpg");
            }
            foreach (string texture in textures)
            {
                bool found = new[] { Path.Combine(root, "Assets/_Project/Resources/Models", texture), "Assets/_Project/Resources/Models/" + texture }.Any(File.Exists);
                Assert.That(found, Is.True, texture + " is made with art/blender/recoil_models.py");
            }
        }

        [Test]
        public void EveryHeadgearAndBackItem_HasItsModels()
        {
            Dictionary<string, ModelData> gear = Load(CharacterLookView.GearSet).ToDictionary(m => m.Name);
            foreach (Recoil.Shared.Cosmetics.HeadgearKind kind in Enum.GetValues(typeof(Recoil.Shared.Cosmetics.HeadgearKind)))
            {
                foreach (string name in CharacterLookView.HeadgearModels(kind))
                {
                    Assert.That(gear.ContainsKey(name), kind + " -> " + name);
                    WellFormed(gear[name]);
                }
            }
            foreach (Recoil.Shared.Cosmetics.HairKind kind in Enum.GetValues(typeof(Recoil.Shared.Cosmetics.HairKind)))
            {
                string name = CharacterLookView.HairModel(kind);
                if (name == null) continue;
                Assert.That(gear.ContainsKey(name), kind + " -> " + name);
                WellFormed(gear[name]);
                // Fitted to the head: over the scalp, not floating above it or sunk into the face.
                Assert.That(gear[name].Positions.Max(p => p.y), Is.InRange(1.73f, 1.82f), name);
                Assert.That(gear[name].Positions.Min(p => p.y), Is.GreaterThan(1.5f), name);
            }
            foreach (Recoil.Shared.Cosmetics.BackKind kind in Enum.GetValues(typeof(Recoil.Shared.Cosmetics.BackKind)))
            {
                string name = CharacterLookView.BackModel(kind);
                if (name == null) continue;
                Assert.That(gear.ContainsKey(name), kind + " -> " + name);
                WellFormed(gear[name]);
            }
        }

        [Test]
        public void EveryWeaponPart_HasAModel_ThatFillsItsBox()
        {
            Dictionary<string, ModelData> parts = Load(ViewModelBuilder.GunSet).ToDictionary(m => m.Name);
            string[] layoutParts =
            {
                "Receiver", "Handguard", "Accent", "Barrel", "Suppressor", "MuzzleDevice", "Stock", "Grip", "Magazine", "Drum",
                "VerticalGrip", "AngledGrip", "Laser", "LaserLens", "SightFrame", "ScopeMount", "Scope", "RearSightL", "RearSightR",
                "FrontSight", "Tube", "Mouth", "Tail", "Band", "Sight", "Handle", "Guard", "Blade", "Ring",
            };
            foreach (string part in layoutParts)
            {
                string model = ViewModelBuilder.ModelFor(part);
                Assert.That(parts.ContainsKey(model), part + " -> " + model);
                ModelData data = parts[model];
                WellFormed(data);
                // Modelled to the unit box, so stretching it to a part's size gives that size (a little detail may stand proud).
                foreach (Vector3 p in data.Positions)
                {
                    Assert.That(Mathf.Abs(p.x), Is.LessThanOrEqualTo(0.56f), model);
                    Assert.That(Mathf.Abs(p.y), Is.LessThanOrEqualTo(0.56f), model);
                    Assert.That(Mathf.Abs(p.z), Is.LessThanOrEqualTo(0.56f), model);
                }
            }
        }
    }
}
