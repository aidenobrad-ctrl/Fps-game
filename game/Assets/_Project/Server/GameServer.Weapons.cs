using System.Collections.Generic;
using UnityEngine;
using Recoil.Shared.Combat;
using Recoil.Shared.Loadouts;
using Recoil.Shared.Match;
using Recoil.Shared.Net;
using Recoil.Shared.Weapons;

namespace Recoil.Server
{
    /// <summary>
    /// Weapons that break and weapons that change hands.
    ///
    /// A shot that lands on the weapon in someone's hands (<see cref="HitZone.Weapon"/>) does
    /// them no harm, but may break it: the harder the shot would have hit, the likelier
    /// (<see cref="WeaponBreaking.Chance"/>). A broken weapon is gone until they are placed
    /// again; they switch to the best one they have left, and with all three broken they fight
    /// with their fists, which cannot break.
    ///
    /// Taking someone out takes the weapon they were holding: it goes into the same slot of
    /// the winner's loadout, new and full, replacing what was there, and it is theirs until
    /// they go down (a round won carries it into the next). Not in Gun Game, where the ladder
    /// decides what everyone carries.
    ///
    /// Both happen at the end of the tick, after every shot of it has landed, and reach
    /// everyone as a rearm (the new weapons) and a <see cref="WeaponEventMessage"/> (what happened).
    /// </summary>
    public sealed partial class GameServer
    {
        readonly System.Random _breakRandom = new System.Random(0x5EED);
        /// <summary>Players whose weapons changed this tick, and the slot to put in their hands (-1: decide).</summary>
        readonly List<(int Player, int Prefer, int Fresh)> _rearmDue = new List<(int, int, int)>(4);
        readonly List<WeaponEventMessage> _weaponEvents = new List<WeaponEventMessage>(4);

        /// <summary>Where a player stands, and what they hold, for the bodies that get shot at.</summary>
        public static BodyPose PoseOf(ServerPlayer player)
        {
            if (player.Sim == null) return default;
            WeaponDefinition held = player.Sim.Inventory != null ? player.Sim.ActiveBuild?.Weapon : null;
            return BodyPose.From(player.Sim.Motor.State, BodyShapes.Held(held));
        }

        /// <summary>A shot landed on the weapon in a player's hands. Rolls for whether it breaks.</summary>
        bool OnWeaponStruck(PlayerVitals vitals, DamageInfo info)
        {
            ServerPlayer victim = _players[vitals.PlayerId];
            if (victim == null || !victim.Spawned || victim.Sim == null) return false;

            int slot = victim.Sim.Inventory.ActiveIndex;
            WeaponBuild build = victim.Sim.ActiveBuild;
            if (build == null || build.Weapon.weaponId == BodyShapes.FistsId) return false;
            // Already broken this tick by another pellet: once is enough.
            if ((victim.Broken & (1 << slot)) != 0) return false;

            float chance = _config.weaponBreakChance >= 0f ? _config.weaponBreakChance : WeaponBreaking.Chance(info.Amount);
            if (_breakRandom.NextDouble() >= chance) return false;

            victim.Broken |= (byte)(1 << slot);
            // A weapon picked up and then broken is not theirs to keep any more.
            victim.Taken[slot] = null;
            ServerPlayer attacker = info.Attacker is PlayerVitals from ? _players[from.PlayerId] : null;
            _rearmDue.Add((victim.Id, -1, -1));
            _weaponEvents.Add(new WeaponEventMessage
            {
                Kind = WeaponEventKind.Broken,
                PlayerId = victim.Id,
                OtherId = attacker != null ? attacker.Id : WeaponEventMessage.Nobody,
                Slot = (byte)slot,
                WeaponId = build.Weapon.weaponId,
            });
            return true;
        }

        /// <summary>Someone was taken out: whoever did it takes the weapon they were holding.</summary>
        void TakeWeapon(ServerPlayer victim, ServerPlayer killer)
        {
            if (killer == null || killer == victim || !killer.Alive || victim.Sim == null || !_mode.WeaponPickups) return;
            int slot = victim.Sim.Inventory.ActiveIndex;
            LoadoutData carried = _placements[victim.Id].Carried;
            WeaponBuildData held = carried?.GetWeapon(slot);
            if (held == null || string.IsNullOrEmpty(held.weaponId) || held.weaponId == BodyShapes.FistsId) return;

            int current = killer.Sim.Inventory.ActiveIndex;
            bool onFists = killer.OnFists;
            killer.Taken[slot] = held.Clone();
            killer.Broken &= (byte)~(1 << slot);
            // Into their hands if they had nothing better (fists) or it replaces the one they hold.
            _rearmDue.Add((killer.Id, onFists || slot == current ? slot : -1, slot));
            _weaponEvents.Add(new WeaponEventMessage
            {
                Kind = WeaponEventKind.Taken,
                PlayerId = killer.Id,
                OtherId = victim.Id,
                Slot = (byte)slot,
                WeaponId = held.weaponId,
            });
        }

