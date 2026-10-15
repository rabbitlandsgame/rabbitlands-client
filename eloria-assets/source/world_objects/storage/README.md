# Ironbound oak storage chest

The owner approved concept A on 2026-10-11. `approved-concept.png` is the
image supplied to Meshy; `provenance.json` records the task, generation
settings, 15-credit cost, checksums and normalization.

The shipped model is `godot-client/assets/world/interactives/storage.glb`:
2,298 triangles with embedded 2k base colour, metallic/roughness and normal
textures. It is grounded at Y=0 and fits the existing 3x3 storage collision
body even with the client's random yaw and maximum 1.08 scale.

`IMPORTED_INTERACTIVES` in `eloria-assets/tools/imported_world_objects.py`
preserves the reviewed model when the world-object generator runs. The
stable `storage` model id and `Storage` role apply it to every storage DTO,
including Landfall, Greenlight, Hearthcroft, Stagheath and Tollholm. Tab maps,
minimaps and area previews retain the brown Storage dots from the legend.

Regenerate registry measurements with:

```powershell
python eloria-assets/tools/build_native_world_object_glbs.py
```

Validation: world-object model checks include byte-for-byte preservation
after regeneration, embedded textures and the storage collision footprint.
Godot placement, storage map markers and chunk regrounding checks passed.
The model and its brown dots were rendered and reviewed on all five maps.
