"""
The weapons added to fill each loadout slot to ten: a pistol and a launcher for the secondary
slot, six blades and a hammer for melee. Built with the same shapes and parts as guns.py (and in
its frame: x across, y up, z to the muzzle, the origin on the bore above the trigger), each with
the named points the game holds and dresses it by.
"""
import math
from guns import Gun, grip, trigger_guard, trigger, picatinny, straight_mag, front_post, rear_notch


def common_points(g, muzzle, eye, rail, under, side, support, mag, butt, mag_dir=(0, 1, 0)):
    g.point("Muzzle", muzzle)
    g.point("Eye", eye)
    if rail:
        g.point("Rail", rail)
    if under:
        g.point("Under", under)
    if side:
        g.point("Side", side)
    if support:
        g.point("Support", support, (0, 1, 0))
    if mag:
        g.point("Mag", mag, mag_dir)
    g.point("Butt", butt)


# ---------------------------------------------------------------------------- secondaries

def deagle(Part):
    g = Gun(Part, "pistol_deagle")
    b = g.body
    # The big slide-and-barrel top, the triangular barrel profile, the gas-operated action.
    b.prism([(-0.075, -0.012), (0.18, -0.012), (0.182, 0.012), (0.17, 0.026), (-0.066, 0.026), (-0.075, 0.014)], -0.016, 0.016, "primary", bevel=0.003, segs=2)
    b.prism([(0.03, 0.026), (0.18, 0.026), (0.18, 0.032), (0.03, 0.032)], -0.006, 0.006, "primary", bevel=0.001)
    picatinny(b, 0.0, 0.17, 0.032, "dark", half_width=0.0075, height=0.005)
    b.tube(0.176, 0.184, 0.009, "metal", segs=16)
    b.prism([(0.17, -0.012), (0.17, -0.03), (0.05, -0.034), (0.04, -0.03), (-0.025, -0.03), (-0.07, -0.024), (-0.078, -0.012)],
            -0.0145, 0.0145, "primary", bevel=0.002)
    rear_notch(b, -0.06, 0.038, width=0.02)
    front_post(b, 0.165, 0.032, 0.039)
    trigger_guard(b, -0.022, 0.046, -0.03, -0.058, half_width=0.0065)
    trigger(b, 0.0, -0.03, length=0.016)
    g.point("Grip", *grip(b, (-0.024, -0.03), 0.054, 0.1, 16, "primary", half_width=0.017, grooves=2))
    straight_mag(g.mag, -0.034, -0.068, -0.044, 0.105, 0.0115, "dark", tilt=16, plate_extra=0.004)
    common_points(g, (0, 0, 0.184), (0, 0.0395, -0.34), (0, 0.032, 0.05), (0, -0.034, 0.12), (0.0145, -0.022, 0.12),
                  None, (0, -0.125, -0.08), (0, 0.0, -0.078), mag_dir=(0, math.cos(math.radians(16)), math.sin(math.radians(16))))
    return g


def m202(Part):
    g = Gun(Part, "rl_m202")
    b = g.body
    # Four 66mm rocket tubes in one box, fired one after another, with the clip's frame round its ends.
    b.box(-0.06, 0.06, -0.06, 0.06, -0.36, 0.36, "primary", bevel=0.008)
    for z in (-0.35, 0.33):
        b.box(-0.063, 0.063, -0.063, 0.063, z, z + 0.022, "dark", bevel=0.004)
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.ring((sx * 0.028, sy * 0.028, 0.36), (0, 0, 1), 0.026, 0.022, 0.004, "dark", 18)
            b.ring((sx * 0.028, sy * 0.028, -0.36), (0, 0, 1), 0.026, 0.022, 0.004, "dark", 18)
    trigger_guard(b, -0.028, 0.032, -0.06, -0.084)
    trigger(b, 0.0, -0.06)
    g.point("Grip", *grip(b, (-0.026, -0.06), 0.04, 0.095, 10, "dark", half_width=0.015))
    up = grip(b, (0.22, -0.06), 0.034, 0.088, 4, "dark", half_width=0.0135)
    g.point("Foregrip", up[0], up[1])
    # The shoulder rest under the box, and the sights: a folding rear notch and a front post on top.
    b.box(-0.03, 0.03, -0.07, -0.056, -0.3, -0.14, "dark", bevel=0.003)
    b.box(-0.01, 0.01, 0.06, 0.08, -0.08, -0.06, "dark", bevel=0.001)
    rear_notch(b, -0.07, 0.088, width=0.02, height=0.01, dots=False)
    b.box(-0.006, 0.006, 0.06, 0.08, 0.3, 0.315, "dark", bevel=0.001)
    front_post(b, 0.308, 0.08, 0.09)
    common_points(g, (0, 0, 0.36), (0, 0.09, -0.26), (0, 0.06, -0.05), None, None, None, None, (0, -0.02, -0.25))
    return g


# ---------------------------------------------------------------------------- blades and the hammer

