# Rabbit Lands assets

Asset sources for the Godot client, and the tools that build them. It must not
contain files extracted from an Eternal Lands installation, release archive,
website, or other Binary Data distribution — `tools/check_provenance.py` fails
the build if an Eternal Lands map name or engine file format appears anywhere in
the repository.

Until 2026-09-03 this directory also generated a complete Eternal Lands format
data pack — Cal3D actors, native E3D scenery, ELM maps, BMP/DDS atlases — for
the C client that has since been removed. That whole `generate_*` chain, its
validators, and the packs it produced are gone; see
[ELORIA_MODIFICATIONS.md](../ELORIA_MODIFICATIONS.md). What is left builds GLB,
PNG and JSON, which is all the Godot client reads.

## Layout

| path                | what it is                                                                |
|---------------------|---------------------------------------------------------------------------|
| `maps/`             | world packages: a GLB scene, a `world.json` manifest, an EWCG `collision.bin`, a minimap, and the region's own `source/build_*.py`. |
| `source/`           | authored model sources, including the Quaternius base characters and animation library. |
| `concepts/`         | the concept art regions, creatures and items are authored against.         |
| `qa/`, `renders/`   | evidence: contact sheets and comparison renders kept with the work they record. |
| `fonts/`            | the client's typeface.                                                     |
| `tools/`            | the builders, importers and validators.                                    |

`provenance.json` records where every generated asset comes from and under what
licence. Adding a generated asset means adding its entry.

## Tools

The ones a normal change runs:

```bash
# Actors, creatures and equipment the client loads
python3 tools/build_native_nymara_glbs.py
python3 tools/build_native_world_object_glbs.py
python3 tools/validate_creature_glbs.py \
  --catalog ../godot-client/data/actors/native_asset_catalog.json \
  --models ../godot-client/data/actors/models.json \
  --animations ../godot-client/data/animations/creature.json

# Inventory icons
python3 tools/build_item_icon_atlases.py

# Licensed sound (retained originals; numpy, scipy and FFmpeg required)
python3 tools/build_native_sounds.py

# Compliance
python3 tools/check_provenance.py
```

Maps are built from their own region directory — `maps/nymara-regions/<region>/
source/build_<region>.py` — over the shared `maps/nymara-regions/_toolkit/`.
`maps/nymara-regions/REGION-PRODUCTION-GUIDE.md` is the guide for that work.

## Licence

Original assets are CC BY 4.0; see [LICENSE.md](LICENSE.md).

Third-party audio retains CC0 or CC BY 3.0 licenses. See
[source/audio/README.md](source/audio/README.md) for sources and attribution.
