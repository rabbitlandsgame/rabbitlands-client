# Mirrorhold: inhabited mountain bowl

Mirrorhold occupies a 384 m square, on 64 ELM tiles, with server origin
`(120, 96)`. The observatory remains above the civic descent and lake. Its
buildings, basins, colonnade and entrance houses retain their human dimensions.
The protected axis bands retain the central 165 m east–west and 214 m
north–south; the journeys around them shorten through the shared
`compact_landscape` operators.

## Geography and work

The west shoulder is a broad working slope below exposed northern cirques.
Three connected terrace streets give Stair Town fifteen full-size houses with
frontage, space at the backs and cart lanes. Eight outlying yards retain their
place names, with fewer houses and explicit road connections. The Lower
Terrace stands on the southern shoulder, clear of the ascending arrival track.
The Lens Works, Cistern Yard and Quarry Shelf have level working fronts. Cargo
stacks line the back of the North Quay, leaving the packet's aisle clear.

Spruce occupies sheltered drainage pockets below the tree line; open grazing
benches and streets remain quiet. The ordinary countryside has granite/turf
slopes. Marble belongs to formal courts; steep terrace edges expose rock.
The arrival track has a seven-metre graded cart bed, a broad earth shoulder
and a narrower, irregular worn surface.

Three meltwater runs descend into the lake. The final terrain is incised to
their downstream profiles. Road/water intersections generate surveyed masonry
bridges through the shared routecraft kit. The lake is clipped to the final
basin, including the full-size Ring island. Random decorative cliff falls
without catchments have been removed; the canal works retain their falls.

## Lore and gameplay

The Orrery, Lens Gate, Rose Gallery, Mirror Basins, canal terraces, aqueduct,
Stair Town, North Quay, South Watch and Ring keep their identities. The Ringing
Face retains the half-drawn blank and testing bell of Foreman Hesk's thread B.
The northern roads still leave through the two cols described in the lore;
the eastern mountain wall has no separate road cut.

All eight portal IDs remain: five exterior connections and the Lens Vault,
Mirror Cistern and Stair Cellars entrances on `mirrorhold_interiors`. Fourteen
exterior secrets and the interior Canal Cache retain their keys, contents and
destinations. Secret standing points are surveyed beside their visible props.
The authoritative NPC/resource/encounter roster is migrated by the same axis
survey; the manifest publishes the four civic service posts and clear roads.

The three resident-scene borders use the shared reciprocal registry:

| Border | Local seam anchor (x, y, z) | Outward |
|---|---|---|
| Whitehorn | -76.5, 85, -281.5 | 0, -1 |
| Amethyst | 10.5, 93, -281.5 | 0, -1 |
| Amberwood | -110.5, 24, 20.5 | -1, 0 |

## Reproduction and evidence

Run `source/rebuild_landscape.py` with Python from `source/`. It builds the
GLB, LOD2, collision and geometry minimap, then refines walking heights, opens
authored decks, stamps building footprints and rebuilds the secret package.
`--skip-build` reruns the corrections; `--skip-secrets` is useful during a
geometry-only iteration. No generated geometry is edited by hand.

`source/migrate_compact_server.py --server <checkout>` reports the one-time
coordinate migration without writing; integration calls its revision-guarded
`migrate(server, apply=True)` before the common continent/content generators.
`source/audit_access.py` checks local portal/interaction connectivity. It is an
authoring diagnostic; integrated server movement must also be walked.

The rollout artifact folder `work-output/northern-rollout/mirrorhold` contains
before/after survey input JSON, the actual gameplay-camera PNGs and telemetry,
the access audit, migration preview, build logs, and the real-server walk
fixture. The baseline uses the frozen original package through the same
runtime camera. The after survey uses the rebuilt package and new streaming
runtime. The Lens Works comparison follows the relocated working court;
camera distance and yaw remain the same. Extra views cover a Stair Town lane
and a meltwater bridge. The root integration report supplies authoritative
walk results and cross-border continuity results for the combined rollout.

Integration movement checks also exercise practical road length, because a
connected flood can hide a long detour between nearby services. The civic
bridge now meets a surveyed turning ramp; each meltwater bridge has an
excavated bed and a linear bank plane that continues through its feathered
ends. The eastern working road keeps the North Quay level before climbing
beyond its shore. One eastern home moved to the nearby stair-yard terrace.
The buried spare pier, obsolete through-road retaining wall, and buried
overlook rail have been removed without changing a named destination.
Thin retaining walls use their actual rotated collision footprints, and
only exposed bridge floors own walking-surface exemptions. The final review
includes the corresponding gameplay-camera comparisons and real World path
length tests for the civic streets, eastern road, ferry return, and quay aisle.

The southern shore road bends around the occupied South Watch and waystation,
then reaches the original Four Gates departure and watch-butts secret.
The Sanctuary deck has a localized bed cut where an adjacent yard previously
buried it; the watch entrance retains its ID and stands at the finished ground.
Final exact server folds pass 16 practical road-distance bounds and connect
all 146 served exterior destinations from the single main arrival `(93, 82)`.
The regional fixture includes 14 routes and 52 walking legs, including the
watch secret's entry, a room step and its return to Mirrorhold.
