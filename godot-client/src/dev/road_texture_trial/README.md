# Offline road texture trial

This experiment is not called by the production game. It qualifies a bounded
replacement for selected Suncoil road visuals after loading the baker's
road-free `base.glb` through the normal `WorldLoader` path.

```gdscript
const Trial := preload("res://src/dev/road_texture_trial/road_texture_trial.gd")
var result := Trial.apply(world_root, absolute_trial_json, "mask")
```

`baseline`, `original`, and `consolidated` are explicit no-ops. `mask` (also
`mask2`/`mask4`) accepts a chunk `trial.json` or its variant index containing
relative chunk metadata paths. It returns `{ok, errors, metrics}`. All fields
and colliders are prepared before placeholders change. Errors abort the trial;
there is no fallback rendering of the original road ribbons.

The baker's `rabbitlands-road-texture-trial-v1` contract is defined by
`eloria-assets/tools/road_texture_trial.py`. Each layer contains an R8 coverage
PNG mip chain, a losslessly Zstd-compressed little-endian RG32F unwrapped-UV
mip chain (raw references are also supported), explicit grid
bounds/gutters, source material glTF JSON, original node frames and compact
exact position/index collision inputs. Source materials are parsed by Godot
using only their referenced images. Their ordinary `LookGround.painted_for`
treatment is adapted from the current production shader with checked textual
anchors; class texture mapping, regional paint, rim noise, source detail
normal and roughness remain the production code's responsibility.

The visual uses the existing terrain mesh once per road sheet, with a shader
lift of 0.055 metres in the source frame. It is an extra masked overlay pass,
not a single-pass terrain blend. Its geometry is shared; the entire terrain
mesh is submitted for every sheet. Measure GPU cost rather than assuming a
performance improvement. Flat face normals and the road's tangent frame are
derived from terrain geometry and the sampled flow UVs.

Invisible compact collision meshes retain the old road node/material naming,
layer-8 collision, source-local positions and expanded triangle byte hashes.
After checking the source-order hash, their triangle corners 1 and 2 are
exchanged exactly as Godot's glTF importer does. Both the compact mesh and its
one-sided collision use that engine winding; backface collision stays disabled.
This keeps road height, grounding, and the existing footstep parent-material
lookup. It does not make the original visual mesh available for fallback.

Full painted mode with decorative grass is rejected explicitly: its CPU
grass classifier still needs a coverage adapter for the compact colliders.
The qualification harness must report that limit. Cartography and production
cache cooking are outside this offline renderer. No production replacement,
asset promotion, upload or release is enabled by these files.

The headless `contract_check.gd` verifies baseline behavior, source-shader
anchors, the material GLB container, decoded field layout/hashes and rejection
of a wrong decoded size, plus the exact collision triangle hash. Pass a variant
or chunk metadata file after `-- --trial PATH`. A passing headless check is not
a shader-compilation, screenshot or frame-time qualification.

`collision_contract_check.gd` separately imports the actual source chunk with
Godot, compares its CPU ImporterMesh triangle bytes with every compact collider,
waits four physics ticks and compares downward ray heights/normals on twelve
deterministic road witnesses. This guards the glTF-to-engine winding conversion,
which a raw source-byte check alone cannot establish.
