"""
A realistic human body for Recoil's soldier, from MakeHuman's CC0 assets (art/makehuman).

MakeHuman's base mesh (hm08) is a carefully modelled human of about 13,000 quads with a
face, ears, hands and feet in proper anatomical topology, plus "targets": per-vertex
offsets that turn the neutral base into a man or a woman, young or old, lean or muscular.
This reads the base mesh and its targets, mixes the targets the way MakeHuman does
(macro modifiers), poses the arms down by the sides and curls the fingers into a grip
using MakeHuman's own skeleton and skin weights, and folds those weights onto the game's
fifteen bones.

Everything is in the game's frame: x right, y up, z forward, metres. MakeHuman's frame is
right-handed with the model's left at +x, so x is mirrored on the way in.
"""
import json, math, os
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "makehuman"))


# ---------------------------------------------------------------------------- reading

def read_obj(path):
    """Vertices, texture coordinates and faces (vertex indices, uv indices, group) of an OBJ."""
    verts, uvs, faces = [], [], []
    group = ""
    with open(path) as f:
        for line in f:
            if line.startswith("v "):
                verts.append(tuple(float(x) for x in line.split()[1:4]))
            elif line.startswith("vt "):
                uvs.append(tuple(float(x) for x in line.split()[1:3]))
            elif line.startswith("g "):
                group = line.split()[1]
            elif line.startswith("f "):
                vi, ti = [], []
                for corner in line.split()[1:]:
                    parts = corner.split("/")
                    vi.append(int(parts[0]) - 1)
                    ti.append(int(parts[1]) - 1 if len(parts) > 1 and parts[1] else -1)
                faces.append((vi, ti, group))
    return verts, uvs, faces


def read_target(name):
    """A target: {vertex index: (dx, dy, dz)} in MakeHuman units."""
    offsets = {}
    with open(os.path.join(DATA, "targets", name)) as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            i, dx, dy, dz = line.split()
            offsets[int(i)] = (float(dx), float(dy), float(dz))
    return offsets


# ---------------------------------------------------------------------------- MakeHuman's macro modifiers

def _three(value, low, mid, high):
    """MakeHuman's split of a 0..1 slider into its min, average and max targets."""
    hi = max(0.0, value * 2 - 1)
    lo = max(0.0, 1 - value * 2)
    return {low: lo, mid: 1 - hi - lo, high: hi}


def macro_targets(gender=1.0, age=0.5, muscle=0.5, weight=0.5, height=0.5, proportions=0.5,
                  races=(("african", 1 / 3), ("asian", 1 / 3), ("caucasian", 1 / 3))):
    """The targets MakeHuman mixes for these slider values, with their weights."""
    genders = {"female": 1 - gender, "male": gender}
    # Age 0.5 is 25 years; this model is always an adult, so only young and old mix.
    old = max(0.0, age * 2 - 1)
    ages = {"young": 1 - old, "old": old}
    muscles = _three(muscle, "minmuscle", "averagemuscle", "maxmuscle")
    weights = _three(weight, "minweight", "averageweight", "maxweight")
    heights = {"minheight": max(0.0, 1 - height * 2), "maxheight": max(0.0, height * 2 - 1)}
    props = {"uncommonproportions": max(0.0, 1 - proportions * 2), "idealproportions": max(0.0, proportions * 2 - 1)}

    out = []
    for g, gw in genders.items():
        for a, aw in ages.items():
            if gw * aw <= 0:
                continue
            for race, rw in races:
                if rw > 0:
                    out.append(("macrodetails/%s-%s-%s.target" % (race, g, a), rw * gw * aw))
            for m, mw in muscles.items():
                for w, ww in weights.items():
                    base = gw * aw * mw * ww
                    if base <= 0:
                        continue
                    out.append(("macrodetails/universal-%s-%s-%s-%s.target" % (g, a, m, w), base))
                    for h, hw in heights.items():
                        if hw > 0:
                            out.append(("macrodetails/height/%s-%s-%s-%s-%s.target" % (g, a, m, w, h), base * hw))
                    for p, pw in props.items():
                        if pw > 0:
                            out.append(("macrodetails/proportions/%s-%s-%s-%s-%s.target" % (g, a, m, w, p), base * pw))
    return [(name, w) for name, w in out if w > 1e-4]


# ---------------------------------------------------------------------------- the body

