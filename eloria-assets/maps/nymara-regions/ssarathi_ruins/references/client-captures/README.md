# Real client frames

Twenty-four frames rendered by **Godot 4.7.2-stable** on a GPU, not by the
offline preview renderer.

Each was produced by loading `../../world.glb` the way the game does, rebuilding
collision and navigation through the project's own `WorldLoader`, and lighting
the scene from `../../world.json`'s `environment` block through the project's
own `WorldEnvironmentBinder`. The camera set is `../captures/index.json`, so
every frame here has a same-framing counterpart in `../captures/` — which is the
**offline preview**, and is not a client frame.

Where the two disagree, these are the truth: they carry the shipped tonemap,
fog, sun and cascaded shadows, and the preview does not.

Reproduce with:

```sh
cd godot-client
Godot_v4.7.2-stable_win64_console.exe --path . \
  --script ../eloria-assets/maps/nymara-regions/_toolkit/godot_capture.gd \
  --rendering-driver vulkan --resolution 1600x1000 -- \
  --package=<abs path to ssarathi_ruins> --out=<abs path> --environment=manifest
```

Stored as WebP at quality 88: the PNG set is 44 MB and this is 5.4 MB.
