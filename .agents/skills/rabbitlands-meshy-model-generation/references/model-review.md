# Meshy output review

Record technical completion and production acceptance separately. A structurally valid file may still be rejected for identity, anatomy, topology, materials, or rigging risk.

## Structural checks

- GLB opens and all buffers, buffer views, accessors, and indices are valid.
- Vertex coordinates and bounds are finite and plausible.
- Every visible primitive has UVs and the intended material.
- Embedded images decode; base-color texture size and color space are correct.
- Geometry and triangle counts match the chosen budget closely enough for the asset.
- No unexpected external file dependency is required by the GLB.
- Optional FBX and separate texture downloads have valid headers and are preserved.
- The task ID, local filenames, and hashes match the ledger record that produced this download.

## Artistic and modeling checks

Rotate around the entire model and compare to the source image:

- species/identity and major silhouette match;
- exact limb, head, wing, horn, fin, and tentacle counts are preserved;
- back, underside, and occluded areas are resolved conservatively;
- surfaces are closed where expected, with no holes, inverted regions, internal duplicates, or floating fragments;
- no hidden inner wall: some deliveries model clothing, or the whole body, as a solid shell whose inside wall sits a few millimetres under the visible surface. On every new character body, run an outside-in visibility pass and remove the wall before rigging (`eloria-assets/tools/drop_inner_shell.py` applies that pass's mask);
- thin surfaces have usable thickness and do not collapse;
- shoulders, hips, knees, elbows, jaws, wing roots, and tail roots have deformation clearance;
- mouth interiors, eyelids, fingers, feathers, cloth, and layered pieces are not fused in ways that block required motion;
- disconnected parts are intentional and have a documented join/rigid/skinned treatment;
- texture projection is coherent on hidden sides and seams;
- baked lighting does not conflict with the game's lighting.

## Pilot-to-batch gate

Before expanding a new setting or asset class beyond its pilot, record:

- whether the selected face budget preserved the silhouette and moving parts;
- whether back/underside inference is acceptable;
- whether separated parts are useful or create rigging problems;
- whether base-color-only output matches the runtime material plan;
- which defects are systematic enough to fix in the source prompt/image rather than by regenerating the same input;
- an explicit proceed, revise, or stop verdict.

## Handoff record

For every asset, retain:

- stable ID and slug;
- source concept path and hash;
- Meshy task ID and submitted settings;
- all original download paths and hashes;
- face/vertex/material/texture counts;
- selected or rejected status with reasons;
- intended scale, up axis, forward axis, root placement, and body plan;
- known cleanup, topology, or rigging risks.

Keep the raw Meshy model immutable. A later stage owns edits.

For an intended bite, inspect whether the lower jaw and mouth interior actually exist as usable geometry. A closed-mouth sculpt may support only a restrained hinge; adding a bone does not create a cavity. Record that limitation before animation or regeneration. When reviewing an apparent face defect in a motion render, isolate the component and its skin owner: long raised claws can overlap the muzzle in side view.

For hero/bake-down assets, the final acceptance record must also identify the approved high-detail source hash, runtime-mesh hash and triangle count, UV set, bake settings/cage, baked map hashes, tangent basis, Godot material configuration, and gameplay-distance review. Passing the high-detail review does not automatically approve the baked runtime asset.
