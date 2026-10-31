# Native hair corrective writer

`append_native_fit.append_native_fit(source, output, deltas, provenance=None)`
appends `hl_native_fit` to a frozen hair module. `deltas` is keyed by
`(mesh_name, primitive_index)`; each value has `POSITION: Nx3` and optionally
`NORMAL: Nx3`. Missing normal deltas are transported from the geometric change.
Omitted primitives receive zero deltas. Existing target counts, including a
style's extra grooming shapes, remain unrestricted.

The writer preserves every old accessor, buffer view, blob byte, attribute,
index and target reference. Existing mesh/node weight prefixes stay exact;
the corrective defaults to zero. It copies an adjacent same-name atlas without
changing it. It does not fit points, repair topology or register a hairstyle.
All supplied deltas must already use the source's bind coordinates.

The CLI takes an NPZ with `m0_p0_POSITION`, optional `m0_p0_NORMAL`, and so on:

```text
python append_native_fit.py --source <hair.glb> --deltas <native-deltas.npz> --out <fresh/hair.glb>
```

Output must have the same basename in a fresh authoring folder. Keep outputs
and reports ignored until all RL and evaluated Native checks pass. Public GLB
extras contain safe source/delta/tool hashes only; supplied provenance remains
in the private `.native-fit.json` receipt. A written corrective stays unqualified.
