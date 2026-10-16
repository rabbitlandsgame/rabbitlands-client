# Producing a Nymara region map

Instructions for an agent taking one of the remaining ten regions from its
placeholder package to a production one, the way `amberwood/` was done.

Read this whole file before touching anything. Most of it is not "how to model";
it is the set of things that will silently waste your time if you discover them
in hour six instead of hour one.

---

## 1. What already exists — reuse it

`amberwood/source/` is a complete, region-agnostic authoring toolkit. It is pure
Python (numpy + Pillow) plus one small C rasteriser used only for offline
previews. **Do not write a second one.** Copy or import it.

| Module | What it gives you |
| --- | --- |
| `amberwood/noise.py` | seeded value/fBm/ridged/Worley noise, tileable variants |
| `amberwood/mesh.py` | mesh container, transforms, welding, angle-weighted normals, tangents, and primitives (box, tapered cylinder, swept tube, lathe, extrude, loft, heightfield, icosphere, stairs, arch, gable roof) |
| `amberwood/textures.py` | ~25 procedural PBR material recipes |
| `amberwood/materials.py` | the single material table shared by the GLB export and the preview renderer |
| `amberwood/gltf.py` | spec-correct glTF 2.0 / GLB writer, embedded buffers and images |
| `amberwood/terrain.py` | heightfield sculpting operators, per-cell surface classes, crack-free multi-material export, water planes, distant backdrop |
| `amberwood/trees.py` | grown-skeleton tree generator with species profiles and three detail tiers |
| `amberwood/architecture.py`, `stonework.py`, `treecraft.py`, `props.py` | the building, masonry, tree-integrated and prop kits |
| `amberwood/render.py` + `native/` | offline preview renderer |
| `validate_gltf.py` | standalone glTF 2.0 validator |
| `verify_runtime.py` | reproduces the client's grounding contract offline |
| `capture_views.py`, `make_comparison.py`, `compress_captures.py` | comparison captures and sheets |
| `export_server_collision.py` | writes the server-side walk grid from the built terrain |

**Region-specific**, i.e. what you actually write: `region.py` (extents, anchors,
routes, watercourses, terrain sculpting) and `populate.py` (placement passes).
Those two files are the map. Everything else should need at most a new texture
recipe or a new kit piece.

### Where the toolkit lives

The shared toolkit belongs at `maps/nymara-regions/_toolkit/`, imported by every
region's `source/`. Ten divergent copies of it is a worse problem than the
refactor that avoids them.

**If `_toolkit/` does not exist yet, creating it is your first task**, as its own
commit, before any region work:

1. `git mv amberwood/source/amberwood _toolkit/amberwood`, and move
   `native/`, `validate_gltf.py`, `verify_runtime.py`, `capture_views.py`,
   `make_comparison.py`, `compress_captures.py`, `export_server_collision.py` and
   `preview.py` with it.
2. Leave `build_amberwood.py` in `amberwood/source/` — it is the region's build,
   not toolkit — and point it at the new location.
3. **Rebuild Amberwood and diff the result.** The build is deterministic, so a
   correct refactor produces a byte-identical `world.glb`. If it does not, you
   have changed behaviour, not just location. Re-run `validate_gltf.py` and
   `verify_runtime.py` and confirm both still report zero errors and zero
   grounding misses.
4. Commit that on its own, then start your region.

If `_toolkit/` already exists, import from it and change nothing there unless
your region genuinely needs a new capability — in which case add to it rather
than forking it, and say so in your report.

---

## 2. Environment reality check — do this first, in ten minutes

Every one of these bit me. Check them before planning anything.

```sh
# 1. Can you push? If not, everything ends as a git bundle.
git push --dry-run origin HEAD

# 2. Is the server repo reachable?
git clone https://github.com/rabbitlandsgame/rabbitlands-server.git /tmp/srv

# 3. Is there a Godot 4 binary? apt only carries godot3.
which godot godot4; apt-cache search godot

# 4. Can you install anything at all?
sudo apt-get install -y -qq cowsay   # often 403s at the proxy
pip download --no-deps -d /tmp/x numpy

# 5. Is there a GPU?
ls /dev/dri
```

In my session: no push (git proxy refused the repo), no server, no Godot 4, no
apt or pip downloads, no GPU. `gcc` **was** available, which is why the preview
renderer is C. Plan for the same and be pleasantly surprised.

