# Whitehorn Range authoring source

This directory contains Whitehorn Range's saved authoring scene,
[`whitehorn_range.tscn`](whitehorn_range.tscn), and its committed assets. Open
it from the **Territories** dock, make it active, and save the scene after
editing. The region's **Bake continent authoring snapshot** button creates a
diagnostic snapshot for the active scene only; the normal continent build
consumes all registered saved scenes. See the
[Territory authoring workspace guide](../../../docs/map-authoring-workspace.md)
for opening neighboring read-only references and the full workflow.

Boundary changes are validated. Some neighboring road approaches use fixed
corrections on procedural-owned shoulder terrain, not a live seam solver. If
the source terrain or route changes, a correction may need to be refreshed and
certified again. It cannot overwrite Whitehorn's saved-authored terrain.

The saved `base-heights.f32le` is the certified resolved Whitehorn terrain.
The matching `base-colors.rgba8` is the published snow, rock, and worn-ground
paint at every terrain grid vertex. This paint is a frozen editable baseline;
it is not recalculated from height or slope. Texture regions can be layered or
the saved paint can be replaced deliberately without invoking the retired
procedural palette.

The 23 imported roads start with **Shape terrain** disabled. Moving, widening,
or deleting one changes its rendered route while the saved terrain remains
unchanged. Enable **Shape terrain** to grade the terrain along an edited road;
new roads shape terrain by default. The 45-control Hornwater path owns the
whole `horn_tributary`, including its Amberwood continuation.

The three published bridge unions remain exact editable asset assemblies.
Each groups the saved walk deck and timber edge under one transform and keeps
its stable river-qualified crossing ID and local endpoints. The published ice
cave remains an authored asset; inactive MC009 source content is excluded.

`Gameplay/Spawns/continent-arrival` is the sole saved default spawn. It is
connected by the normal territory publication contract and intentionally has
no fabricated immutable runtime binding. The 197 runtime bindings in the seed
correspond only to real immutable profile records.

The saved `glacier-temple-pass.tres` sculpt layer cuts a walking pass through the
narrow ridge on the Glacier Temple road near server tile `(320, 472)`. Its 88
height deltas retain the surrounding ridge and leave the frozen base intact.
The road follows the sculpted terrain and the normal bake includes this layer.
