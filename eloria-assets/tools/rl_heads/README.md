# RL head authoring tools

The scripts that build the Rabbit Lands (RL) Human head modules, their hair,
beards and maps, fit the open headwear to them, and fit the head's controls to
reference busts. The game reads only their outputs
(`godot-client/assets/actors/native/rl_heads/`, `rl_head_textures/` and
`data/actors/rl_head_*.json`; see `godot-client/docs/rl-head-prototype.md`).

The tools are committed here. Their inputs and outputs stay in the ignored local
authoring area, `.local/rl-heads/` at the repository root (`RL_HEADS_LOCAL`),
which is never committed: MPFB data, the Blender profile with MPFB installed,
builds, lab renders, generated textures, references, evidence and Meshy task
ledgers.

## Layout

| Path | What |
|---|---|
| `paths.py` | Every location: repository-relative, or set by an environment variable (below). |
| `build_head.py`, `mh.py`, `mhmesh.py`, `place.py`, `gamebody.py`, `lods.py`, `glbw.py`, `landmarks.py` | The head module build: MakeHuman hm08 data in numpy, placement on the shipped skull, neck cut and zip, skinning, identity (`id_*`) and expression (`ex_*`) shapes, LODs, GLB writer. |
| `paint_head.py`, `paint_eye.py`, `hair_atlas.py`, `look.py` | The painted head, eye and strand maps; `look.py` composes a face as the runtime shader does, for previews. |
| `head_lab.py`, `macro_stack.py`, `make_spec.py`, `iterate.sh`, `compare.py`, `compare_godot.py`, `target_gallery.py`, `overlay_*.py`, `preview_*.py`, `lod_preview.py`, `expr_preview.py`, `eye_metrics.py`, `eye_style_lab.py`, `eye_style_fit.py`, `gallery_sheet.py`, `sheet.py`, `baseline_render.py`, `body_probe.py`, `glb_check.py`, `mpfb_smoke.py` | Likeness lab (Blender + MPFB), comparison sheets and checks. |
| `hair/` | Hair and beard modules (own README: definitions, grooming shapes, `hair_detail` keep levels, validation). |
| `headwear/` | Open-headwear audit and offline fit (`fit_all.sh` writes `godot-client/data/actors/rl_head_headwear_fit.json`). |
| `fit/` | Reference fitter: the 21 identity controls, colours, hair envelope and beard fitted to a Meshy bust (own README). |
| `meshy/` | Meshy multi-image-to-3D requests for fitter references, and their previews. |
| `godot/` | Godot measurement scripts (run with `--script <absolute path>`). |
| `specs/` | Build inputs: identity controls, brow styles, paint styles, reference landmarks, the likeness lab specs and the head build specs with their MPFB macro stacks. |
| `generated_textures.json` | Generation receipts of the authoring textures in `.local/rl-heads/gen/` (see Provenance). |
| `sync_from_local.py` | Re-copies the scripts from `.local/rl-heads/scripts/` with machine paths rewritten (refuses machine paths, secrets and empty files). |

## Environment

| Variable | Default | Used for |
|---|---|---|
| `RL_HEADS_LOCAL` | `<repo>/.local/rl-heads` | the authoring area (inputs and outputs) |
| `RL_HEADS_ROOT` | `RL_HEADS_LOCAL` | the hair tools' name for the same area |
| `RL_HEADS_REFERENCE` | `<local>/ref/studies/` | concept study renders the likeness sheets compare with |
| `BLENDER` | `blender` on PATH | Blender 5.x with MPFB 2 in the local profile |
| `GODOT` | `godot` on PATH | Godot 4.7 for the evidence and measurement renders |
| `RL_GPU_LOCK` | none | optional wrapper serialising GPU renders on a shared machine |
| `PYTHON` | `python` | the shell scripts' Python |
| `MESHY_API_KEY` | none | Meshy requests only; read from the environment, never printed or stored |

Requirements: Python 3.11+ with numpy, scipy, trimesh (rtree) and Pillow;
Blender 5.x for the lab, LODs and previews.

## Inputs (in `.local/rl-heads/`, never committed)

- `mpfb_ext/data/` and `blender_profile/` (MPFB 2 installed as a Blender
  extension, with the MakeHuman system assets): base mesh, targets, proxies.
- `lab/<name>/spec.json`: likeness lab specs (the shipped heads came from
  `lab/mira6` and `lab/rowan4`, copied to `specs/likeness_<sex>.json`).
