# Imported hanging hair body support

`hanging_reference_body.py` contains small authoring operations learned from
source-derived curly and wavy hair. It performs no generation, upload, asset
replacement, registration or qualification.

Keep the imported source, extraction, transform, fit, reductions, intermediate
failures and exact tool snapshots in ignored authoring storage. Public
provenance contains hashes and factual validation results only.

Use the current High head for its visible skin, and the evaluated actor's actual
High body cut for its torso. Apply `high_body_triangle_mask` to the exact declared
body source/order, and include both `rl_skin` and `rl_bodypatch` from the current
head. The uncut Native fixture below the head's rim alone can include removed
neck triangles and produce false High torso failures. The larger Native skull
is a separate placement problem. A convex body hull overestimates the neck and
shoulder region and can create an excessive gap around otherwise correct hair.

For each lower reference surface:

1. Establish position-weld groups before support moves any UV split copies.
   Preserve the fixed scalp and the original 46 exterior identity position
   fields. Include all indexed reference rows, including adaptive support rows.
2. Query the complete actual body at vertices, triangle centers and edge
   midpoints. Pass measured contact points and a reviewed shoulder region to
   `contact_step`. Shoulder roof contacts can move upward; lower back curls
   follow the actual outward direction. Do not lift a deep back curl all the
   way to shoulder height just to escape a depth intersection.
3. Share a neutral support proposal with `shared_displacement` before applying
   it. Fixed-cap groups stay fixed. Enforce the explicit, measured body support
   allowance with `assert_local_bound`; this does not alter the ordinary head
   or Native corrective limits, or the production skin-clearance gate.
4. Reduce only local, body-blocked Length/Volume influence. Use one scale for
   all four fields, propagate blocked triangle corners to their entire weld
   groups, and call `shared_control_influence` after every reduction. A final
   minimum-per-group repair is also required when continuing an older pass
   whose UV islands were attenuated independently. Keeping only vertex skin
   clearance can otherwise conceal centimeter-wide control seams.
   If the original fields already contain a small per-copy seating mismatch,
   reconcile that separately with `shared_control_vectors` and an explicit
   small bound before body attenuation. This operation requires fresh physical
   checks; it must not average away a large independent-attenuation seam.
   Audit the 46 identity position fields on those original groups as well.
   Their local binding can tear around the ear even when the neutral surface
   and all four grooming fields are coherent. A measured, bounded identity
   reconciliation keeps every default input and all grooming fields exact;
   preserve the cap's existing identity motion and update detail identity roots.
   The helper's `fixed` flag means zero motion for anchored grooming fields.
   Cap identity fields continue to follow the head and retain their source data.
5. Recompute valid normals and reattach separate detail to the final exterior
   and its linear shape fields. Preserve real curl openings; fill unintended
   scalp exposure with a continuous source-painted cap rather than filling
   every ringlet.

The helpers do not infer anatomy or approve a larger displacement allowance.
The caller records its measured region and bound, verifies the resulting
default silhouette from front, side and back, and preserves failed receipts.

Independently check the unchanged 2 mm skin gap on the current High head and
visible torso, including triangle interiors, all relevant controls and the
actual saved look. Also check scalp coverage, coherent opposite Length/Volume
endpoints, fixed-cap immobility and the detail controls at every LOD. Full
Native control/pose tests and visual review remain separate. A High-only
candidate must keep Native availability withheld until those tests pass.

Run the focused regression with:

```text
python eloria-assets/tools/rl_heads/hair/test_hanging_reference_body.py
```
