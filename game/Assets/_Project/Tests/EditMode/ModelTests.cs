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
        public void TheSoldier_IsOneSkinnedBody_OnASkeletonOfEveryBone()
        {
            ModelSet soldier = LoadSet(SoldierView.Set);
            var bones = soldier.Bones.Select(b => b.Name).ToList();
            foreach (string name in SoldierView.Names) Assert.That(bones, Does.Contain(name));
            Assert.That(soldier.Bones[bones.IndexOf("Head")].Pivot.y, Is.InRange(1.4f, 1.6f), "the neck");
            Assert.That(soldier.Bones[bones.IndexOf("ThighL")].Pivot.x, Is.LessThan(0f), "left is -x");

            ModelData body = soldier.Models.Single(m => m.Name == "Body");
            WellFormed(body);
            Assert.That(body.Skinned, Is.True);
            Assert.That(body.Weight1.All(w => w >= 0f && w <= 0.5f), "the nearer bone always leads");
            Assert.That(body.Weight1.Count(w => w > 0.05f), Is.GreaterThan(500), "the skin blends between bones at the joints");
            // Standing, the top of the head is about 1.75 m up and the soles touch the floor.
            Assert.That(body.Positions.Max(p => p.y), Is.InRange(1.7f, 1.85f));
            Assert.That(body.Positions.Min(p => p.y), Is.InRange(-0.01f, 0.02f));
            // A face, armbands for the team, and no glowing visor.
            foreach (ModelZone zone in new[] { ModelZone.Skin, ModelZone.Eye, ModelZone.Iris, ModelZone.Team, ModelZone.Trim, ModelZone.Primary })
                Assert.That(body.Zones, Has.Member(zone), zone.ToString());
            Assert.That(body.Zones, Has.No.Member(ModelZone.Glow));

            foreach (string side in new[] { "L", "R" })
            {
                WellFormed(soldier.Models.Single(m => m.Name == "FPForearm" + side));
                WellFormed(soldier.Models.Single(m => m.Name == "FPHand" + side));
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
