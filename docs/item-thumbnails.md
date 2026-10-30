# Rabbit Lands item thumbnails

The approved 599-cell painting sheet and per-item provenance are in `eloria-assets/source/item-icons/painted-2026-10-18/`. Rebuild with `python eloria-assets/tools/build_item_icon_atlases.py`; `--check` verifies the runtime pixels without writing. This public rebuild needs no private models, server checkout, rendered equipment screenshots or procedural bottle painters.

Equipment icons reuse the original equipment concept paintings, including the torso design cells and sabatons extracted from their original legwear paintings. Potions use selected existing painted bottle concepts. Ten essences and five crops have individual new paintings. Item image IDs remain unchanged; obsolete spear-to-shield and ringblade-to-cape substitutions are removed. Directional equipment faces left, with long weapons pointing upper-left; neutral frontal items keep their view. Worn mirroring and its warning mark remain status cues.

The cells have plain dark backgrounds and no decorative gold corners. Inventory and equipment buttons leave four logical pixels inside their grid borders in every state, and display the complete artwork without the former eight-pixel crop. The audit and rendered comparison are in `docs/qa/item-thumbnails-2026-10-18/`.

Full-resolution inputs, selection plans and processing stages remain ignored under `.local/asset-authoring/working/item-icon-audit/`. `prepare_painted_item_icons.py` reads that local source plan and records input hashes, extraction, orientation and generated-image prompts in the compact public manifest. Its extracted-image cache checks input hashes before reuse. The compact approved painting sheet is authoritative for routine atlas packing.

The eleven selected [essence paintings](../eloria-assets/source/item-icons/essences-2026-10-29/README.md) replace Frost's cell 74 and the ten school cells 584–593. They depict condensed elemental magic with distinct silhouettes and palettes. The atlas builder verifies each replacement against the original cell hash before packing it; the original painting sheet, all other cells and the numeric item/image IDs remain unchanged. Exact prompts, generated-source hashes and selection notes accompany the new cells in their manifest.

The [consolidated essence families](essences.md) use eight of those base paintings;
Wind keeps the Air artwork. Eight [enriched variants](../eloria-assets/source/item-icons/enriched-essences-2026-10-30/README.md)
extend the ledger at 617–624 with brighter cores and luminous highlights. They
pack into the unused tail of `items25.png`, preserving all existing artwork.
