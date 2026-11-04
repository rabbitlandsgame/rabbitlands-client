# Oldcraft-inspired character presentation

This pass translates the readable fantasy shape language of the supplied
World of Oldcraft reference into Eloria's existing assets. It does not copy
Oldcraft meshes, textures, UI sprites, or animation data. The reusable cues
are broad heroic silhouettes, oversized readable extremities, matte painted
surfaces, warm-brass/oxblood entry UI, and a strongly lit live hero preview.

## Runtime character contract

Eloria's canonical player rig remains the source of truth:

- Keep the 77 joint names, order, parent hierarchy, rest transforms, and
  inverse bind poses stable.
- Keep gameplay displacement code-owned. Animation root motion remains off.
- Body, skinned hair, and modular garments must bind to the same canonical
  skeleton. Rigid equipment remains on named sockets.
- Do not author scale tracks into shared animation clips. Proportion belongs
  in the body meshes; a scale track would override it every frame.
- Retain culture-specific silhouettes in the body meshes themselves. Heavy
  cultures carry more trunk and extremity mass, while tall or spectral
  cultures keep their long-limbed read.
- Continue using equipment fit variants where a silhouette cannot be reached
  by a uniform fit. Covered body zones should remain hidden to avoid clipping
  and unnecessary overdraw.

`OldcraftActorStyle` no longer touches the skeleton. The persistent bone pose
scales it used to apply to the chest, limbs, head, hands, and feet were
removed on 2026-10-05: they compounded down each chain, so a hand ended up
about 1.6 times its authored girth, and they fought the fitted equipment.
Bodies now render at their authored proportions. The class applies only the
material finish to each actor's native model: it retains authored texture,
tint, transparency, emission, metal masks, and normal textures while
softening plastic-looking highlights with a roughness floor, restrained
dielectric specular, and a bounded normal-map strength. Materials whose names
begin with `Race feature glass` keep their authored gloss.
`tests/test_oldcraft_actor_style.gd` checks that no skeleton styling remains
and that glass keeps its gloss.

## Source-model intake contract

The canonical 77-joint Eloria rig remains the only runtime player rig. For the
supplied female reference set, the separated high-poly model is the authority
for proportions, component boundaries, and equipment fit. A low-poly model may
donate geometry or LODs offline only after its UVs and materials are preserved
or cleanly rebaked and its skin is transferred to the canonical skeleton.
Mixamo rigs and animation clips are import/alignment references, never runtime
retargeting sources.

Preferred future source packages provide the exact canonical rest pose,
separated body and wardrobe components, clean UVs with base-colour and normal
textures, no more than four joint weights per vertex, and one material per
piece. Target 18–22k body triangles plus 3–4k hair for High, 8–12k plus 1–2k
hair for Medium, and 3–6k silhouette-preserving body triangles for Low. Fit,
skin transfer, and LOD conversion are baked and validated offline, avoiding
any added per-actor runtime cost.

## Player-selectable character quality

The existing Graphics Quality setting now also controls actor presentation.
Imported Godot scenes provide generated mesh LOD index chains; the runtime
cache shares those meshes, skins, and materials across actors.

| Setting | Mesh selection | Actor shadows | Remote cape cloth |
| --- | --- | --- | --- |
| Low | LOD transitions at 0.35× authored bias | Off | Off |
| Medium | LOD transitions at 0.65× authored bias | Authored setting | Off |
| High | Authored LOD bias | Authored setting | On |

(Low and the Performance preset also take the Low actor tier: fewer crowd
bodies, nearer full-rate animation and finger detail, fewer effects and
banners; see `ActorRenderQuality.QUALITY_PRESETS`.)

The local player's cape remains available at every tier. Existing crowd rules
remain in force as well: nearby actors animate at full rate, farther visible
actors update at half rate, off-screen animation pauses, and actors outside the
draw radius are hidden. Changing quality is live and does not re-import or
duplicate actor resources.

When torso coverage rebuilds a body surface, it filters every imported LOD
index chain through the same face predicate as the full-detail surface. This
keeps Low/Medium/High selection intact without adding a quality-specific mesh
cache or any per-frame geometry work.