class Human:
    """The shaped base mesh, its joints and its MakeHuman skin weights, before any posing."""

    def __init__(self, **sliders):
        verts, uvs, faces = read_obj(os.path.join(DATA, "3dobjs", "base.obj"))
        co = [list(v) for v in verts]
        self.targets = macro_targets(**sliders)
        for name, w in self.targets:
            for i, (dx, dy, dz) in read_target(name).items():
                c = co[i]
                c[0] += dx * w
                c[1] += dy * w
                c[2] += dz * w
        self.mh = [tuple(c) for c in co]          # shaped, MakeHuman units and frame
        self.uvs = uvs
        self.faces = faces

        skel = json.load(open(os.path.join(DATA, "rigs", "default.mhskel")))
        self.joint_verts = skel["joints"]
        self.bones = skel["bones"]
        mhw = json.load(open(os.path.join(DATA, "rigs", "default_weights.mhw")))
        self.mh_weights = mhw["weights"]            # bone -> [[vertex, weight], ...]

        # Into the game's frame and metres: mirror x, scale so the eyes are at eye height, feet on the floor.
        body = {i for vi, _, g in faces if g == "body" for i in vi}
        min_y = min(co[i][1] for i in body)
        eye = self.joint_mh("eye.L____head")
        self.scale = (1.635 - 0.0) / (eye[1] - min_y) if eye[1] > min_y else 0.1
        self.floor = min_y
        self.co = [self.to_game(c) for c in self.mh]

    def to_game(self, c):
        return Vector((-c[0] * self.scale, (c[1] - self.floor) * self.scale, c[2] * self.scale))

    def joint_mh(self, name):
        ids = self.joint_verts[name]
        n = len(ids)
        return (sum(self.mh[i][0] for i in ids) / n, sum(self.mh[i][1] for i in ids) / n, sum(self.mh[i][2] for i in ids) / n)

    def joint(self, name):
        """A joint (e.g. "upperarm01.L____head") in the game's frame, rest pose."""
        ids = self.joint_verts[name]
        p = Vector()
        for i in ids:
            p += self.co[i]
        return p / len(ids)

    def head_of(self, bone):
        return self.joint(self.bones[bone]["head"])

    def tail_of(self, bone):
        return self.joint(self.bones[bone]["tail"])

    def body_faces(self, groups=("body",)):
        return [(vi, ti) for vi, ti, g in self.faces if g in groups]

    def vertex_weights(self):
        """Per vertex: {MakeHuman bone: weight}."""
        out = [dict() for _ in self.co]
        for bone, pairs in self.mh_weights.items():
            for i, w in pairs:
                out[i][bone] = out[i].get(bone, 0.0) + w
        return out

    # ------------------------------------------------------------------------ posing

    def pose(self, rotations):
        """
        Skins the body to a pose: rotations is {MakeHuman bone: rotation (3x3, model frame)},
        each turning that bone (and everything below it) about its own head. Returns the
        new vertex positions and each bone's 4x4 transform.
        """
        transforms = {}

        def world(bone):
            if bone in transforms:
                return transforms[bone]
            parent = self.bones[bone]["parent"]
            base = world(parent) if parent else Matrix.Identity(4)
            r = rotations.get(bone)
            if r is None:
                transforms[bone] = base
            else:
                h = self.head_of(bone)
                transforms[bone] = base @ Matrix.Translation(h) @ r.to_4x4() @ Matrix.Translation(-h)
            return transforms[bone]

        for bone in self.bones:
            world(bone)
        weights = self.vertex_weights()
        out = []
        for i, c in enumerate(self.co):
            w = weights[i]
            total = sum(w.values())
            if total <= 0:
                out.append(c.copy())
                continue
            p = Vector()
            for bone, wb in w.items():
                p += (transforms[bone] @ c) * (wb / total)
            out.append(p)
        return out, transforms


def rotation_between(a, b):
    """The rotation (3x3) turning direction a onto direction b."""
    return Vector(a).normalized().rotation_difference(Vector(b).normalized()).to_matrix()


