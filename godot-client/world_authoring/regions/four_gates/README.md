# Four Gates authoring source

This folder contains the saved scene ([`four_gates.tscn`](four_gates.tscn)), its authoring specification ([`region-authoring-spec.json`](region-authoring-spec.json)), and the scene's assets. Open it from the **Territories** dock to make this territory active. You can select multiple neighboring rows under **Read-only references** while editing. Press **Ctrl+S** to save the active scene. The region's **Bake continent authoring snapshot** button creates an active-scene diagnostic only; the normal continent build consumes all registered saved scenes. See the [Territory authoring workspace guide](../../../docs/map-authoring-workspace.md) for the full workflow.

Imported roads start with **Shape terrain** disabled. Moving, widening, or deleting an imported road changes its route and rendering but leaves the saved ground as-is. Enable **Shape terrain** when an edit should grade the ground; new roads shape terrain by default.

Boundary changes are validated. The all-twelve build uses each saved scene's exact terrain; legacy mixed-state seam and post-support corrections skip saved-owned targets. A fixed neighboring approach correction may need refreshing if its source terrain or route changes, and cannot overwrite a neighbor after it becomes saved authored.
