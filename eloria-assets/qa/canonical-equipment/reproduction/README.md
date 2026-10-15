# Build evidence

These files preserve the exact orchestration used for the staged candidates.
They reference the original scratch directories and are retained for hash
provenance. The older torso build used sixteen workers before the later
request to limit CPU use. Subsequent work uses the same eight-core affinity
mask and no more than eight workers.

For a fresh build, follow `../../canonical-equipment-refit.md` and use the
current tools directly with `--jobs 8`. No historical compatibility exception
is needed for that path. `pack_canonical_equipment.py` installs only validated
scratch outputs and checks the destination hashes before replacing each file.

The source inputs and approved race bodies are unchanged. The complete-set
`.blend` files in the adjacent `blender` folder contain packed textures.
