# vera-world-kit

Generic Blender and Node pipeline that builds VERA region GLBs and resident avatars from content kept outside the repo.

Each tool reads its input from a content folder you point it at: a region folder, or an avatar recipe.

## Requirements

- Blender 5.2, with the MPFB extension (MakeHuman) and the VRM add-on
- Node (tested on 26), with `npm install` run in this repo
- `basisu` on the PATH, for KTX2 texture compression
- A checkout of the VERA app with `npm install` done, named by `VERA_APP`: the nav tools run its own collision, navigation and layout code, and the Node tools load `three` and `@pixiv/three-vrm` from its `node_modules`

## Layout

```
blender/   region builder: geometry helpers, pixel-font signs, painted lighting, chunked export, pipeline runner
nav/       layout parse and navigation check on a region GLB, plus debugging probes
avatars/   MakeHuman build, fused-mesh rigging with spring bones, GLB to VRM conversion, scaling, tinting, KTX2 compression, low-detail bodies, contact sheets, recipe runner
tools/     GLB fingerprinting for comparing builds, swapping a rebuilt GLB into an app region
```

## Regions

A region is a folder in the content folder with a `region.py` config module and the region's own build scripts. The build scripts import `lib`, `kit` and `signs` from `blender/`.

`region.py` provides:

| Name | Meaning |
|---|---|
| `OUT` | Path of the GLB to write |
| `TEXTURES` | Folder for generated textures and sign images |
| `BUILD` | The region's scripts, run in order |
| `DEFAULT_COLLECTION` | Collection geometry goes into when none is named |
| `LIT_COLLECTIONS` | Collections the lighting paints |
| `EXPORT_COLLECTIONS` | Collections the export includes |
| `INTERIOR_COLLECTION` | Collection whose contents split into per-building chunks |
| `STOREY` | Floor-to-floor height, for indoor light |
| `SKY_BOX` | `(x0, y0, x1, y1, top)` of the sky walls |
| `BRICK_COLOURS` | Wall colours that get the brick texture |
| `TEXTURE_RULES` | `(material name substring, texture kind or None)` pairs |
| `EMISSIVE` | Material name substrings that stay unlit |
| `BACKDROP_CARDS` | Name prefixes of flat cards that neither subdivide nor cast shadows |
| `BACKDROP_NAMES` | Name prefixes exported as the always-drawn backdrop |
| `LANDMARKS` | Name prefixes kept with the street even inside a building |
| `inside_rects()` | `(x0, y0, x1, y1, top)` boxes lit as indoors, the first match winning; an optional sixth item sets that room's light colour |
| `enterable()` | `{building: (x0, y0, x1, y1, roof)}` for interior chunks |

Optional: `SUN`, `SUN_COLOR`, `SKY_COLOR`, `INSIDE_COLOR`, `SKY_BANDS`, `CELL`, `STREET_DRAW_DISTANCE`, `INTERIOR_DRAW_DISTANCE`, `LOW_DETAIL_MIN_SIZE`.

Printed artwork (logos, menus, screens, posters, patterns) is painted on a `signs.Canvas` in texels and shown with `signs.printed_material` on a `lib.picture`, which can face any way and be round. The look keeps a printed image's UVs and colours, and the export packs it into the sign atlas. The pixel font prints capitals unless `keep_case=True` is passed, which keeps lowercase and accented letters. A material made with `alpha` below 1 exports as unlit and alpha-blended, for glass. `lib.octahedron` makes hanging decor (lanterns, lamps) whose faces are too steep for the navigation grid to stand on.

Build, light and export in the open Blender file:

```python
KIT = "/path/to/vera-world-kit/blender"
REGION = "/path/to/content/regions/<region>"
exec(open(KIT + "/pipeline.py").read(), {"KIT": KIT, "REGION": REGION})
```

Pass `"STEPS": ("export",)` to run only some of `build`, `look` and `export`. The run is logged to `<region>/pipeline.log`.

Check the result:

```bash
VERA_APP=/path/to/app nav/region-check.sh /path/to/region.glb
```

It writes `layout.json` and floor maps next to the GLB, and reports zones, spots, long routes and blockers.

Put a rebuilt GLB into a region that already exists in the app:

