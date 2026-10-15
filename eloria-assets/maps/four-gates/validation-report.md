# Four Gates 1.0.0 — validation report

All evidence below was produced in this environment against the committed
package. Nothing is extrapolated from an earlier version.

## 1. glTF 2.0 conformance

Tool: **Khronos glTF-Validator 2.0.0-dev.3.10** (official binary release).

```
world.glb
Errors: 0, Warnings: 0, Infos: 12, Hints: 0
```

The twelve informational messages are all `NODE_EMPTY`, reported for the
deliberate locator nodes (`Spawn_*`, `POI_*`, `Marker_*`, `FX_Waterfall_Mist_*`)
that the manifest references by name and that carry no mesh by design.

The file uses **core glTF 2.0 only** — no extensions are declared or required,
so it loads in any conformant runtime. All textures are embedded PNG buffer
views; the GLB depends on no external file and no absolute path.

## 2. Independent viewer

Beyond Godot, the GLB was loaded and rendered in **three.js r169** running in
headless Chromium (SwiftShader), driven over the DevTools protocol. This is a
completely separate glTF implementation from Godot's `GLTFDocument`; it was used
throughout development and caught real defects that a single implementation
would have masked.

Defects found this way and fixed:

| Defect | Symptom |
|---|---|
| Index accessors declared `count` in triangles, not elements | only one triangle in three would be drawn by any conformant loader |
| Flat-shaded normals computed against stale indices | null normals on hard-surface geometry |
| Ground/ring/strip/polar surfaces wound clockwise | every terrain and road surface faced downward |
| Bridge arches sprang above the deck | the arch rings occluded the whole crossing |
| Bridge deck slab coincident with its fascia | z-fighting bands across the causeway |
| Waterfall sheets interpolated through the cliff | falls were invisible from every angle |
| Almost every primitive wound clockwise (1.0.1) | walls rendered inside-out; near faces culled, interiors visible through them |

## 3. Godot import and runtime

Engine: **Godot 4.7.2-stable** (the version the project pins), OpenGL
compatibility renderer on llvmpipe (software GL, no GPU).

- `rendered_four_gates_map.gd` — PASS (existing project test, updated to apply
  the manifest environment).
- `rendered_four_gates_views.gd` — PASS, 22 comparison views captured.
- `rendered_four_gates_minimap.gd` — PASS, minimap rendered orthographically
  from the shipped GLB.
- `WorldManifest` validation warnings: **none**.

## 4. End-to-end gameplay

`rendered_four_gates_gameplay.gd` drives the production `main.tscn` through the
real login flow against a local protocol server, creating a temporary character
(`QA_FourGates_Temp1`). Result: **28 checks, 0 failures.**

Re-run after the 1.0.1 winding correction: still 28 checks, 0 failures, and the
collision probes went from 3/4 to 4/4.

Verified: TCP session, character creation and login, map load, local actor
presence, spawn grounding, click-to-move through the genuine ray → navigation
pick → `MOVE_TO` path, traversal to nine landmarks, collision against authored
proxies, camera rotation and zoom, server-tile round-tripping, the HUD minimap,
the tab map, and world bounds.

Grounding measured at every waypoint as the difference between the actor's Y and
the navigation-surface raycast hit:

| Location | actor Y | surface Y | delta |
|---|---|---|---|
| spawn | 31.10 | 31.08 | +0.020 |
| plaza centre | 31.10 | 31.08 | +0.020 |
| civic quarter | 31.10 | 31.08 | +0.020 |
| ring road east | 31.10 | 31.08 | +0.020 |
| residential block | 31.10 | 31.08 | +0.020 |
| east gate approach | 31.10 | 31.08 | +0.020 |
| north avenue | 31.10 | 31.08 | +0.020 |
| north gate | 31.10 | 31.08 | +0.020 |
| north bridge deck | 27.32 | 27.30 | +0.020 |
| sanctuary approach | 74.12 | 74.10 | +0.020 |

`+0.020` is exactly the offset `main.gd` applies when placing an actor on a
surface, on three different structures at three different elevations. The
character never sank below terrain, floated, or lost its surface.

## 5. Known issues found, not caused by this map