If you cannot push, say so to the user **immediately** and agree a delivery
route before building. A git bundle over ~30 MiB has to be split for upload.

---

## 3. Known defects in every region package

These are not yours to be surprised by; they are the starting condition. Verify
each for your region, then fix or document it.

1. **The terrain is flat.** Every `world.glb` has a single `Terrain_ELM_Authority`
   mesh with y = 0.0 everywhere, and `production-index.json` records
   `terrainHeightRange: [0.0, 0.0]`.
2. **Landmarks belong to other regions.** Crownwater's list contains "Grey Moor
   Ritual Shrine", "Sunmane Caravan Camp", "Amberwood Hollow Tree"; Whitehorn's
   contains "Westhaven Seawall". Between 9 and 15 of each package's ~20 meshes
   are foreign. Do not preserve any of it.
3. **The concept detail boards are truncated PNGs.** Every
   `<region>/references/00-concept-detail-board.png` is cut to exactly 786,444
   bytes; only the top row of five panels decodes. Check with:
   ```sh
   python3 - <<'PY'
   import struct, zlib, sys
   d = open(sys.argv[1] if len(sys.argv)>1 else '00-concept-detail-board.png','rb').read()
   i, idat = 8, b''
   while i < len(d):
       n = struct.unpack('>I', d[i:i+4])[0]; t = d[i+4:i+8]
       if t == b'IDAT': idat += d[i+8:i+8+n]
       i += 12 + n
   try: zlib.decompress(idat); print('OK')
   except Exception as e: print('TRUNCATED', e)
   PY
   ```
   **Ask the user to re-supply the board before you start.** The aerial concepts
   in `eloria-assets/concepts/nymara-regions/<region>_region_concept.png` are
   intact and are your composition authority; the board is your player-scale
   authority and you cannot do panel-level work without it.
4. **The region ships no authored walk grid** beyond what its own
   `collision.bin` carries. The server resamples that; only a map composing
   several interiors needs one written for it, by
   `<region>/source/export_insides_collision.py`.
5. **`eloria-assets/qa/regions/<region>/README.md`** describes the *intended*
   layout in prose. It is a useful starting brief, but it describes the
   placeholder generator's plan, not the concept art. The painting wins.

---

## 4. The runtime contract you must satisfy

Read these files, do not assume:

- `godot-client/src/world/world_loader.gd` — how collision and navigation are
  built from the manifest
- `godot-client/src/world/coordinate_adapter.gd` — server tile ↔ Godot metres
- `godot-client/src/app/main.gd`, `_place_actor_on_surface` — actor grounding
- `godot-client/schemas/world-manifest-1.schema.json` — the manifest schema
- `maps/nymara-regions/server-collision/README.md` — the walk grid format,
  and any region's `world.json` for the package layout
- `eloria-assets/maps/four-gates-city/` — the repository's own best-practice
  exemplar: validator report, performance summary, coverage map, change log

The three rules that matter most:

1. **Grounding is a downward ray on one layer.** The client turns every
   `MeshInstance3D` whose name starts with a `navigation.surfaceNodePrefixes`
   entry into collision on `NAVIGATION_SURFACE_LAYER`, then casts a ray from
   y = 400 to y = -100 and places the actor at the first hit. A miss falls back
   to `coordinateTransform.walkingHeight` — that is the bug that drops or floats
   a character.
2. **Only walkable decks get the navigation prefix.** If you mark a whole
   landmark as a walk surface, the ray snaps actors onto its roof. Amberwood
   splits walkable decks into separate sub-meshes named `Walk_*`
   (`stonework.MeshGroup.add_walk`). Structural geometry is never a walk surface.
3. **The server grid is 2-D.** An overhead deck owns its cell: bridges, canopy
   platforms and docks take the footprint in `collision.bin` at deck height, and
   the ground beneath them is not separately walkable. Decide this deliberately.

---

## 5. Workflow

1. **Recon.** Read the loader, the schema, the Four Gates exemplar, the region's
   aerial concept and its detail board (once you have an intact one), and the
   QA README. Record the current package's defects.
