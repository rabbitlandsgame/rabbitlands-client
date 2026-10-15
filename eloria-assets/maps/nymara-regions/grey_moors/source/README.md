# Grey Moors authored landscape

`rebuild_landscape.py` rebuilds the main and distant scenes, minimap and native collision, then runs the normal geometry-derived walking corrections. For a continental release, use `eloria-assets/tools/rebuild_continent_geography.py --stage geometry --region grey_moors` with the coordinator's server, data and artifact paths. That coordinator expands the served frame, reruns the corrections and records the exact source certificate. Regional scripts do not publish server content.

The local delta approach is authored in `manymouth_approach.py`, after the shared geography/outer stages and before `connector_finish.apply`. Its curve keeps the native start, bends inland, rises toward the surrounding moor and descends to the unchanged shared crossing. The final three metres retain the exact 3.14 m datum. The full 8.5 m road and the seven server crossing lanes remain physical geometry.

`delta_bank_landform.py` shapes both dry banks, with a 35 m landward feather. It conforms the small inner mouth to actual road triangle edges before seating its ground. This intentionally permits changes to inward vertices of the old three-metre ownership band; the actual common boundary remains fixed. Native walking meshes, water, protected footings and linked placements are preserved. Exposed steep terrain receives vertically projected stone on its existing triangles.

`delta_verge.py` retains unlinked scrub newly covered by the curve in nearby irregular verge pockets. It preserves each model and scale, checks its full projected extent against ownership and road clearance, and maintains the original grounding offset. Linked content is excluded.

Run `python -m unittest discover -s eloria-assets/maps/nymara-regions/grey_moors/source -p test_manymouth_approach.py`. Release evidence additionally checks actual exported upward surfaces, all road widths, conservative actor footprints and World steps, adjacent Grey–West edge agreement, and matching gameplay-camera views. Numerical passes alone do not establish visual acceptance.
