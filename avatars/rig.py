"""Rigs a fused character mesh (one textured shell with no skeleton, as image-to-3D generators make) into a GLB for convert.py.

Pass the job as JSON after "--": {"source", "target", "height", "triangles", "max_edge", "joints", "chains"}.
The mesh must stand in a T- or A-pose facing -Y. It is scaled to "height", stood on the ground at the origin and reduced toward
"triangles", after which edges longer than "max_edge" metres are split so limbs can bend. Joints are estimated from the mesh; "joints" ({bone: [x, y, z]}, in metres after scaling) overrides any of them.
Bones are named as in mpfb_bones.json. Each chain is {"name", "parent", "bones", "region", "falloff", "colour", "points"}:
"region" is {"box": [min, max]}, {"sphere": [centre, radius]} or {"capsule": [a, b, radius]}, softened over "falloff" metres;
"colour" ([[r, g, b], distance]) keeps only vertices whose texture colour lies within that distance; the bones run through
"points" when given, otherwise along the region from its end nearest the parent. Chain bones are named <name>_01, <name>_02, ...
and own the region's vertices, blending into the parent over the first half of the first bone.
"""
import json
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

job = json.loads(sys.argv[sys.argv.index("--") + 1])

for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=job["source"])
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
for obj in list(bpy.data.objects):
    if obj.type != "MESH":
        bpy.data.objects.remove(obj, do_unlink=True)
bpy.ops.object.select_all(action="DESELECT")
for obj in meshes:
    obj.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
body = bpy.context.view_layer.objects.active
body.name = "Body"
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def vertices(obj):
    co = np.empty(len(obj.data.vertices) * 3, dtype=np.float64)
    obj.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


points = vertices(body)
low, high = points.min(0), points.max(0)
scale = job["height"] / (high[2] - low[2])
offset = np.array([(low[0] + high[0]) / 2, (low[1] + high[1]) / 2, low[2]])
body.data.transform(np.diag([scale, scale, scale, 1.0]) @ np.block([[np.eye(3), -offset[:, None]], [np.zeros((1, 3)), np.ones((1, 1))]]))
body.data.update()

triangles = job.get("triangles")
if triangles and len(body.data.polygons) > triangles:
    decimate = body.modifiers.new("Decimate", "DECIMATE")
    decimate.ratio = triangles / len(body.data.polygons)
    decimate.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=decimate.name)
    # Collapsing stretches smooth limbs into long slivers that cannot bend, so long edges are split again.
    longest = job.get("max_edge", 0.03 * job["height"] / 1.65)
    split = bmesh.new()
    split.from_mesh(body.data)
    for _ in range(6):
        long_edges = [e for e in split.edges if e.calc_length() > longest]
        if not long_edges:
            break
        bmesh.ops.subdivide_edges(split, edges=long_edges, cuts=1, use_grid_fill=False)
        bmesh.ops.triangulate(split, faces=[f for f in split.faces if len(f.verts) > 3])
    split.to_mesh(body.data)
    split.free()
    body.data.validate()
    # The source's custom normals no longer match the reduced surface.
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.mesh.customdata_custom_splitnormals_clear()
    body.data.shade_smooth()

V = vertices(body)
H = job["height"]


def slice_at(z, half=0.005, mask=None):
    keep = np.abs(V[:, 2] - z) < half
    return V[keep if mask is None else keep & mask]


def crotch_height():
    """Highest point where a ray from the front at x = 0 passes between the legs instead of hitting the pelvis."""
    tree = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
    pelvis_front = slice_at(0.55 * H, 0.01, mask=np.abs(V[:, 0]) < 0.05 * H)[:, 1].min(initial=0.0)
    for z in np.arange(0.6 * H, 0.3 * H, -0.003):
        hit = tree.ray_cast(Vector((0.0, -2.0, z)), Vector((0.0, 1.0, 0.0)))[0]
        if hit is None or hit.y > pelvis_front + 0.06 * H:
            return z
    return 0.47 * H


def arm_axis(side):
    arm = V[(side * V[:, 0] > 0.22 * H) & (V[:, 2] > 0.5 * H)]
    centre = arm.mean(0)
    direction = np.linalg.svd(arm - centre)[2][0]
    if direction[0] * side < 0:
        direction = -direction
    return arm, centre, direction


