# Evaluated native head and clothing checks

`native_hair_fixtures.py` consumes an ignored `npz-manifest.json` of independently
evaluated client surfaces. Each case includes the exact mapped hair identity
controls and native bone deltas in model space. The native skull perimeter is
fixed by `CharacterProportions.face_point`; the checker requires a v2-or-later
`native_fixed_skull` manifest with zero High-head identity weights. It applies
the hair's grooming targets before the pose. Named hair-root/spring descendants
follow Head; unknown joints fail instead of receiving a guessed transform.
An optional internal `hl_native_fit` shape is active at1 in native mode and0
under the High head. It separates local skull fitting from player grooming.
Assets without that shape keep their existing geometry and bake keys.

```text
python native_hair_fixtures.py <candidate.glb> --manifest <ignored/npz-manifest.json> --out <ignored/native-check.json>
```

The default measures all three LODs, all available matching cases, and nine
Length/Volume positions. It checks vertices plus triangle edge midpoints and
centroids where an edge is at least 5 mm long. These extra probes detect coarse
cap intersections that a vertex-only check can miss. The minimum remains 2 mm;
provided outward skin normals establish the sign independently of winding.
Manifest hashes and triangle-used vertex scope are checked before querying.

For a repair iteration, `--neutral-groom-only`, `--cases neutral` and
`--stop-on-first` allow a bounded diagnostic. An early failed scan explicitly
records that the requested scan was incomplete. It never establishes
qualification. Full RL identity/coverage checks, native scalp-coverage review,
client appearance and motion rendering, and equipment checks remain separate.
Native runtime mapping keeps hair on the fixed skull; High identity targets
remain active on the separate High head and its hair.
Keep fixture manifests, original captures and numeric evidence outside Git.

With the optional horizontal outside proof, only negative signed rows enter
the proof query. Positive distances and all closest-point/normal results stay
exact. Negative zero is included to preserve the reference sign bit. The
default bounds-only path and complete-fixture verification remain unchanged.
