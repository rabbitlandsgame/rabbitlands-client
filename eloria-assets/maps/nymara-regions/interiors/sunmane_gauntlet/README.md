# The Red Canyon

Sunmane Steppe's seven-leg gauntlet follows a dry herd wash through open
sandstone cuts. See [the comparison](references/comparison.jpg),
[layout coverage](coverage-map.md) and [assumptions](modeling-assumptions.md).

From nymara-regions, build with:

```sh
python _toolkit/gauntlets/build.py sunmane_steppe
python interiors/sunmane_gauntlet/source/views.py
```

The builder exports client collision and server-collision/sunmane_gauntlet.bin.
For an isolated repeat build, pass --out and --server-collision with temporary
paths. Exterior height-field correction passes must not reopen the gate cuts.

Use tools/sync_gauntlet_layout.py in the server worktree to refresh this existing
route, then sync each of sunmane_gauntlet, sunmane_gauntlet_2 and
sunmane_gauntlet_3 with sync_authored_collision.py --region and regenerate
the ELM maps. [GAUNTLETS.md](../../GAUNTLETS.md) gives the full sequence.

Twenty-two views cover the preparation bay, wash, forks, court, ridge and
shelter details. Capture with _toolkit/godot_capture.gd,
--environment=manifest, gl_compatibility and opengl3. Review the PNGs before
running _toolkit/compress_captures.py from this package.
