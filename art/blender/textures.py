"""
Texture maps for the soldier, baked in Blender.

Each skinned mesh but the face (the uniform, and the kit) gets one UV layout shared by all
its pieces, and two maps over it:

  <Mesh>Normal.jpg  a tangent-space normal map: the weave of the cloth (Poly Haven height
                    maps, at their real size, in art/polyhaven), a ripstop grid, stitching
                    along every hem and seam, leather grain on the boots, neoprene on the
                    gloves, nylon on the carrier and pouches, twill on the webbing;
  <Mesh>Shade.jpg   ambient occlusion: the shade in folds, under straps, pouches and pads,
                    where the body and kit come close.

The face gets SkinNormal.jpg (pores, fine lines round the eyes and on the forehead); its
skin texture is shaded by its own ambient occlusion when human.bake_skin paints it.

The game multiplies a zone's colour by the shade map and lights it with the normal map; the
uniform's pattern is laid over the top at its own scale (see Client/Visuals/ModelLibrary.cs).
"""
import math, os
import bpy, bmesh

HERE = os.path.dirname(os.path.abspath(__file__))
HEIGHTS = os.path.normpath(os.path.join(HERE, "..", "polyhaven"))


# ---------------------------------------------------------------------------- UVs

def unwrap_together(objects, margin=0.004):
    """One UV layout for several objects: cut where the surface turns sharply, every island at the same scale, packed together."""
    for obj in objects:
        if not obj.data.uv_layers:
            obj.data.uv_layers.new(name="UVMap")
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=margin, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    for obj in objects:
        obj["own_uv"] = True


def mark_creases(obj, crease=0.4, limit=0.03):
    """A "hem" attribute on a built piece (a pouch, a plate): how far each vertex is from its nearest sharp edge."""
    import outfit
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    outfit.distance_from_edges(bm, limit=limit, crease=crease)
    if bm.verts.layers.float.get("seam") is None:
        layer = bm.verts.layers.float.new("seam")
        for v in bm.verts:
            v[layer] = 1.0
    bm.to_mesh(obj.data)
    bm.free()


# ---------------------------------------------------------------------------- bake materials

