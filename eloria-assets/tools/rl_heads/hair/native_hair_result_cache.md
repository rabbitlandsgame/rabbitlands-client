# Exact Native fixture result reuse

`native_hair_fixtures.check_hair(..., cache_results=True)` may reuse a numerical
result only when every consumed physical input is identical. Its key includes:

- The hair file SHA-256, LOD, effective identity/groom/Native-fit weights and
  both clearance and triangle-probe thresholds.
- The ordered collision-part names and complete NPZ source hashes, including
  positions, supplied normals and indices.
- Sex, exact mapped hair identity controls and the complete dictionary of named
  bind-to-pose bone deltas, including bones not used by the current hair.

Each requested record still rehashes its physical fixture sources before a
cache hit is allowed. Different filenames may share verified content; reordered
parts, changed normals, changed transforms or changed file bytes cannot share a
result. Case names and quality labels do not affect geometry and remain on
every emitted result.

The cache is local to one checker invocation. It stores the full original
numerical result, including the worst point, closest point and normal; no
geometry approximation, sign change, threshold change or case reduction occurs.
The normal early-failure behavior is retained. Reports include each source
signature and physical source hash, the number of evaluated/reused cases, and
the source case/quality/groom plus the reason for every reuse.

Use `cache_results=False` or CLI `--no-result-cache` for the full reference query
path. The synthetic tests compare every numerical field, verify changed pose
and normal inputs miss the cache, and prove a cached case still rejects a
changed physical source.

The actual-fixture parity run also compared complete neutral, combined-high
face controls and Walk50 cases on both fitted Buzzed variants at all three LODs
and all nine grooming states (162 emitted cases per sex), plus 54 cases on the
painted Twin Buns LOD2. Every numerical field, label, quality and worst witness
matched the uncached reference exactly. Duplicate verified cases accounted for
81/162 and27/54 results respectively; source/manifest hashes and timings remain
in ignored authoring evidence rather than the public repository.
