"""
The soldier's clothes and kit, built on the realistic body from human.py.

Most of the uniform is cut from the body's own surface: a region of it, chosen by a smooth
field over the body (positive inside), lifted off the skin, eased smooth like cloth, given
folds and hemmed. Where the field crosses zero the faces are clipped, so every hem, cuff
and band edge is a clean line rather than the edges of the body's faces. The plate
carrier, its pouches and the belt kit are built as solid shapes fitted to the torso.

Every vertex carries its skin weights as fifteen float attributes, "w0" to "w14", one per
game bone, so smoothing, clipping and extrusion blend them correctly; the exporter keeps
the two largest.

recoil_models.py sets Part and ZONES here before calling dress().
"""
import math
import bpy, bmesh
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

import human
from human import smoothstep, collar_height

Part = None
ZONES = None
BONE_COUNT = 15


# ---------------------------------------------------------------------------- weights

def weight_layers(bm):
    return [bm.verts.layers.float.get("w%d" % b) or bm.verts.layers.float.new("w%d" % b) for b in range(BONE_COUNT)]


def write_weights(vert, layers, mass):
    for b, layer in enumerate(layers):
        vert[layer] = mass.get(b, 0.0)


def set_weights(obj, fn):
    """Gives every vertex of an object weights from fn(position) -> {bone index: weight}."""
    mesh = obj.data
    for b in range(BONE_COUNT):
        if mesh.attributes.get("w%d" % b) is None:
            mesh.attributes.new("w%d" % b, 'FLOAT', 'POINT')
    # Fetched again once all exist: adding an attribute can move the others.
    attrs = [mesh.attributes["w%d" % b] for b in range(BONE_COUNT)]
    for v in mesh.vertices:
        m = fn(v.co)
        for b in range(BONE_COUNT):
            attrs[b].data[v.index].value = m.get(b, 0.0)
    return obj


def rigid(obj, bone):
    return set_weights(obj, lambda co: {bone: 1.0})


def weights_of(obj):
    """Per vertex: (bone, second bone, the second's share), the two largest of the fifteen."""
    mesh = obj.data
    attrs = [mesh.attributes.get("w%d" % b) for b in range(BONE_COUNT)]
    if any(a is None for a in attrs):
        raise ValueError(obj.name + " has no skin weights")
    values = [[a.data[i].value for a in attrs] for i in range(len(mesh.vertices))]
    out = []
    for ws in values:
        ranked = sorted(range(BONE_COUNT), key=lambda b: -ws[b])
        b0, b1 = ranked[0], ranked[1]
        w0, w1 = ws[b0], ws[b1]
        if w1 <= 1e-4 or w0 + w1 <= 0:
            out.append((b0, b0, 0.0))
        else:
            out.append((b0, b1, w1 / (w0 + w1)))
    return out


def mass_of(B, i):
    b0, b1, w1 = B.weights[i]
    m = {b0: 1.0 - w1}
    if w1 > 0:
        m[b1] = m.get(b1, 0.0) + w1
    return m


def mass_near(B, co):
    b0, b1, w1 = B.weights_near(co)
    m = {b0: 1.0 - w1}
    if w1 > 0:
        m[b1] = m.get(b1, 0.0) + w1
    return m


# ---------------------------------------------------------------------------- the body, measured

