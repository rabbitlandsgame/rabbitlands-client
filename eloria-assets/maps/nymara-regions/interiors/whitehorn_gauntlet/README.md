# The Ice Stair

Whitehorn's seven-leg gauntlet, arranged as a silver mine being closed by the
glacier. See [the comparison](references/comparison.jpg),
[layout coverage](coverage-map.md) and [assumptions](modeling-assumptions.md).

From nymara-regions, build with:

```sh
python _toolkit/gauntlets/build.py whitehorn_range
python interiors/whitehorn_gauntlet/source/views.py
```

The builder exports both client collision and server-collision/whitehorn_gauntlet.bin.
For an isolated repeat build, pass both --out and --server-collision with paths
in a temporary directory. Exterior height-field correction passes must not
reopen the sealed gate cuts.

Use the layout refresh in [GAUNTLETS.md](../../GAUNTLETS.md) to update the client
registry and existing server instance coordinates without rerolling encounters.
Sync collision for whitehorn_gauntlet and its _2 and _3 copies, then generate
the ELM maps.

Final captures use _toolkit/godot_capture.gd with --environment=manifest,
gl_compatibility and opengl3. The camera index comes from source/views.py.
Review the PNGs before running _toolkit/compress_captures.py from this package.
The eighteen final views include eye-level approaches and gameplay cutaways.
