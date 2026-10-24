"""A painted look: low-resolution textures with blocky compression, sunlight painted into vertex colours with
real shadows, quantized into visible bands, and every material unlit so the painting is what the app shows.

run() reads the `region` config module: TEXTURES, LIT_COLLECTIONS, TEXTURE_RULES, EMISSIVE, BRICK_COLOURS,
STOREY, SKY_BOX, BACKDROP_CARDS (name prefixes of flat cards that neither subdivide nor cast shadows), inside_rects() ((x0, y0, x1, y1, top) rooms, the first match winning, each with an optional
sixth item: its light colour), and optionally SUN, SUN_COLOR, SKY_COLOR, INSIDE_COLOR, SKY_BANDS."""
import importlib
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import kit
import lib

region = None
SUN = Vector((-0.8, -0.5, 0.34)).normalized()
SUN_COLOR = np.array((0.95, 0.68, 0.38))
SKY_COLOR = np.array((0.4, 0.44, 0.6))
INSIDE_COLOR = np.array((0.62, 0.52, 0.42))
BANDS = 7
GRID = 1.2
rng = np.random.default_rng(3)


# ---------- textures ----------

def blocky(img, block=8, levels=6):
    """JPEG-like look: average a little inside 8x8 blocks, then posterize."""
    h, w = img.shape
    out = img.copy()
    for y in range(0, h, block):
        for x in range(0, w, block):
            cell = out[y:y + block, x:x + block]
            out[y:y + block, x:x + block] = cell * 0.7 + cell.mean() * 0.3
    return np.round(out * levels) / levels


def noise(h, w, scale=1.0):
    return rng.random((h, w)) * scale


