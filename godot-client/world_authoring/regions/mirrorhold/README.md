# Mirrorhold authoring source

This directory contains Mirrorhold's saved authoring scene, [`mirrorhold.tscn`](mirrorhold.tscn), and its committed assets. Open it from the **Territories** dock, make it active, and save the scene after editing. The region's **Bake continent authoring snapshot** button creates a diagnostic snapshot for the active scene only; the normal continent build consumes all registered saved scenes. See the [Territory authoring workspace guide](../../../docs/map-authoring-workspace.md) for opening neighboring read-only references and the full workflow.

This directory is the saved authority for Mirrorhold after its one-time certified bootstrap. The terrain starts from the published resolved grid; imported roads are passive, so moving, widening, or deleting them changes routing and rendering while leaving the saved ground unchanged. Enable **Shape terrain** on a path only when the edit should alter ground.

WaterRegions/MirrorLake owns the saved lake ellipse and water level. Its legacy depth is reference metadata; the actual depth is the saved water level minus the independently editable saved terrain. Deleting or disabling the control does not revive the retired plan lake because the region spec keeps the mirror_lake feature claim.

The captured object prototypes and three architectural crossing/access assemblies come from the certified final composed output. Normal builds use this saved scene and its committed assets. Boundary changes are validated. The Amberwood-side road approach uses fixed corrections on procedural-owned shoulder terrain, not a live seam solver. If the source terrain or route changes, the correction may need to be refreshed and certified again. It cannot overwrite Mirrorhold's saved-authored terrain.
