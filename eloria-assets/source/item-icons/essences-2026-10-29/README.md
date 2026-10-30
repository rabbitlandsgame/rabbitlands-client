# Essence inventory paintings

Eleven individually generated, hand-painted essence icons replace the former
distillate illustrations in their existing image slots: Frost at 74, followed
by Life, Fire, Water, Earth, Matter, Air, Death, Energy, Spirit and Magic at
584–593. Item IDs, spell costs, recipes and pouch references retain their
existing numeric identities.

The artwork follows Rabbit Lands' broad, chunky painted forms. Each school
has a condensed magical droplet or wisp, with a distinct palette and silhouette.
The 50×50 cells preserve generated transparency during Lanczos resizing before
compositing over the standard opaque dark teal backing. The subject fits inside
44×44 pixels, leaving the sampling-grid perimeter clear of artwork.

Generation used the built-in imagegen tool. `manifest.json` records the exact
shared prompt and each individual design prompt, original image dimensions and
hashes, prior cell hashes, current source hashes and visual review verdicts.
Full-resolution authoring images and review evidence stay in the task's ignored
local authoring stage.

Rebuild from the client repository root:

```powershell
python eloria-assets/tools/build_item_icon_atlases.py
python eloria-assets/tools/build_item_icon_atlases.py --check
python godot-client/tests/test_item_icon_atlas.py
```

The builder verifies each original painting and replacement hash. It preserves
the original approved painting sheet and changes only these eleven cells in
`items3.png` and `items24.png`.