class Body:
    """The posed body with what the clothes are fitted by: joints, and each vertex's share of arm, leg and head."""

    def __init__(self, B):
        self.B = B
        self.P, self.N = B.posed, B.normals
        n = len(self.P)
        self.arm, self.hand, self.leg, self.head = [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n
        for i in range(n):
            for name, w in B.mass(i).items():
                if name.startswith(("UpperArm", "Forearm", "Hand")):
                    self.arm[i] += w
                if name.startswith("Hand"):
                    self.hand[i] += w
                if name.startswith(("Thigh", "Shin", "Foot")):
                    self.leg[i] += w
                if name == "Head":
                    self.head[i] += w
        self.side = {}
        for side, s in (("L", ".L"), ("R", ".R")):
            J = lambda name: B.joint(name + s)
            j = dict(shoulder=J("upperarm01"), elbow=J("lowerarm01"), wrist=J("wrist"),
                     hip=J("upperleg01"), knee=J("lowerleg01"), ankle=J("foot"),
                     index=J("finger2-1"), little=J("finger5-1"), middle_tip=B.joint("finger3-3" + s, tail=True))
            j["fore"] = (j["wrist"] - j["elbow"]).normalized()
            j["upper"] = (j["elbow"] - j["shoulder"]).normalized()
            j["fore_len"] = (j["wrist"] - j["elbow"]).length
            # The back of the hand: away from the palm.
            across = (j["little"] - j["index"]).normalized()
            along = (j["middle_tip"] - j["wrist"]).normalized()
            palm = across.cross(along).normalized()
            if (j["index"] - j["wrist"]).cross(j["little"] - j["wrist"]).dot(palm) < 0:
                palm = -palm
            j["palm"] = palm
            self.side[side] = j
        # Which way the body's faces point in its BVH.
        loc, nrm, _, _ = B.bvh.ray_cast(Vector((0.0, 1.25, 0.6)), Vector((0, 0, -1)))
        self.outward = 1.0 if nrm.z > 0 else -1.0
        # The body without the arms (and without the head), for fitting what goes round the torso.
        self.torso_bvh = self.bvh(lambda vi: max(self.arm[i] for i in vi) < 0.3 and max(self.head[i] for i in vi) < 0.6)
        self.trunk_bvh = self.bvh(lambda vi: max(self.arm[i] for i in vi) < 0.3)

    def of(self, p):
        return self.side["L" if p.x < 0 else "R"]

    def bvh(self, keep):
        faces = [list(reversed(vi)) for vi, _ in self.B.faces if keep(vi)]
        return BVHTree.FromPolygons([tuple(p) for p in self.P], faces)

    def cast(self, bvh, origin, direction):
        """The first point of the surface a ray meets, and the outward normal there."""
        origin, direction = Vector(origin), Vector(direction).normalized()
        loc, nrm, _, _ = bvh.ray_cast(origin, direction)
        if loc is None:
            return None, None
        if nrm.dot(direction) > 0:
            nrm = -nrm
        return loc, nrm


# ---------------------------------------------------------------------------- garments cut from the body

def garment(body, name, field, offset, zone, smooth=0, hem=0.004, gap=0.003, fold=None, zones=None, push=True, over=(), over_gap=0.003,
            seams=None):
    """
    A piece of cloth over the body: the part of the surface where field(i) >= 0, clipped
    cleanly where it crosses zero, lifted by offset(i) along the normals, smoothed `smooth`
    times (the hem stays put), kept at least `gap` off the skin, given folds (fold(p) moves
    a point along the cloth's normal) and hemmed: its edges turned in by `hem`.
    zones(p) may name a different zone for the faces around a point.

    For the texture bake (textures.py) every vertex also gets "hem", how far it is across
    the cloth from an edge, and "seam", how far from a seam (seams(p), in metres).
    """
    B, P, N = body.B, body.P, body.N
    values = {}

    def F(i):
        if i not in values:
            f = field(i)
            values[i] = f if abs(f) > 1e-7 else 1e-7
        return values[i]

    base = {}

    def at(i):
        if i not in base:
            base[i] = P[i] + N[i] * offset(i)
        return base[i]

    bm = bmesh.new()
    layers = weight_layers(bm)
    made, crossings = {}, {}

    def vert(i):
        if i not in made:
            v = bm.verts.new(at(i))
            write_weights(v, layers, mass_of(B, i))
            made[i] = v
        return made[i]

    def crossing(a, b):
        key = (min(a, b), max(a, b))
        if key not in crossings:
            fa, fb = F(a), F(b)
            t = fa / (fa - fb)
            v = bm.verts.new(at(a).lerp(at(b), t))
            ma, mb = mass_of(B, a), mass_of(B, b)
            write_weights(v, layers, {k: ma.get(k, 0.0) * (1 - t) + mb.get(k, 0.0) * t for k in set(ma) | set(mb)})
            crossings[key] = v
        return crossings[key]

    for vi, _ in B.faces:
        if max(F(i) for i in vi) < 0:
            continue
        poly = []
        n = len(vi)
        for k in range(n):
            a, b = vi[k], vi[(k + 1) % n]
            if F(a) >= 0:
                poly.append(vert(a))
            if (F(a) >= 0) != (F(b) >= 0):
                poly.append(crossing(a, b))
        if len(poly) >= 3 and len(set(poly)) == len(poly):
            try:
                bm.faces.new(list(reversed(poly)))
            except ValueError:
                pass
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    zone_index = ZONES[zone]
    for f in bm.faces:
        f.material_index = zone_index

    # Cloth bridges hollows and does not show the muscles under it.
    if smooth > 0:
        rim = {v for e in bm.edges if e.is_boundary for v in e.verts}
        inner = [v for v in bm.verts if v not in rim]
        for _ in range(smooth):
            bmesh.ops.smooth_vert(bm, verts=inner, factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    if push:
        for v in bm.verts:
            loc, nrm, _, _ = B.bvh.find_nearest(v.co)
            if loc is None:
                continue
            nrm = nrm * body.outward
            signed = (v.co - loc).dot(nrm)
            if signed < gap:
                v.co += nrm * (gap - signed)
    # Layered on other garments: at least over_gap outside each of them.
    for under in over:
        tree = BVHTree.FromObject(under, bpy.context.evaluated_depsgraph_get())
        for v in bm.verts:
            loc, nrm, _, dist = tree.find_nearest(v.co)
            if loc is None or dist > 0.04:
                continue
            nrm = nrm * body.outward
            signed = (v.co - loc).dot(nrm)
            if signed < over_gap:
                v.co += nrm * (over_gap - signed)
    bm.normal_update()
    if fold is not None:
        moves = [(v, v.normal * fold(v.co)) for v in bm.verts]
        for v, d in moves:
            v.co += d
        bm.normal_update()
    distance_from_edges(bm)
    seam_layer = bm.verts.layers.float.new("seam")
    for v in bm.verts:
        v[seam_layer] = seams(v.co) if seams is not None else 1.0
    if hem > 0:
        edges = [e for e in bm.edges if e.is_boundary]
        normals = {v: v.normal.copy() for e in edges for v in e.verts}
        res = bmesh.ops.extrude_edge_only(bm, edges=edges)
        for elem in res["geom"]:
            if isinstance(elem, bmesh.types.BMVert):
                src = next((e.other_vert(elem) for e in elem.link_edges if e.other_vert(elem) in normals), None)
                if src is not None:
                    elem.co = src.co - normals[src] * hem
        for elem in res["geom"]:
            if isinstance(elem, bmesh.types.BMFace):
                elem.material_index = zone_index
    if zones is not None:
        for f in bm.faces:
            z = zones(f.calc_center_median())
            if z:
                f.material_index = ZONES[z]
    return to_object(bm, name)


def distance_from_edges(bm, limit=0.05, crease=None):
    """
    Gives every vertex a "hem" value: how far it is, across the surface, from the nearest
    edge of the cloth (or, with crease set, from the nearest edge sharper than that angle).
    """
    import heapq
    layer = bm.verts.layers.float.get("hem") or bm.verts.layers.float.new("hem")
    bm.verts.index_update()
    if crease is None:
        start = {v for e in bm.edges if e.is_boundary for v in e.verts}
    else:
        start = {v for e in bm.edges if e.is_boundary or (len(e.link_faces) == 2 and e.calc_face_angle() > crease) for v in e.verts}
    best = {v.index: 0.0 for v in start}
    heap = [(0.0, v.index) for v in start]
    verts = list(bm.verts)
    while heap:
        d, i = heapq.heappop(heap)
        if d > best.get(i, limit) or d > limit:
            continue
        v = verts[i]
        for e in v.link_edges:
            w = e.other_vert(v)
            nd = d + e.calc_length()
            if nd < best.get(w.index, limit):
                best[w.index] = nd
                heapq.heappush(heap, (nd, w.index))
    for v in verts:
        v[layer] = best.get(v.index, limit)


def to_object(bm, name, angle=50):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for p in mesh.polygons:
        p.use_smooth = True
    mesh.use_auto_smooth = True
    mesh.auto_smooth_angle = math.radians(angle)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj["pivot"] = [0, 0, 0]
    return obj


def frame(normal):
    """A rotation taking +z to the normal and keeping +y as near to up as it can."""
    z = Vector(normal).normalized()
    x = Vector((0, 1, 0)).cross(z)
    if x.length < 1e-6:
        x = Vector((1, 0, 0))
    x.normalize()
    y = z.cross(x).normalized()
    m = Matrix((x, y, z)).transposed()
    return m.to_4x4()


def around(p, origin, axis):
    """The angle of p about an axis through origin (radians), and its distance along the axis."""
    axis = axis.normalized()
    side = axis.cross(Vector((0, 0, 1)))
    if side.length < 1e-6:
        side = axis.cross(Vector((1, 0, 0)))
    side.normalize()
    up = axis.cross(side)
    r = p - origin
    return math.atan2(r.dot(up), r.dot(side)), r.dot(axis)


# ---------------------------------------------------------------------------- the uniform

CUFF = 0.052          # the sleeve ends this far above the wrist joint
GLOVE = 0.085         # the glove reaches this far above it, under the sleeve
WAIST, TROUSER_TOP, TROUSER_HEM, BOOT_TOP = 0.955, 1.035, 0.172, 0.215


def shirt(body):
    P, S = body.P, body

    def field(i):
        p = P[i]
        j = body.of(p)
        cuff = (j["wrist"] - p).dot(j["fore"]) - CUFF
        waist = p.y - WAIST + 0.6 * S.arm[i]
        # Up to the collar line round the neck; everything further out (the tops of the
        # shoulders) is covered whatever its height.
        neck = max(collar_height(p) - p.y, min(neck_radius(p) - 0.078, 1.52 - p.y))
        return min(cuff, waist, neck)

    def offset(i):
        return 0.0085 - 0.0015 * S.arm[i]

    def fold(p):
        j = body.of(p)
        d = 0.0
        # Sleeves: bunched in the crook of the elbow and above the cuff.
        if p.y < 1.33 and abs(p.x) > 0.17:
            theta, s = around(p, j["elbow"], (j["fore"] + j["upper"]))
            d += 0.0032 * math.exp(-(s / 0.055) ** 2) * math.sin(2 * math.pi * s / 0.03 + 1.6 * math.sin(theta + 0.7))
            c = (j["wrist"] - p).dot(j["fore"]) - CUFF
            d += 0.0025 * math.exp(-(c / 0.045) ** 2) * math.sin(2 * math.pi * c / 0.024 + 1.2 * math.sin(2 * theta))
            # The shoulder seam of the sleeve.
            a = (p - j["shoulder"]).dot(j["upper"])
            d += 0.0012 * math.exp(-((a + 0.005) / 0.008) ** 2)
        # Gathered at the waist under the belt.
        d += 0.0022 * smoothstep(1.07, 0.99, p.y) * math.sin(p.y * 2 * math.pi / 0.03 + p.x * 40 + math.sin(p.z * 60) * 1.5)
        # Creases down from the shoulder blades and across the chest.
        d += 0.0012 * math.sin(p.x * 70 + p.y * 18) * smoothstep(1.15, 1.25, p.y) * (1 - smoothstep(1.38, 1.45, p.y)) * (1 - smoothstep(0.15, 0.19, abs(p.x)))
        return d

    def zones(p):
        j = body.of(p)
        # Pads in the elbows, on the outside of the bend.
        back = j["elbow"] + Vector((0.012 if p.x > 0 else -0.012, 0.0, -0.038))
        return "trim" if (p - back).length < 0.042 else None

    def seams(p):
        j = body.of(p)
        s = 1 if p.x > 0 else -1
        d = 1.0
        # Round the top of each sleeve, where it is sewn to the body.
        if abs(p.x) > 0.12 and p.y > 1.18:
            n = Vector((s * 1.0, 0.45, 0.0)).normalized()
            d = min(d, abs((p - (j["shoulder"] + Vector((-s * 0.012, 0.0, 0.0)))).dot(n)))
        # Down the inside of each sleeve.
        if abs(p.x) > 0.17 and p.y < 1.3:
            a, b = (j["shoulder"], j["elbow"]) if p.y > j["elbow"].y else (j["elbow"], j["wrist"])
            t = max(0.0, min(1.0, (p - a).dot(b - a) / (b - a).length_squared))
            r = p - (a + (b - a) * t)
            if r.x * s < 0:
                d = min(d, abs(r.z))
        # Down each side of the body.
        if 0.1 < abs(p.x) < 0.19 and p.y < 1.3:
            d = min(d, abs(p.z - 0.012))
        # Across the shoulders, front and back of the yoke.
        if abs(p.x) < 0.16 and p.y > 1.36:
            d = min(d, abs(p.y - (1.43 - 0.25 * abs(p.x))) if p.z < 0 else 1.0)
        return d

    return garment(body, "Shirt", field, offset, "primary", smooth=4, hem=0.004, gap=0.004, fold=fold, seams=seams)


def neck_radius(p):
    """How far a point is from the line up the middle of the neck, across."""
    return math.hypot(p.x, (p.z - 0.018) * 0.92)


def collar(body, over=()):
    P, S = body.P, body
    radius = neck_radius

    def field(i):
        p = P[i]
        c = collar_height(p)
        return min(p.y - c + 0.008, c + 0.036 - p.y, 0.088 - radius(p)) - 2 * S.arm[i]

    def offset(i):
        p = P[i]
        c = collar_height(p)
        return 0.0135 + 0.0025 * smoothstep(c, c + 0.036, p.y)

    return garment(body, "Collar", field, offset, "primary", smooth=3, hem=0.004, gap=0.012, over=over, over_gap=0.003)


def sleeve_band(body, name, low, high, off, zone, hem=0.004, over=()):
    """A band round each forearm, from `low` to `high` above the wrist joint."""
    P, S = body.P, body

    def field(i):
        p = P[i]
        j = body.of(p)
        d = (j["wrist"] - p).dot(j["fore"])
        return min(d - low, high - d, S.arm[i] - 0.5)

    return garment(body, name, field, lambda i: off, zone, smooth=1, hem=hem, gap=off * 0.8, over=over, over_gap=0.0025)


def armbands(body, over=()):
    """The team's colour round each upper arm."""
    P, S = body.P, body

    def field(i):
        p = P[i]
        j = body.of(p)
        a = (p - j["shoulder"]).dot(j["upper"])
        return min(a - 0.075, 0.112 - a, S.arm[i] - 0.6)

    return garment(body, "Armbands", field, lambda i: 0.0115, "team", smooth=1, hem=0.003, gap=0.009, over=over, over_gap=0.0025)


def elbow_pads(body, over=()):
    P = body.P

    def centre(p):
        j = body.of(p)
        return j["elbow"] + Vector((0.012 if p.x > 0 else -0.012, 0.0, -0.038))

    def field(i):
        p = P[i]
        return 0.04 - (p - centre(p)).length + 0.5 * min(0.0, body.arm[i] - 0.5)

    def offset(i):
        p = P[i]
        return 0.0085 + 0.0075 * smoothstep(0.04, 0.026, (p - centre(p)).length)

    return garment(body, "ElbowPads", field, offset, "trim", smooth=2, hem=0.006, gap=0.008, over=over, over_gap=0.003)


def trousers(body):
    P, S = body.P, body

    def field(i):
        p = P[i]
        return min(TROUSER_TOP - p.y, p.y - TROUSER_HEM) - 2 * S.arm[i]

    def pocket(p):
        """The cargo pocket on the outside of each thigh: 0 off it, 1 on it."""
        out = abs(p.x)
        return (smoothstep(0.095, 0.112, out) * smoothstep(0.088, 0.074, abs(p.y - 0.665))
                * smoothstep(0.068, 0.054, abs(p.z - 0.004)))

    def offset(i):
        p = P[i]
        blouse = 0.016 * smoothstep(0.29, 0.19, p.y)
        return 0.0085 + 0.0025 * smoothstep(0.9, 0.6, p.y) + blouse

    def fold(p):
        j = body.of(p)
        d = 0.0
        theta, s = around(p, j["ankle"], j["knee"] - j["ankle"])
        # Bloused over the boots: stacked folds.
        d += 0.0055 * smoothstep(0.32, 0.2, p.y) * math.sin(2 * math.pi * p.y / 0.034 + 1.7 * math.sin(theta * 1.0 + 0.4) + 0.8 * math.sin(theta * 3))
        # Creases behind the knee and across the front of it.
        k = p.y - j["knee"].y
        d += 0.0026 * math.exp(-(k / 0.06) ** 2) * math.sin(2 * math.pi * k / 0.026 + 1.4 * math.sin(theta))
        # Long folds down the shin and thigh.
        d += 0.0016 * math.sin(theta * 5 + p.y * 9) * smoothstep(0.25, 0.4, p.y) * (1 - smoothstep(0.85, 0.95, p.y))
        # The cargo pocket.
        d += 0.011 * pocket(p)
        # The seam down the outside of each leg.
        d -= 0.0012 * math.exp(-((abs(p.x) - abs(j["knee"].x) - 0.075) / 0.004) ** 2) * smoothstep(0.2, 0.3, p.y) * (1 - smoothstep(0.9, 1.0, p.y))
        return d

    def seams(p):
        j = body.of(p)
        d = 1.0
        if p.y < 0.93:
            # Down the outside and the inside of each leg: halfway between front and back.
            a, b = (j["hip"], j["knee"]) if p.y > j["knee"].y else (j["knee"], j["ankle"])
            t = max(0.0, min(1.0, (p - a).dot(b - a) / (b - a).length_squared))
            d = min(d, abs(p.z - (a + (b - a) * t).z))
            # The articulated knee: darts above and below it, at the front.
            if p.z > j["knee"].z:
                d = min(d, abs(p.y - (j["knee"].y + 0.075)), abs(p.y - (j["knee"].y - 0.07)))
            # Stitched round the cargo pocket.
            if abs(p.x) > 0.1:
                d = min(d, abs(max(abs(p.y - 0.665) - 0.082, abs(p.z - 0.004) - 0.064)))
        else:
            # The seat, and the fly at the front.
            d = min(d, abs(p.x) if (p.z < -0.02 or (p.z > 0.06 and p.y > 0.87)) else 1.0)
        # The waistband.
        d = min(d, abs(p.y - 0.99))
        return d

    return garment(body, "Trousers", field, offset, "primary", smooth=4, hem=0.005, gap=0.005, fold=fold, seams=seams)


def pocket_flaps(body, over=()):
    P, S = body.P, body

    def field(i):
        p = P[i]
        return min(abs(p.x) - 0.1, 0.06 - abs(p.z - 0.004), 0.048 - abs(p.y - 0.727)) - 2 * S.arm[i]

    def offset(i):
        return 0.0085 + 0.0025 * smoothstep(0.9, 0.6, P[i].y) + 0.017

    return garment(body, "PocketFlaps", field, offset, "primary", smooth=1, hem=0.005, gap=0.012, over=over, over_gap=0.003)


def knee_pads(body, over=()):
    P, S = body.P, body

    def centre(p):
        j = body.of(p)
        return j["knee"] + Vector((0.0, 0.004, 0.058))

    def metric(p):
        r = p - centre(p)
        return math.sqrt(r.x ** 2 + (r.y / 1.3) ** 2 + r.z ** 2)

    def field(i):
        p = P[i]
        return 0.062 - metric(p) - 2 * S.arm[i]

    def offset(i):
        p = P[i]
        return 0.02 + 0.01 * smoothstep(0.062, 0.035, metric(p))

    def fold(p):
        # A ridge across the middle, as on a moulded cap.
        j = body.of(p)
        return 0.003 * math.exp(-((p.y - j["knee"].y - 0.004) / 0.008) ** 2)

    return garment(body, "KneePads", field, offset, "trim", smooth=3, hem=0.011, gap=0.018, fold=fold, over=over, over_gap=0.008)


def knee_straps(body, over=()):
    P, S = body.P, body

    def field(i):
        p = P[i]
        j = body.of(p)
        k = p.y - j["knee"].y
        upper = min(k - 0.036, 0.058 - k)
        lower = min(-0.04 - k, k + 0.062)
        return max(upper, lower) - 2 * S.arm[i]

    return garment(body, "KneeStraps", lambda i: field(i), lambda i: 0.012, "dark", smooth=3, hem=0.004, gap=0.01, over=over, over_gap=0.0025)


def gloves(body):
    P, S = body.P, body

    def field(i):
        p = P[i]
        j = body.of(p)
        return min((p - j["wrist"]).dot(j["fore"]) + GLOVE, S.arm[i] - 0.5)

    def offset(i):
        return 0.0026 + 0.0012 * S.hand[i]

    return garment(body, "Gloves", field, offset, "dark", smooth=1, hem=0.002, gap=0.002)


def convex_hull(points):
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def outline_at(hull, centre, scale, angle):
    """Where a ray from the centre at this angle (measured with the outline scaled to a circle) leaves a convex outline."""
    d = (math.cos(angle) * scale[0], math.sin(angle) * scale[1])
    best = None
    n = len(hull)
    for k in range(n):
        a, b = hull[k], hull[(k + 1) % n]
        ex, ez = b[0] - a[0], b[1] - a[1]
        den = d[0] * ez - d[1] * ex
        if abs(den) < 1e-12:
            continue
        t = ((a[0] - centre[0]) * ez - (a[1] - centre[1]) * ex) / den
        u = ((a[0] - centre[0]) * d[1] - (a[1] - centre[1]) * d[0]) / den
        if t > 0 and -1e-9 <= u <= 1 + 1e-9 and (best is None or t < best):
            best = t
    if best is None:
        best = 0.0
    return (centre[0] + d[0] * best, centre[1] + d[1] * best)


def boots(body):
    """
    Each boot lofted through slices of the foot and ankle: the outline of each slice is the
    convex hull of the body there (so the toes are one toe box and the arch is filled),
    eased out to leather over a sock, smoothed between slices, with a flat bottom.
    """
    B, P = body.B, body.P
    bm = bmesh.new()
    layers = weight_layers(bm)
    edges = set()
    for vi, _ in B.faces:
        for a, b in zip(vi, vi[1:] + vi[:1]):
            if min(P[a].y, P[b].y) < BOOT_TOP + 0.03 and body.arm[a] < 0.5:
                edges.add((min(a, b), max(a, b)))
    heights = [0.03 + (BOOT_TOP - 0.03) * k / 15 for k in range(16)]
    count = 48
    for side in ("L", "R"):
        j = body.side[side]
        mine = [(a, b) for a, b in edges if (P[a].x < 0) == (side == "L")]
        low = [(P[i].x, P[i].z) for e in mine for i in e if P[i].y < 0.045]
        slices = []
        for y in heights:
            # Where the body's surface crosses this height (and, at the bottom, all of the sole).
            pts = []
            for a, b in mine:
                ya, yb = P[a].y, P[b].y
                if (ya - y) * (yb - y) < 0:
                    t = (y - ya) / (yb - ya)
                    pts.append((P[a].x + (P[b].x - P[a].x) * t, P[a].z + (P[b].z - P[a].z) * t))
            if y < 0.045:
                pts += low
            hull = convex_hull(pts)
            cx = sum(p[0] for p in hull) / len(hull)
            cz = sum(p[1] for p in hull) / len(hull)
            wx = max(abs(p[0] - cx) for p in hull)
            wz = max(abs(p[1] - cz) for p in hull)
            slices.append((y, hull, (cx, cz), (wx, wz)))
        rings = []
        for y, hull, c, w in slices:
            ring = []
            for k in range(count):
                a = 2 * math.pi * k / count
                x, z = outline_at(hull, c, w, a)
                # Out from the sock to the leather: more round the toe and heel.
                dx, dz = x - c[0], z - c[1]
                r = math.hypot(dx, dz) or 1.0
                grow = 0.009 + 0.004 * smoothstep(0.12, 0.04, y)
                ring.append(Vector((x + dx / r * grow, y, z + dz / r * grow)))
            rings.append(ring)
        # Ease each ring along the boot, so the slices blend into one surface.
        for _ in range(3):
            eased = [rings[0]]
            for k in range(1, len(rings) - 1):
                eased.append([(rings[k - 1][m] + rings[k][m] * 2 + rings[k + 1][m]) / 4 for m in range(count)])
            eased.append(rings[-1])
            rings = eased
        # Round each ring a little too.
        for k, ring in enumerate(rings):
            rings[k] = [(ring[m - 1] + ring[m] * 2 + ring[(m + 1) % count]) / 4 for m in range(count)]
        # The bottom flat at the sole's top.
        for m in range(count):
            rings[0][m].y = 0.028
        made = []
        for ring in rings:
            row = []
            for p in ring:
                v = bm.verts.new(p)
                write_weights(v, layers, mass_near(B, p))
                row.append(v)
            made.append(row)
        for ra, rb in zip(made, made[1:]):
            for m in range(count):
                n = (m + 1) % count
                bm.faces.new((ra[m], ra[n], rb[n], rb[m]))
        bottom = bm.faces.new(list(reversed(made[0])))
        # A padded collar at the top, turning in.
        top = made[-1]
        inner = []
        for v in top:
            c = Vector((sum(t.co.x for t in top) / count, v.co.y, sum(t.co.z for t in top) / count))
            p = v.co + (c - v.co).normalized() * 0.007 + Vector((0, -0.004, 0))
            w = bm.verts.new(p)
            write_weights(w, layers, mass_near(B, p))
            inner.append(w)
        for m in range(count):
            n = (m + 1) % count
            bm.faces.new((top[m], top[n], inner[n], inner[m]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        f.material_index = ZONES["boots"]
        c = f.calc_center_median()
        j = body.of(c)
        # The tongue and laces up the front.
        if 0.05 < c.y < BOOT_TOP - 0.01 and abs(c.x - j["ankle"].x) < 0.02 and c.z > j["ankle"].z + 0.02 and f.normal.y > -0.2:
            f.material_index = ZONES["dark"]
    return to_object(bm, "Boots", angle=60)


def soles(body, boot):
    """Thick rubber soles, from the outline of each boot near the floor."""
    part = Part("Soles")
    for side in ("L", "R"):
        j = body.side[side]
        pts = [v.co for v in boot.data.vertices if v.co.y < 0.035 and (v.co.x < 0) == (side == "L")]
        cx = sum(p.x for p in pts) / len(pts)
        cz = sum(p.z for p in pts) / len(pts)
        bins = 64
        radius = [0.0] * bins
        for p in pts:
            a = math.atan2(p.z - cz, p.x - cx)
            k = int((a + math.pi) / (2 * math.pi) * bins) % bins
            radius[k] = max(radius[k], math.hypot(p.x - cx, p.z - cz))
        for _ in range(3):
            filled = [r if r > 0 else max(radius[(k - 1) % bins], radius[(k + 1) % bins]) for k, r in enumerate(radius)]
            radius = filled
        smooth = [(radius[(k - 1) % bins] + 2 * radius[k] + radius[(k + 1) % bins]) / 4 for k in range(bins)]
        outline = []
        for k in range(bins):
            a = (k + 0.5) / bins * 2 * math.pi - math.pi
            r = smooth[k] + 0.004
            outline.append((cx + math.cos(a) * r, cz + math.sin(a) * r))
        # The sole, with a toe that lifts a little, and a heel block under the back.
        bm = part.bm
        before = set(bm.verts)
        front = max(z for _, z in outline)
        bottom = [bm.verts.new((x, 0.004 * smoothstep(front - 0.05, front, z), z)) for x, z in outline]
        top = [bm.verts.new((x, 0.031, z)) for x, z in outline]
        faces = [bm.faces.new(list(reversed(bottom))), bm.faces.new(top)]
        for k in range(bins):
            n = (k + 1) % bins
            faces.append(bm.faces.new((bottom[k], bottom[n], top[n], top[k])))
        for f in faces:
            f.material_index = ZONES["dark"]
        new = [v for v in bm.verts if v not in before]
        edges = list({e for v in new for e in v.link_edges if len(e.link_faces) == 2 and e.calc_face_angle() > 0.6})
        bmesh.ops.bevel(bm, geom=edges, offset=0.003, segments=2, affect='EDGES', clamp_overlap=True, material=ZONES["dark"])
    return part


def laces(body, boot):
    """Laces across the tongue of each boot, fitted to it."""
    tree = BVHTree.FromObject(boot, bpy.context.evaluated_depsgraph_get())
    part = Part("Laces")
    for side in ("L", "R"):
        j = body.side[side]
        for k in range(6):
            y = 0.075 + k * 0.022
            loc, nrm, _, _ = tree.ray_cast(Vector((j["ankle"].x, y, 0.4)), Vector((0, 0, -1)))
            if loc is None:
                continue
            before = set(part.bm.verts)
            part.box((0, 0, 0), (0.04, 0.005, 0.004), "dark", bevel=0.0015)
            new = [v for v in part.bm.verts if v not in before]
            tilt = Matrix.Rotation(math.radians(14 if k % 2 else -14), 4, 'Z')
            bmesh.ops.transform(part.bm, matrix=Matrix.Translation(loc + nrm * 0.002) @ frame(nrm) @ tilt, verts=new)
    return part


# ---------------------------------------------------------------------------- the plate carrier

class Plate:
    """
    One plate bag, front or back, as a surface over the chest: curved across, tilted to
    follow the torso, and far enough off it everywhere to clear the shirt.
    """

    def __init__(self, body, front, bottom, top, width, cut=0.055, corner=0.028, thickness=0.032, clear=0.017, curve=0.9):
        self.sign = 1 if front else -1
        self.bottom, self.top, self.width, self.cut, self.corner = bottom, top, width, cut, corner
        self.thickness, self.curve = thickness, curve
        self.mid = (bottom + top) / 2
        rows = []
        for y in [bottom + (top - bottom) * k / 8 for k in range(9)]:
            row = []
            for x in [-width / 2 + width * k / 8 for k in range(9)]:
                loc, _ = body.cast(body.torso_bvh, (x, y, self.sign * 0.6), (0, 0, -self.sign))
                if loc is not None:
                    row.append((x, y, self.sign * loc.z))
            if row:
                rows.append(row)
        # How the torso leans across this height: the best straight line through the deepest points.
        ys = [r[0][1] for r in rows]
        ms = [max(d + curve * x * x for x, _, d in r) for r in rows]
        n = len(ys)
        my, mm = sum(ys) / n, sum(ms) / n
        var = sum((y - my) ** 2 for y in ys)
        self.tilt = max(-0.6, min(0.6, sum((y - my) * (m - mm) for y, m in zip(ys, ms)) / var if var > 0 else 0.0))
        self.depth0 = max(d + curve * x * x - self.tilt * (y - self.mid) for r in rows for x, y, d in r) + clear + thickness

    def half(self, y):
        """Half the bag's width at a height: a shooter's cut at the top corners, rounded bottom corners."""
        h = self.width / 2
        if y > self.top - self.cut:
            h -= (y - (self.top - self.cut))
        r = self.corner
        if y < self.bottom + r:
            dy = self.bottom + r - y
            h -= r - math.sqrt(max(0.0, r * r - dy * dy))
        return h

    def depth(self, x, y):
        """How far forward (or back) the front face of the bag is."""
        return self.depth0 + self.tilt * (y - self.mid) - self.curve * x * x

    def point(self, x, y, out=0.0):
        """A point on the outer face, `out` beyond it, and the outward normal there."""
        e = 1e-3
        z = self.sign * (self.depth(x, y) + out)
        dzx = self.sign * (self.depth(x + e, y) - self.depth(x - e, y)) / (2 * e)
        dzy = self.sign * (self.depth(x, y + e) - self.depth(x, y - e)) / (2 * e)
        n = Vector((-dzx, -dzy, 1.0)) * self.sign
        return Vector((x, y, z)), n.normalized()

    def build(self, part, zone, nu=16, nv=18):
        bm = part.bm
        s = self.sign
        grid_front, grid_back = [], []
        for jv in range(nv + 1):
            y = self.bottom + (self.top - self.bottom) * jv / nv
            h = self.half(y)
            fr, bk = [], []
            for iu in range(nu + 1):
                u = iu / nu * 2 - 1
                x = u * h
                v = (y - self.mid) / ((self.top - self.bottom) / 2)
                puff = 0.005 * (1 - u ** 4) * (1 - v ** 4)
                d = self.depth(x, y)
                fr.append(bm.verts.new((x, y, s * (d + puff))))
                bk.append(bm.verts.new((x, y, s * (d - self.thickness))))
            grid_front.append(fr)
            grid_back.append(bk)
        faces = []
        for jv in range(nv):
            for iu in range(nu):
                a, b = grid_front[jv][iu], grid_front[jv][iu + 1]
                c, d = grid_front[jv + 1][iu + 1], grid_front[jv + 1][iu]
                faces.append(bm.faces.new((a, b, c, d)))
                a, b = grid_back[jv][iu], grid_back[jv][iu + 1]
                c, d = grid_back[jv + 1][iu + 1], grid_back[jv + 1][iu]
                faces.append(bm.faces.new((d, c, b, a)))
        # The edge all round, puffed out like a padded bag.
        ring = [(0, i) for i in range(nu + 1)] + [(j, nu) for j in range(1, nv + 1)] + \
               [(nv, i) for i in range(nu - 1, -1, -1)] + [(j, 0) for j in range(nv - 1, 0, -1)]
        loops = [[grid_front[j][i] for j, i in ring]]
        steps = 3
        for k in range(1, steps + 1):
            t = k / (steps + 1)
            loop = []
            for idx, (j, i) in enumerate(ring):
                f, b = grid_front[j][i].co, grid_back[j][i].co
                prev = grid_front[ring[idx - 1][0]][ring[idx - 1][1]].co
                nxt = grid_front[ring[(idx + 1) % len(ring)][0]][ring[(idx + 1) % len(ring)][1]].co
                tangent = (nxt - prev)
                outward = Vector((tangent.y, -tangent.x, 0.0))
                centre = Vector((0, self.mid, 0))
                if outward.dot(Vector((f.x, f.y, 0)) - centre) < 0:
                    outward = -outward
                outward = outward.normalized() if outward.length > 0 else Vector()
                p = f.lerp(b, t) + outward * (0.007 * math.sin(math.pi * t))
                loop.append(bm.verts.new(p))
            loops.append(loop)
        loops.append([grid_back[j][i] for j, i in ring])
        for la, lb in zip(loops, loops[1:]):
            for k in range(len(ring)):
                n = (k + 1) % len(ring)
                faces.append(bm.faces.new((la[k], la[n], lb[n], lb[k])))
        for f in faces:
            f.material_index = ZONES[zone]

    def strip(self, part, y0, y1, zone, inset=0.022, raised=0.0035, steps=12):
        """A strip of webbing across the face of the bag."""
        bm = part.bm
        h = min(self.half(y0), self.half(y1)) - inset
        rows = []
        for y in (y0, y1):
            top, base = [], []
            for k in range(steps + 1):
                x = -h + 2 * h * k / steps
                v = (y - self.mid) / ((self.top - self.bottom) / 2)
                puff = 0.005 * (1 - (x / self.half(y)) ** 4) * (1 - v ** 4)
                p, n = self.point(x, y, puff)
                top.append(bm.verts.new(p + n * raised))
                base.append(bm.verts.new(p - n * 0.002))
            rows.append((top, base))
        (t0, b0), (t1, b1) = rows
        faces = []
        for k in range(steps):
            faces.append(bm.faces.new((t0[k], t0[k + 1], t1[k + 1], t1[k])))
            faces.append(bm.faces.new((b0[k], t0[k], t0[k + 1], b0[k + 1])))
            faces.append(bm.faces.new((t1[k], b1[k], b1[k + 1], t1[k + 1])))
        for k in range(steps):
            faces.append(bm.faces.new((b1[k], b1[k + 1], b0[k + 1], b0[k])))
        faces.append(bm.faces.new((b0[0], b1[0], t1[0], t0[0])))
        faces.append(bm.faces.new((t0[-1], t1[-1], b1[-1], b0[-1])))
        for f in faces:
            f.material_index = ZONES[zone]

    def mount(self, part, x, y, build, out=0.0):
        """Builds something with build(part) about the origin (its back face on z = 0, facing +z) and sets it on the bag."""
        before = set(part.bm.verts)
        build(part)
        new = [v for v in part.bm.verts if v not in before]
        p, n = self.point(x, y, out + 0.004)
        bmesh.ops.transform(part.bm, matrix=Matrix.Translation(p) @ frame(n), verts=new)


def mag_pouch(part):
    w, h, d = 0.074, 0.112, 0.056
    part.box((0, h / 2, d / 2), (w, h, d), "trim", bevel=0.011, segments=2)
    # The magazine standing in it, its baseplate and pull tab above the bungee.
    part.box((0, h + 0.014, d / 2), (0.024, 0.04, 0.05), "dark", bevel=0.004)
    part.box((0, h + 0.035, d / 2 + 0.004), (0.028, 0.008, 0.058), "dark", bevel=0.003)
    part.box((0, h - 0.01, d + 0.001), (0.05, 0.007, 0.006), "dark", bevel=0.002)
    part.box((0, h + 0.042, d / 2 + 0.032), (0.016, 0.022, 0.004), "dark", bevel=0.0015, rot=(-20, 0, 0))
    # Stitched seams down the front corners.
    for x in (-w / 2 + 0.006, w / 2 - 0.006):
        part.box((x, h / 2, d), (0.003, h - 0.02, 0.003), "trim")


def admin_pouch(part):
    w, h, d = 0.17, 0.085, 0.024
    part.box((0, h / 2, d / 2), (w, h, d), "trim", bevel=0.008, segments=2)
    part.box((0, h - 0.008, d + 0.0005), (w - 0.02, 0.006, 0.004), "dark", bevel=0.0015)
    part.box((0.035, h * 0.45, d + 0.001), (0.072, 0.046, 0.004), "team", bevel=0.002)
    part.box((-0.05, h * 0.45, d + 0.001), (0.04, 0.025, 0.003), "dark", bevel=0.001)


def kit(body):
    """The plate carrier, its pouches and straps; the belt and its kit: (torso part, pelvis part)."""
    carrier = Part("Carrier")
    front = Plate(body, True, 1.112, 1.432, 0.282)
    back = Plate(body, False, 1.13, 1.455, 0.29)
    front.build(carrier, "trim")
    back.build(carrier, "trim")
    # Webbing on the front above the pouches, and down the back.
    for y in (1.355, 1.393):
        front.strip(carrier, y, y + 0.024, "trim")
    for k in range(6):
        y = 1.165 + k * 0.042
        back.strip(carrier, y, y + 0.026, "trim")
    # A name tape and three magazine pouches under an admin pouch.
    front.mount(carrier, 0.0, 1.36, lambda p: p.box((0, 0.0, 0.003), (0.11, 0.028, 0.004), "dark", bevel=0.0015), out=0.005)
    for x in (-0.08, 0.0, 0.08):
        front.mount(carrier, x, 1.118, mag_pouch)
    front.mount(carrier, 0.0, 1.252, admin_pouch)
    # The drag handle on the back, and a hydration port.
    back.mount(carrier, 0.0, 1.418, lambda p: (p.box((0, 0.0, 0.01), (0.1, 0.022, 0.02), "dark", bevel=0.008),
                                               p.box((0, 0.0, 0.002), (0.13, 0.03, 0.004), "dark", bevel=0.002)))

    # The cummerbund round the sides, between the plates.
    bm = carrier.bm
    rings = []
    heights = [1.09 + k * 0.03 for k in range(6)]
    steps = 64
    for y in heights:
        outer, inner = [], []
        for k in range(steps):
            a = 2 * math.pi * k / steps
            d = Vector((math.sin(a), 0.0, math.cos(a)))
            centre = Vector((0.0, y, 0.015))
            loc, nrm = body.cast(body.torso_bvh, centre + d * 0.6, -d)
            if loc is None:
                loc, nrm = centre + d * 0.15, d
            flat = Vector((nrm.x, 0.0, nrm.z)).normalized()
            outer.append(bm.verts.new(loc + flat * 0.03))
            inner.append(bm.verts.new(loc + flat * 0.021))
        rings.append((outer, inner))
    faces = []
    for (o0, i0), (o1, i1) in zip(rings, rings[1:]):
        for k in range(steps):
            n = (k + 1) % steps
            faces.append(bm.faces.new((o0[k], o0[n], o1[n], o1[k])))
            faces.append(bm.faces.new((i1[k], i1[n], i0[n], i0[k])))
    for (o, i), flip in ((rings[0], True), (rings[-1], False)):
        for k in range(steps):
            n = (k + 1) % steps
            quad = (o[k], i[k], i[n], o[n])
            faces.append(bm.faces.new(quad if flip else tuple(reversed(quad))))
    for f in faces:
        f.material_index = ZONES["trim"]
    # Rows of webbing slots on the cummerbund's sides, a radio pouch on the left, a medical pouch on the right.
    for s, build in ((-1, "radio"), (1, "med")):
        a = math.radians(90 * s)
        d = Vector((math.sin(a), 0.0, math.cos(a)))
        loc, nrm = body.cast(body.torso_bvh, Vector((0.0, 1.17, 0.0)) + d * 0.6, -d)
        if loc is None:
            continue
        flat = Vector((nrm.x, 0.0, nrm.z)).normalized()
        base = loc + flat * 0.034
        before = set(bm.verts)
        if build == "radio":
            carrier.box((0, 0.0, 0.022), (0.068, 0.13, 0.044), "trim", bevel=0.009, segments=2)
            carrier.box((0, 0.082, 0.02), (0.05, 0.035, 0.032), "dark", bevel=0.005)
            carrier.cylinder((0.012, 0.095, 0.02), (0.012, 0.33, 0.012), 0.0045, 0.003, "dark", segments=8)
            carrier.box((0, -0.01, 0.045), (0.05, 0.007, 0.004), "dark", bevel=0.0015)
        else:
            carrier.box((0, 0.0, 0.024), (0.085, 0.11, 0.048), "trim", bevel=0.012, segments=2)
            carrier.box((0, 0.0, 0.0485), (0.04, 0.04, 0.003), "dark", bevel=0.001)
            carrier.box((0, 0.062, 0.03), (0.02, 0.022, 0.004), "dark", bevel=0.0015, rot=(-25, 0, 0))
        new = [v for v in bm.verts if v not in before]
        bmesh.ops.transform(bm, matrix=Matrix.Translation(base) @ frame(flat), verts=new)

    # Padded straps over each shoulder, from the top of one bag to the other.
    for side, s in (("L", -1), ("R", 1)):
        x = s * 0.092
        path = []
        for k in range(17):
            phi = math.radians(14 + 152 * k / 16)
            d = Vector((0.0, math.sin(phi), math.cos(phi)))
            loc, nrm = body.cast(body.trunk_bvh, Vector((x, 1.36, -0.005)) + d * 0.45, -d)
            if loc is not None:
                path.append((loc, nrm))
        centres = [loc + nrm * 0.022 for loc, nrm in path]
        for k in range(len(centres)):
            if 0 < k < len(centres) - 1:
                centres[k] = (centres[k - 1] + centres[k] * 2 + centres[k + 1]) / 4
        sections = []
        for k, (c, (loc, nrm)) in enumerate(zip(centres, path)):
            ahead = centres[min(k + 1, len(centres) - 1)] - centres[max(k - 1, 0)]
            ahead.normalize()
            across = ahead.cross(nrm).normalized()
            up = across.cross(ahead).normalized()
            if up.dot(nrm) < 0:
                up = -up
            ring = []
            for m in range(12):
                t = 2 * math.pi * m / 12
                cx, cy = math.cos(t), math.sin(t)
                px = 0.03 * math.copysign(abs(cx) ** 0.45, cx)
                py = 0.0075 * math.copysign(abs(cy) ** 0.6, cy)
                ring.append(bm.verts.new(c + across * px + up * py))
            sections.append(ring)
        faces = []
        for ra, rb in zip(sections, sections[1:]):
            for m in range(12):
                n = (m + 1) % 12
                faces.append(bm.faces.new((ra[m], ra[n], rb[n], rb[m])))
        faces.append(bm.faces.new(list(reversed(sections[0]))))
        faces.append(bm.faces.new(sections[-1]))
        for f in faces:
            f.material_index = ZONES["trim"]

    belt = Part("BeltKit")
    # A buckle at the front, pouches at each hip and a dump pouch at the back.
    loc, nrm = body.cast(body.torso_bvh, (0.0, 0.977, 0.6), (0, 0, -1))
    if loc is not None:
        belt.box(loc + Vector((0, 0, 0.026)), (0.062, 0.042, 0.012), "metal", bevel=0.004)
        belt.box(loc + Vector((0, 0, 0.033)), (0.04, 0.024, 0.004), "dark", bevel=0.0015)
    for s, size, angle in ((1, (0.07, 0.085, 0.045), 62), (-1, (0.06, 0.1, 0.05), 70), (-1, (0.12, 0.09, 0.05), 150)):
        a = math.radians(angle * s)
        d = Vector((math.sin(a), 0.0, math.cos(a)))
        loc, nrm = body.cast(body.torso_bvh, Vector((0.0, 0.975, 0.0)) + d * 0.6, -d)
        if loc is None:
            continue
        flat = Vector((nrm.x, 0.0, nrm.z)).normalized()
        before = set(belt.bm.verts)
        belt.box((0, -0.02, size[2] / 2), size, "trim", bevel=0.012, segments=2)
        belt.box((0, size[1] / 2 - 0.022, size[2] + 0.001), (size[0] - 0.012, 0.03, 0.004), "trim", bevel=0.002)
        new = [v for v in belt.bm.verts if v not in before]
        bmesh.ops.transform(belt.bm, matrix=Matrix.Translation(loc + flat * 0.026) @ frame(flat), verts=new)
    return carrier, belt


def belt_band(body, over=()):
    P, S = body.P, body

    def field(i):
        p = P[i]
        return min(p.y - 0.954, 0.999 - p.y) - 2 * S.arm[i]

    return garment(body, "Belt", field, lambda i: 0.016, "dark", smooth=4, hem=0.006, gap=0.012, over=over, over_gap=0.003)


# ---------------------------------------------------------------------------- first person

def extract(objects, name, keep, pivot):
    """A rigid copy of the faces of some garments whose centres pass keep(point), pivoted at `pivot`."""
    bm = bmesh.new()
    for obj in objects:
        part = bmesh.new()
        part.from_mesh(obj.data)
        doomed = [f for f in part.faces if not keep(f.calc_center_median())]
        bmesh.ops.delete(part, geom=doomed, context='FACES')
        mesh = bpy.data.meshes.new("tmp")
        part.to_mesh(mesh)
        part.free()
        bm.from_mesh(mesh)
        bpy.data.meshes.remove(mesh)
    obj = to_object(bm, name)
    obj["pivot"] = list(pivot)
    return obj


def first_person(body, uniform):
    """
    The forearms and hands the player sees of themselves: each sleeve from just above the
    elbow down, with its cuff, and each glove, pointing straight down from the wrist (as
    Client/Weapons/FirstPersonArms.cs expects).
    """
    by_name = {o.name.split(".")[0]: o for o in uniform}
    sleeves = [by_name["Shirt"], by_name["Cuffs"]]
    hands = [by_name["Gloves"], by_name["GloveCuffs"]]
    out = []
    for side in ("L", "R"):
        j = body.side[side]
        mine = lambda p, side=side: (p.x < 0) == (side == "L")
        fore = extract(sleeves, "FPForearm" + side,
                       lambda p: mine(p) and abs(p.x) > 0.15 and (p - j["elbow"]).dot(j["fore"]) > -0.035, j["elbow"])
        hand = extract(hands, "FPHand" + side, lambda p: mine(p) and abs(p.x) > 0.15, j["wrist"])
        knuckles = (j["index"] + j["little"]) / 2
        turn = (knuckles - j["wrist"]).rotation_difference(Vector((0, -1, 0))).to_matrix().to_4x4()
        hand.data.transform(Matrix.Translation(j["wrist"]) @ turn @ Matrix.Translation(-j["wrist"]))
        for piece in (fore, hand):
            piece["own_uv"] = True
            piece.data["maps"] = "Uniform"
        out += [fore, hand]
    return out


# ---------------------------------------------------------------------------- all of it

def dress(B, bone_index):
    """
    The uniform and kit for a built body: {"uniform": [objects], "kit": [objects]}, every
    object skinned (weight attributes set).
    """
    body = Body(B)
    torso, pelvis = bone_index["Torso"], bone_index["Pelvis"]
    top, legs, hands = shirt(body), trousers(body), gloves(body)
    uniform = [top, collar(body, [top]), sleeve_band(body, "Cuffs", CUFF - 0.006, CUFF + 0.032, 0.0115, "primary", over=[top]),
               sleeve_band(body, "GloveCuffs", -0.012, CUFF - 0.002, 0.0062, "dark", hem=0.003, over=[hands]),
               armbands(body, [top]), elbow_pads(body, [top]), legs, pocket_flaps(body, [legs]), hands]
    boot = boots(body)
    uniform.append(boot)
    for p in (soles(body, boot), laces(body, boot)):
        obj = p.to_object()
        set_weights(obj, lambda co: {bone_index["FootL" if co.x < 0 else "FootR"]: 1.0})
        uniform.append(obj)
    carrier, belt_kit = kit(body)
    carrier = rigid(carrier.to_object(), torso)
    belt_kit = rigid(belt_kit.to_object(), pelvis)
    belt = rigid(belt_band(body, [top, legs]), pelvis)
    pads = knee_pads(body, [legs])
    straps = knee_straps(body, [legs])
    for obj in (pads, straps):
        set_weights(obj, lambda co: {bone_index["ShinL" if co.x < 0 else "ShinR"]: 1.0} if co.y < 0.53 else
                    {bone_index["ThighL" if co.x < 0 else "ThighR"]: 1.0})
    return {"uniform": uniform, "kit": [carrier, belt, belt_kit, pads, straps], "body": body, "back": back_surface(body)}


def back_surface(body):
    """How far back the carrier's back face is, behind the middle of the back: for hanging packs on."""
    plate = Plate(body, False, 1.13, 1.455, 0.29)
    return -(plate.depth(0.0, 1.3) + 0.005)
