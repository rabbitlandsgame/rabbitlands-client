# Reference-derived hair authoring

`build_loose_reference.py` retains the fitted reference's painted exterior and
adds an independent scalp cap and rooted fine/messy
detail. It uses existing reconstruction files and calls no external service.
Keep original extractions immutable and write each candidate to a fresh stage.
An inset closed backing is optional. Use `backing_mode: "none"` when the
painted exterior already provides the volume; a backing must never become
the visible rear surface or fill an intentional curl opening.

```text
python reference_surface.py extract --fit <fit.json> --out <original>
python build_loose_reference.py prepare --source <original> --fit <fit.json> --profile styles/layered_long.json --stage <stage> --sex female
blender -b --factory-startup --threads 2 --python decimate_reference_surface.py -- <stage> --weld-geometry
python build_loose_reference.py pack --stage <stage> --profile styles/layered_long.json --out <candidate/layered_long_female.glb> --check
```

First run `pack --neutral-only` into a separate ignored preview directory and
inspect the painted silhouette in the real client. This writes zero identity
and grooming deltas and explicitly remains a neutral geometry preview. Repair
unexpected deformation or visible backing before running the expensive checked
build; never install the preview as a qualified hairstyle.

Use the current pinned `RL_HEADS_BUILD`, `RL_MPFB_GROUPS`, `RL_HEADS_ROOT`
and `RL_WORKTREE` inputs described in README.md. Private paths and full source
records belong in ignored reports; runtime extras carry safe SHA-256 values.
The torso/inner-shoulder envelope excludes native head triangles hidden by the
RL head cut, scopes each primitive to its used vertices, and includes the
repaired shirt. Forward/backward clearance preserves hanging X/Y instead of
pushing locks upwards or across outstretched arms. Painted exterior and hidden
backing use distinct clearance layers; each reduced backing is inset against
its matching exterior. Cap/backing UVs stay in the opaque texture region.
`preserve_curtain_depth` shares the required lower-lock displacement within
each side instead of flattening individual curls against the torso envelope.
`transport_normals` carries the source's painted surface shading through that
fit. Both options preserve their old default behavior when absent.
For a profile using closed backing, run `backing` and `smooth_loose_backing.py`
before packing. Do not run blanket topology filling on an exterior with
intentional ringlets: identify an accidental opening before repairing it.
The stage's extraction and reduced exterior/backing files remain reusable when
repairing only exported attachment, grooming, or material data.

`pack(args, groom_builder=None, atlas_builder=None, colour_builder=None, parts_builder=None)`
exposes four authoring hooks. Their default functions are `groom_fields`,
`make_atlas`, `root_colours`, and `all_parts`. A tied style can reuse the export contract while supplying
its own knot motion and paint normalization. A grooming callback returns
`(roots, root_distance, deltas)` and may reserve clearance in `P` in place;
it must supply every identity target and the four `hl_*` targets. A colour
callback returns float RGBA. Core A is 1, fine/messy cards occupy distinct
continuous keep bands, and R carries soft-root coverage on opted-in clumps.
The part callback retains the same return tuple and ranges; exported primitive
`extras.partVertexRanges` records the actual compact ranges for inspection and
for painted backing that shares the exterior's UV region.

Root boundary detection welds POSITION before counting open edges, so UV
seams cannot become false faded stripes. For a geometry-checked older candidate,
the `root-edges --source <candidate.glb> --profile <style.json> --out <fresh/candidate.glb>`
step changes only COLOR.R bytes. Its report proves that geometry, skin, morph,
material and metadata bytes stayed unchanged. Coverage and visual checks must
still be rerun because root opacity changed.

`decimate_reference_surface.py -- <stage> --weld-geometry` is an explicit opt-in
for UV-split reference extractions. It welds positions at 0.001 mm before
reduction while preserving per-corner UVs and source normals, and records their
measured preservation together with source/tool/output hashes and geometric
open-edge counts in `lod-position-weld.json`. Original behavior is unchanged
without the flag. The receipt also reports each requested budget: complicated
painted topology may reach a reduction floor and still needs a separate lower
detail surface; the weld alone does not qualify an asset.

An additional `--split-nonmanifold` opt-in separates only edges incident to more
than two faces after that weld. It preserves every source face corner's position,
UV and normal exactly before reduction, and leaves ordinary two-face UV seams
joined. Its receipt records selected contacts and remaining nonmanifold edges.
Use it only for measured contact obstructions; reduced silhouette, painted seams,
coverage and budgets still require validation. It requires `--weld-geometry` and
does not alter the default reduction path.

A successful pack is a geometry check, not final qualification. Run structural
validation, the shader-equivalent scalp coverage gate at all three LODs, open
headwear fitting, and matched real-client views at neutral and grooming extremes.
Record exact output hashes and keep `qualified` false until those checks pass.
The style profiles alone do not register or replace an existing saved hairstyle.

For an exterior-only module, `bake_loose_cap.py --source <candidate.glb>
--out <fresh/candidate.glb>` maps the independent scalp cap into unique chart
tiles and bakes painted flow per texel from the actual exterior. It retains
every non-UV primitive accessor, every original exterior/detail UV, all skin and
morph data, and opaque cap alpha. The private report includes overlap, paint
distance, coverage and exact-accessor proofs; it does not qualify the geometry.