def blade(Part, gid, handle, outline, edge, guard=None, knuckles=False, pommel=True, tip=None):
    g = Gun(Part, gid)
    b = g.body
    h0, h1, r = handle
    b.tube(h0, h1, r, "dark", segs=14, bevel=0.002)
    for i in range(int((h1 - h0) / 0.012)):
        z = h0 + 0.004 + i * 0.012
        b.tube(z, z + 0.0025, r + 0.0006, "dark", segs=14)
    if pommel:
        b.box(-r * 0.75, r * 0.75, -r * 0.9, r * 0.9, h0 - 0.012, h0, "metal", bevel=0.003)
    if guard:
        gy0, gy1 = guard
        b.box(-0.006, 0.006, gy0, gy1, h1, h1 + 0.007, "metal", bevel=0.0015)
    if knuckles:
        # The M1918's brass knuckle bow along the grip.
        for k in range(4):
            z = h0 + 0.01 + k * (h1 - h0 - 0.02) / 3
            b.ring((0, -0.024, z), (0, 0, 1), 0.011, 0.0075, 0.012, "metal", 14)
        b.box(-0.004, 0.004, -0.036, -0.03, h0, h1, "metal", bevel=0.001)
    b.prism(outline, -0.0028, 0.0028, "primary", bevel=0.0012)
    b.prism(edge, -0.0011, 0.0011, "metal", bevel=0.0003)
    g.point("Grip", (0, 0, (h0 + h1) / 2 - 0.02), (0, 0, 1))
    g.point("Muzzle", tip or (0, 0, max(z for z, _ in outline)))
    return g


def sledgehammer(Part):
    g = Gun(Part, "melee_sledge")
    b = g.body
    b.tube(-0.07, 0.62, 0.0155, "primary", r2=0.0135, segs=14, bevel=0.002)
    b.tube(-0.07, 0.08, 0.0175, "dark", segs=14)
    b.box(-0.03, 0.03, -0.042, 0.042, 0.6, 0.66, "metal", bevel=0.006)
    b.box(-0.032, 0.032, -0.046, -0.04, 0.6, 0.66, "dark", bevel=0.002)
    b.box(-0.032, 0.032, 0.04, 0.046, 0.6, 0.66, "dark", bevel=0.002)
    g.point("Grip", (0, 0, 0.0), (0, 0, 1))
    g.point("Muzzle", (0, 0.046, 0.63))
    return g


def katana(Part):
    g = Gun(Part, "melee_katana")
    b = g.body
    # The long, cord-wrapped hilt with its pommel cap, the round guard and the collar at the blade's root.
    b.tube(-0.25, 0.03, 0.0135, "dark", segs=14, bevel=0.002)
    for i in range(11):
        z = -0.235 + i * 0.025
        b.cbox((0, 0, z), (0.029, 0.029, 0.009), "primary", bevel=0.002, rot=(0, 0, 45))
    b.tube(-0.262, -0.25, 0.0145, "metal", segs=14, bevel=0.002)
    b.tube(0.03, 0.038, 0.038, "metal", segs=28, bevel=0.0015)
    b.box(-0.0055, 0.0055, -0.017, 0.013, 0.038, 0.056, "metal", bevel=0.0012)
    # The blade, curving up towards the point, the edge along its underside.
    n = 12
    def curve(z):
        return 0.045 * ((z - 0.056) / 0.72) ** 2
    zs = [0.056 + (0.72 - 0.056) * i / n for i in range(n + 1)]
    width = [0.03 - 0.006 * (z - 0.056) / 0.72 for z in zs]
    top = [(z, curve(z) + w * 0.4) for z, w in zip(zs, width)]
    bottom = [(z, curve(z) - w * 0.6) for z, w in zip(zs, width)]
    tip = (0.78, curve(0.78) + 0.004)
    b.prism(top + [tip] + list(reversed(bottom)), -0.0032, 0.0032, "primary", bevel=0.0012)
    edge = [(z, y + 0.0012) for z, y in bottom[1:]] + [(0.776, curve(0.776) - 0.002)] + [(z, y - 0.0008) for z, y in reversed(bottom[1:])]
    b.prism(edge, -0.0012, 0.0012, "metal", bevel=0.0003)
    g.point("Grip", (0, 0, -0.11), (0, 0, 1))
    g.point("Muzzle", (0, tip[1], tip[0]))
    return g


# ---------------------------------------------------------------------------- the list

def more_weapons(Part):
    """Every weapon added to fill a loadout slot to ten, by its id."""
    return [
        deagle(Part),
        m202(Part),
        blade(Part, "melee_karambit", (-0.055, 0.02, 0.0125),
              [(0.02, 0.008), (0.06, 0.016), (0.11, 0.008), (0.135, -0.02), (0.125, -0.024), (0.098, -0.004), (0.06, -0.006), (0.02, -0.01)],
              [(0.06, -0.006), (0.098, -0.0045), (0.125, -0.0235), (0.1, -0.0075), (0.06, -0.0085)],
              guard=None, pommel=False, tip=(0, -0.022, 0.13)),
        blade(Part, "melee_kukri", (-0.07, 0.04, 0.0135),
              [(0.04, 0.012), (0.18, 0.004), (0.3, -0.03), (0.34, -0.05), (0.33, -0.062), (0.22, -0.048), (0.12, -0.02), (0.04, -0.012)],
              [(0.12, -0.02), (0.22, -0.047), (0.33, -0.061), (0.22, -0.05), (0.12, -0.022)], guard=(-0.018, 0.018)),
        blade(Part, "melee_bowie", (-0.07, 0.04, 0.013),
              [(0.04, 0.014), (0.2, 0.014), (0.24, 0.004), (0.26, -0.004), (0.245, -0.012), (0.2, -0.02), (0.05, -0.022), (0.04, -0.014)],
              [(0.05, -0.02), (0.2, -0.019), (0.255, -0.006), (0.2, -0.022), (0.05, -0.024)], guard=(-0.03, 0.026)),
        blade(Part, "melee_trench", (-0.06, 0.035, 0.012),
              [(0.035, 0.01), (0.18, 0.006), (0.21, 0.0), (0.18, -0.006), (0.035, -0.01)],
              [(0.04, -0.008), (0.18, -0.0055), (0.208, 0.0), (0.18, -0.0075), (0.04, -0.0105)], guard=(-0.02, 0.02), knuckles=True),
        sledgehammer(Part),
        katana(Part),
    ]
