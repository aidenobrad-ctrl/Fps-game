using System;
using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using Recoil.Client.Cosmetics;
using Recoil.Shared.Cosmetics;
using Recoil.Shared.Net;

namespace Recoil.Tests
{
    /// <summary>The cosmetic catalog, the rules for a look, how a look is sent, and where it is saved.</summary>
    public class CosmeticsTests
    {
        [Test]
        public void EverySlot_HasItems_WithUniqueIds_AndTheDefaultLookIsMadeOfRealItems()
        {
            foreach (CosmeticSlot slot in CosmeticCatalog.Slots)
            {
                IReadOnlyList<CosmeticItem> items = CosmeticCatalog.InSlot(slot);
                Assert.That(items.Count, Is.InRange(2, 255), slot + ": items are sent as one byte");
                var ids = new HashSet<string>();
                for (int i = 0; i < items.Count; i++)
                {
                    Assert.That(ids.Add(items[i].Id), Is.True, slot + " has two items called " + items[i].Id);
                    Assert.That(items[i].Index, Is.EqualTo(i));
                    Assert.That(items[i].Name, Is.Not.Empty);
                    Assert.That(CosmeticCatalog.At(slot, i), Is.SameAs(items[i]));
                }
            }

            var look = new CharacterLook();
            foreach (CosmeticSlot slot in CosmeticCatalog.Slots)
                Assert.That(CosmeticCatalog.Find(slot, look.Get(slot)), Is.Not.Null, slot + " default '" + look.Get(slot) + "' is not in the catalog");
            Assert.That(CosmeticCatalog.Default(CosmeticSlot.WeaponSkin).Factory, Is.True, "weapons start in their own colours");
            Assert.That(CosmeticCatalog.Default(CosmeticSlot.Headgear).Shape, Is.EqualTo((byte)HeadgearKind.Helmet), "soldiers start in a helmet");
            Assert.That(CosmeticCatalog.Default(CosmeticSlot.Hair).Shape, Is.EqualTo((byte)HairKind.Crew), "and a crew cut under it");
            Assert.That(CosmeticCatalog.Count(CosmeticSlot.Hair), Is.EqualTo(Enum.GetValues(typeof(HairKind)).Length), "every hairstyle can be chosen");
        }

        [Test]
        public void ALook_IsCleanedUp_WhateverItSays()
        {
            var messy = new CharacterLook
            {
                suitColor = "not-a-colour",
                pattern = "tiger",
                headgear = null,
                weaponSkin = "gilded",
                weaponSkins = new[]
                {
                    new WeaponSkinChoice { weaponId = "ar_m4a1", skinId = "carbon" },
                    new WeaponSkinChoice { weaponId = "ar_m4a1", skinId = "magma" },        // a second skin for the same weapon
                    new WeaponSkinChoice { weaponId = "smg_mp5", skinId = "gilded" },    // the same as every weapon already has
                    new WeaponSkinChoice { weaponId = "sg_m870", skinId = "no-such-skin" },
                    new WeaponSkinChoice { weaponId = new string('x', 80), skinId = "carbon" },
                    null,
                },
            };

            CharacterLook clean = LookRules.Sanitize(messy);
            Assert.That(clean.suitColor, Is.EqualTo(CosmeticCatalog.Default(CosmeticSlot.SuitColor).Id));
            Assert.That(clean.pattern, Is.EqualTo("tiger"));
            Assert.That(clean.headgear, Is.EqualTo("helmet"));
            Assert.That(clean.weaponSkins.Length, Is.EqualTo(1));
            Assert.That(clean.SkinFor("ar_m4a1").Id, Is.EqualTo("carbon"));
            Assert.That(clean.SkinFor("smg_mp5").Id, Is.EqualTo("gilded"));
            Assert.That(clean.SkinFor("anything_else").Id, Is.EqualTo("gilded"));
            Assert.That(LookRules.Sanitize(null), Is.Not.Null);

            var crowded = new CharacterLook { weaponSkins = new WeaponSkinChoice[100] };
            for (int i = 0; i < crowded.weaponSkins.Length; i++)
                crowded.weaponSkins[i] = new WeaponSkinChoice { weaponId = "weapon_" + i, skinId = "carbon" };
            Assert.That(LookRules.Sanitize(crowded).weaponSkins.Length, Is.EqualTo(LookRules.MaxWeaponSkins));
        }

