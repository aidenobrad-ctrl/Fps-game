"""
Recoil's character and weapon models, built in Blender from code.

    blender -b --python art/blender/recoil_models.py -- --out game/Assets/_Project/Resources/Models [--preview DIR]

Everything is authored directly in the game's frame (x right, y up, z forward, metres), so
the exporter writes positions as they are and only flips the winding of each triangle for
Unity's left-handed space. Each model is split into zones (material slots) that the game
colours at run time: a player's suit, trim and visor colours, team colours on the shoulders,
and a weapon skin's colours on a gun.

Two files come out:

  Soldier.bytes   the soldier, skinned to a fifteen-bone skeleton: a realistic body and face
                  (art/blender/human.py, from the CC0 MakeHuman base mesh) in a fitted
                  uniform and plate carrier (art/blender/outfit.py), as three skinned meshes
                  (Body, Uniform, Kit), plus the first-person sleeves and gloves;
  Gear.bytes      the hair, headgear and back items, fitted to that head and carrier;
  SkinAlbedo.png, EyeAlbedo.png  the face's painted skin and the eyes' texture;
  GunParts.bytes  detailed parts for the weapon builder (receiver, handguard, barrel,
                  suppressor, stock, grip, magazines, sights, launcher and blade parts), each
                  modelled to fill a unit box so the builder can stretch it to any weapon's
                  proportions.
  Projectiles.bytes  what flies: a rocket, grenades, arrows and bolts, a throwing knife, a
                  disc, a flare, plasma, a paintball and a pellet, at the size they are drawn,
                  pointing along +z (the way they travel).

The format is described in Client/Visuals/ModelLibrary.cs, which reads it.
"""
import bpy, bmesh, math, os, struct, sys
from mathutils import Matrix, Vector

# human.py and outfit.py sit next to this file.
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
except NameError:
    pass

ZONES = {"primary": 0, "dark": 1, "metal": 2, "glow": 3, "trim": 4, "team": 5, "helmet": 6,
         "skin": 7, "hair": 8, "eye": 9, "iris": 10, "lips": 11, "boots": 12}
PREVIEW_COLOURS = {
    0: (0.2, 0.24, 0.17, 1), 1: (0.035, 0.037, 0.04, 1), 2: (0.45, 0.46, 0.48, 1), 3: (0.1, 0.9, 1.0, 1),
    4: (0.42, 0.37, 0.27, 1), 5: (0.15, 0.35, 0.8, 1), 6: (0.12, 0.2, 0.26, 1),
    7: (0.62, 0.42, 0.31, 1), 8: (0.06, 0.045, 0.035, 1), 9: (0.85, 0.84, 0.8, 1), 10: (0.12, 0.08, 0.05, 1),
    11: (0.5, 0.29, 0.24, 1), 12: (0.11, 0.08, 0.06, 1),
}


# ---------------------------------------------------------------------------- building

