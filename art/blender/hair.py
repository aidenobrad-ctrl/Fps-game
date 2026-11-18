"""
Hairstyles for the soldier's head, each a shell of hair over the scalp:

  crew        short back and sides, a little longer on top, combed back
  buzz        clipped close all over
  side_part   short sides, a longer top swept over from a parting on the left, lifted at the front
  slick_back  long on top and combed straight back, the sides clipped short
  mohawk      a tall, spiked crest down the middle, the sides shaved
  curly       tight curls, thick on top, short at the sides
  bun         pulled back from the hairline into a bun at the back of the head
  (shaved has no shell: the scalp's own stubble, painted in the skin texture, is all there is)

Each style says, for any point of the scalp, whether hair grows there (coverage), how thick
it lies (depth) and which way it is combed. The shell follows the head's surface out by that
depth, sinks under the skin where the hair stops (so the hairline is the painted one), and
is ridged into clumps that run the way the hair is combed. Its strands are baked into a
normal map: Hair<Style>Normal.jpg.
"""
import math, os
import bpy, bmesh
from mathutils import Vector, noise

from human import smoothstep, mesh_object

STYLES = ["crew", "buzz", "side_part", "slick_back", "mohawk", "curly", "bun"]
MODEL = {"crew": "HairCrew", "buzz": "HairBuzz", "side_part": "HairSidePart", "slick_back": "HairSlickBack",
         "mohawk": "HairMohawk", "curly": "HairCurly", "bun": "HairBun"}

# The head, roughly: its crown, and the point the hair is combed back towards.
CROWN = Vector((0.0, 1.742, 0.03))
NAPE = Vector((0.0, 1.6, -0.06))


def top(p):
    """0 at the sides and back of the head, 1 on top."""
    return smoothstep(1.665, 1.705, p.y) * (1 - smoothstep(0.05, 0.068, abs(p.x)))


def front(p):
    return smoothstep(0.0, 0.09, p.z)


def combed_back(p, n):
    """Straight back over the top, down and back at the sides."""
    d = Vector((0.0, -0.35, -1.0))
    if abs(p.x) > 0.04:
        d = d.lerp(Vector((0.0, -1.0, -0.4)), smoothstep(0.04, 0.07, abs(p.x)))
    return d


class Style:
    def __init__(self, name):
        self.name = name

    # Where hair grows, on top of the scalp's own coverage (0..1).
    def coverage(self, p):
        return 1.0

    def depth(self, p):
        return 0.004

    def flow(self, p, n):
        return combed_back(p, n)

    def clumps(self, p, along, across):
        """How far a point stands out of the shell's surface, for clumps and curls."""
        return 0.0006 * math.sin(across * 2 * math.pi / 0.006 + 2.5 * noise.noise(p * 60))

    def strands(self):
        """Spacing of the fine strands baked into the normal map, and how long they run."""
        return 0.0024, 1.0

    # Styles with detail too fine for the scalp's mesh smooth their shell once more and
    # then raise it by detail(p) along the normals.
    subdivide = False
    # How far in from its edge the hair takes to reach its full depth.
    taper = 0.012

    def detail(self, p):
        return 0.0


class Crew(Style):
    def depth(self, p):
        return 0.0028 + 0.0062 * top(p) * (0.65 + 0.35 * front(p))

    def clumps(self, p, along, across):
        return 0.0011 * top(p) * math.sin(across * 2 * math.pi / 0.007 + 2.0 * noise.noise(p * 50))


class Buzz(Style):
    taper = 0.006

    def depth(self, p):
        return 0.0022

    def clumps(self, p, along, across):
        return 0.0002 * noise.noise(p * 400)

    def strands(self):
        return 0.0016, 0.25


class SidePart(Style):
    PART = -0.028

    def part(self, p):
        """How far from the parting, across the top on the left."""
        if p.y < 1.68 or p.z < -0.03:
            return 1.0
        return abs(p.x - self.PART)

    def depth(self, p):
        t = top(p)
        d = 0.003 + t * (0.011 + 0.012 * front(p))
        # Lifted at the front on the right, where it is swept over.
        d += 0.006 * t * front(p) * smoothstep(-0.02, 0.03, p.x)
        return d * (0.25 + 0.75 * smoothstep(0.0, 0.007, self.part(p)))

    def flow(self, p, n):
        if top(p) > 0.3 and p.z > -0.03:
            side = 1.0 if p.x > self.PART else -1.0
            return Vector((side, -0.25, -0.35))
        return combed_back(p, n)

    def clumps(self, p, along, across):
        return top(p) * 0.0026 * math.sin(across * 2 * math.pi / 0.011 + 2.2 * noise.noise(p * 35))


