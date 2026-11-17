using System.Collections.Generic;
using UnityEngine;
using Recoil.Shared.Combat;
using Recoil.Shared.Movement;
using Recoil.Shared.Simulation;

namespace Recoil.Shared.Match
{
    /// <summary>
    /// A character's body made of real Unity colliders: a head, a torso, two arms and two
    /// legs, each a separate hitbox. The parts shrink towards the ground as the eye height
    /// drops, so a crouching or sliding player is a smaller target.
    ///
    /// The body parts hang under their own root rather than under the movement capsule.
    /// That lets the server put the parts back where they were a moment ago to judge a shot
    /// without disturbing where the player actually is.
    /// </summary>
    public sealed class UnityCharacterBody : ICharacterBody
    {
        /// <summary>One body part. The client hangs a mesh on <see cref="Transform"/> to make it visible.</summary>
        public sealed class Part
        {
            public Transform Transform;
            public Collider Collider;
            public Hitbox Hitbox;
            public HitZone Zone;
            public bool Round;
            /// <summary>Local position and size when standing upright.</summary>
            public Vector3 Offset, Size;
        }

        readonly GameObject _capsule;
        readonly Transform _root;
        readonly List<Part> _parts = new List<Part>(6);
        readonly float _standEyeHeight;
        /// <summary>The weapon in their hands: a box that turns with where they look. Only there while they hold one.</summary>
        readonly Transform _weapon;
        readonly BoxCollider _weaponCollider;
        readonly Hitbox _weaponHitbox;
        bool _hittable = true, _holding;

        public CharacterController Controller { get; }
        /// <summary>At the feet, turned to face the way the character faces.</summary>
        public Transform Root => _root;
        public IReadOnlyList<Part> Parts => _parts;

        public UnityCharacterBody(string name, MovementConfig movement, bool withController, bool server)
        {
            _standEyeHeight = movement.standEyeHeight;

            if (withController)
            {
                _capsule = new GameObject(name) { layer = server ? GameLayers.ServerCharacter : GameLayers.Character };
                Controller = _capsule.AddComponent<CharacterController>();
            }

            _root = new GameObject(name + " Body").transform;
            int layer = server ? GameLayers.ServerHitbox : GameLayers.Hitbox;

            // Kinematic: the parts are moved every tick, and the physics engine handles that
            // far better for a body it knows can move than for colliders it took to be scenery.
            var rigidbody = _root.gameObject.AddComponent<Rigidbody>();
            rigidbody.isKinematic = true;
            rigidbody.useGravity = false;

            // The same shapes as the firing range's dummies and the server's own hit check.
            foreach (BodyShapes.Part part in BodyShapes.Parts)
                AddPart(part.Name, part.Zone, part.Round, part.Offset, part.Size, layer);

            var weapon = new GameObject("Weapon") { layer = layer };
            weapon.transform.SetParent(_root, false);
            _weapon = weapon.transform;
            _weaponCollider = weapon.AddComponent<BoxCollider>();
            _weaponCollider.size = Vector3.one;
            _weaponCollider.enabled = false;
            _weaponHitbox = weapon.AddComponent<Hitbox>();
            _weaponHitbox.zone = HitZone.Weapon;

            SetPose(new BodyPose { EyeHeight = _standEyeHeight });
        }

        void AddPart(string name, HitZone zone, bool round, Vector3 offset, Vector3 size, int layer)
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(_root, false);

            // Unit-sized colliders; the part's scale gives them their real size.
            Collider collider;
            if (round)
            {
                var sphere = go.AddComponent<SphereCollider>();
                sphere.radius = 0.5f;
                collider = sphere;
            }
            else
            {
                var box = go.AddComponent<BoxCollider>();
                box.size = Vector3.one;
                collider = box;
            }

            var hitbox = go.AddComponent<Hitbox>();
            hitbox.zone = zone;
            _parts.Add(new Part
            {
                Transform = go.transform,
                Collider = collider,
                Hitbox = hitbox,
                Zone = zone,
                Round = round,
                Offset = offset,
                Size = size,
            });
        }

        public void SetOwner(IDamageable owner)
        {
            foreach (Part part in _parts) part.Hitbox.SetOwner(owner);
            _weaponHitbox.SetOwner(owner);
        }

        public void SetPose(in BodyPose pose)
        {
            _root.SetPositionAndRotation(pose.Position, Quaternion.Euler(0f, pose.Yaw, 0f));

            float squash = BodyShapes.Squash(pose.EyeHeight, _standEyeHeight);
            for (int i = 0; i < _parts.Count; i++)
            {
                Part part = _parts[i];
                BodyShapes.Part shape = BodyShapes.Parts[i];
                part.Transform.localPosition = BodyShapes.LocalCentre(shape, squash);
                part.Transform.localScale = BodyShapes.LocalSize(shape, squash);
            }

            _holding = pose.Held.Present;
            if (_holding)
            {
                BodyShapes.WeaponFrame(pose.EyeHeight, _standEyeHeight, pose.Pitch, pose.Held, out Vector3 pocket, out float turn);
                _weapon.localPosition = pocket + BodyShapes.RotateX(pose.Held.Centre, turn);
                _weapon.localRotation = Quaternion.Euler(turn, 0f, 0f);
                _weapon.localScale = pose.Held.Size;
            }
            _weaponCollider.enabled = _hittable && _holding;
        }

        public void SetHittable(bool hittable)
        {
            _hittable = hittable;
            foreach (Part part in _parts) part.Collider.enabled = hittable;
            _weaponCollider.enabled = hittable && _holding;
        }

        public void Destroy()
        {
            if (_root != null) Object.Destroy(_root.gameObject);
            if (_capsule != null) Object.Destroy(_capsule);
        }
    }

    /// <summary>The physical world, made of Unity physics.</summary>
    public sealed class UnityGameWorld : IGameWorld
    {
        // One process can hold a server and a client at once (hosting from the game). The
        // level's collision is the same for both, so it is built once and shared.
        static readonly Dictionary<string, GameObject> Arenas = new Dictionary<string, GameObject>();

        readonly bool _server;

        /// <param name="server">True for the server's side of the world: its bodies go on the server's layers.</param>
        public UnityGameWorld(bool server)
        {
            _server = server;
        }

        public void BuildArena(ArenaLayout layout)
        {
            if (Arenas.TryGetValue(layout.Id, out GameObject existing) && existing != null) return;

            // Maps are all built around the same centre, so only one can stand at a time.
            foreach (KeyValuePair<string, GameObject> other in Arenas)
            {
                if (other.Value == null) continue;
                other.Value.SetActive(false);       // gone from physics now, not at the end of the frame
                Object.Destroy(other.Value);
            }
            Arenas.Clear();

            var root = new GameObject("Arena Collision (" + layout.DisplayName + ")");
            foreach (ArenaBox box in layout.Boxes)
            {
                var block = new GameObject("Block") { layer = GameLayers.Default };
                block.transform.SetParent(root.transform, false);
                block.transform.localPosition = box.Center;
                block.AddComponent<BoxCollider>().size = box.Size;
            }
            Arenas[layout.Id] = root;

            // New static colliders are not seen by queries until the physics scene catches up.
            Physics.SyncTransforms();
        }

        public ICharacterBody CreateBody(string name, MovementConfig movement, bool withController) =>
            new UnityCharacterBody(name, movement, withController, _server);

        public void SyncPhysics() => Physics.SyncTransforms();
    }
}
