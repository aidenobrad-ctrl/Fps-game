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
        static List<ModelData> Load(string set)
        {
            string root = Environment.GetEnvironmentVariable("RECOIL_PROJECT") ?? "";
            foreach (string candidate in new[] { Path.Combine(root, "Assets/_Project/Resources/Models", set + ".bytes"), "Assets/_Project/Resources/Models/" + set + ".bytes" })
            {
                if (File.Exists(candidate)) return ModelFile.Parse(File.ReadAllBytes(candidate));
            }
            Assert.Fail("Resources/Models/" + set + ".bytes was not found. Make it with art/blender/recoil_models.py.");
            return null;
        }

        static void WellFormed(ModelData model)
        {
            Assert.That(model.Positions.Length, Is.GreaterThan(8), model.Name);
            Assert.That(model.Normals.Length, Is.EqualTo(model.Positions.Length), model.Name);
            Assert.That(model.Normals.All(n => Mathf.Abs(n.magnitude - 1f) < 0.02f), model.Name + ": normals are unit length");
            Assert.That(model.Indices.Sum(i => i.Length), Is.GreaterThan(30), model.Name);
            Assert.That(model.Zones.Distinct().Count(), Is.EqualTo(model.Zones.Length), model.Name + ": one submesh per zone");
        }

        [Test]
        public void TheSoldier_HasEverySegment_AtHumanProportions()
        {
            Dictionary<string, ModelData> soldier = Load("Soldier").ToDictionary(m => m.Name);
            foreach (string name in SoldierView.Names)
            {
                Assert.That(soldier.ContainsKey(name), name);
                WellFormed(soldier[name]);
            }
            Assert.That(soldier["Head"].Pivot.y, Is.InRange(1.4f, 1.6f), "the neck");
            Assert.That(soldier["ThighL"].Pivot.x, Is.LessThan(0f), "left is -x");
            Assert.That(soldier["ThighR"].Pivot.x, Is.GreaterThan(0f));
            // Standing, the top of the helmet is about 1.8 m up and the soles touch the floor.
            float top = soldier["Head"].Positions.Max(p => p.y) + soldier["Head"].Pivot.y;
            float sole = soldier["FootL"].Positions.Min(p => p.y) + soldier["FootL"].Pivot.y;
            Assert.That(top, Is.InRange(1.75f, 1.9f));
            Assert.That(sole, Is.InRange(-0.01f, 0.02f));
            // Shoulder pads carry the team colour; the helmet has its visor.
            Assert.That(soldier["Torso"].Zones, Does.Contain(ModelZone.Team));
            Assert.That(soldier["Head"].Zones, Does.Contain(ModelZone.Glow));
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