class Part:
    """One exported mesh, built up from primitives in a bmesh."""

    def __init__(self, name, pivot=(0, 0, 0)):
        self.name = name
        self.pivot = Vector(pivot)
        self.bm = bmesh.new()

    def _finish(self, geom_verts, zone, bevel, segments):
        verts = list(geom_verts)
        faces = {f for v in verts for f in v.link_faces}
        for f in faces:
            f.material_index = ZONES[zone]
        if bevel > 0:
            edges = list({e for f in faces for e in f.edges})
            result = bmesh.ops.bevel(self.bm, geom=edges, offset=bevel, segments=segments, profile=0.5,
                                     affect='EDGES', clamp_overlap=True, material=ZONES[zone])
            for f in result["faces"]:
                f.material_index = ZONES[zone]
        return verts

    def box(self, center, size, zone, bevel=0.0, segments=2, rot=(0, 0, 0), taper=None, taper_bottom=None):
        """A box. taper=(sx, sz) scales the top face (+y), taper_bottom the bottom one, to shape a silhouette."""
        m = Matrix.Translation(center) @ euler(rot) @ Matrix.Diagonal((size[0], size[1], size[2], 1))
        res = bmesh.ops.create_cube(self.bm, size=1.0, matrix=m)
        verts = res["verts"]
        c = Vector(center)
        for scale, pick in ((taper, max), (taper_bottom, min)):
            if not scale:
                continue
            edge = pick(v.co.y for v in verts)
            for v in verts:
                if abs(v.co.y - edge) < 1e-6:
                    v.co.x = c.x + (v.co.x - c.x) * scale[0]
                    v.co.z = c.z + (v.co.z - c.z) * scale[1]
        return self._finish(verts, zone, min(bevel, min(size) * 0.45), segments)

    def cylinder(self, a, b, r1, r2, zone, segments=16, bevel=0.0, bevel_segments=2):
        """A cylinder (or cone) from point a to point b, radius r1 at a and r2 at b."""
        a, b = Vector(a), Vector(b)
        axis = b - a
        length = axis.length
        rot = axis.to_track_quat('Z', 'Y').to_matrix().to_4x4()
        m = Matrix.Translation((a + b) / 2) @ rot
        res = bmesh.ops.create_cone(self.bm, cap_ends=True, cap_tris=False, segments=segments,
                                    radius1=r1, radius2=r2, depth=length, matrix=m)
        return self._finish(res["verts"], zone, min(bevel, min(r1, r2) * 0.6, length * 0.3), bevel_segments)

    def sphere(self, center, radius, zone, scale=(1, 1, 1), u=24, v=14):
        m = Matrix.Translation(center) @ Matrix.Diagonal((scale[0], scale[1], scale[2], 1))
        res = bmesh.ops.create_uvsphere(self.bm, u_segments=u, v_segments=v, radius=radius, matrix=m)
        return self._finish(res["verts"], zone, 0, 0)

    def ring(self, center, axis, r_outer, r_inner, length, zone, segments=20):
        """A hollow tube: an outer cylinder, an inner one facing in, and the rims between."""
        c, ax = Vector(center), Vector(axis).normalized()
        rot = ax.to_track_quat('Z', 'Y').to_matrix()
        outer_front, outer_back, inner_front, inner_back = [], [], [], []
        for i in range(segments):
            t = 2 * math.pi * i / segments
            d = rot @ Vector((math.cos(t), math.sin(t), 0))
            front, back = c + ax * (length / 2), c - ax * (length / 2)
            outer_front.append(self.bm.verts.new(front + d * r_outer))
            outer_back.append(self.bm.verts.new(back + d * r_outer))
            inner_front.append(self.bm.verts.new(front + d * r_inner))
            inner_back.append(self.bm.verts.new(back + d * r_inner))
        faces = []
        for i in range(segments):
            j = (i + 1) % segments
            faces.append(self.bm.faces.new((outer_back[i], outer_back[j], outer_front[j], outer_front[i])))
            faces.append(self.bm.faces.new((inner_back[j], inner_back[i], inner_front[i], inner_front[j])))
            faces.append(self.bm.faces.new((outer_front[i], outer_front[j], inner_front[j], inner_front[i])))
            faces.append(self.bm.faces.new((outer_back[j], outer_back[i], inner_back[i], inner_back[j])))
        for f in faces:
            f.material_index = ZONES[zone]
        return faces

    def lathe(self, profile, zone, segments=32, axis_offset=(0, 0, 0)):
        """
        A surface of revolution about the z axis: profile is a list of (z, radius) from the
        back to the front. Ends with a radius above zero are closed with a flat cap.
        """
        o = Vector(axis_offset)
        rings = []
        for z, r in profile:
            if r <= 1e-5:
                rings.append([self.bm.verts.new(o + Vector((0, 0, z)))])
                continue
            rings.append([self.bm.verts.new(o + Vector((math.cos(2 * math.pi * i / segments) * r,
                                                         math.sin(2 * math.pi * i / segments) * r, z)))
                          for i in range(segments)])
        faces = []
        for a, b in zip(rings, rings[1:]):
            if len(a) == 1 and len(b) == 1:
                continue
            for i in range(segments):
                j = (i + 1) % segments
                if len(a) == 1:
                    faces.append(self.bm.faces.new((a[0], b[j], b[i])))
                elif len(b) == 1:
                    faces.append(self.bm.faces.new((a[i], a[j], b[0])))
                else:
                    faces.append(self.bm.faces.new((a[i], a[j], b[j], b[i])))
        if len(rings[0]) > 1:
            faces.append(self.bm.faces.new(list(reversed(rings[0]))))
        if len(rings[-1]) > 1:
            faces.append(self.bm.faces.new(rings[-1]))
        for f in faces:
            f.material_index = ZONES[zone]
        return faces

    def to_object(self, subsurf=0):
        mesh = bpy.data.meshes.new(self.name)
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        self.bm.to_mesh(mesh)
        self.bm.free()
        if subsurf > 0:
            # Smoothed with Catmull-Clark subdivision, keeping each face's zone.
            temp = bpy.data.objects.new("temp", mesh)
            bpy.context.scene.collection.objects.link(temp)
            temp.modifiers.new("smooth", 'SUBSURF').levels = subsurf
            smoothed = bpy.data.meshes.new_from_object(temp.evaluated_get(bpy.context.evaluated_depsgraph_get()))
            bpy.data.objects.remove(temp)
            bpy.data.meshes.remove(mesh)
            mesh = smoothed
            mesh.name = self.name
        for poly in mesh.polygons:
            poly.use_smooth = True
        mesh.use_auto_smooth = True
        mesh.auto_smooth_angle = math.radians(38)
        obj = bpy.data.objects.new(self.name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj["pivot"] = list(self.pivot)
        return obj


def cut_sphere(part, centre, radius, scale, zone, plane_co, plane_no, thickness=0.0, u=36, v=22):
    """A sphere cut cleanly by a plane, keeping the side the normal points to, thickened if asked."""
    before = set(part.bm.faces)
    res = bmesh.ops.create_uvsphere(part.bm, u_segments=u, v_segments=v, radius=radius)
    verts = res["verts"]
    for vert in verts:
        vert.co = Vector(centre) + Vector((vert.co.x * scale[0], vert.co.y * scale[1], vert.co.z * scale[2]))
    faces = list({f for vert in verts for f in vert.link_faces})
    edges = list({e for vert in verts for e in vert.link_edges})
    bmesh.ops.bisect_plane(part.bm, geom=faces + edges + verts, plane_co=Vector(plane_co),
                           plane_no=Vector(plane_no).normalized(), clear_inner=True)
    faces = [f for f in part.bm.faces if f not in before]
    for f in faces:
        f.material_index = ZONES[zone]
    if thickness > 0:
        res = bmesh.ops.solidify(part.bm, geom=faces, thickness=thickness)
        for elem in res["geom"]:
            if isinstance(elem, bmesh.types.BMFace):
                elem.material_index = ZONES[zone]
    return part


def euler(rot):
    rx, ry, rz = (math.radians(a) for a in rot)
    return (Matrix.Rotation(ry, 4, 'Y') @ Matrix.Rotation(rx, 4, 'X') @ Matrix.Rotation(rz, 4, 'Z'))


def mirror_x(p):
    return (-p[0], p[1], p[2])


# ---------------------------------------------------------------------------- the soldier

# The skeleton: each bone's name, the bone it hangs from, and its joint, in the game's frame.
# Client/Visuals/SoldierView.cs reads these from the file and animates them.
# The joints are the realistic body's (human.py): hips, knees, ankles, shoulders, elbows and
# wrists where MakeHuman's skeleton has them in the soldier's rest pose. The torso bends at
# 1.02 m, where Shared/Match/BodyShapes.cs puts the joint the gun is held from.
BONES = [("Pelvis", None, (0, 0.96, 0)), ("Torso", "Pelvis", (0, 1.02, 0)), ("Head", "Torso", (0, 1.5, 0.011))]
for _side, _s in (("L", -1), ("R", 1)):
    BONES += [
        ("Thigh" + _side, "Pelvis", (_s * 0.107, 0.945, -0.007)),
        ("Shin" + _side, "Thigh" + _side, (_s * 0.107, 0.515, 0.027)),
        ("Foot" + _side, "Shin" + _side, (_s * 0.115, 0.068, 0.011)),
        ("UpperArm" + _side, "Torso", (_s * 0.192, 1.382, 0.011)),
        ("Forearm" + _side, "UpperArm" + _side, (_s * 0.233, 1.148, -0.092)),
        ("Hand" + _side, "Forearm" + _side, (_s * 0.268, 0.904, 0.011)),
    ]
BONE_INDEX = {name: i for i, (name, _, _) in enumerate(BONES)}
PIVOT = {name: Vector(p) for name, _, p in BONES}
PARENT = {name: parent for name, parent, _ in BONES}
# Where the headgear and back items are modelled around; refit_gear() moves them onto the
# realistic head and plate carrier.
HEAD_CENTRE = Vector((0, 1.645, 0.0))
BACK_CENTRE = Vector((0, 1.17, 0.0))


def gear_models():
    """Headgear (centred on the head) and back items (centred on the torso), worn on top of the body."""
    parts = []
    C = HEAD_CENTRE

    def shell(part, centre, radius, scale, zone, keep, thickness=0.006, u=36, v=20):
        """Part of a sphere: the vertices where keep(relative position) is true, thickened inwards."""
        res = bmesh.ops.create_uvsphere(part.bm, u_segments=u, v_segments=v, radius=radius)
        verts = res["verts"]
        for vert in verts:
            vert.co = Vector((vert.co.x * scale[0], vert.co.y * scale[1], vert.co.z * scale[2]))
        doomed = [vert for vert in verts if not keep(vert.co)]
        kept = [vert for vert in verts if keep(vert.co)]
        bmesh.ops.delete(part.bm, geom=doomed, context='VERTS')
        faces = list({f for vert in kept if vert.is_valid for f in vert.link_faces})
        for f in faces:
            f.material_index = ZONES[zone]
        if thickness > 0:
            res = bmesh.ops.solidify(part.bm, geom=faces, thickness=thickness)
            for elem in res["geom"]:
                if isinstance(elem, bmesh.types.BMFace):
                    elem.material_index = ZONES[zone]
        return centre

    def place(part, offset):
        bmesh.ops.translate(part.bm, verts=list(part.bm.verts), vec=offset)

    hair = Part("Hair", C)
    cut_sphere(hair, C + Vector((0, 0.004, -0.004)), 0.1, (0.84, 1.13, 1.04), "hair", C + Vector((0, 0.022, 0)), (0, 1, -0.6), thickness=0.004)
    parts.append(hair)

    helmet = Part("Helmet", C)
    cut_sphere(helmet, C + Vector((0, 0.028, -0.008)), 0.122, (0.94, 0.96, 1.06), "trim", C + Vector((0, 0.0, 0)), (0, 1, -0.45), thickness=0.012)
    for side in (-1, 1):
        helmet.box(C + Vector((side * 0.112, 0.045, -0.01)), (0.012, 0.022, 0.1), "dark", bevel=0.004)
        helmet.box(C + Vector((side * 0.08, -0.045, 0.035)), (0.008, 0.07, 0.012), "dark", rot=(20, 0, side * -10))
    helmet.box(C + Vector((0, 0.1, 0.11)), (0.04, 0.03, 0.015), "metal", bevel=0.005, rot=(-50, 0, 0))
    helmet.box(C + Vector((0, 0.11, -0.1)), (0.07, 0.04, 0.012), "dark", bevel=0.004, rot=(35, 0, 0))
    parts.append(helmet)

    cap = Part("Cap", C)
    cut_sphere(cap, C + Vector((0, 0.014, -0.002)), 0.106, (0.84, 1.0, 1.0), "trim", C + Vector((0, 0.03, 0)), (0, 1, -0.15), thickness=0.005)
    cap.box(C + Vector((0, 0.04, 0.125)), (0.15, 0.008, 0.08), "trim", bevel=0.004, rot=(-12, 0, 0), taper=(0.85, 0.7))
    cap.sphere(C + Vector((0, 0.12, -0.002)), 0.008, "trim")
    parts.append(cap)

    beanie = Part("Beanie", C)
    cut_sphere(beanie, C + Vector((0, 0.012, -0.002)), 0.108, (0.84, 1.14, 1.0), "trim", C + Vector((0, 0.02, 0)), (0, 1, -0.2), thickness=0.006)
    beanie.ring(C + Vector((0, 0.03, -0.002)), (0, 1, 0), 0.094, 0.082, 0.04, "trim", segments=32)
    for vert in beanie.bm.verts:
        rel = vert.co - C
        if 0.005 < rel.y < 0.055 and abs(rel.z) > 0.0:
            pass
    parts.append(beanie)

    boonie = Part("Boonie", C)
    cut_sphere(boonie, C + Vector((0, 0.03, -0.002)), 0.11, (0.84, 0.95, 1.0), "primary", C + Vector((0, 0.04, 0)), (0, 1, 0), thickness=0.005)
    boonie.ring(C + Vector((0, 0.044, -0.002)), (0, 1, 0), 0.165, 0.088, 0.008, "primary", segments=32)
    boonie.ring(C + Vector((0, 0.055, -0.002)), (0, 1, 0), 0.094, 0.086, 0.02, "dark", segments=32)
    parts.append(boonie)

    def headset(part):
        for side in (-1, 1):
            part.cylinder(C + Vector((side * 0.074, 0.0, -0.005)), C + Vector((side * 0.102, 0.0, -0.005)), 0.042, 0.04, "dark", segments=18, bevel=0.008)
        # The band over the top: half a ring.
        before = set(part.bm.faces)
        part.ring(C + Vector((0, 0.0, -0.008)), (0, 0, 1), 0.11, 0.1, 0.02, "dark", segments=40)
        band = [f for f in part.bm.faces if f not in before]
        verts = list({v for f in band for v in f.verts})
        edges = list({e for f in band for e in f.edges})
        bmesh.ops.bisect_plane(part.bm, geom=band + edges + verts, plane_co=C + Vector((0, 0.02, 0)), plane_no=Vector((0, 1, 0)), clear_inner=True)
        for vert in verts:
            if vert.is_valid:
                rel = vert.co - C
                vert.co.x = C.x + rel.x * 0.95
        part.cylinder(C + Vector((-0.098, -0.02, 0.01)), C + Vector((-0.04, -0.062, 0.088)), 0.005, 0.004, "dark", segments=8)
        part.sphere(C + Vector((-0.038, -0.063, 0.09)), 0.011, "dark")

    phones = Part("Headset", C)
    headset(phones)
    parts.append(phones)

    helmet_phones = Part("HelmetHeadset", C)
    for s in (-1, 1):
        helmet_phones.cylinder(C + Vector((s * 0.075, -0.005, -0.005)), C + Vector((s * 0.105, -0.005, -0.005)), 0.044, 0.042, "dark", segments=18, bevel=0.008)
    helmet_phones.cylinder(C + Vector((-0.1, -0.025, 0.01)), C + Vector((-0.04, -0.06, 0.1)), 0.005, 0.004, "dark", segments=8)
    parts.append(helmet_phones)

    bandana = Part("Bandana", C)
    bandana.cylinder(C + Vector((0, 0.03, -0.004)), C + Vector((0, 0.06, -0.004)), 1.0, 1.0, "trim", segments=32)
    for vert in bandana.bm.verts:
        rel = vert.co - C
        vert.co.x = C.x + rel.x * 0.081
        vert.co.z = C.z - 0.004 + (rel.z + 0.004) * 0.1
    bandana.box(C + Vector((0, 0.04, -0.105)), (0.03, 0.03, 0.02), "trim", bevel=0.008)
    bandana.box(C + Vector((0.01, 0.01, -0.11)), (0.02, 0.05, 0.006), "trim", bevel=0.003, rot=(10, 0, 15))
    parts.append(bandana)

    B = BACK_CENTRE
    pack = Part("AssaultPack", B)
    pack.box(B + Vector((0, 0.06, -0.235)), (0.27, 0.36, 0.13), "trim", bevel=0.04, segments=3, taper=(0.9, 0.85))
    pack.box(B + Vector((0, 0.2, -0.24)), (0.25, 0.06, 0.14), "trim", bevel=0.02, segments=2)
    for s in (-1, 1):
        pack.box(B + Vector((s * 0.15, 0.0, -0.23)), (0.04, 0.16, 0.09), "trim", bevel=0.015)
    pack.box(B + Vector((0, 0.02, -0.305)), (0.16, 0.18, 0.02), "dark", bevel=0.006)
    parts.append(pack)

    hydration = Part("HydrationPack", B)
    hydration.box(B + Vector((0, 0.08, -0.2)), (0.2, 0.32, 0.06), "trim", bevel=0.025, segments=3)
    hydration.cylinder(B + Vector((0.07, 0.24, -0.19)), B + Vector((0.12, 0.31, 0.02)), 0.008, 0.008, "dark", segments=8)
    hydration.cylinder(B + Vector((0.12, 0.31, 0.02)), B + Vector((0.11, 0.18, 0.17)), 0.008, 0.008, "dark", segments=8)
    parts.append(hydration)

    radio = Part("RadioPack", B)
    radio.box(B + Vector((0, 0.07, -0.2)), (0.22, 0.3, 0.07), "trim", bevel=0.02, segments=2)
    radio.box(B + Vector((0.05, 0.1, -0.245)), (0.1, 0.19, 0.06), "dark", bevel=0.01)
    radio.cylinder(B + Vector((0.08, 0.2, -0.25)), B + Vector((0.1, 0.62, -0.27)), 0.005, 0.003, "dark", segments=8)
    radio.cylinder(B + Vector((0.03, 0.2, -0.25)), B + Vector((0.03, 0.23, -0.25)), 0.012, 0.01, "metal", segments=10)
    parts.append(radio)

    ruck = Part("Rucksack", B)
    ruck.box(B + Vector((0, 0.03, -0.26)), (0.32, 0.5, 0.18), "trim", bevel=0.05, segments=3, taper=(0.92, 0.85))
    ruck.box(B + Vector((0, 0.27, -0.26)), (0.3, 0.07, 0.19), "trim", bevel=0.025, segments=2)
    for s in (-1, 1):
        ruck.box(B + Vector((s * 0.18, -0.05, -0.25)), (0.05, 0.2, 0.12), "trim", bevel=0.02)
    ruck.box(B + Vector((0, -0.2, -0.27)), (0.3, 0.012, 0.19), "dark")
    parts.append(ruck)

    bedroll = Part("BedrollPack", B)
    bedroll.box(B + Vector((0, 0.02, -0.235)), (0.26, 0.32, 0.13), "trim", bevel=0.04, segments=3)
    bedroll.cylinder(B + Vector((-0.17, 0.24, -0.23)), B + Vector((0.17, 0.24, -0.23)), 0.06, 0.06, "primary", segments=20, bevel=0.02)
    for x in (-0.09, 0.09):
        bedroll.cylinder(B + Vector((x - 0.008, 0.24, -0.23)), B + Vector((x + 0.008, 0.24, -0.23)), 0.064, 0.064, "dark", segments=20)
    parts.append(bedroll)

    scarf = Part("Scarf", B)
    scarf.cylinder(B + Vector((0, 0.28, -0.01)), B + Vector((0, 0.36, -0.005)), 0.1, 0.085, "primary", segments=28, bevel=0.02)
    scarf.box(B + Vector((0.03, 0.15, 0.13)), (0.1, 0.2, 0.02), "primary", bevel=0.008, rot=(8, 0, 6), taper_bottom=(0.6, 1.0))
    parts.append(scarf)
    return parts


# ---------------------------------------------------------------------------- skinned export

def export_skinned(path, skinned, rigid):
    """
    RCM2: magic; uint8 bone count; per bone: name, int8 parent (-1 for none), pivot (3 floats);
    uint16 mesh count; per mesh: name, pivot, uint8 flags (1: skinned), uint16 vertex count,
    vertices (position, normal, uv, and when skinned: uint8 bone, uint8 bone, float weight of
    the second), uint8 submesh count, then per submesh: uint8 zone, uint32 index count, uint16
    indices. A skinned mesh is in the body's rest pose, in model space.

    skinned: [(mesh name, [objects with weight attributes])]; rigid: objects, each its own mesh.
    An object marked own_uv keeps its UV map (the face and eyes are textured); the rest get
    box-projected coordinates for the uniform's patterns.
    """
    import outfit
    out = bytearray(b"RCM2")
    out += struct.pack("<B", len(BONES))
    for name, parent, pivot in BONES:
        data = name.encode("utf-8")
        out += struct.pack("<B", len(data)) + data
        out += struct.pack("<b", BONE_INDEX[parent] if parent else -1)
        out += struct.pack("<3f", *pivot)
    meshes = [(name, Vector(), objects, True) for name, objects in skinned] + \
             [(obj.name, Vector(obj["pivot"]), [obj], False) for obj in rigid]
    out += struct.pack("<H", len(meshes))
    total = 0
    for name, pivot, sources, is_skinned in meshes:
        vertices, by_zone = [], {}
        for obj in sources:
            mesh = obj.data
            weights = outfit.weights_of(obj) if is_skinned else None
            mesh.calc_normals_split()
            mesh.calc_loop_triangles()
            uv_layer = mesh.uv_layers.active if obj.get("own_uv") else None
            lookup = {}
            for tri in mesh.loop_triangles:
                corner = []
                for loop_index in tri.loops:
                    loop = mesh.loops[loop_index]
                    vi = loop.vertex_index
                    co = mesh.vertices[vi].co - pivot
                    n = loop.normal
                    uv = tuple(uv_layer.data[loop_index].uv) if uv_layer else box_uv(mesh.vertices[vi].co, tri.normal)
                    key = (vi, round(n.x, 3), round(n.y, 3), round(n.z, 3), round(uv[0], 4), round(uv[1], 4))
                    if key not in lookup:
                        lookup[key] = len(vertices)
                        record = [co.x, co.y, co.z, n.x, n.y, n.z, uv[0], uv[1]]
                        if is_skinned:
                            record.append(weights[vi])
                        vertices.append(record)
                    corner.append(lookup[key])
                by_zone.setdefault(tri.material_index, []).extend((corner[0], corner[2], corner[1]))
                total += 1
        assert len(vertices) < 65536, (name, len(vertices))
        data = name.encode("utf-8")
        out += struct.pack("<B", len(data)) + data
        out += struct.pack("<3f", *pivot)
        out += struct.pack("<B", 1 if is_skinned else 0)
        out += struct.pack("<H", len(vertices))
        for v in vertices:
            out += struct.pack("<8f", *v[:8])
            if is_skinned:
                b0, b1, w1 = v[8]
                out += struct.pack("<BBf", b0, b1, w1)
        out += struct.pack("<B", len(by_zone))
        for zone in sorted(by_zone):
            indices = by_zone[zone]
            out += struct.pack("<BI", zone, len(indices))
            out += struct.pack("<%dH" % len(indices), *indices)
        print("  %s: %d vertices" % (name, len(vertices)))
    with open(path, "wb") as f:
        f.write(out)
    print(f"wrote {path}: {len(meshes)} meshes, {total} triangles, {len(out) // 1024} KB")


# ---------------------------------------------------------------------------- the realistic soldier

def build_soldier(texture_dir):
    """
    The soldier: the realistic body and face (human.py) dressed in the uniform and kit
    (outfit.py). Bakes the face's skin texture into texture_dir and copies the eyes' there.
    Returns (skinned [(mesh name, objects)], first-person objects, gear objects).
    """
    import human, outfit
    outfit.Part, outfit.ZONES = Part, ZONES
    B = human.Built(BONE_INDEX)
    head, eyes, lashes, hair = human.build_head(B, ZONES, texture_dir)
    TEXTURES["skin"] = human.bake_skin(head, texture_dir)
    eye_image = bpy.data.images.load(os.path.join(human.DATA, "eyes", "brown_eye.png"))
    eye_image.scale(512, 512)
    eye_image.filepath_raw = TEXTURES["eye"] = os.path.join(texture_dir, "EyeAlbedo.png")
    eye_image.file_format = 'PNG'
    eye_image.save()
    outfit.set_weights(head, lambda co: outfit.mass_near(B, co))
    for obj in (eyes, lashes):
        outfit.rigid(obj, BONE_INDEX["Head"])
    head["own_uv"] = True
    eyes["own_uv"] = True
    dressed = outfit.dress(B, BONE_INDEX)
    skinned = [("Body", [head, eyes, lashes]), ("Uniform", dressed["uniform"]), ("Kit", dressed["kit"])]
    gear = refit_gear(head, hair, dressed["back"])
    return skinned, dressed["first_person"], gear


def refit_gear(head, hair, back_z):
    """
    The headgear and back items, moved from where gear_models() makes them onto the
    realistic head and plate carrier, and the realistic hair in place of the old one.
    """
    objects = {}
    for part in gear_models():
        obj = part.to_object()
        objects[part.name] = obj
    old_hair = objects.pop("Hair")
    bpy.data.objects.remove(old_hair)
    hair.name = "Hair"

    # The old head, in the band the hat brims sit in: half as wide as this, this far back and
    # forward, and its crown this high (with hair). The new one, measured the same way.
    old_half, old_back, old_front, old_top = 0.082, -0.098, 0.076, 1.762
    band = [head.matrix_world @ v.co for v in head.data.vertices if 1.66 <= v.co.y <= 1.72]
    band += [v.co for v in hair.data.vertices if 1.66 <= v.co.y <= 1.72]
    new_half = max(abs(p.x) for p in band)
    new_back = min(p.z for p in band)
    new_front = max(p.z for p in band if abs(p.x) < 0.03 and p.y > 1.69)
    new_top = max(v.co.y for v in hair.data.vertices)
    sx = new_half / old_half
    sz = (new_front - new_back) / (old_front - old_back)
    sy = (sx + sz) / 2
    oc, nc = (old_front + old_back) / 2, (new_front + new_back) / 2
    print("refit head: x %.3f z %.3f y %.3f, centre %.3f -> %.3f, top %.3f" % (sx, sz, sy, oc, nc, new_top))

    def on_head(co):
        return Vector((co.x * sx, new_top - (old_top - co.y) * sy, nc + (co.z - oc) * sz))

    # The old carrier's back face was here; the new one's is at back_z.
    back_shift = Vector((0.0, 0.0, back_z - (-0.1605)))
    for name, obj in objects.items():
        for v in obj.data.vertices:
            if name in ("Helmet", "Cap", "Beanie", "Boonie", "Headset", "HelmetHeadset", "Bandana"):
                v.co = on_head(v.co)
            elif name == "Scarf":
                v.co = v.co + Vector((0.0, 0.0, 0.026))
            else:
                v.co = v.co + back_shift
        obj.data.update()
    return [hair] + list(objects.values())


# ---------------------------------------------------------------------------- posing, as the game does

def unity_euler(x, y, z):
    """Unity's Quaternion.Euler(x, y, z) as a matrix: z, then x, then y."""
    return (Matrix.Rotation(math.radians(y), 4, 'Y') @ Matrix.Rotation(math.radians(x), 4, 'X')
            @ Matrix.Rotation(math.radians(z), 4, 'Z'))


def pose_bones(motion, gun_profile=None, gun_att=None):
    """
    The bones' model-space matrices for a pose, by Client/Visuals/SoldierView.cs's rules, and
    where the gun goes. Returns (matrices by bone, gun root matrix or None).
    """
    rot = {n: Matrix.Identity(4) for n, _, _ in BONES}
    local = {n: PIVOT[n] - (PIVOT[PARENT[n]] if PARENT[n] else Vector()) for n, _, _ in BONES}
    length = lambda a, b: (PIVOT[b] - PIVOT[a]).length
    thigh_len, shin_len = length("ThighL", "ShinL"), length("ShinL", "FootL")
    upper_len, fore_len = length("UpperArmL", "ForearmL"), length("ForearmL", "HandL")
    ankle = PIVOT["FootL"].y

    speed, phase, stance = motion["speed"], motion["phase"], motion.get("stance", "stand")
    amplitude = min(speed / 5.6, 1.3)
    drop = 0.0 if stance == "stand" else 0.34
    bob = amplitude * 0.035 * abs(math.cos(phase))
    pelvis_pos = PIVOT["Pelvis"] - Vector((0, drop + bob, 0))
    hip_height = PIVOT["Pelvis"].y - (PIVOT["Pelvis"].y - PIVOT["ThighL"].y) - drop - bob
    reach = max(0.25, min(hip_height - ankle, thigh_len + shin_len - 0.005))
    hip = math.acos(max(-1, min(1, (thigh_len ** 2 + reach ** 2 - shin_len ** 2) / (2 * thigh_len * reach))))
    inner = math.acos(max(-1, min(1, (thigh_len ** 2 + shin_len ** 2 - reach ** 2) / (2 * thigh_len * shin_len))))
    thigh_base, knee_base = -math.degrees(hip), math.degrees(math.pi - inner)
    for side, ph in (("L", phase), ("R", phase + math.pi)):
        swing = math.sin(ph)
        lift = max(0.0, math.cos(ph)) * amplitude * 42
        pitch = thigh_base - swing * amplitude * 30 - lift * 0.4
        knee = knee_base + lift
        rot["Thigh" + side] = unity_euler(pitch, 0, 0)
        rot["Shin" + side] = unity_euler(knee, 0, 0)
        rot["Foot" + side] = unity_euler(-(pitch + knee) - lift * 0.2, 0, 0)
    view_pitch = motion.get("pitch", 0.0)
    lean = amplitude * 7
    rot["Torso"] = unity_euler(view_pitch * 0.4 + lean, 0, 0)
    rot["Head"] = unity_euler(view_pitch * 0.35 - lean * 0.6, 0, 0)

    world = {}
    def world_of(n):
        if n not in world:
            base = Matrix.Identity(4) if PARENT[n] is None else world_of(PARENT[n])
            world[n] = base @ Matrix.Translation(pelvis_pos if n == "Pelvis" else local[n]) @ rot[n]
        return world[n]
    for n, _, _ in BONES:
        world_of(n)

    if gun_profile is None:
        for side, s in (("L", -1), ("R", 1)):
            world["UpperArm" + side] = world["Torso"] @ Matrix.Translation(local["UpperArm" + side]) @ unity_euler(0, 0, s * 3)
            world["Forearm" + side] = world["UpperArm" + side] @ Matrix.Translation(local["Forearm" + side]) @ unity_euler(-4, 0, 0)
            world["Hand" + side] = world["Forearm" + side] @ Matrix.Translation(local["Hand" + side])
        return world, None

    mount = world["Torso"] @ Matrix.Translation((0.13, 0.36, 0.05)) @ unity_euler(view_pitch * 0.6 - lean, 0, 0)
    b, body_len = gun_profile["bulk"], gun_profile["body"]
    rear = -(body_len * 0.5 + gun_profile["stock"])
    gun_root = mount @ Matrix.Translation((0, 0, -rear - 0.03))
    grip = gun_root @ Vector((0, -0.075 * b, -body_len * 0.28))
    handguard = gun_profile["barrel"] * 0.55
    support = gun_root @ Vector((0, 0.004 * b - 0.026 * b, body_len * 0.5 + max(handguard, 0.04) * 0.5))
    up = (gun_root.to_3x3() @ Vector((0, 1, 0))).normalized()
    fwd = (gun_root.to_3x3() @ Vector((0, 0, 1))).normalized()
    right = (gun_root.to_3x3() @ Vector((1, 0, 0))).normalized()

    def reach_arm(side, target, pole):
        upper, fore, hand = "UpperArm" + side, "Forearm" + side, "Hand" + side
        shoulder = world[upper].to_translation()
        to_target = target - shoulder
        distance = max(0.05, min(to_target.length, upper_len + fore_len - 0.002))
        direction = to_target.normalized()
        cos_a = max(-1, min(1, (upper_len ** 2 + distance ** 2 - fore_len ** 2) / (2 * upper_len * distance)))
        sin_a = math.sqrt(1 - cos_a ** 2)
        bend = pole - direction * pole.dot(direction)
        bend.normalize()
        elbow = shoulder + direction * (cos_a * upper_len) + bend * (sin_a * upper_len)
        wrist = shoulder + direction * distance
        r_upper = (PIVOT[fore] - PIVOT[upper]).rotation_difference(elbow - shoulder).to_matrix().to_4x4()
        r_fore = (PIVOT[hand] - PIVOT[fore]).rotation_difference(wrist - elbow).to_matrix().to_4x4()
        world[upper] = Matrix.Translation(shoulder) @ r_upper
        world[fore] = Matrix.Translation(elbow) @ r_fore
        world[hand] = Matrix.Translation(wrist) @ r_fore

    reach_arm("R", grip + up * 0.055 - fwd * 0.02, Vector((0.7, -1, -0.3)))
    reach_arm("L", support - up * 0.02 - right * 0.025, Vector((-0.8, -1, -0.1)))
    return world, gun_root


def posed_copy(obj, bone, weights, world, place, name):
    """A copy of a body piece, skinned to the posed bones (linear blend, as Unity does) and placed."""
    mesh = obj.data.copy()
    skin = {n: world[n] @ Matrix.Translation(-PIVOT[n]) for n, _, _ in BONES}
    names = [n for n, _, _ in BONES]
    for v, (b0, b1, w1) in zip(mesh.vertices, weights):
        p = v.co.copy()
        a = skin[names[b0]] @ p
        if w1 > 0:
            a = a * (1 - w1) + (skin[names[b1]] @ p) * w1
        v.co = place @ a
    mesh.update()
    copy = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(copy)
    copy["pivot"] = [0, 0, 0]
    return copy


def posed_soldier(pieces, gear, motion, gun=None, gun_objects=None, origin=(0, 0, 0), yaw=0.0, headgear="Helmet", back=None, tag=""):
    """A whole soldier in a pose: body pieces, headgear, a back item and a gun. Returns the objects."""
    world, gun_root = pose_bones(motion, *(gun or (None, None)))
    place = Matrix.Translation(origin) @ Matrix.Rotation(math.radians(yaw), 4, 'Y')
    made = []
    for obj, bone, weights in pieces:
        made.append(posed_copy(obj, bone, weights, world, place, obj.name + "_posed" + tag))
    gear_by_name = {o.name.split(".")[0]: o for o in gear}
    worn = []
    if headgear:
        worn += [(gear_by_name[n], "Head") for n in (headgear if isinstance(headgear, (list, tuple)) else [headgear])]
    if back:
        worn.append((gear_by_name[back], "Torso"))
    for obj, bone in worn:
        rigid = [(BONE_INDEX[bone], BONE_INDEX[bone], 0.0)] * len(obj.data.vertices)
        made.append(posed_copy(obj, bone, rigid, world, place, obj.name + "_worn" + tag))
    if gun is not None:
        meshes = {o.name.split(".")[0]: o.data for o in gun_objects}
        for name, pos, size, rot_x in gun_layout(*gun):
            g = bpy.data.objects.new(name + "_held" + tag, meshes[name])
            bpy.context.scene.collection.objects.link(g)
            g["pivot"] = [0, 0, 0]
            g.matrix_world = place @ gun_root @ Matrix.Translation(pos) @ unity_euler(rot_x, 0, 0) @ Matrix.Diagonal((size[0], size[1], size[2], 1))
            made.append(g)
    return made


# ---------------------------------------------------------------------------- gun parts

def gun_parts():
    """Detailed parts, each filling the unit box (-0.5..0.5 on every axis), +z towards the muzzle."""
    parts = []

    p = Part("Receiver")
    p.box((0, -0.06, 0), (0.96, 0.82, 1.0), "primary", bevel=0.09, segments=3)
    p.box((0, 0.4, 0.02), (0.62, 0.16, 0.96), "dark", bevel=0.03)
    for i in range(14):
        p.box((0, 0.485, -0.44 + i * 0.066), (0.66, 0.06, 0.03), "metal", bevel=0.008)
    p.box((0.47, 0.06, 0.12), (0.08, 0.22, 0.3), "dark", bevel=0.02)
    p.box((0.49, 0.06, 0.12), (0.04, 0.12, 0.22), "metal", bevel=0.01)
    p.box((-0.47, 0.1, -0.2), (0.08, 0.08, 0.18), "metal", bevel=0.02)
    p.box((0, -0.45, 0.18), (0.7, 0.12, 0.36), "primary", bevel=0.03)
    for z in (-0.35, 0.36):
        for s in (-1, 1):
            p.cylinder((s * 0.5, -0.1, z), (s * 0.47, -0.1, z), 0.035, 0.035, "metal", segments=8)
    parts.append(p)

    p = Part("Handguard")
    p.box((0, 0, 0), (0.96, 0.92, 1.0), "primary", bevel=0.14, segments=3)
    for z in (-0.3, -0.1, 0.1, 0.3):
        for s in (-1, 1):
            p.box((s * 0.47, 0.05, z), (0.08, 0.26, 0.12), "dark", bevel=0.04, segments=2)
    for i in range(13):
        p.box((0, 0.47, -0.44 + i * 0.073), (0.5, 0.07, 0.035), "metal", bevel=0.01)
    for i in range(13):
        p.box((0, -0.47, -0.44 + i * 0.073), (0.4, 0.06, 0.03), "dark", bevel=0.01)
    parts.append(p)

    p = Part("Barrel")
    p.cylinder((0, 0, -0.5), (0, 0, 0.5), 0.5, 0.46, "primary", segments=18, bevel=0.05)
    for z in (-0.3, 0.42):
        p.cylinder((0, 0, z - 0.04), (0, 0, z + 0.04), 0.53, 0.53, "metal", segments=18, bevel=0.03)
    parts.append(p)

    p = Part("Suppressor")
    p.cylinder((0, 0, -0.5), (0, 0, 0.5), 0.5, 0.5, "primary", segments=24, bevel=0.12, bevel_segments=3)
    for z in (-0.38, 0.0, 0.38):
        p.cylinder((0, 0, z - 0.02), (0, 0, z + 0.02), 0.505, 0.505, "dark", segments=24)
    p.cylinder((0, 0, 0.48), (0, 0, 0.505), 0.2, 0.2, "dark", segments=16)
    parts.append(p)

    p = Part("MuzzleDevice")
    p.cylinder((0, 0, -0.5), (0, 0, 0.5), 0.46, 0.5, "primary", segments=16, bevel=0.06)
    for a in range(3):
        t = a * 2 * math.pi / 3
        p.box((math.cos(t) * 0.45, math.sin(t) * 0.45, 0.05), (0.18, 0.18, 0.55), "dark", bevel=0.04, rot=(0, 0, math.degrees(t)))
    parts.append(p)

    p = Part("Stock")
    # A buffer tube from the receiver, then the buttstock: a cheek riser on top, a sloped
    # underside, a rubber pad at the back.
    p.cylinder((0, 0.12, 0.5), (0, 0.12, -0.05), 0.24, 0.24, "dark", segments=16, bevel=0.03)
    p.box((0, 0.02, -0.24), (0.92, 0.96, 0.5), "primary", bevel=0.1, segments=3, taper_bottom=(0.85, 0.55))
    p.box((0, 0.42, -0.2), (0.62, 0.16, 0.42), "primary", bevel=0.06, segments=2)
    p.box((0, -0.44, 0.05), (0.3, 0.1, 0.5), "dark", bevel=0.03, rot=(-14, 0, 0))
    p.box((0, 0.02, -0.48), (1.0, 1.0, 0.06), "dark", bevel=0.025, segments=2)
    p.box((0.47, 0.1, -0.22), (0.06, 0.16, 0.2), "metal", bevel=0.02)
    parts.append(p)

    p = Part("Grip")
    p.box((0, 0, 0), (1.0, 1.0, 0.92), "primary", bevel=0.25, segments=3, taper=(0.9, 0.95))
    for y in (-0.25, 0.0, 0.25):
        p.box((0, y, 0.45), (0.8, 0.12, 0.12), "primary", bevel=0.05)
    for y in (-0.3, -0.1, 0.1, 0.3):
        for s in (-1, 1):
            p.box((s * 0.48, y, -0.05), (0.06, 0.08, 0.6), "dark", bevel=0.02)
    p.box((0, -0.48, 0), (0.9, 0.06, 0.9), "dark", bevel=0.03)
    parts.append(p)

    p = Part("Magazine")
    p.box((0, 0.04, 0), (0.94, 0.92, 0.96), "primary", bevel=0.12, segments=2)
    for y in (-0.3, -0.1, 0.1, 0.3):
        for s in (-1, 1):
            p.box((s * 0.47, y, 0.0), (0.08, 0.1, 0.7), "primary", bevel=0.03)
    p.box((0, -0.46, 0.02), (1.0, 0.1, 1.0), "dark", bevel=0.04, segments=2)
    p.box((0, 0.48, 0), (0.8, 0.04, 0.9), "metal")
    parts.append(p)

    p = Part("Drum")
    p.cylinder((-0.5, 0, 0), (0.5, 0, 0), 0.5, 0.5, "primary", segments=24, bevel=0.12, bevel_segments=3)
    for x in (-0.3, 0.3):
        p.cylinder((x - 0.03, 0, 0), (x + 0.03, 0, 0), 0.51, 0.51, "dark", segments=24)
    p.cylinder((0.48, 0, 0), (0.52, 0, 0), 0.2, 0.2, "metal", segments=12)
    parts.append(p)

    p = Part("VerticalGrip")
    p.cylinder((0, -0.5, 0), (0, 0.5, 0), 0.42, 0.48, "primary", segments=16, bevel=0.1)
    for y in (-0.3, -0.05, 0.2):
        p.cylinder((0, y - 0.04, 0), (0, y + 0.04, 0), 0.5, 0.5, "dark", segments=16)
    p.box((0, 0.46, 0), (0.7, 0.08, 0.9), "metal", bevel=0.02)
    parts.append(p)

    p = Part("AngledGrip")
    p.box((0, 0, 0), (0.9, 0.8, 1.0), "primary", bevel=0.2, segments=3, taper=(0.9, 0.4))
    p.box((0, 0.44, 0), (0.7, 0.12, 0.95), "metal", bevel=0.02)
    parts.append(p)

    p = Part("Laser")
    p.box((0, 0, 0), (1.0, 1.0, 1.0), "primary", bevel=0.18, segments=2)
    p.cylinder((0.18, 0.15, 0.45), (0.18, 0.15, 0.52), 0.15, 0.15, "glow", segments=12)
    p.cylinder((-0.18, -0.15, 0.45), (-0.18, -0.15, 0.52), 0.12, 0.12, "metal", segments=12)
    p.box((0.5, 0, -0.1), (0.06, 0.3, 0.3), "dark", bevel=0.03)
    parts.append(p)

    # An open sight frame: base, posts and a top, with a hollow window to look through.
    p = Part("SightFrame")
    p.box((0, -0.38, 0), (1.0, 0.24, 1.0), "primary", bevel=0.05, segments=2)
    for s in (-1, 1):
        p.box((s * 0.44, 0.06, 0), (0.12, 0.66, 0.96), "primary", bevel=0.04, segments=2)
    p.box((0, 0.44, 0), (1.0, 0.12, 0.96), "primary", bevel=0.04, segments=2)
    p.box((0.5, 0.1, -0.1), (0.06, 0.18, 0.2), "metal", bevel=0.02)
    p.box((0, -0.38, 0.45), (0.5, 0.1, 0.06), "glow")
    parts.append(p)

    p = Part("Scope")
    p.cylinder((0, 0, -0.5), (0, 0, -0.32), 0.42, 0.42, "primary", segments=20, bevel=0.04)
    p.cylinder((0, 0, -0.32), (0, 0, 0.22), 0.3, 0.3, "primary", segments=20)
    p.cylinder((0, 0, 0.22), (0, 0, 0.5), 0.36, 0.5, "primary", segments=20, bevel=0.04)
    p.cylinder((0, 0, 0.495), (0, 0, 0.505), 0.42, 0.42, "glow", segments=20)
    p.cylinder((0, 0.25, -0.05), (0, 0.48, -0.05), 0.12, 0.12, "metal", segments=12, bevel=0.02)
    p.cylinder((0.25, 0, -0.05), (0.46, 0, -0.05), 0.11, 0.11, "metal", segments=12, bevel=0.02)
    parts.append(p)

    p = Part("ScopeMount")
    p.box((0, -0.2, 0), (1.0, 0.6, 1.0), "dark", bevel=0.08)
    for z in (-0.32, 0.32):
        p.box((0, 0.2, z), (1.0, 0.6, 0.18), "metal", bevel=0.05)
    parts.append(p)

    p = Part("Post")
    p.box((0, -0.1, 0), (1.0, 0.8, 1.0), "primary", bevel=0.2, segments=2)
    p.box((0, 0.38, 0), (0.5, 0.24, 0.6), "metal", bevel=0.08)
    parts.append(p)

    p = Part("Tube")
    p.cylinder((0, 0, -0.5), (0, 0, 0.5), 0.5, 0.5, "primary", segments=24, bevel=0.03)
    for z in (-0.25, 0.0, 0.25):
        p.cylinder((0, 0, z - 0.025), (0, 0, z + 0.025), 0.515, 0.515, "dark", segments=24)
    p.box((0, 0.5, -0.1), (0.25, 0.08, 0.4), "metal", bevel=0.02)
    parts.append(p)

    p = Part("Mouth")
    p.ring((0, 0, 0), (0, 0, 1), 0.5, 0.36, 1.0, "primary", segments=24)
    parts.append(p)

    p = Part("Tail")
    p.cylinder((0, 0, 0.5), (0, 0, -0.5), 0.42, 0.5, "primary", segments=24, bevel=0.04)
    p.cylinder((0, 0, -0.505), (0, 0, -0.49), 0.3, 0.3, "dark", segments=16)
    parts.append(p)

    p = Part("Band")
    p.cylinder((0, 0, -0.5), (0, 0, 0.5), 0.5, 0.5, "primary", segments=24)
    parts.append(p)

    p = Part("Blade")
    # Tapering to a point, with a bevelled edge along the bottom.
    p.box((0, 0.1, -0.05), (0.7, 0.8, 0.9), "primary", bevel=0.05, taper=(0.2, 1.0))
    p.box((0, -0.38, -0.05), (0.25, 0.24, 0.9), "metal", bevel=0.02)
    p.box((0, 0.0, 0.42), (0.5, 0.5, 0.16), "primary", bevel=0.05, taper=(0.1, 0.1))
    parts.append(p)

    p = Part("Handle")
    p.box((0, 0, 0), (0.9, 0.9, 1.0), "primary", bevel=0.25, segments=3)
    for z in (-0.3, -0.1, 0.1, 0.3):
        p.box((0, 0, z), (0.95, 0.95, 0.06), "metal", bevel=0.03)
    parts.append(p)

    p = Part("Box")
    p.box((0, 0, 0), (1.0, 1.0, 1.0), "primary", bevel=0.12, segments=2)
    parts.append(p)

    return parts


# ---------------------------------------------------------------------------- projectiles

def ogive(z0, z1, r, steps=10, tip=0.0):
    """A pointed nose from radius r at z0 to a point (or a small flat of radius tip) at z1."""
    out = []
    for i in range(steps + 1):
        t = i / steps
        # A tangent ogive: full width at the back, curving in to the point.
        out.append((z0 + (z1 - z0) * t, tip + (r - tip) * math.sqrt(max(0.0, 1 - t * t))))
    return out


def dome(z0, z1, r, steps=8):
    """A rounded end: radius r at z0 closing to a point at z1 along a quarter circle."""
    return [(z0 + (z1 - z0) * math.sin(math.pi / 2 * i / steps), r * math.cos(math.pi / 2 * i / steps)) for i in range(steps + 1)]


def fins(part, z, length, root_r, span, thickness, zone, count=4, sweep=0.35, offset_deg=45):
    """Swept fins round the z axis: count of them, each a tapered plate from the body outwards."""
    for k in range(count):
        a = math.radians(offset_deg + 360 * k / count)
        out = Vector((math.cos(a), math.sin(a), 0))
        side = Vector((-math.sin(a), math.cos(a), 0))
        root_back, root_front = Vector((0, 0, z - length / 2)), Vector((0, 0, z + length / 2))
        tip_back = root_back + out * span
        tip_front = root_back + out * span + Vector((0, 0, length * (1 - sweep)))
        quad = [root_back + out * root_r, root_front + out * root_r, tip_front + out * root_r, tip_back + out * root_r]
        half = side * (thickness / 2)
        front = [part.bm.verts.new(v + half) for v in quad]
        back = [part.bm.verts.new(v - half) for v in quad]
        faces = [part.bm.faces.new(front), part.bm.faces.new(list(reversed(back)))]
        for i in range(4):
            j = (i + 1) % 4
            faces.append(part.bm.faces.new((front[j], front[i], back[i], back[j])))
        for f in faces:
            f.material_index = ZONES[zone]


def vanes(part, z, length, height, thickness, zone, count=3, root_r=0.0):
    """Fletching: count of thin vanes round a shaft, rising from the shaft and tapering back."""
    for k in range(count):
        a = math.radians(90 + 360 * k / count)
        out = Vector((math.cos(a), math.sin(a), 0))
        side = Vector((-math.sin(a), math.cos(a), 0))
        pts = [Vector((0, 0, z - length / 2)) + out * root_r,
               Vector((0, 0, z + length / 2)) + out * root_r,
               Vector((0, 0, z + length * 0.05)) + out * (root_r + height * 0.35),
               Vector((0, 0, z - length * 0.42)) + out * (root_r + height)]
        half = side * (thickness / 2)
        front = [part.bm.verts.new(v + half) for v in pts]
        back = [part.bm.verts.new(v - half) for v in pts]
        faces = [part.bm.faces.new(front), part.bm.faces.new(list(reversed(back)))]
        for i in range(4):
            j = (i + 1) % 4
            faces.append(part.bm.faces.new((front[j], front[i], back[i], back[j])))
        for f in faces:
            f.material_index = ZONES[zone]


def projectile_models():
    """
    What flies, at the size it is drawn (a little larger than life where life would be too
    small to see at range), pointing along +z, centred on where the simulation has it.
    Zones: primary is the weapon's (or item's) body colour, trim its accent colour, glow a
    bright unlit version of the accent, dark and metal the shared materials.
    """
    parts = []

    # A rocket: an ogive warhead, a body with a band, swept fins and a burning motor.
    p = Part("Rocket")
    p.lathe([(-0.27, 0.0), (-0.27, 0.026), (-0.255, 0.034), (-0.24, 0.036)], "metal", 32)
    p.lathe([(-0.24, 0.036), (-0.2, 0.04), (0.06, 0.04)], "primary", 32)
    p.lathe([(0.06, 0.0405), (0.1, 0.0405)], "trim", 32)
    p.lathe([(0.1, 0.04), (0.14, 0.04)] + ogive(0.14, 0.31, 0.04, 14, tip=0.004)[1:], "primary", 32)
    p.lathe([(0.305, 0.006), (0.316, 0.0)], "metal", 16)
    p.lathe([(-0.278, 0.0), (-0.278, 0.022), (-0.272, 0.024)], "glow", 24)
    fins(p, -0.19, 0.11, 0.038, 0.05, 0.004, "dark", count=4, sweep=0.45)
    p.lathe([(-0.02, 0.0405), (0.0, 0.0405)], "dark", 32)
    parts.append(p)

    # A 40 mm grenade, made big enough to follow: a rounded nose on a short case.
    p = Part("Grenade40")
    p.lathe([(-0.055, 0.0), (-0.055, 0.03), (-0.05, 0.036), (-0.02, 0.036)], "dark", 32)
    p.lathe([(-0.02, 0.0375), (0.0, 0.0375)], "trim", 32)
    p.lathe([(0.0, 0.036)] + dome(0.0, 0.07, 0.036, 10)[1:], "primary", 32)
    p.lathe([(0.004, 0.0372), (0.012, 0.0372)], "metal", 32)
    p.lathe([(-0.06, 0.0), (-0.06, 0.012), (-0.056, 0.014)], "glow", 16)
    parts.append(p)

    # A hand grenade: a ridged egg, the fuse on top, the spoon down its side and the ring.
    p = Part("FragGrenade")
    egg = [(-0.042, 0.0)] + [(-0.042 + 0.084 * t, 0.032 * math.sin(math.pi * t) ** 0.8 * (1 - 0.12 * t)) for t in [i / 20 for i in range(1, 20)]] + [(0.042, 0.0)]
    p.lathe(egg, "primary", 36)
    for i in range(1, 6):
        t = i / 6
        z = -0.042 + 0.084 * t
        r = 0.032 * math.sin(math.pi * t) ** 0.8 * (1 - 0.12 * t)
        p.lathe([(z - 0.0018, r + 0.0006), (z + 0.0018, r + 0.0006)], "dark", 36)
    p.lathe([(0.04, 0.0), (0.04, 0.012), (0.055, 0.012), (0.058, 0.009), (0.058, 0.0)], "metal", 20)
    p.box((0.0, 0.016, 0.03), (0.008, 0.004, 0.07), "metal", bevel=0.001, rot=(-12, 0, 0))
    p.ring((0.0, -0.013, 0.058), (1, 0, 0), 0.009, 0.0065, 0.002, "metal", 20)
    parts.append(p)

    # An impact grenade: a squat can with a domed striker and a glowing band.
    p = Part("ImpactGrenade")
    p.lathe([(-0.045, 0.0), (-0.045, 0.026), (-0.04, 0.03), (0.02, 0.03)], "primary", 32)
    p.lathe([(0.0, 0.0306), (0.01, 0.0306)], "glow", 32)
    p.lathe([(0.02, 0.03)] + dome(0.02, 0.05, 0.03, 8)[1:], "dark", 32)
    p.lathe([(0.046, 0.008), (0.055, 0.006), (0.056, 0.0)], "metal", 16)
    parts.append(p)

    # A sticky grenade: a ball in a tacky shell, studded, with a glowing seam.
    p = Part("StickyGrenade")
    p.sphere((0, 0, 0), 0.035, "primary", u=32, v=18)
    p.lathe([(-0.003, 0.0362), (0.003, 0.0362)], "glow", 32)
    for i in range(14):
        a = i * 2.39996
        y = 1 - 2 * (i + 0.5) / 14
        rr = math.sqrt(max(0.0, 1 - y * y))
        d = Vector((math.cos(a) * rr, y, math.sin(a) * rr))
        p.sphere(tuple(d * 0.035), 0.007, "dark", u=10, v=6)
    parts.append(p)

    # A shock charge: a puck with prongs and a glowing coil.
    p = Part("ShockCharge")
    p.lathe([(-0.018, 0.0), (-0.018, 0.04), (-0.012, 0.046), (0.012, 0.046), (0.018, 0.04), (0.018, 0.0)], "primary", 36)
    p.ring((0, 0, 0), (0, 0, 1), 0.049, 0.043, 0.012, "glow", 36)
    for k in range(3):
        a = math.radians(90 + k * 120)
        base = Vector((math.cos(a) * 0.026, math.sin(a) * 0.026, 0.018))
        p.cylinder(base, base + Vector((0, 0, 0.018)), 0.004, 0.0025, "metal", segments=10)
        p.sphere(tuple(base + Vector((0, 0, 0.02))), 0.004, "glow", u=10, v=6)
    parts.append(p)

    # A ricochet disc: thin, bevelled, a glowing rim and a hub. It flies flat.
    p = Part("Disc")
    p.lathe([(-0.006, 0.0), (-0.006, 0.05), (-0.002, 0.07), (0.002, 0.07), (0.006, 0.05), (0.006, 0.0)], "primary", 48)
    p.ring((0, 0, 0), (0, 0, 1), 0.073, 0.068, 0.004, "glow", 48)
    p.lathe([(-0.0085, 0.0), (-0.0085, 0.016), (0.0085, 0.016), (0.0085, 0.0)], "dark", 24)
    for k in range(6):
        a = math.radians(k * 60)
        p.box((math.cos(a) * 0.036, math.sin(a) * 0.036, 0.0), (0.012, 0.012, 0.0136), "trim", bevel=0.002, rot=(0, 0, k * 60))
    # Lie it flat: the disc's face up, rim leading.
    for v in p.bm.verts:
        v.co = Vector((v.co.x, v.co.z, v.co.y))
    parts.append(p)

    # An arrow: a broadhead, a long shaft, three vanes and a nock.
    p = Part("Arrow")
    p.lathe([(-0.36, 0.0), (-0.36, 0.005), (0.33, 0.005), (0.33, 0.0)], "primary", 12)
    p.lathe([(0.325, 0.0), (0.325, 0.0065), (0.345, 0.0065), (0.345, 0.0)], "dark", 12)
    p.box((0, 0, 0.375), (0.026, 0.0025, 0.06), "metal", bevel=0.0008, taper=None)
    p.box((0, 0, 0.375), (0.0025, 0.026, 0.06), "metal", bevel=0.0008)
    p.lathe([(0.345, 0.0055), (0.36, 0.0055)] + ogive(0.36, 0.42, 0.0055, 6)[1:], "metal", 12)
    vanes(p, -0.29, 0.1, 0.018, 0.0015, "trim", count=3, root_r=0.005)
    p.lathe([(-0.375, 0.0), (-0.375, 0.006), (-0.36, 0.006), (-0.36, 0.0)], "dark", 12)
    parts.append(p)

    # A crossbow bolt: shorter and thicker, a field point, stiff vanes.
    p = Part("Bolt")
    p.lathe([(-0.2, 0.0), (-0.2, 0.0065), (0.17, 0.0065), (0.17, 0.0)], "primary", 14)
    p.lathe([(0.165, 0.007), (0.18, 0.007)] + ogive(0.18, 0.225, 0.007, 8)[1:], "metal", 14)
    vanes(p, -0.15, 0.08, 0.015, 0.002, "trim", count=3, root_r=0.0065)
    p.lathe([(-0.205, 0.0), (-0.205, 0.007), (-0.195, 0.007), (-0.195, 0.0)], "dark", 14)
    parts.append(p)

    # A throwing knife: a narrow blade and a wrapped handle with a ring. It spins in flight.
    p = Part("ThrowingKnife")
    p.box((0, 0, 0.055), (0.003, 0.028, 0.11), "metal", bevel=0.0008, taper=(1.0, 0.25))
    p.box((0, -0.006, 0.055), (0.0045, 0.012, 0.11), "metal", bevel=0.001)
    for v in p.bm.verts:
        if v.co.z > 0.1:
            v.co.y *= 0.2
    p.lathe([(-0.07, 0.0), (-0.07, 0.008), (0.0, 0.008), (0.0, 0.0)], "dark", 14)
    for i in range(5):
        z = -0.06 + i * 0.013
        p.lathe([(z, 0.0088), (z + 0.004, 0.0088)], "trim", 14)
    p.ring((0, 0, -0.082), (1, 0, 0), 0.013, 0.008, 0.004, "metal", 20)
    parts.append(p)

    # A flare: a cartridge burning bright at the front.
    p = Part("Flare")
    p.lathe([(-0.05, 0.0), (-0.05, 0.016), (0.02, 0.016)], "dark", 24)
    p.lathe([(-0.052, 0.0), (-0.052, 0.019), (-0.045, 0.019), (-0.045, 0.016)], "metal", 24)
    p.lathe([(0.02, 0.016)] + dome(0.02, 0.05, 0.016, 8)[1:], "glow", 24)
    p.sphere((0, 0, 0.03), 0.026, "glow", u=20, v=12)
    parts.append(p)

    # Plasma: a bright core inside two spinning rings, pointed fore and aft.
    p = Part("Plasma")
    p.lathe([(-0.1, 0.0)] + [(-0.1 + 0.2 * t, 0.024 * math.sin(math.pi * t) ** 0.6) for t in [i / 16 for i in range(1, 16)]] + [(0.1, 0.0)], "glow", 24)
    for z, r in ((-0.03, 0.034), (0.03, 0.03)):
        p.ring((0, 0, z), (0, 0, 1), r, r - 0.005, 0.006, "trim", 32)
    parts.append(p)

    # A ricochet blaster's charge: a faceted ball of light.
    p = Part("Spark")
    res = bmesh.ops.create_icosphere(p.bm, subdivisions=2, radius=0.03)
    for f in {f for v in res["verts"] for f in v.link_faces}:
        f.material_index = ZONES["glow"]
    res = bmesh.ops.create_icosphere(p.bm, subdivisions=1, radius=0.042)
    shell = list({f for v in res["verts"] for f in v.link_faces})
    for f in shell:
        f.material_index = ZONES["trim"]
    bmesh.ops.delete(p.bm, geom=[f for i, f in enumerate(shell) if i % 3 == 0], context='FACES_ONLY')
    parts.append(p)

    # A paintball: a glossy ball with its seam.
    p = Part("Paintball")
    p.sphere((0, 0, 0), 0.03, "primary", u=28, v=16)
    p.ring((0, 0, 0), (0, 1, 0), 0.0305, 0.028, 0.003, "trim", 28)
    parts.append(p)

    # A slingshot pellet: a steel ball, big enough to see.
    p = Part("Pellet")
    p.sphere((0, 0, 0), 0.022, "metal", u=24, v=14)
    parts.append(p)

    return parts


# ---------------------------------------------------------------------------- export

def export(objects, path, magic=b"RCM1"):
    """
    RCM1: magic; uint16 mesh count; then per mesh: name (uint8 length, UTF-8), pivot
    (3 floats), uint16 vertex count, vertices (position 3 floats, normal 3 floats, uv 2
    floats), uint8 submesh count, then per submesh: uint8 zone, uint32 index count,
    uint16 indices. Positions are relative to the pivot, in the game's frame.
    """
    out = bytearray(magic)
    out += struct.pack("<H", len(objects))
    total_tris = 0
    for obj in objects:
        mesh = obj.data
        mesh.calc_normals_split()
        mesh.calc_loop_triangles()
        pivot = Vector(obj["pivot"])
        vertices, lookup = [], {}
        by_zone = {}
        for tri in mesh.loop_triangles:
            corner = []
            for loop_index in tri.loops:
                loop = mesh.loops[loop_index]
                co = mesh.vertices[loop.vertex_index].co - pivot
                n = loop.normal
                uv = box_uv(mesh.vertices[loop.vertex_index].co, tri.normal)
                key = (loop.vertex_index, round(n.x, 3), round(n.y, 3), round(n.z, 3), round(uv[0], 4), round(uv[1], 4))
                if key not in lookup:
                    lookup[key] = len(vertices)
                    vertices.append((co.x, co.y, co.z, n.x, n.y, n.z, uv[0], uv[1]))
                corner.append(lookup[key])
            # Blender winds front faces anticlockwise; Unity, in its left-handed space, clockwise.
            by_zone.setdefault(tri.material_index, []).extend((corner[0], corner[2], corner[1]))
            total_tris += 1
        assert len(vertices) < 65536, obj.name
        name = obj.name.encode("utf-8")
        out += struct.pack("<B", len(name)) + name
        out += struct.pack("<3f", *pivot)
        out += struct.pack("<H", len(vertices))
        for v in vertices:
            out += struct.pack("<8f", *v)
        out += struct.pack("<B", len(by_zone))
        for zone in sorted(by_zone):
            indices = by_zone[zone]
            out += struct.pack("<BI", zone, len(indices))
            out += struct.pack("<%dH" % len(indices), *indices)
    with open(path, "wb") as f:
        f.write(out)
    print(f"wrote {path}: {len(objects)} meshes, {total_tris} triangles, {len(out) // 1024} KB")


def box_uv(co, normal):
    """Texture coordinates projected along the face's main axis, two repeats a metre."""
    ax, ay, az = abs(normal.x), abs(normal.y), abs(normal.z)
    if ax >= ay and ax >= az:
        return (co.z * 2.0, co.y * 2.0)
    if ay >= az:
        return (co.x * 2.0, co.z * 2.0)
    return (co.x * 2.0, co.y * 2.0)


# ---------------------------------------------------------------------------- previews

def preview(objects, path, camera_at, look_at, lens=50, size=(900, 1100), offsets=None):
    scene = bpy.context.scene
    for slot_zone, colour in PREVIEW_COLOURS.items():
        name = "preview_%d" % slot_zone
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = colour
        bsdf.inputs["Roughness"].default_value = 0.45 if slot_zone != 2 else 0.3
        bsdf.inputs["Metallic"].default_value = 0.8 if slot_zone == 2 else 0.0
        if slot_zone == 3:
            bsdf.inputs["Emission Color"].default_value = colour
            bsdf.inputs["Emission Strength"].default_value = 4.0
    rig = bpy.data.objects.new("PreviewRig", None)
    scene.collection.objects.link(rig)
    # The game's frame (y up, z forward) stood up in Blender's (z up): turn it about x.
    rig.matrix_world = Matrix.Rotation(math.radians(90), 4, 'X')
    for i, obj in enumerate(objects):
        # Only ever appended: clearing the list would reset every face to the first slot.
        if len(obj.data.materials) == 0:
            for zone in range(len(PREVIEW_COLOURS)):
                obj.data.materials.append(bpy.data.materials["preview_%d" % zone])
        obj.parent = rig
        if offsets and isinstance(offsets[i], Matrix):
            obj.matrix_basis = offsets[i]
        elif offsets:
            obj.location = offsets[i]
        else:
            obj.location = obj["pivot"]
            obj.location = (0, 0, 0)
    to_blender = lambda p: Vector((p[0], -p[2], p[1]))
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = lens
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = to_blender(camera_at)
    direction = to_blender(look_at) - cam.location
    cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam
    for name, loc, energy in (("key", (2.5, 3.0, 3.0), 120), ("rim", (-2.5, -2.0, 2.5), 90), ("fill", (-2.0, 3.0, 1.0), 25)):
        light = bpy.data.lights.new(name, 'AREA')
        light.energy = energy
        light.size = 2.0
        lo = bpy.data.objects.new(name, light)
        scene.collection.objects.link(lo)
        lo.location = to_blender(loc)
        lo.rotation_euler = (to_blender(look_at) - lo.location).to_track_quat('-Z', 'Y').to_euler()
    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.025, 0.035, 1)
    scene.world = world
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 48
    scene.cycles.use_denoising = False
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for obj in list(scene.objects):
        if obj.type in ('CAMERA', 'LIGHT', 'EMPTY'):
            bpy.data.objects.remove(obj)