class SlickBack(Style):
    def coverage(self, p):
        # Clipped short at the sides: the shell only on top (the sides are the painted stubble).
        return smoothstep(1.66, 1.675, p.y) * (1 - smoothstep(0.052, 0.06, abs(p.x)))

    def depth(self, p):
        return 0.004 + 0.014 * top(p) * (0.7 + 0.3 * front(p))

    def flow(self, p, n):
        return Vector((0.0, -0.2, -1.0))

    def clumps(self, p, along, across):
        return 0.0024 * top(p) * math.sin(across * 2 * math.pi / 0.009 + 1.6 * noise.noise(p * 30))


class Mohawk(Style):
    subdivide = True
    taper = 0.007

    def coverage(self, p):
        return 1 - smoothstep(0.019, 0.026, abs(p.x))

    def depth(self, p):
        rise = smoothstep(1.6, 1.7, p.y)
        crest = 0.012 + 0.036 * rise * (1 - 0.3 * smoothstep(0.06, 0.12, p.z))
        # Spikes along the crest.
        spikes = 0.72 + 0.28 * abs(math.sin(p.z * math.pi / 0.016 + 0.6 * math.sin(p.y * 90)))
        edge = 1 - smoothstep(0.008, 0.022, abs(p.x))
        return 0.002 + crest * spikes * edge

    def flow(self, p, n):
        # Standing up off the head, leaning back a little.
        return Vector((0.0, 1.0, -0.3))

    def clumps(self, p, along, across):
        return 0.0018 * math.sin(across * 2 * math.pi / 0.006 + 2.0 * noise.noise(p * 70))


class Curly(Style):
    subdivide = True

    def depth(self, p):
        t = top(p)
        return 0.006 + 0.02 * t * (0.85 + 0.15 * front(p))

    def clumps(self, p, along, across):
        return 0.0

    def detail(self, p):
        # Curls: round, tight lumps, larger on top.
        cell = noise.voronoi(p * 110, distance_metric='DISTANCE', exponent=2.5)[0][0]
        return (0.0015 + 0.005 * top(p)) * (0.55 - min(1.0, cell * 1.5)) + 0.0006 * noise.noise(p * 400)

    def strands(self):
        return 0.0018, 0.3


class Bun(Style):
    BUN = Vector((0.0, 1.715, -0.068))

    def depth(self, p):
        return 0.0045 + 0.004 * top(p)

    def flow(self, p, n):
        # Towards the bun from everywhere.
        return self.BUN - p

    def clumps(self, p, along, across):
        return 0.0012 * math.sin(across * 2 * math.pi / 0.006 + 1.5 * noise.noise(p * 50))


def style(name):
    return {"crew": Crew, "buzz": Buzz, "side_part": SidePart, "slick_back": SlickBack,
            "mohawk": Mohawk, "curly": Curly, "bun": Bun}[name](name)


# ---------------------------------------------------------------------------- building