2. **Establish scale and coordinates before modelling.** Read the region's entry
   in `godot-client/data/maps/registry.json` — `coordinateTransform` is what
   puts the server's tiles on your geometry — and the `collision` block of the
   package's `world.json`. The client builds the active map's
   `CoordinateAdapter` from that registry entry (`godot-client/src/app/main.gd`,
   `_load_server_map`), while the world loader, a resident neighbour's actors
   and clicks past a seam read the package's own `coordinateTransform`
   (`WorldManifest.coordinate_adapter()`), so change both and compare them.
   Anything addressed by a server tile goes at `CoordinateAdapter.tile_center()`
   (`godot-client/src/world/coordinate_adapter.gd`); bare `server_to_godot` on
   a tile's integers is its corner. Decide the extent with the user —
   Amberwood went to 576 m on a 96x96-tile server map at one metre per tile,
   which required a server-side change they agreed to.
3. **Terrain first, and prove grounding on it** before any detail work. Build
   the heightfield, export it, run `verify_runtime.py`, and only proceed at zero
   grounding misses.
4. **Then largest to smallest**: coast and water → forest/biome massing and
   world boundaries → primary landmarks → roads and satellite locations →
   secondary architecture → ground vegetation → props → lighting, minimap,
   metadata.
5. **Preview constantly.** `capture_views.py` renders player-eye views. Look at
   them. A map you have not looked at from 1.7 m is not finished.
6. **Validate every export**: `validate_gltf.py` then `verify_runtime.py`. Both
   must report zero errors.
7. **Comparison sheets** with `make_comparison.py`, then iterate.
8. **Commit, bundle, report.**

Write the composition in a fixed **design space** and scale it, as
`region.SCALE` does. Then changing the region's extent is one constant, not a
rewrite.

---

## 6. Traps that cost me hours

- **Scaling clearings with the map.** Distances between places should scale;
  the places themselves must not. A courtyard is sized by the buildings in it.
  Tripling the map tripled every clearing and ate the forest. `region.LOCAL`
  exists for this.
- **`_smoothstep` with reversed edges.** `max(edge1 - edge0, 1e-9)` on a
  descending ramp gives a divisor of 1e-9, so the "rim" mask evaluates to 1
  everywhere and the whole terrain lifts by the wall height. Symptom: your
  spawn is 26 m higher than you expect.
- **Collision row order.** Rows are indexed by server tile Y, which runs north
  to south, so row 0 is the +Z edge. Writing them the other way silently
  mirrors every walkability decision. `verify_runtime.py`'s cell-to-surface
  cross-check catches it; nothing else will.
- **Zero-length vertex normals.** Cards whose centre vertex coincides with the
  cluster centre produce a (0,0,0) normal. glTF forbids it and Godot shades it
  black. `mesh.sanitise_normals()` guards it; the validator catches it.
- **Arch orientation.** `mesh.arch` builds in XY and extrudes along Z. Rotating
  it 90° for a bridge makes you look at the barrel end. Build bridge elevations
  as solid wall slices whose underside follows the intrados instead of floating
  arch rings — see `stonework.high_bridge`.
- **Stairs that climb into their own podium.** `mesh.stairs` climbs toward +Z
  from y = 0. Compute the run length and place the foot outside the mass.
- **Cameras inside geometry.** Preview cameras given absolute Y end up
  underground the moment the terrain changes. Make them ground-relative, and
  use the depth probe in `capture_views._free_camera` to require both open
  framing and line of sight to the subject.
- **Texture bytes dominate the GLB.** ORM maps at 256 and no normal map on
  alpha-cut foliage cut ~25% off the package with no visible difference. See
  `TextureSet.compact` and `.reduced`.
- **`sudo apt-get install -s` succeeds while the real install 403s.** The
  simulation reads cached metadata. Never conclude a tool is available from
  `-s`.
- **`pkill -f <script>` can match and kill the shell running your pipeline.**
  Use `pgrep` first, and a pattern specific enough to miss your own wrapper.

---

## 7. Budgets

The repository's stated desktop guideline is **1.5 M visible triangles and
512 MiB of texture**, from `four-gates-city/performance-summary.md`. Four Gates
itself is 4,538 unique triangles across 1,750 nodes at 3.0 MB.

Amberwood at 576 m x 576 m came out at 535,709 unique / 3,123,378 instanced
triangles, 10,069 nodes, 28.7 MB, with a reduced `world-lod2.glb` at 2.20 M and
19.0 MB. That is ~9.4 triangles per square metre and about 2.1x the guideline.

