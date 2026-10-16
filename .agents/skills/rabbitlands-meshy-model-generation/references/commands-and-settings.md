# Commands and settings

The project client is `.local/asset-authoring/workspace/eloria-tools/meshy_gen.py`. Always inspect its current `--help`; this reference records the intended workflow, not an immutable API schema.

## Dry run

```powershell
python .local\asset-authoring\workspace\eloria-tools\meshy_gen.py .local\asset-authoring\workspace\concept_art\selected -R `
  -o .local\asset-authoring\workspace\generate_models\my_asset_batch_meshy `
  --pattern *.png --limit 1 `
  --model-type smart-topology --target-polycount 4000 `
  --texture-resolution 2k --pose none --dry-run
```

Start with one representative asset. A dry run does not submit it; run the same command without `--dry-run` after paid-task authorization, then review that downloaded pilot before removing `--limit 1`.

## Production creature batch

```powershell
python .local\asset-authoring\workspace\eloria-tools\meshy_gen.py .local\asset-authoring\workspace\concept_art\selected -R `
  -o .local\asset-authoring\workspace\generate_models\my_asset_batch_meshy `
  --pattern *.png -j 1 `
  --model-type smart-topology --target-polycount 4000 `
  --texture-resolution 2k --pose none --fbx
```

Use only after the user authorizes paid submission. Increase concurrency conservatively and within current Meshy rate limits.

## Resume and retry

- Resume an interrupted batch by re-running the identical command and output directory. The task ledger skips completed work and retains accepted task IDs.
- If polling times out or the client stops, inspect the ledger and query the recorded task. Do not submit another task merely because no result was returned during that process lifetime.
- A `SUCCEEDED` provider state still requires valid downloads and local validation; a terminal response can contain unusable or incomplete artifacts.
- Do not rename inputs midway through a batch; filenames provide stable ledger keys.
- Do not delete the output directory or ledger to solve a transient problem.
- Use `--retry-failed` only for a diagnosed terminal failure and within explicit paid-retry authorization. It creates a fresh task and can consume additional credits. After a repeated failure, stop and revise the input/settings or ask the user; do not loop paid retries.

## Setting guidance

- `--model-type smart-topology`: optimized production mesh; Meshy T2; target range 100–15,000 faces.
- `--target-polycount 4000`: established creature baseline, not a universal budget.
- `--texture-resolution 2k`: established base-color resolution.
- omit `--pbr`: established Eloria creature baseline uses base color only.
- `--pose none`: creatures and nonhumanoid props.
- `--pose a-pose` or `--pose t-pose`: only suitable humanoid inputs.
- `--rig`: Meshy's humanoid rig path; not the default for Eloria creatures and not compatible with the player-rig contract by itself.
- `--ultra`: costs more and is not automatically better for stylized, deliberately simplified forms.
- `--no-texture`: geometry-only diagnostic or deliberate later texturing workflow.

## High-detail fallback route

When the [hybrid routing guide](hybrid-production-routing.md) selects the hero/bake-down route, run a separately named high-detail pilot rather than changing the established Smart Topology batch in place. Inspect the current client help and Meshy API before choosing standard-generation fields; do not assume the direct-route settings produce a high-detail source. Preserve that source, then create later retopology, UV, and bake stages. A decimated file is not game-ready until silhouette, deformation topology, UVs, materials, baked maps, and Godot rendering have been reviewed.

Never put a key in a command that will be copied into documentation or committed. Use `MESHY_API_KEY` in the process environment (or `--api-key` for a single run); do not keep a key file in the checkout.
