# The Coil Causeway

Ssarathi's seven-leg gauntlet is a processional water route beneath the temple,
kept as a hatchery between ceremonies. See [the comparison](references/comparison.jpg),
[layout coverage](coverage-map.md) and [assumptions](modeling-assumptions.md).

From nymara-regions, build with:

```sh
python _toolkit/gauntlets/build.py ssarathi_ruins
python interiors/ssarathi_gauntlet/source/views.py
```

The builder exports both client collision and server-collision/ssarathi_gauntlet.bin.
For an isolated repeat build, pass --out and --server-collision with temporary
paths. Exterior height-field correction passes must not reopen the gate cuts.

Use tools/sync_gauntlet_layout.py in the server worktree to refresh this existing
route, then sync each of ssarathi_gauntlet, ssarathi_gauntlet_2 and
ssarathi_gauntlet_3 with sync_authored_collision.py --region and regenerate the
ELM maps. [GAUNTLETS.md](../../GAUNTLETS.md) gives the full sequence.

Twenty repeatable views cover the approaches, gameplay cutaways and hatchery
details. Capture with _toolkit/godot_capture.gd, --environment=manifest,
gl_compatibility and opengl3. Review the PNGs before running
_toolkit/compress_captures.py from this package.
