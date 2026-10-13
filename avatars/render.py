"""Renders VRM files front-on into one contact sheet. usage: blender -b --python render.py -- out.png a.vrm b.vrm ..."""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
sheet_path, files = args[0], args[1:]
W, H = 300, 420

scene = bpy.context.scene
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "TEXTURE"
scene.render.resolution_x, scene.render.resolution_y = W, H
camera = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
scene.collection.objects.link(camera)
scene.camera = camera
tiles = []
for index, path in enumerate(files):
    before = set(bpy.data.objects)
    try:
        bpy.ops.import_scene.gltf(filepath=path)
    except Exception as error:
        print("IMPORT FAILED", path, error)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    bpy.context.view_layer.update()
    if meshes:
        points = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
        low = Vector([min(p[i] for p in points) for i in range(3)])
        high = Vector([max(p[i] for p in points) for i in range(3)])
        height = high.z - low.z
        camera.location = ((low.x + high.x) / 2, low.y - height * 1.9, low.z + height * 0.5)
        camera.rotation_euler = (math.radians(90), 0, 0)
        target = os.path.join(os.path.dirname(sheet_path), f"_tile{index}.png")
        scene.render.filepath = target
        bpy.ops.render.render(write_still=True)
        image = bpy.data.images.load(target)
        tiles.append(np.array(image.pixels[:], dtype=np.float32).reshape(H, W, 4))
        bpy.data.images.remove(image)
        os.remove(target)
    else:
        tiles.append(np.zeros((H, W, 4), dtype=np.float32))
    for obj in new:
        bpy.data.objects.remove(obj, do_unlink=True)

cols = min(6, len(tiles))
rows = (len(tiles) + cols - 1) // cols
sheet = np.ones((rows * H, cols * W, 4), dtype=np.float32)
for index, tile in enumerate(tiles):
    r, c = divmod(index, cols)
    y0 = (rows - 1 - r) * H
    sheet[y0:y0 + H, c * W:(c + 1) * W] = tile
image = bpy.data.images.new("sheet", cols * W, rows * H)
image.pixels.foreach_set(sheet.ravel())
image.filepath_raw = sheet_path
image.file_format = "PNG"
image.save()
print("SHEET", sheet_path, len(tiles))