def centre_near(pts, origin, direction, distance, width=0.01):
    along = (pts - origin) @ direction
    near = pts[np.abs(along - distance) < width]
    return near.mean(0) if len(near) else origin + direction * distance


def estimate():
    joints = {}
    crotch = crotch_height()
    hip_z = crotch + 0.05 * H
    ankle_z = 0.048 * H
    knee_z = ankle_z + 0.5 * (hip_z - ankle_z)
    for side, tag in ((1, "l"), (-1, "r")):
        leg = (side * V[:, 0] > 0.005) & (side * V[:, 0] < 0.16 * H)
        thigh_slice = slice_at((crotch + knee_z) / 2, 0.01, mask=leg)
        hip = np.array([np.median(thigh_slice[:, 0]), np.median(thigh_slice[:, 1]), hip_z])
        knee = np.median(slice_at(knee_z, 0.01, mask=leg), 0)
        ankle = np.median(slice_at(ankle_z, 0.01, mask=leg), 0)
        foot = V[leg & (V[:, 2] < 0.04 * H)]
        toe = foot[np.argmin(foot[:, 1])]
        toe = np.array([ankle[0], toe[1], 0.015 * H])
        ball = ankle + 0.72 * (toe - ankle)
        ball[2] = 0.015 * H
        joints[f"thigh_{tag}"], joints[f"calf_{tag}"], joints[f"foot_{tag}"] = hip, knee, ankle
        joints[f"ball_{tag}"], joints[f"toe_{tag}"] = ball, toe

        arm, centre, direction = arm_axis(side)
        reach = (arm - centre) @ direction
        tip = centre + direction * reach.max()
        shoulder_along = (side * 0.1 * H - centre[0]) / direction[0]
        shoulder = centre + direction * shoulder_along
        wrist_along = reach.max() - 0.105 * H
        elbow_along = shoulder_along + 0.56 * (wrist_along - shoulder_along)
        joints[f"upperarm_{tag}"] = shoulder
        joints[f"lowerarm_{tag}"] = centre_near(arm, centre, direction, elbow_along)
        joints[f"hand_{tag}"] = centre_near(arm, centre, direction, wrist_along)
        joints[f"fingertip_{tag}"] = tip - direction * 0.01 * H

    pelvis = (joints["thigh_l"] + joints["thigh_r"]) / 2
    shoulders = (joints["upperarm_l"] + joints["upperarm_r"]) / 2
    profile = V[np.abs(V[:, 0]) < 0.015 * H]
    heights = np.arange(shoulders[2] - 0.02 * H, shoulders[2] + 0.15 * H, 0.004)
    front = np.array([profile[np.abs(profile[:, 2] - z) < 0.004, 1].min(initial=np.inf) for z in heights])
    searched = np.where((heights < shoulders[2] + 0.06 * H) & np.isfinite(front), front, -np.inf)
    neck_index = int(np.argmax(searched))
    chin_index = next((i for i in range(neck_index, len(heights)) if front[i] < front[neck_index] - 0.02 * H), neck_index)
    head = np.array([0.0, shoulders[1] + 0.01 * H, heights[chin_index] - 0.005 * H])
    neck = np.array([0.0, shoulders[1], min(shoulders[2], head[2] - 0.04 * H)])
    top = np.array([0.0, head[1], V[np.abs(V[:, 0]) < 0.05 * H, 2].max()])
    joints["pelvis"] = np.array([0.0, pelvis[1], pelvis[2]])
    for index, name in enumerate(("spine_01", "spine_02", "spine_03")):
        t = (index + 1) / 4
        joints[name] = joints["pelvis"] * (1 - t) + neck * t
    joints["neck_01"], joints["head"], joints["head_top"] = neck, head, top
    for side, tag in ((1, "l"), (-1, "r")):
        joints[f"clavicle_{tag}"] = np.array([side * 0.015 * H, neck[1], neck[2] - 0.01 * H])
    return joints


joints = estimate()
for name, position in job.get("joints", {}).items():
    joints[name] = np.array(position, dtype=float)

BONES = [("pelvis", "pelvis", "spine_01", None), ("spine_01", "spine_01", "spine_02", "pelvis"), ("spine_02", "spine_02", "spine_03", "spine_01"),
         ("spine_03", "spine_03", "neck_01", "spine_02"), ("neck_01", "neck_01", "head", "spine_03"), ("head", "head", "head_top", "neck_01")]