def tex_brick():
    h, w = 64, 64
    img = np.full((h, w), 0.86)
    for row in range(0, h, 8):
        offset = 8 if (row // 8) % 2 else 0
        for col in range(-16, w, 16):
            x0 = col + offset
            shade = 0.78 + rng.random() * 0.22
            img[row:row + 7, max(0, x0):max(0, min(w, x0 + 15))] = shade
        img[row + 7:row + 8, :] = 0.55
    for col in range(0, w, 16):
        for row in range(0, h, 8):
            x = col + (8 if (row // 8) % 2 else 0)
            if 0 <= x < w:
                img[row:row + 7, x] = 0.55
    return blocky(img + noise(h, w, 0.06) - 0.03)


def tex_plaster():
    h, w = 64, 64
    base = np.kron(rng.random((8, 8)), np.ones((8, 8))) * 0.06 + 0.88
    return blocky(base + noise(h, w, 0.04) - 0.02, levels=10)


def tex_planks():
    h, w = 64, 64
    img = np.zeros((h, w))
    for col in range(0, w, 10):
        img[:, col:col + 10] = 0.72 + rng.random() * 0.25
        img[:, col] = 0.5
    grain = np.sin(np.linspace(0, 30, h))[:, None] * 0.04
    return blocky(img + grain + noise(h, w, 0.05))


def tex_cobble():
    h, w = 64, 64
    img = np.full((h, w), 0.55)
    for row in range(0, h, 10):
        offset = 5 if (row // 10) % 2 else 0
        for col in range(-10, w, 10):
            x0 = col + offset
            shade = 0.72 + rng.random() * 0.25
            img[row + 1:row + 9, max(0, x0 + 1):max(0, min(w, x0 + 9))] = shade
    return blocky(img + noise(h, w, 0.05))


def tex_slabs(size=32):
    h, w = 64, 64
    img = np.full((h, w), 0.88)
    for y in range(0, h, size):
        for x in range(0, w, size):
            img[y:y + size, x:x + size] = 0.8 + rng.random() * 0.18
    img[::size, :] = 0.6
    img[:, ::size] = 0.6
    return blocky(img + noise(h, w, 0.06) - 0.03)


def tex_asphalt():
    h, w = 64, 64
    img = 0.8 + noise(h, w, 0.18)
    for _ in range(3):
        x, y = rng.integers(0, w), rng.integers(0, h)
        for k in range(30):
            x = (x + rng.integers(-1, 2)) % w
            y = (y + 1) % h
            img[y, x] = 0.5
    return blocky(img)


def tex_tile():
    h, w = 64, 64
    yy, xx = np.mgrid[0:h, 0:w]
    img = np.where(((yy // 8) + (xx // 8)) % 2 == 0, 0.95, 0.72)
    return blocky(img + noise(h, w, 0.04))


def tex_concrete():
    h, w = 64, 64
    img = 0.82 + np.kron(rng.random((4, 4)), np.ones((16, 16))) * 0.1 + noise(h, w, 0.08)
    img[::32, :] = 0.62
    return blocky(img)


def tex_tar():
    h, w = 64, 64
    img = 0.8 + np.kron(rng.random((8, 8)), np.ones((8, 8))) * 0.18 + noise(h, w, 0.06)
    return blocky(img, levels=5)


def tex_metal():
    h, w = 64, 64
    img = 0.82 + (np.sin(np.arange(w) * math.pi / 4)[None, :] * 0.08) + noise(h, w, 0.05)
    return blocky(img)


def tex_fabric():
    h, w = 64, 64
    yy, xx = np.mgrid[0:h, 0:w]
    img = 0.85 + ((yy + xx) % 4 == 0) * 0.08 - ((yy - xx) % 4 == 0) * 0.06
    return blocky(img + noise(h, w, 0.04))


def tex_glass():
    h, w = 64, 64
    img = np.linspace(1.15, 0.75, h)[:, None] * np.ones((1, w))
    for k in range(-20, 64, 24):
        for y in range(h):
            x = k + y // 2
            if 0 <= x < w - 3:
                img[y, x:x + 3] += 0.25
    return blocky(img, levels=6)


def tex_stone():
    h, w = 64, 64
    img = np.full((h, w), 0.6)
    for row in range(0, h, 12):
        offset = 10 if (row // 12) % 2 else 0
        for col in range(-20, w, 20):
            x0 = col + offset
            img[row + 1:row + 12, max(0, x0 + 1):max(0, min(w, x0 + 20))] = 0.78 + rng.random() * 0.2
    return blocky(img + noise(h, w, 0.07) - 0.03)


def tex_plain():
    return blocky(0.9 + noise(64, 64, 0.1), levels=8)


MAKERS = {
    "brick": tex_brick, "plaster": tex_plaster, "planks": tex_planks, "cobble": tex_cobble, "slabs": tex_slabs,
    "paving": lambda: tex_slabs(16), "asphalt": tex_asphalt, "tile": tex_tile, "concrete": tex_concrete, "tar": tex_tar,
    "metal": tex_metal, "fabric": tex_fabric, "glass": tex_glass, "plain": tex_plain, "stone": tex_stone,
}


def save_texture(kind):
    name = f"tex {kind}"
    path = os.path.join(region.TEXTURES, f"{kind}.png")
    gray = np.clip(MAKERS[kind](), 0, 1).astype(np.float32)
    rgba = np.ones((gray.shape[0], gray.shape[1], 4), dtype=np.float32)
    rgba[:, :, 0] = rgba[:, :, 1] = rgba[:, :, 2] = gray
    image = bpy.data.images.get(name)
    if image is not None:
        bpy.data.images.remove(image)
    image = bpy.data.images.new(name, gray.shape[1], gray.shape[0], alpha=False)
    image.pixels.foreach_set(np.flipud(rgba).ravel())
    os.makedirs(region.TEXTURES, exist_ok=True)
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    return image


def texture_kind(mat):
    if mat.get("printed"):
        return None
    n = mat.name.lower()
    color = tuple(mat.diffuse_color[:3])
    brickish = any(abs(color[0] - c[0]) < 0.02 and abs(color[1] - c[1]) < 0.02 for c in region.BRICK_COLOURS)
    rules = region.TEXTURE_RULES
    for key, kind in rules:
        if key in n:
            return kind
    if n.startswith("wall"):
        return "brick" if brickish else "plaster"
    return "plain"


def is_emissive(mat):
    n = mat.name.lower()
    return any(k in n for k in (*region.EMISSIVE, "sky band"))


def make_unlit(mat, image, use_vc=True):
    """Texture x vertex light x tint, straight into the output: the glTF exporter writes this as KHR_materials_unlit."""
    tint = tuple(mat.diffuse_color[:3])
    nodes = mat.node_tree.nodes
    old_image = None
    for node in nodes:
        if node.type == "TEX_IMAGE":
            old_image = node.image
    if image is None:
        image = old_image
    if is_emissive(mat):
        bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is not None and bsdf.inputs["Emission Strength"].default_value > 0:
            emission = bsdf.inputs["Emission Color"].default_value[:3]
            tint = tuple(min(1.0, 0.5 * a + 0.6 * b) for a, b in zip(tint, emission))
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    color = None
    if image is not None:
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.interpolation = "Closest"
        color = tex.outputs["Color"]
    if use_vc:
        attr = nodes.new("ShaderNodeVertexColor")
        attr.layer_name = "Light"
        if color is None:
            color = attr.outputs["Color"]
        else:
            mix = nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            mat.node_tree.links.new(color, mix.inputs["A"])
            mat.node_tree.links.new(attr.outputs["Color"], mix.inputs["B"])
            color = mix.outputs["Result"]
    if not mat.get("printed"):
        tinted = nodes.new("ShaderNodeMix")
        tinted.data_type = "RGBA"
        tinted.blend_type = "MULTIPLY"
        tinted.inputs["Factor"].default_value = 1.0
        tinted.inputs["B"].default_value = (*tint, 1.0)
        if color is None:
            tinted.inputs["A"].default_value = (1.0, 1.0, 1.0, 1.0)
        else:
            mat.node_tree.links.new(color, tinted.inputs["A"])
        color = tinted.outputs["Result"]
    nodes.remove(out)
    lib.unlit_output(mat, color, mat.diffuse_color[3])
    mat.use_backface_culling = False


# ---------- geometry: finer grids so light and shadow can vary across big faces ----------

def refine(obj, limit=GRID):
    if any(len(p.vertices) != 4 for p in obj.data.polygons):
        return
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    for _ in range(8):
        world = obj.matrix_world
        long_edges = [e for e in bm.edges if ((world @ e.verts[0].co) - (world @ e.verts[1].co)).length > limit]
        if not long_edges:
            break
        bmesh.ops.subdivide_edges(bm, edges=long_edges, cuts=1, use_grid_fill=True)
    bm.to_mesh(obj.data)
    bm.free()


def is_printed(obj):
    return any(slot.material is not None and slot.material.get("printed") for slot in obj.material_slots)


def box_uvs(obj, scale=0.5):
    mesh = obj.data
    if mesh.uv_layers.get("UVMap") and is_printed(obj):
        return
    uv = mesh.uv_layers.get("UVMap") or mesh.uv_layers.new(name="UVMap")
    world = obj.matrix_world
    rot = world.to_3x3()
    for poly in mesh.polygons:
        n = rot @ poly.normal
        ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
        for li in poly.loop_indices:
            co = world @ mesh.vertices[mesh.loops[li].vertex_index].co
            if az >= ax and az >= ay:
                u, v = co.x, co.y
            elif ax >= ay:
                u, v = co.y * (1 if n.x > 0 else -1), co.z
            else:
                u, v = co.x * (1 if n.y < 0 else -1), co.z
            uv.data[li].uv = (u * scale, v * scale)


# ---------- light ----------

def build_bvh(objects):
    verts, polys = [], []
    for obj in objects:
        world = obj.matrix_world
        base = len(verts)
        verts.extend(world @ v.co for v in obj.data.vertices)
        polys.extend([base + i for i in p.vertices] for p in obj.data.polygons)
    return BVHTree.FromPolygons(verts, polys, all_triangles=False)


def light_object(obj, bvh, rects, interior):
    mesh = obj.data
    attr = mesh.color_attributes.get("Light") or mesh.color_attributes.new("Light", "BYTE_COLOR", "CORNER")
    world = obj.matrix_world
    rot = world.to_3x3()
    values = np.zeros((len(mesh.loops), 4), dtype=np.float32)
    values[:, 3] = 1.0
    cache = {}
    for poly in mesh.polygons:
        n = (rot @ poly.normal).normalized()
        facing = max(0.0, n.dot(SUN))
        for li in poly.loop_indices:
            vi = mesh.loops[li].vertex_index
            key = (vi, round(n.x, 2), round(n.y, 2), round(n.z, 2))
            if key in cache:
                values[li, :3] = cache[key]
                continue
            co = world @ mesh.vertices[vi].co
            room = next((r for r in rects if r[0] < co.x < r[2] and r[1] < co.y < r[3] and co.z < r[4] - 0.05), None) if interior else None
            if room is not None:
                lift = min(1.0, max(0.0, (co.z % region.STOREY) / 3.0))
                rgb = (np.array(room[5]) if len(room) > 5 else INSIDE_COLOR) * (0.82 + 0.18 * lift)
            else:
                sun = 0.0
                if facing > 0.0:
                    hit = bvh.ray_cast(co + n * 0.03 + SUN * 0.01, SUN, 200.0)
                    sun = facing if hit[0] is None else 0.0
                ground_dark = 0.78 + 0.22 * min(1.0, max(0.0, co.z / 3.0)) if abs(n.z) < 0.5 else 1.0
                up = 0.5 + 0.5 * max(0.0, n.z)
                strength = 0.0 if sun <= 0.0 else 0.45 + 0.55 * sun
                level = math.floor(strength * BANDS + 0.5) / BANDS
                rgb = SKY_COLOR * (0.75 + 0.25 * up) * ground_dark + SUN_COLOR * level
            rgb = np.clip(np.round(rgb * 12) / 12, 0, 1)
            cache[key] = rgb
            values[li, :3] = rgb
    attr.data.foreach_set("color", values.ravel())


# ---------- sky ----------

SKY_BANDS = [
    (0.0, (1.0, 0.78, 0.56)), (8.0, (0.98, 0.8, 0.62)), (16.0, (0.9, 0.8, 0.7)), (24.0, (0.78, 0.78, 0.78)),
    (32.0, (0.66, 0.74, 0.84)), (42.0, (0.55, 0.68, 0.86)), (54.0, (0.46, 0.62, 0.86)), (70.0, (0.4, 0.56, 0.84)),
]


def sky():
    """Banded sky walls hugging the region and a ceiling, close enough for the app's draw distance."""
    lib.clear_collection("Sky")
    x0, y0, x1, y1, top = region.SKY_BOX
    walls = [("N", (x0, y1), (x1, y1)), ("S", (x1, y0), (x0, y0)), ("W", (x0, y0), (x0, y1)), ("E", (x1, y1), (x1, y0))]
    scale = top / SKY_BANDS[-1][0]
    for index in range(len(SKY_BANDS) - 1):
        z0 = SKY_BANDS[index][0] * scale
        z1 = SKY_BANDS[index + 1][0] * scale
        mat = lib.material(f"Sky band {index}", SKY_BANDS[index][1])
        for side, (ax, ay), (bx, by) in walls:
            kit.quad(f"Sky {side} {index}", [(ax, ay, z0), (bx, by, z0), (bx, by, z1), (ax, ay, z1)], mat, "Sky")
    ceiling = lib.material("Sky band top", SKY_BANDS[-1][1])
    kit.quad("Sky ceiling", [(x0, y0, top), (x1, y0, top), (x1, y1, top), (x0, y1, top)], ceiling, "Sky")


def run(config):
    global region, rng, SUN, SUN_COLOR, SKY_COLOR, INSIDE_COLOR, SKY_BANDS
    region = config
    rng = np.random.default_rng(3)
    SUN = Vector(getattr(region, "SUN", SUN)).normalized()
    SUN_COLOR = np.array(getattr(region, "SUN_COLOR", SUN_COLOR))
    SKY_COLOR = np.array(getattr(region, "SKY_COLOR", SKY_COLOR))
    INSIDE_COLOR = np.array(getattr(region, "INSIDE_COLOR", INSIDE_COLOR))
    SKY_BANDS = getattr(region, "SKY_BANDS", SKY_BANDS)
    # Objects a build script just created keep a stale matrix_world until the scene is evaluated, which would light them at the origin.
    bpy.context.view_layer.update()
    images = {kind: save_texture(kind) for kind in MAKERS}
    objects = [o for name in region.LIT_COLLECTIONS for o in bpy.data.collections[name].all_objects if o.type == "MESH"]
    for obj in objects:
        if not is_printed(obj) and not obj.name.startswith(region.BACKDROP_CARDS):
            refine(obj)
        box_uvs(obj)
    bvh = build_bvh([o for o in objects if not o.name.startswith(region.BACKDROP_CARDS)])
    rects = region.inside_rects()
    for obj in objects:
        light_object(obj, bvh, rects, interior=True)
    done = set()
    for obj in objects:
        for slot in obj.material_slots:
            mat = slot.material
            if mat is None or mat.name in done:
                continue
            done.add(mat.name)
            kind = texture_kind(mat)
            make_unlit(mat, images.get(kind) if kind else None, use_vc=not is_emissive(mat))
    sky()
    for mat in bpy.data.materials:
        if mat.name.startswith("Sky band"):
            make_unlit(mat, None, use_vc=False)
    print(len(objects), "objects lit,", len(done), "materials unlit")
