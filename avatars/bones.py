import bpy, sys, re
path = sys.argv[sys.argv.index("--") + 1]
bpy.ops.import_scene.gltf(filepath=path)
arm = max((o for o in bpy.data.objects if o.type == "ARMATURE"), key=lambda o: len(o.data.bones))
def walk(b, d):
    name = re.sub(r"_\d+$", "", re.sub(r"^(GLTF_created_\d+_|mixamorig\d*:|[A-Za-z0-9]+:)", "", b.name))
    if d < 9 and not re.search(r"(?i)finger|thumb|index|middle|ring|pinky|hair|eye|jaw|tongue|teeth|lip|brow|cheek|nose|ear|cloth|skirt|breast|bust", name):
        print("  " * d + name)
    for c in b.children: walk(c, d + 1)
for root in [b for b in arm.data.bones if b.parent is None]: walk(root, 0)