for tag in ("l", "r"):
    BONES += [(f"clavicle_{tag}", f"clavicle_{tag}", f"upperarm_{tag}", "spine_03"), (f"upperarm_{tag}", f"upperarm_{tag}", f"lowerarm_{tag}", f"clavicle_{tag}"),
              (f"lowerarm_{tag}", f"lowerarm_{tag}", f"hand_{tag}", f"upperarm_{tag}"), (f"hand_{tag}", f"hand_{tag}", f"fingertip_{tag}", f"lowerarm_{tag}"),
              (f"thigh_{tag}", f"thigh_{tag}", f"calf_{tag}", "pelvis"), (f"calf_{tag}", f"calf_{tag}", f"foot_{tag}", f"thigh_{tag}"),
              (f"foot_{tag}", f"foot_{tag}", f"ball_{tag}", f"calf_{tag}"), (f"ball_{tag}", f"ball_{tag}", f"toe_{tag}", f"foot_{tag}")]

armature = bpy.data.objects.new("Armature", bpy.data.armatures.new("Armature"))
bpy.context.scene.collection.objects.link(armature)
bpy.ops.object.select_all(action="DESELECT")
armature.select_set(True)
bpy.context.view_layer.objects.active = armature
bpy.ops.object.mode_set(mode="EDIT")
edit = armature.data.edit_bones
for name, head, tail, parent in BONES:
    bone = edit.new(name)
    bone.head, bone.tail = Vector(joints[head]), Vector(joints[tail])
    bone.roll = 0.0
for name, head, tail, parent in BONES:
    if parent:
        edit[name].parent = edit[parent]
bpy.ops.object.mode_set(mode="OBJECT")

# Bone heat finds no solution on open, self-intersecting shells or on loose pieces, so weights are solved on the largest
# piece of a watertight voxel copy and transferred to every vertex by proximity.
proxy = body.copy()
proxy.data = body.data.copy()
proxy.name = "WeightProxy"
bpy.context.scene.collection.objects.link(proxy)
remesh = proxy.modifiers.new("Remesh", "REMESH")
remesh.mode = "VOXEL"
remesh.voxel_size = 0.008 * H / 1.65
bpy.ops.object.select_all(action="DESELECT")
proxy.select_set(True)
bpy.context.view_layer.objects.active = proxy
bpy.ops.object.modifier_apply(modifier=remesh.name)
pieces = bmesh.new()
pieces.from_mesh(proxy.data)
pieces.verts.ensure_lookup_table()
label = np.full(len(pieces.verts), -1)
for start in pieces.verts:
    if label[start.index] >= 0:
        continue
    label[start.index] = start.index
    stack = [start]
    while stack:
        vertex = stack.pop()
        for edge in vertex.link_edges:
            other = edge.other_vert(vertex)
            if label[other.index] < 0:
                label[other.index] = start.index
                stack.append(other)
largest = np.bincount(label).argmax()
bmesh.ops.delete(pieces, geom=[v for v in pieces.verts if label[v.index] != largest], context="VERTS")
pieces.to_mesh(proxy.data)
pieces.free()
armature.select_set(True)
bpy.context.view_layer.objects.active = armature
bpy.ops.object.parent_set(type="ARMATURE_AUTO")
for name, *_ in BONES:
    body.vertex_groups.new(name=name)
transfer = body.modifiers.new("Weights", "DATA_TRANSFER")
transfer.object = proxy
transfer.use_vert_data = True
transfer.data_types_verts = {"VGROUP_WEIGHTS"}
transfer.vert_mapping = "POLYINTERP_NEAREST"
transfer.layers_vgroup_select_src = "ALL"
transfer.layers_vgroup_select_dst = "NAME"
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.modifier_apply(modifier=transfer.name)
bpy.data.objects.remove(proxy, do_unlink=True)

names = [name for name, *_ in BONES]
column_of_group = {body.vertex_groups[name].index: column for column, name in enumerate(names)}
weights = np.zeros((len(V), len(names)))
for vertex in body.data.vertices:
    for element in vertex.groups:
        weights[vertex.index, column_of_group[element.group]] = element.weight


