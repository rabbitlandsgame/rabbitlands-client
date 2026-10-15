# Amethyst Barrens authoring source

The saved `base-heights.f32le` is the certified, resolved Amethyst terrain.
It includes the published ground beneath legacy roads and crossing assemblies
and is the only terrain height source used by the authoring snapshot.

The 22 imported roads start with **Shape terrain** disabled. Moving, widening,
or deleting one changes its rendered road and routing contribution while the
saved ground remains unchanged. Enable **Shape terrain** to grade the saved
ground along an edited road. Newly created roads shape terrain by default.
Because the old grade is ordinary saved terrain, moving a road does not
automatically heal its former bed; edit that ground explicitly with terrain
controls when a layout change requires restoration.

The eight surveyed bridge and ferry assemblies are editable assets. Their
visual, solid, and walk subtrees and declared crossing endpoints share the same
saved asset transform. Their published approach landform remains part of the
saved terrain.
