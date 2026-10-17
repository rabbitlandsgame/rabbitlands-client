# Continent v2 section partition

Active map IDs, exact polygons and ownership priority come from `partition-inputs/sections_spec.json`; the recorded
check report has 33 ordinary shared borders. Ravenhead retains both disjoint ownership rings. All editor bases are
byte crops of the hash-pinned `group-terrain` frozen terrain. Its grid is a data parent outside the active catalog.
The original plan and catalog are pinned under `partition-inputs` with their source commit and file hashes.

Run `python godot-client/tools/bootstrap_continent_v2_territory.py --check` to replay immutable crop/frame/plan checks.
The bootstrap does not reset existing authored scenes and preserves gameplay/authority spec fields. Edit those
scenes normally, then run `python godot-client/tools/continent_v2_territories.py` to validate seams and ownership.
Do not re-run the original Meshy conditioning. Source kit libraries are shared by catalog metadata; placements
remain authored content. Original source scene/content/package directories retire after their saved content and
publication move; the three catalog-declared kit folders remain shared libraries without active source editors.

## Region borders

Neighbouring maps change gradually, never at a line. The ground-colour grade over the frozen vertex colours ramps
linearly across each border, `featherMetres` (130 m) on each side, about 260 m in all. The border it ramps across is
warped by smooth noise (`borderWarpMetres` 60 m, `borderWarpScaleMetres` 80 m), so maps interfinger, and border zones
lean toward a neutral meadow `ecotone` colour, so two strong palettes meet through grassland rather than a muddy mix.
Each `godot-client/world_authoring/regions/<map>/colour-grade.json` records these values beside its graded copy
`base-colors-graded.rgba8`; all fifteen maps use the same ones. Flora and ground-region bands that cross a border
follow the same rule at roughly 150-250 m.

## Server publication

After all active saved scenes are committed, bake every catalog map and publish its client package from that
exact bake. Export collision, crossings and the other shared publication steps before running `publish_server.py`.
Pass one `--bake MAP_ID=BAKE_DIRECTORY` argument for each active catalog entry, plus `--server`, `--stage m4` and
either `--check` or `--apply`. The publisher validates the catalog/frame/content-table map set dynamically; it has
no fixed fifteen-map list. Apply is followed by check using the same inputs.

The generated server overlay carries per-map rows and map-qualified chapter targets, approaches, NPC posts and
register/ferry objects. `landing.json` retains schema `eloria-landing-v1`: each target and cast post includes `map`,
and register/ferry object descriptors are `{map, id}`. The hub is `landfall`; chapter steps 1-6 occur there, step 7
in Warrenmead, step 9 in Reedfall and step 10 in Greenlight. Runtime isle membership comes from the served manifest.
Retired map saves return home; fresh map IDs have no character position migration.

Three authored default spawn markers are conserved. Twelve additional maps use separately hash-bound generated
arrival metadata, validated by `arrivals.py` against the recorded source/frame/ownership contract. Generated
arrivals are outside gameplay marker arrays and do not increase the authored marker total. Marker rename history
and shared kit identities retain pinned historical source names; active ownership uses the new catalog IDs.

The overlay sits beside certified legacy tables. A runtime change to a certified source such as `world.py` needs
the owner's separate certificate-advance kit; publication does not overwrite the immutable legacy authority.

Five public shared-storage chests are authored in Landfall (beside the register), Greenlight (the ferry quay),
Hearthcroft (the roadside hamlet), Stagheath (the red lighthouse courtyard), and Tollholm (beside the square).
Each uses per-map object ID 22 and the existing server `storage` role. The server stamps its 3x3 solid body;
publication requires the complete two-tile approach ring to be open and connected to an arrival. Client packages
retain the storage positions for generated cartography. Brown dots matching the Storage legend identify chests
on live Tab maps and minimaps, on other-area Tab previews, and on the Landfall overview. The original 254 conserved source markers
remain recorded in marker-renames.json; these five additions, eight Cotton plants, four underground entrances, and Rowan's tool shop bring the active authored total to 272.

Rowan Hale runs Rowan's Tools beside the Landfall civic square. The
shop sells Pickaxes, Hatchets, Needles, Mortar and Pestle, Smith's Hammer and basic
supplies. NPC scene extras `occupation` publishes the line a client draws under the
name (`npcs.txt` gains `occupation=` beside `actor_type=`; names stay simple, so a
name that starts with its own occupation is refused). NPC scene extras `mapCategory`
and `mapLabel` publish permanent service
markers: `general_store` is green and `tavern` is orange. Rowan's Tools and Bettany
Orl's Tavern appear on live maps, minimaps, region previews and the isle overview.

Two Cotton patches in Landfall provide beginner Thread and Cloth Roll supplies.
Each has four plants: one near the register and arrival, and one beside the Sage
meadow. The saved scene owns their positions and IDs 336-343. Publication checks
that every plant's approach ring is walkable with NPC posts and storage blocking
their occupied ground. Cotton uses the existing plant model and needs no tool.

Four cave mouths lead to `landfall_insides`: Lantern Mine, Pinebrow Deep Workings,
Spindle Mineral Cavern, and Boarsend Old Barrow. Their rooms share one interior
map with unfloored blackspace between sections. The peaceful Lantern Mine
supplies beginner Coal and Iron Ore; the deeper areas contain intermediate
encounters and additional minerals. See `../landfall_insides/README.md` for
locations, resources, encounter tiers, and the rebuild workflow.

## Publication order

New kit GLB or PNG files need `godot --headless --path godot-client --import` before the bake. A bake made without it
was seen to pass, and `publish_client.py` then refused the package because an external image "is not hash-bound by the
snapshot" (`_embed_external_images` in `eloria-assets/maps/nymara-regions/_continent/authoring.py`); delete those
maps' bakes and bake again after the import. `publish_server.py` refuses a bake whose scene SHA-256 is not the
checkout's scene file (`read_bake`), so bake from the committed scene.

`publish_server.py --apply` writes `_continent_v2/publication.json` into the client checkout, and the server's sync
records the client checkout's HEAD as `clientCommit` in the server's `tools/collision/manifest.json`. Apply, commit
the record, then apply again so that provenance names the commit holding it; `--check` still passes when only that
recorded commit differs, and notes it as `provenanceOnly`. After a merge, regenerate the generated outputs
(crossings, publication records, each package's `world.json`, `collision.bin` and served grid) from the merged
sources instead of hand-merging them.

## Harvest presentation

Owner-approved 2026-10-14 (`work-output/landfall-audit-2026-10-14/harvest/FINDINGS.md` 5.1-5.6): inside a harvest
grouping every visible plant or rock of that kind is harvestable, as a patch node (the node's model is the whole
natural unit; only its centre tile blocks) or as promoted scenery (a placed kit model is the node's art). A
`Gameplay/Harvestables` marker may carry `variant`, `yaw`, `footprint`, `grouping`, `groupingName` and
`bindPlacement` extras; `harvest_presentation.py` is the schema and its checks. `publish_client.py` writes every
harvest marker into the territory manifest's `harvestables` (with `harvestablesSchema`) and the groupings into
`harvestGroupings`; packages from before carry an empty list and the client presents their nodes as it always did.
`publish_server.py` refuses a node whose tile centre lies within a road's half-width (D11) and judges harvest nodes
by the reach-side approach rule (D4: three ring tiles open and reached, or a reached tile within Chebyshev 2, and
the server's walk-to tile reached); `HARVEST_APPROACH_RULE = "ring"` restores the eight-neighbour rule.
