# The Resin Road

Amberwood's seven-leg gauntlet, authored as an abandoned charcoal and resin haul
route. See [the comparison](references/comparison.jpg), [layout coverage](coverage-map.md)
and [assumptions](modeling-assumptions.md).

From nymara-regions, build with:
```sh
python _toolkit/gauntlets/build.py amberwood
python interiors/amberwood_gauntlet/source/views.py
```

The builder exports both client collision and server-collision/amberwood_gauntlet.bin.
For an isolated repeat build, pass both --out and --server-collision with paths
in a temporary directory. Geometry corrections for exterior height fields must
not reopen this instance's gate cuts.

Server authoring follows GAUNTLETS.md. Use tools/sync_gauntlet_layout.py for
a layout refresh of an existing route. A layout-only refresh must preserve the
published wave definitions, keeper and exterior return berth: the full authoring
tool also rerolls waves and repositions other keepers. Update the arrival in
tools/generate_nymara_maps.py when the package origin changes, then sync each
of amberwood_gauntlet, amberwood_gauntlet_2 and amberwood_gauntlet_3 using
sync_authored_collision.py --region, and regenerate the ELM maps.

For final images, run _toolkit/godot_capture.gd with the package path,
--environment=manifest, gl_compatibility and opengl3. The camera index comes from
source/views.py; final captures live in references/godot-captures. Run
_toolkit/compress_captures.py from this package after reviewing the PNGs.
