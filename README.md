# vera-world-kit

Generic Blender and Node pipeline that builds VERA region GLBs and resident avatars from content kept outside the repo.

Each tool reads its input from a content folder you point it at: a region folder, or an avatar recipe.

## Requirements

- Blender 5.2, with the MPFB extension (MakeHuman) and the VRM add-on
- Node (tested on 26)
- `basisu` on the PATH, for KTX2 texture compression
- A checkout of the VERA app with `npm install` done, named by `VERA_APP`: the nav tools run its own collision, navigation and layout code, and the Node tools load `three` and `@pixiv/three-vrm` from its `node_modules`

## Layout

```
blender/   region builder: geometry helpers, pixel-font signs, painted lighting, chunked export, pipeline runner
nav/       layout parse and navigation check on a region GLB, plus debugging probes
avatars/   MakeHuman build, GLB to VRM conversion, tinting, KTX2 compression, contact sheets, recipe runner
tools/     GLB fingerprinting for comparing builds
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
| `inside_rects()` | `(x0, y0, x1, y1, top)` boxes lit as indoors |
| `enterable()` | `{building: (x0, y0, x1, y1, roof)}` for interior chunks |

Optional: `SUN`, `SUN_COLOR`, `SKY_COLOR`, `INSIDE_COLOR`, `SKY_BANDS`, `CELL`, `STREET_DRAW_DISTANCE`, `INTERIOR_DRAW_DISTANCE`, `LOW_DETAIL_MIN_SIZE`.

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
2. All bodies: `node avatars/bodies.mjs <recipe.json> [key ...]` converts or copies each body to `body-<key>.vrm`, tints it, and writes a KTX2-compressed copy to the `ktx` folder. Bodies marked `"unused"` are skipped unless named. Set `BLENDER` when Blender isn't at the macOS default path.

`tint.mjs` also works on its own: `node avatars/tint.mjs list a.vrm` lists material names, and `node avatars/tint.mjs in.vrm out.vrm '<json>'` applies `name`, `tints` and `alpha` rules.

## Comparing builds

```bash
node tools/glb-fingerprint.mjs a.glb --hashes > a.txt
node tools/glb-fingerprint.mjs b.glb --hashes > b.txt
diff a.txt b.txt
```
