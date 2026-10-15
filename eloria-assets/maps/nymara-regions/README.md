# Nymara regional production maps

This package covers all eighteen supplied maps beyond Four Gates. It contains 180 detailed concept perspectives. The Godot-native production pass is active for the eleven exteriors; the seven interiors have complete concept packages and preserved ELM sources ready for the next geometry tranche.

## Scope

- 18 maps, each with a five-by-two concept detail board
- 180 distinct close perspectives; the 110 exterior views have per-panel production checkpoints
- 18 source ELM SHA-256 matches
- 615 landmark instances in the current terrain/landmark/material pass
- 33 original 512×512 textures: base color, normal, and ORM for every region
- Godot registry entries for canonical `maps/nymara/*.elm`, bare IDs, and filename aliases

The generated GLBs are production starters, not final art. Terrain, routes, water masks, arrival coordinates, material language, and landmark silhouettes are implemented. Hero landmark geometry, final foliage/prop density, lighting polish, and per-map performance LODs remain in progress.

## The continent layer

How the regions join up - the crossings graph, the marches at every edge, the
lore sites the NPC threads point at, the small rooms on every insides map and
the tools that write the server's portal table from all of it - is in
`CONTINENT.md`. The hidden layer under each map - the secrets, their
entrances and what they hold - is in `SECRETS.md`; `SECRETS-REVIEW.md` lists
what was proposed for them but not built.
The instanced routes a party runs from a keeper - the gauntlets - are in
`GAUNTLETS.md`, with `GAUNTLETS-REVIEW.md` for what they could still gain.

## Rebuild and verify

Each region builds itself, from its own `source/build_<region>.py` over the
shared `_toolkit/`. The single ELM-driven builder that produced the first pass
went with the C client; see `REGION-PRODUCTION-GUIDE.md`.

```sh
cd eloria-assets/maps/nymara-regions/<region>/source && python3 build_<region>.py
python3 eloria-assets/tools/render_nymara_region_maps.py \
  eloria-assets/maps/nymara-regions/*/world.glb \
  --columns 4 \
  --output eloria-assets/maps/nymara-regions/production-preview-contact-sheet.png
```

See `concept-generation-manifest.json` for the board prompt pattern and all 180 panel subjects. See `validation-report.json` for source hashes, GLB structure, texture dimensions, duplicate/blank-panel checks, and exterior concept evidence coverage.