def soldier_pose(human, arm_angle=9.0, curl=1.0, foot_apart=0.115):
    """
    Standing straight with the feet under the hips, arms hanging at the sides a little
    away from the body, and the fingers curled into a loose grip: the rest pose the game
    animates from. Returns MakeHuman bone rotations.
    """
    rot = {}
    for side, s in ((".L", -1), (".R", 1)):
        # MakeHuman stands with its feet wide; bring each leg in under its hip.
        hip = human.head_of("upperleg01" + side)
        ankle = human.head_of("foot" + side)
        target = Vector((s * foot_apart, ankle.y, ankle.z))
        rot["upperleg01" + side] = rotation_between(ankle - hip, target - hip)
        # ...and keep the foot flat and pointing ahead.
        rot["foot" + side] = rotation_between(target - hip, ankle - hip)

        shoulder = human.head_of("upperarm01" + side)
        wrist = human.head_of("wrist" + side)
        hang = Vector((s * math.sin(math.radians(arm_angle)), -math.cos(math.radians(arm_angle)), 0.0))
        whole = rotation_between(wrist - shoulder, hang)
        # Most of the turn at the shoulder joint, a little through the collarbone and shoulder.
        q = whole.to_quaternion()
        axis, angle = q.to_axis_angle()
        rot["clavicle" + side] = Matrix.Rotation(angle * 0.12, 3, axis)
        rot["shoulder01" + side] = Matrix.Rotation(angle * 0.13, 3, axis)
        rot["upperarm01" + side] = Matrix.Rotation(angle * 0.75, 3, axis)

        # Curl the fingers about the hand's sideways axis, toward the palm.
        index_base = human.head_of("finger2-1" + side)
        little_base = human.head_of("finger5-1" + side)
        middle_tip = human.tail_of("finger3-3" + side)
        across = (little_base - index_base).normalized()
        along = (middle_tip - human.head_of("wrist" + side)).normalized()
        palm = across.cross(along).normalized()
        # The palm faces down in MakeHuman's rest pose; make sure it points that way.
        if palm.y > 0:
            palm = -palm
        curl_axis = along.cross(palm).normalized()
        # A relaxed hand: each finger a little more curled than the one before, the thumb loose.
        for finger, angles in (("2", (14, 22, 14)), ("3", (17, 25, 15)), ("4", (20, 27, 16)), ("5", (23, 29, 16))):
            for joint, a in zip(("1", "2", "3"), angles):
                rot["finger%s-%s%s" % (finger, joint, side)] = Matrix.Rotation(math.radians(a * curl), 3, curl_axis)
        for joint, a in (("2", 6), ("3", 8)):
            rot["finger1-%s%s" % (joint, side)] = Matrix.Rotation(math.radians(a * curl), 3, curl_axis)
    return rot


# ---------------------------------------------------------------------------- the game's skeleton

def game_bone(mh_bone):
    """Which of the game's fifteen bones a MakeHuman bone belongs to."""
    side = "L" if mh_bone.endswith(".L") else "R" if mh_bone.endswith(".R") else ""
    name = mh_bone[:-2] if side else mh_bone
    if name in ("root", "spine05", "pelvis"):
        return "Pelvis"
    if name in ("spine04", "spine03", "spine02", "spine01", "breast", "clavicle"):
        return "Torso"
    if name.startswith("shoulder") or name.startswith("upperarm"):
        return "UpperArm" + side
    if name.startswith("lowerarm"):
        return "Forearm" + side
    if name in ("wrist",) or name.startswith("metacarpal") or name.startswith("finger"):
        return "Hand" + side
    if name.startswith("upperleg"):
        return "Thigh" + side
    if name.startswith("lowerleg"):
        return "Shin" + side
    if name == "foot" or name.startswith("toe"):
        return "Foot" + side
    # Neck, head, jaw, eyes, tongue and the face's muscles.
    return "Head"


def game_weights(human, bone_index):
    """Per vertex: (bone, second bone, the second's weight), folded from MakeHuman's weights onto the game's bones."""
    out = []
    for w in human.vertex_weights():
        mass = {}
        for mh_bone, wb in w.items():
            g = game_bone(mh_bone)
            mass[g] = mass.get(g, 0.0) + wb
        ranked = sorted(mass.items(), key=lambda kv: -kv[1])
        if not ranked:
            out.append((bone_index["Pelvis"], bone_index["Pelvis"], 0.0))
            continue
        first = ranked[0]
        second = ranked[1] if len(ranked) > 1 else first
        total = first[1] + (second[1] if second is not first else 0.0)
        w1 = second[1] / total if second is not first and total > 0 else 0.0
        out.append((bone_index[first[0]], bone_index[second[0]], w1))
    return out


# ---------------------------------------------------------------------------- building meshes

import bmesh, bpy
from mathutils.kdtree import KDTree
from mathutils.bvhtree import BVHTree


def smoothstep(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0))) if e1 != e0 else (1.0 if x >= e1 else 0.0)
    return t * t * (3 - 2 * t)


