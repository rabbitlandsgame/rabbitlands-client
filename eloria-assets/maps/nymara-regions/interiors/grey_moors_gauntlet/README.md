# The Barrow Run

Grey Moors' seven-leg gauntlet follows a family visitation road through linked
burial chambers beneath the peat. See [the comparison](references/comparison.jpg),
[layout coverage](coverage-map.md) and [assumptions](modeling-assumptions.md).

From nymara-regions, build with:

```sh
python _toolkit/gauntlets/build.py grey_moors
python interiors/grey_moors_gauntlet/source/views.py
```

The builder exports client collision and server-collision/grey_moors_gauntlet.bin.
For an isolated repeat build, pass --out and --server-collision with temporary
paths. Exterior height-field correction passes must not reopen the gate cuts.

Use tools/sync_gauntlet_layout.py in the server worktree to refresh this existing
route, then sync each of grey_moors_gauntlet, grey_moors_gauntlet_2 and
grey_moors_gauntlet_3 with sync_authored_collision.py --region and regenerate
the ELM maps. [GAUNTLETS.md](../../GAUNTLETS.md) gives the full sequence.

Twenty views cover the arrival, chambers, fork, court and burial and crossing
details. Capture with _toolkit/godot_capture.gd, --environment=manifest,
gl_compatibility and opengl3. Review the PNGs before running
_toolkit/compress_captures.py from this package.
