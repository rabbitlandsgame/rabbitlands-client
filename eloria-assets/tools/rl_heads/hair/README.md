# RL hair and beard modules

Offline Python tools that turn hairstyle and beard *definitions* (JSON) into
game-ready, skinned, morphing GLB modules for the Rabbit Lands (RL) head. They
are deterministic: the same definition, seed and head build give the same asset.

## Files

| File | Purpose |
|---|---|
| `build_hair.py` | style JSON → `build/hair/<style>.glb` (+ `.report.json`). The style schema is in its docstring. |
| `build_beard.py` | beard JSON → `build/beards/<style>.glb` (+ report; `--chart` writes an authoring chart). Schema in its docstring. |
| `hairgen.py` | Library: head frame and hairline, root sampling, flow fields, guide-curve growth, shaping, and primitives (tube clumps, ribbons, cards, helical curls, braid, torus bun, scalp under-shell). Also the grooming curve rescale. |
| `headref.py` | The RL head module as a reference surface: binding, signed distance, ray casts, morph deltas. |
| `assemble.py` | Morph transfer, clearance checks, COLOR_0, and the GLB writer wrapper. |
| `rlglb.py`, `glbwriter.py` | Self-contained GLB reading and writing (numpy only). `glbwriter.py` is a vendored copy of the RL head build writer. |
| `textures.py` | Writes the three textures (see Provenance). |
| `preview.py` | Blender headless previews and concept-vs-render comparison sheets. |
| `validate.py` | Structural checks of the GLBs, plus the scalp coverage gate for hair modules. |
| `coverage.py` | Scalp coverage: ray casts from scalp samples to a sphere of view directions, with the runtime alpha test and hair_detail discard. |
| `godot/hair_coverage_shots.gd` | Back, crown and nape screenshots of an installed style in the real client actor (run with `-s` against a client checkout; writes only `RL_SHOT_DIR`). |
| `paths.py` | Locates every input. No machine-specific paths. |
| `styles/*.json`, `beards/*.json` | Starter definitions (`mira_bun`, `rowan_shag`; `full_beard`, `short_beard`, `moustache`, `goatee`). Each group carries a `_doc` note. |

## Inputs (ignored local files)

