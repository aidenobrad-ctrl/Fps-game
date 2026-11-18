"""
Recoil's weapons: real guns, launchers and blades at their real sizes, built from code.

Each weapon is modelled in its own frame, in metres: +z towards the muzzle, +y up, +x to
the right, with the origin on the bore's axis straight above the trigger. A weapon is one
mesh named by its id in the game (ar_m4a1, smg_mp5...), with up to three more that the game
can swap or hide:

  <id>.Mag    the magazine (or belt box, or loaded rocket), lengthened for an extended
              magazine, hidden for a drum, dropped during a reload;
  <id>.Stock  a stock that can be swapped for a lighter or heavier one, or taken off;
  <id>.Irons  the iron sights, carry handle or built-in scope, put away when an optic is
              fitted.

Zones: primary is the weapon's main finish (a skin's pattern goes here: receivers,
handguards, stocks, furniture), dark the secondary finish (grips, rails, pads, controls),
metal bare steel (barrels, bolts, pins), glow the sights' tritium or fibre dots.

Named points tell the game how to hold and fit the weapon. Each is a position and a
direction:

  Muzzle    where shots leave and barrel attachments go; along the bore.
  Sight     the eye line through the iron sights (or the built-in optic); along the bore.
  Rail      where an optic sits on the top rail; along the bore.
  Under     the bottom of the handguard, for a foregrip; along the bore.
  Side      the right side of the handguard, for a laser; along the bore.
  Grip      where the right hand holds: the centre of the pistol grip. Its direction is up
            the grip (the hand's up), the hand facing forward across it.
  Support   where the left hand holds: under the handguard, a foregrip or a pump. Its
            direction is the hand's up.
  Mag       the bottom of the magazine well; the direction the magazine goes in (upwards).
  Butt      the back of the stock, against the shoulder.

The hands themselves (hands.py) are made to close round these points.
"""
import math
import bmesh
from mathutils import Vector, Matrix

ZONES = {"primary": 0, "dark": 1, "metal": 2, "glow": 3, "trim": 4}


# ---------------------------------------------------------------------------- shapes

class Shape:
    """A Part with the shapes weapons are made of."""

    def __init__(self, Part, name):
        self.part = Part(name)
        self.name = name

    @property
    def bm(self):
        return self.part.bm

    def box(self, x0, x1, y0, y1, z0, z1, zone, bevel=0.0015, segs=2, rot=(0, 0, 0), taper=None, taper_bottom=None):
        """An axis-aligned box between two corners."""
        centre = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
        size = (abs(x1 - x0), abs(y1 - y0), abs(z1 - z0))
        return self.part.box(centre, size, zone, bevel=bevel, segments=segs, rot=rot, taper=taper, taper_bottom=taper_bottom)

    def cbox(self, centre, size, zone, bevel=0.0015, segs=2, rot=(0, 0, 0), taper=None, taper_bottom=None):
        return self.part.box(centre, size, zone, bevel=bevel, segments=segs, rot=rot, taper=taper, taper_bottom=taper_bottom)

    def tube(self, z0, z1, r, zone, x=0.0, y=0.0, r2=None, segs=20, bevel=0.0):
        """A cylinder along the bore's direction."""
        return self.part.cylinder((x, y, z0), (x, y, z1), r, r if r2 is None else r2, zone, segments=segs, bevel=bevel)

    def rod(self, a, b, r, zone, r2=None, segs=12, bevel=0.0):
        """A cylinder between any two points."""
        return self.part.cylinder(a, b, r, r if r2 is None else r2, zone, segments=segs, bevel=bevel)

    def ball(self, centre, r, zone, scale=(1, 1, 1), u=16, v=10):
        return self.part.sphere(centre, r, zone, scale=scale, u=u, v=v)

    def lathe(self, profile, zone, segs=24, x=0.0, y=0.0):
        """A surface of revolution about a line along z: profile is [(z, radius)] back to front."""
        return self.part.lathe(profile, zone, segs, (x, y, 0))

    def ring(self, centre, axis, r_outer, r_inner, length, zone, segs=20):
        return self.part.ring(centre, axis, r_outer, r_inner, length, zone, segs)

    def prism(self, outline, x0, x1, zone, bevel=0.0012, segs=1):
        """
        A side profile drawn in (z, y), extruded across x from x0 to x1: the way most of a
        gun's silhouette is best described.
        """
        outline = _clean(outline)
        bm = self.bm
        left = [bm.verts.new((x0, y, z)) for z, y in outline]
        right = [bm.verts.new((x1, y, z)) for z, y in outline]
        bm.faces.new(left)
        bm.faces.new(list(reversed(right)))
        n = len(outline)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((left[j], left[i], right[i], right[j]))
        bevel = min(bevel, abs(x1 - x0) * 0.4)
        return self.part._finish(left + right, zone, bevel, segs)

    def plate(self, outline, y0, y1, zone, bevel=0.0008, segs=1):
        """A top-down outline drawn in (x, z), extruded up from y0 to y1."""
        outline = _clean(outline)
        bm = self.bm
        low = [bm.verts.new((x, y0, z)) for x, z in outline]
        high = [bm.verts.new((x, y1, z)) for x, z in outline]
        bm.faces.new(low)
        bm.faces.new(list(reversed(high)))
        n = len(outline)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((low[j], low[i], high[i], high[j]))
        bevel = min(bevel, abs(y1 - y0) * 0.4)
        return self.part._finish(low + high, zone, bevel, segs)

    def face(self, outline, z0, z1, zone, bevel=0.0006, segs=1):
        """An outline drawn in (x, y), across the bore, extruded along z from z0 to z1."""
        outline = _clean(outline)
        bm = self.bm
        back = [bm.verts.new((x, y, z0)) for x, y in outline]
        front = [bm.verts.new((x, y, z1)) for x, y in outline]
        bm.faces.new(back)
        bm.faces.new(list(reversed(front)))
        n = len(outline)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((back[j], back[i], front[i], front[j]))
        bevel = min(bevel, abs(z1 - z0) * 0.4)
        return self.part._finish(back + front, zone, bevel, segs)

    def ridges(self, z0, z1, pitch, y0, y1, half_width, zone, depth=0.0018, along=None):
        """Small raised bars across the top, as on a rail or a grip's checkering."""
        z = z0
        while z + pitch * 0.5 <= z1 + 1e-6:
            self.box(-half_width, half_width, y0, y1, z, z + pitch * 0.5, zone, bevel=0.0004, segs=1)
            z += pitch

    def transform(self, verts, matrix):
        for v in verts:
            v.co = matrix @ v.co


def _clean(outline):
    """Drops repeated points, which would make degenerate faces."""
    out = []
    for p in outline:
        if not out or (abs(p[0] - out[-1][0]) > 1e-7 or abs(p[1] - out[-1][1]) > 1e-7):
            out.append((float(p[0]), float(p[1])))
    if len(out) > 2 and abs(out[0][0] - out[-1][0]) < 1e-7 and abs(out[0][1] - out[-1][1]) < 1e-7:
        out.pop()
    return out