class Nodes:
    """A little help building a node tree: sockets in, sockets out."""

    def __init__(self, mat):
        self.nt = mat.node_tree
        self.n, self.l = self.nt.nodes, self.nt.links
        self.coords = self.n.new("ShaderNodeTexCoord")
        self.xyz = self.n.new("ShaderNodeSeparateXYZ")
        self.l.new(self.coords.outputs["Object"], self.xyz.inputs[0])
        self.nrm = self.n.new("ShaderNodeSeparateXYZ")
        self.l.new(self.coords.outputs["Normal"], self.nrm.inputs[0])

    def link(self, a, b):
        if isinstance(a, (int, float)):
            b.default_value = a
        else:
            self.l.new(a, b)

    def math(self, op, a, b=None, clamp=False):
        m = self.n.new("ShaderNodeMath")
        m.operation = op
        m.use_clamp = clamp
        self.link(a, m.inputs[0])
        if b is not None:
            self.link(b, m.inputs[1])
        return m.outputs[0]

    def ramp(self, value, lo, hi, smooth=True):
        """0 below lo, 1 above hi (or the other way when lo > hi), smoothly between."""
        r = self.n.new("ShaderNodeMapRange")
        if smooth:
            r.interpolation_type = 'SMOOTHSTEP'
        r.inputs["From Min"].default_value = lo
        r.inputs["From Max"].default_value = hi
        self.link(value, r.inputs["Value"])
        return r.outputs["Result"]

    def attribute(self, name):
        a = self.n.new("ShaderNodeAttribute")
        a.attribute_name = name
        return a.outputs["Fac"]

    def image(self, path, tile):
        """A height map laid over the surface from three sides, `tile` metres across."""
        mapping = self.n.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (1 / tile, 1 / tile, 1 / tile)
        self.l.new(self.coords.outputs["Object"], mapping.inputs["Vector"])
        tex = self.n.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(path, check_existing=True)
        tex.image.colorspace_settings.name = 'Non-Color'
        tex.projection = 'BOX'
        tex.projection_blend = 0.25
        tex.interpolation = 'Cubic'
        self.l.new(mapping.outputs[0], tex.inputs["Vector"])
        return tex.outputs["Color"]

    def noise(self, scale, detail=3.0, stretch=(1, 1, 1)):
        mapping = self.n.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (scale * stretch[0], scale * stretch[1], scale * stretch[2])
        self.l.new(self.coords.outputs["Object"], mapping.inputs["Vector"])
        tex = self.n.new("ShaderNodeTexNoise")
        tex.inputs["Detail"].default_value = detail
        self.l.new(mapping.outputs[0], tex.inputs["Vector"])
        return tex.outputs["Fac"]

    def voronoi(self, scale):
        mapping = self.n.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (scale, scale, scale)
        self.l.new(self.coords.outputs["Object"], mapping.inputs["Vector"])
        tex = self.n.new("ShaderNodeTexVoronoi")
        self.l.new(mapping.outputs[0], tex.inputs["Vector"])
        return tex.outputs["Distance"]

    def lines(self, spacing, width):
        """A grid of fine raised lines every `spacing` metres, on whichever two axes run across the surface."""
        total = None
        for axis in ("X", "Y", "Z"):
            c = self.math('FRACT', self.math('DIVIDE', self.xyz.outputs[axis], spacing))
            line = self.ramp(self.math('ABSOLUTE', self.math('SUBTRACT', c, 0.5)), 0.5 - width / spacing, 0.5)
            across = self.math('SUBTRACT', 1.0, self.math('ABSOLUTE', self.nrm.outputs[axis]))
            line = self.math('MULTIPLY', line, self.ramp(across, 0.25, 0.7))
            total = line if total is None else self.math('MAXIMUM', total, line)
        return total

    def dashes(self, length):
        """Stitches: short dashes along whatever line they are masked to."""
        along = self.math('ADD', self.math('ADD', self.xyz.outputs["X"], self.math('MULTIPLY', self.xyz.outputs["Y"], 0.83)),
                          self.math('MULTIPLY', self.xyz.outputs["Z"], 1.21))
        wave = self.math('SINE', self.math('MULTIPLY', along, 2 * math.pi / length))
        return self.ramp(wave, -0.1, 0.45)

    def rows(self, distance, offsets, width=0.0006):
        """Rows of stitching `offsets` metres from an edge or seam (distance is that measure)."""
        total = None
        for o in offsets:
            row = self.ramp(self.math('ABSOLUTE', self.math('SUBTRACT', distance, o)), width, 0.0)
            total = row if total is None else self.math('MAXIMUM', total, row)
        return self.math('MULTIPLY', total, self.dashes(0.0042))

    def bump(self, height, distance, normal=None, strength=1.0):
        b = self.n.new("ShaderNodeBump")
        b.inputs["Distance"].default_value = distance
        b.inputs["Strength"].default_value = strength
        self.link(height, b.inputs["Height"])
        if normal is not None:
            self.l.new(normal, b.inputs["Normal"])
        return b.outputs["Normal"]


