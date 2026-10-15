# Amberwood region source

The shared authoring toolkit now lives in `../../_toolkit/` and is documented
there. What remains here is Amberwood's own map: the composition, the placement
passes, its camera set, and its build entry points.

| File | Purpose |
| --- | --- |
| `build_amberwood.py` | Builds the whole runtime package: `world.glb`, `world.json`, `collision.bin`, `minimap.webp`, the validator report and the performance summary. Deterministic for a given seed. |
| `build_interiors.py` | Builds Amberwood's four interior packages. |
| `layout.py` | Surveyed terraces, crossings, millrace and authored content plots. |
| `landscape_plan.py` | Clearings, woodland habitat, worn ground, household yards and entrance grounding. |
| `compact_plan.py` | The 384-metre survey with protected village dimensions and restored route clearance. |
| `border_plan.py` | Open border approaches and views sampled from Whitehorn, Mirrorhold and the Grey Moors. |
| `rebuild_landscape.py` | Rebuilds the pilot and synchronises its collision, server content, entrances, markers and package digests. |
| `views.py` | `VIEWS` (the comparison camera set) and `PANELS` (detail-board panel to capture mapping). Region data, read by the toolkit's `capture_views.py` and `make_comparison.py`. |
| `preview_interior.py` | Interior preview harness. |

Amberwood's composition and placement modules (`region.py`, `populate.py`,
`interiors.py`) still sit inside the shared package for now; they are the
region-specific half of it and are the obvious next thing to separate.

```sh
make -C ../../_toolkit/native        # required before importing the region builder
python3 build_amberwood.py
python3 build_interiors.py
python3 build_insides.py              # combined estate and its collision grid
python3 ../../_toolkit/refine_walk_heights.py ..
python3 ../../_toolkit/open_walk_surfaces.py ..
python3 ../../_toolkit/stamp_solid_landmarks.py ..
python3 ../../_toolkit/secrets_build.py amberwood
python3 ../../_toolkit/verify_runtime.py --package ..
python3 ../../_toolkit/validate_gltf.py ../world.glb
```

## Reproducibility

A cache-cold rebuild reproduces every artefact byte-for-byte. Two things make
that true and are easy to break:

- name-derived seeds must use `noise.stable_hash()`, never the built-in
  `hash()`, which is salted per interpreter run;
- the texture cache in `preview.py` is keyed by a digest of `textures.py` and
  `materials.py`, so editing a recipe invalidates it. Before this was keyed, a
  stale cache silently shipped textures that no longer matched the source.

## Server-owned marker positions

server-content.json is the generated tile source for the package's legacy
NPC and harvest markers. The region builder reapplies it using the actual
rendered standing surface, preserving deterministic standalone builds.
After the server collision, portal, authored-content and relocation passes,
run from the client root:

    python eloria-assets/tools/sync_package_content.py --manifest ../wt-continent-server/config/eloria/client_content_manifest.json --package nymara-regions/amberwood --write-source-posts --apply

The server contract identifies harvest markers by server_object_id; NPC
markers follow their names. They must follow newly authored posts instead of
keeping an old scatter point walkable.
