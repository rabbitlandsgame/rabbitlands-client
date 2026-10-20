# Procedural model retirement

On 2026-10-16 the user requested archiving procedural models across **all model
types**, then explicitly requested removing them from game use as well.

The retirement covers 1,036 standalone model files: legacy procedural creatures,
equipment, harvest/service objects, scenery and editor-kit pieces. Their original
files, associated sidecars, source scripts and pre-change catalogs are preserved
with SHA-256 verification under the ignored local authoring archive:

```text
.local/asset-authoring/archives/procedural-models-20261016/
  manifest.json
  retirement-receipt.json
  files/                 Exact original models, sidecars and source implementations
  changes-before/        Catalog and scene records before retirement
```

The public summary and per-model hashes are in `docs/qa/procedural-model-archive`.
The archive is recoverable source material, outside the game's model folders and
outside packaging. It is not an active asset-development destination.

The Landfall arrival plaza's star mosaic is a user-requested restoration on
2026-10-16. Its original `kit-sw-plaza-rosette.glb` and 1024-pixel mosaic texture
remain active as a ground inlay. The saved Landfall scene binds the preserved
model again, and the runtime retirement index permits its mesh in chunk
`08_11`. The nine original `kit-sw-garden-paving-*` limestone path overlays
were subsequently restored at the user's request. Their original model and
texture hashes, saved placements and terrain-conforming geometry are preserved;
their scene instances, authoring catalogue entries and runtime meshes are active
again. See `docs/qa/procedural-model-archive/ground-inlay-restoration.json` for
verification. The original retirement and audit receipts remain historical
records; the rosette and paving generators remain disabled.

One generator has run again since: the owner re-enabled
`eloria-assets/maps/continent-v2/_continent_v2/build_underground.py` on
2026-10-20 to rebuild the Cenote Deeps as a jungle cenote. It still refuses to
run without `--owner-approved`, and it draws only the interior's rock shell,
pools and light; the cave's art is reviewed Meshy kit scenery.

Procedural actor and equipment definitions are removed, including 158 actor
model entries, 163 actor-type mappings, four equipment visuals and 710 obsolete
authoring-catalog records. Historical identifiers remain reserved in the
retirement index; they are not active definitions. The server also removes its
three remaining procedural livestock definitions, 35 spawn rows, nine old
equipment items and 188 unused equipment name mappings, with their recipes,
drops and quest reward references. Items
with current updated models remain available. A stale actor/equipment packet
cannot create a substitute body or equipment mesh. Service markers and interactions remain
available without the retired object visual. Existing map layouts, terrain,
navigation and network package digests are preserved. Exact geometric copies
of retired scenery in baked map data are suppressed by a file-hash-bound mesh
index and a pooled-prototype deny-list. Scene-cache keys include this policy,
so an older cached scene cannot bring the retired visuals back.

The original procedural implementations are archived. Twelve old generation
entrypoints are disabled, and shared GLB writers refuse their procedural
generator types. Some modules remain importable because current imported-model
tools need their readers, rig measurements, skin fitting or packing classes.
These compatibility utilities do not authorize regenerating procedural models.
Mesh import, rig fitting, retargeting, hairstyle packing, the current sculpted
cape, race bodies and prepared Meshy scenery remain supported. An exporter name
alone does not establish that geometry is procedural.

Black Bear and Ice Bear are archived procedural targets. Their attempted Walk
and Jog adaptations were withdrawn, including the comparison package and its
authoring scripts. The installed Moss Bear model and all its approved clips
remain unchanged. Obsidian Bear, Crystal Polar Bear and Owlbear are the updated
bear-like candidates for a future anatomical audit.

Before animation work, use `eloria-assets/source/model-development-roster.json`.
Do not select an archived target just because its name matches a creature family.
The motion-fitting CLI rejects known procedural inputs; low-level archive and
validation readers can still inspect old files.

Focused verification:

```powershell
python tools/asset-authoring/test_procedural_retirement.py
godot --headless --path godot-client --script tests/test_retired_procedural_models.gd
godot --headless --path godot-client --script tests/test_ursine_video_motion.gd
```

The focused client checks, five server content checks and all seven Moss Bear
clips pass. The real map loader also loads a filtered map chunk. All 8,181
preserved models have their 31,411 external references available; the archive
includes its own referenced textures. See `docs/qa/procedural-model-archive/checks.json`.

The broader retained-catalog test still flags the Skeleton placement in
`landfall_insides` because it checks expansion spawns against exterior isle
registrations. The saved original tables with the same overlay reproduce that
failure. Full drop regeneration was also already out of date; this retirement
removes the three retired drop tables while preserving other creatures' loot.

Publication is a separate, user-directed step. This retirement requires no paid
generation, asset-service upload, deployment or player database change. Older QA
and generation receipts are historical records.