# ---------------------------------------------------------------------------- assembled guns, for checking

def gun_layout(p, att):
    """The weapon builder's layout (Client/Weapons/ViewModelBuilder.cs), for previews: (mesh, position, size, x rotation)."""
    b, length = p["bulk"], p["body"]
    out = []
    top, front = 0.0375 * b, length * 0.5
    out.append(("Receiver", (0, 0, 0), (0.055 * b, 0.075 * b, length), 0))
    handguard = p["barrel"] * 0.55
    exposed = p["barrel"] * 0.45
    barrel_y = 0.008 * b
    if handguard > 0.01:
        out.append(("Handguard", (0, 0.004 * b, front + handguard * 0.5), (0.046 * b, 0.052 * b, handguard), 0))
        out.append(("Box", (0, 0.004 * b + 0.027 * b, front + handguard * 0.5), (0.03 * b, 0.004, handguard * 0.6), 0))
    if exposed > 0.01:
        out.append(("Barrel", (0, barrel_y, front + handguard + exposed * 0.5), (0.022 * b, 0.022 * b, exposed), 0))
    muzzle = front + handguard + exposed
    if att.get("barrel") == "suppressor":
        out.append(("Suppressor", (0, barrel_y, muzzle + 0.07), (0.04, 0.04, 0.14), 0))
    elif att.get("barrel") == "muzzle":
        out.append(("MuzzleDevice", (0, barrel_y, muzzle + 0.02), (0.034, 0.034, 0.04), 0))
    if p["stock"] > 0.01:
        size = (0.045 * b, 0.065 * b, p["stock"])
        out.append(("Stock", (0, -0.012 * b, -front - size[2] * 0.5), size, 0))
    out.append(("Grip", (0, -0.075 * b, -length * 0.28), (0.034 * b, 0.09, 0.045), 18))
    if p["mag"] > 0.01:
        if att.get("mag") == "drum":
            out.append(("Drum", (0, -top - 0.05, length * 0.12), (0.085, 0.09, 0.075), 0))
        else:
            out.append(("Magazine", (0, -top - p["mag"] * 0.5, length * 0.12), (0.034 * b, p["mag"], 0.06), -8))
    under_y, under_z = 0.004 * b - 0.026 * b, front + max(handguard, 0.04) * 0.5
    if att.get("grip") == "vertical":
        out.append(("VerticalGrip", (0, under_y - 0.04, under_z), (0.028, 0.08, 0.03), 0))
    sight_z = -length * 0.05
    if att.get("sight") in ("reddot", "holo"):
        w, h, d = (0.034, 0.028, 0.05) if att["sight"] == "reddot" else (0.046, 0.034, 0.07)
        frame = (w + 0.01, 0.012 + h + 0.005, d)
        out.append(("SightFrame", (0, top + frame[1] * 0.5, sight_z), frame, 0))
    elif att.get("sight") == "scope":
        out.append(("ScopeMount", (0, top + 0.006, sight_z), (0.02, 0.012, 0.12), 0))
        out.append(("Scope", (0, top + 0.037, sight_z), (0.05, 0.05, 0.26), 0))
    else:
        out.append(("Post", (-0.012, top + 0.01, -length * 0.3), (0.007, 0.02, 0.012), 0))
        out.append(("Post", (0.012, top + 0.01, -length * 0.3), (0.007, 0.02, 0.012), 0))
        out.append(("Post", (0, top + 0.01, front + handguard - 0.02), (0.005, 0.02, 0.005), 0))
    return out


