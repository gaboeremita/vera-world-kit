"""Exports a region GLB in chunks the app draws by distance.

- Backdrop: the sky and the region's backdrop meshes, marked `backdrop`, drawn at any distance.
- Street chunks: a CELL x CELL grid, full detail within the street draw distance and a `lowDetail`
  version of flat-coloured boxes beyond it.
- Interior chunks: what is inside each enterable building, drawn only up close. Outer walls, roofs,
  ground floors and ceilings stay with the street, so a building never opens a hole when its inside hides.
- Anything wider than a cell (roads, ground, perimeter, wires) is drawn always.
Meshes are merged per material inside each group, in name order. Works on copies, so the .blend stays untouched.

run() reads the `region` config module: OUT, TEXTURES, EXPORT_COLLECTIONS, INTERIOR_COLLECTION, BACKDROP_NAMES,
LANDMARKS, enterable() -> {building: (x0, y0, x1, y1, roof)}, and optionally CELL, STREET_DRAW_DISTANCE,
INTERIOR_DRAW_DISTANCE, LOW_DETAIL_MIN_SIZE."""
import bpy
import math
import os
import re

import bmesh
import numpy as np
from mathutils import Vector

import kit

EXPORT = "Export"
CELL = 32.0
STREET_DRAW_DISTANCE = 60.0
INTERIOR_DRAW_DISTANCE = 25.0
LOW_DETAIL_MIN_SIZE = 1.5
SHELL = re.compile(r"^(?P<building>.+) (wall [NSEW](\d+( over| under)?| end)|floor|roof|ceiling)$")

region = None
export = None
ENTERABLE = {}


def world_box(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return Vector([min(c[i] for c in corners) for i in range(3)]), Vector([max(c[i] for c in corners) for i in range(3)])


def building_at(x, y, top):
    for name, (x0, y0, x1, y1, roof) in ENTERABLE.items():
        if x0 <= x <= x1 and y0 <= y <= y1 and top <= roof + 0.05:
            return name
    return None


def classify(obj, collection):
    """('backdrop',), ('always',), ('interior', building) or ('street', ix, iy)."""
    if collection == "Sky" or obj.name.startswith(region.BACKDROP_NAMES):
        return ("backdrop",)
    low, high = world_box(obj)
    if max(high.x - low.x, high.y - low.y) > CELL:
        return ("always",)
    centre = (low + high) / 2
    if collection == region.INTERIOR_COLLECTION and not SHELL.match(obj.name) and not obj.name.startswith(region.LANDMARKS):
        building = building_at(centre.x, centre.y, high.z)
        if building is not None:
            return ("interior", building)
    return ("street", math.floor(centre.x / CELL), math.floor(centre.y / CELL))


# ---------- low detail: one box per sizeable object, each side coloured like the faces it stands for ----------

_image_means = {}


def image_mean(image):
    if image.name not in _image_means:
        pixels = np.empty(len(image.pixels), dtype=np.float32)
        image.pixels.foreach_get(pixels)
        srgb = pixels.reshape(-1, 4)[:, :3]
        linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
        _image_means[image.name] = linear.mean(axis=0)
    return _image_means[image.name]


def material_colour(mat):
    colour = np.ones(3)
    if mat is None or mat.node_tree is None:
        return colour
    for node in mat.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image is not None:
            colour = colour * image_mean(node.image)
        if node.type == "MIX" and node.blend_type == "MULTIPLY" and not node.inputs["B"].is_linked:
            colour = colour * np.array(node.inputs["B"].default_value[:3])
    return colour


def face_colours(obj):
    """Area-weighted colour of the object's faces for each of the six axis directions, and overall."""
    mesh = obj.data
    count = len(mesh.polygons)
    if count == 0:
        return None
    normals = np.empty(count * 3, dtype=np.float32)
    mesh.polygons.foreach_get("normal", normals)
    normals = normals.reshape(-1, 3) @ np.array(obj.matrix_world.to_3x3()).T
    areas = np.empty(count, dtype=np.float32)
    mesh.polygons.foreach_get("area", areas)
    indices = np.empty(count, dtype=np.int32)
    mesh.polygons.foreach_get("material_index", indices)
    slots = [material_colour(slot.material) for slot in obj.material_slots] or [np.ones(3)]
    base = np.array([slots[min(i, len(slots) - 1)] for i in indices])
    light = np.ones((count, 3))
    attribute = mesh.color_attributes.get("Light")
    if attribute is not None and attribute.domain == "CORNER":
        loops = np.empty(len(mesh.loops) * 4, dtype=np.float32)
        attribute.data.foreach_get("color", loops)
        loops = loops.reshape(-1, 4)[:, :3]
        starts = np.empty(count, dtype=np.int32)
        totals = np.empty(count, dtype=np.int32)
        mesh.polygons.foreach_get("loop_start", starts)
        mesh.polygons.foreach_get("loop_total", totals)
        light = np.add.reduceat(loops, starts) / totals[:, None]
    colours = base * light
    weights = np.maximum(areas, 1e-6)
    overall = (colours * weights[:, None]).sum(axis=0) / weights.sum()
    axis = np.abs(normals).argmax(axis=1)
    sign = np.take_along_axis(normals, axis[:, None], axis=1)[:, 0] > 0
    sides = {}
    for a in range(3):
        for positive in (False, True):
            chosen = (axis == a) & (sign == positive)
            if chosen.any():
                w = weights[chosen]
                sides[(a, positive)] = (colours[chosen] * w[:, None]).sum(axis=0) / w.sum()
    return overall, sides


BOX_SIDES = [
    ((0, False), [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)]),
    ((0, True), [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)]),
    ((1, False), [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]),
    ((1, True), [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)]),
    ((2, False), [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)]),
    ((2, True), [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]),
]


