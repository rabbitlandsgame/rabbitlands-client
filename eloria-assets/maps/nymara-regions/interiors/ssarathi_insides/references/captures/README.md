# Real client frames

Thirty-one frames rendered by **Godot 4.7.2-stable** on a GPU, not by the
offline preview renderer.

Each was produced by loading `../../world.glb` the way the game does, rebuilding
collision and navigation through the project's own `WorldLoader`, and lighting
the scene from `../../world.json`'s `environment` block through the project's own
`WorldEnvironmentBinder` — so the twenty-nine declared lamps are real lights and
the tonemap is the one the package ships.

The camera set in `index.json` is derived from the manifest's own `spaces` by
`_toolkit/interior_views.py`: one eye-level shot per space plus a raised plan
overview, so it cannot drift from the geometry.

Stored as WebP at quality 88: the PNG set is 22.6 MB and this is 1.8 MB.
