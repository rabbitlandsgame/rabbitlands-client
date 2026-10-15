# Canonical continent ownership (opt-in)

`user-boundary-redesign-v4.json` preserves source data copied without coordinate rounding,
resampling or polygon repair from the approved coordinate-locked master revision
`user-boundary-redesign-v4-marked-amberwood-amethyst`. Its provenance records the
master manifest's SHA-256. The design metadata retains the Four Gates circle
(center 520,820; radius 200; 384 millimetre-rounded vertices) and the Amberwood and
Amethyst marked inclusions. The true ownership domain is `[0,0,1500,1680]`; the
larger artwork canvas is bleed, not another ownership domain.

The original arrays remain immutable historical provenance. Their Grey Moors
ring self-intersects; the strict loader rejects it. On 2026-09-26 the user
approved the exact topology candidate with SHA-256
`30356aca59906ccd2ec8ee01c5051eb369a61564b4a3de10d484b2ec0d1c6a09`.
`user-boundary-redesign-v4-topology-correction-v1.json` adopts that candidate's
polygons, frames, storage and design metadata exactly, under a separate revision.
Its `correction` record retains the original source/master and candidate hashes,
the candidate report hash, approval and method. No further coordinates changed.
The correction removes Grey Moors' thin folded spike (maximum boundary movement
51.135075226 m; Z maximum 700 to 650), plus the reviewed gap/overlap face changes.
All 384 Four Gates vertices are identical to the original source.

The regions remain in the existing plan's authoritative order. Coordinates and
baseline storage values come from the saved region specs and matching published
frames. These records pin continent translations, logical server origins, local
origins, tile scale and axis direction. In particular, Four Gates' translation
remains `[530,0,840]` although its new circle center is `[520,820]`.

The active `diagonal-plan.json` intentionally has **no** `ownership_contract`
selection. Source inspection/preview can opt in with a separate in-memory plan:

```python
import copy
import landscape
import world_layout

plan = copy.deepcopy(landscape.load_plan())
plan["ownership_contract"] = {
    "path": "ownership/user-boundary-redesign-v4-topology-correction-v1.json",
    "sha256": "98e48012e95815957437f26dedbc66f9394dd5538ff7a318e9b945c1f05b011f",
    "revision": "user-boundary-redesign-v4-marked-amberwood-amethyst-topology-correction-v1",
}
ids, sampled_owner, x0, z0 = world_layout.ownership_map(plan, cell=8)
```

`ownership_contract.for_plan` rejects missing/modified sources, unsupported
schema, duplicate JSON keys, invalid polygons, region/domain mismatch, interior
gaps or overlaps, and a changed plan translation. Validation tolerates only
1e-7 square metres of geometric arithmetic noise, without modifying polygons.
The approved marked inclusions are checked after domain clipping and excluding
the immutable Four Gates polygon, with the same 0.01 square metre area tolerance
for millimetre-rounded intersections. The authoritative master generator
(`work-output/continent-region-masters/build_continent_package.py`, transfers at
lines 308–310) assigns both marked zones before assigning the Four Gates circle
last. The earlier validator incorrectly required Amberwood to include the whole
enclosure, including 480.346434 square metres owned by Four Gates. The original
master has this same precedence; the residual outside-circle missing area is
0.004808723 square metres in the approved candidate. This validator correction
enforces the existing authority without altering geometry or tolerance. Nymara
design checks follow the corrected revision and original design lineage, so a
new correction revision does not evade circle or inclusion validation.

Cell masks sample polygon membership at cell centers, including the actual
center of a partially covered final preview cell. Shared boundaries belong to
the lexically first region ID; reversing index/plan order cannot change the named
owner. The returned integer indices still refer to the requested region order.
Exact point queries use the polygon, not the containing raster cell. Canonical
`World.polygons` retain every approved coordinate independent of sampling
resolution. Outside the closed domain ownership is -1. A cached parse is keyed
by bytes, so a same-size/mtime source edit cannot bypass hash verification.

Composition certificates include the selected source file and the loader code.
`World.address()` retains the source baseline origin/cells rather than deriving
a new transform from a polygon bounding box. These baseline storage envelopes
do not yet cover all newly owned land. Do not activate this plan in production
or claim that the full continent pipeline supports the new boundaries yet.

Remaining integration phases are separate:

1. Extend storage by the union of existing storage and required new extents,
   using optional `serverStorageVersion: 1` / `serverTileMin` (default zero).
   Keep existing logical transforms and coordinates fixed. Introduce negotiated
   per-map wire storage coordinates, never global sign extension.
2. Extend saved source terrain/color/sculpt grids on the common lattice; verify
   complete owned-vertex/ring coverage and equal shared heights. Wire the Godot
   editor to this source authority and export normal fresh snapshots.
3. Keep all immutable named portal anchors/XYZ/IDs and reciprocal destinations;
   derive separate geographic boundary crossing lanes and approach targets.
4. Clip exported boundary geometry against canonical polygons, then author,
   bake, test and verify all twelve regions through the normal pipeline.

No generated snapshot, package manifest, chunk, GLB, server field or current
scene is an input to this optional loader at runtime. Their source migrations
and acceptance tests belong to the later phases.