class Built:
    """The posed body and everything worked out from it, shared by the pieces built on it."""

    def __init__(self, bone_index):
        self.h = Human(gender=1.0, age=0.5, muscle=0.75, weight=0.58, height=0.6, proportions=0.8)
        self.posed, self.transforms = self.h.pose(soldier_pose(self.h))
        self.bone_index = bone_index
        self.bone_names = sorted(bone_index, key=lambda n: bone_index[n])
        self.weights = game_weights(self.h, bone_index)
        self.faces = self.h.body_faces()
        # A vertex normal for every body vertex, from the posed surface.
        n = [Vector() for _ in self.posed]
        for vi, _ in self.faces:
            a, b, c = self.posed[vi[0]], self.posed[vi[1]], self.posed[vi[2]]
            fn = (c - a).cross(b - a)            # x was mirrored, so the winding is reversed
            for i in vi:
                n[i] += fn
        self.normals = [v.normalized() if v.length > 0 else Vector((0, 1, 0)) for v in n]
        used = sorted({i for vi, _ in self.faces for i in vi})
        self.kd = KDTree(len(used))
        for i in used:
            self.kd.insert(self.posed[i], i)
        self.kd.balance()
        self.bvh = BVHTree.FromPolygons([tuple(p) for p in self.posed], [list(reversed(vi)) for vi, _ in self.faces])

    def joint(self, mh_bone, tail=False):
        p = self.h.tail_of(mh_bone) if tail else self.h.head_of(mh_bone)
        return self.transforms[mh_bone] @ p

    def mass(self, i):
        """{game bone: share} for a body vertex."""
        b0, b1, w1 = self.weights[i]
        out = {self.bone_names[b0]: 1 - w1}
        if w1 > 0:
            out[self.bone_names[b1]] = out.get(self.bone_names[b1], 0) + w1
        return out

    def weights_near(self, p, k=4):
        """Skin weights for any point, blended from the nearest body vertices."""
        found = self.kd.find_n(p, k)
        acc = {}
        total = 0.0
        for co, i, d in found:
            w = 1.0 / (d + 1e-4) ** 2
            total += w
            b0, b1, w1 = self.weights[i]
            acc[b0] = acc.get(b0, 0) + w * (1 - w1)
            if w1 > 0:
                acc[b1] = acc.get(b1, 0) + w * w1
        ranked = sorted(acc.items(), key=lambda kv: -kv[1])
        first = ranked[0]
        if len(ranked) == 1:
            return (first[0], first[0], 0.0)
        second = ranked[1]
        return (first[0], second[0], second[1] / (first[1] + second[1]))


def mesh_object(name, verts, faces, zone_index, uvs=None, pivot=(0, 0, 0), smooth=True):
    """A Blender object from vertices and faces (indices into verts), every face in one zone, with optional per-corner UVs."""
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in verts], [], [list(f) for f in faces])
    mesh.update()
    if uvs is not None:
        layer = mesh.uv_layers.new(name="UVMap")
        for poly, corner_uvs in zip(mesh.polygons, uvs):
            for li, uv in zip(poly.loop_indices, corner_uvs):
                layer.data[li].uv = uv
    for poly in mesh.polygons:
        poly.material_index = zone_index
        poly.use_smooth = smooth
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj["pivot"] = list(pivot)
    return obj


def apply_subsurf(obj, levels=1):
    """Smooths an object with Catmull-Clark subdivision, keeping its UVs, zones and colour attributes."""
    mod = obj.modifiers.new("smooth", 'SUBSURF')
    mod.levels = levels
    mod.render_levels = levels
    deps = bpy.context.evaluated_depsgraph_get()
    smoothed = bpy.data.meshes.new_from_object(obj.evaluated_get(deps))
    old = obj.data
    obj.modifiers.clear()
    obj.data = smoothed
    bpy.data.meshes.remove(old)
    for poly in smoothed.polygons:
        poly.use_smooth = True
    smoothed.use_auto_smooth = True
    smoothed.auto_smooth_angle = math.radians(60)
    return obj


def unwrap(obj, margin=0.004):
    """A fresh UV layout for the object: islands cut where the surface turns sharply, packed to fill the square."""
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(70), island_margin=margin, area_weight=1.0, correct_aspect=True, scale_to_bounds=True)
    bpy.ops.object.mode_set(mode='OBJECT')


def fit_proxy(human, obj_path, mhclo_path):
    """A MakeHuman proxy (eyes, clothes) fitted to the shaped body: its vertices, UVs and faces in the game's frame."""
    verts, uvs, faces = read_obj(obj_path)
    refs, scale = [], {}
    with open(mhclo_path) as f:
        mode = None
        for line in f:
            words = line.split()
            if not words or words[0].startswith("#"):
                continue
            if words[0] in ("x_scale", "y_scale", "z_scale"):
                a, b, d = int(words[1]), int(words[2]), float(words[3])
                axis = "xyz".index(words[0][0])
                scale[axis] = abs(human.mh[a][axis] - human.mh[b][axis]) / d
                continue
            if words[0] == "verts":
                mode = "verts"
                continue
            if mode == "verts":
                if len(words) == 9:
                    refs.append(([int(w) for w in words[:3]], [float(w) for w in words[3:6]], [float(w) for w in words[6:9]]))
                elif len(words) == 1:
                    refs.append(([int(words[0])], [1.0], [0.0, 0.0, 0.0]))
                else:
                    mode = None
    fitted = []
    for ids, ws, off in refs:
        p = [0.0, 0.0, 0.0]
        for i, w in zip(ids, ws):
            for k in range(3):
                p[k] += human.mh[i][k] * w
        for k in range(3):
            p[k] += off[k] * scale.get(k, 1.0)
        fitted.append(human.to_game(p))
    return fitted, uvs, faces