Pin the material set a region embeds, and pin it to what the region actually
references rather than to the whole shared table. Amberwood shipped 2.79 MB of
textures no mesh pointed at for exactly that reason, and nothing said so until
`export_glb` was taught to warn about it.

Mirrorhold, the same extent, came out at 300,734 unique / 1,246,632 instanced
triangles, 2,308 nodes, 16.1 MB - ~3.8 triangles per square metre, inside the
guideline. It is a stone region with a sparse alpine tree belt rather than a
forest, so the two bracket the range a 576 m region can sit in.
Nothing streams or switches LODs yet.

Use that as calibration, not as licence. Pick a triangles-per-square-metre
target up front, measure against it every build, and record the real number.
The cheapest levers, in order: per-instance detail tier, ground-dressing
subdivision counts, tree spacing, then unique-kit variant count.

---

## 8. Definition of done

- `world.glb` loads through the real loader path, self-contained, no glTF
  extensions, no external files.
- `validate_gltf.py`: **0 errors, 0 warnings**.
- `verify_runtime.py`: **0 errors**, and **0 grounding misses** across every
  reachable server tile. Warnings only for cliffs, deliberate overhead decks,
  and documented cases.
- `world.json` complete against the schema: bounds, coordinate transform,
  spawns, collision, navigation, landmarks, interactives, NPC and creature
  markers, harvestables, portals, roads, water, environment, minimap
  transform, provenance.
- `collision.bin` dimensions are positive multiples of six and its encoded
  heights agree with the rendered walk surface.
- Minimap rendered from the final geometry, not drawn by hand.
- Comparison sheets against the aerial and all ten panels.
- `source/` committed and reproducible; runtime startup never depends on
  rerunning it.
- Docs beside the package: `README.md`, `modeling-assumptions.md`,
  `validation-report.md`, `coverage-map.md`, `comparison-report.md`,
  `change-log.md`, `performance-summary.md`.

**Report honestly.** State what you could not verify. In my session that was:
in-client rendering, end-to-end login, and every place name — the authoritative
written region descriptions were never available, so Amberwood's names are all
placeholders. Say so plainly rather than letting a clean validator report imply
more than it covers. Every capture in `references/captures/` is from the offline
renderer, not from Godot; label them that way.

---

## 9. The remaining regions

All ten are at `terrain-landmark-material-pass` with the defects in section 3.
Their composition authority is
`eloria-assets/concepts/nymara-regions/<region>_region_concept.png`.

| region | map id |
| --- | --- |
| `mirrorhold` | `mirrorhold` |
| `crownwater` | `crownwater` |
| `whitehorn_range` | `whitehorn_range` |
| `amethyst_barrens` | `amethyst_barrens` |
| `sunmane_steppe` | `sunmane_steppe` |
| `grey_moors` | `grey_moors` |
| `westhaven` | `westhaven` |
| `verdant_stair` | `verdant_stair` |
| `ssarathi_ruins` | `ssarathi_ruins` |
| `manymouth_delta` | `manymouth_delta` |

Do not take the biome from the region's name or from my guesses — open the
painting. Several will need kit Amberwood does not have (open steppe grass,
crystal, marsh, snow, masonry-heavy city), which means new recipes in
`textures.py` and new pieces in the kits, not new toolkits.

**Take one region at a time and finish it.** Amberwood took a full session for
one region; a half-finished second region is worth less than one finished one.

---

## 10. Coordination

- Branch per region: `feature/<region>-production-glb-map`. Check
  `git branch -r` first — `feature/amberwood-production-glb-map` is already
  taken by unrelated interiors work, which is exactly the collision to avoid.
- Two files are shared by every region and will conflict:
  `godot-client/data/maps/registry.json` and
  `maps/nymara-regions/production-index.json`. Touch only your region's entry,
  and expect to resolve by keeping both sides.
- Set `status` to `production-geometry-materials-population` and, if the region
  needs a bigger server map, record it under `requiresServerMap` as Amberwood
  does.
- The server owns gameplay. NPCs, creatures, harvestables and portals are
  editor/visual metadata carrying `"authority": "server"`. Nothing dynamic is
  baked into the static mesh.