def vertex_colours():
    mesh = body.data
    loop_vertex = np.empty(len(mesh.loops), dtype=np.int64)
    mesh.loops.foreach_get("vertex_index", loop_vertex)
    uv = np.empty(len(mesh.loops) * 2)
    mesh.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    loop_material = np.repeat([p.material_index for p in mesh.polygons], [p.loop_total for p in mesh.polygons])
    total, count = np.zeros((len(V), 3)), np.zeros(len(V))
    for index, material in enumerate(mesh.materials):
        bsdf = next((n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if material and material.node_tree else None
        link = bsdf.inputs["Base Color"].links if bsdf else []
        if not link or link[0].from_node.type != "TEX_IMAGE":
            continue
        image = link[0].from_node.image
        w, h = image.size
        pixels = np.array(image.pixels[:], dtype=np.float32).reshape(h, w, -1)[..., :3]
        loops = np.nonzero(loop_material == index)[0]
        u = (np.mod(uv[loops, 0], 1) * (w - 1)).astype(int)
        v = (np.mod(uv[loops, 1], 1) * (h - 1)).astype(int)
        np.add.at(total, loop_vertex[loops], pixels[v, u])
        np.add.at(count, loop_vertex[loops], 1)
    return total / np.maximum(count, 1)[:, None]


def region_weight(region, falloff):
    if "box" in region:
        lo, hi = np.array(region["box"][0]), np.array(region["box"][1])
        inside = np.minimum(V - lo, hi - V).min(1)
    elif "sphere" in region:
        centre, radius = np.array(region["sphere"][0]), region["sphere"][1]
        inside = radius - np.linalg.norm(V - centre, axis=1)
    else:
        a, b, radius = np.array(region["capsule"][0]), np.array(region["capsule"][1]), region["capsule"][2]
        t = np.clip((V - a) @ (b - a) / ((b - a) @ (b - a)), 0, 1)
        inside = radius - np.linalg.norm(V - (a + t[:, None] * (b - a)), axis=1)
    return np.clip(inside / max(falloff, 1e-6), 0, 1)


colours = vertex_colours() if any("colour" in c for c in job.get("chains", [])) else None
# Vertices are split along texture seams; copies at one position must get one decision or the seams crack open.
_, weld = np.unique(np.round(V, 5), axis=0, return_inverse=True)
weld = weld.ravel()
weld_count = np.bincount(weld)
edges = np.empty(len(body.data.edges) * 2, dtype=np.int64)
body.data.edges.foreach_get("vertices", edges)
welded_edges = weld[edges.reshape(-1, 2)]
welded_degree = np.bincount(welded_edges.ravel(), minlength=len(weld_count))
chain_report = []
chain_parts = []
bpy.ops.object.select_all(action="DESELECT")
armature.select_set(True)
bpy.context.view_layer.objects.active = armature
for chain in job.get("chains", []):
    share = region_weight(chain["region"], chain.get("falloff", 0.02))
    if "colour" in chain:
        target, distance = np.array(chain["colour"][0]), chain["colour"][1]
        matching = np.bincount(weld, np.linalg.norm(colours - target, axis=1) <= distance) / weld_count
        # Painted strands and shadows inside the hair miss the colour: growing the match over neighbours and shrinking it
        # back by as much fills those gaps without spreading onto the clothes around the hair.
        for grow in [np.maximum] * 6 + [np.minimum] * 6:
            total = np.zeros(len(matching))
            np.add.at(total, welded_edges[:, 0], matching[welded_edges[:, 1]])
            np.add.at(total, welded_edges[:, 1], matching[welded_edges[:, 0]])
            matching = grow(matching, total / np.maximum(welded_degree, 1))
        share *= np.clip(matching[weld] * 2 - 0.5, 0, 1)
    members = share > 0
    parent_head = np.array(armature.data.bones[chain["parent"]].head_local)
    if "points" in chain:
        path = np.array(chain["points"], dtype=float)
    else:
        pts = V[members]
        centre = pts.mean(0)
        axis = np.linalg.svd(pts - centre)[2][0]
        along = (pts - centre) @ axis
        ends = centre + np.outer([along.min(), along.max()], axis)
        if np.linalg.norm(ends[0] - parent_head) > np.linalg.norm(ends[1] - parent_head):
            axis, along = -axis, -along
        stops = np.linspace(along.min(), along.max(), chain["bones"] + 1)
        path = np.array([pts[np.abs(along - s) < max(0.01, (stops[1] - stops[0]) / 2)].mean(0) for s in stops])
    lengths = np.linalg.norm(np.diff(path, axis=0), axis=1)
    knots = np.concatenate([[0], np.cumsum(lengths)])
    count = len(path) - 1
    bpy.ops.object.mode_set(mode="EDIT")
    edit = armature.data.edit_bones
    chain_names = [f"{chain['name']}_{i + 1:02d}" for i in range(count)]
    previous = edit[chain["parent"]]
    for i, name in enumerate(chain_names):
        bone = edit.new(name)
        bone.head, bone.tail, bone.parent = Vector(path[i]), Vector(path[i + 1]), previous
        previous = bone
    # A VRM spring's last joint only marks where the chain ends, so an unweighted end bone lets the real last bone swing.
    end = edit.new(f"{chain['name']}_{count + 1:02d}")
    end.head = Vector(path[-1])
    end.tail = Vector(path[-1] + (path[-1] - path[-2]) * 0.25)
    end.parent = previous
    bpy.ops.object.mode_set(mode="OBJECT")

    # Arc-length position of each member vertex along the chain, from its nearest segment.
    pts = V[members]
    best = np.full(len(pts), np.inf)
    position = np.zeros(len(pts))
    for i in range(count):
        a, b = path[i], path[i + 1]
        t = np.clip((pts - a) @ (b - a) / max((b - a) @ (b - a), 1e-9), 0, 1)
        d = np.linalg.norm(pts - (a + t[:, None] * (b - a)), axis=1)
        closer = d < best
        best[closer], position[closer] = d[closer], knots[i] + t[closer] * lengths[i]
    segment = np.interp(position, knots, np.arange(count + 1)) - 0.5
    chain_weights = np.zeros((len(pts), count))
    lower = np.clip(np.floor(segment).astype(int), 0, count - 1)
    upper = np.clip(lower + 1, 0, count - 1)
    frac = np.clip(segment - np.floor(segment), 0, 1)
    chain_weights[np.arange(len(pts)), lower] += 1 - frac
    chain_weights[np.arange(len(pts)), upper] += frac
    root = np.clip(position / max(knots[1] * 0.5, 1e-6), 0, 1)
    chain_parts.append((chain["parent"], chain_names, np.nonzero(members)[0], share[members], root, chain_weights))
    chain_report.append({"name": chain["name"], "bones": chain_names, "vertices": int(members.sum()), "length": round(float(knots[-1]), 3)})

# Overlapping chains split a vertex between them; the body keeps whatever share no chain claims.
claimed = np.zeros(len(V))
for _, _, members, share, _, _ in chain_parts:
    claimed[members] += share
over = np.maximum(claimed, 1.0)
weights *= (1 - np.minimum(claimed, 1.0))[:, None]
for parent, chain_names, members, share, root, chain_weights in chain_parts:
    s = share / over[members]
    weights[members, names.index(parent)] += s * (1 - root)
    weights = np.hstack([weights, np.zeros((len(V), len(chain_names)))])
    weights[np.ix_(members, range(len(names), len(names) + len(chain_names)))] = chain_weights * (s * root)[:, None]
    names += chain_names

weakest = np.argsort(weights, axis=1)[:, :-4]
np.put_along_axis(weights, weakest, 0.0, axis=1)
totals = weights.sum(1, keepdims=True)
weights = np.where(totals > 0, weights / np.maximum(totals, 1e-9), 0)
for group in list(body.vertex_groups):
    body.vertex_groups.remove(group)
for column, name in enumerate(names):
    group = body.vertex_groups.new(name=name)
    for vertex_index in np.nonzero(weights[:, column] > 0.001)[0]:
        group.add([int(vertex_index)], float(weights[vertex_index, column]), "REPLACE")

body.parent = armature
modifier = body.modifiers.new("Armature", "ARMATURE")
modifier.object = armature
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True)
armature.select_set(True)
bpy.context.view_layer.objects.active = armature
bpy.ops.export_scene.gltf(filepath=job["target"], use_selection=True, export_format="GLB", export_skins=True, export_animations=False)
result = {"triangles": len(body.data.polygons), "bones": [b.name for b in armature.data.bones], "unweighted": int((totals[:, 0] == 0).sum()),
          "joints": {k: [round(float(c), 3) for c in v] for k, v in joints.items()}, "chains": chain_report}
print("RESULT", json.dumps(result))