# ---------------------------------------------------------------------------- the head

# Where things are on this face (game frame, metres), read off the shaped MakeHuman head.
EYE_L, EYE_R = Vector((-0.0288, 1.635, 0.1242)), Vector((0.0288, 1.635, 0.1242))
MOUTH = Vector((0.0, 1.566, 0.152))


def collar_height(p):
    """Where the collar sits on the neck: low at the front, high at the back."""
    return 1.452 + 0.07 * smoothstep(0.04, -0.07, p.z)


def _interp(points, x):
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 >= x >= x1:
            t = (x - x0) / (x1 - x0) if x1 != x0 else 0.0
            return y0 + (y1 - y0) * t
    return points[0][1] if x > points[0][0] else points[-1][1]


def hairline(p):
    """The height the hair starts at, by how far forward on the head a point is."""
    return _interp([(0.2, 1.698), (0.07, 1.69), (0.045, 1.658), (0.02, 1.638), (0.0, 1.63), (-0.03, 1.612), (-0.065, 1.582), (-0.2, 1.565)], p.z) \
        + 0.006 * smoothstep(0.02, 0.055, abs(p.x)) * smoothstep(0.05, 0.1, p.z)


def face_masks(p):
    """
    Two sets of masks for the skin texture at a point on the head, each 0..1:
    (lips, eyebrows, stubble) and (eye sockets, redness, scalp hair).
    """
    ax = abs(p.x)
    eye = EYE_L if p.x < 0 else EYE_R
    front = smoothstep(0.02, 0.07, p.z)

    # Lips: an ellipse round the mouth, fuller below the line than above.
    dy = p.y - MOUTH.y
    ry = 0.0105 if dy < 0 else 0.0085
    lip = (p.x / 0.0245) ** 2 + (dy / ry) ** 2
    lips = (1 - smoothstep(0.55, 1.0, lip)) * smoothstep(0.125, 0.145, p.z)

    # Eyebrows: an arc over each eye, thick at the inner end, thinning out to the temple.
    u = (ax - 0.009) / 0.052
    if 0 <= u <= 1 and p.z > eye.z - 0.03:
        centre = 1.6545 + 0.0055 * math.sin(math.pi * min(1.0, u * 1.25)) - 0.004 * u
        half = 0.0052 * (1 - u) + 0.0026 * u
        brows = (1 - smoothstep(half * 0.6, half, abs(p.y - centre))) * smoothstep(0.0, 0.08, u) * (1 - smoothstep(0.88, 1.0, u))
    else:
        brows = 0.0

    # Stubble: a day's growth on the jaw, chin, upper lip and the front of the neck.
    upper = 1.592 - 0.35 * max(0.0, ax - 0.022)
    upper = max(upper, 1.556) if ax < 0.058 else 1.6 + 0.06 * smoothstep(0.058, 0.07, ax)
    stubble = smoothstep(upper + 0.004, upper - 0.006, p.y) * smoothstep(1.465, 1.5, p.y) * smoothstep(-0.03, 0.0, p.z)
    stubble *= 1 - lips
    # Sideburns, in front of the ears.
    if 0.058 < ax < 0.08 and -0.01 < p.z < 0.035:
        stubble = max(stubble, smoothstep(1.665, 1.655, p.y) * smoothstep(1.6, 1.61, p.y))

    # Eye sockets: a little shadow round each eye, deepest at the inner corner.
    d = math.hypot((p.x - eye.x) / 1.15, p.y - eye.y + 0.002)
    socket = (1 - smoothstep(0.012, 0.026, d)) * smoothstep(eye.z - 0.03, eye.z - 0.012, p.z)

    # Warmth: cheeks, the nose tip, the ears.
    red = 0.0
    for cx in (-0.047, 0.047):
        red = max(red, 1 - smoothstep(0.008, 0.026, (p - Vector((cx, 1.598, 0.112))).length))
    red = max(red, 0.8 * (1 - smoothstep(0.004, 0.018, (p - Vector((0.0, 1.598, 0.163))).length)))
    red = max(red, 0.6 * smoothstep(0.066, 0.076, ax) * smoothstep(1.56, 1.58, p.y) * (1 - smoothstep(1.66, 1.68, p.y)))

    # Hair: above the hairline, not on the ears.
    scalp = smoothstep(hairline(p) - 0.012, hairline(p) + 0.014, p.y)
    ear = smoothstep(0.064, 0.07, ax) * smoothstep(1.672, 1.662, p.y) * smoothstep(-0.045, -0.03, p.z) * smoothstep(0.04, 0.025, p.z)
    scalp *= 1 - ear
    return (lips, brows, stubble), (socket, red, scalp)


