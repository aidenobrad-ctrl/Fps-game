"""
Recoil's character and weapon models, built in Blender from code.

    blender -b --python art/blender/recoil_models.py -- --out game/Assets/_Project/Resources/Models [--preview DIR]

Everything is authored directly in the game's frame (x right, y up, z forward, metres), so
the exporter writes positions as they are and only flips the winding of each triangle for
Unity's left-handed space. Each model is split into zones (material slots) that the game
colours at run time: a player's suit, trim and visor colours, team colours on the shoulders,
and a weapon skin's colours on a gun.

Two files come out:

  Soldier.bytes   the armoured operator, as rigid segments (pelvis, torso, head, arms, legs)
                  each modelled around its own joint, for the game to pose and animate;
  GunParts.bytes  detailed parts for the weapon builder (receiver, handguard, barrel,
                  suppressor, stock, grip, magazines, sights, launcher and blade parts), each
                  modelled to fill a unit box so the builder can stretch it to any weapon's
                  proportions.

The format is described in Client/Visuals/ModelLibrary.cs, which reads it.
"""
import bpy, bmesh, math, os, struct, sys
from mathutils import Matrix, Vector

ZONES = {"primary": 0, "dark": 1, "metal": 2, "glow": 3, "trim": 4, "team": 5, "helmet": 6}
PREVIEW_COLOURS = {
    0: (0.18, 0.32, 0.42, 1), 1: (0.05, 0.055, 0.06, 1), 2: (0.45, 0.46, 0.48, 1), 3: (0.1, 0.9, 1.0, 1),
    4: (0.75, 0.62, 0.3, 1), 5: (0.9, 0.2, 0.15, 1), 6: (0.12, 0.2, 0.26, 1),
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

    def to_object(self):
        mesh = bpy.data.meshes.new(self.name)
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        self.bm.to_mesh(mesh)
        self.bm.free()
        for poly in mesh.polygons:
            poly.use_smooth = True
        mesh.use_auto_smooth = True
        mesh.auto_smooth_angle = math.radians(38)
        obj = bpy.data.objects.new(self.name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj["pivot"] = list(self.pivot)
        return obj


def euler(rot):
    rx, ry, rz = (math.radians(a) for a in rot)
    return (Matrix.Rotation(ry, 4, 'Y') @ Matrix.Rotation(rx, 4, 'X') @ Matrix.Rotation(rz, 4, 'Z'))


def mirror_x(p):
    return (-p[0], p[1], p[2])


# ---------------------------------------------------------------------------- the soldier

def soldier():
    """The armoured operator, one Part per rigid segment. Left is -x."""
    parts = []

    # Head: helmet shell, wraparound visor, a rebreather and ear cups.
    head = Part("Head", (0, 1.50, 0))
    head.cylinder((0, 1.47, -0.01), (0, 1.6, 0.0), 0.08, 0.07, "dark", segments=16)
    head.cylinder((0, 1.49, -0.01), (0, 1.55, -0.01), 0.098, 0.085, "dark", segments=20, bevel=0.012)
    head.sphere((0, 1.662, -0.004), 0.138, "helmet", scale=(1.0, 0.96, 1.1), u=32, v=18)
    head.cylinder((0, 1.588, -0.006), (0, 1.622, -0.006), 0.146, 0.143, "dark", segments=32, bevel=0.01)
    head.box((0, 1.666, 0.108), (0.25, 0.08, 0.075), "metal", bevel=0.022, segments=3)
    head.box((0, 1.668, 0.135), (0.215, 0.05, 0.04), "glow", bevel=0.012, segments=2)
    head.box((0, 1.58, 0.102), (0.12, 0.075, 0.08), "metal", bevel=0.024, segments=3)
    for s in (-1, 1):
        head.cylinder((s * 0.068, 1.575, 0.115), (s * 0.085, 1.565, 0.135), 0.024, 0.022, "dark", segments=12, bevel=0.004)
        head.cylinder((s * 0.122, 1.652, 0.0), (s * 0.158, 1.652, 0.0), 0.05, 0.046, "dark", segments=16, bevel=0.008)
        head.box((s * 0.162, 1.652, 0.0), (0.012, 0.03, 0.03), "glow" if s > 0 else "metal", bevel=0.004)
    head.box((0, 1.792, -0.02), (0.04, 0.03, 0.2), "trim", bevel=0.012, segments=2)
    parts.append(head)

    # Torso: under-suit, chest plate and its overlay, magazine pouches, back plate, collar, shoulder pads.
    torso = Part("Torso", (0, 1.02, 0))
    torso.box((0, 1.13, 0), (0.26, 0.24, 0.19), "dark", bevel=0.05, segments=3, taper=(1.15, 1.05))
    for y, w in ((1.06, 0.27), (1.11, 0.285), (1.16, 0.3)):
        torso.box((0, y, 0.005), (w, 0.022, 0.2), "dark", bevel=0.009)
    torso.box((0, 1.315, 0.006), (0.36, 0.31, 0.25), "primary", bevel=0.06, segments=3, taper=(1.18, 0.95))
    torso.box((0, 1.34, 0.128), (0.32, 0.2, 0.045), "primary", bevel=0.018, segments=2)
    torso.box((0, 1.305, -0.137), (0.36, 0.3, 0.05), "primary", bevel=0.018, segments=2)
    for x in (-0.088, 0.0, 0.088):
        torso.box((x, 1.2, 0.155), (0.076, 0.1, 0.05), "dark", bevel=0.012, segments=2)
        torso.box((x, 1.255, 0.158), (0.08, 0.026, 0.056), "trim", bevel=0.008)
    torso.box((0.078, 1.41, 0.153), (0.11, 0.008, 0.008), "glow")
    torso.cylinder((0, 1.44, -0.008), (0, 1.535, -0.008), 0.122, 0.104, "dark", segments=24, bevel=0.014)
    for s in (-1, 1):
        torso.box((s * 0.235, 1.448, 0), (0.14, 0.05, 0.18), "team", bevel=0.02, segments=2, rot=(0, 0, -s * 24))
        torso.box((s * 0.19, 1.29, 0), (0.03, 0.22, 0.2), "dark", bevel=0.01)
        torso.box((s * 0.12, 1.42, 0.12), (0.035, 0.12, 0.012), "dark", bevel=0.004)
    parts.append(torso)

    # Pelvis: belt and buckle, hips, hanging side plates, a pouch at the back.
    pelvis = Part("Pelvis", (0, 0.96, 0))
    pelvis.box((0, 0.985, 0), (0.335, 0.07, 0.225), "dark", bevel=0.025, segments=2)
    pelvis.box((0, 0.985, 0.116), (0.06, 0.044, 0.02), "metal", bevel=0.006)
    pelvis.box((0, 0.9, 0), (0.3, 0.14, 0.2), "primary", bevel=0.045, segments=3, taper_bottom=(0.82, 0.9))
    for s in (-1, 1):
        pelvis.box((s * 0.166, 0.9, 0.0), (0.03, 0.15, 0.15), "trim", bevel=0.012, rot=(0, 0, s * -6))
    pelvis.box((0, 0.97, -0.13), (0.14, 0.08, 0.06), "dark", bevel=0.015)
    parts.append(pelvis)

    for side, s in (("L", -1), ("R", 1)):
        hip = (s * 0.105, 0.93, 0)
        thigh = Part("Thigh" + side, hip)
        thigh.cylinder((s * 0.108, 0.95, 0), (s * 0.112, 0.52, 0.005), 0.086, 0.064, "primary", segments=16, bevel=0.012)
        thigh.box((s * 0.112, 0.79, 0.07), (0.1, 0.15, 0.026), "trim", bevel=0.011, segments=2, rot=(-6, 0, 0), taper_bottom=(0.8, 1.0))
        if s > 0:
            thigh.box((0.185, 0.75, 0.0), (0.05, 0.14, 0.12), "dark", bevel=0.015)
            thigh.box((0.205, 0.72, 0.0), (0.012, 0.05, 0.05), "metal", bevel=0.003)
        else:
            thigh.box((-0.175, 0.8, 0.0), (0.022, 0.05, 0.13), "dark", bevel=0.005)
        parts.append(thigh)

        knee = (s * 0.11, 0.5, 0.01)
        shin = Part("Shin" + side, knee)
        shin.box((s * 0.11, 0.5, 0.075), (0.12, 0.11, 0.06), "trim", bevel=0.026, segments=3)
        shin.cylinder((s * 0.11, 0.49, 0.005), (s * 0.115, 0.12, -0.005), 0.062, 0.05, "dark", segments=14, bevel=0.01)
        shin.box((s * 0.112, 0.3, 0.05), (0.1, 0.3, 0.04), "primary", bevel=0.016, segments=2, taper=(1.12, 1.0))
        shin.box((s * 0.115, 0.21, -0.045), (0.09, 0.012, 0.05), "dark", bevel=0.004)
        parts.append(shin)

        ankle = (s * 0.115, 0.09, -0.01)
        boot = Part("Foot" + side, ankle)
        boot.box((s * 0.115, 0.018, 0.035), (0.118, 0.036, 0.29), "dark", bevel=0.012, segments=2)
        boot.box((s * 0.115, 0.088, 0.02), (0.106, 0.12, 0.24), "dark", bevel=0.034, segments=3, taper=(0.92, 0.8))
        boot.box((s * 0.115, 0.056, 0.135), (0.1, 0.05, 0.07), "trim", bevel=0.02, segments=2)
        boot.box((s * 0.115, 0.123, -0.02), (0.113, 0.026, 0.13), "trim", bevel=0.008)
        boot.box((s * 0.115, 0.165, -0.015), (0.098, 0.05, 0.1), "dark", bevel=0.018)
        parts.append(boot)

        shoulder = (s * 0.215, 1.415, 0)
        elbow = (s * 0.235, 1.13, -0.01)
        wrist = (s * 0.24, 0.88, 0.0)
        upper = Part("UpperArm" + side, shoulder)
        upper.cylinder(shoulder, elbow, 0.06, 0.05, "primary", segments=14, bevel=0.012)
        upper.box((s * 0.265, 1.29, 0.0), (0.035, 0.14, 0.085), "trim", bevel=0.012, segments=2)
        upper.box((s * 0.23, 1.2, 0.0), (0.11, 0.018, 0.1), "dark", bevel=0.006)
        parts.append(upper)

        fore = Part("Forearm" + side, elbow)
        fore.sphere(elbow, 0.05, "metal", scale=(1.0, 0.9, 1.0), u=16, v=10)
        fore.cylinder(elbow, wrist, 0.048, 0.04, "primary", segments=14, bevel=0.01)
        fore.box((s * 0.24, 1.0, 0.016), (0.07, 0.13, 0.064), "trim", bevel=0.018, segments=2, taper=(1.1, 1.1))
        fore.box((s * 0.24, 0.92, 0.0), (0.09, 0.02, 0.085), "dark", bevel=0.007)
        fore.box((s * 0.283, 1.02, 0.01), (0.008, 0.06, 0.012), "glow")
        parts.append(fore)

        hand = Part("Hand" + side, wrist)
        hand.box((s * 0.24, 0.835, 0.0), (0.075, 0.09, 0.04), "dark", bevel=0.016, segments=2)
        hand.box((s * 0.24, 0.775, 0.012), (0.072, 0.05, 0.034), "dark", bevel=0.014, segments=2, rot=(18, 0, 0))
        hand.box((s * 0.207, 0.835, 0.028), (0.022, 0.06, 0.024), "dark", bevel=0.009, rot=(-20, 0, s * 15))
        hand.box((s * 0.24, 0.85, -0.022), (0.06, 0.05, 0.008), "metal", bevel=0.003)
        parts.append(hand)

    return parts


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
            for zone in range(7):
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


# ---------------------------------------------------------------------------- posed soldier, for checking the rig

def unity_euler(x, y, z):
    """Unity's Quaternion.Euler(x, y, z) as a matrix: z, then x, then y."""
    return (Matrix.Rotation(math.radians(y), 4, 'Y') @ Matrix.Rotation(math.radians(x), 4, 'X')
            @ Matrix.Rotation(math.radians(z), 4, 'Z'))


def pose_soldier(soldier_objects, gun_objects, motion, gun_profile, gun_att, origin=(0, 0, 0), yaw=0.0, tag=""):
    """
    Poses copies of the soldier's segments the way Client/Visuals/SoldierView.cs does, with an
    assembled gun at the weapon mount and the arms solved to its grips. Returns the new objects.
    """
    by_name = {o.name: o for o in soldier_objects}
    pivot = {n: Vector(o["pivot"]) for n, o in by_name.items()}
    parent = {"Pelvis": None, "Torso": "Pelvis", "Head": "Torso"}
    for side in "LR":
        parent.update({"Thigh" + side: "Pelvis", "Shin" + side: "Thigh" + side, "Foot" + side: "Shin" + side,
                       "UpperArm" + side: "Torso", "Forearm" + side: "UpperArm" + side, "Hand" + side: "Forearm" + side})
    local_pos = {n: pivot[n] - (pivot[parent[n]] if parent[n] else Vector()) for n in parent}
    rot = {n: Matrix.Identity(4) for n in parent}

    def length(a, b):
        return (pivot[b] - pivot[a]).length
    thigh_len, shin_len = length("ThighL", "ShinL"), length("ShinL", "FootL")
    upper_len, fore_len = length("UpperArmL", "ForearmL"), length("ForearmL", "HandL")

    speed, phase, stance = motion["speed"], motion["phase"], motion.get("stance", "stand")
    amplitude = min(speed / 5.6, 1.3)
    drop = 0.0 if stance == "stand" else 0.34
    bob = amplitude * 0.035 * abs(math.cos(phase))
    pelvis_pos = pivot["Pelvis"] - Vector((0, drop + bob, 0))
    reach = max(0.25, min(pivot["Pelvis"].y - 0.03 - drop - bob - 0.09, thigh_len + shin_len - 0.005))
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
        if n in world:
            return world[n]
        base = Matrix.Identity(4) if parent[n] is None else world_of(parent[n])
        lp = pelvis_pos if n == "Pelvis" else local_pos[n]
        world[n] = base @ Matrix.Translation(lp) @ rot[n]
        return world[n]
    for n in parent:
        world_of(n)

    # The gun at the shoulder pocket, turned with the rest of the view's pitch.
    mount = world["Torso"] @ Matrix.Translation((0.13, 0.36, 0.05)) @ unity_euler(view_pitch * 0.6 - lean, 0, 0)
    layout = gun_layout(gun_profile, gun_att)
    b, length_ = gun_profile["bulk"], gun_profile["body"]
    rear = -(length_ * 0.5 + gun_profile["stock"])
    gun_root = mount @ Matrix.Translation((0, 0, -rear - 0.03))
    meshes = {o.name: o.data for o in gun_objects}
    made = []
    for name, pos, size, rot_x in layout:
        obj = bpy.data.objects.new(name + "_held" + tag, meshes[name])
        bpy.context.scene.collection.objects.link(obj)
        obj["pivot"] = [0, 0, 0]
        obj.matrix_world = gun_root @ Matrix.Translation(pos) @ unity_euler(rot_x, 0, 0) @ Matrix.Diagonal((size[0], size[1], size[2], 1))
        made.append(obj)
    grip = gun_root @ Vector((0, -0.075 * b, -length_ * 0.28))
    handguard = gun_profile["barrel"] * 0.55
    support = gun_root @ Vector((0, 0.004 * b - 0.026 * b, length_ * 0.5 + max(handguard, 0.04) * 0.5))
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
        upper_rest = pivot[fore] - pivot[upper]
        fore_rest = pivot[hand] - pivot[fore]
        r_upper = upper_rest.rotation_difference(elbow - shoulder).to_matrix().to_4x4()
        r_fore = fore_rest.rotation_difference(wrist - elbow).to_matrix().to_4x4()
        world[upper] = Matrix.Translation(shoulder) @ r_upper
        world[fore] = Matrix.Translation(elbow) @ r_fore
        world[hand] = Matrix.Translation(wrist) @ r_fore

    reach_arm("R", grip + up * 0.055 - fwd * 0.02, Vector((0.7, -1, -0.3)))
    reach_arm("L", support - up * 0.02 - right * 0.025, Vector((-0.8, -1, -0.1)))

    for n, obj in by_name.items():
        copy = bpy.data.objects.new(n + "_posed" + tag, obj.data.copy())
        bpy.context.scene.collection.objects.link(copy)
        # The segment's mesh is in absolute rest coordinates: take it to its pivot first.
        copy.data.transform(Matrix.Translation(-pivot[n]))
        copy.matrix_world = world[n]
        copy["pivot"] = [0, 0, 0]
        copy["soldier"] = True
        made.append(copy)
    # Then stand the whole figure where it belongs, turned to face its way.
    place = Matrix.Translation(origin) @ Matrix.Rotation(math.radians(yaw), 4, 'Y')
    for obj in made:
        obj.matrix_world = place @ obj.matrix_world
    return made


def preview_posed(soldier_objects, gun_objects, path):
    for obj in soldier_objects + gun_objects:
        obj.hide_render = True
    rifle = (dict(bulk=1.0, body=0.3, barrel=0.3, stock=0.2, mag=0.14), dict(sight="reddot", grip="vertical"))
    shown = pose_soldier(soldier_objects, gun_objects, dict(speed=0, phase=0, pitch=5), *rifle, origin=(-0.5, 0, 0))
    shown += pose_soldier(soldier_objects, gun_objects, dict(speed=5.6, phase=0.9, pitch=-5), *rifle, origin=(0.6, 0, -0.4))
    preview(shown, path, (1.6, 1.45, 3.3), (0.05, 1.0, -0.2), lens=45, size=(1400, 1000),
            offsets=[o.matrix_world.copy() for o in shown])


# ---------------------------------------------------------------------------- first-person arms, for checking

# The same numbers as Client/Weapons/FirstPersonArms.cs, in the weapon's own space.
FP_RIGHT_WRIST = (0.012, 0.0, 0.0)       # added to the grip, then moved up the grip's axis
FP_RIGHT_UP_GRIP = 0.05
FP_RIGHT_ELBOW = (0.4, -0.55, -1.0)      # direction from the wrist back to the elbow
FP_LEFT_WRIST = (-0.035, -0.045, -0.015)  # from the support point
FP_LEFT_FINGERS = (0.55, 0.8, 0.25)
FP_LEFT_ELBOW = (-0.55, -0.45, -1.0)


def fp_arm_matrices(grip, support, b, pivot):
    """World (gun-space) matrices for the forearm and hand of each arm."""
    grip_axis = (unity_euler(18, 0, 0).to_3x3() @ Vector((0, -1, 0))).normalized()
    out = {}
    fore_rest = {s: (pivot["Hand" + s] - pivot["Forearm" + s]) for s in "LR"}
    forearm_len = fore_rest["R"].length

    def arm(side, wrist, fingers, elbow_dir):
        elbow = wrist + Vector(elbow_dir).normalized() * forearm_len
        r_fore = fore_rest[side].rotation_difference(wrist - elbow).to_matrix().to_4x4()
        r_hand = Vector((0, -1, 0)).rotation_difference(Vector(fingers).normalized()).to_matrix().to_4x4()
        out["Forearm" + side] = Matrix.Translation(elbow) @ r_fore
        out["Hand" + side] = Matrix.Translation(wrist) @ r_hand

    right_wrist = Vector(grip) + Vector(FP_RIGHT_WRIST) - grip_axis * FP_RIGHT_UP_GRIP
    arm("R", right_wrist, grip_axis, FP_RIGHT_ELBOW)
    if support is not None:
        arm("L", Vector(support) + Vector(FP_LEFT_WRIST), FP_LEFT_FINGERS, FP_LEFT_ELBOW)
    return out


def preview_first_person(soldier_objects, gun_objects, path):
    for obj in bpy.context.scene.objects:
        obj.hide_render = True
    profile, att = dict(bulk=1.0, body=0.3, barrel=0.3, stock=0.2, mag=0.14), dict(sight="reddot", grip="vertical")
    b, length_ = profile["bulk"], profile["body"]
    hip = Matrix.Translation((0.17, -0.17, 0.3 + length_ * 0.2))
    meshes = {o.name: o.data for o in gun_objects}
    shown = []
    for name, pos, size, rot_x in gun_layout(profile, att):
        obj = bpy.data.objects.new(name + "_fp", meshes[name])
        bpy.context.scene.collection.objects.link(obj)
        obj["pivot"] = [0, 0, 0]
        obj.matrix_world = hip @ Matrix.Translation(pos) @ unity_euler(rot_x, 0, 0) @ Matrix.Diagonal((size[0], size[1], size[2], 1))
        shown.append(obj)
    pivot = {o.name.split(".")[0]: Vector(o["pivot"]) for o in soldier_objects}
    handguard = profile["barrel"] * 0.55
    grip = (0, -0.075 * b, -length_ * 0.28)
    support = (0, 0.004 * b - 0.026 * b, length_ * 0.5 + max(handguard, 0.04) * 0.5)
    for name, m in fp_arm_matrices(grip, support, b, pivot).items():
        source = next(o for o in soldier_objects if o.name.split(".")[0] == name)
        copy = bpy.data.objects.new(name + "_fp", source.data.copy())
        bpy.context.scene.collection.objects.link(copy)
        copy.data.transform(Matrix.Translation(-pivot[name]))
        copy.matrix_world = hip @ m
        copy["pivot"] = [0, 0, 0]
        shown.append(copy)
    # The player's eye at the origin, looking down +z, with the game's 74-degree field of view.
    preview(shown, path, (0, 0, 0), (0, 0, 1), lens=15, size=(1280, 720), offsets=[o.matrix_world.copy() for o in shown])


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


def zone_set(prefix, suit, trim, team, visor, helmet):
    return [
        material(prefix + "suit", suit, 0.42),
        material(prefix + "dark", (0.03, 0.033, 0.037, 1), 0.55),
        material(prefix + "metal", (0.5, 0.52, 0.55, 1), 0.28, 0.9),
        material(prefix + "glow", visor, 0.3, 0.0, 8.0),
        material(prefix + "trim", trim, 0.38, 0.2),
        material(prefix + "team", team, 0.4, 0.0, 0.5),
        material(prefix + "helmet", helmet, 0.3, 0.1),
    ]


def render_backdrop(path, samples=160):
    """The art behind the main menu: soldiers in a dark arena, lit from behind, on the right of the frame."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    soldier_objects = [p.to_object() for p in soldier()]
    gun_objects = [p.to_object() for p in gun_parts()]
    for obj in soldier_objects + gun_objects:
        obj.hide_render = True

    gun_set = [material("gun_" + n, c, r, m, e) for n, c, r, m, e in (
        ("body", (0.06, 0.065, 0.07, 1), 0.38, 0.3, 0), ("dark", (0.025, 0.027, 0.03, 1), 0.5, 0.1, 0),
        ("metal", (0.45, 0.46, 0.48, 1), 0.3, 0.9, 0), ("glow", (0.1, 0.85, 1.0, 1), 0.3, 0, 10.0),
        ("trim", (0.3, 0.3, 0.3, 1), 0.4, 0, 0), ("team", (0.3, 0.3, 0.3, 1), 0.4, 0, 0), ("helm", (0.3, 0.3, 0.3, 1), 0.4, 0, 0))]
    for obj in gun_objects:
        for m in gun_set:
            obj.data.materials.append(m)

    rifle = (dict(bulk=1.0, body=0.3, barrel=0.3, stock=0.2, mag=0.14), dict(sight="reddot", grip="vertical", barrel="suppressor"))
    marksman = (dict(bulk=1.05, body=0.34, barrel=0.5, stock=0.24, mag=0.08), dict(sight="scope", barrel="muzzle"))
    lmg = (dict(bulk=1.3, body=0.36, barrel=0.4, stock=0.22, mag=0.12), dict(mag="drum"))
    figures = [
        (rifle, dict(speed=0, phase=0, pitch=4), (1.15, 0, 0.95), -38, zone_set("a_", (0.14, 0.2, 0.26, 1), (0.85, 0.55, 0.18, 1), (0.2, 0.55, 1.0, 1), (0.15, 0.9, 1.0, 1), (0.08, 0.11, 0.14, 1))),
        (marksman, dict(speed=5.2, phase=2.2, pitch=2), (2.45, 0, -2.4), -24, zone_set("b_", (0.3, 0.31, 0.29, 1), (0.12, 0.6, 0.75, 1), (0.2, 0.55, 1.0, 1), (1.0, 0.55, 0.12, 1), (0.16, 0.17, 0.16, 1))),
        (lmg, dict(speed=0, phase=0, pitch=10, stance="crouch"), (0.75, 0, -3.3), -8, zone_set("c_", (0.32, 0.12, 0.1, 1), (0.85, 0.82, 0.75, 1), (0.2, 0.55, 1.0, 1), (0.15, 0.9, 1.0, 1), (0.18, 0.08, 0.07, 1))),
    ]
    shown = []
    for i, (gun, motion, origin, yaw, zones) in enumerate(figures):
        made = pose_soldier(soldier_objects, gun_objects, motion, *gun, origin=origin, yaw=yaw, tag="_%d" % i)
        for obj in made:
            if obj.get("soldier"):
                for m in zones:
                    obj.data.materials.append(m)
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

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[argv.index("--out") + 1]
    preview_dir = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    if "--backdrop" in argv:
        render_backdrop(argv[argv.index("--backdrop") + 1], int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 160)
        return
    os.makedirs(out, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    soldier_objects = [p.to_object() for p in soldier()]
    export(soldier_objects, os.path.join(out, "Soldier.bytes"))
    if preview_dir:
        os.makedirs(preview_dir, exist_ok=True)
        for obj in soldier_objects:
            obj.location = (0, 0, 0)
        preview(soldier_objects, os.path.join(preview_dir, "soldier_front.png"), (1.3, 1.25, 2.6), (0, 0.95, 0), lens=55)
        preview(soldier_objects, os.path.join(preview_dir, "soldier_back.png"), (-1.6, 1.4, -2.2), (0, 0.95, 0), lens=55)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    gun_objects = [p.to_object() for p in gun_parts()]
    export(gun_objects, os.path.join(out, "GunParts.bytes"))
    if preview_dir:
        # Laid out in rows and columns along z and y, and seen from the right-hand side.
        cols = 6
        offsets = [Vector((0, -(i // cols) * 1.6, ((i % cols) - cols / 2 + 0.5) * 1.6)) for i in range(len(gun_objects))]
        preview(gun_objects, os.path.join(preview_dir, "gun_parts.png"), (11.0, -1.6, 0.0), (0, -1.6, 0), lens=42,
                size=(1500, 900), offsets=offsets)
        for obj in gun_objects:
            obj.hide_render = True
        preview_guns(gun_objects, os.path.join(preview_dir, "guns_assembled.png"))
        # The soldier again, posed by the game's own rules, holding a rifle.
        soldier_again = [p.to_object() for p in soldier()]
        preview_posed(soldier_again, gun_objects, os.path.join(preview_dir, "soldier_posed.png"))
        soldier_fp = [p.to_object() for p in soldier()]
        preview_first_person(soldier_fp, gun_objects, os.path.join(preview_dir, "first_person.png"))

main()