def bake_material(name, kind, target):
    """
    A material for baking one kind of surface: its detail as a chain of bumps feeding the
    shader's normal, and the target image as the active node.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    g = Nodes(mat)
    bsdf = g.n["Principled BSDF"]
    H = lambda f: os.path.join(HEIGHTS, f)
    hem = g.attribute("hem")
    seam = g.attribute("seam")
    normal = None
    if kind in ("cloth", "pad"):
        weave = g.image(H("stretch_poplin_disp_512.png"), 0.16) if kind == "cloth" else g.image(H("hessian_230_disp_512.png"), 0.07)
        normal = g.bump(weave, 0.0005)
        if kind == "cloth":
            normal = g.bump(g.lines(0.0065, 0.0005), 0.00035, normal)
        # Fine creases in the cloth.
        normal = g.bump(g.noise(90.0, 4.0, (1.0, 3.0, 1.0)), 0.0007, normal, 0.6)
        # A rolled hem, stitched; seams sunk between two rows of stitching.
        roll = g.ramp(hem, 0.0035, 0.0)
        normal = g.bump(roll, 0.0008, normal)
        normal = g.bump(g.rows(hem, (0.0055, 0.0085)), 0.0005, normal)
        groove = g.math('SUBTRACT', 1.0, g.ramp(seam, 0.0, 0.0018))
        normal = g.bump(g.math('MULTIPLY', groove, -1.0), 0.0009, normal)
        normal = g.bump(g.rows(seam, (0.0035, 0.0062)), 0.0005, normal)
    elif kind == "nylon":
        normal = g.bump(g.image(H("hessian_230_disp_512.png"), 0.075), 0.0005)
        # Binding round every edge, stitched.
        normal = g.bump(g.ramp(hem, 0.004, 0.0), 0.0006, normal)
        normal = g.bump(g.rows(hem, (0.0055,)), 0.0005, normal)
    elif kind == "webbing":
        normal = g.bump(g.image(H("denim_fabric_03_disp_512.png"), 0.05), 0.0006)
        normal = g.bump(g.rows(hem, (0.003,)), 0.0004, normal)
    elif kind == "leather":
        normal = g.bump(g.image(H("brown_leather_disp_512.png"), 0.22), 0.0009)
        normal = g.bump(g.noise(140.0, 4.0), 0.0003, normal, 0.6)
        normal = g.bump(g.rows(hem, (0.004, 0.0065)), 0.0005, normal)
    elif kind == "glove":
        normal = g.bump(g.image(H("scuba_suede_disp_512.png"), 0.09), 0.0006)
        normal = g.bump(g.rows(hem, (0.004,)), 0.0004, normal)
    elif kind == "rubber":
        ridges = g.math('SINE', g.math('MULTIPLY', g.xyz.outputs["Y"], 2 * math.pi / 0.005))
        normal = g.bump(g.ramp(ridges, -0.3, 0.6), 0.0006)
        normal = g.bump(g.noise(300.0, 2.0), 0.0002, normal)
    elif kind == "plastic":
        normal = g.bump(g.noise(220.0, 2.0), 0.0002)
        normal = g.bump(g.ramp(hem, 0.003, 0.0), 0.0005, normal)
    elif kind == "skin":
        # Pores, fine lines round the eyes and on the forehead, and lines on the lips.
        pores = g.voronoi(2600.0)
        normal = g.bump(g.math('MULTIPLY', g.ramp(pores, 0.0, 0.32), -1.0), 0.00012)
        normal = g.bump(g.noise(700.0, 3.0), 0.0001, normal, 0.7)
        y, x, z = g.xyz.outputs["Y"], g.xyz.outputs["X"], g.xyz.outputs["Z"]
        forehead = g.math('MULTIPLY', g.ramp(y, 1.662, 1.672), g.ramp(y, 1.705, 1.69))
        forehead = g.math('MULTIPLY', forehead, g.ramp(z, 0.08, 0.11))
        lines = g.ramp(g.math('SINE', g.math('ADD', g.math('MULTIPLY', y, 2 * math.pi / 0.0075),
                                                  g.math('MULTIPLY', g.noise(30.0, 2.0), 3.0))), 0.7, 1.0)
        normal = g.bump(g.math('MULTIPLY', g.math('MULTIPLY', lines, forehead), -0.5), 0.0001, normal)
        side = g.ramp(g.math('ABSOLUTE', x), 0.046, 0.056)
        corner = g.math('MULTIPLY', side, g.math('MULTIPLY', g.ramp(y, 1.615, 1.625), g.ramp(y, 1.655, 1.645)))
        corner = g.math('MULTIPLY', corner, g.ramp(z, 0.07, 0.095))
        crow = g.ramp(g.math('SINE', g.math('MULTIPLY', g.math('ADD', y, g.math('MULTIPLY', z, 0.6)), 2 * math.pi / 0.004)), 0.6, 1.0)
        normal = g.bump(g.math('MULTIPLY', g.math('MULTIPLY', crow, corner), -1.0), 0.0002, normal)
    if normal is not None:
        g.l.new(normal, bsdf.inputs["Normal"])
    tex = g.n.new("ShaderNodeTexImage")
    tex.image = target
    g.n.active = tex
    return mat


# What each piece is made of, by its zones.
KINDS = {
    "Shirt": {"primary": "cloth"}, "Collar": {"primary": "cloth"}, "Cuffs": {"primary": "cloth"},
    "GloveCuffs": {"dark": "glove"}, "Armbands": {"team": "cloth"}, "ElbowPads": {"trim": "pad"},
    "Trousers": {"primary": "cloth"}, "PocketFlaps": {"primary": "cloth"}, "Gloves": {"dark": "glove"},
    "Boots": {"boots": "leather", "dark": "webbing"}, "Soles": {"dark": "rubber"}, "Laces": {"dark": "webbing"},
    "Carrier": {"trim": "nylon", "dark": "webbing", "team": "cloth", "metal": None},
    "Belt": {"dark": "webbing"}, "BeltKit": {"trim": "nylon", "dark": "webbing", "metal": None},
    "KneePads": {"trim": "plastic"}, "KneeStraps": {"dark": "webbing"},
}


def with_materials(objects, zones, image, prefix):
    """Gives each object bake materials for the image (kept zone by zone), and returns how to put them back."""
    names = {v: k for k, v in zones.items()}
    made = {}
    saved = []
    for obj in objects:
        piece = obj.name.split(".")[0]
        kinds = KINDS.get(piece, {})
        saved.append((obj, [p.material_index for p in obj.data.polygons]))
        indices = [p.material_index for p in obj.data.polygons]
        obj.data.materials.clear()
        for zone in range(13):
            kind = kinds.get(names.get(zone), None) if piece in KINDS else None
            key = (kind, image.name)
            if key not in made:
                made[key] = bake_material("%s_%s_%s" % (prefix, kind or "plain", image.name), kind, image)
            obj.data.materials.append(made[key])
        for p, i in zip(obj.data.polygons, indices):
            p.material_index = i

    def restore():
        for obj, indices in saved:
            obj.data.materials.clear()
            for p, i in zip(obj.data.polygons, indices):
                p.material_index = i
        for mat in made.values():
            bpy.data.materials.remove(mat)
    return restore


def bake(objects, kind, image, samples):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    if kind == 'NORMAL':
        bpy.ops.object.bake(type='NORMAL', normal_space='TANGENT', margin=6, use_clear=True)
    else:
        bpy.ops.object.bake(type=kind, margin=6, use_clear=True)


def occlusion(nt, distance, strength):
    """Nodes giving 1 in the open, falling towards 1 - strength where the surface is enclosed."""
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.samples = 16
    ao.inputs["Distance"].default_value = distance
    soft = nt.nodes.new("ShaderNodeMapRange")
    soft.inputs["From Min"].default_value = 0.0
    soft.inputs["From Max"].default_value = 1.0
    soft.inputs["To Min"].default_value = 1.0 - strength
    soft.inputs["To Max"].default_value = 1.0
    nt.links.new(ao.outputs["AO"], soft.inputs["Value"])
    return soft.outputs["Result"]


def with_shade(objects, image, distance=0.12, strength=0.82):
    """Gives objects one material that glows with how open each point is, for an EMIT bake into image."""
    mat = bpy.data.materials.new("shade_" + image.name)
    mat.use_nodes = True
    nt = mat.node_tree
    for node in list(nt.nodes):
        nt.nodes.remove(node)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(occlusion(nt, distance, strength), emit.inputs["Color"])
    nt.links.new(emit.outputs[0], out.inputs[0])
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = image
    nt.nodes.active = tex
    saved = []
    for obj in objects:
        indices = [p.material_index for p in obj.data.polygons]
        saved.append((obj, indices))
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        for p in obj.data.polygons:
            p.material_index = 0

    def restore():
        for obj, indices in saved:
            obj.data.materials.clear()
            for p, i in zip(obj.data.polygons, indices):
                p.material_index = i
        bpy.data.materials.remove(mat)
    return restore


def ensure_world(distance=0.12):
    scene = bpy.context.scene
    if scene.world is None:
        scene.world = bpy.data.worlds.new("bake")
    scene.world.light_settings.distance = distance


def save(image, path, quality=92):
    image.filepath_raw = path
    image.file_format = 'JPEG'
    scene = bpy.context.scene
    scene.render.image_settings.quality = quality
    image.save()


def bake_maps(objects, zones, name, out_dir, size=2048, hide=()):
    """
    The normal and shade maps for a mesh made of these objects (already sharing one UV
    layout): <name>Normal.jpg and <name>Shade.jpg in out_dir. Objects in `hide` cast no shade.
    """
    ensure_world()
    for obj in objects:
        if obj.data.attributes.get("hem") is None:
            mark_creases(obj)
    for obj in hide:
        obj.hide_render = True

    normal = bpy.data.images.new(name + "Normal", size, size, alpha=False)
    normal.colorspace_settings.name = 'Non-Color'
    restore = with_materials(objects, zones, normal, name + "N")
    bake(objects, 'NORMAL', normal, 6)
    restore()
    save(normal, os.path.join(out_dir, name + "Normal.jpg"))

    # The shade: ambient occlusion, softened so the deepest folds are shaded rather than
    # black, baked as colour (sRGB), as the game reads it.
    shade = bpy.data.images.new(name + "Shade", size // 2, size // 2, alpha=False)
    restore = with_shade(objects, shade)
    bake(objects, 'EMIT', shade, 32)
    restore()
    save(shade, os.path.join(out_dir, name + "Shade.jpg"))
    for obj in hide:
        obj.hide_render = False
    return os.path.join(out_dir, name + "Normal.jpg"), os.path.join(out_dir, name + "Shade.jpg")


def bake_face(head, out_dir, hide=()):
    """The face's normal map: SkinNormal.jpg."""
    ensure_world(0.05)
    for obj in hide:
        obj.hide_render = True
    size = 1024
    normal = bpy.data.images.new("SkinNormal", size, size, alpha=False)
    normal.colorspace_settings.name = 'Non-Color'
    saved = [p.material_index for p in head.data.polygons]
    head.data.materials.clear()
    mat = bake_material("skin_bake", "skin", normal)
    head.data.materials.append(mat)
    for p in head.data.polygons:
        p.material_index = 0
    bake([head], 'NORMAL', normal, 6)
    head.data.materials.clear()
    bpy.data.materials.remove(mat)
    for p, i in zip(head.data.polygons, saved):
        p.material_index = i
    for obj in hide:
        obj.hide_render = False
    save(normal, os.path.join(out_dir, "SkinNormal.jpg"))
    return os.path.join(out_dir, "SkinNormal.jpg")


