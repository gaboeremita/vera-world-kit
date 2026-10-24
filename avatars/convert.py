"""Turns a rigged GLB character into a VRM 1.0 avatar: cleans the import, sizes it, maps the humanoid bones and exports.

Pass the job as JSON after "--": {"source", "target", "name", "author", "height", "tint": {material substring: [r, g, b]}, "bones",
"springs"}. "springs" maps a spring group name to {"chains", "stiffness", "gravity", "drag", "radius", "colliders"}: every bone named
<chain>_NN for each listed chain becomes a joint of one spring per chain, and each bone in "colliders" gets a capsule along it,
sized from the mesh it moves.
"""
import bpy
from mathutils import Vector

import contextlib
import json
import sys

job = json.loads(sys.argv[sys.argv.index("--") + 1])


def override():
    return contextlib.nullcontext()


for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

with override():
    if job["source"].endswith(".vrm"):
        bpy.ops.import_scene.vrm(filepath=job["source"])
    else:
        bpy.ops.import_scene.gltf(filepath=job["source"])

armature = max((o for o in bpy.data.objects if o.type == "ARMATURE"), key=lambda o: len(o.data.bones))
for action in list(bpy.data.actions):
    bpy.data.actions.remove(action)
for obj in bpy.data.objects:
    if obj.animation_data:
        obj.animation_data_clear()
armature.data.pose_position = "REST"
import re
for bone in ([] if job.get("bones") else armature.data.bones):
    clean = re.sub(r"^(GLTF_created_\d+_|mixamorig\d*:|[A-Za-z0-9]+:)", "", bone.name)
    clean = re.sub(r"_\d+$", "", clean)
    if clean and clean != bone.name and clean not in armature.data.bones:
        bone.name = clean


def skinned_to(obj):
    return any(m.type == "ARMATURE" and m.object == armature for m in obj.modifiers) or (obj.parent == armature and obj.parent_type == "BONE")


for obj in list(bpy.data.objects):
    if obj.type == "MESH" and not skinned_to(obj):
        bpy.data.objects.remove(obj, do_unlink=True)
    elif obj.type not in ("MESH", "ARMATURE"):
        if obj != armature and not any(c.type == "MESH" for c in obj.children_recursive):
            bpy.data.objects.remove(obj, do_unlink=True)

# Flatten the hierarchy so the armature is a root, then bake every transform into the data.
for obj in list(bpy.data.objects):
    if obj.type == "MESH" and obj.parent not in (None, armature):
        world = obj.matrix_world.copy()
        obj.parent = armature
        obj.matrix_world = world
if armature.parent is not None:
    world = armature.matrix_world.copy()
    armature.parent = None
    armature.matrix_world = world
for obj in list(bpy.data.objects):
    if obj.type == "EMPTY" and not obj.children:
        bpy.data.objects.remove(obj, do_unlink=True)

with override():
    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.data.objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

meshes = [o for o in bpy.data.objects if o.type == "MESH"]
bpy.context.view_layer.update()
points = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
low = Vector([min(p[i] for p in points) for i in range(3)])
high = Vector([max(p[i] for p in points) for i in range(3)])
scale = job["height"] / (high.z - low.z)
offset = Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, low.z))
armature.location = -offset * scale
armature.scale = (scale, scale, scale)
with override():
    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.data.objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

for substring, colour in job.get("tint", {}).items():
    for mat in bpy.data.materials:
        if substring.lower() in mat.name.lower() and mat.node_tree:
            bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf is None:
                continue
            base = bsdf.inputs["Base Color"]
            if base.is_linked:
                mix = mat.node_tree.nodes.new("ShaderNodeMix")
                mix.data_type = "RGBA"
                mix.blend_type = "MULTIPLY"
                mix.inputs["Factor"].default_value = 1.0
                mix.inputs["B"].default_value = (*colour, 1.0)
                mat.node_tree.links.new(base.links[0].from_socket, mix.inputs["A"])
                mat.node_tree.links.new(mix.outputs["Result"], base)
            else:
                base.default_value = (*colour, 1.0)

armature.data.vrm_addon_extension.spec_version = "1.0"
meta = armature.data.vrm_addon_extension.vrm1.meta
meta.vrm_name = job["name"]
if len(meta.authors) == 0:
    meta.authors.add()