def build_head(B, zones, out_dir):
    """
    The head and neck in skin, with the eyes in, eyelashes and the hair: the face as
    MakeHuman made it, smoothed once, with a skin texture baked for it. Returns
    (head, eyes, lashes, hair) objects; hair is rigid (a Gear model) and the rest skinned.
    """
    P = B.posed
    keep = []
    for vi, ti in B.faces:
        if all(P[i].y > collar_height(P[i]) - 0.035 and (P[i].y > 1.55 or abs(P[i].x) < 0.09) for i in vi):
            keep.append((vi, ti))
    index = {}
    verts = []
    faces, corner_uvs = [], []
    for vi, ti in keep:
        f = []
        for i in vi:
            if i not in index:
                index[i] = len(verts)
                verts.append(P[i])
            f.append(index[i])
        faces.append(list(reversed(f)))
        corner_uvs.append([B.h.uvs[t] for t in reversed(ti)])
    head = mesh_object("Head", verts, faces, zones["skin"], uvs=corner_uvs)
    apply_subsurf(head, 1)
    unwrap(head)

    # The masks the skin texture is painted from, as colour attributes, worked out on the
    # smoothed head so their edges are as fine as it is.
    a = head.data.color_attributes.new("maskA", 'FLOAT_COLOR', 'POINT')
    b = head.data.color_attributes.new("maskB", 'FLOAT_COLOR', 'POINT')
    for v in head.data.vertices:
        (m1, m2, m3), (n1, n2, n3) = face_masks(v.co)
        a.data[v.index].color = (m1, m2, m3, 1.0)
        b.data[v.index].color = (n1, n2, n3, 1.0)

    # The eyes: MakeHuman's eye model, fitted to this face, with its own texture.
    fitted, eye_uvs, eye_faces = fit_proxy(B.h, os.path.join(DATA, "eyes", "high-poly.obj"), os.path.join(DATA, "eyes", "high-poly.mhclo"))
    # The clear cornea over each eye is drawn from the corner of the texture where it is
    # see-through; without transparency it would cover the iris, so it is left out.
    eye_faces = [(vi, ti, g) for vi, ti, g in eye_faces
                 if not all(eye_uvs[t][0] > 0.78 and eye_uvs[t][1] < 0.22 for t in ti)]
    eyes = mesh_object("Eyes", fitted, [list(reversed(vi)) for vi, ti, g in eye_faces], zones["eye"],
                       uvs=[[eye_uvs[t] for t in reversed(ti)] for vi, ti, g in eye_faces])

    lashes = build_lashes(B, zones)
    hair = build_hair(head, zones)
    return head, eyes, lashes, hair


def build_lashes(B, zones):
    """
    Lashes along each eyelid, from MakeHuman's eyelash strips (helper geometry that fans
    out from the lid margins of this face). Each strip is cut down to a short fringe,
    longest in the middle of the lid and tapering to nothing at the corners, and drawn
    from both sides in the hair colour.
    """
    from collections import defaultdict
    P = B.posed
    strips = defaultdict(list)
    for vi, ti, g in B.h.faces:
        if "eyelashes" in g:
            strips[g].append(vi)
    verts, faces = [], []
    for g, fs in sorted(strips.items()):
        upper = g.endswith("-2")
        length = 0.5 if upper else 0.32
        # The strip is a band of quads: its outline has four corners, two long sides (the
        # lid margin and the tips of the lashes) and two short ends.
        edges = defaultdict(int)
        for f in fs:
            for a, b in zip(f, f[1:] + f[:1]):
                edges[(min(a, b), max(a, b))] += 1
        nbr, valence = defaultdict(set), defaultdict(int)
        for (a, b), n in edges.items():
            valence[a] += 1
            valence[b] += 1
            if n == 1:
                nbr[a].add(b)
                nbr[b].add(a)
        start = next(k for k in nbr if valence[k] == 2)
        ring = [start]
        while True:
            nxt = [n for n in nbr[ring[-1]] if n not in ring]
            if not nxt:
                break
            ring.append(nxt[0])
        corners = [i for i, k in enumerate(ring) if valence[k] == 2] + [len(ring)]
        sides = [ring[corners[i]:corners[i + 1] + 1] if corners[i + 1] < len(ring) else ring[corners[i]:] + ring[:1]
                 for i in range(len(corners) - 1)]
        long_sides = sorted(sides, key=len)[-2:]
        # Lashes grow forward from the lid: the margin is the long side further back.
        root = min(long_sides, key=lambda chain: sum(P[k].z for k in chain) / len(chain))
        xs = [P[k].x for k in root]
        x0, x1 = min(xs), max(xs)
        base = len(verts)
        index = {}
        for k in sorted({k for f in fs for k in f}):
            r = min(root, key=lambda q: (P[q] - P[k]).length)
            u = (P[r].x - x0) / max(1e-6, x1 - x0)
            taper = math.sin(math.pi * min(1.0, max(0.0, u))) ** 0.6
            index[k] = len(verts)
            verts.append(P[r] + (P[k] - P[r]) * length * (0.25 + 0.75 * taper))
        for f in fs:
            loop = [index[k] for k in f]
            faces.append(list(reversed(loop)))
            faces.append(loop)
    return mesh_object("Lashes", verts, faces, zones["hair"])


