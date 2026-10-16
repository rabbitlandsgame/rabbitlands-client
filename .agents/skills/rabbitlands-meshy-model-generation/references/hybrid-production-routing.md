# Hybrid production routing

Choose the cheapest route that preserves the asset's gameplay silhouette, deformation needs, and visible material detail. Record the route in the manifest before paid generation.

## Route A — volume/direct Smart Topology

Use by default for:

- ordinary creatures and background NPCs;
- prototypes and early gameplay tests;
- small or mid-distance props;
- broad, chunky designs whose identity lives in silhouette and painted color rather than microdetail;
- large batches where consistent automation matters more than close-up surface fidelity.

Established baseline: Smart Topology at about 4,000 triangle faces, 2K embedded base color, no PBR maps, and local rigging. Adjust the face target only when silhouette, appendage thickness, or camera distance demonstrates a need.

This route can still require cleanup or deformation-aware retopology. “Direct” means there is no mandatory high-to-low bake, not that the raw download is automatically production-ready.

## Route B — hero high-detail to baked low-poly

Use selectively for:

- player races and frequently seen player equipment;
- major bosses and close-up characters;
- hero weapons, complex armor, and signature props;
- assets needing carved, scaled, layered, damaged, feathered, or cloth surface detail that should survive on a lower-poly runtime mesh;
- assets needing multiple deliberately authored LODs.

Stages:

1. Generate and approve an immutable high-detail source. Judge identity, anatomy, silhouette, hidden surfaces, and materials before optimization.
2. Build an intentional runtime mesh. Set the triangle budget from screen size, silhouette, deformation, and platform—not from a universal number.
3. Place deformation loops around actual joints and preserve thickness in fingers, jaws, wing membranes, cloth edges, straps, and other thin structures.
4. UV unwrap the runtime mesh with sufficient padding, stable texel density, and seams placed away from focal areas and high-deformation regions where possible.
5. Bake from the approved high-detail source to the runtime mesh using a controlled cage or equivalent projection setup.
6. Inspect every baked map for ray misses, projection overlaps, gradients across hard edges, mirrored asymmetry, seam errors, and tangent-space mismatch.
7. Validate the low-poly silhouette and materials in Godot under game lighting and at gameplay distance before rigging approval.

Keep high source, runtime mesh, UV/bake configuration, cage when used, baked textures, hashes, and validation evidence in separate versioned stages.

## Deformation-critical override

Topology for animation is separate from surface detail. Route an asset through intentional retopology whenever automatic topology does not provide stable loops and clearance at required joints—even if the final material uses only base color and no high-poly bake.

Typical triggers include:

- player shoulders, elbows, hands, hips, knees, and face/jaw areas;
- digitigrade legs and paws;
- wing roots and folding membranes or feather panels;
- tentacle bases, multiple heads, many limbs, or segmented bodies;
- layered skirts, capes, straps, and fitted armor that must deform with the body.

Do not rely on a normal map to repair a bad silhouette, fused anatomy, missing thickness, or poor deformation topology.

## Material policy

- Preserve base-color-only materials for ordinary Eloria assets when additional maps do not improve the game view.
- Bake normal, roughness, metallic, or other PBR maps only when the asset and Godot material plan need them.
- Keep normal-map detail broad and restrained. It should reinforce the hand-painted forms rather than introduce realistic noise that disappears at gameplay distance.
- Validate tangent basis, color-space settings, channel packing, compression, and texture memory in the actual Godot material.

## Route-change rules

- Do not promote an entire batch to Route B because one asset fails. Reclassify only affected assets or body-plan groups.
- Do not repeatedly regenerate the same Smart Topology input to solve a systematic topology problem. Improve the concept or switch to intentional retopology.
- Do not downgrade a hero asset solely to meet a face count. Preserve silhouette first, then optimize hidden or low-value regions.
- A route change is a new documented stage; preserve the prior tasks and downloads.