**The legacy 11-bit actor coordinate field cannot address the whole map under
the current registry binding.** `protocol.gd` masks actor X/Y with `0x7ff`, so
only server tiles 0–2047 survive the wire. With the registry's
`metresPerTile 0.4651162791` and `serverOrigin [384, 384]` that is:

```
world x: -178.6 .. +773.5 m
world z: -773.5 .. +178.6 m
```

The walled city spans ±352 m, so **the western and northern thirds of the city
are not addressable** — `MOVE_TO` to those tiles wraps. This is a property of
the existing binding, not of the new geometry: the previous 720 m map had the
same limit. The map preserves the binding unchanged so nothing regresses, and
the gameplay test's waypoints stay inside the addressable range and record the
limit rather than hiding it.

Note also that the packaged EWCG collision grid's own mapping implies **2.15 m
per tile** (`(tile − 384) × 2.15`, giving ±825 m over its 1536 half-tile cells),
which is the reciprocal of the registry's `metresPerTile`. One of the two is
wrong. Resolving it needs the authoritative server profile, which was not
reachable from this environment. Recommended server-side follow-up: confirm the
tile scale, then either set `metresPerTile` to 2.15 or raise `serverOrigin` so
the whole island falls inside tiles 0–2047.

**Client performance defect fixed here:** the minimap and tab-map SubViewports
shipped with `render_target_update_mode = ALWAYS`, so the entire world was
rendered three times per frame even while both panels were hidden. They are now
gated on panel visibility. On the software renderer this was the difference
between a stalled capture and a completed one.

## 6. Performance

Measured in the running client, software GL, 1280×720:

| Metric | Value |
|---|---|
| Unique mesh triangles | 188,383 |
| Visible triangles (whole map in frustum) | 811,083 |
| Nodes / instances | 3,030 / 2,992 |
| Meshes / materials / textures | 154 / 30 / 91 |
| Draw calls (typical gameplay view) | 288 |
| Objects in frame | 486 |
| Texture memory (exported, RGBA8 + mips) | 110.5 MB |
| GLB size | 23.5 MB |
| Frame time, software GL (median) | 244 ms |

Against the budgets recorded for the previous package (desktop LOD1 under 1.5 M
visible triangles and 512 MiB textures): visible triangles are at 59% of budget
and texture memory at 22%. The 244 ms frame time is a software-rasteriser
figure with no GPU present and is not indicative of real hardware; the useful
hardware-independent numbers are the draw-call and triangle counts above.

## 7. Not verified here

- No run against a real `eloria-server`: the repository was not reachable from
  this environment. All server-facing behaviour was exercised against a local
  protocol fixture written from `protocol.gd`, so the *client* side of login,
  map assignment, actor spawn, movement and coordinate reporting is genuinely
  tested, but the server's own collision map, spawn table and NPC/creature
  spawning are not.
- Portals and map transitions are declared in `world.json` and their positions
  were checked against the navigation surface, but no transition was executed:
  that requires a second map and a server that issues `CHANGE_MAP`.
- No GPU was available, so shadow quality, MSAA and high-graphics settings were
  not evaluated; only the compatibility renderer path was exercised.

## 8. Reproduction

```sh
# rebuild the package
python3 eloria-assets/tools/four_gates/build_four_gates.py

# spec conformance
gltf_validator eloria-assets/maps/four-gates/world.glb

# client views and minimap
godot --path godot-client --rendering-driver opengl3 \
  --script res://tests/integration/rendered_four_gates_views.gd
godot --path godot-client --rendering-driver opengl3 \
  --script res://tests/integration/rendered_four_gates_minimap.gd

# end-to-end gameplay against the local fixture
python3 godot-client/tests/integration/local_protocol_server.py --port 2000 &
godot --path godot-client --rendering-driver opengl3 \
  --script res://tests/integration/rendered_four_gates_gameplay.gd
```

Temporary characters created by the gameplay test: **`QA_FourGates_Temp1`**
(the name is overridable with `ELORIA_TEST_CHARACTER`). It exists only in the
local fixture's in-memory account table, which is discarded when the process
exits; no shared or production database was touched.
