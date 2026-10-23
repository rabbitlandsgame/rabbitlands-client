# Perk cape inventory icons

Ten painted cape icons occupy image IDs 607–616, in the order of
`eloria-assets/source/perk-capes/catalog.json`. Each matches that cape's cloth
colors and embroidered back emblem. These item pictures remain visible when
the local setting hides emblems on worn capes.

The selected 50 × 50 PNG cells and their hashes are recorded in `manifest.json`,
together with the exact generation prompt prefix, individual design prompts,
style references and review results. Full-size paintings remain in the ignored
asset-authoring workspace. Generated transparency was fitted inside 44 × 44
pixels and composited onto the existing dark teal inventory background.

From the client repository, rebuild the runtime atlas with:

```powershell
python eloria-assets/tools/build_item_icon_atlases.py
python eloria-assets/tools/build_item_icon_atlases.py --check
```

The existing image IDs 0–606 are preserved. The new pictures share `items25.png`
with the current quiver icons; no additional atlas or runtime override is needed.
