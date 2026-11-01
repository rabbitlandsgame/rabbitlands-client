# Native-only ribbon inheritance

After the painted core has a qualified `hl_native_fit`,
`inherit_native_detail_roots.py` transfers that corrective to each fine-ribbon
column using exact parent-triangle barycentrics. It absorbs the existing small
High root offset into Native only. Every High attribute, identity/groom/tie
shape, index, default weight, skin and scene accessor stays exact; the core's
Native corrective also stays exact. Existing Native ribbon targets are replaced.

Parents must be non-cap, nondegenerate core faces with root coverage at least
0.55. Each indexed ribbon must have two roots with matching parent skin binds.
The default source-root distance ceiling is 0.5 mm and inherited fine correction
ceiling is 14 mm. Far roots, unindexed detail rows or mismatched skin fail before
output. Keep the authoring input and private root-binding receipt.

```
python inherit_native_detail_roots.py --source PRIVATE/core-fitted/style_male.glb \
  --out PRIVATE/native-rooted/style_male.glb --report PRIVATE/root-bindings.json
```

Public extras contain only safe hashes. The canonical full-array Native POSITION
and NORMAL digest is refreshed, including signed-zero bytes. The receipt records
the exact roots, triangles, barycentrics and original offsets. This step does not
qualify free tips, posed clearance, scalp coverage or appearance; retain the
independent final gates. No generation, upload or runtime registration occurs.
