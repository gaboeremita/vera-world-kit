import sys

import bpy
import bmesh
import math
from mathutils import Vector

CEIL = 2.6
SLAB = 0.2
FLOOR_TO_FLOOR = CEIL + SLAB


def collection(name):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def clear_collection(name):
    coll = bpy.data.collections.get(name)
    if coll is None:
        return
    for obj in list(coll.all_objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for child in list(coll.children):
        clear_collection(child.name)
        bpy.data.collections.remove(child)
    bpy.data.collections.remove(coll)


def principled(mat):
    """The material's Principled BSDF, rebuilding a plain one when a later pass replaced the node tree."""
    nodes = mat.node_tree.nodes
    bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        nodes.clear()
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        out = nodes.new("ShaderNodeOutputMaterial")
        mat.node_tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return bsdf


def material(name, color, roughness=0.5, metallic=0.0, alpha=1.0, emission=None, emission_strength=0.0):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = principled(mat)
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Alpha"].default_value = alpha
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    if alpha < 1.0:
        mat.surface_render_method = "BLENDED"
    mat.diffuse_color = (*color, alpha)
    return mat


def unlit_output(mat, colour, alpha=1.0):
    """Sends a colour socket straight to the material output, which the glTF exporter writes as unlit;
    below alpha 1 it mixes in transparency the way the exporter reads as an unlit, alpha-blended material."""
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    out = next((n for n in nodes if n.type == "OUTPUT_MATERIAL"), None) or nodes.new("ShaderNodeOutputMaterial")
    if alpha >= 1.0:
        links.new(colour, out.inputs["Surface"])
        return
    emission = nodes.new("ShaderNodeEmission")
    links.new(colour, emission.inputs["Color"])
    camera = nodes.new("ShaderNodeMixShader")
    links.new(nodes.new("ShaderNodeLightPath").outputs["Is Camera Ray"], camera.inputs["Fac"])
    links.new(nodes.new("ShaderNodeBsdfTransparent").outputs[0], camera.inputs[1])
    links.new(emission.outputs[0], camera.inputs[2])
    blend = nodes.new("ShaderNodeMixShader")
    blend.inputs["Fac"].default_value = alpha
    links.new(nodes.new("ShaderNodeBsdfTransparent").outputs[0], blend.inputs[1])
    links.new(camera.outputs[0], blend.inputs[2])
    links.new(blend.outputs[0], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"


def default_collection():
    """The collection geometry goes into when none is named: the region config's DEFAULT_COLLECTION, else "World"."""
    return getattr(sys.modules.get("region"), "DEFAULT_COLLECTION", "World")


def _link(obj, coll_name):
    collection(coll_name or default_collection()).objects.link(obj)
    return obj


def box(name, x0, y0, z0, x1, y1, z1, mat, coll=None):
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    z0, z1 = min(z0, z1), max(z0, z1)
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x = x0 + (v.co.x + 0.5) * (x1 - x0)
        v.co.y = y0 + (v.co.y + 0.5) * (y1 - y0)
        v.co.z = z0 + (v.co.z + 0.5) * (z1 - z0)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    mesh.materials.append(mat)
    return _link(obj, coll)


def obox(name, center, size, mat, rotation=(0, 0, 0), coll=None):
    """Box of `size` centred at `center`, rotated by `rotation` (degrees, XYZ)."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z *= size[2]
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = center
    obj.rotation_euler = tuple(math.radians(a) for a in rotation)
    mesh.materials.append(mat)
    return _link(obj, coll)


def rod(name, start, end, radius, mat, coll=None, verts=12):
    """Cylinder between two points."""
    start, end = Vector(start), Vector(end)
    direction = end - start
    obj = cylinder(name, 0, 0, -direction.length / 2, direction.length / 2, radius, mat, coll, verts)
    obj.location = (start + end) / 2
    obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    return obj


def cylinder(name, x, y, z0, z1, radius, mat, coll=None, verts=24, radius_top=None):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm, cap_ends=True, segments=verts,
        radius1=radius, radius2=radius if radius_top is None else radius_top,
        depth=z1 - z0,
    )
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (x, y, (z0 + z1) / 2)
    mesh.materials.append(mat)
    return _link(obj, coll)


def sphere(name, x, y, z, radius, mat, coll=None, scale=(1, 1, 1), segments=16):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=max(8, segments // 2), radius=radius)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (x, y, z)
    obj.scale = scale
    mesh.materials.append(mat)
    return _link(obj, coll)


def octahedron(name, x, y, z, radius, mat, coll=None, height=None):
    """Round-ish hanging shape whose faces are all steeper than 45 degrees while height > 0.71 * radius,
    so the navigation grid finds nothing to stand on (lanterns, lamps, floating decor)."""
    h = radius if height is None else height
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    ring = [bm.verts.new((radius * math.cos(a), radius * math.sin(a), 0.0)) for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2)]
    top, bottom = bm.verts.new((0, 0, h)), bm.verts.new((0, 0, -h))
    for k in range(4):
        a, b = ring[k], ring[(k + 1) % 4]
        bm.faces.new((a, b, top))
        bm.faces.new((b, a, bottom))
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (x, y, z)
    mesh.materials.append(mat)
    return _link(obj, coll)


def prism(name, profile, mat, axis="y", t0=0.0, t1=0.1, coll=None):
    """Extrude a 2D profile across `axis`. For axis 'y' the profile is (x, z) points;
    for axis 'x' it is (y, z) points."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()

    def point(u, z, t):
        if axis == "z":
            return (u, z, t)
        return (u, t, z) if axis == "y" else (t, u, z)

    front = [bm.verts.new(point(u, z, t0)) for u, z in profile]
    back = [bm.verts.new(point(u, z, t1)) for u, z in profile]
    bm.faces.new(front)
    bm.faces.new(list(reversed(back)))
    count = len(profile)
    for i in range(count):
        j = (i + 1) % count
        bm.faces.new((front[i], front[j], back[j], back[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    mesh.materials.append(mat)
    return _link(obj, coll)


def arc(name, cx, cy, r_in, r_out, a0, a1, z0, z1, mat, coll=None, segments=32):
    """Partial (or full, a1 - a0 = 360) ring between two radii, angles in degrees."""
    full = abs((a1 - a0) - 360) < 1e-6
    steps = segments if full else max(2, int(segments * (a1 - a0) / 360) + 1)
    count = steps if full else steps + 1
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    rings = []
    for z in (z0, z1):
        inner, outer = [], []
        for i in range(count):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            inner.append(bm.verts.new((cx + r_in * math.cos(a), cy + r_in * math.sin(a), z)))
            outer.append(bm.verts.new((cx + r_out * math.cos(a), cy + r_out * math.sin(a), z)))
        rings.append((inner, outer))
    (bi, bo), (ti, to) = rings
    last = count if full else count - 1
    for i in range(last):
        j = (i + 1) % count
        bm.faces.new((bi[i], bo[i], bo[j], bi[j]))
        bm.faces.new((ti[i], ti[j], to[j], to[i]))
        bm.faces.new((bo[i], to[i], to[j], bo[j]))
        bm.faces.new((bi[i], bi[j], ti[j], ti[i]))
    if not full:
        bm.faces.new((bi[0], ti[0], to[0], bo[0]))
        bm.faces.new((bi[-1], bo[-1], to[-1], ti[-1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    mesh.materials.append(mat)
    return _link(obj, coll)


def window(name, axis, t0, t1, a0, a1, z0, z1, frame_mat, glass_mat, coll=None, bar=0.05, mullion=True):
    """Window in an opening running along `axis` from a0 to a1, frame depth t0..t1."""
    def piece(suffix, r0, r1, h0, h1, mat, d0=t0, d1=t1):
        if axis == "x":
            box(f"{name} {suffix}", r0, d0, h0, r1, d1, h1, mat, coll)
        else:
            box(f"{name} {suffix}", d0, r0, h0, d1, r1, h1, mat, coll)

    piece("frame bottom", a0, a1, z0, z0 + bar, frame_mat)
    piece("frame top", a0, a1, z1 - bar, z1, frame_mat)
    piece("frame left", a0, a0 + bar, z0, z1, frame_mat)
    piece("frame right", a1 - bar, a1, z0, z1, frame_mat)
    if mullion:
        mid = (a0 + a1) / 2
        piece("frame mullion", mid - bar / 2, mid + bar / 2, z0, z1, frame_mat)
    middle = (t0 + t1) / 2
    piece("glass", a0 + bar, a1 - bar, z0 + bar, z1 - bar, glass_mat, middle - 0.005, middle + 0.005)


def wall(name, axis, t0, t1, a, b, mat, openings=(), z0=0.0, z1=CEIL, coll="Walls"):
    """Wall running along `axis` ('x' or 'y') from a to b, spanning t0..t1 across.
    openings: (a0, a1, bottom, top) along the run."""
    def piece(suffix, r0, r1, h0, h1):
        if r1 - r0 < 1e-4 or h1 - h0 < 1e-4:
            return
        if axis == "x":
            box(f"{name}{suffix}", r0, t0, h0, r1, t1, h1, mat, coll)
        else:
            box(f"{name}{suffix}", t0, r0, h0, t1, r1, h1, mat, coll)

    cursor = a
    for index, (o0, o1, bottom, top) in enumerate(sorted(openings)):
        piece(f" seg{index}", cursor, o0, z0, z1)
        piece(f" below{index}", o0, o1, z0, bottom)
        piece(f" above{index}", o0, o1, top, z1)
        cursor = o1
    piece(" end", cursor, b, z0, z1)


def image_material(name, path, roughness=0.6, emission_strength=0.0):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    tex = next((n for n in nodes if n.type == "TEX_IMAGE"), None) or nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path, check_existing=True)
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if emission_strength:
        mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def picture(name, bottom_left, right, width, height, mat, coll=None, up=(0, 0, 1), round_segments=0):
    """Flat quad with 0-1 UVs; it faces the viewer for whom `right` points to the right and `up` points up.
    With round_segments, the face is the ellipse inscribed in that rectangle, cut from the same image."""
    origin, rvec, uvec = Vector(bottom_left), Vector(right).normalized(), Vector(up).normalized()
    if round_segments:
        coords = [(0.5 + 0.5 * math.cos(2 * math.pi * k / round_segments), 0.5 + 0.5 * math.sin(2 * math.pi * k / round_segments))
                  for k in range(round_segments)]
    else:
        coords = [(0, 0), (1, 0), (1, 1), (0, 1)]
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    verts = [bm.verts.new(origin + rvec * (u * width) + uvec * (v * height)) for u, v in coords]
    face = bm.faces.new(verts)
    uv = bm.loops.layers.uv.new("UVMap")
    for loop, coord in zip(face.loops, coords):
        loop[uv].uv = coord
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    mesh.materials.append(mat)
    return _link(obj, coll)


def railing(name, start, end, base_z0, base_z1, mat, collar_mat=None, coll=None, spacing=0.12, height=0.9, round_top=False):
    """Square-baluster railing from start to end (x, y); base heights may differ for a raked stair rail."""
    start, end = Vector((*start, 0)), Vector((*end, 0))
    length = (end - start).length
    count = max(2, int(length / spacing) + 1)
    top0, top1 = base_z0 + height, base_z1 + height
    if round_top:
        rod(f"{name} top rail", (start.x, start.y, top0), (end.x, end.y, top1), 0.022, mat, coll, 12)
    else:
        obox(f"{name} top rail", ((start.x + end.x) / 2, (start.y + end.y) / 2, (top0 + top1) / 2),
             (length, 0.06, 0.035), mat, (0, -math.degrees(math.atan2(top1 - top0, length)), math.degrees(math.atan2(end.y - start.y, end.x - start.x))), coll)
    rod(f"{name} bottom rail", (start.x, start.y, base_z0 + 0.1), (end.x, end.y, base_z1 + 0.1), 0.012, mat, coll, 6)
    for i in range(count):
        f = i / (count - 1)
        p = start + (end - start) * f
        base = base_z0 + (base_z1 - base_z0) * f
        top = top0 + (top1 - top0) * f
        obox(f"{name} baluster {i + 1}", (p.x, p.y, (base + top) / 2), (0.016, 0.016, top - base), mat, (0, 0, 0), coll)
        if collar_mat is not None and 0 < i < count - 1:
            obox(f"{name} collar {i + 1}", (p.x, p.y, base + (top - base) * 0.45), (0.04, 0.04, 0.05), collar_mat, (0, 0, 45), coll)
