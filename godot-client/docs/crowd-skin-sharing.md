# Crowd Skin Sharing Results

This record covers exact-content rebound `Skin` interning on the 300-actor mixed workload: 150 visible actors, 100 active actors, native presentation `All`, affinity mask 15. The production renderer and schedule were unchanged.

The structural result is exact: actor-level Skin identities fall from **1,500 to 450**, bind entries across those identities from **115,500 to 34,650**, and global Skin identities from **19 to 3**. Mesh instances remain **1,500**.

The measured baseline is `c7463ece20ac36b075962b39092f2bccbcb56753`; the candidate is `01e9af09cf0296bef44c1973c7e82dce1fb81784`. Only the actor's finalized-Skin interning call differs in the reversal. The helper uses the complete ordered bind names, indices, and exact transforms as its key; returned resources are immutable, while meshes and materials remain independent.

Work continues on `perf/native-crowd-300-benchmark` in `C:/rabbitlands/rabbitlands-client`. The original study started from fetched develop `05596ec5cfb3c3a363b55973dbe8611af42eecbb`. The previous stage was merged and pushed at the user's request as `0bf6c96bc09aba578b2bd54877a8940c2964f4a6`; this continuation stays on the task branch. The primary checkout and its local develop remain at `349600742f6cd7646ccbe28eb31d33bf2809a2e8`.

## ABBAAB acceptance sessions

Times below are milliseconds. Official Godot 4.7.2 runs were serial, with every task process pinned to logical processors 0-3. Hardware was an Ultra 9 275HX, RTX 5080 Laptop, and 31.38 GiB RAM; these are not mid-range certification results. Windowed wall timings include compositor pacing. The exact interference label is `shared host; unrelated Godot jobs authorized; activity not continuously monitored`.

| Session | Variant | Run | Wall mean | p95 | p99 | max | frames |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Headless/gl_compatibility | baseline (A) | 1 | 24.841 | 43.624 | 48.903 | 55.335 | 201 |
| Headless/gl_compatibility | optimized (B) | 2 | 22.451 | 40.293 | 51.909 | 56.048 | 222 |
| Headless/gl_compatibility | optimized (B) | 3 | 20.378 | 35.542 | 44.585 | 46.215 | 245 |
| Headless/gl_compatibility | baseline (A) | 4 | 23.595 | 41.259 | 50.949 | 54.083 | 212 |
| Headless/gl_compatibility | baseline (A) | 5 | 18.051 | 30.425 | 35.858 | 37.528 | 277 |
| Headless/gl_compatibility | optimized (B) | 6 | 19.479 | 35.129 | 41.969 | 42.656 | 256 |
| Windowed/forward_plus | baseline (A) | 1 | 50.723 | 71.074 | 89.541 | 89.541 | 99 |
| Windowed/forward_plus | optimized (B) | 2 | 45.964 | 72.690 | 83.577 | 88.247 | 109 |
| Windowed/forward_plus | optimized (B) | 3 | 39.798 | 59.205 | 76.132 | 96.323 | 126 |
| Windowed/forward_plus | baseline (A) | 4 | 53.759 | 90.627 | 101.671 | 101.671 | 93 |
| Windowed/forward_plus | baseline (A) | 5 | 42.800 | 67.187 | 70.007 | 81.223 | 117 |
| Windowed/forward_plus | optimized (B) | 6 | 41.121 | 63.712 | 79.913 | 83.470 | 122 |

The [portable evidence JSON](benchmarks/crowd-skin-sharing-results-2026-09-19.json) preserves complete hashes, paths, summaries, and attestations. All 12 runs were clean, report/schema-valid, hash-matched, process-verified, and affinity-15. Median of the three run summaries per variant is descriptive only:

| Renderer | Baseline mean/p95/p99/max | Candidate mean/p95/p99/max |
| --- | --- | --- |
| Headless/gl_compatibility | 23.595 / 41.259 / 48.903 / 54.083 ms | 20.378 / 35.542 / 44.585 / 46.215 ms |
| Windowed/forward_plus | 50.723 / 71.074 / 89.541 / 89.541 ms | 41.121 / 63.712 / 79.913 / 88.247 ms |

Shared-host interference means these rows do not establish stable FPS or an exclusive-host causal delta. The 16.67 ms target remains unmet.

## Engine profile component evidence

| Renderer | `update_skins` baseline -> candidate | Fall | Total skeleton baseline -> candidate |
| --- | ---: | ---: | ---: |
| Compatibility headless | 0.918 -> 0.403 ms | 56.2% | 7.956 -> 7.326 ms |
| Forward+ windowed | 1.299 -> 0.529 ms | 59.3% | 9.332 -> 7.776 ms |

The [engine profile report](crowd-engine-profile.md) records one captured window per variant and renderer using the same instrumented engine; timings are wall spans that can include preemption and waits. The profiler baseline predates the unused helper and manifest additions in the official reversal baseline. Production scheduling is identical. Both traces retain 150 `update_skins` calls and 300 skeleton notifications per frame. See [headless details](../test-artifacts/engine-profile/captures/20260919T180754135Z-headless-gl_compatibility/steady-zone-summary.json) and [Forward+ details](../test-artifacts/engine-profile/captures/20260919T180930579Z-windowed-forward_plus/steady-zone-summary.json). Nested inclusive zones are not additive; no total-frame/FPS gain is claimed.

## Parity and bounded visual evidence

- [Cross-rig comparison](../test-artifacts/skin-pool/parity-comparison.json) is exact ignoring phase for 20 snapshots across four rigs and five states.

- Accepted [baseline-v3 checks](../test-artifacts/presentation-checks/skin-pool-baseline-v3-gl_compatibility-20260919T175731178Z/checks.json) and [candidate checks](../test-artifacts/presentation-checks/skin-pool-candidate-gl_compatibility-20260919T175828349Z/checks.json) passed; candidate checks include all body-template fit profiles and the crowd contract.

- [Synthetic contract](../tests/test_rebound_skin_pool.gd) covers exact identity sharing, altered bind content rejection, adjacent float32 pose distinction, null rejection, and input immutability.

- [Bounded renderer validation](../test-artifacts/skin-pool/renderer-parity-validation-2026-09-19.json) reports byte-identical same-renderer candidate PNGs and six shader/material controls passing at max RGB delta 1/255. Scope is native presentation 0, static cloth, and particles off; no FPS/general renderer claim.

The parity fixture freezes only CapeCloth, uses manual AnimationPlayer seek/pause at idle 0.37 seconds, and records ordered binds, materials, visibility, and posed vertices at a deterministic non-rest pose.

## Remaining work

The retained change removes exact duplicate bind data with an observed 0.52-0.77 ms reduction in the direct skin-update zone. The next measured targets are cape cloth (2.77 ms inclusive in the baseline headless profile), combat pose callbacks (2.09 ms), and AnimationMixer processing (3.73 ms). Profile bone reads and pose application around those callbacks before expanding native ownership; preserve actor identity, one-shots, and animation cadence. These nested figures must not be added together. Shipping renderer behavior remains unchanged.