def build_hair(head, zones):
    """
    A short, close crop: a shell over the scalp, thicker on the crown, with a little
    texture. Toward the hairline the shell sinks under the skin, so its visible edge is
    wherever the hair mask crosses one half: a smooth line, not the edges of faces.
    """
    mesh = head.data
    mask = mesh.color_attributes["maskB"].data
    scalp = [mask[v.index].color[2] for v in mesh.vertices]
    normals = [v.normal.copy() for v in mesh.vertices]
    index, verts, faces = {}, [], []
    for poly in mesh.polygons:
        if max(scalp[i] for i in poly.vertices) < 0.5:
            continue
        f = []
        for i in poly.vertices:
            if i not in index:
                index[i] = len(verts)
                co = mesh.vertices[i].co
                m = scalp[i]
                full = 0.0022 + 0.0030 * smoothstep(0.6, 1.0, m) * smoothstep(1.62, 1.71, co.y)
                full *= 0.85 + 0.3 * (0.5 + 0.5 * math.sin(co.x * 610 + math.sin(co.z * 520) * 2.1 + co.y * 230))
                depth = full * smoothstep(0.72, 0.9, m) - 0.0025 * (1 - smoothstep(0.55, 0.72, m))
                verts.append(co + normals[i] * depth)
            f.append(index[i])
        faces.append(f)
    hair = mesh_object("Hair", verts, faces, zones["hair"])
    return hair


def _multiply(nt, colour, factor):
    n = nt.nodes.new("ShaderNodeMix")
    n.data_type = 'RGBA'
    n.blend_type = 'MULTIPLY'
    n.inputs[0].default_value = 1.0
    nt.links.new(colour, n.inputs[6])
    nt.links.new(factor, n.inputs[7])
    return n.outputs[2]


