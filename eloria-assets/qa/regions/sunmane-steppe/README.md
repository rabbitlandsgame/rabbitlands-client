# Sunmane Steppe regional QA

Sunmane Steppe follows the concept's broad caravan grassland: four Orun clan
camps surround a shared seasonal market and ceremonial crossroads, with
caravanserais guarding the travel axes and windmills, wells, animal pens, banner
shrines and burial mounds establishing the wider pastoral landscape.

The region is now a production Godot-native package rather than a converted
starter. Terrain, coastline, mesas, the fortified encampment, the modular
architecture kit, props, vegetation and the PBR material set are authored for
this region; the earlier pass carried landmark silhouettes named for other
Nymara regions and no authored buildings.

The layout includes twelve round tents, four market structures, eight banner
shrines, four caravanserais, six windmills, four wells, six animal pens and six
burial mounds, plus the central hall, four gate bays, wall towers, remote
outposts, two standing-stone circles, a cove landing and eight satellite
outrider camps. Eight warm landmark lights supplement the four transition
lights. Six terrain classes separate clan clearings, open steppe, caravan roads,
dry grass, shore rock and beach sand while preserving the clear `(58,58)`
arrival datum.

## Building and validating

```sh
python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/build_sunmane.py
python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/build_sunmane.py --lod 2
python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/creatures.py
python3 eloria-assets/maps/nymara-regions/sunmane_steppe/source/validate_package.py
python3 eloria-assets/tools/check_provenance.py
```

## Client verification

```sh
godot --headless --path godot-client --script res://tests/integration/sunmane_grounding.gd
xvfb-run -a godot --display-driver x11 --audio-driver Dummy \
  --rendering-method gl_compatibility --path godot-client \
  --script res://tests/integration/rendered_sunmane_steppe.gd
xvfb-run -a godot --display-driver x11 --audio-driver Dummy \
  --rendering-method gl_compatibility --path godot-client \
  --script res://tests/integration/sunmane_minimap.gd
xvfb-run -a godot --display-driver x11 --audio-driver Dummy \
  --rendering-method gl_compatibility --path godot-client \
  --script res://tests/integration/sunmane_performance.gd
```

Validation asserts the exact landmark counts, self-contained glTF structure,
node-name uniqueness, that every declared collision and landmark node exists,
the coordinate and minimap transforms, and that no other region's landmark
names remain. Grounding is verified by raycasting the navigation-surface layer
across the whole region on a 4 m grid: 2809 of 2809 columns ground, with zero
misses.

Shaded client captures are no longer pending. Twenty-one framings plus four
golden-hour variants are rendered from the running Godot client and paired with
the concept references in
`eloria-assets/maps/nymara-regions/sunmane_steppe/comparison/`. The remaining
gap is a live server session: `eloria-server` was not reachable from the
workspace, so the real login flow was not exercised. See
`maps/nymara-regions/sunmane_steppe/validation-report.md`.
