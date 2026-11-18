"""
The first-person hands, in tactical gloves, posed round what they hold.

Each hand is built joint by joint from capsules (palm, four fingers, thumb, wrist cuff) laid
round the shape it grips, then fused into one smooth surface with a voxel remesh and
thinned. It is modelled in the frame of the point it holds (see guns.py): the origin is
that point, +y the hand's up along the grip, +z forward, +x to the right. The game puts the
hand on a weapon's Grip or Support point, so the hand closes on the weapon whatever its
size, and the forearm runs from the hand's Wrist point back to the elbow.

  HandGripR     the right hand on a pistol grip, its index finger on the trigger;
  HandHoldR     the right hand closed round a handle (a knife's, a machete's), or a fist;
  HandHoldL     the left hand closed round a vertical foregrip or a front grip, or a fist;
  HandSupportL  the left hand under a handguard or a pump, thumb along the left side and
                fingers up the right, below the sight line;
  HandPistolL   the left hand wrapped round the right on a handgun's grip.
"""
import math
import bmesh
import bpy
from mathutils import Vector, Matrix

# Phalanx lengths (proximal, middle, distal) and radii, gloved, for an adult hand.
FINGERS = [
    ("index", (0.041, 0.024, 0.02), 0.0094),
    ("middle", (0.045, 0.027, 0.021), 0.0097),
    ("ring", (0.042, 0.026, 0.02), 0.0091),
    ("little", (0.034, 0.02, 0.018), 0.0082),
]
THUMB = ((0.034, 0.028), 0.0105)


class Hand:
    def __init__(self, Part, name):
        self.part = Part(name)
        self.name = name
        self.points = {}

    def capsule(self, a, b, ra, rb, segs=14):
        a, b = Vector(a), Vector(b)
        if (b - a).length > 1e-5:
            self.part.cylinder(a, b, ra, rb, "dark", segments=segs)
        self.part.sphere(a, ra, "dark", u=segs, v=8)
        self.part.sphere(b, rb, "dark", u=segs, v=8)

    def chain(self, pts, r0, r1):
        n = len(pts) - 1
        for i in range(n):
            self.capsule(pts[i], pts[i + 1], r0 + (r1 - r0) * i / n, r0 + (r1 - r0) * (i + 1) / n)

    def blob(self, c, r, scale=(1, 1, 1)):
        self.part.sphere(Vector(c), r, "dark", scale=scale, u=16, v=10)


def on_ellipse(a, b, phi, y, cx=0.0, cz=0.0):
    """A point round an upright elliptical grip: phi from +x (0) towards +z (90)."""
    return Vector((cx + a * math.cos(math.radians(phi)), y, cz + b * math.sin(math.radians(phi))))


def wrap(a, b, start_phi, y, lengths, turn=+1, rise=0.0, cx=0.0, cz=0.0):
    """
    Joints walked round an ellipse from start_phi, each a chord of the given length from the
    last: how a finger lies round a grip. rise tilts the walk along the grip's axis.
    """
    pts = [on_ellipse(a, b, start_phi, y, cx, cz)]
    phi = start_phi
    for length in lengths:
        p0 = pts[-1]
        lo, hi = 0.0, 179.0
        for _ in range(48):
            mid = (lo + hi) / 2
            q = on_ellipse(a, b, phi + turn * mid, p0.y + rise * length, cx, cz)
            if (q - p0).length < length:
                lo = mid
            else:
                hi = mid
        phi += turn * lo
        pts.append(on_ellipse(a, b, phi, p0.y + rise * length, cx, cz))
    return pts


def palm(h, mcps, wrist, wrist_halfwidth, a, b, back_phi, mcp_phi, radius=0.0135, cx=0.0, cz=0.0):
    """
    The palm: from each knuckle back round the grip and on to the wrist, as overlapping
    spheres that the remesh fuses into one surface.
    """
    for i, (mcp, y) in enumerate(mcps):
        across = (i - 1.5) / 1.5
        rim = wrist + Vector((0.0, across * wrist_halfwidth, 0.0))
        pts = []
        steps = 7
        for k in range(steps + 1):
            t = k / steps
            phi = mcp_phi + (back_phi - mcp_phi) * t
            yy = y + (rim.y - y) * t * 0.6
            pts.append(on_ellipse(a, b, phi, yy, cx, cz))
        for k in range(1, 5):
            t = k / 4
            pts.append(pts[steps].lerp(rim, t))
        for p in pts:
            h.blob(p, radius * (1.08 if i in (1, 2) else 1.0))


def cuff(h, wrist, forearm, rx=0.029, rz=0.024):
    """The glove's cuff: an oval sleeve from the wrist up the forearm."""
    d = Vector(forearm).normalized()
    for k in range(5):
        c = wrist + d * (0.008 * k)
        h.part.sphere(c, 1.0, "dark", scale=_oval(d, rx, rz), u=18, v=10)
    h.points["Wrist"] = list(wrist) + list(d)


