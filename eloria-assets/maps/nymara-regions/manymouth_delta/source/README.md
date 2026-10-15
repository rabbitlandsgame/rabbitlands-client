# Manymouth compact source

The native distributary fan occupies 480 × 396 metres, X −138..342 and
Z −276..120. Its native server grid remains 480 × 480 with origin [138,120];
the northern empty rows are not additional land. The continent geography
stage adds addressable padding for the three shared land approaches and
frames the minimap from the region's owned physical footprint.

`compact_plan.py` resamples the original terrain before exporting geometry.
The market's 151 × 109 metre core retains its original metre spacing. Outer
channels contract through a monotone piecewise-linear field. All 72 named
houses and the halls, arch, shrines and stepped temple retain their original
mesh dimensions. Timber routes and house porches are surveyed again at full
width, with physical beds below their decks. The temple's western approach
uses a processional switchback between the low quay and its original stair
foot. The northern Crownwater link remains a ferry journey.

Four short timber spurs give the school, reliquary, banyan and rootrun
discoveries direct access. Temple Spring and Crab Pit sit on adjacent clear
silt beside their original neighbourhoods, clear of the temple approach and
an inhabited house floor. All fourteen discovery props and their explicit
standing posts are checked together against exported walking geometry.
The old westward march stone stands on the sea landing's timber deck. The
Paddy Watch landmark records its veranda level; its nine actual timber piles
reach the varying channel bed below, so the central undercroft is not a
floating foundation.

The east watch landing keeps an opening above its timber road. Two mature
palms stand farther into the southern forest verge, with two smaller crowns
at its edge; other forest specimens retain their full size. The source
regression checks nine actual camera-to-landing rays, root contact and the
four crowns' bounds inside the region's ownership polygon.

`continent-migration.json` serializes the identical X/Z field. Publication
first maps legacy 576-grid coordinates into the compact native frame, then
adds the separately recorded continent origin delta. Source content sidecars
remain in the compact native frame. The `ready` flag is set only after the
complete geometry and exact server-height route audit passes. The publisher
resets saved Manymouth player positions once to `nativeArrival`, retaining
inventory and progress; it maps authored content through the full field.

From this directory:

```powershell
python -X utf8 -u rebuild_landscape.py --server <paired-server-checkout>
```

This builds the main GLB and LOD, pads only supported geographical ground,
refines deck heights, opens actual walk surfaces, stamps solids, applies the
actor-centre surface guard, verifies routes and preserved IDs, and renders
the common north-up geometry minimap. It never writes server configuration.
`--out <isolated-package>` supports source reproduction evidence, while
`--correct-only` repeats the derived collision/cartography stages after an
already completed native build. `audit_compact.py --server` uses the paired
server's actual height quantization and diagonal climb rules; omitting it
explicitly reports the weaker client-mask-only check.

For an isolated native prototype without continent geology, use
`build_manymouth_delta.py --prototype --out <isolated-package> --skip-minimap`.
Its shared gate endpoints intentionally stop 42 metres inside the seam.
`legacy-content-manifest.json` records the pre-compaction semantic IDs;
`legacy-server-content.json` records the original served coordinate rows.
