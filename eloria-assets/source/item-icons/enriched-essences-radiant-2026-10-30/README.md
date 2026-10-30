# Enriched essences: selected radiant bursts

The selected Enriched Life Essence option 4 establishes the painted light burst
and two star glints around each essence. Seven separate built-in imagegen edits
extend that treatment to Fire, Water, Earth, Wind, Death, Magic and Frost. Each
preserves its previous essence body, silhouette and palette; the surrounding
burst uses the same school's colors. Life reuses the exact selected painting.

These 50×50 cells replace the previous enriched selection at image IDs 617–624
and item IDs 1950–1957. The original base and enriched paintings remain intact.
The atlas builder verifies each prior cell hash before applying a replacement,
so every other inventory cell stays unchanged.

`manifest.json` records the exact prompts, selected style-reference hash, input
and output hashes, dimensions, previous selection, stable item/image IDs and
visual review. Full-resolution inputs and outputs remain in the ignored local
authoring stage. Generated alpha is preserved through Lanczos downsampling;
the complete essence and effect fit within 44×44 pixels on the normal dark teal
backing, leaving the sampling perimeter clear.

Rebuild and verify from the client repository root:

```powershell
python eloria-assets/tools/build_item_icon_atlases.py
python eloria-assets/tools/build_item_icon_atlases.py --check
python godot-client/tests/test_item_icon_atlas.py
```