        [Test]
        public void WeaponSkins_CanBeSetOneAtATime_OrForEveryWeapon()
        {
            var look = new CharacterLook();
            look.SetSkin("ar_m4a1", "tiger");
            look.SetSkin("pistol_m17", "neon_grid");
            Assert.That(look.SkinFor("ar_m4a1").Id, Is.EqualTo("tiger"));
            Assert.That(look.SkinFor("pistol_m17").Id, Is.EqualTo("neon_grid"));
            Assert.That(look.SkinFor("sg_m870").Factory, Is.True);

            look.SetSkin("ar_m4a1", "factory");
            Assert.That(look.weaponSkins.Length, Is.EqualTo(1), "choosing the skin every weapon has removes the weapon's own");

            look.SetSkinForAll("arctic");
            Assert.That(look.weaponSkins, Is.Empty);
            Assert.That(look.SkinFor("pistol_m17").Id, Is.EqualTo("arctic"));
        }

        [Test]
        public void ALook_SurvivesTheTrip_InUnderAKilobyte()
        {
            var look = new CharacterLook
            {
                suitColor = "#3A5F1C", trimColor = "saffron", pattern = "circuit", headgear = "boonie", hair = "mohawk", skin = "#6B4A33",
                back = "scarf", weaponSkin = "carbon",
            };
            for (int i = 0; i < LookRules.MaxWeaponSkins; i++) look.SetSkin("weapon_number_" + i.ToString("00"), i % 2 == 0 ? "tiger" : "nebula");

            var writer = new NetWriter(64);
            NetMessages.WriteLook(writer, look);
            Assert.That(writer.Length, Is.LessThan(1110), "a look must fit in a player's info with room to spare");

            var reader = new NetReader();
            reader.Reset(writer.Data, 0, writer.Length);
            CharacterLook read = NetMessages.ReadLook(reader);
            Assert.That(reader.Failed, Is.False);
            Assert.That(reader.Remaining, Is.EqualTo(0));
            foreach (CosmeticSlot slot in CosmeticCatalog.Slots) Assert.That(read.Get(slot), Is.EqualTo(look.Get(slot)), slot.ToString());
            Assert.That(read.weaponSkins.Length, Is.EqualTo(LookRules.MaxWeaponSkins));
            Assert.That(read.SkinFor("weapon_number_03").Id, Is.EqualTo("nebula"));

            // Cut short anywhere, it fails cleanly and gives a usable look.
            for (int length = 0; length < writer.Length; length++)
            {
                reader.Reset(writer.Data, 0, length);
                CharacterLook partial = NetMessages.ReadLook(reader);
                Assert.That(reader.Failed, Is.True, "cut to " + length);
                Assert.That(partial, Is.Not.Null);
            }

            // An item this copy of the game does not have (a newer version's) becomes the default.
            var odd = new NetWriter(16);
            for (int i = 0; i < CosmeticCatalog.Slots.Length; i++) odd.WriteByte(250);
            odd.WriteByte(0);
            reader.Reset(odd.Data, 0, odd.Length);
            CharacterLook unknown = NetMessages.ReadLook(reader);
            Assert.That(reader.Failed, Is.False);
            Assert.That(unknown.headgear, Is.EqualTo("helmet"));
        }