meta.authors[0].value = job.get("author", "")
with override():
    bpy.context.view_layer.objects.active = armature
    bpy.ops.vrm.assign_vrm1_humanoid_human_bones_automatically(armature_object_name=armature.name)
    if job.get("bones"):
        human_bones = armature.data.vrm_addon_extension.vrm1.humanoid.human_bones
        for vrm_bone in dir(human_bones):
            prop = getattr(human_bones, vrm_bone, None)
            if hasattr(prop, "node") and vrm_bone not in job["bones"]:
                prop.node.bone_name = ""
        for vrm_bone, bone_name in job["bones"].items():
            assert bone_name in armature.data.bones, f"no bone {bone_name}"
            getattr(human_bones, vrm_bone).node.bone_name = bone_name
    bpy.ops.vrm.make_estimated_humanoid_t_pose(armature_object_name=armature.name)
    bpy.ops.vrm.assign_vrm1_expressions_automatically(armature_object_name=armature.name)


def collider_radius(bone_name):
    """Median distance from the bone to the vertices it moves most, pulled in so hair rests on the surface."""
    bone = armature.data.bones[bone_name]
    a, b = Vector(bone.head_local), Vector(bone.tail_local)
    distances = []
    for obj in meshes:
        group = obj.vertex_groups.get(bone_name)
        if group is None:
            continue
        for vertex in obj.data.vertices:
            strongest = max(vertex.groups, key=lambda g: g.weight, default=None)
            if strongest is not None and strongest.group == group.index:
                point = vertex.co
                t = max(0.0, min(1.0, (point - a).dot(b - a) / max((b - a).length_squared, 1e-9)))
                distances.append((point - (a + (b - a) * t)).length)
    distances.sort()
    return max(0.02, min(0.2, 0.85 * distances[len(distances) // 2])) if distances else 0.05


spring_report = []
springs = job.get("springs") or {}
if springs:
    spring_bone = armature.data.vrm_addon_extension.spring_bone1
    colliders = {}
    for name in sorted({bone for group in springs.values() for bone in group.get("colliders", [])}):
        bone = armature.data.bones[name]
        collider = spring_bone.add_collider(bpy.context, armature)
        collider.node.bone_name = name
        collider.shape_type = "Capsule"
        collider.shape.capsule.offset = (0.0, 0.0, 0.0)
        collider.shape.capsule.tail = (0.0, bone.length, 0.0)
        collider.shape.capsule.radius = collider_radius(name)
        # Adding to a collection invalidates Python handles to its earlier items, so keep the uuid.
        colliders[name] = collider.uuid
    for group_name, settings in springs.items():
        group_uuid = None
        if settings.get("colliders"):
            collider_group = spring_bone.add_collider_group()
            collider_group.vrm_name = group_name
            group_uuid = collider_group.uuid
            for name in settings["colliders"]:
                collider_group.add_collider().collider_uuid = colliders[name]
        for chain in settings["chains"]:
            bones = sorted(b.name for b in armature.data.bones if re.fullmatch(re.escape(chain) + r"_\d+", b.name))
            spring = spring_bone.add_spring()
            spring.vrm_name = chain
            for name in bones:
                joint = spring.add_joint()
                joint.node.bone_name = name
                joint.stiffness = settings.get("stiffness", 1.0)
                joint.gravity_power = settings.get("gravity", 0.0)
                joint.gravity_dir = (0.0, 0.0, -1.0)
                joint.drag_force = settings.get("drag", 0.5)
                joint.hit_radius = settings.get("radius", 0.02)
            if group_uuid is not None:
                spring.add_collider_group().collider_group_uuid = group_uuid
            spring_report.append({"spring": chain, "joints": len(bones)})

human = armature.data.vrm_addon_extension.vrm1.humanoid.human_bones
required =["hips", "spine", "head", "left_upper_arm", "right_upper_arm", "left_upper_leg", "right_upper_leg", "left_lower_leg", "right_lower_leg", "left_foot", "right_foot"]
missing = [b for b in required if not getattr(human, b).node.bone_name]
result = {"assigned": sum(1 for name in dir(human) if hasattr(getattr(human, name), "node") and getattr(human, name).node.bone_name), "height": round(high.z - low.z, 3), "scale": round(scale, 4), "missing": missing, "meshes": len(meshes),
          "tris": sum(len(o.data.polygons) for o in meshes), "springs": spring_report}
if not missing:
    with override():
        bpy.ops.export_scene.vrm(filepath=job["target"], armature_object_name=armature.name, ignore_warning=True)
print("RESULT", json.dumps(result))