def low_detail_mesh(name, objects, material):
    bm = bmesh.new()
    colour_layer = bm.loops.layers.float_color.new("Light")
    boxes = 0
    for obj in objects:
        low, high = world_box(obj)
        if max(high - low) < LOW_DETAIL_MIN_SIZE:
            continue
        colours = face_colours(obj)
        if colours is None:
            continue
        overall, sides = colours
        size = high - low
        for key, corners in BOX_SIDES:
            axis = key[0]
            if size[axis] < 0.02 and key[1] is False:
                continue
            verts = [bm.verts.new((low.x + c[0] * size.x, low.y + c[1] * size.y, low.z + c[2] * size.z)) for c in corners]
            face = bm.faces.new(verts)
            colour = sides.get(key, overall)
            for loop in face.loops:
                loop[colour_layer] = (*colour, 1.0)
        boxes += 1
    if boxes == 0:
        bm.free()
        return None
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.color_attributes.active_color = mesh.color_attributes["Light"]
    mesh.color_attributes.render_color_index = mesh.color_attributes.active_color_index
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    obj["lowDetail"] = True
    export.objects.link(obj)
    return obj


# ---------- shared surfaces: tints baked into the vertex light, signs packed into one atlas ----------

SIGN_ATLAS_WIDTH = 512
SIGN_PADDING = 1


def material_image(mat):
    return next((n.image for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image is not None), None)


def material_tint(mat):
    tint = np.ones(3)
    for node in mat.node_tree.nodes:
        if node.type == "MIX" and node.blend_type == "MULTIPLY" and not node.inputs["B"].is_linked:
            tint = tint * np.array(node.inputs["B"].default_value[:3])
    return tint


def uses_light(mat):
    return any(n.type == "VERTEX_COLOR" for n in mat.node_tree.nodes)