PREVIEW_GUNS = [
    (dict(bulk=1.0, body=0.3, barrel=0.3, stock=0.2, mag=0.14), dict(sight="reddot", barrel="suppressor", grip="vertical")),
    (dict(bulk=0.95, body=0.26, barrel=0.18, stock=0.16, mag=0.13), dict(sight="holo")),
    (dict(bulk=1.05, body=0.34, barrel=0.55, stock=0.26, mag=0.07), dict(sight="scope", barrel="muzzle")),
    (dict(bulk=1.15, body=0.3, barrel=0.42, stock=0.2, mag=0.0), dict()),
    (dict(bulk=1.35, body=0.36, barrel=0.4, stock=0.22, mag=0.12), dict(mag="drum")),
    (dict(bulk=0.88, body=0.16, barrel=0.1, stock=0.0, mag=0.0), dict()),
]


def preview_guns(part_objects, path):
    meshes = {o.name: o.data for o in part_objects}
    shown = []
    for row, (profile, att) in enumerate(PREVIEW_GUNS):
        for name, pos, size, rot_x in gun_layout(profile, att):
            obj = bpy.data.objects.new(name + "_shown", meshes[name])
            bpy.context.scene.collection.objects.link(obj)
            obj["pivot"] = [0, 0, 0]
            obj.location = (pos[0], pos[1] - row * 0.26, pos[2] + (0.25 if row % 2 else -0.25) * 0)
            obj.rotation_euler = (math.radians(rot_x), 0, 0)
            obj.scale = size
            shown.append(obj)
    preview(shown, path, (2.6, -0.62, 0.3), (0, -0.62, 0.12), lens=55, size=(1300, 1600),
            offsets=[o.location.copy() for o in shown])


