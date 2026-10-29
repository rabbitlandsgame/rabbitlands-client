# Creature comment repairs: second review batch

The previously accepted Skeleton, Tengu, Giant Wasp, Heartwood Treant and Nightweave Spider repairs are installed in develop at `fff765386e0fa20427633ef8e17dced5261cea30`. The primary client checkout was fast-forwarded, its native-actor import guards prepared, and two settled editor-import passes completed without errors. Its project configuration was restored exactly and its tracked/untracked status was clean.

The following **new, unapproved drafts** are available for exact-version review. They have not replaced runtime assets or been pushed. All retain the full native animation inventory, at most 30 Hz sampling and zero corrective shapes. Sizes below are ordinary GLB bytes, without ZIP or RLCZ encoding.

| Creature | Active runtime bytes | Previously commented bake bytes | New repair bytes |
| --- | ---: | ---: | ---: |
| Mossbound Stone Golem | 1,896,812 | 1,896,812 | 1,896,812 |
| Autumn Bark Treant | 1,927,172 | 1,927,172 | 1,927,176 |
| Crystal Cave Spider | 22,663,360 | 1,061,472 | 1,061,772 |
| Storm Chimera | 1,571,288 | 2,372,480 | 2,372,480 |
| Ostrich | 25,878,072 | 703,000 | 703,000 |

Together the five candidates occupy 7,961,240 bytes, 304 bytes more than their commented bake baselines. Compared with the five active runtime models' 53,936,704 bytes, installing these exact candidates would save 45,975,464 bytes, subject to review.

For the spider, chimera and ostrich, the previously commented compact bake was never installed. It is the reviewer's comparison baseline; the active runtime model is recorded separately. The golem and autumn treant baselines are their already accepted, installed bakes. Actual client placement, overhead and selection metadata were checked against active runtime models.

## Repairs and limits

- **Golem:** a bounded skin edit improves the reported arm/leg contour without new bones or bytes. This is partial: the reported local edge stretch improves from 3.060 to 2.559 times, while the affected region's worst other pose rises from 4.096 to 4.238 times. Unchanged vertices and original bone transforms remain exact. See [the repair receipt](mossbound-stone-golem-limb-repair.json).
- **Autumn treant:** lowers the raised Walk arm using one existing quaternion curve. All six other actions, physical feet and original leg transforms remain exact; the measured canopy movement is at most 13.406 mm in the actual client. This changes arm carriage, rather than reauthoring the gait. See [the repair receipt](autumn-bark-treant-walk-repair.json).
- **Crystal spider:** restores whole rigid leg-piece ownership using existing bones. The source-like attachments improve substantially over the distorted bake. The Death-to-live transition can still extend 76.30 mm below its inherited stance plane; that plane is not a certificate of game-ground clearance. See [the repair receipt](crystal-cave-spider-rigid-repair.json).
- **Storm chimera:** restores original default contours for 27 complete mane strands and assigns each an existing anatomical owner. It reduces strand distortion, but original gaps between open hair cards remain. Source-position RMS improves while the maximum normal error increases slightly. This is a partial repair. See [the repair receipt](storm-chimera-mane-repair.json).
- **Ostrich:** a small skin-only edit moderately improves the reported attack knee shear, with residual narrowing during attack, Jog and Death. A two-control alternative was rejected because its lower aggregate numeric error produced a sharper visible knee kink. The offered version adds no bytes, bones or draw surfaces. See [the repair receipt](ostrich-left-leg-repair.json).

Storm's selected authoring rig already contains 153 bones and eight stored influence slots, compared with the older installed model's 63 bones and four slots. The repair adds no bones to that selected rig, but installing it would add 801,192 raw bytes compared with the active model. A scoped CPU measurement found warm animation advance plus forced bone updates rose from 20.95 to 52.71 microseconds for Walk and 22.71 to 51.24 microseconds for Jog. Retained static first-actor Godot allocations increased by 5,833,378 bytes. These measurements include shared caches and are neither per-instance RAM nor whole-game FPS estimates. See [the benchmark and its scope](storm-chimera-component-benchmark.json).

## Validation and review

The candidates have hash-bound structural, full-native-clip numeric client and fresh Blender load/finite-pose evidence. Client checks include defaults, held endings, first-tick switches and established outgoing poses followed by frame-stepped transitions. Training metrics are kept separate from independent validation.

Golem and Autumn have multi-angle PBR captures over all native cycles; Crystal has full-cycle, attachment and transition views. Storm has seven native-clip stills, targeted opposing head views and a complete tracked Walk cycle. Ostrich has seven fully framed native-clip stills plus targeted multi-angle attack/Jog/Death/default views; it does not have seven full-cycle PBR movies. Preserved older capture captions with incorrect Storm byte counts or rejected Ostrich helper costs are explicitly corrected in the final handoffs; exact payload hashes and structural receipts identify the offered files.

The local reviewer contains only these five new candidates, in the order above. Left/right changes creature; up/down changes animation; Space records approval of the exact displayed candidate across all clips; T opens comments. Drag orbits, the wheel zooms, P pauses and the commented-pose button jumps to the reported issue. The journal is append-only, and test smoke runs use isolated test journals.

Seventeen additional commented creatures remain after this five-creature review batch. Acceptance and installation are separate from preparing these drafts.