def surface_material(name, image):
    """Texture x vertex light, straight into the output, which the glTF exporter writes as unlit."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    attr = nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "Light"
    colour = attr.outputs["Color"]
    if image is not None:
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.interpolation = "Closest"
        mix = nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        mat.node_tree.links.new(tex.outputs["Color"], mix.inputs["A"])
        mat.node_tree.links.new(colour, mix.inputs["B"])
        colour = mix.outputs["Result"]
    mat.node_tree.links.new(colour, out.inputs["Surface"])
    mat.use_backface_culling = False
    return mat


def sign_atlas(images):
    """Packs the sign images in rows, each with a 1 px border of its own edge pixels; returns the atlas and each image's pixel rect."""
    placed = {}
    x = y = row = 0
    for image in sorted(images, key=lambda i: (-i.size[1], i.name)):
        w, h = image.size[0] + 2 * SIGN_PADDING, image.size[1] + 2 * SIGN_PADDING
        if x + w > SIGN_ATLAS_WIDTH:
            x, y, row = 0, y + row, 0
        placed[image.name] = (x + SIGN_PADDING, y + SIGN_PADDING, image.size[0], image.size[1])
        x += w
        row = max(row, h)
    height = 1
    while height < y + row:
        height *= 2
    pixels = np.zeros((height, SIGN_ATLAS_WIDTH, 4), dtype=np.float32)
    pixels[:, :, 3] = 1.0
    for image in images:
        px, py, w, h = placed[image.name]
        source = np.empty(w * h * 4, dtype=np.float32)
        image.pixels.foreach_get(source)
        source = np.pad(source.reshape(h, w, 4), ((SIGN_PADDING, SIGN_PADDING), (SIGN_PADDING, SIGN_PADDING), (0, 0)), mode="edge")
        pixels[py - SIGN_PADDING:py + h + SIGN_PADDING, px - SIGN_PADDING:px + w + SIGN_PADDING] = source
    atlas = bpy.data.images.get("sign atlas")
    if atlas is not None:
        bpy.data.images.remove(atlas)
    atlas = bpy.data.images.new("sign atlas", SIGN_ATLAS_WIDTH, height, alpha=False)
    atlas.pixels.foreach_set(pixels.ravel())
    atlas.filepath_raw = os.path.join(region.TEXTURES, "sign-atlas.png")
    atlas.file_format = "PNG"
    atlas.save()
    return atlas, placed, (SIGN_ATLAS_WIDTH, height)


def shared_surfaces(objects):
    """For each source material: the shared material its copies use, and how to rewrite a copy for it."""
    materials = sorted({obj.material_slots[0].material for obj in objects}, key=lambda m: m.name)
    signs = [m for m in materials if (material_image(m) is not None and material_image(m).name.startswith("sign"))]
    atlas, placed, atlas_size = sign_atlas({material_image(m) for m in signs}) if signs else (None, {}, None)
    surfaces = {}
    for mat in materials:
        image = material_image(mat)
        is_sign = mat in signs
        target = surface_material(f"Surface · {'signs' if is_sign else (image.name if image else 'colour')}", atlas if is_sign else image)
        surfaces[mat.name] = {
            "material": target,
            "tint": material_tint(mat),
            "light": uses_light(mat),
            "rect": placed[image.name] if is_sign else None,
            "atlas": atlas_size if is_sign else None,
        }
    return surfaces


def bake_surface(copy, surface):
    mesh = copy.data
    attribute = mesh.color_attributes["Light"]
    colours = np.empty(len(attribute.data) * 4, dtype=np.float32)
    attribute.data.foreach_get("color", colours)
    colours = colours.reshape(-1, 4)
    if not surface["light"]:
        colours[:, :3] = 1.0
    colours[:, :3] *= surface["tint"]
    attribute.data.foreach_set("color", colours.ravel())
    if surface["rect"] is not None:
        px, py, w, h = surface["rect"]
        aw, ah = surface["atlas"]
        uv = mesh.uv_layers.active.data
        coords = np.empty(len(uv) * 2, dtype=np.float32)
        uv.foreach_get("uv", coords)
        coords = coords.reshape(-1, 2)
        coords[:, 0] = (px + coords[:, 0] * w) / aw
        coords[:, 1] = (py + coords[:, 1] * h) / ah
        uv.foreach_set("uv", coords.ravel())
    copy.material_slots[0].material = surface["material"]


# ---------- grouping and merging ----------

def merged_copies(objects, label, surfaces=None):
    """Copies of the objects joined per material, named after the material and the group.
    With surfaces, each copy first takes its shared material, so copies of many tints merge into one mesh."""
    by_material = {}
    for obj in objects:
        name = surfaces[obj.material_slots[0].material.name]["material"].name if surfaces else obj.material_slots[0].material.name
        by_material.setdefault(name, []).append(obj)
    merged = []
    for material_name, members in by_material.items():
        copies = []
        for obj in members:
            copy = obj.copy()
            copy.data = obj.data.copy()
            export.objects.link(copy)
            if surfaces:
                bake_surface(copy, surfaces[obj.material_slots[0].material.name])
            copies.append(copy)
        bpy.ops.object.select_all(action="DESELECT")
        for copy in copies:
            copy.select_set(True)
        bpy.context.view_layer.objects.active = copies[0]
        if len(copies) > 1:
            bpy.ops.object.join()
        target = bpy.context.view_layer.objects.active
        target.name = f"{material_name} · {label}" if label else material_name
        merged.append(target)
    return merged