### LOD bias and switching distances

Besides the importer's chains (imported races, hair and creatures in an editor
checkout), an actor glTF parsed raw can
carry the package-time chains of the actor geometry cook
(`actor-geometry-lods.md`): levels near 50 / 25 / 12 / 5 % of each surface's
triangles, placed at 8 / 18 / 36 / 70 m for a bias of 1 at 1920 px, and never
before the level's geometric error covers 3 px. Godot draws a level once
`edge * lod_bias * model scale / (distance * 2 tan(hfov / 2)) <= 1 px / width`,
the distance running from the camera to the near side of the mesh's bounds, so
the quality's bias scales every switch:

| Setting | Bias | Levels from (1920 px; a 1280 px view switches at 2/3 of these) | Error allowed |
| --- | --- | --- | --- |
| High | 1.0 | 8 / 18 / 36 / 70 m | 3 px |
| Medium | 0.65 | 5.2 / 11.7 / 23.4 / 45.5 m | 4.6 px |
| Low | 0.35 | 2.8 / 6.3 / 12.6 / 24.5 m | 8.6 px |

The biases stay 0.35 / 0.65 / 1.0 (wave-2 schedule 1.1 #5); a retune is an
owner decision taken on the LOD ladder below. RL heads and RL hair keep their
authored lod0/1/2 bands (10 / 25 m) and are never cooked.

### Far presentation

`ActorRenderQuality` also carries the far presentation the far-crowd tier
(actor LODs C7) applies: `apply_mesh(mesh, level, true)` and
`apply_actor(root, level, true)` draw the coarsest level of every chain
(`FAR_LOD_BIAS`, the minimum bias) and cast no shadow at every quality, and the
next call without `far` gives back exactly what that quality draws, from the
same authored baseline. Which bodies are far is decided by rank:
in-view bodies ranked by camera distance, nearest first, priority actors not
ranked, keep full presentation up to `far_detail_bodies(level)` (High 24,
Medium 20, Low 16); a full body goes far from that rank plus
`FAR_HYSTERESIS_BODIES` (4), and a far body comes back inside the limit
(`far_by_rank`). Surfaces without a chain (torso lining soups, the cape) stay
whole; hiding the cape, quiver and banners, forcing the RL head band and the
animation rate are the actor's part of the tier. Nothing applies it yet: the
default path draws what it drew before at every quality.

### LOD ladder

`tests/integration/actor_lod_ladder.gd` (windowed, under the GPU lock) builds
two Humans in the crowd benchmark's kits A and B, an unequipped Glasswarden and
a creature as remote actors at each quality, poses them, and backs the camera
(FOV 50, 1920x1080, pitch -35) away to 4 / 8 / 12 / 18 / 26 / 36 / 50 / 70 m.
Per step it records the visible and shadow primitives and draw calls of the
actor alone, the primitives Godot's LOD rule predicts from the meshes' chains
(per piece: level drawn and triangles), and a crop of the frame at native
pixels. By default every actor file is parsed raw, as an exported build parses
it (`RABBITLANDS_LADDER_PARSE=editor` keeps a checkout's imported races, hair
and creatures; a guarded checkout's equipment is `importer="skip"` and parsed
raw either way).
One process draws one renderer and one geometry variant
(`RABBITLANDS_ACTOR_GEOMETRY=off`, or `RABBITLANDS_ACTOR_GEOMETRY_ROOT` for a
cook); `RABBITLANDS_LADDER_MODE=clip` writes a zoom clip of one subject at the
three qualities side by side (3 -> 70 -> 3 m). `actor_lod_ladder.py gate`
judges gate G5 across runs (Compatibility draws what Forward+ draws and what
the rule predicts, and fewer primitives than the plain parse from 18 m),
`compose` writes the owner's strips and `clip` encodes the clip.

Measured 2026-11-04 (dev laptop dGPU, editor binary 4.7.2, a scratch cook with
lining masks for the review sample and the budget stage): gate G5 is GO.
Compatibility selects exactly the levels Forward+ selects (its primitives
differ from the rule's prediction by the same amount in 96 of 96 cells, and
are identical wherever both draw the same pieces); Mobile draws exactly what
Forward+ draws, shadows included. The renderers differ only by design: the RL
head is drawn on Forward+ and Mobile, Compatibility keeps the classic High
head. Primitives of one equipped Human (kit B, 3 px chains) against the plain
parse: High 57.0k at 4 m (masked linings only), 38.4k at 26 m and 28.7k at 70 m
(plain 58.1k / 52.9k / 47.5k, the RL head's own bands); Medium 29.5k and Low
27.4k at 26 m (plain 47.4k). The Glasswarden falls from 39.4k to 12.5k (High)
and 10.6k (Low) at 26 m, the boar from 4,130 to 1,031 at 70 m (High). The
Humans do not reach the ~25k High budget beyond 8 m with these chains: about
21k of what they draw at any distance has no chain (the torso lining soup,
15.0k, and the cape, 6.1k), so vertex-colour torso linings (C10) and a cape
chain are the remaining levers.

The generated LOD chains are reached through `GlbSceneCache`'s imported-scene
route, which only an editor checkout takes. An exported client has no resource
path: `ProjectSettings.globalize_path("res://assets/...")` returns a path
relative to the game folder, `localize_path()` cannot map it back to `res://`,
and every actor glTF is parsed from its loose file with `GLTFDocument`, as it
was before this work. Packaged clients therefore ship the actor glTF files
loose only and the face masks (the actor files the client `load()`s) in the
PCK only. The RL head (the High Human head) follows the same split: its GLBs
(`native/rl_heads`) ship loose only, and its maps (`native/rl_head_textures`)
in the PCK only, VRAM-compressed with mipmaps by import settings committed
beside them. The textures the equipment glTFs name by relative URI ship in the
PCK too: `GLTFDocument` asks `ResourceLoader` for an external image before it
reads the file, a relative path resolves to `res://`, and the packager writes
their import settings (VRAM-compressed, mipmapped), so packaged equipment
uploads the imported textures rather than decoding each JPEG without mips.
Actor images nothing names (the editor's extracted copies of embedded glTF
images, the race and neck texture sources) are left out of a package; one
that any other shipped text names (data, scenes, map manifests) ships loose.
`GLTFDocument` reads each imported texture back with `get_image()`, a
RenderingServer call that a worker thread can only make by waiting for the
main thread, so equipment glTFs are parsed on the main thread only, never in
`NativeAnimationImporter.prewarm` or a map preloader's `GlbSceneCache.prepare`. A
packaged actor still carries no LOD chains, so Low and Medium change
shadows, cape simulation and LOD bias but not mesh detail there. The route to
packaged LODs is the actor geometry cook (`actor-geometry-lods.md`): every raw
actor parse hands its state to `ActorGeometry.apply`, which attaches the
package-time chains of a catalogue that validates against that parse; a
package draws them once release packaging installs a catalogue (actor LODs
C9). Until then an exported build has none and draws as before.

Anything pinned to a mesh's bytes must therefore pin the parsed mesh too. The
importer lays out each face's corners differently from `GLTFDocument`, so a
fingerprint taken from the imported scene does not match the raw parse. The
Orun male's reviewed rear-neck face mask pinned both until the race rebase
rebuilt every race body on the Human body; it was retired with that rebuild.
`TorsoBodyCover` now pins no face list: a race's shared-neck bridge takes the
same face test as the rest of the body, apart from its throat
(`FRONT_BRIDGE_MIN_WEIGHT`), so the body below the bridge is cut exactly like
the Human's on either route. That rule finds the bridge by its material name,
"Shared neck bridge"; `tests/test_torso_body_cover_lods.gd` builds a rebased
female through `_build_raw`, the route a package takes, and requires the
same cut as the imported scene.

For future authored assets, use the following review targets rather than
adding more runtime modifiers:

- High: 18–22k body triangles plus 3–4k hair, normal map, local shadows.
- Medium: 8–12k body triangles plus 1–2k hair, 30 Hz distant animation.
- Low: 3–6k silhouette-preserving body, simplified or baked hair, 512–1024
  textures, 10–15 Hz distant animation.
- Prefer one material per visible piece and no more than four visible actor
  submissions on High. A future baked crowd representation can target two on
  Medium and one on Low without changing the gameplay actor contract.

## Entry-screen contract

Login and character creation keep Eloria's identity but use the reference's
visual hierarchy:

- dark carved-stone framing (`#1E1E22` / `#333338`),
- brass edging (`#F4C542` / `#B88A3B`),
- oxblood actions (`#8E1B12`, `#B82B1A` on hover),
- warm text (`#F5F0E0`), and
- a cool moonlit preview with a warm key, teal rim, and stone/brass pedestal.

The login remains lightweight procedural UI over Eloria's existing painted
world image. Character creation uses one original 1920×1080 painted stage, one
512×128 four-icon atlas, one live 3D actor, a stone class rail, and a parchment
form. The SubViewport has a transparent background so the actor reads as part
of the painting instead of inside a black box. No extra actors or animated
scenery are created, and the existing viewport gate disables preview rendering
as soon as character creation is hidden. The two UI textures are not referenced
by gameplay scenes.

## Creation class and starter-item contract

Creation offers four open-ended starting callings: Vanguard (`0`), Ranger
(`1`), Arcanist (`2`), and Warden (`3`). The calling is independent of the
selected race and sex. It grants an initial inventory but never restricts
attributes, skills, equipment, or later progression.

The server-owned starter grants are intentionally light enough to leave room
for tutorial rewards: Vanguard gets a militia sword, round shield, guard cape
and Studded Jack; Ranger gets an Amberwood longbow, 20 arrows and Scout Vest;
Arcanist gets an arcane focus wand, Warded Tabard and three mana potions; and
Warden gets a fighting quarterstaff, Furtrim Coat and leaf cape. The live
preview combines those starter pieces with each race's native lower wardrobe
to communicate a coherent class silhouette; the adjacent text names the items
actually granted.

The legacy `CREATE_CHAR` payload keeps its original eight appearance bytes in
the original order. Eloria appends one `class_id` byte after them. Updated
servers validate that byte against their own immutable starter-kit table and
select inventory using only the class id; `actor_type` remains a separate
visual choice. A missing ninth byte defaults to Vanguard, which keeps old
clients valid, and legacy servers ignore the trailing byte.

The client class table owns only presentation: label, description, icon key,
and representative equipment visual ids. The server owns the actual item
names and quantities. Switching race rebuilds the same selected loadout on the
new body. Players can temporarily hide class gear to inspect hair and wardrobe
colours without changing the selected class or the items creation will grant.

The class kits wear the Human fits (`eloria-assets/tools/refit_human_bodies.py`
installed by `install_human_equipment.py`); every race falls back to them, and
headwear has a fit per race body (`refit_race_headwear.py`). The class-equipment
pass reviewed before the race programme (the four class torsos and the Arcanist
and Ranger legs and boots, on the retired Luminous bodies) was produced by
`revise_class_equipment_fit.py` and `build_class_equipment_fit_references.py`.
Both tools and the test that pinned their outputs were retired in the race
programme's P7 cleanup (2026-10), together with those outputs: no body wore the
old-male base scenes or the `variants/luminous_female` scenes any more.
`eloria-assets/qa/class-equipment-fit-baseline.json` stays as the record of
that pass, and the tools remain in git history (last present at a35ff1c43).

A race headwear refit can carry many times the triangles of the Human fit it
was made from (the Votary Sun Headband: 38,558 against 1,285). The actor
geometry cook's budget stage (`tools/actor_geometry/budget_policy.gd`, see
`actor-geometry-lods.md`) gives such a refit a simplified base that it draws at
every distance: the largest simplified level within twice its Human fit's
triangles whose error meets the LOD policy's 3 px clamp from 8 m, or, when no
level within twice does, the smallest level that does (removing at least a
quarter); a refit with no such level keeps its full mesh. The refit's own
vertices, UVs and materials are kept. It takes effect only where the game
applies cooked actor geometry.

## Asset-generation decision

No new generated mesh was required for this pass. The existing canonical
bodies and modular equipment can carry the target silhouette through their
shared rig, so no external generation credits were consumed.