def shell(head, s, zone):
    """
    The style's shell over the scalp of the (smoothed) head. It is cut cleanly where the
    hair stops (where coverage crosses one half) and meets the skin there, thickening over
    the first `taper` metres in from the edge, so the edge of the hair is a smooth line on
    the scalp rather than the edges of faces or a step.
    """
    import outfit
    mesh = head.data
    mask = mesh.color_attributes["maskB"].data
    P = [v.co.copy() for v in mesh.vertices]
    N = [v.normal.copy() for v in mesh.vertices]
    m = [mask[i].color[2] * s.coverage(P[i]) for i in range(len(P))]
    f = [x - 0.5 if abs(x - 0.5) > 1e-6 else 1e-6 for x in m]
    base, normal, full, across_values = [], [], [], []
    faces, made, crossings = [], {}, {}

    def frame(co, n):
        flow = s.flow(co, n)
        flow = flow - n * flow.dot(n)
        flow = flow.normalized() if flow.length > 1e-6 else Vector((0.0, 0.0, -1.0))
        side = n.cross(flow)
        return co.dot(flow), co.dot(side)

    def add(co, n, depth, across):
        base.append(co)
        normal.append(n)
        full.append(depth)
        across_values.append(across)
        return len(base) - 1

    def vert(i):
        if i not in made:
            along, across = frame(P[i], N[i])
            made[i] = add(P[i], N[i], s.depth(P[i]) + s.clumps(P[i], along, across), across)
        return made[i]

    def crossing(a, b):
        key = (min(a, b), max(a, b))
        if key not in crossings:
            t = f[a] / (f[a] - f[b])
            co = P[a].lerp(P[b], t)
            n = N[a].lerp(N[b], t).normalized()
            crossings[key] = add(co, n, 0.0, frame(co, n)[1])
        return crossings[key]

    for poly in mesh.polygons:
        vi = list(poly.vertices)
        if max(f[i] for i in vi) < 0:
            continue
        loop = []
        for k in range(len(vi)):
            a, b = vi[k], vi[(k + 1) % len(vi)]
            if f[a] >= 0:
                loop.append(vert(a))
            if (f[a] >= 0) != (f[b] >= 0):
                loop.append(crossing(a, b))
        if len(loop) >= 3 and len(set(loop)) == len(loop):
            faces.append(loop)

    # How far each point is from the edge of the hair, across the scalp.
    bm = bmesh.new()
    bverts = [bm.verts.new(p) for p in base]
    for loop in faces:
        try:
            bm.faces.new([bverts[k] for k in loop])
        except ValueError:
            pass
    outfit.distance_from_edges(bm, limit=0.05)
    layer = bm.verts.layers.float["hem"]
    # (Adding the layer replaced the vertices: read them afresh, in the order they were made.)
    edge = [v[layer] for v in bm.verts]
    bm.free()
    verts = []
    for k, p in enumerate(base):
        rise = smoothstep(0.0, s.taper, edge[k])
        verts.append(p + normal[k] * (full[k] * rise - 0.0005 * (1 - smoothstep(0.0, 0.002, edge[k]))))
    obj = mesh_object(MODEL[s.name], verts, faces, zone)
    # For the strand bake: a measure across the way the hair is combed; and how far in from its edge.
    across_attr = obj.data.attributes.new("across", 'FLOAT', 'POINT')
    edge_attr = obj.data.attributes.new("edge", 'FLOAT', 'POINT')
    for k in range(len(verts)):
        across_attr.data[k].value = across_values[k]
        edge_attr.data[k].value = edge[k]
    if s.subdivide:
        from human import apply_subsurf
        apply_subsurf(obj, 1)
        mesh = obj.data
        edges = mesh.attributes["edge"].data
        for v in mesh.vertices:
            v.co = v.co + v.normal * s.detail(v.co) * smoothstep(0.0, s.taper, edges[v.index].value)
        mesh.update()
    return obj


def bun_knot(s, zone):
    """The bun itself: a twisted knot of hair, and the band round its base."""
    from human import mesh_object as make
    bm = bmesh.new()
    res = bmesh.ops.create_uvsphere(bm, u_segments=28, v_segments=18, radius=0.03)
    c = Bun.BUN
    for v in res["verts"]:
        p = v.co.copy()
        a = math.atan2(p.x, p.y)
        h = p.z / 0.03
        twist = 0.0035 * math.sin(a * 5 + h * 4)
        r = p.normalized()
        v.co = c + Vector((p.x * 1.15, p.y * 0.95, p.z * 0.9 - 0.004)) + r * twist
    verts = [v.co.copy() for v in bm.verts]
    bm.verts.index_update()
    faces = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    knot = make("BunKnot", verts, faces, zone)
    attr = knot.data.attributes.new("across", 'FLOAT', 'POINT')
    for v in knot.data.vertices:
        rel = v.co - c
        attr.data[v.index].value = math.atan2(rel.x, rel.y) * 0.03 + rel.z * 0.3
    return knot


def build_styles(head, zones, out_dir, size=512):
    """Every hairstyle as an object with its own UVs, and its strand normal map in out_dir. Returns the objects."""
    import textures
    made = []
    for name in STYLES:
        s = style(name)
        obj = shell(head, s, zones["hair"])
        if name == "bun":
            knot = bun_knot(s, zones["hair"])
            band = bmesh.new()
            ring = bmesh.ops.create_cone(band, cap_ends=False, segments=20, radius1=0.019, radius2=0.017, depth=0.008)
            for v in ring["verts"]:
                v.co = Bun.BUN + Vector((v.co.x, v.co.y, v.co.z)) + Vector((0.0, 0.0, 0.017))
            bpy.ops.object.select_all(action='DESELECT')
            knot.select_set(True)
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.join()
            band_mesh = bpy.data.meshes.new("band")
            band.to_mesh(band_mesh)
            band.free()
            tie = bmesh.new()
            tie.from_mesh(obj.data)
            tie.from_mesh(band_mesh)
            bpy.data.meshes.remove(band_mesh)
            tie.to_mesh(obj.data)
            tie.free()
            for poly in obj.data.polygons:
                if poly.material_index != zones["hair"]:
                    poly.material_index = zones["dark"]
        obj["pivot"] = [0, 0, 0]
        textures.unwrap_together([obj], margin=0.01)
        textures.bake_hair(obj, s, os.path.join(out_dir, obj.name + "Normal.jpg"), size)
        made.append(obj)
    return made