All inputs live under the RL head authoring area, `RL_HEADS_ROOT` (default:
`RL_HEADS_LOCAL`, else the repository's `.local/rl-heads`). None of them is committed.

- `build/v1/rl_head_<sex>.glb` and `.npz` — the RL head module build. Supplies the skin, morph targets, skeleton and skin weights.
- `blender_profile/extensions/user_default/mpfb/entities/socketobject/_extra_vertex_groups.py` — the MPFB2 scalp, ears and lips vertex-index lists. Override with `RL_MPFB_GROUPS`.
- `gen/hair_lock_v1.png` — source of the clump texture.
- `ref/*.png` — concept crops, used only for the comparison sheets.
- `<RL_WORKTREE>/godot-client/assets/actors/native/races/luminous_<sex>.glb` — the shipped body. Used by `preview.py` (context) and `validate.py` (the `hair_root` check). `RL_WORKTREE` defaults to two levels above `RL_HEADS_ROOT`.

Other environment variables: `BLENDER` (default: `blender` on PATH) and
`RL_GPU_LOCK` (an optional wrapper that serialises GPU renders on a shared
machine, run through `bash`).

Requirements: Python 3.11+ with numpy, scipy, trimesh (with rtree) and Pillow.
`preview.py` also needs Blender 5.x.

## Outputs

Everything is written under `RL_HEADS_ROOT/build/`:

- `hair/<style>.glb`, `hair/<style>.report.json`
- `beards/<style>.glb` and report, plus `beards/charts/`
- `hair/textures/{hair_strands,hair_clump}.png`, `beards/textures/beard.png`
- `hair/preview/...`, `beards/preview/...`

## Commands

```
python textures.py
python build_hair.py styles/rowan_shag.json male ../../build/hair/rowan_shag.glb      [--no-check] [--only g1,g2] [--embed-textures]
python build_beard.py beards/full_beard.json male ../../build/beards/full_beard.glb   [--chart chart.png] [--no-check]
python validate.py ../../build/hair/*.glb ../../build/beards/*.glb
python preview.py --sex male --asset ../../build/hair/rowan_shag.glb --name rowan_shag [--lod 1]
python preview.py ... --views back,back_tq_l,back_tq_r,top_back,low_back --detail-level 0 [--shapes hl_volume_n,hl_length_n | all_id_p]
python coverage.py ../../build/hair/rowan_shag.glb --sex male [--cases rest,hl_volume_n] [--map map.png] [--json out.json]
```

## Asset contract (summary)

- **Hair skeleton:** `hair_root`, whose rest global equals the body's `Head`, plus optional spring chains `lock_<k>_<j>` (j = 0 at the root). Vertices are in body model space; the inverse binds make rest coincide with that space.
- **Hair meshes:** `hair_lod0/1/2` with materials `rl_hair_clump` (clump texture) and `rl_hair_card` (strand atlas). UV v runs root (0) → tip (1).
- **Beards:** skinned to `spine_03`, `neck_01` and `Head` using the head module's inverse binds. Meshes `beard_lod0/1/2`, material `rl_beard`.
- **COLOR_0** (normalised u8):
  - R — per-lock random;
  - G — position along the lock (0 root … 1 tip);
  - B — ambient occlusion (0 deep … 1 outer);
  - A — hair_detail keep-level (see below).
- **Morph targets** (names in mesh `extras.targetNames`, POSITION only, sparse):
  - hair: every `id_*` head shape, plus the grooming shapes `hl_length_p`, `hl_length_n`, `hl_volume_p`, `hl_volume_n`;
  - beards: every `id_*` and `ex_*` head shape.
- **Extras:**
  - `asset.extras.rlHair`: springs, collisions (in `hair_root` space), tris, grooming, colour channels and `headSHA256`.
  - `asset.extras.rlBeard`: the same idea for beards.

### Grooming shapes (hair)

Weight 1 is the full effect; weight 0 is the authored hair.

- **`hl_length_p` / `_n`:** each lock is re-meshed along its own growth curve at +60% / −40% of its length, with roots pinned. Extensions continue the tip and droop toward gravity. Curls keep their helix per parameter, so ringlets stretch or compress.
  - Groups with `"groom": {"length": false}` (for example Mira's swept locks that end in the bun) keep their length.
- **`hl_volume_p` / `_n`:** each ring moves along the skin normal by +80% / −50% of its stand-off above a 4.5 mm hugging base. The effect ramps in from the root and is full from 45% of the lock length.
  - Flattening is capped per vertex by its clearance at rest, shortened and lengthened.
- **Clearance safety:**
  - Every grooming shape is pushed out to ≥ 2.6 mm against the rest skin.
  - It is also pushed out against the skin morphed by the all-`_p` and all-`_n` identity extremes, including the hair's own identity deltas.
- **Spring chains** keep their authored rest lengths. Extended tips stay weighted to the last joint, so they swing with it; shortened locks simply use fewer joints.

### hair_detail (COLOR_0.A): Sleek <-> Messy

The runtime shader discards a fragment when `A < 1 - level/100`, so a card with keep
value A becomes visible once the level exceeds `100 * (1 - A)`.

| Band | Contents | Visible from level |
|---|---|---|
| `A = 1` | Core geometry: shell, clumps, ribbons, bun, braid, curls, baby hairs | Always |
| `A = 0.5..0.95` | Authored fine detail: flyaway and wisp cards (`"detail": "fine"`, the card default) | 5..50; level 50 shows exactly the authored look |
| `A = 0.05..0.45` | Messy extras (`"detail": "messy"`): strays, crown and temple frizz, loose locks, separated tips | Fade in progressively over 55..95 |

- Below 50, the authored flyaways drop out progressively; 0 is sleek.
- Values are spread per card (deterministic, from the lock random).
- Beards and older assets carry `A = 1`.
- Messy groups use `avoid_eyes` (cut where they would enter a box in front of the eyes).
- Hanging messy groups use `spring_follow` (they borrow the nearest sprung lock's skin weights within 2.5 cm).
- `preview.py --detail-level L` (0..1) renders with the same discard rule; `--cpu` renders with Cycles on the CPU (no GPU, no GPU lock).

### Scalp coverage

`validate.py` runs `coverage.py` on every hair module (skip with `--no-coverage`).

- **Samples.** About 900 scalp points at least 4° (true angular distance) inside the hairline.
- **Views.** About 165 directions, elevation ≥ −30°.
- **Runtime model.** Rays use the runtime rules: double-sided surfaces, the alpha test at 0.5 against the texture, and the hair_detail discard.
- **Worst case.** The check runs at detail 0, where only core A = 1 geometry is drawn.
- **Hole.** A robust escaped ray (2 of 4 jittered rays escape too) that climbs 10 mm off the skin while still ≥ 6° inside the hairline. The viewer sees scalp through a gap in the hair.
- **Edge.** An escaped ray that runs out under the hairline edge, such as under the fringe, over an ear or up at the nape. These are reported only.
- **Gate.** The build fails on any hole at rest, under `hl_volume_n`, under `hl_length_n`, or under both, on any LOD.
- **Warnings.** `all_id_p`, `all_id_n` (alone and with both grooming shapes) and four random identity mixes are measured and reported as warnings.

Under-shell options (style `shell`) that keep the scalp covered:

- **Whole sectors.** `cols` is rounded to whole texture sectors. 40 columns over 12 sectors left a 36° wedge of scalp bare from the crown to the nape on LOD0. That wedge was the hole reported on 2026-10-28.
- **`face_clear`.** Raises the grid until the triangle faces, not only the vertices, keep that fraction of `offset_mm` off the skin (ears excluded, lift ≤ 4 mm). Coarse grids dipped up to 6 mm under the skin at LOD2.
- **`edge_inset`.** May be `[[lon, deg], ...]`, so the edge can sit under baby hairs at the front and past the hairline at the nape.
- **Seam vertices.** Duplicated seam vertices share their morph deltas, so the seams do not open under identity shapes.

## Provenance and licences

- **Textures:**
  - `hair_strands.png` and `beard.png` are fully procedural, generated by `textures.py` (our code, fixed seeds).
  - `hair_clump.png` is derived by `textures.py` from `gen/hair_lock_v1.png`: re-tiled, contrast-normalised, overlaid with procedural fine strands, and given procedural alpha.
  - `hair_lock_v1.png` was generated with gpt-image-bridge (Codex image generation through the owner's ChatGPT connection, authorised in the owner's brief) on 2026-10-27; its receipt (SHA-256, time, prompt, size) is in `../generated_textures.json`.
- **Geometry:**
  - All hair and beard geometry is generated procedurally by these scripts.
  - It is placed on and bound to the RL head module skin, which is derived from MPFB2 / MakeHuman hm08. The MakeHuman base mesh and targets are CC0 1.0.
  - The GLBs contain no MakeHuman mesh data. Their morph deltas are computed from the head module's shapes by surface binding.
  - At build time the tools read the scalp, ears and lips vertex-index lists from MPFB2's `_extra_vertex_groups.py`. MPFB2 is GPL-3.0; the file is read, not vendored.
- **Code:** project code. `glbwriter.py` is copied from the RL head build in this project.