        /// <summary>End of the tick: hand out the weapons that changed, and tell everyone why.</summary>
        void SettleWeapons()
        {
            for (int i = 0; i < _rearmDue.Count; i++)
            {
                (int id, int prefer, int fresh) = _rearmDue[i];
                ServerPlayer player = _players[id];
                if (player == null || !player.Alive) continue;
                // Several changes to one player in a tick: the last one decides, having seen them all.
                bool later = false;
                for (int j = i + 1; j < _rearmDue.Count && !later; j++) later = _rearmDue[j].Player == id;
                if (later) continue;
                RefreshArms(player, prefer, fresh);
            }
            _rearmDue.Clear();

            foreach (WeaponEventMessage message in _weaponEvents)
            {
                ServerPlayer player = _players[message.PlayerId];
                WeaponEventMessage sent = message;
                if (player != null)
                {
                    sent.Broken = player.Broken;
                    sent.Fists = player.OnFists;
                }
                _out.Reset();
                NetMessages.Write(_out, sent);
                Broadcast(_out, reliable: true);
            }
            _weaponEvents.Clear();
        }

        /// <summary>
        /// What a player carries now: what they were placed with, with the weapons they took
        /// in place of their own, less the ones that broke, and fists if nothing is left.
        /// </summary>
        void RefreshArms(ServerPlayer player, int prefer, int fresh)
        {
            LoadoutData carried = (player.SpawnCarried ?? new LoadoutData()).Clone();
            byte mask = player.SpawnMask == 0 ? MatchLoadouts.AllSlots : player.SpawnMask;
            for (int slot = 0; slot < Loadout.WeaponSlots; slot++)
            {
                if (player.Taken[slot] == null) continue;
                SetWeapon(carried, slot, player.Taken[slot].Clone());
                mask |= (byte)(1 << slot);
            }
            mask &= (byte)~player.Broken;

            bool wereOnFists = player.OnFists;
            player.OnFists = (mask & MatchLoadouts.WeaponBits) == 0;
            if (player.OnFists)
            {
                SetWeapon(carried, MatchLoadouts.MeleeSlot, new WeaponBuildData { weaponId = BodyShapes.FistsId });
                mask = (byte)((mask & MatchLoadouts.UtilityBit) | (1 << MatchLoadouts.MeleeSlot));
            }

            int current = player.Sim.Inventory.ActiveIndex;
            int active;
            if (player.OnFists) active = MatchLoadouts.MeleeSlot;
            else if (prefer >= 0 && (mask & (1 << prefer)) != 0) active = prefer;
            else if ((mask & (1 << current)) != 0 && !(wereOnFists && current == MatchLoadouts.MeleeSlot)) active = current;
            else active = FirstUsable(mask);

            RearmCore(player, carried, mask, active, fresh);
        }

        static int FirstUsable(byte mask)
        {
            for (int slot = 0; slot < Loadout.WeaponSlots; slot++)
            {
                if ((mask & (1 << slot)) != 0) return slot;
            }
            return MatchLoadouts.MeleeSlot;
        }

        static void SetWeapon(LoadoutData data, int slot, WeaponBuildData weapon)
        {
            switch (slot)
            {
                case 0: data.primary = weapon; break;
                case 1: data.secondary = weapon; break;
                default: data.melee = weapon; break;
            }
        }

        /// <summary>A placed player's loadout with the weapons they took laid over their own.</summary>
        static LoadoutData WithTaken(LoadoutData carried, ServerPlayer player)
        {
            bool any = false;
            for (int slot = 0; slot < Loadout.WeaponSlots; slot++) any |= player.Taken[slot] != null;
            if (!any) return carried;
            LoadoutData with = carried.Clone();
            for (int slot = 0; slot < Loadout.WeaponSlots; slot++)
            {
                if (player.Taken[slot] != null) SetWeapon(with, slot, player.Taken[slot].Clone());
            }
            return with;
        }
    }

}