def group_empty(name, **properties):
    empty = bpy.data.objects.new(name, None)
    for key, value in properties.items():
        empty[key] = value
    export.objects.link(empty)
    return empty


def parent(children, empty):
    for child in children:
        world = child.matrix_world.copy()
        child.parent = empty
        child.matrix_world = world


def run(config):
    global region, export, ENTERABLE, CELL, STREET_DRAW_DISTANCE, INTERIOR_DRAW_DISTANCE, LOW_DETAIL_MIN_SIZE
    region = config
    CELL = getattr(region, "CELL", CELL)
    STREET_DRAW_DISTANCE = getattr(region, "STREET_DRAW_DISTANCE", STREET_DRAW_DISTANCE)
    INTERIOR_DRAW_DISTANCE = getattr(region, "INTERIOR_DRAW_DISTANCE", INTERIOR_DRAW_DISTANCE)
    LOW_DETAIL_MIN_SIZE = getattr(region, "LOW_DETAIL_MIN_SIZE", LOW_DETAIL_MIN_SIZE)
    ENTERABLE = region.enterable()
    OUT = region.OUT
    # Objects a build script just created keep a stale matrix_world until the scene is evaluated, which would put them in the wrong chunk.
    bpy.context.view_layer.update()

    old = bpy.data.collections.get(EXPORT)
    if old is not None:
        for obj in list(old.objects):
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and data.users == 0:
                bpy.data.meshes.remove(data)
        bpy.data.collections.remove(old)
    export = bpy.data.collections.new(EXPORT)
    bpy.context.scene.collection.children.link(export)

    lit = [m for m in bpy.data.materials if m.node_tree and any(n.type == "VERTEX_COLOR" for n in m.node_tree.nodes)]
    assert lit, "run look before exporting: no material carries the painted light"

    groups = {}
    for collection in region.EXPORT_COLLECTIONS:
        for obj in sorted(bpy.data.collections[collection].all_objects, key=lambda o: o.name):
            if obj.type != "MESH" or not obj.material_slots:
                continue
            groups.setdefault(classify(obj, collection), []).append(obj)

    surfaces = shared_surfaces([obj for key, objects in groups.items() if key[0] != "backdrop" for obj in objects])
    material = surface_material("Surface · colour", None)
    roots = []
    street_chunks = interior_chunks = 0
    for key, objects in sorted(groups.items(), key=lambda item: tuple(str(part) for part in item[0])):
        kind = key[0]
        if kind == "always":
            roots += merged_copies(objects, "", surfaces)
            continue
        if kind == "backdrop":
            empty = group_empty("Backdrop", backdrop=True)
            parent(merged_copies(objects, "backdrop"), empty)
        elif kind == "interior":
            empty = group_empty(f"Interior · {key[1]}", drawDistance=INTERIOR_DRAW_DISTANCE)
            parent(merged_copies(objects, key[1], surfaces), empty)
            interior_chunks += 1
        else:
            label = f"cell {key[1]} {key[2]}"
            empty = group_empty(f"Chunk · {label}", drawDistance=STREET_DRAW_DISTANCE)
            children = merged_copies(objects, label, surfaces)
            low = low_detail_mesh(f"Low detail · {label}", objects, material)
            if low is not None:
                children.append(low)
            parent(children, empty)
            street_chunks += 1
        roots.append(empty)

    bpy.ops.object.select_all(action="DESELECT")
    for obj in export.objects:
        obj.select_set(True)
    for obj in bpy.data.collections[kit.MARKERS].all_objects:
        obj.hide_set(False)
        obj.select_set(True)

    bpy.ops.export_scene.gltf(
        filepath=OUT,
        export_format="GLB",
        use_selection=True,
        export_extras=True,
        export_apply=True,
        export_cameras=False,
        export_lights=False,
        export_yup=True,
        export_vertex_color="ACTIVE",
    )

    for obj in bpy.data.collections[kit.MARKERS].all_objects:
        obj.select_set(False)
    meshes = sum(1 for obj in export.objects if obj.type == "MESH")
    for obj in list(export.objects):
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and data.users == 0:
            bpy.data.meshes.remove(data)
    bpy.data.collections.remove(export)
    print("exported", OUT, os.path.getsize(OUT) // 1024, "KB,", meshes, "meshes,", street_chunks, "street chunks,", interior_chunks, "interiors")