def bake_hair(obj, s, path, size=512):
    """A hairstyle's strand normal map: fine strands running the way the hair is combed (its "across" attribute measures across them)."""
    ensure_world()
    image = bpy.data.images.new(obj.name + "Normal", size, size, alpha=False)
    image.colorspace_settings.name = 'Non-Color'
    spacing, length = s.strands()
    mat = bpy.data.materials.new(obj.name + "_bake")
    mat.use_nodes = True
    g = Nodes(mat)
    across = g.attribute("across")
    # Strands: fine ridges across the comb direction, wandering as they run along it.
    wander = g.math('MULTIPLY', g.noise(30.0 / length, 2.0), 7.0)
    phase = g.math('ADD', g.math('MULTIPLY', across, 2 * math.pi / spacing), wander)
    strands = g.ramp(g.math('SINE', phase), -1.0, 1.0)
    # Some strands stand proud of the rest; locks part here and there.
    strands = g.math('MULTIPLY', strands, g.ramp(g.noise(140.0, 2.0), 0.3, 0.7))
    normal = g.bump(strands, 0.0003)
    locks = g.ramp(g.math('SINE', g.math('ADD', g.math('MULTIPLY', across, 2 * math.pi / (spacing * 9)),
                                         g.math('MULTIPLY', g.noise(12.0 / length, 2.0), 5.0))), -1.0, 1.0)
    normal = g.bump(locks, 0.0006, normal)
    g.l.new(normal, g.n["Principled BSDF"].inputs["Normal"])
    tex = g.n.new("ShaderNodeTexImage")
    tex.image = image
    g.n.active = tex
    indices = [p.material_index for p in obj.data.polygons]
    obj.data.materials.clear()
    for _ in range(max(indices) + 1):
        obj.data.materials.append(mat)
    for p, i in zip(obj.data.polygons, indices):
        p.material_index = i
    bake([obj], 'NORMAL', image, 4)
    obj.data.materials.clear()
    for p, i in zip(obj.data.polygons, indices):
        p.material_index = i
    bpy.data.materials.remove(mat)
    save(image, path)
    return path