# ---------------------------------------------------------------------------- the menu's backdrop

def material(name, colour, roughness=0.45, metallic=0.0, emission=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = colour
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if emission > 0:
        bsdf.inputs["Emission Color"].default_value = colour
        bsdf.inputs["Emission Strength"].default_value = emission
    return mat


# The face's and eyes' textures, once build_soldier() has made them.
TEXTURES = {}


def textured(name, path, tint, roughness, subsurface=0.0):
    """A material from an image, multiplied by a tint (as the game does with a skin tone)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    image = nt.nodes.new("ShaderNodeTexImage")
    image.image = bpy.data.images.load(path, check_existing=True)
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    mix.inputs[0].default_value = 1.0
    mix.inputs[7].default_value = tint
    nt.links.new(image.outputs[0], mix.inputs[6])
    nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = roughness
    if subsurface > 0:
        bsdf.inputs["Subsurface Weight"].default_value = subsurface
        bsdf.inputs["Subsurface Scale"].default_value = 0.003
    return mat


def zone_set(prefix, uniform, gear, team, skin, hair=(0.05, 0.035, 0.025, 1)):
    """One soldier's materials, in zone order. The skin is the baked face texture in this tone."""
    if "skin" in TEXTURES:
        skin_mat = textured(prefix + "skin", TEXTURES["skin"], tuple(c / 0.75 for c in skin[:3]) + (1,), 0.5, 0.05)
        eye_mat = textured(prefix + "eye", TEXTURES["eye"], (1, 1, 1, 1), 0.08)
    else:
        skin_mat = material(prefix + "skin", skin, 0.5)
        eye_mat = material(prefix + "eye", (0.85, 0.84, 0.8, 1), 0.15)
    return [
        material(prefix + "uniform", uniform, 0.85),
        material(prefix + "dark", (0.03, 0.032, 0.035, 1), 0.7),
        material(prefix + "metal", (0.5, 0.52, 0.55, 1), 0.3, 0.9),
        material(prefix + "glow", (0.1, 0.85, 1.0, 1), 0.3, 0.0, 6.0),
        material(prefix + "gear", gear, 0.75, 0.0),
        material(prefix + "team", team, 0.7, 0.0),
        material(prefix + "helmet", gear, 0.6, 0.0),
        skin_mat,
        material(prefix + "hair", hair, 0.7),
        eye_mat,
        material(prefix + "iris", (0.08, 0.05, 0.03, 1), 0.1),
        material(prefix + "lips", tuple(c * 0.82 for c in skin[:3]) + (1,), 0.45),
        material(prefix + "boots", (0.09, 0.07, 0.05, 1), 0.55),
    ]


def soldier_pieces(skinned):
    """The skinned objects with their weights, for posing: [(object, None, weights)]."""
    import outfit
    return [(obj, None, outfit.weights_of(obj)) for _, objects in skinned for obj in objects]


def dress(objects, zones):
    for obj in objects:
        if len(obj.data.materials) == 0:
            for m in zones:
                obj.data.materials.append(m)


def render_backdrop(path, samples=160):
    """The art behind the main menu: soldiers in a dark arena, lit from behind, on the right of the frame."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    import tempfile
    skinned, fp_arms, gear = build_soldier(tempfile.mkdtemp())
    pieces = soldier_pieces(skinned)
    gun_objects = [p.to_object() for p in gun_parts()]
    for obj in [o for o, _, _ in pieces] + fp_arms + gear + gun_objects:
        obj.hide_render = True

    gun_set = [material("gun_" + n, c, r, m, e) for n, c, r, m, e in (
        ("body", (0.06, 0.065, 0.07, 1), 0.38, 0.3, 0), ("dark", (0.025, 0.027, 0.03, 1), 0.5, 0.1, 0),
        ("metal", (0.45, 0.46, 0.48, 1), 0.3, 0.9, 0), ("glow", (0.9, 0.3, 0.1, 1), 0.3, 0, 3.0),
        ("trim", (0.3, 0.3, 0.3, 1), 0.4, 0, 0), ("team", (0.3, 0.3, 0.3, 1), 0.4, 0, 0), ("helm", (0.3, 0.3, 0.3, 1), 0.4, 0, 0))]
    for obj in gun_objects:
        for m in gun_set:
            obj.data.materials.append(m)

    rifle = (dict(bulk=1.0, body=0.3, barrel=0.3, stock=0.2, mag=0.14), dict(sight="reddot", grip="vertical", barrel="suppressor"))
    marksman = (dict(bulk=1.05, body=0.34, barrel=0.5, stock=0.24, mag=0.08), dict(sight="scope", barrel="muzzle"))
    lmg = (dict(bulk=1.3, body=0.36, barrel=0.4, stock=0.22, mag=0.12), dict(mag="drum"))
    blue = (0.15, 0.35, 0.8, 1)
    figures = [
        (rifle, dict(speed=0, phase=0, pitch=4), (1.15, 0, 0.95), -38, "Helmet", "AssaultPack",
         zone_set("a_", (0.2, 0.23, 0.16, 1), (0.36, 0.31, 0.22, 1), blue, (0.62, 0.42, 0.31, 1))),
        (marksman, dict(speed=5.2, phase=2.2, pitch=2), (2.45, 0, -2.4), -24, ["Cap", "Headset"], "RadioPack",
         zone_set("b_", (0.32, 0.3, 0.26, 1), (0.13, 0.14, 0.12, 1), blue, (0.35, 0.22, 0.15, 1))),
        (lmg, dict(speed=0, phase=0, pitch=10, stance="crouch"), (0.75, 0, -3.3), -8, ["Helmet", "HelmetHeadset"], None,
         zone_set("c_", (0.12, 0.13, 0.15, 1), (0.2, 0.21, 0.19, 1), blue, (0.8, 0.62, 0.5, 1))),
    ]
    shown = []
    for i, (gun, motion, origin, yaw, headgear, back, zones) in enumerate(figures):
        made = posed_soldier(pieces, gear, motion, gun, gun_objects, origin=origin, yaw=yaw, headgear=headgear, back=back, tag="_%d" % i)
        dress([o for o in made if "_held" not in o.name], zones)
        shown += made

    # The arena: a glossy floor, dark blocks and pillars with strips of light.
    env = Part("Arena")
    env.box((0, -0.05, -4), (40, 0.1, 40), "dark")
    for x, z, w, h, d in ((-3.2, -5.5, 2.2, 3.4, 1.6), (4.6, -5.0, 1.4, 5.0, 1.4), (1.2, -8.0, 6.0, 2.2, 1.2),
                          (-6.5, -3.0, 1.2, 4.2, 1.2), (6.5, -2.0, 2.4, 1.2, 2.0), (-1.8, -1.2, 1.6, 0.9, 1.0)):
        env.box((x, h / 2, z), (w, h, d), "primary", bevel=0.04)
        env.box((x, h - 0.12, z + d / 2 + 0.005), (w * 0.8, 0.035, 0.01), "glow")
    for x in (-9, -4.5, 0, 4.5, 9):
        env.box((x, 4.5, -12), (0.6, 9, 0.6), "primary", bevel=0.05)
    env.box((0, 4.5, -12.4), (30, 9, 0.2), "primary")
    env.box((0, 7.2, -12.25), (26, 0.05, 0.05), "glow")
    arena = env.to_object()
    arena["pivot"] = [0, 0, 0]
    for m in (material("floor", (0.05, 0.055, 0.065, 1), 0.22, 0.2), material("floor_dark", (0.03, 0.033, 0.04, 1), 0.3),
              material("wall_metal", (0.4, 0.4, 0.42, 1), 0.3, 0.9), material("strip", (0.1, 0.8, 1.0, 1), 0.3, 0, 12.0)):
        arena.data.materials.append(m)
    # Zone 0 is the blocks, zone 1 the floor: swap them so the floor is the glossy one.
    arena.data.materials[0], arena.data.materials[1] = arena.data.materials[1], arena.data.materials[0]
    shown.append(arena)

    rig = bpy.data.objects.new("Rig", None)
    scene.collection.objects.link(rig)
    rig.matrix_world = Matrix.Rotation(math.radians(90), 4, 'X')
    for obj in shown:
        world = obj.matrix_world.copy()
        obj.parent = rig
        obj.matrix_basis = world
    to_blender = lambda p: Vector((p[0], -p[2], p[1]))

    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 30
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = to_blender((-0.9, 0.95, 3.7))
    cam.rotation_euler = (to_blender((1.25, 1.2, -0.2)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam

    def lamp(name, kind, at, look, energy, colour, size=1.0, spot=None):
        data = bpy.data.lights.new(name, kind)
        data.energy = energy
        data.color = colour
        if kind == 'AREA':
            data.size = size
        if kind == 'SPOT':
            data.spot_size = math.radians(spot or 45)
            data.spot_blend = 0.6
        obj = bpy.data.objects.new(name, data)
        scene.collection.objects.link(obj)
        obj.location = to_blender(at)
        obj.rotation_euler = (to_blender(look) - obj.location).to_track_quat('-Z', 'Y').to_euler()

    lamp("rim_cyan", 'SPOT', (2.5, 4.0, -6.0), (1.0, 1.0, 0.0), 2600, (0.25, 0.8, 1.0), spot=55)
    lamp("rim_warm", 'SPOT', (-3.5, 3.5, -5.0), (0.5, 1.0, 0.0), 1500, (1.0, 0.55, 0.25), spot=50)
    lamp("key", 'AREA', (-1.0, 2.6, 3.5), (0.9, 1.2, 0.0), 160, (1.0, 0.92, 0.85), size=3.0)
    lamp("fill", 'AREA', (4.0, 1.5, 2.0), (1.0, 1.0, 0.0), 40, (0.5, 0.7, 1.0), size=3.0)

    world = bpy.data.worlds.new("w")
    world.use_nodes = True
    nodes = world.node_tree.nodes
    nodes["Background"].inputs[0].default_value = (0.006, 0.008, 0.012, 1)
    # A thin haze, so the lights draw beams.
    volume = nodes.new("ShaderNodeVolumePrincipled")
    volume.inputs["Density"].default_value = 0.018
    volume.inputs["Anisotropy"].default_value = 0.35
    world.node_tree.links.new(volume.outputs[0], nodes["World Output"].inputs["Volume"])
    scene.world = world

    scene.render.engine = 'CYCLES'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    scene.cycles.volume_step_rate = 4.0
    scene.cycles.max_bounces = 6
    scene.render.resolution_x, scene.render.resolution_y = 2048, 1024
    scene.render.filepath = path
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'AgX - Punchy'
    bpy.ops.render.render(write_still=True)


# ---------------------------------------------------------------------------- main

def preview_projectiles(objects, path):
    """Every projectile side by side, larger ones further back, lit and coloured."""
    colours = {0: (0.62, 0.18, 0.08, 1), 1: (0.04, 0.04, 0.045, 1), 2: (0.6, 0.6, 0.62, 1), 3: (1.0, 0.75, 0.3, 1),
               4: (0.9, 0.55, 0.12, 1)}
    mats = [material("pp_%d" % i, colours.get(i, (0.5, 0.5, 0.5, 1)), 0.35, 0.85 if i == 2 else 0.1, 6.0 if i == 3 else 0.0)
            for i in range(13)]
    offsets = []
    columns = 5
    for i, obj in enumerate(objects):
        for m in mats:
            obj.data.materials.append(m)
        x = (i % columns - (columns - 1) / 2) * 0.24
        y = -(i // columns) * 0.2
        # Side on, pointing right, so a projectile's length shows.
        offsets.append(Matrix.Translation((x, y, 0)) @ Matrix.Rotation(math.radians(90), 4, 'Y') @ Matrix.Rotation(math.radians(-20), 4, 'X'))
    preview(objects, path, (0, -0.2, 1.55), (0, -0.2, 0), lens=50, size=(1400, 900), offsets=offsets)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[argv.index("--out") + 1]
    preview_dir = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    if "--backdrop" in argv:
        render_backdrop(argv[argv.index("--backdrop") + 1], int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 160)
        return
    os.makedirs(out, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    if "--projectiles" in argv:
        # Only the projectiles, for working on them without rebuilding the soldier.
        projectile_objects = [p.to_object() for p in projectile_models()]
        export(projectile_objects, os.path.join(out, "Projectiles.bytes"))
        if preview_dir:
            os.makedirs(preview_dir, exist_ok=True)
            preview_projectiles(projectile_objects, os.path.join(preview_dir, "projectiles.png"))
        return
    skinned, fp_arms, gear = build_soldier(out)
    export_skinned(os.path.join(out, "Soldier.bytes"), skinned, fp_arms)
    export(gear, os.path.join(out, "Gear.bytes"))
    pieces = soldier_pieces(skinned)
    gun_objects = [p.to_object() for p in gun_parts()]
    export(gun_objects, os.path.join(out, "GunParts.bytes"))
    projectile_objects = [p.to_object() for p in projectile_models()]
    export(projectile_objects, os.path.join(out, "Projectiles.bytes"))
    if not preview_dir:
        return

    os.makedirs(preview_dir, exist_ok=True)
    for obj in [o for o, _, _ in pieces] + fp_arms + gear + gun_objects + projectile_objects:
        obj.hide_render = True
    zones = zone_set("p_", PREVIEW_COLOURS[0], PREVIEW_COLOURS[4], PREVIEW_COLOURS[5], PREVIEW_COLOURS[7])
    gun_set = [material("pg_%d" % i, c, 0.4, 0.8 if i == 2 else 0.2) for i, c in sorted(PREVIEW_COLOURS.items())]
    for obj in gun_objects:
        for m in gun_set:
            obj.data.materials.append(m)
    rifle = (dict(bulk=1.0, body=0.3, barrel=0.3, stock=0.2, mag=0.14), dict(sight="reddot", grip="vertical"))

    def shot(name, made, camera, look, lens=50, size=(900, 1100)):
        dress([o for o in made if "_held" not in o.name], zones)
        preview(made, os.path.join(preview_dir, name), camera, look, lens=lens, size=size, offsets=[o.matrix_world.copy() for o in made])
        for o in made:
            o.hide_render = True

    rest = dict(speed=0, phase=0, pitch=0)
    shot("soldier_front.png", posed_soldier(pieces, gear, rest, headgear="Helmet", back="AssaultPack", tag="_f"), (1.3, 1.25, 2.6), (0, 0.95, 0), lens=55)
    shot("soldier_back.png", posed_soldier(pieces, gear, rest, headgear="Helmet", back="AssaultPack", tag="_b"), (-1.6, 1.4, -2.2), (0, 0.95, 0), lens=55)
    shot("head.png", posed_soldier(pieces, gear, rest, headgear="Hair", tag="_h"), (0.3, 1.7, 0.85), (0, 1.63, 0.05), lens=60, size=(800, 800))
    made = posed_soldier(pieces, gear, dict(speed=0, phase=0, pitch=5), rifle, gun_objects, origin=(-0.5, 0, 0), tag="_p1")
    made += posed_soldier(pieces, gear, dict(speed=5.6, phase=0.9, pitch=-5), rifle, gun_objects, origin=(0.6, 0, -0.4), headgear=["Cap", "Headset"], back="RadioPack", tag="_p2")
    shot("soldier_posed.png", made, (1.6, 1.45, 3.3), (0.05, 1.0, -0.2), lens=45, size=(1400, 1000))
    lineup = []
    for i, (hg, back) in enumerate((("Hair", None), ("Helmet", None), ("Cap", "HydrationPack"), ("Beanie", "Rucksack"),
                                     (["Hair", "Headset"], "BedrollPack"), ("Boonie", "Scarf"), (["Helmet", "HelmetHeadset"], "RadioPack"), (["Hair", "Bandana"], None))):
        lineup += posed_soldier(pieces, gear, rest, origin=((i - 3.5) * 0.75, 0, 0), yaw=180 if i % 2 else 0, headgear=hg, back=back, tag="_l%d" % i)
    shot("lineup.png", lineup, (0, 1.5, 6.5), (0, 1.0, 0), lens=40, size=(1600, 800))

main()
