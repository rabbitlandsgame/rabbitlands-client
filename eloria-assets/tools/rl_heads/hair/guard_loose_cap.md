# Independent RL scalp cap support

`guard_loose_cap.py --source <hair.glb> --out <fresh/hair.glb>` supports only
the hidden cap against the actual RL head, every identity shape and standard
mixed cases. `--extra-controls <controls.json>` adds a fitted character's actual
identity. The output remains unqualified until coverage, clothing, client pose
and appearance checks pass. Native seating is a separate later corrective.

Ordinary support retains all original UV, colour, skin, index and target
accessors. Only cap position/normal rows can change. Explicit
`--rebuild-from-profile <style.json>` restores the same cap topology from its
profile and directly binds its identity deltas to the RL skin, avoiding a broad
generic identity envelope. This also updates cap root colour and its identity
deltas; every painted-lock attribute and target remains exact. Profile hashes
and topology must match the source. Grooming on this cap remains zero.

Some lower nape rays leave the open head rim. The generator's nearest-surface
fallback can then raise the cap above the intended hairline. Optional
`--pin-profile-nape` restores low rear boundary rows to the profile's physical
ear-lobe-minus-nape height. It affects rear longitudes from 135 degrees and
blends through a 25mm neighborhood; forehead and higher ear roots stay exact.
It applies only within 25mm of that declared height, and never chooses a longer
nape setting. Actual head/body seating and full coverage still decide acceptance.

Keep original assets and intermediate stages. The report records hashes,
changed counts, displacements and preservation proofs; public asset metadata
contains semantic methods and hashes only.

## Explicit local cap footprint

`repair(..., edge_inset_override=None)` retains the original profile footprint by
default. An explicit scalar or periodic `[longitude, degrees]` table can rebuild
only the cap edge within eight degrees of the source hairline. The original
profile is still hash-validated and is never edited. Overrides are recorded in
the asset and receipt; cap identity rebinding, surface/coverage checks and later
Native fitting remain required. The command-line option is
`--cap-edge-inset-json`. This changes no painted exterior or declared hairline.
