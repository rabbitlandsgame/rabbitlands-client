# Compact a completed hair asset

Append-only authoring retains previous geometry and image payloads for private
recovery. Before packaging, `compact_hair_glb.py` removes unreferenced accessors
and buffer views from the generated RL hair graph. Keep the authoring file.

The tool copies every live view byte exactly, including embedded images, skin
bind matrices, sparse morph data, normalised colours and weights. It remaps
references without resampling, welding, recomputing normals or re-encoding
textures. It verifies all live decoded accessors and raw view bytes. All scene,
material, spring and default shape metadata are retained.

The input must be a known, single-buffer RL hair GLB with embedded images and
no animation or glTF extensions. Unsupported graphs fail before output. The
new output must have the same basename in a separate directory; its companion
PNG is copied unchanged when present. Safe source/tool hashes are added to the
public asset; write the detailed receipt only to ignored/private evidence.

```
python compact_hair_glb.py --source PRIVATE/authoring/style_female.glb \
  --out PRIVATE/package/style_female.glb --report PRIVATE/compact-receipt.json
```

Compaction does not qualify a model. Existing geometry, coverage, pose and
appearance evidence remains reusable only after the exact live-payload proof;
the final packaged file still needs its structural/runtime resource checks.