- `gen/*.png`: generated authoring textures (receipts in `generated_textures.json`).
- `ref/`: reference landmarks and the concept study renders.
- The shipped bodies, `godot-client/assets/actors/native/races/luminous_<sex>.glb`,
  read from this repository.

## Outputs

- `build/v1/rl_head_<sex>.glb` (+ `.npz` and a build report): the head modules.
- `build/textures/`: the head maps (`head_<sex>_albedo.png`, `_features.png`, `_features2.png`, `_brows.png`) and `eye.png`.
- `build/hair/<style>.glb`, `build/beards/<style>.glb` (+ reports, textures, previews).
- `evidence/...`: lab sheets, headwear audit, fitter output.
- Generated directly into the repository: `godot-client/data/actors/rl_head_headwear_fit.json`
  (`headwear/fit_all.sh`, merge step).

A new build reaches the game only when its files are copied into
`godot-client/assets/actors/native/rl_heads/` (head, `hair/`, `beards/`) and
`rl_head_textures/` (maps with their committed `.import` settings). Then run
`tests/test_rl_head.gd`: it pins every hairstyle and beard to the head build they
were fitted to (`headSHA256`), and the identity bake, quality switch and
rendered checks in `godot-client/docs/rl-head-prototype.md` apply.

## Commands

Run from this folder (the build specs name their macro stacks relative to it).

```
# Likeness lab: Blender + MPFB renders of lab/<name>/spec.json, compared with the reference
bash iterate.sh <lab name> <character>
# Lab spec -> head build spec (MPFB macro stack via Blender)
python make_spec.py "$RL_HEADS_LOCAL/lab/<lab name>/spec.json" <sex> specs/<sex>_v1.json
# Head module: <local>/build/v1/rl_head_<sex>.glb (+ .npz, report)
python build_head.py specs/female_v1.json "$RL_HEADS_LOCAL/build/v1"
python build_head.py specs/male_v1.json "$RL_HEADS_LOCAL/build/v1"
# Head maps and eye
python paint_head.py "$RL_HEADS_LOCAL/build/v1" female specs/paint_female.json "$RL_HEADS_LOCAL/build/textures" --size 2048
python paint_eye.py "$RL_HEADS_LOCAL/build/textures/eye.png" 1024
# Hair and beards (see hair/README.md)
python hair/textures.py
python hair/build_hair.py hair/styles/rowan_shag.json male "$RL_HEADS_LOCAL/build/hair/rowan_shag.glb"
python hair/build_beard.py hair/beards/full_beard.json male "$RL_HEADS_LOCAL/build/beards/full_beard.glb"
python hair/validate.py "$RL_HEADS_LOCAL"/build/hair/*.glb "$RL_HEADS_LOCAL"/build/beards/*.glb
# Open headwear fit -> godot-client/data/actors/rl_head_headwear_fit.json
bash headwear/fit_all.sh
# Reference fitter (see fit/README.md)
python fit/fit_reference.py <reference.glb> --sex male --out "$RL_HEADS_LOCAL/evidence/fit/<name>"
# Meshy references: a dry run without --submit; paid runs need the owner's go-ahead
python meshy/meshy_multi.py --help
# Re-copy the scripts after editing them in .local/rl-heads/scripts
python sync_from_local.py
```

## Provenance and licences

- **MakeHuman system assets** (hm08 base mesh, targets, proxies, eyes, brows,
  lashes, teeth): CC0 1.0. The head modules' geometry, identity and expression
  shapes and proxies derive from them.
- **MPFB 2** (GPL-3.0): an authoring dependency only. The lab and `make_spec.py`
  run it inside Blender; `mh.py` reproduces its linear target and `.mhclo`
  proxy maths in numpy; the hair tools read MPFB's scalp, ear and lip
  vertex-group lists from the installed extension. No MPFB code is vendored here
  and nothing from MPFB ships with the game.
- **Generated textures**: `gen/hair_lock_v1.png` (source of the hair clump
  texture), `gen/iris_neutral_v1.png` and `gen/skin_brush_v1.png` were made with
  gpt-image-bridge (Codex image generation through the owner's ChatGPT
  connection, as the owner's brief authorised) on 2026-10-27. Their SHA-256,
  times, prompts and sizes are in `generated_textures.json`; the local files
  match those hashes.
- **Procedural textures and geometry**: the strand atlas, beard texture, hair and
  beard geometry, painted head masks and the eye are generated by this code.
- **Code**: project code. `hair/glbwriter.py` is a copy of the head build's writer.