        [Test]
        public void MixedColours_AreKept_ForTheUniformGearAndSkin_ButNothingElse()
        {
            Assert.That(CosmeticCatalog.TryParseColour("#3a5F1c", out UnityEngine.Color colour), Is.True);
            Assert.That(colour.g, Is.EqualTo(0x5F / 255f).Within(0.001f));
            foreach (string bad in new[] { "#12345", "123456", "#12345G", "#1234567", "", null })
                Assert.That(CosmeticCatalog.TryParseColour(bad, out _), Is.False, bad ?? "null");

            CosmeticItem mixed = CosmeticCatalog.FindOrDefault(CosmeticSlot.SuitColor, "#3A5F1C");
            Assert.That(mixed.Custom, Is.True);
            Assert.That(mixed.Id, Is.EqualTo("#3A5F1C"));
            Assert.That(CosmeticCatalog.CustomColour(CosmeticSlot.Skin, colour).Id, Is.EqualTo("#3A5F1C"), "the id is the colour");

            var look = new CharacterLook { suitColor = "#3a5f1c", trimColor = "#FFFFFF", skin = "#6B4A33", pattern = "#123456", headgear = "#ABCDEF" };
            CharacterLook clean = LookRules.Sanitize(look);
            Assert.That(clean.suitColor, Is.EqualTo("#3A5F1C"), "written the one way");
            Assert.That(clean.trimColor, Is.EqualTo("#FFFFFF"));
            Assert.That(clean.skin, Is.EqualTo("#6B4A33"));
            Assert.That(clean.pattern, Is.EqualTo("plain"), "patterns cannot be mixed");
            Assert.That(clean.headgear, Is.EqualTo("helmet"));
        }

        [Test]
        public void RandomLooks_AreRealItems_AndRepeatForTheSameSeed()
        {
            var seen = new HashSet<string>();
            for (uint seed = 1; seed < 60; seed++)
            {
                CharacterLook look = LookRules.Random(seed);
                Assert.That(LookRules.Sanitize(look).suitColor, Is.EqualTo(look.suitColor));
                Assert.That(look.trimColor, Is.Not.EqualTo(look.suitColor));
                Assert.That(LookRules.Random(seed).headgear, Is.EqualTo(look.headgear));
                seen.Add(look.headgear);
            }
            Assert.That(seen.Count, Is.GreaterThan(3), "bots should not all look alike");
        }

        [Test]
        public void TheLook_IsSaved_AndComesBack_AndABadFileIsKeptAside()
        {
            string folder = Path.Combine(Path.GetTempPath(), "pb-look-" + System.Guid.NewGuid().ToString("N").Substring(0, 8));
            string file = Path.Combine(folder, CosmeticsLibrary.FileName);
            try
            {
                long now = 1000;
                var library = new CosmeticsLibrary(file, () => now);
                Assert.That(library.Look.suitColor, Is.EqualTo(new CharacterLook().suitColor), "nothing saved yet: the default");
                int changes = 0;
                library.Changed += () => changes++;

                library.Edit(look => look.Set(CosmeticSlot.Headgear, "beanie"));
                library.Edit(look => look.Set(CosmeticSlot.SuitColor, "#204060"));
                library.Edit(look => look.SetSkin("ar_m4a1", "gilded"));
                Assert.That(changes, Is.EqualTo(3));
                Assert.That(library.Look.updatedAt, Is.GreaterThanOrEqualTo(now));

                var again = new CosmeticsLibrary(file, () => now);
                Assert.That(again.Look.headgear, Is.EqualTo("beanie"));
                Assert.That(again.Look.suitColor, Is.EqualTo("#204060"));
                Assert.That(again.Look.SkinFor("ar_m4a1").Id, Is.EqualTo("gilded"));

                File.WriteAllText(file, "{ this is not json");
                var broken = new CosmeticsLibrary(file, () => now);
                Assert.That(broken.Look.headgear, Is.EqualTo("helmet"));
                Assert.That(File.Exists(file + ".unreadable"), Is.True);
            }
            finally
            {
                if (Directory.Exists(folder)) Directory.Delete(folder, true);
            }
        }
    }
}
