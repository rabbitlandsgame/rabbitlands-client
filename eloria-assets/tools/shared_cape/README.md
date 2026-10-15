# Shared cape: provenance and rebuild

Every cape item in the game (all 29 cape visuals, equipment ids 2:10 and
2:100-105 included) uses one mesh: `godot-client/assets/actors/native/equipment/generic_cape.glb`.
Each item colours it through `tint` in `equipment.json`:

- The mesh has three materials, `Cape Base` (the cloth), `Cape Trim` (the woven border) and `Cape Detail` (the lining).
- All three read one greyscale texture and one normal map.
- The cloth and trim are double-sided. The lining is single-sided and faces the body (see Traps).
- The client multiplies each material by `tint[0]`, `tint[1]` and `tint[2]` (matched by the material-name suffix).

For a new look, give a cape item a new tint. To paint pattern or emblem detail
into the cape, change the shared texture.

## Sources (outside the repo)

All sources are in `generate_models/human_bodies_2026-10/`:

- `meshy_capes/cape_back.glb`: the Meshy delivery (image-to-3D from a gpt-image concept of a back-view cape on a mannequin).
- `cape/cape_grey.png`: the greyscale texture `cape_texture.py` made from the Meshy paint.
- `cape/cape_mesh.npz`: the finished Blender mesh dump that `build_shared_cape.py` packs.

## Rebuild

These scripts run inside a live Blender that has the Blender MCP add-on
(socket `localhost:9876`). `blender_socket.py` sends a file and defines `SCR`
as this folder's path first, so the scripts find one another.

1. `python blender_socket.py scene_setup.py`
   Imports the animation library, the old and new Human bodies, the raw
   Meshy cape and the old generic cape (the clearance reference), and makes
   the `NC Cape *` materials. It expects `SCR/old/` to hold the develop-era
   `luminous_male.glb`, `luminous_female.glb` and `generic_cape.glb`, plus
   `SCR/cape_grey.png`. Edit the paths at its top for your checkout.
2. `python blender_socket.py cape_pipeline.py`
   Turns the raw Meshy cape into `NC_cape` on the canonical rig. The steps:
   1. Weld and scale the mesh.
   2. Remap the collar to a ±105° arc behind the neck.
   3. Make a planar cut through the collar front, with flat caps on each side.
   4. Push the cloth back to clear the old armour-safe cape.
   5. Taper the shoulders.
   6. Decimate to about 6k triangles.
   7. Classify Base/Trim/Detail.
   8. Scale the outer cloth across over z 1.34-1.46, so the outline tapers smoothly into the collar instead of stepping in (the step read as a spike from behind).
   9. Recalculate one consistent winding over the whole shell.
   10. Apply `cape_weights_blender.py` last, on the final positions: the top on `spine_03`, the rest on the `cape_l/c/r_01..04` chains. It ports `equipment_authoring.cape_weights` but keeps the weights continuous across the chains (see Traps).
3. `python blender_socket.py dump_cape_uv.py`, then (system Python with
   Pillow) `python cape_texture.py`. This writes `cape_grey.png`/`.jpg`:
   per-region gains plus low-frequency flattening, so a tint reads evenly.
4. `python cape_normal.py cape_grey.png <generic_cape.glb> cape_normal.png`
   derives the tangent-space normal map from the texture's own fine relief
   (the woven trim and the weave), blurred only inside UV islands so the
   seams do not crease. The GLB argument supplies the UV islands; the UVs do
   not change between rebuilds.
5. `python blender_socket.py dump_cape_mesh.py`, then
   `python ../build_shared_cape.py cape_mesh.npz cape_grey.jpg <out.glb> --normal cape_normal.png`.
   This packs the dump onto the `generic_cape` skeleton and inverse bind
   matrices: smooth normals per layer, fold triangles rewound to their
   shading normal, the lining wound toward the body, one JPEG texture and
   one PNG normal map. The default `--template` is the shipped cape, which
   keeps the same 77-joint skin.
6. Refresh `genericEquipment.generic_cape` in `native_asset_catalog.json`
   (bytes, vertices, triangles) and re-import.

`posekit.py` poses the review bodies in the library idle. It applies world
deltas from `Rest_Pose`, the same way the client copies local rotations by
bone name.

## Traps

- **Do not Laplacian-smooth the cape.** It is two thin layers of cloth, and
  smoothing pulled the outer layer through the lining.
- **Normals:** after decimation the split normals render as dark facets.
  `build_shared_cape.py` recomputes smooth normals welded by position.
- **Holes:** `holes_fill` on the collar ring makes a sheet through the neck.
  The pipeline deletes the seam chords and caps each side separately.
- **Clearance:** displacing per vertex in 3D shreds the mesh. Push along the
  body-facing axis only, against the old cape's inner line.
- **Dark slits on the back** have had three separate causes, and the red-lining
  check finds all of them: tint the `Detail` slot pure red in a scratch
  `--equipment` registry and render the back with `canonical_equipment_preview.gd`.
  1. Fold triangles faced against their smooth normal, so Godot lit them from
     inside. `build_shared_cape.py` rewinds them.
  2. The original cape weights give the near chain links k and k+1 and the far
     chain link k+1 only. Where the near chain changes (halfway between two
     chains) a vertex's bones jump. The cloth solver bends the chains apart,
     so that line tore. `cape_weights_blender.py` keeps both chains on the same
     pair of links. In the top fifth, where `spine_03` still holds part of a
     vertex, the chains use only their first link, which keeps every vertex at
     4 influences.
  3. Over a bulky torso the solver swings chain link 2 back by 15 cm. The
     coarse inner face of this thin shell then cuts through the outer one,
     because the two layers' vertices are 2-5 cm apart and skin differently.
     The lining is therefore single-sided and faces the body, so it is culled
     wherever it comes through. Do not make it double-sided again.
- **Runtime drape (`godot-client/src/actors/cape_drape.gd`):** its fade bands
  are tuned to this cape's shape (30/45 degrees of bearing, y 1.38/1.46). It
  also caps how fast the push may change across the cloth (`SLOPE`).
  `tests/test_cape_drape.gd` checks both. If the cape's shape changes,
  re-check the shoulder hook on a bulky coat (5:232) and the stretch numbers.