def _oval(d, rx, rz):
    # The cuff is made of axis-aligned ellipsoids; leaning ones would need a matrix, and a
    # near-round cuff hides the difference.
    r = (rx + rz) / 2
    return (r, r, r)


def finish(obj, voxel=0.0012, smooth=6, ratio=0.035):
    """Fuses the capsules into one surface, smooths and thins it, and makes it all glove."""
    remesh = obj.modifiers.new("remesh", 'REMESH')
    remesh.mode = 'VOXEL'
    remesh.voxel_size = voxel
    remesh.adaptivity = 0.0
    smooth_mod = obj.modifiers.new("smooth", 'SMOOTH')
    smooth_mod.factor = 0.6
    smooth_mod.iterations = smooth
    decimate = obj.modifiers.new("decimate", 'DECIMATE')
    decimate.ratio = ratio
    graph = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(graph))
    old = obj.data
    obj.modifiers.clear()
    obj.data = mesh
    bpy.data.meshes.remove(old)
    mesh.name = obj.name
    for poly in mesh.polygons:
        poly.material_index = 1
        poly.use_smooth = True
    mesh.use_auto_smooth = True
    mesh.auto_smooth_angle = math.radians(60)
    return obj


def mirror(h):
    """Makes a right hand into a left one."""
    bmesh.ops.scale(h.part.bm, vec=(-1, 1, 1), verts=list(h.part.bm.verts))
    for name, p in list(h.points.items()):
        h.points[name] = [-p[0], p[1], p[2], -p[3], p[4], p[5]]


# ---------------------------------------------------------------------------- poses

def grip_hand(Part, name, a=0.0148, b=0.025, trigger=True, heights=(0.028, 0.008, -0.012, -0.031), rake_wrist=20.0):
    """
    A right hand round an upright grip of half-width a and half-depth b: palm on the right
    side and back, fingers round the front, thumb round the back to the left side. With
    trigger, the index finger reaches forward on to a trigger at the standard place.
    """
    h = Hand(Part, name)
    mcp_phi, back_phi = 12.0, -95.0
    a_up = math.radians(rake_wrist)
    forearm = Vector((0.12, -math.sin(a_up), -math.cos(a_up))).normalized()
    wrist = Vector((0.016, -0.012, -b - 0.042))
    mcps = []
    for (fname, lengths, r), y in zip(FINGERS, heights):
        ao, bo = a + r + 0.0004, b + r + 0.0004
        mcp = on_ellipse(ao + 0.004, bo + 0.004, mcp_phi, y)
        if fname == "index" and trigger:
            # Forward along the right of the frame, then the last joint curled on the trigger.
            pip = mcp + Vector((-0.004, 0.006, 0.04))
            dip = pip + Vector((-0.017, -0.002, 0.014))
            tip = dip + Vector((-0.013, -0.004, -0.012))
            h.chain([mcp, pip, dip, tip], r * 1.05, r * 0.88)
        else:
            pts = wrap(ao, bo, mcp_phi + 4.0, y, lengths, +1)
            h.chain([mcp] + pts[1:], r * 1.05, r * 0.88)
        mcps.append((mcp, y))
    palm(h, mcps, wrist, 0.019, a + 0.012, b + 0.012, back_phi, mcp_phi)
    # The thumb: from its base by the wrist, round the back of the grip, along the left side.
    t_len, t_r = THUMB
    cmc = wrist + Vector((-0.016, 0.03, 0.012))
    base = on_ellipse(a + t_r + 0.002, b + t_r + 0.002, 238.0, heights[0] + 0.012)
    pts = wrap(a + t_r + 0.001, b + t_r + 0.001, 238.0, heights[0] + 0.012, t_len, -1, rise=0.12)
    h.chain([cmc, base], t_r * 1.35, t_r * 1.12)
    h.chain(pts, t_r * 1.1, t_r * 0.9)
    h.blob(cmc.lerp(base, 0.45) + Vector((0.004, -0.008, 0.0)), 0.016, (1.0, 1.25, 1.0))
    cuff(h, wrist, forearm)
    return h