def bake_skin(head, out_dir, size=1024, shade=True):
    """
    Paints the face from its masks into a texture, through the head's UVs: brows, lips,
    stubble, a little colour in the cheeks and shadow round the eyes, short hair on the
    scalp, and fine mottling everywhere. The base is a neutral 0.75 grey, so the game can
    multiply it by any skin tone. Writes SkinAlbedo.png and returns its path.
    """
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 8
    scene.cycles.use_denoising = False

    mat = bpy.data.materials.new("SkinBake")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    links.new(bsdf.outputs[0], out.inputs[0])

    def attr(name):
        n = nodes.new("ShaderNodeAttribute")
        n.attribute_name = name
        s = nodes.new("ShaderNodeSeparateColor")
        links.new(n.outputs["Color"], s.inputs[0])
        return s

    ma, mb = attr("maskA"), attr("maskB")
    coords = nodes.new("ShaderNodeTexCoord")

    def noise(scale, detail=2.0, stretch=(1, 1, 1), kind="noise", low=0.4, high=0.6):
        mapping = nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (stretch[0] * scale, stretch[1] * scale, stretch[2] * scale)
        links.new(coords.outputs["Object"], mapping.inputs["Vector"])
        if kind == "noise":
            tex = nodes.new("ShaderNodeTexNoise")
            tex.inputs["Detail"].default_value = detail
            links.new(mapping.outputs[0], tex.inputs["Vector"])
            src = tex.outputs["Fac"]
        else:
            tex = nodes.new("ShaderNodeTexVoronoi")
            links.new(mapping.outputs[0], tex.inputs["Vector"])
            src = tex.outputs["Distance"]
        ramp = nodes.new("ShaderNodeMapRange")
        ramp.inputs["From Min"].default_value = low
        ramp.inputs["From Max"].default_value = high
        links.new(src, ramp.inputs["Value"])
        return ramp.outputs["Result"]

    def mul(a, b):
        n = nodes.new("ShaderNodeMath")
        n.operation = 'MULTIPLY'
        links.new(a, n.inputs[0])
        if isinstance(b, float):
            n.inputs[1].default_value = b
        else:
            links.new(b, n.inputs[1])
        return n.outputs[0]

    def mix(colour_a, colour_b, fac, blend='MIX'):
        n = nodes.new("ShaderNodeMix")
        n.data_type = 'RGBA'
        n.blend_type = blend
        links.new(fac, n.inputs[0])
        for slot, c in ((6, colour_a), (7, colour_b)):
            if isinstance(c, tuple):
                n.inputs[slot].default_value = c
            else:
                links.new(c, n.inputs[slot])
        return n.outputs[2]

    base = (0.75, 0.75, 0.75, 1.0)
    # Mottling: skin is never one flat colour.
    mottle = noise(60.0, 4.0, low=0.25, high=0.75)
    col = mix(base, (0.70, 0.71, 0.73, 1.0), mul(mottle, 0.5))
    col = mix(col, (0.80, 0.72, 0.70, 1.0), mul(noise(18.0, 3.0, low=0.4, high=0.7), 0.4))
    # Warmth and shadow.
    col = mix(col, (0.82, 0.62, 0.60, 1.0), mul(mb.outputs[1], 0.55))
    col = mix(col, (0.62, 0.56, 0.58, 1.0), mul(mb.outputs[0], 0.7))
    # Lips.
    col = mix(col, (0.62, 0.38, 0.38, 1.0), mul(ma.outputs[0], 0.85))
    # Stubble: fine dark dots.
    dots = noise(1500.0, kind="voronoi", low=0.35, high=0.12)
    col = mix(col, (0.24, 0.22, 0.22, 1.0), mul(mul(ma.outputs[2], dots), 0.7))
    col = mix(col, (0.50, 0.48, 0.48, 1.0), mul(ma.outputs[2], 0.45))
    # Scalp under a close crop.
    # Full colour well before the hair shell comes up through the skin (at about 0.72), so
    # the shell's edge is dark on dark and the hairline is this soft painted one.
    hairdots = noise(1700.0, kind="voronoi", low=0.42, high=0.1)
    scalp = nodes.new("ShaderNodeMapRange")
    scalp.interpolation_type = 'SMOOTHSTEP'
    scalp.inputs["From Min"].default_value = 0.08
    scalp.inputs["From Max"].default_value = 0.62
    links.new(mb.outputs[2], scalp.inputs["Value"])
    scalp = scalp.outputs["Result"]
    # Clipped short: stubble over the scalp, which the hairstyles cover or leave showing.
    col = mix(col, (0.2, 0.17, 0.15, 1.0), mul(scalp, 0.8))
    col = mix(col, (0.035, 0.03, 0.027, 1.0), mul(mul(scalp, hairdots), 0.92))
    # Brows: hairs lying along the brow.
    strokes = noise(1.0, 2.0, stretch=(120.0, 1200.0, 500.0), low=0.45, high=0.6)
    col = mix(col, (0.18, 0.14, 0.12, 1.0), mul(ma.outputs[1], 0.7))
    col = mix(col, (0.05, 0.04, 0.035, 1.0), mul(ma.outputs[1], mul(strokes, 0.9)))
    if shade:
        # Shaded where the face is enclosed: round the eyes and nostrils, under the jaw and
        # the collar, behind the ears.
        import textures
        col = _multiply(nt, col, textures.occlusion(nt, 0.05, 0.6))
    links.new(col, bsdf.inputs["Base Color"])

    image = bpy.data.images.new("SkinAlbedo", size, size, alpha=False)
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    nodes.active = tex
    # Clearing the slots resets every face's slot, so note them first.
    keep_index = [p.material_index for p in head.data.polygons]
    head.data.materials.clear()
    head.data.materials.append(mat)
    for p in head.data.polygons:
        p.material_index = 0

    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = head
    head.select_set(True)
    bpy.ops.object.bake(type='DIFFUSE', pass_filter={'COLOR'}, margin=12, use_clear=True)
    path = os.path.join(out_dir, "SkinAlbedo.png")
    image.filepath_raw = path
    image.file_format = 'PNG'
    image.save()

    head.data.materials.clear()
    for p, z in zip(head.data.polygons, keep_index):
        p.material_index = z
    return path