def arc(cz, cy, r, a0, a1, n=8):
    """Points on a circle in (z, y), from angle a0 to a1 in degrees (0 along +z, 90 along +y)."""
    return [(cz + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


def rounded(z0, z1, y0, y1, r, n=3):
    """A rectangle in (z, y) with rounded corners, anticlockwise from the bottom left."""
    r = min(r, abs(z1 - z0) / 2 - 1e-5, abs(y1 - y0) / 2 - 1e-5)
    pts = []
    pts += arc(z0 + r, y0 + r, r, 180, 270, n)
    pts += arc(z1 - r, y0 + r, r, 270, 360, n)
    pts += arc(z1 - r, y1 - r, r, 0, 90, n)
    pts += arc(z0 + r, y1 - r, r, 90, 180, n)
    return pts


# ---------------------------------------------------------------------------- weapons

class Gun:
    """A weapon being built: its meshes and its named points."""

    def __init__(self, Part, gid):
        self.Part = Part
        self.id = gid
        self.body = Shape(Part, gid)
        self.extra = {}
        self.points = {}

    def part(self, suffix):
        """One of the separate meshes: Mag, Stock or Irons."""
        if suffix not in self.extra:
            self.extra[suffix] = Shape(self.Part, self.id + "." + suffix)
        return self.extra[suffix]

    @property
    def mag(self):
        return self.part("Mag")

    @property
    def stock(self):
        return self.part("Stock")

    @property
    def irons(self):
        return self.part("Irons")

    def point(self, name, position, direction=(0, 0, 1)):
        d = Vector(direction).normalized()
        self.points[name] = (tuple(position), tuple(d))

    def objects(self):
        made = []
        for shape in [self.body] + list(self.extra.values()):
            obj = shape.part.to_object()
            obj["uv_scale"] = 6.0
            made.append(obj)
        made[0]["points"] = {k: list(p) + list(d) for k, (p, d) in self.points.items()}
        return made


def grip(shape, top_front, depth, length, rake, zone, half_width=0.0145, swell=0.004, bottom=0.007, grooves=0):
    """
    A pistol grip: drawn from the front of its top, raked back by `rake` degrees. Returns
    where a hand holds it (the middle of the grip, a little above half way) and the grip's
    up direction, for the Grip point.
    """
    a = math.radians(rake)
    down = Vector((-math.sin(a), -math.cos(a)))      # (z, y), down the grip
    fwd = Vector((math.cos(a), -math.sin(a)))        # across it, towards the front strap
    tf = Vector(top_front)
    front, back = [], []
    n = 10
    for i in range(n + 1):
        t = i / n
        bump = 0.0
        if grooves:
            # Finger grooves down the front strap.
            bump = 0.0016 * math.sin(math.pi * grooves * t) ** 2 if 0.15 < t < 0.95 else 0.0
        front.append(tf + down * (length * t) + fwd * bump)
        back.append(tf - fwd * (depth + swell * math.sin(math.pi * t)) + down * (length * t))
    # A rounded bottom from the front to the back.
    bottom_pts = []
    b0, b1 = front[-1], back[-1]
    for i in range(1, 5):
        t = i / 5
        p = b0 * (1 - t) + b1 * t + down * (bottom * math.sin(math.pi * t))
        bottom_pts.append(p)
    outline = [(p.x, p.y) for p in front] + [(p.x, p.y) for p in bottom_pts] + [(p.x, p.y) for p in reversed(back)]
    shape.prism(outline, -half_width, half_width, zone, bevel=0.003, segs=2)
    centre = tf - fwd * (depth * 0.5 + swell * 0.5) + down * (length * 0.4)
    up = Vector((0.0, math.cos(a), math.sin(a)))
    return (0.0, centre.y, centre.x), tuple(up)


def trigger_guard(shape, z_back, z_front, y_top, y_bottom, zone="dark", half_width=0.004, thickness=0.004):
    """A loop under the receiver round the trigger."""
    r = min(0.012, (z_front - z_back) / 3)
    outer = [(z_back, y_top), (z_back, y_bottom + r)] + arc(z_back + r, y_bottom + r, r, 180, 270, 3) + \
            arc(z_front - r, y_bottom + r, r, 270, 360, 3) + [(z_front, y_top)]
    t = thickness
    ri = max(r - t, 0.002)
    inner = [(z_front - t, y_top)] + arc(z_front - r, y_bottom + r, ri, 360, 270, 3) + \
            arc(z_back + r, y_bottom + r, ri, 270, 180, 3) + [(z_back + t, y_top)]
    shape.prism(outer + inner, -half_width, half_width, zone, bevel=0.001)


def trigger(shape, z, y_top, length=0.017, zone="metal"):
    """A curved trigger blade hanging from y_top at z."""
    pts_front, pts_back = [], []
    for i in range(6):
        t = i / 5
        curve = 0.006 * math.sin(t * math.pi * 0.5)
        pts_front.append((z - curve + 0.0015, y_top - length * t))
        pts_back.append((z - curve - 0.0015, y_top - length * t))
    shape.prism(pts_front + list(reversed(pts_back)), -0.003, 0.003, zone, bevel=0.0006)


def picatinny(shape, z0, z1, y, zone="dark", face="top", x=0.0, half_width=0.0106, height=0.0095, centre=None):
    """
    A Picatinny rail: a spine and the raised teeth on a 10 mm pitch. face is which way the
    rail faces: top, bottom, left or right; y (or x for the sides) is the surface it sits on.
    """
    teeth = []
    spine = height * 0.45
    if face == "top":
        shape.box(x - half_width * 0.85, x + half_width * 0.85, y, y + spine, z0, z1, zone, bevel=0.0008)
        z = z0 + 0.0025
        while z + 0.0052 <= z1:
            shape.box(x - half_width, x + half_width, y + spine * 0.6, y + height, z, z + 0.0052, zone, bevel=0.0007, segs=1,
                      taper=(0.82, 1.0))
            z += 0.01
    elif face == "bottom":
        shape.box(x - half_width * 0.85, x + half_width * 0.85, y - spine, y, z0, z1, zone, bevel=0.0008)
        z = z0 + 0.0025
        while z + 0.0052 <= z1:
            shape.box(x - half_width, x + half_width, y - height, y - spine * 0.6, z, z + 0.0052, zone, bevel=0.0007, segs=1,
                      taper_bottom=(0.82, 1.0))
            z += 0.01
    else:
        s = 1 if face == "right" else -1
        cy = y if centre is None else centre
        shape.box(x if s > 0 else x - spine, x + spine if s > 0 else x, cy - half_width * 0.85, cy + half_width * 0.85, z0, z1, zone, bevel=0.0008)
        z = z0 + 0.0025
        while z + 0.0052 <= z1:
            a, b = (x + spine * 0.6, x + height) if s > 0 else (x - height, x - spine * 0.6)
            shape.box(a, b, cy - half_width, cy + half_width, z, z + 0.0052, zone, bevel=0.0007, segs=1)
            z += 0.01


def curved_mag(shape, z_front, z_back, y_top, length, radius, half_width, zone, base_zone=None, ribs=True, plate=0.004):
    """
    A magazine curving forward as it goes down (an AK's, gently a STANAG's), from the well
    at y_top: the front edge is an arc of `radius` about a centre ahead of it.
    """
    d = z_front - z_back
    cz, cy = z_front + radius, y_top
    sweep = length / (radius + d / 2)
    n = 10
    front = [(cz - radius * math.cos(sweep * i / n), cy - radius * math.sin(sweep * i / n)) for i in range(n + 1)]
    back = [(cz - (radius + d) * math.cos(sweep * i / n), cy - (radius + d) * math.sin(sweep * i / n)) for i in range(n + 1)]
    shape.prism(front + list(reversed(back)), -half_width, half_width, zone, bevel=0.0018, segs=2)
    if ribs:
        # Two stiffening ribs down each side.
        for k in (0.3, 0.7):
            r = radius + d * k
            rib = [(cz - r * math.cos(sweep * i / n), cy - r * math.sin(sweep * i / n)) for i in range(1, n)]
            rib2 = [(cz - (r + 0.004) * math.cos(sweep * i / n), cy - (r + 0.004) * math.sin(sweep * i / n)) for i in range(n - 1, 0, -1)]
            shape.prism(rib + rib2, -half_width - 0.0012, half_width + 0.0012, zone, bevel=0.0005)
    # The floor plate.
    a = sweep
    bz0, by0 = cz - radius * math.cos(a), cy - radius * math.sin(a)
    bz1, by1 = cz - (radius + d) * math.cos(a), cy - (radius + d) * math.sin(a)
    tz, ty = math.sin(a), -math.cos(a)  # the downward normal of the plate, in (z, y)
    corners = [(bz0 + 0.003 * math.cos(a), by0 + 0.003 * math.sin(a)), (bz1 - 0.003 * math.cos(a), by1 - 0.003 * math.sin(a))]
    plate_outline = [corners[0], corners[1], (corners[1][0] + tz * plate, corners[1][1] + ty * plate), (corners[0][0] + tz * plate, corners[0][1] + ty * plate)]
    shape.prism(plate_outline, -half_width - 0.0015, half_width + 0.0015, base_zone or zone, bevel=0.0012)
    return sweep


def straight_mag(shape, z_front, z_back, y_top, length, half_width, zone, tilt=0.0, plate=0.004, base_zone=None, plate_extra=0.0015):
    """A straight box magazine, leaning back by `tilt` degrees as it goes down."""
    a = math.radians(tilt)
    dz, dy = -math.sin(a) * length, -math.cos(a) * length
    outline = [(z_front, y_top), (z_front + dz, y_top + dy), (z_back + dz, y_top + dy), (z_back, y_top)]
    shape.prism(outline, -half_width, half_width, zone, bevel=0.0018, segs=2)
    px, py = -math.sin(a), -math.cos(a)
    plate_outline = [(z_front + dz + 0.002, y_top + dy + 0.001), (z_front + dz + 0.002 + px * plate, y_top + dy + py * plate),
                     (z_back + dz - 0.002 + px * plate, y_top + dy + py * plate), (z_back + dz - 0.002, y_top + dy + 0.001)]
    shape.prism(plate_outline, -half_width - plate_extra, half_width + plate_extra, base_zone or zone, bevel=0.0012)


def front_post(shape, z, y_base, y_top, zone="dark", glow=True, ears=0.0):
    """A front sight post, with protective ears if asked, and a dot at the tip."""
    shape.box(-0.0012, 0.0012, y_base, y_top, z - 0.0015, z + 0.0015, zone, bevel=0.0003, segs=1)
    if glow:
        shape.box(-0.0013, 0.0013, y_top - 0.0025, y_top, z - 0.0016, z + 0.0016, "glow", bevel=0.0, segs=1)
    if ears:
        for s in (-1, 1):
            shape.box(s * 0.0045 - 0.0012, s * 0.0045 + 0.0012, y_base, y_top + 0.001, z - 0.004, z + 0.004, zone, bevel=0.0004)


def rear_aperture(shape, z, y_centre, zone="dark", base=None, width=0.016):
    """A rear peep sight: a plate with a ring round the eye line."""
    y_base = y_centre - 0.012 if base is None else base
    shape.box(-width / 2, width / 2, y_base, y_centre - 0.0035, z - 0.003, z + 0.003, zone, bevel=0.0008)
    shape.ring((0, y_centre, z), (0, 0, 1), 0.0045, 0.0018, 0.004, zone, 16)
    for s in (-1, 1):
        shape.box(s * 0.0055 - 0.002, s * 0.0055 + 0.002, y_centre - 0.004, y_centre + 0.004, z - 0.002, z + 0.002, zone, bevel=0.0005)


def rear_notch(shape, z, y_top, zone="dark", width=0.02, height=0.006, notch=0.0035, dots=True):
    """A rear notch sight (a pistol's, an AK's): a blade with a square notch."""
    w, h = width / 2, height
    outline = [(-w, y_top - h), (w, y_top - h), (w, y_top), (notch / 2, y_top), (notch / 2, y_top - h * 0.55),
               (-notch / 2, y_top - h * 0.55), (-notch / 2, y_top), (-w, y_top)]
    shape.face(outline, z - 0.002, z + 0.002, zone, bevel=0.0003)
    if dots:
        for s in (-1, 1):
            shape.box(s * notch * 1.2 - 0.0009, s * notch * 1.2 + 0.0009, y_top - 0.0032, y_top - 0.0014, z - 0.0021, z + 0.0021, "glow", bevel=0.0)


def scope(shape, z_back, z_front, y, tube_r=0.015, objective_r=0.024, eye_r=0.02, zone="dark", turrets=True, rings=None, rail_y=None):
    """A riflescope along the bore at height y, with its rings down to rail_y."""
    L = z_front - z_back
    prof = [(z_back, 0.0), (z_back, eye_r * 0.82), (z_back + 0.004, eye_r), (z_back + L * 0.18, eye_r), (z_back + L * 0.26, tube_r),
            (z_back + L * 0.66, tube_r), (z_back + L * 0.78, objective_r), (z_front - 0.004, objective_r), (z_front, objective_r * 0.86), (z_front, 0.0)]
    shape.lathe(prof, zone, 28, y=y)
    shape.lathe([(z_front - 0.0012, 0.0), (z_front - 0.0012, objective_r * 0.84), (z_front + 0.0004, objective_r * 0.84), (z_front + 0.0004, 0.0)], "glow", 28, y=y)
    if turrets:
        zc = z_back + L * 0.46
        shape.rod((0, y + tube_r * 0.6, zc), (0, y + tube_r + 0.011, zc), 0.0095, "dark", segs=16)
        shape.rod((tube_r * 0.6, y, zc), (tube_r + 0.011, y, zc), 0.0095, "dark", segs=16)
        shape.rod((-tube_r * 0.6, y, zc + 0.008), (-tube_r - 0.008, y, zc + 0.008), 0.008, "dark", segs=16)
        shape.box(-tube_r * 0.95, tube_r * 0.95, y - tube_r * 0.95, y + tube_r * 0.95, zc - 0.022, zc + 0.022, zone, bevel=0.004, segs=2)
    if rings and rail_y is not None:
        for zr in rings:
            shape.ring((0, y, zr), (0, 0, 1), tube_r + 0.004, tube_r - 0.0005, 0.012, "dark", 20)
            shape.box(-0.009, 0.009, rail_y, y - tube_r, zr - 0.006, zr + 0.006, "dark", bevel=0.001)
            shape.box(-0.013, 0.013, rail_y, rail_y + 0.006, zr - 0.008, zr + 0.008, "dark", bevel=0.001)


def muzzle_brake(shape, z, r, length, zone="dark", ports=3):
    """A slotted muzzle device from z forward."""
    shape.tube(z, z + length, r, zone, segs=16, bevel=0.0008)
    for i in range(ports):
        zc = z + length * (0.25 + 0.5 * i / max(ports - 1, 1))
        for s in (-1, 1):
            shape.box(s * r * 0.7, s * (r + 0.0006), -r * 0.45, r * 0.45, zc - 0.0022, zc + 0.0022, "metal", bevel=0.0)


def flash_hider(shape, z, r, length, zone="dark"):
    """A birdcage flash hider: a tube with slots."""
    shape.tube(z, z + length * 0.25, r * 0.85, zone, segs=16)
    shape.tube(z + length * 0.25, z + length, r, zone, segs=16, bevel=0.0006)
    for k in range(5):
        a = math.radians(30 + k * 60)
        cx, cy = math.cos(a) * r, math.sin(a) * r
        shape.cbox((cx, cy, z + length * 0.62), (0.0026, 0.0026, length * 0.6), "metal", bevel=0.0, rot=(0, 0, math.degrees(a)))


# ---------------------------------------------------------------------------- assault rifles

def ar15(Part, gid, barrel_end, handguard_end, butt, fixed_stock=False, carry_handle=False):
    """The AR-15 family: the M4A1 carbine and the M16A4 rifle."""
    g = Gun(Part, gid)
    b = g.body
    # Upper receiver, with its flat-top rail, ejection port, forward assist and charging handle.
    b.box(-0.0135, 0.0135, -0.016, 0.0175, -0.105, 0.075, "primary", bevel=0.003)
    picatinny(b, -0.102, 0.072, 0.0175, "primary")
    b.box(0.0133, 0.0152, -0.006, 0.01, -0.045, 0.02, "dark", bevel=0.0008)
    b.box(0.0133, 0.021, 0.0, 0.012, -0.064, -0.05, "primary", bevel=0.002)
    b.rod((0.011, 0.004, -0.084), (0.025, 0.004, -0.076), 0.0055, "dark", segs=12)
    b.box(-0.011, 0.011, 0.009, 0.017, -0.12, -0.103, "dark", bevel=0.001)
    # Lower receiver: the magazine well, the trigger and the pistol grip.
    lower = [(0.095, -0.016), (0.098, -0.067), (0.091, -0.071), (0.033, -0.071), (0.031, -0.05), (-0.03, -0.05),
             (-0.1, -0.045), (-0.105, -0.016)]
    b.prism(lower, -0.0125, 0.0125, "primary", bevel=0.0016)
    b.rod((0.0125, -0.03, 0.03), (0.016, -0.03, 0.03), 0.004, "dark", segs=10)
    b.rod((-0.0125, -0.028, -0.032), (-0.017, -0.028, -0.032), 0.0045, "dark", segs=10)
    b.box(-0.016, -0.0125, -0.035, -0.022, 0.005, 0.02, "dark", bevel=0.001)
    trigger_guard(b, -0.028, 0.033, -0.05, -0.074)
    trigger(b, 0.0, -0.05)
    g.point("Grip", *grip(b, (-0.026, -0.05), 0.044, 0.095, 22, "dark", grooves=3))
    # Receiver extension and, behind it, the stock.
    b.tube(-0.105, -0.29, 0.0145, "dark", y=-0.002, segs=18)
    b.ring((0, -0.002, -0.108), (0, 0, 1), 0.0175, 0.0145, 0.006, "dark", 18)
    s = g.stock
    if fixed_stock:
        s.prism([(-0.105, 0.016), (-0.2, 0.019), (butt + 0.008, 0.023), (butt, 0.021), (butt, -0.074), (butt + 0.01, -0.079),
                 (-0.2, -0.042), (-0.11, -0.04)], -0.02, 0.02, "primary", bevel=0.004, segs=2)
    else:
        s.prism([(-0.205, 0.022), (butt + 0.006, 0.031), (butt, 0.029), (butt, -0.07), (butt + 0.012, -0.075), (-0.29, -0.042),
                 (-0.215, -0.014), (-0.205, -0.008)], -0.021, 0.021, "primary", bevel=0.004, segs=2)
        s.box(-0.006, 0.006, -0.03, -0.014, -0.25, -0.215, "dark", bevel=0.002)
    s.box(-0.0215, 0.0215, -0.079, 0.033, butt - 0.01, butt + 0.001, "dark", bevel=0.003)
    # A quad-rail handguard round the barrel.
    b.ring((0, 0, 0.078), (0, 0, 1), 0.029, 0.01, 0.008, "primary", 24)
    b.box(-0.026, 0.026, -0.026, 0.026, 0.082, handguard_end, "primary", bevel=0.005, segs=2)
    picatinny(b, 0.085, handguard_end - 0.004, 0.026, "primary")
    picatinny(b, 0.085, handguard_end - 0.004, -0.026, "primary", face="bottom")
    picatinny(b, 0.1, handguard_end - 0.01, 0.0, "primary", face="right", x=0.026)
    picatinny(b, 0.1, handguard_end - 0.01, 0.0, "primary", face="left", x=-0.026)
    # The front sight base and gas block, then the barrel and flash hider.
    fsb = handguard_end + 0.004
    b.box(-0.011, 0.011, -0.016, 0.014, fsb, fsb + 0.026, "dark", bevel=0.002)
    b.prism([(fsb + 0.002, 0.014), (fsb + 0.024, 0.014), (fsb + 0.018, 0.052), (fsb + 0.008, 0.052)], -0.0062, 0.0062, "dark", bevel=0.0015)
    for sx in (-1, 1):
        b.box(sx * 0.0052 - 0.0014, sx * 0.0052 + 0.0014, 0.048, 0.068, fsb + 0.008, fsb + 0.018, "dark", bevel=0.0005)
    front_post(b, fsb + 0.013, 0.05, 0.066)
    b.box(-0.004, 0.004, -0.03, -0.016, fsb + 0.006, fsb + 0.018, "dark", bevel=0.001)
    b.tube(0.075, barrel_end, 0.0098, "metal", segs=18)
    flash_hider(b, barrel_end, 0.0112, 0.055)
    # Iron sights: a flip-up rear (or the carry handle's) that folds away under an optic.
    i = g.irons
    if carry_handle:
        i.prism([(-0.096, 0.0175), (0.01, 0.0175), (0.01, 0.028), (0.0, 0.05), (-0.068, 0.05), (-0.072, 0.058),
                 (-0.096, 0.058)], -0.0105, 0.0105, "primary", bevel=0.002)
        i.box(-0.006, 0.006, 0.0175, 0.044, -0.06, -0.005, "primary", bevel=0.001)
        rear_aperture(i, -0.084, 0.066, base=0.056)
    else:
        i.box(-0.011, 0.011, 0.0265, 0.042, -0.098, -0.08, "dark", bevel=0.001)
        rear_aperture(i, -0.088, 0.066, base=0.04)
    # A 30-round STANAG magazine.
    curved_mag(g.mag, 0.093, 0.033, -0.02, 0.195, 0.6, 0.0118, "primary")
    hg_mid = (0.082 + handguard_end) / 2
    g.point("Muzzle", (0, 0, barrel_end + 0.055))
    g.point("Eye", (0, 0.066, -0.17))
    g.point("Rail", (0, 0.027, -0.035))
    g.point("Under", (0, -0.0355, hg_mid + 0.02))
    g.point("Side", (0.0355, 0, hg_mid))
    g.point("Support", (0, -0.0355, hg_mid + 0.005), (0, 1, 0))
    g.point("Mag", (0, -0.069, 0.063), (0, 1, 0))
    g.point("Butt", (0, -0.02, butt - 0.01))
    return g


def ak47(Part):
    g = Gun(Part, "ar_ak47")
    b = g.body
    # The receiver and its rounded dust cover, the rear sight block, the charging handle.
    b.box(-0.0145, 0.0145, -0.036, 0.012, -0.13, 0.12, "dark", bevel=0.002)
    b.box(-0.0135, 0.0135, 0.006, 0.021, -0.128, 0.086, "dark", bevel=0.0065, segs=3)
    b.box(-0.0125, 0.0125, 0.006, 0.026, 0.086, 0.122, "dark", bevel=0.003)
    rear_notch(b, 0.112, 0.036, width=0.018, dots=False)
    b.box(-0.0035, 0.0035, 0.026, 0.031, 0.088, 0.112, "dark", bevel=0.0005)
    b.box(0.0143, 0.0156, -0.006, 0.008, -0.025, 0.065, "metal", bevel=0.0006)
    b.rod((0.0145, 0.003, 0.058), (0.031, 0.003, 0.058), 0.0035, "metal", segs=10)
    b.ball((0.032, 0.003, 0.058), 0.0055, "metal", scale=(1, 0.8, 1.3))
    b.prism([(-0.105, -0.004), (0.02, -0.004), (0.026, -0.012), (-0.1, -0.012)], 0.0145, 0.0168, "dark", bevel=0.0006)
    for z in (-0.11, -0.04, 0.03, 0.1):
        b.rod((-0.016, -0.026, z), (0.016, -0.026, z), 0.0018, "metal", segs=8)
    trigger_guard(b, -0.026, 0.032, -0.036, -0.061)
    trigger(b, 0.0, -0.036)
    g.point("Grip", *grip(b, (-0.026, -0.036), 0.042, 0.094, 24, "primary", half_width=0.0145))
    # Wooden handguards round the gas tube and barrel, the gas block, the front sight.
    b.box(-0.021, 0.021, -0.036, 0.004, 0.122, 0.305, "primary", bevel=0.007, segs=3)
    for z in (0.17, 0.2, 0.23, 0.26):
        b.box(-0.0215, 0.0215, -0.028, -0.024, z, z + 0.012, "dark", bevel=0.0)
    b.tube(0.122, 0.33, 0.0105, "primary", y=0.016, segs=18)
    b.tube(0.3, 0.335, 0.0095, "dark", y=0.016, segs=16)
    b.box(-0.011, 0.011, -0.013, 0.027, 0.33, 0.352, "dark", bevel=0.002)
    b.tube(0.12, 0.49, 0.0085, "metal", segs=16)
    b.box(-0.009, 0.009, -0.012, 0.012, 0.455, 0.49, "dark", bevel=0.002)
    b.prism([(0.462, 0.012), (0.485, 0.012), (0.482, 0.03), (0.466, 0.03)], -0.0075, 0.0075, "dark", bevel=0.001)
    front_post(b, 0.474, 0.026, 0.036, ears=1)
    b.tube(0.49, 0.505, 0.0098, "dark", segs=16)
    b.rod((0, -0.017, 0.335), (0, -0.017, 0.478), 0.0028, "metal", segs=8)
    # The wooden stock.
    s = g.stock
    s.prism([(-0.124, 0.006), (-0.2, 0.0), (-0.386, -0.012), (-0.39, -0.014), (-0.39, -0.112), (-0.374, -0.116), (-0.2, -0.062),
             (-0.124, -0.036)], -0.019, 0.019, "primary", bevel=0.004, segs=2)
    s.box(-0.0195, 0.0195, -0.117, -0.01, -0.396, -0.388, "dark", bevel=0.002)
    # Thirty rounds in the curved steel magazine.
    curved_mag(g.mag, 0.1, 0.036, -0.026, 0.205, 0.3, 0.0145, "dark")
    g.point("Muzzle", (0, 0, 0.505))
    g.point("Eye", (0, 0.036, -0.2))
    g.point("Rail", (0, 0.034, -0.03))
    g.point("Under", (0, -0.036, 0.235))
    g.point("Side", (0.021, -0.012, 0.22))
    g.point("Support", (0, -0.036, 0.215), (0, 1, 0))
    g.point("Mag", (0, -0.036, 0.068), (0, 1, 0))
    g.point("Butt", (0, -0.06, -0.396))
    # A side-rail mount, shown under an optic.
    m = g.part("Mount")
    m.box(-0.032, -0.0145, -0.01, 0.026, -0.07, 0.03, "dark", bevel=0.002)
    m.box(-0.032, 0.012, 0.026, 0.034, -0.065, 0.025, "dark", bevel=0.002)
    return g


def famas(Part):
    g = Gun(Part, "ar_famas")
    b = g.body
    # A bullpup: the action and magazine behind the grip, the cheek on the receiver.
    b.prism([(-0.33, 0.016), (-0.33, -0.082), (-0.31, -0.09), (-0.22, -0.05), (-0.09, -0.042), (0.12, -0.04), (0.12, 0.018)],
            -0.0215, 0.0215, "primary", bevel=0.005, segs=2)
    b.box(-0.022, 0.022, -0.09, 0.018, -0.338, -0.329, "dark", bevel=0.003)
    b.box(-0.02, 0.02, -0.033, 0.016, 0.12, 0.255, "primary", bevel=0.006, segs=2)
    for z in (0.15, 0.18, 0.21):
        b.box(-0.0205, 0.0205, -0.015, -0.007, z, z + 0.018, "dark", bevel=0.0)
    for sx in (-1, 1):
        b.rod((sx * 0.021, -0.016, 0.0), (sx * 0.021, -0.016, 0.24), 0.0038, "dark", segs=8)
    b.tube(0.255, 0.405, 0.0088, "metal", segs=16)
    b.tube(0.395, 0.428, 0.0112, "dark", segs=16)
    # The long carry handle over everything, with the sights inside it.
    b.prism([(-0.28, 0.018), (-0.28, 0.074), (0.205, 0.074), (0.205, 0.018), (0.185, 0.018), (0.185, 0.06), (-0.26, 0.06),
             (-0.26, 0.018)], -0.0075, 0.0075, "primary", bevel=0.0025)
    b.box(-0.006, 0.006, 0.026, 0.06, 0.03, 0.08, "dark", bevel=0.001)
    rear_aperture(b, -0.25, 0.049, base=0.04)
    front_post(b, 0.18, 0.034, 0.049, ears=1)
    picatinny(b, -0.2, 0.15, 0.074, "dark", half_width=0.0075, height=0.006)
    trigger_guard(b, -0.03, 0.034, -0.04, -0.066)
    trigger(b, 0.0, -0.04)
    g.point("Grip", *grip(b, (-0.026, -0.04), 0.042, 0.092, 16, "primary"))
    straight_mag(g.mag, -0.098, -0.158, -0.03, 0.135, 0.0118, "primary")
    g.point("Muzzle", (0, 0, 0.428))
    g.point("Eye", (0, 0.049, -0.33))
    g.point("Rail", (0, 0.08, -0.06))
    g.point("Under", (0, -0.033, 0.2))
    g.point("Side", (0.02, -0.008, 0.19))
    g.point("Support", (0, -0.033, 0.19), (0, 1, 0))
    g.point("Mag", (0, -0.044, -0.128), (0, 1, 0))
    g.point("Butt", (0, -0.035, -0.338))
    return g


# ---------------------------------------------------------------------------- submachine guns

def mp5(Part, gid, suppressed=False):
    g = Gun(Part, gid)
    b = g.body
    # The stamped receiver and the cocking tube above the barrel.
    b.box(-0.0155, 0.0155, -0.024, 0.022, -0.125, 0.165, "primary", bevel=0.009, segs=3)
    b.tube(0.165, 0.27, 0.011, "primary", y=0.011, segs=18)
    b.rod((-0.011, 0.014, 0.245), (-0.03, 0.017, 0.24), 0.0032, "dark", segs=8)
    b.ball((-0.031, 0.017, 0.24), 0.0045, "dark")
    b.box(0.0153, 0.0162, -0.004, 0.01, -0.03, 0.03, "dark", bevel=0.0005)
    for z in (-0.07, 0.05):
        b.box(-0.0095, 0.0095, 0.021, 0.025, z - 0.006, z + 0.006, "dark", bevel=0.001)
    # Trigger housing and grip.
    b.prism([(0.045, -0.022), (0.045, -0.042), (-0.03, -0.046), (-0.112, -0.04), (-0.112, -0.022)], -0.016, 0.016, "dark", bevel=0.002)
    trigger_guard(b, -0.028, 0.03, -0.044, -0.068)
    trigger(b, 0.0, -0.044)
    g.point("Grip", *grip(b, (-0.026, -0.044), 0.044, 0.09, 20, "dark", grooves=3))
    b.box(-0.013, 0.013, -0.034, -0.02, 0.05, 0.102, "primary", bevel=0.002)
    # The rear drum sight and the hooded front post.
    # The rotary drum sits below the eye line, its aperture on top.
    b.rod((-0.012, 0.027, -0.105), (0.012, 0.027, -0.105), 0.0095, "dark", segs=16)
    b.box(-0.006, 0.006, 0.02, 0.03, -0.112, -0.098, "dark", bevel=0.001)
    b.box(-0.0035, 0.0035, 0.034, 0.038, -0.108, -0.102, "dark", bevel=0.0005)
    b.ring((0, 0.041, -0.105), (0, 0, 1), 0.0042, 0.0018, 0.005, "dark", 14)
    b.box(-0.008, 0.008, 0.016, 0.032, 0.262, 0.284, "primary", bevel=0.002)
    b.ring((0, 0.042, 0.273), (0, 0, 1), 0.0095, 0.0075, 0.014, "dark", 18)
    front_post(b, 0.273, 0.03, 0.041)
    if suppressed:
        b.tube(0.165, 0.43, 0.0205, "primary", segs=24, bevel=0.003)
        b.tube(0.15, 0.3, 0.0245, "dark", segs=10, bevel=0.002)
        b.tube(0.428, 0.432, 0.012, "dark", segs=16)
        muzzle = 0.432
        hg_mid = 0.225
        under_y = -0.0245
    else:
        b.box(-0.0195, 0.0195, -0.031, 0.006, 0.122, 0.268, "dark", bevel=0.008, segs=3)
        b.tube(0.268, 0.31, 0.0088, "metal", segs=16)
        b.tube(0.298, 0.322, 0.0108, "dark", segs=16)
        for k in range(3):
            a = math.radians(90 + k * 120)
            b.cbox((math.cos(a) * 0.011, math.sin(a) * 0.011, 0.31), (0.004, 0.004, 0.008), "dark", bevel=0.0)
        muzzle = 0.322
        hg_mid = 0.2
        under_y = -0.031
    # A retractable stock: two struts and a butt plate.
    s = g.stock
    s.box(-0.017, 0.017, -0.032, 0.016, -0.135, -0.124, "dark", bevel=0.003)
    for sx in (-1, 1):
        s.rod((sx * 0.0165, -0.006, -0.13), (sx * 0.0165, -0.024, -0.345), 0.0045, "metal", segs=10)
    s.prism([(-0.335, 0.004), (-0.362, 0.006), (-0.364, -0.072), (-0.338, -0.074)], -0.022, 0.022, "dark", bevel=0.003)
    curved_mag(g.mag, 0.098, 0.057, -0.026, 0.205, 0.36, 0.0112, "primary")
    g.point("Muzzle", (0, 0, muzzle))
    g.point("Eye", (0, 0.041, -0.2))
    g.point("Rail", (0, 0.034, -0.035))
    g.point("Under", (0, under_y, hg_mid + 0.02))
    g.point("Side", (0.02, -0.008, hg_mid))
    g.point("Support", (0, under_y, hg_mid), (0, 1, 0))
    g.point("Mag", (0, -0.034, 0.077), (0, 1, 0))
    g.point("Butt", (0, -0.034, -0.364))
    # The claw mount an optic sits on.
    m = g.part("Mount")
    m.box(-0.0125, 0.0125, 0.022, 0.0335, -0.09, 0.02, "dark", bevel=0.002)
    for z in (-0.07, 0.05):
        m.box(-0.017, 0.017, 0.012, 0.026, z - 0.008, z + 0.008, "dark", bevel=0.001)
    return g


def ump45(Part):
    g = Gun(Part, "smg_ump45")
    b = g.body
    b.prism([(-0.13, 0.024), (0.19, 0.024), (0.203, 0.012), (0.203, -0.03), (0.13, -0.034), (0.11, -0.04), (-0.13, -0.04)],
            -0.0215, 0.0215, "primary", bevel=0.004, segs=2)
    picatinny(b, -0.115, 0.12, 0.024, "primary")
    picatinny(b, 0.135, 0.195, -0.032, "primary", face="bottom")
    b.box(0.0213, 0.0222, -0.006, 0.012, -0.04, 0.03, "dark", bevel=0.0006)
    b.rod((-0.0215, 0.012, 0.13), (-0.036, 0.012, 0.13), 0.0035, "dark", segs=8)
    b.tube(0.203, 0.228, 0.0095, "metal", segs=16)
    b.tube(0.226, 0.243, 0.0112, "dark", segs=16)
    b.box(-0.008, 0.008, 0.024, 0.035, 0.168, 0.186, "dark", bevel=0.001)
    b.ring((0, 0.047, 0.177), (0, 0, 1), 0.0085, 0.0065, 0.014, "dark", 16)
    front_post(b, 0.177, 0.034, 0.047)
    trigger_guard(b, -0.026, 0.045, -0.04, -0.07, half_width=0.006)
    trigger(b, 0.0, -0.04)
    g.point("Grip", *grip(b, (-0.026, -0.04), 0.043, 0.09, 17, "primary", grooves=3))
    rear_aperture(g.irons, -0.1, 0.047, base=0.0335)
    s = g.stock
    s.prism([(-0.13, 0.022), (-0.37, 0.022), (-0.37, 0.012), (-0.13, 0.01)], -0.009, 0.009, "dark", bevel=0.002)
    s.prism([(-0.13, -0.03), (-0.355, -0.06), (-0.355, -0.072), (-0.13, -0.044)], -0.009, 0.009, "dark", bevel=0.002)
    s.prism([(-0.36, 0.025), (-0.392, 0.026), (-0.392, -0.076), (-0.36, -0.074)], -0.02, 0.02, "dark", bevel=0.003)
    straight_mag(g.mag, 0.108, 0.064, -0.03, 0.165, 0.0135, "primary", tilt=-5)
    g.point("Muzzle", (0, 0, 0.243))
    g.point("Eye", (0, 0.047, -0.2))
    g.point("Rail", (0, 0.0335, -0.03))
    g.point("Under", (0, -0.0415, 0.165))
    g.point("Side", (0.0215, -0.006, 0.16))
    g.point("Support", (0, -0.0415, 0.16), (0, 1, 0))
    g.point("Mag", (0, -0.04, 0.086), (0, 1, 0))
    g.point("Butt", (0, -0.025, -0.392))
    return g


def p90(Part):
    g = Gun(Part, "smg_p90")
    b = g.body
    # The sculpted body: a long top, the front loop the support hand holds, a thumbhole
    # behind the grip and the deep butt.
    b.prism([(-0.3, 0.028), (0.13, 0.028), (0.175, 0.006), (0.19, -0.012), (0.19, -0.03), (0.14, -0.036), (0.112, -0.068),
             (0.085, -0.084), (0.06, -0.084), (0.045, -0.062), (0.04, -0.04), (-0.07, -0.04), (-0.105, -0.07), (-0.16, -0.098),
             (-0.29, -0.102), (-0.3, -0.09)], -0.0265, 0.0265, "primary", bevel=0.006, segs=2)
    b.box(-0.027, 0.027, -0.1, 0.03, -0.306, -0.296, "dark", bevel=0.003)
    b.prism([(0.06, -0.062), (0.072, -0.062), (0.075, -0.072), (0.063, -0.072)], -0.027, 0.027, "dark", bevel=0.001)
    b.tube(0.175, 0.21, 0.0088, "metal", segs=16)
    b.tube(0.2, 0.226, 0.0108, "dark", segs=16)
    for sx in (-1, 1):
        b.rod((sx * 0.027, 0.004, -0.02), (sx * 0.034, 0.004, -0.02), 0.004, "dark", segs=8)
    trigger(b, 0.0, -0.04)
    g.point("Grip", *grip(b, (-0.026, -0.04), 0.04, 0.072, 6, "primary", half_width=0.016))
    # The ring sight on top.
    i = g.irons
    i.box(-0.019, 0.019, 0.052, 0.06, -0.1, -0.02, "dark", bevel=0.003)
    for sx in (-1, 1):
        i.box(sx * 0.0165 - 0.0025, sx * 0.0165 + 0.0025, 0.06, 0.088, -0.1, -0.02, "dark", bevel=0.0015)
    i.box(-0.019, 0.019, 0.084, 0.09, -0.1, -0.02, "dark", bevel=0.002)
    i.ring((0, 0.072, -0.03), (0, 0, 1), 0.0062, 0.0052, 0.0015, "glow", 20)
    # Fifty rounds lying along the top.
    m = g.mag
    m.box(-0.0215, 0.0215, 0.028, 0.052, -0.215, 0.11, "dark", bevel=0.004, segs=2)
    m.box(-0.022, 0.022, 0.03, 0.05, 0.095, 0.12, "dark", bevel=0.003)
    g.point("Muzzle", (0, 0, 0.226))
    g.point("Eye", (0, 0.072, -0.24))
    g.point("Rail", (0, 0.062, -0.055))
    g.point("Under", (0, -0.036, 0.15))
    g.point("Side", (0.0265, -0.012, 0.14))
    g.point("Support", (0, -0.036, 0.15), (0, 1, 0))
    g.point("Mag", (0, 0.028, -0.05), (0, -1, 0))
    g.point("Butt", (0, -0.04, -0.306))
    return g


def mac10(Part):
    g = Gun(Part, "smg_mac10")
    b = g.body
    b.box(-0.0245, 0.0245, -0.05, 0.016, -0.125, 0.15, "primary", bevel=0.003)
    b.box(-0.0035, 0.0035, 0.0155, 0.0168, -0.085, 0.12, "dark", bevel=0.0)
    b.rod((0, 0.016, 0.07), (0, 0.03, 0.07), 0.0045, "dark", segs=10)
    b.ball((0, 0.031, 0.07), 0.0062, "dark")
    b.tube(0.15, 0.172, 0.0088, "metal", segs=16)
    b.tube(0.17, 0.19, 0.0105, "dark", segs=16)
    rear_aperture(b, -0.108, 0.027, base=0.016, width=0.02)
    front_post(b, 0.135, 0.016, 0.027, ears=1)
    for sx in (-1, 1):
        b.rod((sx * 0.026, -0.042, -0.13), (sx * 0.026, -0.042, 0.1), 0.003, "metal", segs=8)
    b.box(-0.03, 0.03, -0.062, -0.02, -0.138, -0.128, "dark", bevel=0.002)
    # A strap under the front for the support hand.
    b.box(-0.011, 0.011, -0.062, -0.05, 0.05, 0.14, "dark", bevel=0.003)
    b.box(-0.011, 0.011, -0.062, -0.049, 0.135, 0.145, "dark", bevel=0.002)
    trigger_guard(b, -0.026, 0.036, -0.05, -0.074)
    trigger(b, 0.0, -0.05)
    g.point("Grip", *grip(b, (-0.026, -0.05), 0.041, 0.1, 6, "primary"))
    straight_mag(g.mag, -0.031, -0.066, -0.06, 0.2, 0.0108, "dark", tilt=6)
    g.point("Muzzle", (0, 0, 0.19))
    g.point("Eye", (0, 0.027, -0.3))
    g.point("Rail", (0, 0.016, -0.03))
    g.point("Under", (0, -0.05, 0.09))
    g.point("Side", (0.0245, -0.02, 0.09))
    g.point("Support", (0, -0.062, 0.095), (0, 1, 0))
    g.point("Mag", (0, -0.152, -0.06), (0, math.cos(math.radians(6)), math.sin(math.radians(6))))
    g.point("Butt", (0, -0.03, -0.138))
    return g


# ---------------------------------------------------------------------------- machine guns

def m249(Part):
    g = Gun(Part, "lmg_m249")
    b = g.body
    b.box(-0.029, 0.029, -0.046, 0.034, -0.14, 0.172, "primary", bevel=0.004)
    b.box(-0.027, 0.027, 0.034, 0.05, -0.065, 0.135, "primary", bevel=0.004)
    picatinny(b, -0.055, 0.125, 0.05, "primary")
    b.box(0.029, 0.031, -0.008, 0.016, -0.06, 0.05, "dark", bevel=0.0006)
    b.rod((0.029, 0.004, 0.09), (0.046, 0.004, 0.09), 0.004, "dark", segs=8)
    # Feed tray and a belt running in from the left.
    b.box(-0.042, -0.029, 0.006, 0.026, 0.02, 0.06, "dark", bevel=0.002)
    b.box(-0.0295, 0.0295, -0.046, 0.002, 0.172, 0.33, "primary", bevel=0.005)
    picatinny(b, 0.18, 0.32, -0.046, "primary", face="bottom")
    b.tube(0.172, 0.555, 0.0118, "metal", segs=18)
    b.box(-0.016, 0.016, 0.012, 0.024, 0.2, 0.42, "dark", bevel=0.003)
    b.box(-0.015, 0.015, -0.04, 0.0, 0.33, 0.37, "dark", bevel=0.002)
    for sx in (-1, 1):
        b.rod((sx * 0.012, -0.03, 0.35), (sx * 0.012, -0.03, 0.55), 0.0045, "dark", segs=8)
    b.box(-0.052, -0.04, -0.004, 0.02, 0.26, 0.36, "dark", bevel=0.004)
    b.box(-0.045, -0.029, 0.004, 0.012, 0.29, 0.33, "dark", bevel=0.001)
    b.box(-0.0065, 0.0065, 0.0, 0.05, 0.522, 0.538, "dark", bevel=0.0015)
    front_post(b, 0.53, 0.05, 0.07)
    flash_hider(b, 0.555, 0.0138, 0.05)
    trigger_guard(b, -0.028, 0.035, -0.046, -0.072)
    trigger(b, 0.0, -0.046)
    g.point("Grip", *grip(b, (-0.026, -0.046), 0.045, 0.095, 18, "dark", grooves=3))
    s = g.stock
    s.prism([(-0.14, 0.03), (-0.43, 0.03), (-0.44, 0.026), (-0.44, -0.088), (-0.42, -0.094), (-0.25, -0.06), (-0.14, -0.046)],
            -0.021, 0.021, "primary", bevel=0.004, segs=2)
    s.box(-0.022, 0.022, -0.095, 0.032, -0.452, -0.44, "dark", bevel=0.003)
    rear_aperture(g.irons, -0.09, 0.07, base=0.0595)
    m = g.mag
    m.box(-0.07, 0.0, -0.17, -0.045, 0.02, 0.15, "dark", bevel=0.012, segs=3)
    m.box(-0.071, 0.001, -0.06, -0.045, 0.03, 0.14, "dark", bevel=0.004)
    g.point("Muzzle", (0, 0, 0.605))
    g.point("Eye", (0, 0.07, -0.25))
    g.point("Rail", (0, 0.0595, 0.02))
    g.point("Under", (0, -0.0555, 0.255))
    g.point("Side", (0.0295, -0.02, 0.25))
    g.point("Support", (0, -0.0555, 0.24), (0, 1, 0))
    g.point("Mag", (-0.035, -0.046, 0.085), (0, 1, 0))
    g.point("Butt", (0, -0.03, -0.452))
    return g


def pkm(Part):
    g = Gun(Part, "lmg_pkm")
    b = g.body
    b.box(-0.026, 0.026, -0.042, 0.02, -0.165, 0.2, "dark", bevel=0.003)
    b.box(-0.025, 0.025, 0.02, 0.038, -0.06, 0.16, "dark", bevel=0.004)
    b.box(-0.012, 0.012, 0.03, 0.05, 0.14, 0.17, "dark", bevel=0.002)
    rear_notch(b, 0.155, 0.058, width=0.016, dots=False)
    b.rod((0.026, 0.0, 0.1), (0.044, 0.0, 0.1), 0.0045, "metal", segs=8)
    b.tube(0.2, 0.735, 0.0112, "metal", segs=18)
    for z in (0.26, 0.3, 0.34, 0.38):
        b.ring((0, 0, z), (0, 0, 1), 0.0118, 0.0105, 0.012, "dark", 16)
    b.tube(0.2, 0.5, 0.0078, "dark", y=-0.022, segs=14)
    b.box(-0.012, 0.012, -0.034, 0.012, 0.495, 0.52, "dark", bevel=0.002)
    for sx in (-1, 1):
        b.rod((sx * 0.01, -0.03, 0.51), (sx * 0.01, -0.03, 0.7), 0.0042, "dark", segs=8)
    b.box(-0.006, 0.006, 0.008, 0.044, 0.69, 0.71, "dark", bevel=0.0015)
    front_post(b, 0.7, 0.044, 0.058, ears=1)
    b.prism([(0.33, 0.012), (0.36, 0.012), (0.37, 0.06), (0.32, 0.06)], -0.004, 0.004, "dark", bevel=0.001)
    b.box(-0.025, 0.025, -0.046, -0.006, 0.2, 0.33, "primary", bevel=0.006)
    muzzle_brake(b, 0.735, 0.0132, 0.045, ports=2)
    trigger_guard(b, -0.028, 0.032, -0.042, -0.068)
    trigger(b, 0.0, -0.042)
    g.point("Grip", *grip(b, (-0.026, -0.042), 0.042, 0.09, 22, "primary"))
    s = g.stock
    s.prism([(-0.165, 0.012), (-0.39, 0.0), (-0.39, -0.02), (-0.165, -0.01)], -0.016, 0.016, "primary", bevel=0.003)
    s.prism([(-0.09, -0.11), (-0.37, -0.09), (-0.37, -0.11), (-0.09, -0.128)], -0.016, 0.016, "primary", bevel=0.003)
    s.prism([(-0.365, 0.002), (-0.396, 0.003), (-0.396, -0.118), (-0.365, -0.115)], -0.019, 0.019, "primary", bevel=0.004)
    s.box(-0.02, 0.02, -0.12, 0.004, -0.402, -0.394, "dark", bevel=0.002)
    m = g.mag
    m.box(0.0, 0.065, -0.155, -0.042, 0.03, 0.155, "dark", bevel=0.004)
    m.box(-0.001, 0.066, -0.06, -0.052, 0.028, 0.157, "dark", bevel=0.002)
    m.box(0.02, 0.045, -0.04, -0.03, 0.06, 0.13, "dark", bevel=0.002)
    g.point("Muzzle", (0, 0, 0.78))
    g.point("Eye", (0, 0.058, -0.21))
    g.point("Rail", (0, 0.05, -0.05))
    g.point("Under", (0, -0.046, 0.28))
    g.point("Side", (0.025, -0.02, 0.27))
    g.point("Support", (0, -0.046, 0.265), (0, 1, 0))
    g.point("Mag", (0.032, -0.042, 0.09), (0, 1, 0))
    g.point("Butt", (0, -0.055, -0.402))
    m = g.part("Mount")
    m.box(-0.04, -0.026, -0.02, 0.046, -0.12, -0.01, "dark", bevel=0.002)
    m.box(-0.04, 0.012, 0.046, 0.05, -0.115, -0.015, "dark", bevel=0.002)
    return g


# ---------------------------------------------------------------------------- shotguns

def m870(Part):
    g = Gun(Part, "sg_m870")
    b = g.body
    b.prism([(-0.078, 0.012), (0.13, 0.012), (0.132, -0.058), (0.03, -0.06), (-0.04, -0.052), (-0.078, -0.036)],
            -0.0172, 0.0172, "primary", bevel=0.003)
    b.box(0.017, 0.018, -0.022, 0.006, 0.0, 0.072, "dark", bevel=0.0006)
    picatinny(b, -0.07, 0.125, 0.012, "dark")
    b.tube(0.13, 0.6, 0.0108, "metal", segs=18)
    b.tube(0.13, 0.555, 0.0118, "dark", y=-0.03, segs=16)
    b.tube(0.552, 0.572, 0.0124, "dark", y=-0.03, segs=16)
    b.box(-0.008, 0.008, -0.03, 0.0, 0.545, 0.56, "dark", bevel=0.002)
    b.box(-0.007, 0.007, 0.006, 0.02, 0.575, 0.592, "dark", bevel=0.001)
    front_post(b, 0.583, 0.02, 0.0335)
    # The pump.
    b.box(-0.021, 0.021, -0.052, -0.008, 0.18, 0.33, "dark", bevel=0.007, segs=2)
    for z in range(9):
        zz = 0.195 + z * 0.014
        b.box(-0.0215, 0.0215, -0.046, -0.042, zz, zz + 0.006, "dark", bevel=0.0)
    trigger_guard(b, -0.03, 0.03, -0.052, -0.074)
    trigger(b, 0.0, -0.052)
    g.point("Grip", *grip(b, (-0.026, -0.052), 0.044, 0.095, 22, "dark", grooves=3))
    s = g.stock
    s.prism([(-0.078, 0.01), (-0.39, -0.002), (-0.39, -0.112), (-0.37, -0.116), (-0.2, -0.072), (-0.078, -0.05)],
            -0.019, 0.019, "primary", bevel=0.004, segs=2)
    s.box(-0.0195, 0.0195, -0.117, 0.002, -0.408, -0.39, "dark", bevel=0.004)
    rear_aperture(g.irons, -0.04, 0.0335, base=0.0215)
    g.point("Muzzle", (0, 0, 0.6))
    g.point("Eye", (0, 0.0335, -0.18))
    g.point("Rail", (0, 0.0215, 0.02))
    g.point("Under", (0, -0.052, 0.255))
    g.point("Side", (0.021, -0.03, 0.255))
    g.point("Support", (0, -0.052, 0.25), (0, 1, 0))
    g.point("Mag", (0, -0.03, 0.36), (0, 0, -1))
    g.point("Butt", (0, -0.055, -0.408))
    return g


def m1014(Part):
    g = Gun(Part, "sg_m1014")
    b = g.body
    b.prism([(-0.082, 0.013), (0.14, 0.013), (0.152, 0.0), (0.152, -0.055), (0.03, -0.058), (-0.04, -0.05), (-0.082, -0.034)],
            -0.018, 0.018, "primary", bevel=0.003)
    picatinny(b, -0.075, 0.135, 0.013, "dark")
    b.box(0.0178, 0.0188, -0.02, 0.006, 0.0, 0.07, "metal", bevel=0.0006)
    b.rod((0.018, -0.006, 0.06), (0.035, -0.006, 0.06), 0.0045, "metal", segs=8)
    b.box(-0.022, 0.022, -0.054, -0.004, 0.152, 0.33, "primary", bevel=0.007, segs=2)
    b.tube(0.152, 0.6, 0.0105, "metal", segs=18)
    b.tube(0.33, 0.56, 0.0118, "dark", y=-0.03, segs=16)
    b.box(-0.008, 0.008, -0.03, 0.0, 0.5, 0.515, "dark", bevel=0.002)
    b.box(-0.0075, 0.0075, 0.006, 0.024, 0.57, 0.59, "dark", bevel=0.001)
    front_post(b, 0.58, 0.024, 0.0375, ears=1)
    trigger_guard(b, -0.03, 0.03, -0.05, -0.074)
    trigger(b, 0.0, -0.05)
    g.point("Grip", *grip(b, (-0.026, -0.05), 0.045, 0.095, 20, "dark", grooves=3))
    s = g.stock
    s.prism([(-0.082, 0.009), (-0.395, 0.0), (-0.395, -0.104), (-0.375, -0.11), (-0.22, -0.062), (-0.082, -0.046)],
            -0.019, 0.019, "primary", bevel=0.004, segs=2)
    s.box(-0.0195, 0.0195, -0.111, 0.002, -0.41, -0.394, "dark", bevel=0.004)
    rear_aperture(g.irons, -0.05, 0.0375, base=0.0225)
    g.point("Muzzle", (0, 0, 0.6))
    g.point("Eye", (0, 0.0375, -0.19))
    g.point("Rail", (0, 0.0225, 0.03))
    g.point("Under", (0, -0.054, 0.25))
    g.point("Side", (0.022, -0.028, 0.25))
    g.point("Support", (0, -0.054, 0.25), (0, 1, 0))
    g.point("Mag", (0, -0.03, 0.4), (0, 0, -1))
    g.point("Butt", (0, -0.05, -0.41))
    return g


def aa12(Part):
    g = Gun(Part, "sg_aa12")
    b = g.body
    b.prism([(-0.42, 0.028), (0.2, 0.028), (0.2, -0.05), (-0.09, -0.05), (-0.42, -0.074)], -0.027, 0.027, "primary", bevel=0.005, segs=2)
    b.box(-0.028, 0.028, -0.076, 0.03, -0.434, -0.42, "dark", bevel=0.004)
    b.box(-0.026, 0.026, -0.042, 0.022, 0.2, 0.362, "dark", bevel=0.004)
    for z in range(6):
        zz = 0.215 + z * 0.024
        for sx in (-1, 1):
            b.box(sx * 0.0262 - 0.0005, sx * 0.0262 + 0.0005, -0.025, 0.008, zz, zz + 0.012, "metal", bevel=0.0)
    b.tube(0.362, 0.43, 0.0115, "metal", segs=18)
    b.tube(0.425, 0.46, 0.0142, "dark", segs=18, bevel=0.001)
    b.prism([(-0.25, 0.028), (-0.25, 0.06), (0.15, 0.06), (0.15, 0.028), (0.13, 0.028), (0.13, 0.05), (-0.23, 0.05), (-0.23, 0.028)],
            -0.0085, 0.0085, "primary", bevel=0.002)
    picatinny(b, -0.24, 0.14, 0.06, "dark")
    front_post(b, 0.14, 0.0695, 0.08, ears=1)
    b.rod((0.027, 0.0, 0.05), (0.042, 0.0, 0.05), 0.0045, "dark", segs=8)
    trigger_guard(b, -0.03, 0.04, -0.05, -0.076)
    trigger(b, 0.0, -0.05)
    g.point("Grip", *grip(b, (-0.026, -0.05), 0.046, 0.1, 15, "dark", grooves=3))
    rear_aperture(g.irons, -0.2, 0.08, base=0.0695)
    straight_mag(g.mag, 0.132, 0.046, -0.04, 0.135, 0.0245, "primary")
    g.point("Muzzle", (0, 0, 0.46))
    g.point("Eye", (0, 0.08, -0.27))
    g.point("Rail", (0, 0.0695, -0.06))
    g.point("Under", (0, -0.042, 0.29))
    g.point("Side", (0.026, -0.01, 0.29))
    g.point("Support", (0, -0.042, 0.28), (0, 1, 0))
    g.point("Mag", (0, -0.05, 0.089), (0, 1, 0))
    g.point("Butt", (0, -0.022, -0.434))
    return g


def double_barrel(Part, gid, barrel_end, sawn=False):
    g = Gun(Part, gid)
    b = g.body
    for sx in (-1, 1):
        b.tube(0.085, barrel_end, 0.0108, "metal", x=sx * 0.0108, segs=18)
        b.tube(barrel_end - 0.003, barrel_end, 0.0112, "metal", x=sx * 0.0108, segs=18)
    b.box(-0.0045, 0.0045, 0.006, 0.0128, 0.085, barrel_end - 0.004, "metal", bevel=0.001)
    b.box(-0.006, 0.006, -0.016, -0.006, 0.085, barrel_end - 0.004, "metal", bevel=0.001)
    b.ball((0, 0.0145, barrel_end - 0.01), 0.0022, "glow")
    b.prism([(-0.045, 0.0135), (0.085, 0.0135), (0.088, -0.012), (0.06, -0.03), (-0.045, -0.032)], -0.0215, 0.0215, "dark", bevel=0.004, segs=2)
    b.box(-0.0045, 0.0045, 0.013, 0.019, -0.055, -0.02, "metal", bevel=0.001, rot=(0, 18, 0))
    for sx in (-1, 1):
        b.prism([(-0.048, 0.008), (-0.06, 0.03), (-0.068, 0.028), (-0.058, 0.002)], sx * 0.009 - 0.0028, sx * 0.009 + 0.0028, "metal", bevel=0.0008)
    fore_end = 0.22 if sawn else 0.31
    b.box(-0.0195, 0.0195, -0.027, -0.006, 0.095, fore_end, "primary", bevel=0.006, segs=2)
    trigger_guard(b, -0.03, 0.032, -0.032, -0.058)
    trigger(b, -0.006, -0.032)
    trigger(b, 0.012, -0.032)
    if sawn:
        g.point("Grip", *grip(b, (-0.03, -0.03), 0.046, 0.1, 34, "primary", half_width=0.0165))
        b.prism([(-0.045, 0.012), (-0.07, 0.002), (-0.075, -0.02), (-0.045, -0.034)], -0.0165, 0.0165, "primary", bevel=0.004)
        butt = (0, -0.06, -0.1)
        eye = (0, 0.0165, -0.3)
    else:
        g.point("Grip", *grip(b, (-0.03, -0.034), 0.044, 0.075, 34, "primary", half_width=0.0165))
        b.prism([(-0.045, 0.012), (-0.2, -0.012), (-0.35, -0.02), (-0.36, -0.024), (-0.36, -0.122), (-0.34, -0.124), (-0.15, -0.086),
                 (-0.08, -0.07), (-0.045, -0.034)], -0.019, 0.019, "primary", bevel=0.005, segs=2)
        b.box(-0.0195, 0.0195, -0.125, -0.02, -0.372, -0.36, "dark", bevel=0.003)
        butt = (0, -0.07, -0.372)
        eye = (0, 0.0165, -0.18)
    g.point("Muzzle", (0, 0, barrel_end))
    g.point("Eye", eye)
    g.point("Under", (0, -0.027, (0.095 + fore_end) / 2 + 0.02))
    g.point("Side", (0.0195, -0.016, (0.095 + fore_end) / 2))
    g.point("Support", (0, -0.027, (0.095 + fore_end) / 2 + 0.01), (0, 1, 0))
    g.point("Butt", butt)
    return g


# ---------------------------------------------------------------------------- sniper rifles

def bolt_handle(shape, z, side_y=0.004, length=0.034, knob=0.0075):
    shape.rod((0.012, side_y, z), (0.012 + length, side_y - 0.016, z - 0.008), 0.0034, "metal", segs=10)
    shape.ball((0.014 + length, side_y - 0.017, z - 0.009), knob, "dark", scale=(1, 1, 1.15))


def m24(Part):
    g = Gun(Part, "sr_m24")
    b = g.body
    # A one-piece fibreglass stock: the fore-end, the grip and the butt.
    b.prism([(-0.06, -0.006), (0.38, -0.008), (0.388, -0.022), (0.38, -0.052), (-0.06, -0.054)], -0.022, 0.022, "primary", bevel=0.006, segs=2)
    b.prism([(-0.06, -0.006), (-0.2, 0.004), (-0.418, 0.017), (-0.424, 0.012), (-0.424, -0.124), (-0.408, -0.13), (-0.2, -0.084),
             (-0.13, -0.074), (-0.06, -0.054)], -0.021, 0.021, "primary", bevel=0.006, segs=2)
    b.box(-0.0215, 0.0215, -0.131, 0.018, -0.436, -0.423, "dark", bevel=0.004)
    g.point("Grip", *grip(b, (-0.028, -0.052), 0.046, 0.078, 14, "primary", half_width=0.0165))
    # The round Remington 700 action, its bolt, and a heavy barrel.
    b.tube(-0.095, 0.082, 0.0165, "dark", segs=20)
    picatinny(b, -0.09, 0.075, 0.0165, "dark")
    b.tube(-0.105, -0.095, 0.014, "metal", segs=16)
    bolt_handle(b, -0.06)
    b.tube(0.082, 0.668, 0.0128, "metal", r2=0.0102, segs=20)
    b.box(-0.006, 0.006, -0.06, -0.052, -0.035, 0.03, "dark", bevel=0.001)
    trigger(b, 0.0, -0.054)
    trigger_guard(b, -0.03, 0.032, -0.054, -0.076)
    for z in (0.05, 0.31):
        b.rod((0, -0.054, z), (0, -0.062, z), 0.004, "metal", segs=8)
    scope(g.irons, -0.125, 0.205, 0.05, tube_r=0.0127, objective_r=0.024, eye_r=0.0195, rings=(-0.04, 0.06), rail_y=0.026)
    g.point("Muzzle", (0, 0, 0.668))
    g.point("Eye", (0, 0.05, -0.205))
    g.point("Rail", (0, 0.026, -0.01))
    g.point("Under", (0, -0.054, 0.3))
    g.point("Side", (0.022, -0.03, 0.3))
    g.point("Support", (0, -0.054, 0.26), (0, 1, 0))
    g.point("Butt", (0, -0.056, -0.436))
    return g


def l115a3(Part):
    g = Gun(Part, "sr_l115a3")
    b = g.body
    b.prism([(-0.04, -0.008), (0.4, -0.01), (0.406, -0.026), (0.4, -0.06), (-0.04, -0.062)], -0.024, 0.024, "primary", bevel=0.005, segs=2)
    b.box(-0.024, 0.024, -0.062, 0.002, -0.11, -0.03, "primary", bevel=0.004)
    # The thumbhole stock: a top bar to the butt, the butt, and a lower bar under the hand.
    b.prism([(-0.11, 0.004), (-0.44, 0.02), (-0.44, -0.002), (-0.11, -0.022)], -0.018, 0.018, "primary", bevel=0.004)
    b.prism([(-0.375, 0.024), (-0.446, 0.026), (-0.446, -0.13), (-0.4, -0.134), (-0.375, -0.1)], -0.021, 0.021, "primary", bevel=0.005)
    b.prism([(-0.11, -0.122), (-0.38, -0.116), (-0.38, -0.1), (-0.11, -0.104)], -0.016, 0.016, "primary", bevel=0.004)
    b.box(-0.018, 0.018, 0.02, 0.038, -0.38, -0.2, "dark", bevel=0.004)
    b.box(-0.022, 0.022, -0.135, 0.028, -0.458, -0.446, "dark", bevel=0.004)
    g.point("Grip", *grip(b, (-0.03, -0.062), 0.046, 0.09, 10, "primary", half_width=0.0165))
    b.tube(-0.11, 0.06, 0.0172, "dark", segs=20)
    picatinny(b, -0.1, 0.055, 0.0172, "dark")
    bolt_handle(b, -0.075, length=0.038)
    b.tube(0.06, 0.72, 0.0132, "metal", r2=0.011, segs=20)
    muzzle_brake(b, 0.72, 0.0152, 0.06, ports=3)
    for sx in (-1, 1):
        b.rod((sx * 0.012, -0.055, 0.38), (sx * 0.014, -0.06, 0.6), 0.005, "dark", segs=8)
    trigger(b, 0.0, -0.062)
    trigger_guard(b, -0.03, 0.03, -0.062, -0.084)
    scope(g.irons, -0.145, 0.245, 0.058, tube_r=0.017, objective_r=0.033, eye_r=0.022, rings=(-0.05, 0.045), rail_y=0.0267)
    straight_mag(g.mag, 0.062, 0.012, -0.044, 0.088, 0.0142, "dark")
    g.point("Muzzle", (0, 0, 0.78))
    g.point("Eye", (0, 0.058, -0.23))
    g.point("Rail", (0, 0.0267, -0.02))
    g.point("Under", (0, -0.062, 0.3))
    g.point("Side", (0.024, -0.03, 0.3))
    g.point("Support", (0, -0.062, 0.26), (0, 1, 0))
    g.point("Mag", (0, -0.062, 0.037), (0, 1, 0))
    g.point("Butt", (0, -0.055, -0.458))
    return g


def m107(Part):
    g = Gun(Part, "sr_m107")
    b = g.body
    b.box(-0.03, 0.03, -0.012, 0.04, -0.25, 0.45, "primary", bevel=0.004)
    for z in range(7):
        zz = 0.24 + z * 0.028
        for sx in (-1, 1):
            b.box(sx * 0.0302 - 0.0006, sx * 0.0302 + 0.0006, 0.0, 0.026, zz, zz + 0.016, "dark", bevel=0.0)
    picatinny(b, -0.235, 0.2, 0.04, "dark")
    b.prism([(-0.25, -0.012), (0.15, -0.012), (0.15, -0.062), (0.03, -0.066), (-0.03, -0.066), (-0.25, -0.05)], -0.027, 0.027, "dark", bevel=0.003)
    b.rod((0.03, 0.02, 0.05), (0.05, 0.02, 0.05), 0.005, "metal", segs=8)
    b.box(-0.006, 0.006, 0.04, 0.074, 0.3, 0.315, "dark", bevel=0.001)
    b.box(-0.006, 0.006, 0.04, 0.074, 0.41, 0.425, "dark", bevel=0.001)
    b.box(-0.007, 0.007, 0.068, 0.078, 0.3, 0.425, "dark", bevel=0.002)
    b.tube(0.45, 0.86, 0.0168, "metal", segs=20)
    b.box(-0.031, 0.031, -0.02, 0.02, 0.86, 0.985, "dark", bevel=0.004)
    for z in (0.885, 0.94):
        for sx in (-1, 1):
            b.box(sx * 0.031 - 0.0008, sx * 0.031 + 0.0008, -0.014, 0.014, z, z + 0.03, "metal", bevel=0.0)
    for sx in (-1, 1):
        b.rod((sx * 0.02, -0.012, 0.42), (sx * 0.022, -0.02, 0.7), 0.0065, "dark", segs=10)
    trigger_guard(b, -0.03, 0.032, -0.066, -0.09)
    trigger(b, 0.0, -0.066)
    g.point("Grip", *grip(b, (-0.026, -0.066), 0.046, 0.1, 12, "dark", grooves=3))
    s = g.stock
    s.prism([(-0.25, 0.036), (-0.47, 0.036), (-0.476, 0.03), (-0.476, -0.118), (-0.452, -0.124), (-0.3, -0.06), (-0.25, -0.05)],
            -0.026, 0.026, "primary", bevel=0.005, segs=2)
    s.box(-0.02, 0.02, 0.036, 0.05, -0.43, -0.3, "dark", bevel=0.004)
    s.box(-0.028, 0.028, -0.126, 0.04, -0.5, -0.476, "dark", bevel=0.006)
    s.rod((0, -0.1, -0.4), (0, -0.16, -0.4), 0.007, "dark", segs=10)
    scope(g.irons, -0.205, 0.15, 0.078, tube_r=0.015, objective_r=0.028, eye_r=0.021, rings=(-0.1, 0.05), rail_y=0.0495)
    straight_mag(g.mag, 0.12, 0.036, -0.052, 0.14, 0.0205, "dark")
    g.point("Muzzle", (0, 0, 0.985))
    g.point("Eye", (0, 0.078, -0.29))
    g.point("Rail", (0, 0.0495, -0.06))
    g.point("Under", (0, -0.012, 0.32))
    g.point("Side", (0.03, 0.012, 0.3))
    g.point("Support", (0, -0.012, 0.24), (0, 1, 0))
    g.point("Mag", (0, -0.066, 0.078), (0, 1, 0))
    g.point("Butt", (0, -0.045, -0.5))
    return g


# ---------------------------------------------------------------------------- battle and marksman rifles

def m14ebr(Part):
    g = Gun(Part, "mr_m14ebr")
    b = g.body
    b.box(-0.026, 0.026, -0.046, 0.016, -0.125, 0.13, "primary", bevel=0.004)
    b.box(-0.0165, 0.0165, 0.0, 0.03, -0.12, 0.12, "dark", bevel=0.003)
    b.box(0.0165, 0.03, -0.004, 0.006, 0.04, 0.12, "metal", bevel=0.001)
    b.box(0.028, 0.034, -0.006, 0.01, 0.112, 0.124, "metal", bevel=0.001)
    picatinny(b, -0.118, 0.118, 0.03, "primary")
    b.box(-0.026, 0.026, -0.03, 0.028, 0.13, 0.36, "primary", bevel=0.005, segs=2)
    picatinny(b, 0.135, 0.355, 0.028, "primary")
    picatinny(b, 0.135, 0.355, -0.03, "primary", face="bottom")
    picatinny(b, 0.15, 0.35, 0.0, "primary", face="right", x=0.026)
    picatinny(b, 0.15, 0.35, 0.0, "primary", face="left", x=-0.026)
    b.tube(0.13, 0.53, 0.0115, "metal", segs=18)
    flash_hider(b, 0.53, 0.0132, 0.05)
    trigger_guard(b, -0.03, 0.035, -0.046, -0.07)
    trigger(b, 0.0, -0.046)
    g.point("Grip", *grip(b, (-0.026, -0.046), 0.044, 0.095, 20, "dark", grooves=3))
    s = g.stock
    s.tube(-0.125, -0.3, 0.0148, "dark", y=-0.004, segs=18)
    s.prism([(-0.215, 0.03), (-0.335, 0.034), (-0.342, 0.03), (-0.342, -0.08), (-0.326, -0.085), (-0.26, -0.046), (-0.215, -0.02)],
            -0.022, 0.022, "primary", bevel=0.004, segs=2)
    s.box(-0.0225, 0.0225, -0.086, 0.035, -0.352, -0.341, "dark", bevel=0.003)
    i = g.irons
    i.box(-0.011, 0.011, 0.0395, 0.055, -0.11, -0.092, "dark", bevel=0.001)
    rear_aperture(i, -0.1, 0.07, base=0.053)
    i.box(-0.009, 0.009, 0.0375, 0.054, 0.33, 0.348, "dark", bevel=0.001)
    front_post(i, 0.339, 0.052, 0.07, ears=1)
    straight_mag(g.mag, 0.112, 0.042, -0.036, 0.12, 0.0135, "primary", tilt=-3)
    g.point("Muzzle", (0, 0, 0.58))
    g.point("Eye", (0, 0.07, -0.18))
    g.point("Rail", (0, 0.0395, -0.03))
    g.point("Under", (0, -0.0395, 0.26))
    g.point("Side", (0.0355, 0, 0.26))
    g.point("Support", (0, -0.0395, 0.25), (0, 1, 0))
    g.point("Mag", (0, -0.046, 0.077), (0, 1, 0))
    g.point("Butt", (0, -0.025, -0.352))
    return g


def svd(Part):
    g = Gun(Part, "mr_svd")
    b = g.body
    b.box(-0.0145, 0.0145, -0.036, 0.012, -0.14, 0.15, "dark", bevel=0.002)
    b.box(-0.0135, 0.0135, 0.006, 0.021, -0.138, 0.1, "dark", bevel=0.0065, segs=3)
    b.box(-0.0125, 0.0125, 0.006, 0.026, 0.1, 0.15, "dark", bevel=0.003)
    rear_notch(b, 0.135, 0.036, width=0.018, dots=False)
    b.rod((0.0145, 0.003, 0.07), (0.03, 0.003, 0.07), 0.0035, "metal", segs=10)
    b.ball((0.031, 0.003, 0.07), 0.0055, "metal", scale=(1, 0.8, 1.3))
    b.box(-0.021, 0.021, -0.03, 0.03, 0.15, 0.4, "primary", bevel=0.009, segs=3)
    for z in (0.2, 0.24, 0.28, 0.32):
        for sx in (-1, 1):
            b.box(sx * 0.0212 - 0.0005, sx * 0.0212 + 0.0005, 0.0, 0.016, z, z + 0.026, "dark", bevel=0.0)
    b.box(-0.011, 0.011, -0.014, 0.022, 0.4, 0.43, "dark", bevel=0.002)
    b.tube(0.4, 0.72, 0.0095, "metal", segs=16)
    b.box(-0.008, 0.008, -0.011, 0.012, 0.685, 0.71, "dark", bevel=0.002)
    front_post(b, 0.698, 0.012, 0.036, ears=1)
    b.tube(0.72, 0.8, 0.0118, "dark", segs=16)
    for k in range(5):
        a = math.radians(30 + k * 60)
        b.cbox((math.cos(a) * 0.0118, math.sin(a) * 0.0118, 0.765), (0.0025, 0.0025, 0.05), "metal", bevel=0.0, rot=(0, 0, math.degrees(a)))
    # The side mount the scope clamps to, always there.
    b.box(-0.031, -0.0145, -0.01, 0.026, -0.07, 0.04, "dark", bevel=0.002)
    b.box(-0.031, 0.012, 0.026, 0.034, -0.065, 0.035, "dark", bevel=0.002)
    trigger_guard(b, -0.028, 0.032, -0.036, -0.06)
    trigger(b, 0.0, -0.036)
    g.point("Grip", *grip(b, (-0.026, -0.036), 0.042, 0.088, 22, "primary", half_width=0.0145))
    s = g.stock
    s.prism([(-0.14, 0.006), (-0.42, -0.004), (-0.42, -0.022), (-0.14, -0.012)], -0.018, 0.018, "primary", bevel=0.004)
    s.box(-0.019, 0.019, -0.004, 0.012, -0.34, -0.2, "primary", bevel=0.004)
    s.prism([(-0.075, -0.11), (-0.4, -0.118), (-0.4, -0.1), (-0.075, -0.094)], -0.016, 0.016, "primary", bevel=0.004)
    s.prism([(-0.398, 0.0), (-0.43, 0.0), (-0.43, -0.124), (-0.398, -0.124)], -0.019, 0.019, "primary", bevel=0.004)
    s.box(-0.0195, 0.0195, -0.125, 0.001, -0.438, -0.429, "dark", bevel=0.002)
    # The PSO-1 scope on its mount.
    scope(g.irons, -0.155, 0.075, 0.062, tube_r=0.0125, objective_r=0.0175, eye_r=0.02, rings=None)
    g.irons.box(-0.013, 0.013, 0.034, 0.05, -0.06, 0.03, "dark", bevel=0.003)
    curved_mag(g.mag, 0.112, 0.046, -0.026, 0.11, 0.5, 0.0135, "dark")
    g.point("Muzzle", (0, 0, 0.8))
    g.point("Eye", (0, 0.062, -0.235))
    g.point("Rail", (0, 0.034, -0.015))
    g.point("Under", (0, -0.03, 0.29))
    g.point("Side", (0.021, 0.0, 0.28))
    g.point("Support", (0, -0.03, 0.27), (0, 1, 0))
    g.point("Mag", (0, -0.036, 0.079), (0, 1, 0))
    g.point("Butt", (0, -0.062, -0.438))
    return g


def mk17(Part):
    g = Gun(Part, "mr_mk17")
    b = g.body
    b.box(-0.022, 0.022, -0.012, 0.028, -0.13, 0.3, "primary", bevel=0.004)
    picatinny(b, -0.125, 0.295, 0.028, "primary")
    picatinny(b, 0.13, 0.29, -0.012, "primary", face="bottom")
    picatinny(b, 0.14, 0.28, 0.008, "primary", face="right", x=0.022)
    picatinny(b, 0.14, 0.28, 0.008, "primary", face="left", x=-0.022)
    b.rod((-0.022, 0.012, 0.12), (-0.04, 0.012, 0.118), 0.004, "dark", segs=8)
    b.box(0.0218, 0.0228, -0.004, 0.012, -0.05, 0.02, "dark", bevel=0.0006)
    b.prism([(0.122, -0.012), (0.122, -0.062), (0.036, -0.066), (0.034, -0.052), (-0.03, -0.052), (-0.13, -0.045), (-0.13, -0.012)],
            -0.02, 0.02, "dark", bevel=0.002)
    b.tube(0.3, 0.46, 0.0105, "metal", segs=18)
    flash_hider(b, 0.46, 0.0128, 0.045)
    trigger_guard(b, -0.028, 0.034, -0.052, -0.076)
    trigger(b, 0.0, -0.052)
    g.point("Grip", *grip(b, (-0.026, -0.052), 0.044, 0.095, 20, "dark", grooves=3))
    s = g.stock
    s.prism([(-0.13, 0.022), (-0.38, 0.03), (-0.386, 0.026), (-0.386, -0.084), (-0.37, -0.088), (-0.25, -0.05), (-0.13, -0.04)],
            -0.02, 0.02, "primary", bevel=0.004, segs=2)
    s.box(-0.016, 0.016, 0.03, 0.041, -0.36, -0.22, "dark", bevel=0.003)
    s.box(-0.0205, 0.0205, -0.089, 0.031, -0.396, -0.385, "dark", bevel=0.003)
    i = g.irons
    i.box(-0.011, 0.011, 0.0375, 0.053, -0.11, -0.092, "dark", bevel=0.001)
    rear_aperture(i, -0.1, 0.07, base=0.051)
    i.box(-0.009, 0.009, 0.0375, 0.052, 0.262, 0.28, "dark", bevel=0.001)
    front_post(i, 0.271, 0.05, 0.07, ears=1)
    straight_mag(g.mag, 0.112, 0.042, -0.036, 0.12, 0.0135, "dark", tilt=-4)
    g.point("Muzzle", (0, 0, 0.505))
    g.point("Eye", (0, 0.07, -0.2))
    g.point("Rail", (0, 0.0375, -0.01))
    g.point("Under", (0, -0.0215, 0.22))
    g.point("Side", (0.0315, 0.008, 0.21))
    g.point("Support", (0, -0.0215, 0.21), (0, 1, 0))
    g.point("Mag", (0, -0.062, 0.077), (0, 1, 0))
    g.point("Butt", (0, -0.025, -0.396))
    return g


# ---------------------------------------------------------------------------- pistols

def pistol_frame(g, slide, frame, grip_args, sights, zone_slide="primary", zone_frame="primary", muzzle_r=0.0062):
    """The parts every semi-automatic pistol shares: slide, frame, guard, trigger, grip."""
    b = g.body
    b.prism(slide, -0.0132, 0.0132, zone_slide, bevel=0.0025, segs=2)
    b.prism(frame, -0.0128, 0.0128, zone_frame, bevel=0.002, segs=2)
    zf = max(z for z, _ in slide)
    for i in range(6):
        z = min(z for z, _ in slide) + 0.006 + i * 0.0045
        for sx in (-1, 1):
            b.box(sx * 0.0133 - 0.0006, sx * 0.0133 + 0.0006, -0.006, 0.012, z, z + 0.0022, "dark", bevel=0.0)
    b.tube(zf - 0.006, zf + 0.0008, muzzle_r, "metal", segs=14)
    rear_z, front_z, top = sights
    rear_notch(b, rear_z, top + 0.006, width=0.018)
    front_post(b, front_z, top, top + 0.0055)
    return b


def m17(Part):
    g = Gun(Part, "pistol_m17")
    b = pistol_frame(g, [(-0.064, -0.012), (0.142, -0.012), (0.144, 0.004), (0.139, 0.0165), (-0.058, 0.0175), (-0.064, 0.011)],
                     [(0.135, -0.012), (0.135, -0.029), (0.04, -0.031), (0.03, -0.028), (-0.02, -0.026), (-0.062, -0.02), (-0.068, -0.012)],
                     None, (-0.052, 0.13, 0.0175))
    b.box(0.003, 0.0132, 0.0168, 0.0182, 0.0, 0.042, "metal", bevel=0.0004)
    picatinny(b, 0.07, 0.125, -0.029, "primary", face="bottom", half_width=0.009, height=0.0055)
    b.box(-0.0145, -0.0128, -0.016, -0.01, 0.0, 0.03, "dark", bevel=0.0008)
    b.box(-0.0145, -0.0128, -0.022, -0.017, -0.035, -0.02, "dark", bevel=0.0008)
    trigger_guard(b, -0.022, 0.042, -0.026, -0.052, half_width=0.006)
    trigger(b, 0.0, -0.026, length=0.015)
    g.point("Grip", *grip(b, (-0.022, -0.026), 0.05, 0.095, 17, "primary", half_width=0.0155, grooves=3))
    straight_mag(g.mag, -0.032, -0.064, -0.04, 0.1, 0.0105, "dark", tilt=17, plate_extra=0.004)
    g.point("Muzzle", (0, 0, 0.145))
    g.point("Eye", (0, 0.0235, -0.34))
    g.point("Rail", (0, 0.0175, -0.025))
    g.point("Under", (0, -0.0345, 0.1))
    g.point("Side", (0.0128, -0.022, 0.1))
    g.point("Mag", (0, -0.12, -0.078), (0, math.cos(math.radians(17)), math.sin(math.radians(17))))
    g.point("Butt", (0, 0.0, -0.068))
    return g


def m1911(Part):
    g = Gun(Part, "pistol_m1911")
    b = pistol_frame(g, [(-0.07, -0.01), (0.145, -0.01), (0.147, 0.004), (0.143, 0.0135), (-0.066, 0.0148), (-0.07, 0.008)],
                     [(0.145, -0.01), (0.145, -0.022), (0.035, -0.024), (-0.03, -0.02), (-0.07, -0.016), (-0.076, -0.01)],
                     None, (-0.058, 0.137, 0.0148), muzzle_r=0.0085)
    b.prism([(-0.068, -0.004), (-0.08, 0.012), (-0.086, 0.01), (-0.076, -0.01)], -0.0038, 0.0038, "dark", bevel=0.0008)
    b.prism([(-0.062, -0.018), (-0.09, -0.02), (-0.088, -0.026), (-0.062, -0.03)], -0.012, 0.012, "primary", bevel=0.002)
    b.box(-0.0145, -0.0115, -0.012, -0.004, -0.06, -0.035, "dark", bevel=0.0008)
    b.box(-0.0145, -0.0115, -0.016, -0.008, 0.0, 0.03, "dark", bevel=0.0008)
    trigger_guard(b, -0.022, 0.036, -0.022, -0.046, half_width=0.0055)
    b.box(-0.003, 0.003, -0.036, -0.022, -0.004, 0.002, "dark", bevel=0.0006)
    g.point("Grip", *grip(b, (-0.022, -0.022), 0.05, 0.095, 18, "primary", half_width=0.015))
    for sx in (-1, 1):
        b.prism([(-0.03, -0.03), (-0.052, -0.106), (-0.08, -0.098), (-0.064, -0.026)], sx * 0.015 - 0.0012, sx * 0.015 + 0.0012, "dark", bevel=0.0008)
    straight_mag(g.mag, -0.03, -0.062, -0.04, 0.1, 0.0095, "dark", tilt=18, plate_extra=0.004)
    g.point("Muzzle", (0, 0, 0.148))
    g.point("Eye", (0, 0.0198, -0.35))
    g.point("Rail", (0, 0.0148, -0.03))
    g.point("Under", (0, -0.024, 0.1))
    g.point("Side", (0.0128, -0.018, 0.1))
    g.point("Mag", (0, -0.116, -0.077), (0, math.cos(math.radians(18)), math.sin(math.radians(18))))
    g.point("Butt", (0, 0.0, -0.09))
    return g


def revolver(Part):
    g = Gun(Part, "pistol_357")
    b = g.body
    b.box(-0.008, 0.008, 0.0195, 0.026, -0.032, 0.058, "primary", bevel=0.002)
    b.box(-0.011, 0.011, -0.024, 0.026, 0.044, 0.06, "primary", bevel=0.002)
    b.box(-0.013, 0.013, -0.03, 0.026, -0.04, 0.004, "primary", bevel=0.003)
    b.box(-0.009, 0.009, -0.028, -0.019, -0.01, 0.05, "primary", bevel=0.002)
    # Six chambers in a fluted cylinder.
    b.lathe([(0.004, 0.0), (0.004, 0.017), (0.007, 0.0195), (0.041, 0.0195), (0.045, 0.017), (0.045, 0.0)], "primary", 30, y=-0.0)
    for k in range(6):
        a = math.radians(30 + k * 60)
        b.cbox((math.cos(a) * 0.0195, math.sin(a) * 0.0195, 0.025), (0.0045, 0.0045, 0.03), "dark", bevel=0.001, rot=(0, 0, math.degrees(a)))
    b.tube(0.06, 0.157, 0.0085, "primary", segs=18)
    b.box(-0.0048, 0.0048, 0.006, 0.0118, 0.06, 0.157, "primary", bevel=0.0012)
    b.box(-0.0078, 0.0078, -0.022, -0.006, 0.06, 0.155, "primary", bevel=0.003)
    b.tube(0.155, 0.158, 0.006, "metal", segs=14)
    b.prism([(0.132, 0.0118), (0.154, 0.0118), (0.154, 0.0195), (0.147, 0.0195)], -0.0018, 0.0018, "dark", bevel=0.0004)
    b.box(-0.0019, 0.0019, 0.0165, 0.0195, 0.146, 0.152, "glow", bevel=0.0)
    rear_notch(b, -0.025, 0.031, width=0.015, height=0.005, dots=False)
    b.prism([(-0.03, 0.015), (-0.05, 0.031), (-0.058, 0.029), (-0.042, 0.004)], -0.0035, 0.0035, "dark", bevel=0.0008)
    b.box(-0.0148, -0.013, -0.006, 0.004, -0.025, -0.012, "dark", bevel=0.0006)
    trigger_guard(b, -0.022, 0.032, -0.028, -0.052, half_width=0.0055)
    trigger(b, 0.0, -0.028, length=0.017)
    g.point("Grip", *grip(b, (-0.026, -0.028), 0.046, 0.09, 25, "dark", half_width=0.017, grooves=3))
    g.point("Muzzle", (0, 0, 0.158))
    g.point("Eye", (0, 0.027, -0.33))
    g.point("Rail", (0, 0.026, 0.0))
    g.point("Under", (0, -0.022, 0.12))
    g.point("Side", (0.0078, -0.014, 0.11))
    g.point("Butt", (0, 0.0, -0.06))
    return g


def beretta93r(Part):
    g = Gun(Part, "pistol_93r")
    b = pistol_frame(g, [(-0.07, -0.008), (0.152, -0.008), (0.152, 0.01), (0.148, 0.0125), (-0.066, 0.014), (-0.07, 0.008)],
                     [(0.152, -0.008), (0.152, -0.022), (0.06, -0.024), (-0.07, -0.016), (-0.074, -0.008)],
                     None, (-0.06, 0.142, 0.014), muzzle_r=0.0068)
    muzzle_brake(b, 0.15, 0.0088, 0.03, "dark", ports=2)
    b.tube(-0.01, 0.12, 0.0066, "metal", y=0.008, segs=14)
    trigger_guard(b, -0.022, 0.066, -0.022, -0.052, half_width=0.0055)
    trigger(b, 0.0, -0.022, length=0.015)
    # The fold-down front grip, down.
    b.box(-0.0065, 0.0065, -0.03, -0.022, 0.075, 0.105, "dark", bevel=0.001)
    b.prism([(0.08, -0.03), (0.1, -0.03), (0.098, -0.082), (0.084, -0.084)], -0.0075, 0.0075, "dark", bevel=0.002)
    g.point("Grip", *grip(b, (-0.022, -0.016), 0.052, 0.1, 18, "primary", half_width=0.0155))
    straight_mag(g.mag, -0.032, -0.066, -0.04, 0.14, 0.0105, "dark", tilt=18, plate_extra=0.003)
    g.point("Muzzle", (0, 0, 0.18))
    g.point("Eye", (0, 0.0195, -0.34))
    g.point("Rail", (0, 0.014, -0.03))
    g.point("Under", (0, -0.024, 0.13))
    g.point("Side", (0.0128, -0.016, 0.125))
    g.point("Foregrip", (0, -0.056, 0.091), (0, 1, 0))
    g.point("Mag", (0, -0.112, -0.08), (0, math.cos(math.radians(18)), math.sin(math.radians(18))))
    g.point("Butt", (0, 0.0, -0.075))
    return g


def skorpion(Part):
    g = Gun(Part, "pistol_skorpion")
    b = g.body
    b.box(-0.0135, 0.0135, -0.022, 0.016, -0.072, 0.13, "primary", bevel=0.004)
    for sx in (-1, 1):
        b.ball((sx * 0.0165, 0.004, -0.02), 0.0055, "dark")
        b.rod((sx * 0.012, 0.022, -0.068), (sx * 0.012, 0.022, 0.1), 0.0025, "metal", segs=8)
    b.box(-0.014, 0.014, 0.016, 0.026, 0.096, 0.108, "metal", bevel=0.002)
    b.tube(0.13, 0.155, 0.0075, "metal", segs=14)
    b.box(-0.007, 0.007, 0.016, 0.026, 0.112, 0.128, "dark", bevel=0.001)
    front_post(b, 0.12, 0.024, 0.031, ears=1)
    b.box(-0.008, 0.008, 0.016, 0.025, -0.06, -0.044, "dark", bevel=0.001)
    rear_notch(b, -0.052, 0.031, width=0.014, height=0.006, dots=False)
    trigger_guard(b, -0.026, 0.036, -0.022, -0.046, half_width=0.005)
    trigger(b, 0.0, -0.022, length=0.015)
    g.point("Grip", *grip(b, (-0.026, -0.022), 0.042, 0.09, 12, "dark", half_width=0.0145))
    curved_mag(g.mag, 0.083, 0.048, -0.016, 0.13, 0.3, 0.0092, "primary")
    g.point("Muzzle", (0, 0, 0.155))
    g.point("Eye", (0, 0.03, -0.32))
    g.point("Rail", (0, 0.026, -0.02))
    g.point("Under", (0, -0.022, 0.11))
    g.point("Side", (0.0135, -0.004, 0.11))
    g.point("Foregrip", (0, -0.075, 0.074), (0, 1, -0.28))
    g.point("Mag", (0, -0.022, 0.0655), (0, 1, 0))
    g.point("Butt", (0, 0.0, -0.076))
    return g


# ---------------------------------------------------------------------------- launchers

def rpg7(Part):
    g = Gun(Part, "rl_rpg7")
    b = g.body
    b.tube(-0.45, 0.38, 0.02, "dark", segs=24)
    b.tube(0.355, 0.38, 0.0235, "dark", segs=24, bevel=0.001)
    b.lathe([(-0.575, 0.0), (-0.575, 0.046), (-0.565, 0.046), (-0.52, 0.038), (-0.45, 0.022), (-0.45, 0.0)], "dark", 28)
    b.ring((0, 0, -0.573), (0, 0, 1), 0.047, 0.04, 0.006, "metal", 28)
    # Wooden heat shields where the shoulder and cheek rest.
    b.tube(-0.28, 0.02, 0.0285, "primary", segs=24, bevel=0.003)
    b.ring((0, 0, -0.282), (0, 0, 1), 0.0305, 0.02, 0.006, "metal", 24)
    b.ring((0, 0, 0.022), (0, 0, 1), 0.0305, 0.02, 0.006, "metal", 24)
    b.box(-0.006, 0.006, -0.022, -0.014, -0.04, 0.03, "dark", bevel=0.001)
    trigger_guard(b, -0.028, 0.032, -0.022, -0.046)
    trigger(b, 0.0, -0.022)
    g.point("Grip", *grip(b, (-0.026, -0.022), 0.04, 0.095, 10, "primary", half_width=0.015))
    up = grip(b, (0.19, -0.02), 0.034, 0.088, 4, "primary", half_width=0.0135)
    g.point("Foregrip", up[0], up[1])
    b.box(-0.005, 0.005, -0.024, -0.016, 0.15, 0.2, "dark", bevel=0.001)
    # Iron sights, and the optical sight on its bracket to the left.
    b.box(-0.006, 0.006, 0.019, 0.04, 0.35, 0.365, "dark", bevel=0.001)
    front_post(b, 0.357, 0.04, 0.052)
    b.box(-0.009, 0.009, 0.019, 0.04, -0.03, -0.015, "dark", bevel=0.001)
    rear_notch(b, -0.022, 0.052, width=0.02, height=0.012, dots=False)
    b.box(-0.07, -0.024, -0.006, 0.008, -0.12, -0.04, "dark", bevel=0.002)
    b.box(-0.085, -0.045, 0.004, 0.05, -0.13, 0.02, "dark", bevel=0.004)
    b.tube(-0.17, -0.13, 0.015, "dark", x=-0.065, y=0.027, segs=16)
    b.tube(0.02, 0.03, 0.017, "glow", x=-0.065, y=0.027, segs=16)
    # The loaded PG-7V grenade.
    m = g.mag
    m.lathe([(0.36, 0.0), (0.36, 0.0185), (0.42, 0.0185), (0.442, 0.0425), (0.57, 0.0425), (0.575, 0.04), (0.71, 0.013),
             (0.735, 0.009), (0.735, 0.0)], "dark", 28)
    m.lathe([(0.735, 0.0), (0.735, 0.009), (0.75, 0.006), (0.755, 0.0)], "metal", 16)
    m.lathe([(0.57, 0.0428), (0.58, 0.0428)], "metal", 28)
    g.point("Muzzle", (0, 0, 0.4))
    g.point("Eye", (0, 0.052, -0.26))
    g.point("Rail", (0, 0.03, -0.1))
    g.point("Mag", (0, 0, 0.38), (0, 0, -1))
    g.point("Butt", (0, -0.02, -0.22))
    return g


def m32(Part):
    g = Gun(Part, "gl_m32")
    b = g.body
    cy = -0.048
    b.lathe([(0.008, 0.0), (0.008, 0.064), (0.012, 0.068), (0.146, 0.068), (0.15, 0.064), (0.15, 0.0)], "primary", 36, y=cy)
    for k in range(6):
        a = math.radians(k * 60)
        b.cbox((math.cos(a) * 0.066, cy + math.sin(a) * 0.066, 0.078), (0.012, 0.012, 0.12), "dark", bevel=0.002, rot=(0, 0, math.degrees(a)))
        b.tube(0.149, 0.152, 0.021, "metal", x=math.cos(a + math.radians(30)) * 0.045, y=cy + math.sin(a + math.radians(30)) * 0.045, segs=16)
    b.box(-0.022, 0.022, 0.022, 0.03, -0.085, 0.165, "dark", bevel=0.002)
    picatinny(b, -0.075, 0.15, 0.03, "dark")
    b.box(-0.022, 0.022, -0.065, 0.03, -0.085, 0.008, "primary", bevel=0.004)
    b.box(-0.02, 0.02, -0.11, 0.03, 0.15, 0.175, "primary", bevel=0.003)
    b.rod((0, cy, -0.002), (0, cy, 0.16), 0.008, "metal", segs=12)
    b.tube(0.175, 0.44, 0.026, "dark", segs=24)
    b.box(-0.032, 0.032, -0.032, 0.032, 0.195, 0.38, "primary", bevel=0.005, segs=2)
    picatinny(b, 0.2, 0.37, 0.032, "primary")
    picatinny(b, 0.2, 0.37, -0.032, "primary", face="bottom")
    picatinny(b, 0.21, 0.36, 0.0, "primary", face="right", x=0.032)
    trigger_guard(b, -0.03, 0.036, -0.065, -0.09)
    trigger(b, 0.0, -0.065)
    g.point("Grip", *grip(b, (-0.026, -0.065), 0.045, 0.095, 18, "dark", grooves=3))
    up = grip(b, (0.33, -0.0415), 0.034, 0.088, 2, "dark", half_width=0.0135)
    g.point("Foregrip", up[0], up[1])
    s = g.stock
    s.tube(-0.085, -0.25, 0.0145, "dark", y=-0.012, segs=18)
    s.prism([(-0.2, 0.018), (-0.33, 0.024), (-0.336, 0.02), (-0.336, -0.08), (-0.32, -0.084), (-0.25, -0.048), (-0.2, -0.026)],
            -0.021, 0.021, "primary", bevel=0.004, segs=2)
    s.box(-0.0215, 0.0215, -0.085, 0.025, -0.347, -0.336, "dark", bevel=0.003)
    # The reflex sight on the top rail.
    i = g.irons
    i.box(-0.022, 0.022, 0.0395, 0.046, -0.05, 0.035, "dark", bevel=0.002)
    for sx in (-1, 1):
        i.box(sx * 0.02 - 0.003, sx * 0.02 + 0.003, 0.046, 0.08, -0.04, 0.03, "dark", bevel=0.0015)
    i.box(-0.023, 0.023, 0.078, 0.084, -0.04, 0.03, "dark", bevel=0.0015)
    i.box(-0.006, 0.006, 0.046, 0.05, 0.022, 0.03, "glow", bevel=0.0)
    g.point("Muzzle", (0, 0, 0.44))
    g.point("Eye", (0, 0.062, -0.2))
    g.point("Rail", (0, 0.0395, -0.02))
    g.point("Under", (0, -0.0415, 0.26))
    g.point("Side", (0.0415, 0, 0.29))
    g.point("Butt", (0, -0.03, -0.347))
    return g


# ---------------------------------------------------------------------------- blades

def knife(Part):
    g = Gun(Part, "melee_field_knife")
    b = g.body
    b.tube(-0.058, 0.05, 0.0125, "dark", segs=14, bevel=0.002)
    for i in range(9):
        z = -0.05 + i * 0.011
        b.tube(z, z + 0.0025, 0.0131, "dark", segs=14)
    b.box(-0.0095, 0.0095, -0.011, 0.011, -0.072, -0.058, "metal", bevel=0.003)
    b.box(-0.0058, 0.0058, -0.024, 0.017, 0.05, 0.057, "metal", bevel=0.0015)
    b.prism([(0.057, 0.011), (0.19, 0.011), (0.236, -0.002), (0.234, -0.005), (0.2, -0.013), (0.07, -0.016), (0.057, -0.012)],
            -0.0028, 0.0028, "primary", bevel=0.0012)
    b.prism([(0.068, -0.0125), (0.2, -0.0105), (0.233, -0.0035), (0.2, -0.0145), (0.07, -0.0168)], -0.0011, 0.0011, "metal", bevel=0.0003)
    g.point("Grip", (0, 0, -0.004), (0, 0, 1))
    g.point("Muzzle", (0, 0, 0.236))
    return g


def machete(Part):
    g = Gun(Part, "melee_machete")
    b = g.body
    b.tube(-0.068, 0.058, 0.0128, "dark", segs=14, bevel=0.003)
    b.ring((0, 0, -0.06), (1, 0, 0), 0.006, 0.003, 0.028, "dark", 12)
    b.box(-0.004, 0.004, -0.018, 0.016, 0.056, 0.064, "dark", bevel=0.001)
    b.prism([(0.064, 0.013), (0.4, 0.02), (0.47, 0.016), (0.505, 0.002), (0.5, -0.016), (0.42, -0.032), (0.064, -0.016)],
            -0.0018, 0.0018, "primary", bevel=0.0008)
    b.prism([(0.08, -0.015), (0.42, -0.0305), (0.5, -0.0152), (0.42, -0.034), (0.08, -0.0172)], -0.0008, 0.0008, "metal", bevel=0.0002)
    g.point("Grip", (0, 0, -0.004), (0, 0, 1))
    g.point("Muzzle", (0, -0.01, 0.505))
    return g


def tomahawk(Part):
    g = Gun(Part, "melee_tomahawk")
    b = g.body
    b.tube(-0.07, 0.325, 0.0138, "dark", r2=0.0118, segs=14, bevel=0.002)
    for i in range(6):
        z = -0.06 + i * 0.016
        b.tube(z, z + 0.006, 0.0145, "dark", segs=14)
    b.box(-0.0085, 0.0085, -0.016, 0.016, 0.276, 0.326, "primary", bevel=0.003)
    b.prism([(0.28, -0.012), (0.322, -0.012), (0.34, -0.04), (0.365, -0.08), (0.36, -0.09), (0.24, -0.09), (0.236, -0.082),
             (0.262, -0.04)], -0.0042, 0.0042, "primary", bevel=0.0015)
    b.prism([(0.24, -0.0875), (0.36, -0.0875), (0.358, -0.092), (0.242, -0.092)], -0.0018, 0.0018, "metal", bevel=0.0004)
    b.prism([(0.284, 0.012), (0.318, 0.012), (0.304, 0.07), (0.298, 0.07)], -0.0042, 0.0042, "primary", bevel=0.0012)
    g.point("Grip", (0, 0, -0.004), (0, 0, 1))
    g.point("Muzzle", (0, -0.09, 0.3))
    return g


def etool(Part):
    g = Gun(Part, "melee_etool")
    b = g.body
    b.tube(-0.075, 0.37, 0.0145, "primary", segs=14, bevel=0.002)
    b.tube(-0.08, -0.07, 0.016, "dark", segs=14)
    b.tube(0.36, 0.405, 0.019, "metal", segs=16, bevel=0.002)
    b.box(-0.006, 0.006, -0.02, 0.02, 0.385, 0.405, "metal", bevel=0.002)
    b.plate([(-0.075, 0.405), (0.075, 0.405), (0.08, 0.5), (0.062, 0.575), (0.0, 0.615), (-0.062, 0.575), (-0.08, 0.5)],
            -0.0016, 0.0016, "primary", bevel=0.0006)
    b.plate([(0.078, 0.5), (0.06, 0.577), (0.0, 0.617), (-0.06, 0.577), (-0.078, 0.5), (-0.074, 0.5), (-0.058, 0.571), (0.0, 0.61),
             (0.058, 0.571), (0.074, 0.5)], -0.0017, 0.0017, "metal", bevel=0.0)
    b.box(-0.004, 0.004, -0.0025, 0.0025, 0.405, 0.54, "primary", bevel=0.0008)
    g.point("Grip", (0, 0, -0.01), (0, 0, 1))
    g.point("Muzzle", (0, 0, 0.615))
    return g


def all_weapons(Part):
    """Every weapon with a model, by its id."""
    return [
        ar15(Part, "ar_m4a1", 0.405, 0.255, -0.345),
        ak47(Part),
        ar15(Part, "ar_m16a4", 0.548, 0.38, -0.406, fixed_stock=True, carry_handle=True),
        famas(Part),
        mp5(Part, "smg_mp5"),
        mp5(Part, "smg_mp5sd", suppressed=True),
        ump45(Part),
        p90(Part),
        mac10(Part),
        m249(Part),
        pkm(Part),
        m870(Part),
        m1014(Part),
        aa12(Part),
        double_barrel(Part, "sg_double_barrel", 0.6),
        double_barrel(Part, "sg_sawed_off", 0.3, sawn=True),
        m24(Part),
        l115a3(Part),
        m107(Part),
        m14ebr(Part),
        svd(Part),
        mk17(Part),
        m17(Part),
        m1911(Part),
        revolver(Part),
        beretta93r(Part),
        skorpion(Part),
        rpg7(Part),
        m32(Part),
        knife(Part),
        machete(Part),
        tomahawk(Part),
        etool(Part),
    ]


# ---------------------------------------------------------------------------- what they fire

def projectiles(Part, ogive):
    """
    What flies, at its real size, pointing along +z and centred where the simulation has
    it: the RPG-7's grenade, a 40mm grenade, and the four thrown items. Zones: primary is
    the weapon's (or item's) colour, trim its accent, glow a fire's light, dark and metal the
    shared finishes.
    """
    parts = []
    # A PG-7V: the warhead's cone and body, the motor, folding fins and a burning tail.
    p = Part("Rocket")
    p.lathe([(-0.33, 0.0), (-0.33, 0.017), (-0.06, 0.019), (-0.04, 0.0)], "dark", 24)
    p.lathe([(-0.06, 0.0), (-0.06, 0.02), (-0.03, 0.0425), (0.09, 0.0425), (0.096, 0.04)] + ogive(0.096, 0.25, 0.04, 12, tip=0.009)[1:], "trim", 32)
    p.lathe([(0.25, 0.0), (0.25, 0.009), (0.268, 0.006), (0.272, 0.0)], "metal", 16)
    p.lathe([(0.085, 0.0430), (0.093, 0.0430)], "metal", 32)
    for k in range(4):
        a = math.radians(45 + k * 90)
        p.box((math.cos(a) * 0.04, math.sin(a) * 0.04, -0.29), (0.004, 0.004, 0.06), "metal", bevel=0.0005, rot=(0, 0, math.degrees(a)))
        p.box((math.cos(a) * 0.03, math.sin(a) * 0.03, -0.29), (0.02, 0.003, 0.05), "metal", bevel=0.0005, rot=(0, 0, math.degrees(a)))
    p.lathe([(-0.345, 0.0), (-0.345, 0.014), (-0.33, 0.016), (-0.33, 0.0)], "glow", 16)
    parts.append(p)

    # A 40mm M433: an aluminium case and the olive projectile with its fuse.
    p = Part("Grenade40")
    p.lathe([(-0.05, 0.0), (-0.05, 0.0205), (-0.002, 0.0205), (-0.002, 0.0)], "metal", 28)
    p.lathe([(-0.004, 0.0), (-0.004, 0.0198), (0.03, 0.0198)] + ogive(0.03, 0.062, 0.0198, 8, tip=0.006)[1:], "trim", 28)
    p.lathe([(0.012, 0.0201), (0.02, 0.0201)], "primary", 28)
    parts.append(p)

    # An M67: a smooth steel ball, the fuse on top, the spoon down its side, the pin's ring.
    p = Part("FragGrenade")
    p.sphere((0, 0, 0), 0.032, "primary", u=28, v=16)
    p.lathe([(0.026, 0.0), (0.026, 0.011), (0.044, 0.011), (0.047, 0.0085), (0.047, 0.0)], "metal", 18)
    p.box((0.0, 0.026, 0.02), (0.009, 0.004, 0.06), "metal", bevel=0.001, rot=(-28, 0, 0))
    p.ring((-0.014, -0.004, 0.04), (1, 0, 0), 0.0095, 0.007, 0.002, "metal", 18)
    parts.append(p)

    # An RGN: two shells round a fuse with an impact sensor.
    p = Part("ImpactGrenade")
    p.sphere((0, 0, 0), 0.029, "primary", scale=(1, 1, 1.12), u=28, v=16)
    p.lathe([(-0.002, 0.0298), (0.002, 0.0298)], "dark", 28)
    p.lathe([(0.03, 0.0), (0.03, 0.0105), (0.048, 0.0105), (0.051, 0.007), (0.051, 0.0)], "metal", 18)
    p.ring((-0.013, 0.0, 0.043), (1, 0, 0), 0.009, 0.0068, 0.002, "metal", 18)
    parts.append(p)

    # An MK3A2: a fibre tube with metal ends and the fuse.
    p = Part("ShockCharge")
    p.lathe([(-0.07, 0.0), (-0.07, 0.025), (-0.065, 0.027), (0.06, 0.027), (0.065, 0.025), (0.065, 0.0)], "primary", 28)
    for z in (-0.068, 0.062):
        p.lathe([(z - 0.003, 0.0275), (z + 0.003, 0.0275)], "metal", 28)
    p.lathe([(0.065, 0.0), (0.065, 0.011), (0.083, 0.011), (0.086, 0.007), (0.086, 0.0)], "metal", 18)
    p.box((0.0, 0.024, 0.04), (0.009, 0.004, 0.06), "metal", bevel=0.001, rot=(-14, 0, 0))
    parts.append(p)

    # A C4 block: wrapped in tape, a detonator in one end, a light blinking on it.
    p = Part("C4")
    p.box((0, 0, 0), (0.052, 0.034, 0.14), "primary", bevel=0.004)
    for z in (-0.04, 0.04):
        p.box((0, 0, z), (0.054, 0.036, 0.016), "dark", bevel=0.002)
    p.cylinder((0.012, 0.01, 0.07), (0.012, 0.01, 0.095), 0.0045, 0.0045, "metal", segments=12)
    p.box((-0.01, 0.019, 0.03), (0.022, 0.006, 0.03), "dark", bevel=0.001)
    p.sphere((-0.004, 0.0225, 0.038), 0.0028, "glow", u=10, v=6)
    parts.append(p)
    return parts