```bash
VERA_APP=/path/to/app tools/region-swap.sh <region id> /path/to/region.glb [backup folder]
```

It does what the app's region update does (parse the layout, store the file beside the region's current GLB, update the region, drop passage links whose passage is gone), refuses when the layout parser warns, and copies the previous GLB into the backup folder (default: the GLB's folder) before deleting it.

## Avatars

A recipe JSON lists the bodies to build. Paths are relative to the recipe.

```json
{
  "author": "VRM author field",
  "bones": "mpfb",
  "ktx": "ktx-folder",
  "bodies": [
    {"key": "a", "name": "A", "height": 1.7, "makehuman": {"macro": {}, "skin": "", "hair": "", "clothes": []}, "tint": {}},
    {"key": "b", "source": "sources/b.vrm", "tint": {"name": "B", "tints": [["material regex", [1, 1, 1]]]}}
  ]
}
```

1. MakeHuman bodies: in Blender, run `avatars/mpfb_build.py` with `RECIPE` and `OUT` set, and optionally `ONLY`. It writes `mpfb-<key>.glb`.
2. All bodies: `node avatars/bodies.mjs <recipe.json> [key ...]` converts or copies each body to `body-<key>.vrm` (a source body with `"height"` is scaled to that height, measured over the whole mesh including hair), tints it, and writes a KTX2-compressed copy to the `ktx` folder. Bodies marked `"unused"` are skipped unless named. Set `BLENDER` when Blender isn't at the macOS default path.

### Fused meshes

A body generated as one textured shell with no skeleton (image-to-3D output) is rigged by `avatars/rig.py` from a `"rig"` entry:

```json
{"key": "c", "name": "C", "height": 1.65,
 "rig": {"source": "sources/c.glb", "triangles": 60000, "joints": {}, "chains": [
   {"name": "hair_l", "parent": "head", "bones": 5, "falloff": 0.03, "colour": [[0.15, 0.28, 0.42], 0.2], "region": {"box": [[0.0, -0.05, 0.84], [0.3, 0.35, 1.47]]}},
   {"name": "strap", "parent": "pelvis", "falloff": 0.015, "region": {"box": [[-0.13, -0.26, 0.72], [-0.05, -0.18, 0.95]]}, "points": [[-0.09, -0.19, 0.95], [-0.08, -0.23, 0.72]]}]},
 "springs": {"hair": {"chains": ["hair_l"], "stiffness": 0.9, "gravity": 0.3, "drag": 0.4, "radius": 0.03, "colliders": ["head", "spine_03", "upperarm_l"]}}}
```

The source must stand in a T- or A-pose facing -Y. `rig.py` scales it to `height`, reduces it toward `triangles` while keeping edges short enough to bend, places the joints from the mesh (`joints` overrides any of them, in metres) and weights the body. Each chain adds bones through `points`, or along its region when `points` is left out, and takes over the region's vertices: `region` is a box, sphere or capsule softened over `falloff` metres, and `colour` keeps vertices whose texture colour is within the given distance, which separates hair from the clothes it is fused to. `bodies.mjs` writes `rigged-<key>.glb`, then `convert.py` adds one VRM spring per chain and a capsule collider on each bone in a spring group's `colliders`. `node avatars/vrmcheck.mjs` reports the spring joints and colliders the app loads.

### Low-detail bodies

```bash
npm install
node avatars/lod.mjs in.vrm out.vrm [--triangles 12000] [--error 0.005] [--max 256]
```

Makes the body the app shows beyond 18 m. Each mesh is simplified toward the triangle budget until it would drift more than `--error` (a fraction of the mesh's size) from its shape. Morph targets and the expression binds that use them are removed, and textures are shrunk to `--max` px as KTX2. The skeleton, skinning, humanoid mapping, materials and metadata are kept, so the same poses and animations play on it. Input textures may be PNG, JPEG or KTX2.

`tint.mjs` also works on its own: `node avatars/tint.mjs list a.vrm` lists material names, and `node avatars/tint.mjs in.vrm out.vrm '<json>'` applies `name`, `tints` and `alpha` rules.

## Comparing builds

```bash
node tools/glb-fingerprint.mjs a.glb --hashes > a.txt
node tools/glb-fingerprint.mjs b.glb --hashes > b.txt
diff a.txt b.txt
```
