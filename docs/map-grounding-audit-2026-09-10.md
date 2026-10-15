# Map scenery grounding audit — 10 September 2026

The reported object was a persistent timber gatepost in Lantern Reach. Its
reusable gate model spans 8.1 metres including the stone feet, but the beacon
and return connectors are narrower. The return connector is also offset from
the gameplay gate's centre. Opening a gate hides its leaf, exposing the
unsupported posts.

The gate authoring now clips the full footing footprint to the available land,
leaves a bank margin, and samples the rendered floor at the footing corners.
The production client and prototype both consume those generated transforms.
The quest flags, server gate bounds, routes and walk grids are unchanged.

## Other confirmed corrections

| Map | Object | Correction |
| --- | --- | --- |
| Amberwood | `Prop_BurntBrazier_2` | Lowered from 30.561 m to the ground at 28.355 m. The builder now samples each brazier's own position instead of the neighbouring camp's height. |
| Verdant Stair | `Signpost_TempleCourt` | Lowered from 100 m to the recessed forecourt at 98.2 m. The builder uses the actual court height. |
| Crownwater | `Prop_Lamp_Harbour_7` and `Prop_Banner_Harbour_3` | Removed the final stations of the decorative rows, which extended beyond the quay/island over water. The source rows now end at their last supported stations. Their obsolete collision-node declarations were removed. |
| Westhaven | `Prop_Lamp_crown_climb_06` | Lowered from 41.626 m to the rendered floor at 41 m. Street lamps now sample the actual terrain triangles. |
| Ssarathi Ruins | `Tree_779` | Lowered from 16.770 m to its planting surface at 15.917 m. Tree placement now samples the actual terrain triangles. |

The triangle sampler addresses a separate source of floating objects: bilinear
height interpolation can return a point above a rendered triangle on a saddle.
It is used for prop placement without changing the terrain-shaping sampler.

The packaged GLBs and their reduced-detail counterparts were updated where the
affected instances exist. The reduced-detail Ssarathi scene does not contain
`Tree_779`. Mesh and texture binary payloads were preserved; the edits change
node placement or remove unsupported instances. File statistics and structural
validation reports were refreshed.

## Coverage and limits

The read-only geometry screen considered all **65 map packages**, checking
**11,136 scenery groups** against named ground and walking surfaces. Potential
gaps were then checked against surrounding scene geometry and the object's
authored anchor. This distinguishes a planted tree with roots over a slope
from an unsupported tree, and avoids automatically moving boats, sails, roof
pieces, wall fittings and suspended decorations.

This is not a complete manual walkthrough or a guarantee that every small
component is grounded. Material-batched scenery and composed rooms can combine
several objects into one group; architectural attachments and scenery beyond
the terrain require visual interpretation. The six additional corrections
above are the confirmed ordinary-scenery defects from this pass.

The diagnostic scripts and raw screening results are in the workspace's
`work-output/audit_floating_scenery.py`, `check_scenery_support.py`, and their
JSON reports. Those candidate lists include legitimate elevated scenery and
are not lists of confirmed defects.

## Verification

- Godot imported the real Lantern Reach scene and checked all **24 corners**
  of the six stone footings: **zero failures**. Opening all three gates still
  hides only their leaves and retains their grounded posts.
- Rendered before/after captures confirm the beacon and return posts sit on
  the banks after the correction (`work-output/*_gate-before.png` and
  `work-output/*_gate-after.png`).
- **14 Python tests passed**, covering generated gate transforms, the existing
  tutorial package contracts and reproducibility, triangle interpolation,
  corrected prop contact, and the shortened Crownwater rows.
- The existing native boat-boarding regression passed.
- All **nine edited GLBs** passed the project structural validator with
  **zero errors and zero warnings**.

Restart the client to load the updated presentation scripts and map packages.