def support_hand(Part, name="HandSupportL", half_width=0.026, height=0.05):
    """
    The left hand cupping a handguard from below: the Support point is the middle of the
    handguard's underside. Palm under it, thumb forward along the left side, fingers up
    and forward along the right side, all of it below the top of the handguard.
    """
    h = Hand(Part, name)
    # The handguard's cross-section, centred above the support point.
    a, b = half_width, height / 2
    cy = height / 2
    forearm = Vector((-0.5, -0.62, -0.6)).normalized()
    wrist = Vector((-0.036, -0.03, -0.075))
    depths = (0.032, 0.012, -0.008, -0.026)
    mcps = []
    for (fname, lengths, r), z in zip(FINGERS, depths):
        # Round the cross-section in the x-y plane: from under the right edge, up the side.
        ao, bo = a + r + 0.0004, b + r + 0.0004
        pts = []
        theta = -58.0
        p = Vector((ao * math.cos(math.radians(theta)), cy + bo * math.sin(math.radians(theta)), z))
        pts.append(p)
        for length in lengths:
            lo, hi = 0.0, 120.0
            for _ in range(48):
                mid = (lo + hi) / 2
                q = Vector((ao * math.cos(math.radians(theta + mid)), cy + bo * math.sin(math.radians(theta + mid)), p.z + 0.32 * length))
                if (q - p).length < length:
                    lo = mid
                else:
                    hi = mid
            theta = min(theta + lo, 34.0)
            p = Vector((ao * math.cos(math.radians(theta)), cy + bo * math.sin(math.radians(theta)), p.z + 0.32 * length))
            pts.append(p)
        h.chain(pts, r * 1.05, r * 0.88)
        mcps.append(pts[0])
    # The palm: under the handguard, from the knuckles back to the wrist.
    for i, mcp in enumerate(mcps):
        rim = wrist + Vector((0.0, 0.0, (i - 1.5) / 1.5 * 0.018))
        start = mcp + Vector((-0.004, -0.004, 0.0))
        for k in range(9):
            t = k / 8
            p = start.lerp(rim, t)
            # Keep the palm's middle up against the underside.
            p.y = min(p.y, -0.009 - 0.02 * t * t)
            h.blob(p, 0.0135)
    # The thumb along the left side, pointing forward.
    t_len, t_r = THUMB
    cmc = wrist + Vector((0.006, 0.018, 0.022))
    base = Vector((-a - t_r - 0.002, 0.004, 0.012))
    mid = base + Vector((0.002, 0.004, t_len[0]))
    tip = mid + Vector((0.004, 0.002, t_len[1]))
    h.chain([cmc, base], t_r * 1.35, t_r * 1.12)
    h.chain([base, mid, tip], t_r * 1.1, t_r * 0.9)
    h.blob(cmc.lerp(base, 0.5) + Vector((0.004, -0.006, 0.0)), 0.016, (1.0, 1.0, 1.25))
    cuff(h, wrist, forearm)
    return h


def pistol_support_hand(Part, name="HandPistolL"):
    """
    The left hand on a handgun, built as a right hand round the firing hand's fingers (a
    fatter grip, a little lower and further forward) and then mirrored: palm on the left
    side, fingers round the front of the right hand, thumb forward under the slide.
    """
    h = Hand(Part, name)
    a, b, cz = 0.031, 0.042, 0.012
    heights = (0.004, -0.015, -0.034, -0.051)
    mcp_phi, back_phi = 10.0, -80.0
    forearm = Vector((0.55, -0.45, -0.7)).normalized()
    wrist = Vector((0.03, -0.045, -0.04))
    mcps = []
    for (fname, lengths, r), y in zip(FINGERS, heights):
        ao, bo = a + r, b + r
        mcp = on_ellipse(ao + 0.003, bo + 0.003, mcp_phi, y, cz=cz)
        pts = wrap(ao, bo, mcp_phi + 4.0, y, lengths, +1, cz=cz)
        h.chain([mcp] + pts[1:], r * 1.05, r * 0.88)
        mcps.append((mcp, y))
    palm(h, mcps, wrist, 0.018, a + 0.011, b + 0.011, back_phi, mcp_phi, cz=cz)
    t_len, t_r = THUMB
    cmc = wrist + Vector((-0.012, 0.03, 0.016))
    base = Vector((a * 0.55, 0.026, cz + b * 0.6))
    mid = base + Vector((0.004, 0.003, t_len[0]))
    tip = mid + Vector((0.002, 0.002, t_len[1]))
    h.chain([cmc, base], t_r * 1.35, t_r * 1.12)
    h.chain([base, mid, tip], t_r * 1.1, t_r * 0.9)
    h.blob(cmc.lerp(base, 0.45), 0.016, (1.0, 1.2, 1.0))
    cuff(h, wrist, forearm)
    mirror(h)
    return h


def all_hands(Part):
    hands = [grip_hand(Part, "HandGripR"),
             grip_hand(Part, "HandHoldR", a=0.0128, b=0.0145, trigger=False, heights=(0.027, 0.007, -0.013, -0.031), rake_wrist=8.0)]
    left = grip_hand(Part, "HandHoldL", a=0.0138, b=0.016, trigger=False, heights=(0.027, 0.007, -0.013, -0.031), rake_wrist=8.0)
    mirror(left)
    hands.append(left)
    hands.append(support_hand(Part))
    hands.append(pistol_support_hand(Part))
    return hands


def objects(Part):
    made = []
    for h in all_hands(Part):
        obj = h.part.to_object()
        finish(obj)
        obj["uv_scale"] = 6.0
        obj["points"] = dict(h.points)
        made.append(obj)
    return made
