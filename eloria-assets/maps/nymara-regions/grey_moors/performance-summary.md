# Grey Moors performance — inhabited 384 m survey

The package is 33.33 MB with 522,281 unique triangles and 719,147 instanced triangles. These totals include the authored receiving-scene subset, which the runtime hides on the active map and selects only for the corresponding neighboring view.

The reduced package is 20.61 MB with 532,155 instanced triangles. The final geometry/minimap/collision are deterministic toolkit outputs. The map retains 72 landmarks while terrain area contracts by 55.6 percent; placement meshes keep full human dimensions.

Gameplay-camera measurements are recorded in work-output/northern-rollout/grey_moors/after/survey.json. Those numbers are GPU/host observations, not a portable frame-rate guarantee. Root integration tests the real resident-neighbor handoff.
