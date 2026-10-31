# Reference-derived hair authoring

`build_loose_reference.py` retains the fitted reference's painted exterior and
adds an inset closed backing, an independent scalp cap, and rooted fine/messy
detail. It uses existing reconstruction files and calls no external service.
Keep original extractions immutable and write each candidate to a fresh stage.

```text
python reference_surface.py extract --fit <fit.json> --out <original>
python build_loose_reference.py prepare --source <original> --fit <fit.json> --profile styles/layered_long.json --stage <stage> --sex female
blender -b --factory-startup --threads 2 --python repair_reference_topology.py -- <stage>
blender -b --factory-startup --threads 2 --python decimate_reference_surface.py -- <stage>
python build_loose_reference.py backing --stage <stage> --profile styles/layered_long.json
blender -b --factory-startup --threads 2 --python smooth_loose_backing.py -- <stage/backing>
python build_loose_reference.py pack --stage <stage> --profile styles/layered_long.json --out <candidate/layered_long_female.glb> --check
```

Use the current pinned `RL_HEADS_BUILD`, `RL_MPFB_GROUPS`, `RL_HEADS_ROOT`
and `RL_WORKTREE` inputs described in README.md. Private paths and full source
records belong in ignored reports; runtime extras carry safe SHA-256 values.
Body clearance excludes the native head triangles hidden by the RL head cut,
scopes each primitive to its used vertices, and includes the repaired shirt.
The stage's extraction and reduced exterior/backing files remain reusable when
repairing only exported attachment, grooming, or material data.

`pack(args, groom_builder=None, atlas_builder=None, colour_builder=None)` exposes
three authoring hooks. Their default functions are `groom_fields`, `make_atlas`
and `root_colours`. A tied style can reuse the export contract while supplying
its own knot motion and paint normalization. A grooming callback returns
`(roots, root_distance, deltas)` and may reserve clearance in `P` in place;
it must supply every identity target and the four `hl_*` targets. A colour
callback returns float RGBA. Core A is 1, fine/messy cards occupy distinct
continuous keep bands, and R carries soft-root coverage on opted-in clumps.

Root boundary detection welds POSITION before counting open edges, so UV
seams cannot become false faded stripes. For a geometry-checked older candidate,
the `root-edges --source <candidate.glb> --profile <style.json> --out <fresh/candidate.glb>`
step changes only COLOR.R bytes. Its report proves that geometry, skin, morph,
material and metadata bytes stayed unchanged. Coverage and visual checks must
still be rerun because root opacity changed.

A successful pack is a geometry check, not final qualification. Run structural
validation, the shader-equivalent scalp coverage gate at all three LODs, open
headwear fitting, and matched real-client views at neutral and grooming extremes.
Record exact output hashes and keep `qualified` false until those checks pass.
The style profiles alone do not register or replace an existing saved hairstyle.
