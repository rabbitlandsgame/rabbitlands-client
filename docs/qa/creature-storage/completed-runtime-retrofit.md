# Completed creature delivery retrofit

The 205 remaining completed animation sets have full 30 Hz and zero-corrective review candidates. Together with the already accepted Crystalback Tortoise V2, the local approval browser contains 206 creatures. The original selected sets are frozen separately; 17 are newer local drafts and retain that status. Larger differences require visual review. Successful loading and measurement do not establish an appearance match.

| Raw GLB storage, 205 sets | Bytes | Decimal GB |
|---|---:|---:|
| Frozen selected references | 3,286,969,072 | 3.287 |
| Full 30 Hz animation candidates | 1,835,172,712 | 1.835 |
| Fixed mesh/skin candidates, including duration repair | 274,639,648 | 0.275 |

Sampling saves 1,451,796,360 bytes (44.2%). Removing the remaining corrective data in the review drafts saves a further 1,560,533,064 bytes; combined draft reduction is 91.6%. Of the 205 sets, 134 already have no corrective shapes, so their bake is an identical copy of their sampled candidate. The other 71 contain fitted mesh, skin and shading changes. These figures describe proposed visual compromises, not an approved install size.

All 205 sampled files have actual configured raw-client comparisons and fresh Blender checks. All 71 changed bakes have complete original-to-final client comparisons; the other 134 reuse the exact same sampled payload proof. Final Blender coverage consists of 201 new imports and 135 exact-byte proof reuses across the selected bake and close-match variants. One additional import covers the superseded Skeleton bake; its receipt is retained alongside the repaired version. Named native clips, off-grid states, directed switches, held endings, default/RESET and actor placement are checked. Errors remain explicitly recorded, including large outliers. This is sampled validation, not a continuous-time guarantee.

The Skeleton's Death_A bone curves contained only a time-zero pose. Its corrective curve supplied the 1.85-second ending; deleting that track shortened the clip. A separate versioned repair appends the exact held value to an existing node curve, adds 444 bytes, and preserves every original key/default. Both original files remain available. The large shape error of this bake remains unapproved.

On the same generic client protocol, 102 sampled candidates and 85 combined bake candidates have both smaller maximum and RMS **surface position** differences than the accepted tortoise reference comparison (31.691 mm maximum, 1.277 mm whole-surface RMS). These are separate from the tortoise's denser body-only 4,827-state fit measurements. Shading, contacts and visual review still matter; the tortoise's acceptance does not authorize a global tolerance.

Sampling alone retains the same corrective geometry: the summed per-creature native buffer inventories remain 2,098,406,780 bytes. The zero-corrective drafts remove those buffers. This sum is not simultaneous residency or a whole-game memory estimate. Ordinary skinning, textures and draw work remain. Fewer curve keys reduce stored/loaded animation data and lookup work; no whole-game CPU percentage or FPS gain is inferred. Creatures ship as ordinary uncompressed GLBs.

The four-bone Magpie pilot improved independent clip poses but increased transition error and added 72,972 bytes. It remains rejected and outside the approval catalog. See [the experiment receipt](helper-bone-pilot.json).

Run `godot-client/open-creature-optimization-review.bat` in the task checkout. Both models remain visible with synchronized cameras and playback. Left/right changes creature; up/down changes animation; Space approves the exact displayed version across all clips; T opens a comment window, Ctrl+Enter saves, and Escape cancels. Drag to orbit, wheel to zoom, and P to pause. A variant selector provides the 30 Hz, fixed-bake and qualified higher-rate controls. Decisions append to an ignored local journal bound to source/candidate hashes. The viewer never installs assets. Smoke tests use a separate test catalog and journal.

The [machine-readable receipt](completed-runtime-retrofit.json) records per-creature hashes, sizes and measured differences. Private intermediate data, original sources and review journals remain outside Git. Historical authoring observations remain unchanged. The separate runtime-delivery receipt identifies any conservative replacements; visual acceptance of the aggressive drafts remains pending.

## Conservative runtime selections

The task checkout installs 116 positive-saving close matches: 56 at 120 Hz and 60 at 240 Hz. Their raw files shrink from 907,506,872 to 423,528,540 bytes, saving **483,978,332 bytes**. Every measured maximum is at most 1 mm in position and 0.5 degrees in normal direction; static geometry, all skins/binds, corrective arrays, materials, clip behavior and placement are preserved. Fresh Blender checks also pass. This deliberately conservative delivery choice does not mark a creature artistically accepted.

All 17 newer local-only sets retain their prior state. Moss Bear and Leafwing Owl also remain unchanged: their qualified close versions save negative and zero raw bytes respectively. The 30 Hz and zero-corrective versions remain available in the reviewer, including for creatures with a closer higher-rate runtime selection.

The [runtime delivery registry](runtime-delivery.json) is the current hash/cadence record for these 116 assets. Active roster hashes, import cadence and animation-map optimization receipts were updated; previous statuses and historical physical witnesses were preserved. Historical family QA observations describe the frozen authoring versions and should not be silently regenerated or relaxed to fit a new delivery. Installation recovery copies and the full pre/post SHA transaction remain ignored locally. No push or release is included.
