# Coherent posterior source fitting

Some reconstructed nape surfaces sit near the target neck's medial axis.
Nearest-normal fitting can put adjacent corners on opposite sides of the neck,
stretching a short source edge across its interior. Diagnose the raw,
neutralised, mapped, head-guard and body-guard stages separately before opting in.

The tied builder accepts this source-specific preparation option:

```json
"posterior_nape_fit": {
  "below_eye_mm": [135, 35],
  "half_width_mm": 75,
  "max_z_from_center_mm": -10,
  "rear_margin_mm": 6,
  "rear_sample_up_mm": 12,
  "max_shift_mm": 70,
  "feather_mm": 5
}
```

These example bounds describe one measured input; they are not universal hair
settings. The helper shoots full-skin rearward rays in that local region and
uses the actual posterior envelope. A bounded upward sampling band can find
the back wall above a curved open neck rim; front-facing hits are excluded.
It moves only depth, transports normals from the actual geometric change and
preserves topology and paint UVs. Missing posterior rays keep the source row.
The declared displacement bound fails closed. An absent option is an exact
no-op. This source-fitting limit does not alter any Native corrective limit.

Use `build_tied_reference.py prepare ...` or call
`shared.prepare(args, head_fit=build_tied_reference.prepare_head_fit)`.
The callback applies the coherent field before the ordinary head clearance
step. Its receipt records both displacements. The optional hook requires
`build_loose_reference.prepare(args, head_fit=None)`; its default path is
unchanged. The callback does not repair an inverse-identity tear that happened
before head fitting: qualify that stage separately.

Inspect the original source-edge lengths before and after every stage, then
recheck all physical High surfaces, all evaluated Native cases, scalp coverage,
budgets, grooming and actual client views. A successful source fit alone never
qualifies an asset.
