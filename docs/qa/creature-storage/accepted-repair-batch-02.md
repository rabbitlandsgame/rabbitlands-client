# Accepted second-batch creature repairs

The user accepted the exact Autumn Bark Treant, Crystal Cave Spider, Storm Chimera and Ostrich review candidates. Four real saved reviewer approvals bind their source and candidate hashes; the accompanying current instruction explicitly excludes the Mossbound Stone Golem repair because its right thumb still follows the right leg.

Installation uses the separate [second-batch delivery registry](accepted-repair-delivery-batch02.json). The [first-batch registry](accepted-repair-delivery.json) remains unchanged. Earlier conservative/visual delivery rows retain their historical evidence and point to superseding selections where applicable.

| Creature | Previous runtime GLB bytes | Accepted GLB bytes |
| --- | ---: | ---: |
| Autumn Bark Treant | 1,927,172 | 1,927,176 |
| Crystal Cave Spider | 22,663,360 | 1,061,772 |
| Storm Chimera | 1,571,288 | 2,372,480 |
| Ostrich | 25,878,072 | 703,000 |
| **Total** | **52,039,892** | **6,064,428** |

The exact accepted files save **45,975,464 raw bytes**. They use ordinary uncompressed GLBs, at most 30 Hz animation sampling and zero corrective shapes. No new helper bones were added by these four local repairs. The selected newer Storm rig is nevertheless larger than its older installed predecessor: 153 versus 63 joints, with eight versus four stored influence slots. Its measured CPU component cost and allocation scope remain disclosed in [the benchmark](storm-chimera-component-benchmark.json).

Acceptance covers the known partial-repair limits recorded in [the batch review report](comment-repair-batch-02.md). It does not turn the approximate candidates into lossless replacements or erase the original authoring findings. Golem's rejected limb repair remains a separate private draft; its earlier accepted installed model is retained while a new thumb-specific candidate is prepared.

The installer validates exact approval events, final evidence hashes, active runtime predecessors, qualified metadata and full native clip inventories before writing. Recovery preserves original assets and metadata under the task worktree's ignored `.local`. Crystal/Ostrich retain existing animation-map behavior and placement. Storm receives an actor-specific copy of its actually reviewed generic map, retaining Walk/Run playback multipliers of 1.15/1.25 and its existing stride policy. The owning agent's different 1.0 playback rates and new stride fields are not promoted. Its literal attachment aliases come from the qualified selected-source registry, with unchanged appearance transforms. The shared generic map is unchanged. The generated receipt records the exact installed files and authorization.

Post-install verification checked all four exact installed hashes and confirmed the other 202 creature runtime files, including Golem, were unchanged. The current configured raw client passed 1,520 finite self-comparison states across all native clips, defaults, held endings and both first-tick/frame-stepped switches. Six new installer guard tests and six original installer regression tests passed. See [the scoped client-check receipt](accepted-repair-batch02-client-check.json); these checks do not establish new reference fidelity or GPU performance.

These changes are committed locally to the task branch. No further develop push or release is implied by this acceptance.
