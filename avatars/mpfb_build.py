"""Builds dressed MakeHuman characters in the NPCs scene and exports each as a GLB for convert.py.

Before exec, set RECIPE to a bodies recipe (see bodies.mjs), OUT to the output folder, and optionally ONLY to a list of keys.
Every body with a "makehuman" spec is built: {"macro": {...}, "skin", "hair", "clothes": [...], "brows", "lashes",
"cover": [material substrings whose garment hides the skin under it]}. Each is exported as OUT/mpfb-<key>.glb.
"""
import json
import importlib
import os

import bpy

mpfb = "bl_ext.blender_org.mpfb.services."
HumanService = importlib.import_module(mpfb + "humanservice").HumanService
AssetService = importlib.import_module(mpfb + "assetservice").AssetService
SPECS = [{"key": body["key"], **body["makehuman"]} for body in json.load(open(RECIPE))["bodies"]
         if "makehuman" in body and (not globals().get("ONLY") or body["key"] in ONLY)]


def asset(subdir, name, extension="mhclo"):
    """The asset's file in whichever MPFB data root holds it: the bundled data or the user's installed packs."""
    path = AssetService.find_asset_absolute_path(f"{name}/{name}.{extension}", subdir)
    if path is None:
        raise FileNotFoundError(f"MPFB has no {subdir} asset called {name}")
    return path


def clear_scene(scene):
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)


def bake(obj):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    if obj.data.shape_keys:
        bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
    for modifier in list(obj.modifiers):
        if modifier.type == "ARMATURE":
            continue
        try:
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        except RuntimeError:
            obj.modifiers.remove(modifier)
    obj.select_set(False)


def hide_under(body, garments, reach=0.06):
    """Deletes body vertices that a garment covers within `reach` along their normal, for garments that ship without a delete group."""
    import bmesh
    from mathutils.bvhtree import BVHTree
    trees = []
    for garment in garments:
        world = garment.matrix_world
        trees.append(BVHTree.FromPolygons([world @ v.co for v in garment.data.vertices], [tuple(p.vertices) for p in garment.data.polygons]))
    world, turn = body.matrix_world, body.matrix_world.to_3x3()
    covered = set()
    for v in body.data.vertices:
        point, normal = world @ v.co, (turn @ v.normal).normalized()
        # The inward cast catches skin that already pokes a little through the garment.
        if any(tree.ray_cast(point + normal * 0.001, normal, reach)[0] is not None or tree.ray_cast(point, -normal, 0.03)[0] is not None for tree in trees):
            covered.add(v.index)
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.verts[i] for i in covered], context="VERTS")
    bm.to_mesh(body.data)
    bm.free()
    print("hid", len(covered), "body vertices under", [g.name for g in garments])


scene = bpy.data.scenes["NPCs"]
bpy.context.window.scene = scene
results = []
for spec in SPECS:
    clear_scene(scene)
    macro = {"gender": 0.5, "age": 0.5, "muscle": 0.5, "weight": 0.5, "proportions": 0.5, "height": 0.5, "cupsize": 0.5, "firmness": 0.5,
             "race": {"asian": 0.33, "caucasian": 0.33, "african": 0.33}}
    macro.update({k: v for k, v in spec["macro"].items() if k != "race"})
    macro["race"].update(spec["macro"].get("race", {}))
    basemesh = HumanService.create_human(macro_detail_dict=macro)
    HumanService.add_builtin_rig(basemesh, "game_engine")
    HumanService.set_character_skin(asset("skins", spec["skin"], "mhmat"), basemesh, skin_type="GAMEENGINE", material_instances=False)
    parts = [("eyes", "low-poly", "Eyes"), ("eyebrows", spec.get("brows", "eyebrow001"), "Eyebrows"), ("eyelashes", spec.get("lashes", "eyelashes01"), "Eyelashes")]
    if spec.get("hair"):
        parts.append(("hair", spec["hair"], "Hair"))
    for subdir, name, kind in parts:
        HumanService.add_mhclo_asset(asset(subdir, name), basemesh, asset_type=kind, subdiv_levels=0, material_type="GAMEENGINE")
    for name in spec["clothes"]:
        HumanService.add_mhclo_asset(asset("clothes", name), basemesh, asset_type="Clothes", subdiv_levels=0, material_type="GAMEENGINE")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in list(scene.objects):
        if obj.type == "MESH":
            bake(obj)
    if spec.get("cover"):
        hide_under(basemesh, [o for o in scene.objects if o.type == "MESH" and o is not basemesh
                              and any(name in s.material.name for s in o.material_slots if s.material for name in spec["cover"])])
    bpy.ops.object.select_all(action="DESELECT")
    for obj in scene.objects:
        obj.select_set(True)
    target = os.path.join(OUT, f"mpfb-{spec['key']}.glb")
    bpy.ops.export_scene.gltf(filepath=target, export_format="GLB", use_selection=True, use_active_scene=True, export_apply=False,
                              export_animations=False, export_cameras=False, export_lights=False)
    results.append((spec["key"], len(scene.objects), os.path.getsize(target) // 1024))
clear_scene(scene)
print(results)
