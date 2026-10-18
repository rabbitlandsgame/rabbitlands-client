# Equipment on shared canonical player bodies

## Current layout (2026-10, after the race programme)

The text below this section records the September 2026 shared-body delivery.
Since then:

- **Bodies.** The Human bodies (`races/luminous_<sex>.glb`) were regenerated on
  2026-10-05, and all fourteen race bodies were rebuilt on them below the neck
  by `rebase_race_body.py` (build, verify, install, post-import), with horns,
  crowns, crystals and growths on their own `race_feature_*` nodes.
- **Torso, legs, boots (200 designs).** One fit per sex, on the Human body:
  `variants/human_male|human_female/<slug>.glb`, registry groups
  `canonical_human_male|female`. Every race lists its own group first and
  falls back to the Human group of its sex.
- **Headwear (64 designs).** The Human fits plus one fit per race body:
  `variants/<race>/<slug>.glb`, group `canonical_<race>` (896 race variants).
- **Base scenes.** Each generated model's base `scene` is its
  `canonical_human_male` file (`authoredFor: human_male`, mapped to
  `luminous_male` by `authoringRigs`). The race programme's P7 cleanup
  (2026-10-08) deleted the old-male base scenes `equipment/<slug>.glb` (264),
  the `variants/luminous_female` scenes (264) and the 128 textures only they
  named, dropped the `canonical_luminous_*` variants, and set
  `fitGroups.luminous_<sex>` to `[canonical_human_<sex>]`. A simulation of all
  6,864 body-by-model resolutions showed nothing worn changed.
- **Retired tools.** `refit_canonical_equipment.py build` and
  `pack_canonical_equipment.py pack|install` raise (`build_one`,
  `tool_hashes`, `pack_glb` and `validate` drive the current tools);
  `import_generated_equipment.py` no longer rebuilds an installed piece's
  `equipment/<slug>.glb` (it builds installed pieces only into scratch, with
  `--meshes-only --build-dir`);
  `build_shared_player_body_set.py`, `prepare_shared_registry.py`,
  `revise_class_equipment_fit.py`, `build_class_equipment_fit_references.py`,
  `install_neck_refinements.py`, `repair_ssarathi_*`, `build_neck_textures.py`
  and `verify_orun_neck_apron_mask.py` are deleted; they remain in git history
  (last present at a35ff1c43).

All races now use the Luminous male or female body shape below the neck, with
their original heads and Ssarathi tails retained. A continuous neck adaptor
joins each head to its body. Equipment is rebuilt from the original Meshy
`.glb.orig` designs and fitted to those two body shapes.

This supersedes the earlier sixteen-body equipment delivery. The isolated
worktree began at `68f4f6e20e7c11051aecbb580c03b47b89a25393`.
Item definitions and gameplay stats are unchanged.

## Set-level design fit (2026-10-16)

`torso_remap` and `limb_head_remap` fit each piece on its own, so the pieces
of one set are seated by different rules: a sleeve is scaled uniformly by the
arm-length ratio (girth included) and trimmed by a fixed profile, pauldrons
take the same scale, the trunk's depth is compressed to 0.8 of its width, and
the body-contact cage flares a skirt outward to clear the thighs. Worn
together, the Phoenix set read bulkier than its concept, with a bell-shaped
skirt and wide thigh plates.

A design fit instead fits a set the way it was drawn, on the body that wears
it. First an iteration target was built in Blender: the raw Meshy pieces of
the set assembled on the Human body in the game's idle pose
([target](design-fit/phoenix-target.jpg)). `design_fit_blender.py` makes that
assembly reproducible and turns it into the fitted shell:

- Each vertex rides the design bone it belongs to. The design skeleton (trunk
  lower/upper, upper arm, forearm, pelvis, thigh, calf, foot) is read off the
  concept-pose mesh and recorded in a set spec,
  `eloria-assets/source/equipment-design-fit/<set>.json`. Each design bone is
  carried onto its body bone by a similarity. The bone direction is rotated
  onto the body's, the cross-section is scaled by the piece's single girth
  scale, and the bone is stretched only along its length.
- Clearance is solved per bone with rays from the body bone's axis through the
  skin it carries. A ridge-damped least-squares shift centres the shell. One
  girth factor (capped at +12%) clears the skin by 12 mm on 85% of rays. A
  shell lying more than 25 mm inside the skin is a designed opening and is
  ignored, so openings never balloon a segment.
- Skin weights come from the posed body surface nearest each vertex, scoped to
  the bones each design bone may inherit from. They are smoothed over the
  shell, and small welded plates are made rigid. The skirt's tassets may take
  thigh weights, so they move with the legs instead of being flared clear of
  them.
- Rest positions invert linear-blend skinning at the idle pose. The client's
  own skinning therefore returns the target exactly in idle (round trip
  0.01 mm).

The tool writes `<source>.npz` per body under
`eloria-assets/source/equipment-design-fit/luminous_<sex>/`. When that file
exists, `design_fit.override` hands the shell to `torso_remap.build` /
`limb_head_remap.build` in place of their own retarget. Backings, inseams,
the textured fitted cloth, the cuff cut, sole seating
(`limb_head_remap.seat_harness_soles`), normals and packing all run as before.
The file pins source and body hashes, and a stale one is refused. Fit records
carry `design_fit_sha256`, and `tool_hashes` includes `design_fit.py`.

```powershell
blender -b --factory-startup --python eloria-assets/tools/design_fit_blender.py -- --spec eloria-assets/source/equipment-design-fit/phoenix.json --body <bodies>/luminous_male.glb --sources <generate_models/meshy-armor-individual-glb> --out eloria-assets/source/equipment-design-fit/luminous_male
python eloria-assets/tools/refit_human_bodies.py --bodies <bodies> --generated <generate_models/meshy-armor-individual-glb> --out <scratch> --pieces legendary_hero_cuirass_01,legendary_leg_armor_01,legendary_sabatons_01 --tag <t>
python eloria-assets/tools/install_human_equipment.py <scratch> --tag <t>
python eloria-assets/tools/share_human_equipment_textures.py
```

The installer writes `equipment.json` and `native_asset_catalog.json` with
CRLF line endings. This checkout is LF, so convert both back before
committing.

**Phoenix results.** The set covers Phoenix Cuirass, Phoenix Legguards and
Phoenix Sabatons, on both bodies; the socketed Phoenix Helm is unchanged.
Silhouette IoU against the target in idle (Blender, orthographic, backings
hidden):

| View | Old fit | Design fit |
| --- | ---: | ---: |
| Front | 0.903 | 0.981 |
| Side | 0.810 | 0.985 |

The leg pipeline still recomputes nearest-surface weights in the rest pose and
cuts the cuff at 0.32 m, which accounts for the remainder.

Evidence:

- [Blender old/new/target](design-fit/phoenix-blender-old-new-target.jpg)
- [in-engine before/after](design-fit/phoenix-engine-before-after.jpg) (real
  `ReplicatedActor3D`, `canonical_equipment_preview.gd`)
- [in-engine walk/run cycles](design-fit/phoenix-engine-walk-run.jpg)

The equipment, remapper and held-prop suites show the same 9 failures as clean
develop at `224bb9b9`; all of them predate this change and come from today's
procedural retirement plus registry checks. `test_torso_body_cover_lods.gd`
and `test_equipment_registry_snapshot_cache.gd` pass. The new
`GeneratedArmorBacking` textures replace two orphaned ones. The packed GLBs
grow 0.1–4%.

### Starter kits (2026-10-17)

The four class starter kits, the gear every new player wears, now have set
specs as well: `vanguard.json`, `ranger.json`, `arcanist.json` and
`warden.json`. They cover twelve pieces on both bodies:

| Kit | Torso | Legs | Boots |
| --- | --- | --- | --- |
| Vanguard | Studded Jack 5:209 | Leather Kneecops 4:220 | Banded Warboots 6:249 |
| Ranger | Scout Vest 5:225 | Sidelace Breeches 4:230 | Laced Fieldboots 6:226 |
| Arcanist | Acolyte Tunic 5:222 | Acolyte Legguards 4:185 | Acolyte Boots 6:198 |
| Warden | Furtrim Coat 5:189 | Furtrim Legguards 4:176 | Furtrim Boots 6:205 |

Their legs end at the ankle and their boots are separate sources. The Phoenix
set never needed either, so `design_fit_blender.py` and the leg hook gained
the pieces below. Each is opt-in per spec. Phoenix uses none of them, and
re-solving it reproduces its committed overrides exactly.

- **Calf/foot boot skeleton.** A boot's scale comes from its foot length (the
  body's 0.27 m plus 0.02 m of room, as `boot_frame` sizes boots). The ankle
  and ball sit where the body's do relative to the heel and sole. The calf
  bone runs up the shaft's own lean, so neither bone stretches (k = 1.00).
- **Sole seating.** `ground` seats each boot in the rest pose, 4 mm under the
  weighted sole (`seat_soles`), and the idle shell follows. On the fit path,
  `limb_head_remap.build` now seats separate boots as well
  (`seat_boot_soles`). It takes the stocking's cuff from the fitted shaft
  (`shaft_cuff`, factored out of `boot_frame`). Before this change both came
  from `boot_frame`'s own shell, which the override discards, and only full
  legendary harnesses called `seat_harness_soles`.
- **Clearance surfaces.** A bone's `surfaces` limits what its clearance
  clears. A boot shaft clears the default boot but not the default trouser
  leg, which the runtime hides under a fitted boot (`generated_body_cover`).
- **Limb split.** On the Vanguard, Arcanist and Warden torsos the sleeves hang
  against the coat. `split_limbs` assigns them by distance over the surface, as
  `torso_remap.connected_sleeve` does, instead of by nearest bone. Nearest
  bone gave 31% of the Vanguard sleeve to the trunk; the surface split gives
  11%, mostly cuff lining.
- **Layering.** `tuck_into` tucks the trouser legs inside the set's own boots
  wherever the boots cover them: 6 mm inside the shaft and never within 2 mm
  of the body. Fitted apart, both shells cleared the same body by the same
  margin, so they crossed and flickered through each other, worst under the
  Vanguard's tall warboots. The Arcanist trousers are drawn to hang over their
  boots, so they are not tucked.

The skeletons were read off gridded orthographic renders of the raw sources.

- **Torso.** The shoulder line at top − 0.17h maps to `neck_01`. Here h is the
  height without loose fragments, which leaves out the thin strap hanging below
  the Ranger's hem. The split is at `spine_02`. The girth scale comes from a
  chest and waist clearance table: Vanguard 0.72, Ranger 1.00, Arcanist 0.78,
  Warden 0.78. Trunk lengths follow the body's proportions at that scale.
- **Sleeves.** The shoulder sits one sleeve radius below the cap, on the
  sleeve's centre line. The wrist sits 4 cm above the cuff, and the elbow at
  the body's upper-arm/forearm split.
- **Legs.** The crotch maps to the body's crotch at 0.77 m. The knee falls at
  the body's thigh/calf split, or on a knee cop where one is drawn. The ankle
  sits just above the hem. Leg girth scales are 0.90, 0.95, 0.85 and 0.90.
- **Leg and boot offsets.** These bones carry the measured offset of the body
  leg's cross-section from its bone: the calf's centre sits 3.5–4 cm behind
  the calf bone.

The rules, measurements and renders are in the client's ignored
`.local/asset-authoring/working/equipment-fit-2026-10-17-kits/` (`make_specs.py`).

```powershell
blender -b --factory-startup --python eloria-assets/tools/design_fit_blender.py -- --spec eloria-assets/source/equipment-design-fit/<kit>.json --body <bodies>/luminous_<sex>.glb --sources <generate_models/meshy-armor-individual-glb> --out eloria-assets/source/equipment-design-fit/luminous_<sex>
python eloria-assets/tools/refit_human_bodies.py --bodies <bodies> --generated <generate_models/meshy-armor-individual-glb> --out <scratch> --pieces militia_torso_armor_02,militia_leg_armor_02,militia_greaves_02,leather_ranger_torso_02,rugged_ranger_legwear_04,frontier_boots_03,eloria_arcane_armor_07,arcane_leg_armor_07,arcane_fantasy_boots_07,amberwood_woodland_cuirass_06,amberwood_woodland_legguards_06,amberwood_woodland_boots_06 --tag <t> --jobs 4
```

**Starter-kit results.** The table gives silhouette IoU of each kit (all three
pieces) against its solved target in idle (Blender, orthographic, backings
hidden). "Old" is the per-piece fit installed before this change.

| Kit | Body | Front old | Front new | Side old | Side new |
| --- | --- | ---: | ---: | ---: | ---: |
| Vanguard | male | 0.857 | 0.994 | 0.794 | 0.994 |
| Vanguard | female | 0.873 | 0.995 | 0.810 | 0.994 |
| Ranger | male | 0.802 | 0.985 | 0.773 | 0.992 |
| Ranger | female | 0.825 | 0.978 | 0.783 | 0.993 |
| Arcanist | male | 0.835 | 0.986 | 0.746 | 0.967 |
| Arcanist | female | 0.823 | 0.988 | 0.781 | 0.968 |
| Warden | male | 0.877 | 0.993 | 0.777 | 0.977 |
| Warden | female | 0.888 | 0.995 | 0.797 | 0.982 |

At the 95th percentile, the installed visible art lies this close to the
target in idle: torsos 0.2–0.7 mm, boots 2–6 mm and legs 4–15 mm. The old fits
were 30–60 mm, 19–31 mm and 35–101 mm. The leg pipeline still recomputes
rest-pose weights, and the Arcanist's long back drape moves the most.

The poke check casts rays from each covered body bone's axis. It counts the
share of rays on which the worn volume lies 2–25 mm outside the visible art;
the worn volume includes the default clothes, which the runtime hides under
the piece.

| Piece | Design fit | Old fit |
| --- | ---: | ---: |
| Torsos | 0.2–2.8% | 3.4–13.9% |
| Boots | 5.9–24% | 8.2–40% |
| Legs | 5–12.5% | 2.3–19.5% |

On the legs, the Vanguard and Warden figures rise because the tucked calves
now sit on the hidden default trousers inside the boots. The Arcanist boots
stay highest because their shaft cannot clear the hidden default boot within
its 1.2 girth cap.

Evidence:

- [Blender target / design fit / old fit](design-fit/starter-kits-blender-old-new-target.jpg)
- [in-engine before/after, idle](design-fit/starter-kits-engine-before-after.jpg)
  (real `ReplicatedActor3D`, `canonical_equipment_preview.gd`)
- [in-engine walk/run cycles](design-fit/starter-kits-engine-walk-run.jpg)

The engine check used the real actor, before and after, on both bodies: Idle_Subtle front, side and back, plus 24-frame Walk and Run_Female cycles from the side. All 80 captures reported `CLIENT_CAPTURE_OK` with no script errors.

- The Vanguard warboots and the Ranger fieldboots now show over the trousers. Before, the trousers flared over them.
- The coats keep their drawn shoulders and sleeves.
- The cycles show no tearing at the armpits, knees or boot cuffs.

One thing carries over from the source: a thin loose strap below the Scout
Vest's hem now hangs at the right hip. The old fit threw it a metre to the
side, out of frame.

**Clean lining cuffs.** Inside wide cuffs, such as the Studded Jack's and the
Acolyte Tunic's, the wrist used to show a ragged fringe. It had two causes,
and both came from choosing whole triangles by their centre.

- **The lining's spikes.** `torso_remap.lining` kept body and default-shirt
  triangles whose centre fell short of the wrist plane. That left shirt-cuff
  and wrist-skin spikes up to 2 cm past the plane. The lining is now cut
  exactly on the plane (`clip_open_sheet`, the neckline clip generalised).
  Each sleeve ends in one ring, at least 9 mm inside each kit's cuff (lining
  0.743 m against art 0.752–0.788 m in the rest pose).
- **Holes in the hand.** At runtime, `TorsoBodyCover` hides every body
  triangle whose rest centre lies inside `bodyCover`. The wrist edge sat on
  the lining's plane, but a male wrist triangle reaches up to 2.5 cm past its
  centre. The hidden skin therefore left a row of holes past the lining's
  end, and the dark sleeve interior showed through them.

  The edge is now `wrist_cover`: half a millimetre short of the nearest centre
  of any triangle that crosses the plane (0.732 m male, 0.724 m female). No hidden triangle reaches
  past the lining any more. Over its last stretch the lining stays at least
  3 mm outside the skin it keeps. There it also takes that skin's own
  lowerarm/hand weights (`lining_weights`); otherwise the wrist skin swings
  out through the ring as the hand bends in idle. The hand now comes out of a
  clean ring.

The four kit torsos were refitted with both fixes. Their art is byte-identical;
only the lining and its `bodyCover` changed. Other torsos pick up the fixes
when they are next refitted. Evidence:
[lining cuffs before/after](design-fit/starter-kits-lining-cuffs.jpg).

The equipment, remapper and held-prop suites fail on the same 9 test IDs as
clean develop at `224bb9b9`. The Kneecops and Sidelace Breeches GLBs gain a
`ReconstructedInseams` mesh, now that the fitted legs meet at the inseam. The
packed GLBs change by −0.4% to +6.1%. The eight new fitted-cloth textures
replace eight textures that no GLB references any more. They were re-sampled
once more after the cuff cut, again replacing the eight they superseded.

**Not yet done.** Other sets keep their per-piece fits until they have a spec.
There is still no automatic landmark finder, so each spec's skeleton is read
off renders. Race headwear is untouched.

### Reviewing fits in the client

`godot-client/review-equipment.bat` opens an interactive turntable on the
real client actor (`tools/equipment_review/`). It is configured the way
`tests/canonical_equipment_preview.gd` configures it.

- **Drop-downs:** race (all eight), sex, armour set and animation. The sets
  are the four class starter kits from `CreationArchetypes`, plus those in
  `tools/equipment_review/review_sets.json`. The chosen clip loops at the
  game's playback speed. A walk or a run plays at the speed the client gives
  it for its own pace: Walk at 2.17× for 1.67 m/s and Run_Female at 1.81× for
  5.0 m/s (before 2026-10-18 the viewer played them at 3.5× and 2.17×).
- **Toggles:** headwear, weapons and cape, hair, and travel.
- **Travel** (T, or `--travel yes`): a walk or a run moves the actor through
  the scene at that pace, along the way it faces, with the camera following
  and a metre grid on the floor. On the spot the cape cloth never sees the
  actor move, so it hangs into the arms and legs as it never does in play.
  Travelling, the clip, the actor and the cloth advance together in game
  frames: a pause freezes the cloth where it was, `.` plays one frame on, and
  slow motion shows each frame for longer instead of making it shorter.
- **Camera:** mouse orbit, pan and zoom, keyboard turning, and preset views
  on 1–5. Space pauses, `,` and `.` step a frame, and `[` and `]` change the
  speed.
- **Notes:** F2 or C saves a screenshot without the panels and asks for a
  note.
- **Reload:** F5 reloads from disk after an edit.

A piece whose GLB is newer than Godot's import is built straight from the
file, so the viewer never shows a stale import.

Notes go to `<checkout>/.local/asset-authoring/working/equipment-review/<session>/`.
Each session folder holds:

- `notes.jsonl`: one line per note, with the race, sex, set, each piece's key
  and resolved scene, the clip and its time, the travel toggle with its pace
  and clip speed, the camera (its target is relative to the actor's ground
  point), and the commit;
- `notes.md`, the same notes in readable form;
- `shot_NNN.png`, the screenshots;
- `session.json`.

`--race`, `--sex`, `--set`, `--clip` and `--review-dir` preselect the view
and the notes folder.

The viewer also reshoots a review without anyone at the keyboard:

- `--replay <notes.jsonl> [--notes 7,13] [--out <dir>]` restores each note's
  race, sex, set, toggles, clip time and camera, saves `replay_NNN.png` and
  quits. Any file of note-shaped lines works, so a list of chosen views can be
  shot the same way.
- `--equipment <equipment.json>` reads a copy that points at candidate GLBs,
  so a fix is seen on the noted view before it is installed.
- `--headwear yes|no` overrides the notes' headwear toggle.
- `--travel yes|no` overrides the notes' travel toggle. Travelling, a replay
  plays 2 s of the clip at 60 frames a second, ending on the noted time, so
  the cloth is streaming on the noted frame.
- `--debug-tint yes` draws generated backings magenta and body surfaces cyan.
  It tells a hole from a dark lining, or from the skin behind it.

The actor's nameplate, health bar and their backing are hidden: the empty
backing used to float above the head as a dark box.

### Owner review fixes (2026-10-17)

The owner reviewed all five sets in the viewer and left 17 notes (review
commit `724ee07e`). Ten are fixed here. The seven headwear notes (4, 6, 9–12
and 17) are left for their own pass; see **Not yet done** below.

**Sleeves tearing in the bow pull (notes 1, 2, 15 and 16).** The design fit
weighted every vertex from the posed body surface nearest it in idle. There
the arms hang against the coat, so a sleeve's inner wall took chest weights
and its hem stayed behind as the arm rose. `design_fit.bind_sleeves` now binds
every vertex the fit gave to an arm with torso_remap's own arm field. The
upper arm hands over to the forearm from 43% to 59% of the way to the wrist.
The trunk keeps the fit's weights. The weights are smoothed with the
sleeve/coat bridges opened, except across the shoulder yoke, and the rest pose
is solved again from the idle shell. The client therefore still shows the
fitted shell exactly in idle. The npz is now `FORMAT` 2, adding each vertex's
arm share and the idle skinning matrices. A loose tie on the Scout Vest
(`loose_ties`, 10 triangles) is dropped, as torso_remap drops it.

Share of art triangles stretched past 1.8× their idle edge length, at the
worst frame of Bow_Pull_Back (`stretch_check.py`):

| Torso | Male before | Male after | Female before | Female after |
| --- | ---: | ---: | ---: | ---: |
| Studded Jack | 4.48% | 0.94% | 4.73% | 0.81% |
| Scout Vest | 4.99% | 0.35% | 4.96% | 0.21% |
| Acolyte Tunic | 2.47% | 0.71% | 2.47% | 1.11% |
| Furtrim Coat | 2.35% | 0.64% | 2.32% | 0.64% |
| Phoenix Cuirass | 0.59% | 1.15% | 0.88% | 1.40% |

The Phoenix figure rises by six triangles of its 1,357, at the shoulder. In
the engine its torn, hanging sleeve (notes 15 and 16) is gone. A pauldron's
edge now lifts with the arm and shows the dark lining under it.

**Holes at the throat (notes 7, 13 and 14).** Under a torso, `TorsoBodyCover`
keeps only those neck faces whose three corners carry more than half
Head/neck_01 weight. On the Human body that ring starts at 1.467 m (male)
and 1.456 m (female) at the front. The lining's neckline is cut at 1.40 m, and
the throat faces between carry no neck weight at all. Under an open collar
the throat was therefore neither skin nor lining: a hole into the coat
(notes 13 and 14), and a dark well seen from above (note 7). Lowering the
weight threshold, as race bridges do, would not reach them.

torso_remap now writes the lining's neckline height, `LINING_NECKLINE`, as
bodyCover's fourth value. With it, `TorsoBodyCover.keeps_open_throat` keeps
the skin in front of the neck axis, within 13 cm of the midline, from 1 cm
below that neckline as torso_remap cuts it. Pieces without the value are cut
as before; today only the five refitted torsos carry it.

Inside the Furtrim Coat, a 28-vertex loose fragment ran 9 cm deep into the
neck and showed as the black band of note 14. `buried_fragments` drops small
components centred in that open throat that lie more than 3 cm inside the
skin; on these torsos only that fragment qualifies. Trim that merely dips
into the skin elsewhere stays.

**Flat female chest (note 8).** One girth and shift per trunk bone keeps a coat
drawn for a flat chest flat. On the female body the Studded Jack's front sat
on the bust apex, with the skin up to 1.6 cm through it, and stood 3–4 cm off
the upper chest and the waist. The torso specs now carry a `conform` entry,
applied on `luminous_female` only. On a 1 cm grid in front of the chest it
moves the trunk art front to back, so that its outermost layer sits 1.2–1.6 cm
off the skin. It moves out by at most 3 cm and in by at most 2 cm, smoothed;
every layer at a point moves together, and the sleeves and the back do not
move. A plate that stands well off the body keeps that standoff: the target is
taken above the quarter of the grid closest to the skin. That is 36 mm for the
Phoenix Cuirass and 0.5–15 mm for the coats. Measured this way, without the
standoff, the cap had drawn the cuirass in by 2 cm all over and its chest read
flatter. The bust now comes forward 12–23 mm and the waist goes in up to 2 cm.

**Collars not reaching the back of the neck (after the headwear notes).** The
owner pointed out that part of the gap between hood and collar (notes 9–11)
was the torso: the collar did not come far enough back. A trunk bone's
clearance clears the spine and clavicle skin, not the neck's. So in idle the
back of every kit collar lay inside the nape: from 1.46 m on the Studded Jack
(5 cm deep by 1.56 m) and from 1.48–1.54 m on the others. From the side, the
nape showed where the collar should wrap it.

The torso specs now carry a `collar` entry, on both bodies. It casts rays
out of the posed neck_01 → Head axis, every 1 cm from 1.40 to 1.64 m and
every 10° around. Where the outermost trunk art is closer than the skin plus
15 mm, it moves the art at that height and bearing out along the ray. The move
is smoothed round the neck, measured and applied twice, and faded in over the
first 4 cm. Only art within 4 cm of the neck skin moves, so the shoulders and
an open collar's front keep their shape. The largest moves are at the back:
up to 7–8 cm on the Scout Vest and the Studded Jack, 11 cm on the female
Furtrim Coat, 4–6 cm on the Acolyte Tunic and 2 cm on the Phoenix Cuirass. In
idle, every collar's back now clears the nape up to 1.60 m: at least flush,
and 5–15 mm off it in all but two 1 cm cells per torso (8 mm clearance had
left the skin grazing through at the back centre). The collars wrap the nape
and meet the hoods' back edge. The collar art carries `neck_01` weight there,
so it follows the head. The tearing figures above are for the collared
torsos. Evidence: [collars](design-fit/review-fixes-collar.jpg).

**Arcanist tails folding at the knee (note 5).** The Acolyte Legguards' two
back tails, and three trim strips, took thigh weights above the knee and calf
weights below it, so they creased at the knee in every stride. The legs
spec's `drape` entry hangs them from the pelvis instead. Each tail follows its
thigh up to 80% by 60% of its drop, with 15% calf at the hem, so it swings as
one panel.

Evidence:
[tearing](design-fit/review-fixes-tearing.jpg),
[throat](design-fit/review-fixes-throat.jpg),
[female chest](design-fit/review-fixes-chest.jpg),
[Arcanist tails](design-fit/review-fixes-tails.jpg). Each image shows the
installed fit beside the fix, on the noted view, reshot with `--replay`.

`wrist_cover` now sits half a millimetre short of that triangle's centre. On
the centre itself, the triangle sat on the cover's strict edge: the Human body
kept it and a race body, whose rest skeleton differs by micrometres, cut it.
`torso_body_cover.gd` caught this as one face in 2,027 on six male races,
after the cuff fix.

All 30 design-fit pieces were refitted. Only the five torsos and the Acolyte
Legguards changed; the other legs and boots are unchanged to the micron and
reinstalled byte for byte. The ten new fitted-cloth textures replace ten that
no GLB references any more; the six older orphans stay.

Tests:

- The equipment, remapper and held-prop suites fail on the same 9 IDs as
  clean develop at `224bb9b9`.
- `torso_body_cover.gd` passes: 16 races, cover and equip/unequip.
- `creation_class_equipment_fit.gd` passes: 54,666 checks on 16 rigs.
- The torso LOD, imported-actor LOD and registry snapshot tests pass.
- `armour_body_cover.gd` reports 60 failures, all "restores sculpted hair
  visibility". In each, the scalp stays visible under the Amberwood 04 helm
  (3:120) in its own set, on ten rigs. No piece or code path changed here
  touches it.

**Not yet done.**

- **Headwear (notes 4, 6, 9–12 and 17)** is fixed in the next section.
- **Other torsos.** The open throat and the female conform reach only the
  five refitted torsos. Every other torso keeps the throat cover until it is
  refitted, and keeps its flat front until it has a set spec.

### Headwear review fixes (2026-10-17)

The seven headwear notes are fixed on the five pieces they name: the Leather
Helm (3:134), the Phoenix Helm (3:125), the Buckled Hood (3:159), the Acolyte
Hood (3:115) and the Antler Hood (3:122). `limb_head_remap.head_frame` seats
every helm and hood with one uniform scale and a translation. A new opt-in
step, `headwear_fit.py`, reshapes these five pieces after it. Its rows live in
`eloria-assets/source/equipment-design-fit/headwear.json`, keyed by Meshy
source like the set specs. The step runs inside the fitter: the frame on
every body, the rest on the Human bodies. The race variants are therefore
carried from the reshaped Human fit by `refit_race_headwear.py`, as before.
`race_pass` now takes the Human fit itself, vertex for vertex, as its carry
reference. Before, it rebuilt the reference from the race fit by `frame_map`,
which gives the same thing only while both fits are similarity images of the
source.

**Helms read large (notes 6 and 17).** head_frame grows a helm until every ray
from the cranium clears the skin by 9 mm, cheek guards and nape included. That
left the Leather Helm 30 mm (male) / 24 mm (female) off the cranium at the
median and 40 / 31 mm at the crown. The Phoenix Helm's sculpted shell stood
82 / 77 mm off. Both are now scaled about the cranium centre that
race_headwear_clearance fits behind the face. The Leather Helm takes 0.90
(male) and 0.94 (female); the Phoenix Helm 0.90 and 0.92. The female fits
were already tighter. Whatever of the head then comes within 6 mm (cranium,
face and ears above the jaw) is pushed out radially. This is `radial_push`,
the broad push the race passes give a helm: at most 8.5 mm on the Leather
Helm, 16–27 mm under the Phoenix Helm's cheek plates. The push moves vertices
only and never splits a face, so the race carry still matches vertex for
vertex. The Leather Helm's median gap is now 17.6 / 16.2 mm (28 / 23 mm at the
crown), the Phoenix Helm's 68 / 64 mm. Scaling about the brow was tried first.
It pulled the Leather Helm's back into the skull and the Phoenix Helm's cheek
plates into the cheeks, and the push then had to move them 16–30 mm back out.

**Hoods over the collar (notes 9–12) and the Acolyte chin (note 4).** The
torso fix above closed note 9's gap at the back: the collars now wrap the
nape. Two problems remained. On all three kits the torso's front collar stood
outside the hood's lower front: the Scout Vest's shirt collar points, the
Acolyte Tunic's stand collar and the Furtrim Coat's high collar. And the
Acolyte Hood's mouth wrap crossed the chin. headwear_fit's `cowl` now reshapes
each hood against the torso it is designed with (`over` in the spec), in the
idle pose. The design fit is solved there, and a torso's rest shell is an
inverse-skinning image that stands up to 5 cm higher behind the neck than
anything a player sees. Body and torso are skinned to idle with the matrices
in the torso's design-fit npz, and the hood rides Head. Round the idle neck
axis, on a 5° × 2.5 mm grid:

- The hem follows the upper envelope of the collar's visible top, taken over
  40° either side, so an open V-neck does not pull it down. Below a pivot 1 cm
  under the Head joint, the hood is stretched down, linearly with depth, to
  end 15 mm under that line (by at most 5 cm).
- The shell is pushed out to 6 mm over the skin and over the art seen from
  outside, by at most 6 cm. Every layer at a cell moves by the same amount.
  Art more than 7 cm outside the shell is a hem tucked under by design, and is
  left. The push flares up into the hood over 4 cm.
- The move is smoothed over space (2 cm), so a wrap folds as one cloth and
  its trims and beads stay on it. Smoothing along mesh edges had left the
  Acolyte Hood's gold trims, which are separate pieces, standing off the
  cloth like spikes.
- Head's idle matrix carries the shape back to rest.

The hoods' lower parts move by up to 6–10 cm, most on the Antler Hood. The
Acolyte Hood's wrap now passes in front of the chin. Through the clips below,
it crosses at most 27 (male) and 20 (female) skin triangles, against 88 and 75
installed: those were the chin cut of note 4.

**Rigid, not skinned.** The brief's question was whether a cowl lying on the
collar lets the collar through when the head turns. The head moves a long way
against the upper torso in the game's clips. Measured from idle, Head turns
against spine_03 by 16° in Walk, 36° in Jog and 72° in Bow_Pull_Back. A ring
9 cm round the neck at the collar, rigid with Head, moves 7–15 cm against
spine_03. So `headwear_fit` can also skin the cowl (`skinned: true`). Head
weights the crown. Below the pivot the shell takes the skin's own neck and
yoke weights, the collar art's weights where it lies on the collar, and Head
again over the chin. The fitter and `refit_race_headwear` then write a skinned
piece. The runtime's skinned equipment path and its part-3 hair hiding need
no change. Both kinds were measured through eight clips in Blender: posekit,
torso skinned, inward rays square to the posed neck every 10° at 30 heights.
"Collar over hood" counts the rays whose first surface is torso art with the
hood beneath it. Stretch is the share of hood triangles past 1.8× their idle
edge length (the sleeves' tearing measure). Male, most rays at any frame:

| Hood | Kind | Idle | Jog | Bow_Pull_Back | Stretch, Bow / Sword |
| --- | --- | ---: | ---: | ---: | ---: |
| Buckled | installed | 99 | 225 | 363 | 0 / 0 |
| Buckled | rigid cowl (shipped) | 55 | 218 | 346 | 0 / 0 |
| Buckled | skinned cowl | 55 | 184 | 332 | 5.9% / 6.8% |
| Acolyte | installed | 88 | 253 | 346 | 0 / 0 |
| Acolyte | rigid cowl (shipped) | 53 | 231 | 312 | 0 / 0 |
| Acolyte | skinned cowl | 53 | 207 | 298 | 10.8% / 12.9% |
| Antler | installed | 104 | 340 | 463 | 0 / 0 |
| Antler | rigid cowl (shipped) | 115 | 302 | 447 | 0 / 0 |
| Antler | skinned cowl | 115 | 262 | 397 | 10.9% / 11.4% |

In motion a skinned cowl lets the collar through 4–16% less than the rigid
one. But in the bow pull and sword swings it stretches 6–13% of its triangles
past 1.8×, and the owner read the bow-pull sleeves as torn at 0.6–5%.
Narrowing the weight blend made it worse (up to 18%). The shipped cowls are
therefore rigid on Head. Across all eight clips (Idle_Subtle, Walk, Jog,
Fighting_Idle, Bow_Pull_Back, Sword_Regular_A, Spell_Simple_Shoot, Hit_Head)
and both bodies, they let the collar through no more often than the hoods they
replace, with four exceptions, all small. The Antler Hood rises from 104 to
115 rays in male idle and from 310 to 317 in female Jog, then +3 and +1
elsewhere. Their skin contact is lower in every clip, and nothing stretches.
In the engine, the motion frames match HEAD's.

**Race gates.** `refit_race_headwear.py measure` covers the 14 race bodies in
rest pose. The Leather Helm's body crossings fall from 251 to 30 and its
collar clip from 67 to 33 cm². The Phoenix Helm's crossings fall from 2,790 to
2,015 and its collar clip from 693 to 431 cm²; the neck and skin enclosed by
its smaller shell rise from 3.3 to 6.0 and 0.25 to 2.1 cm². The Buckled Hood
is about unchanged (3,118 to 3,059). The Acolyte and Antler hoods' body
crossings rise from 66 to 132 and 35 to 181. Their lower fronts are shaped in
idle and cross the rest-pose shoulders on some male races, up to 31 edges
each. In idle on those bodies (Orun, Mycelari and Glasswarden male; Ssarathi,
Votary and Greyhaven female; Stoneborn male) nothing shows. Collar crossings
fall for the Acolyte Hood (56 to 26) and hold for the Antler Hood (198 to 208).

**Install.** The ten Human variants were installed with
`install_human_equipment.py`, then `share_human_equipment_textures.py`; the
registry and catalogue were converted back to LF. The 70 race variants were
installed with `refit_race_headwear.py install`, and its audit passes all 80
assets. Every image matched a shipped texture, so there are no new textures.
The registry and catalogue entries are byte-identical: scenes and sockets are
unchanged. Godot's import was refreshed, and the seven creature `.import`
files it rewrites were reverted.

Tests:

- The equipment, remapper and held-prop suites fail on the same 9 IDs as
  clean develop at `224bb9b9`. `test_race_headwear_clearance.py` passes (4
  tests, 1,968 subtests).
- `creation_class_equipment_fit.gd` (54,666 checks), `torso_body_cover.gd`,
  `character_appearance_fit.gd` (785 checks, helmets cover and restore hair),
  `equipment_fit_profiles.gd`, and the registry snapshot, imported-actor LOD
  and torso LOD tests pass.
- `armour_body_cover.gd` reports the same 60 "restores sculpted hair
  visibility" failures under helm 3:120 as before, line for line.

Evidence: [the seven notes](design-fit/review-fixes-headwear.jpg), each the
owner's view beside the installed fix, reshot with `--replay`; [hood fronts
and the Leather Helm](design-fit/review-fixes-hood-fronts.jpg), three-quarter
front, both bodies, before (the collar fix) and after.

**Hole above the forehead under the Leather Helm (second review, note 3).**
The owner then saw, from a low front camera, "a hole in the top of the head"
through which the inside of the helmet showed. It is not from the rescale:
the old helm shows the same hole. A "hide" helm hides the scalp with the hair
and the race features. The head is then open above the face skin's top edge,
the jagged hairline, and under an open brow that stands off the forehead a
camera that looks up sees past that edge into the helm. A hood already keeps
its scalp for exactly this reason. The policy table therefore gains an
optional `scalp: "show"` for open-faced helms, set on the Leather Helm and
copied into `equipment.json` as `models["3:134"].scalp`. With it,
`_race_feature_hides` still hides the hair and `race_feature_head` but keeps
the scalp. The race passes then count the scalp as head the helm must clear,
and the measure gate already reports scalp poke. The scalp comes through the
Leather Helm on none of the 16 bodies (0 cm², both Human bodies and the 14
races). Refitted with the scalp in the race push, every variant came out
byte-identical, so no GLB changed. `race_feature_visibility.gd` used this helm
as its example of a helm that hides the scalp; it now checks that the Leather
Helm keeps it, and the Phoenix Helm (closed, still `hide`) for the hiding
case: 892 checks, no failures. `armour_body_cover.gd` expects the kept scalp;
its 60 failures are the same lines as before. `character_appearance_fit.gd`
passes, and `test_race_headwear_clearance.py` checks the new field against
the table. Evidence: [note 3](design-fit/review-fixes-helm-scalp.jpg), the
owner's shot and the reshoot, and the female body from the same view.

**Not yet done.**

- Only the five noted pieces have a headwear.json row. Each cowl is shaped
  over its own kit's collar. Worn over another torso with a tall collar it can
  cross that collar, as any hood could before. Other helms keep head_frame's
  fit, which clears every ray by 9 mm and so reads large wherever a design has
  cheek or nape guards.
- Other open-faced helms with policy `hide` may show the same opening above
  the forehead. Give them `scalp: "show"` once `refit_race_headwear.py
  measure` shows no scalp poke on any body.
- When the head turns hard against the chest (Bow_Pull_Back, the sword
  swings), the tall kit collars still show beside or through the hoods, as
  they did before. A skinned cowl reduces this but tears; cloth simulation or
  a collar that follows the head more would be needed.

### Owner's second review (2026-10-17)

A second review (22 notes, at commit `ac868b73`, session
`equipment-review/2026-10-17_18-18-43`) covered all five sets again. Note 3,
the hole through the Leather Helm's crown, is the headwear section's
(`54e7b083`). Note 2, the cape's curve, has its own section below. The
other 20 are addressed here, on all 15 design-fit pieces and both Human bodies.

**Arm holes and shoulder seams (notes 1, 4, 6, 9, 12, 14, 16, 18, 20).**
`bind_sleeves` used to switch from the arm field to the coat's weights in one
step, with the sleeve/coat bridges cut below the shoulder yoke. In idle and
walk the arm slid through the coat's arm hole. In a drawn bow the cut seams
opened onto the skin (Furtrim Coat, notes 14, 16, 18) or let a torn sleeve
strip hang (Phoenix, note 20). Now, over a band 5 cm wide on the sleeve and
6 cm on the coat (surface distance from the seam), each side takes a share of
the other's weights, half at the seam, and the seam stays sewn. The arm hole
moves with the arm. Only seam triangles that the fit has already stretched past
1.6× their drawn size in idle are still cut, 0–16 per torso; the lining
shows behind them. On the Scout Vest and the Studded Jack, the sleeve art at
the back of the upper arm that stood outside the coat's own trunk art moves
just inside it (`tuck_sleeves`, at most 4 cm): the shirt sleeve no longer
comes through the vest's back shoulder (note 9), and the jack's arm hole wraps
the sleeve at the back (note 1).

Sewn seams stretch where cut ones used to open, so `stretch_check.py` counts
more stretched triangles in Bow_Pull_Back than after the first review. The
sewn seams show no gaps, skin or hanging strips in the noted views. The
Studded Jack keeps a small flap at the front of its arm hole (note 6).

| Torso | Male, first review | Male now | Female, first review | Female now |
| --- | ---: | ---: | ---: | ---: |
| Studded Jack | 0.94% | 4.29% | 0.81% | 3.57% |
| Scout Vest | 0.35% | 3.12% | 0.21% | 2.71% |
| Acolyte Tunic | 0.71% | 3.47% | 1.11% | 4.17% |
| Furtrim Coat | 0.64% | 2.63% | 0.64% | 2.40% |
| Phoenix Cuirass | 1.15% | 1.80% | 1.40% | 2.02% |

**Trousers through the coat's back (notes 5, 10, 17, 21).** The legs specs
now tuck the trousers into the set's torso as well as its boots (`tuck_into`
takes a list): rays from the pelvis and thigh axes. The tuck is limited to the
back (bearings 110–250°), and a vertex that would have to move more than 4 cm
stays put. Tucked all round, it pushed the Sidelace Breeches' belt and buckle
under the Scout Vest, though they are drawn over it, and crushed the Furtrim
Legguards' front fur flaps by 14 cm.

**The crotch and the seat (notes 7, 10, 11).** The debug tint showed the dark,
"wet" patch to be the trousers' lining and reconstructed inseams. They were
drawn in one flat colour with flat normals, wherever the Meshy art leaves a gap
between the legs. Both now wear the trousers' own material and texture
(`limb_head_remap.wear_art`). Each triangle takes the texture island of the art
nearest its centre, and each corner the UV and normal of the nearest art
vertex in that island; no UV blends across the two legs' islands. The leg
`Backing` material is no longer written; boots keep theirs.

**The waist turning with the chest (notes 13, 15).** A trunk vertex took the
weights of the body surface nearest it: pelvis up to about 1.12 m, with no
spine_01 at all. So the belt and everything below it stayed with the hips while
the chest turned. The clips turn the chest mostly at spine_03 (65° in
Bow_Pull_Back, with spine_01 turning the other way). `twist` caps the pelvis
share on a ramp from half at the hip joint to none at spine_02, and gives the
rest to spine_02 and spine_03 (40/60). Share of the chest's turn that the belt
and the hem follow (`twist_check.py`, male):

| Torso | Run_Female belt | hem | Bow_Pull_Back belt | hem |
| --- | ---: | ---: | ---: | ---: |
| Studded Jack | 0.64 | 0.22 | 0.56 | 0.21 |
| Scout Vest | 0.65 | 0.26 | 0.59 | 0.22 |
| Acolyte Tunic (belt before: run 0.18, bow 0.07) | 0.54 | 0.36 | 0.44 | 0.26 |
| Furtrim Coat (belt before: run 0.13, bow 0.05) | 0.64 | 0.22 | 0.53 | 0.17 |
| Phoenix Cuirass | 0.46 | 0.28 | 0.35 | 0.21 |

**Cuffs on the wrists (note 22).** In idle the Phoenix cuff's ring stood 4–5 cm
in front of the wrist. The forearm bone's similarity carries a cuff drawn off
the middle of the concept's sleeve that far off. Moving the design bone's tail
onto the art's cuff ring was tried first and was unreliable: coat art beside
the wrist pulled the centroid. `centre_cuffs` measures the result instead:
in the posed shell, the centre of the art each forearm bone owns in the last
20% of the segment, against the forearm surface there. It takes the difference
off that art, fully at the cuff and fading to none at 35% from the elbow.
Distance of the sleeve end's centre from the wrist's, in idle:

| Torso | Male l / r | Female l / r |
| --- | ---: | ---: |
| Phoenix Cuirass (before: 42 / 27 male, 45 / 45 female) | 6.8 / 6.7 mm | 5.8 / 7.5 mm |
| Studded Jack | 13.7 / 11.8 mm | 14.9 / 8.3 mm |
| Scout Vest | 14.8 / 18.1 mm | 18.3 / 24.9 mm |
| Acolyte Tunic | 7.7 / 10.1 mm | 9.3 / 11.3 mm |
| Furtrim Coat | 28.0 / 9.7 mm | 26.2 / 19.7 mm |

**The Laced Fieldboots' shaft (note 8).** In idle the shaft stood 2.5–3.6 cm off
the front of the shin, and the calf came through its back by up to 2 cm. The
calf bones now also clear the default trousers' calf (girth cap 1.25), and the
shaft's top sits 3.5 cm further back with its shift held to 1 cm. The back now
clears the calf on both bodies (male within 1 mm, female 12–39 mm). Over the
shin the gap is 0.3–2.8 cm; the 3.4–3.9 cm left at the instep is the boot's
tongue as drawn.

**The grey patch below the Phoenix belt (note 19)** no longer appears at the
noted view, at five times through Fighting_Idle.

The viewer's `--debug-tint` now also draws reconstructed inseams green.

Tests, with all 15 pieces installed:

- The equipment, remapper and held-prop suites fail on the same 9 IDs as
  develop at `224bb9b9`.
- `torso_body_cover.gd` passes: 16 races, cover and equip/unequip.
- `creation_class_equipment_fit.gd` passes: 54,666 checks on 16 rigs.
- The torso LOD, imported-actor LOD and registry snapshot tests pass.
- `armour_body_cover.gd` keeps its 60 scalp lines (helm 3:120), as above.

The equipment `textures/` folder keeps only its six older orphans.

Evidence, installed before and after on each noted view, reshot with
`--replay`: [arms and shoulders](design-fit/review2-arms.jpg) and
[waist, crotch, cuffs and boots](design-fit/review2-waist-cuffs-boots.jpg).

**Not yet done.**

- The Furtrim Coat still shows two small dark notches near its back hem
  (note 17), where the fur band used to cover them. Shards of the legguards'
  fur stay in the coat's back slit.
- A small light shard shows above the Phoenix belt at the back (note 21).
- The Studded Jack's arm hole keeps a small flap at the front in the bow
  (note 6). The Furtrim Coat's left cuff is still 2.6–2.8 cm off the wrist.

### The cape's hang (second review, note 2)

The owner noted that, in idle, the Vanguard cape flared out at the top of the
back and then followed the legs near the hem. The bare chest showed the same
curve. The cause was in the cloth solver, not in the chain roots:

- Each chain simulated its *material line*, a plumb line from the chain's root
  bone, which sits on the spine about 10 cm in front of the cloth. The trunk
  capsule pushed that line out to its surface, and the cloth then hung 10 cm
  further out again. The capsule is round, and its reach came from the worn
  torso's flanks: the Studded Jack stands 0.29 m from the spine at 60–90°
  but only 0.15 m straight back. Over the jack, the middle of the cape stood
  12 cm off the armour.
- Below the shoulders, the bone write kept the cape's bind shape. That shape
  was conformed to the bare body, and below the seat the cloth sits 7–11 cm
  further in, against the thighs and calves.

Fix (`cape_cloth.gd`, `cape_drape.gd`, `replicated_actor_3d.gd`):

- `CapeDrape.fabric_line` measures where each chain's cloth hangs behind its
  material line at each joint. It is measured once per rig, cape and torso,
  in rest space. It reads the middle half of the sheet in a 10 cm strip,
  using only cloth that the chain itself carries, so the line starts where
  the rigid yoke lets go.
- The solver hangs that line plumb (`set_fabric_line`), collides it, and turns
  each link from its own cloth's authored direction, which straightens the
  lean onto the legs. With no line it is the old solver: with the line
  cleared, both frozen baselines match to 1e-6 through Walk, an attack, a
  teleport and a reset.
- The trunk and waist reach counts only armour within 45° of straight back
  (the chains hang within about 40°), held 2 cm off. The waist capsule's cap
  also counts what hangs up to 20 cm below the pelvis: coat tails and plate
  skirts, where the cape's middle joint is.
- The native kernel is handed the measured line as its rests. The bone write
  is shared GDScript, so the kernel itself is unchanged.

Depth change of the cape's middle (cloth within 10 cm of the spine) from just
below the yoke to the calves, Idle_Subtle at 2.03 s. A positive change means
the cape comes in toward the legs:

| Wearer | Before | After |
| --- | ---: | ---: |
| Bare chest | +85 mm | +10 mm |
| Studded Jack (noted) | +90 mm | +10 mm |
| Scout Vest, 184, 213, 197 | — | −1 to +10 mm |
| Phoenix Cuirass | — | −9 mm |

Armour through the cape's sheet, using the over-armour fixture's measure on
the solver's own output (same pose): Scout Vest 17 → 17 mm, 184 8 → 8 mm,
213 2 → 0 mm, 197 0 → 6 mm, Studded Jack 0 → 0 mm, Phoenix 63 → 35 mm. In the
back three-quarter view, the Arcanist's tunic tails no longer come through
the cape at the seat. Other races (Stoneborn, Ssarathi, Orun, Mycelari,
Glasswarden) and the female body hang the same way. Evidence:
[note 2 and the synthetic views](design-fit/review2-cape.jpg).

Tests:

- `test_cape_cloth.gd`, `test_cape_drape.gd` and `test_actor_render_quality.gd`
  pass.
- `rendered_cape_clipping.gd` passes. None of its three attacks
  (`Sword_Attack`, `Attack_Ground_Pound`, `Punch_Cross`) existed in the
  animation map, and it skipped missing clips, so it used to pass without
  swinging at all. It now swings `Combat_Slash_A` and `_B`, and a missing
  clip fails it. Both clips read the same: the cape stays 98 mm behind the
  spine plane (40 mm ahead is allowed), and does not rise above the anchor.
  Offline, the rise reads about zero for any solver, as this harness's
  gravity is delta-driven.
- `test_cape_idle.gd` passes. Its new check, "hangs plumb from the back"
  (under 40 mm), measures 0.3–10.3 mm on both bodies; the old solver gives
  85–90 mm.
- `test_cape_cloth_pose_cache.gd` and `test_cape_cloth_capsule_cache.gd`
  pass, and the frozen baselines are unchanged (the owner's call). The harness
  now clears the measured line on the live solver, so parity guards the
  material-line arithmetic the baselines were reviewed on. With the line live,
  the solver diverges from them, as intended. The rig never had the
  `Sword_Attack` clip, so the harness's real-actor sequence used to be
  skipped; it now swings `Combat_Slash_A`.
- `test_cape_cloth_native_constraint.gd` (17 checks) and
  `test_native_presentation_modes.gd` fail only because this checkout has no
  built native extension (`bin/`).
- `rendered_cape_over_armour.gd` and its `_baseline` variant fail with the
  same numbers for the new and the frozen solver. The fixture measures after
  a frame, by which point the solver's output is gone from the pose. Its
  collar band (74–159 mm) is the rigid yoke, which this change does not touch.

Scratch views, probes and scripts are in the client
`.local/asset-authoring/working/equipment-cape-2026-10-17/`.

**Not yet done.**

- The Phoenix Cuirass's tail still shows 35 mm into the sheet at the seat.
- The native kernel path was not run here.

### Owner's third review (2026-10-17)

The third review (14 notes, at `aa5709ca`, session
`equipment-review/2026-10-17_22-12-25`) covered the four kits and Phoenix
again, and found that the viewer's weapons and cape did not appear.

**The viewer's weapons and cape.** The toggle works: clicked through the real
UI on every set, it adds each set's own pieces. These are the Vanguard's
Militia Arming Sword, Wooden Round Shield and cape, the Ranger's Amberwood
Yew Longbow, the Arcanist's Arcane Focus Wand, and the Warden's Fighting
Quarterstaff and cape. The Phoenix set, from `review_sets.json`, had no
weapon or cape at all, and the Default clothes have none, so the toggle
showed nothing there. The Phoenix set now carries the Phoenix Feather Spear
(0:189) and the Red Cape (2:12). The status line names what the toggle adds,
or says the set carries none. The kits carry no arrows or quiver, so none
show. Evidence: [toggle on, each set](design-fit/review3-viewer-weapons-cape.jpg).

**Holes at the groin and seat (notes 1, 2, 11).** Meshy's trousers leave a gap
between the legs, and the trousers' lining and reconstructed inseams fill it.
Drawn in the trousers' texture (second review), each corner took its own
nearest art vertex's UV, so the fill smeared into dark shards and read as a
hole. A per-triangle texture map did no better: the texture round the gap is
patchy. The lining and inseams are now one plain cloth colour, the median
texel under the art within 12 cm of the midline between 0.70 and 1.00 m
(`limb_head_remap.crotch_colour`), with the art's own roughness and their own
smooth normals. The gap reads as cloth. A few light slivers of the art's own
inner edge still show at its border on the Sidelace Breeches (note 11).

**Trousers through the coat (notes 3, 6, 13, 14).** Two causes.

- The back tuck skipped any vertex that would have had to move more than
  4 cm. The Kneecops' waist stood up to 8 cm proud of the jack's back hem
  (note 3), the Furtrim Legguards' back fur up to 7 cm out of the coat's back
  slit (note 13), and the Phoenix Legguards' hip panels rose to the
  cuirass's belt at the back (note 14). Those three now tuck up to 8 cm.
  The Kneecops also tuck at the front (note 6): their belt, drawn over the
  jack's front, came through its skirt in a walk, so it now sits under the
  jack, which keeps its own belt.
- The waist `twist` capped the pelvis weight down to the hem, so in a walk
  the skirt turned toward the chest while the thighs drove through it. It now
  starts at the belt (`free_below`, 0.98 m) and leaves the hem with the hips.

Share of the chest's turn the belt and the hem follow (`twist_check.py`,
male):

| Torso | Run belt | Run hem | Bow belt | Bow hem | Walk belt | Walk hem |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Studded Jack | 0.57 | 0.10 | 0.49 | 0.05 | 0.73 | 0.06 |
| Scout Vest | 0.52 | 0.12 | 0.43 | 0.06 | 0.78 | 0.08 |
| Acolyte Tunic | 0.41 | 0.19 | 0.26 | 0.12 | 0.69 | 0.23 |
| Furtrim Coat | 0.50 | 0.10 | 0.38 | 0.04 | 0.87 | 0.06 |
| Phoenix Cuirass | 0.35 | 0.15 | 0.24 | 0.09 | 0.65 | −0.13 |

**The torso's sides in a drawn bow (notes 7, 8, 9, 12).** Two causes.

- Blended under the arm as well as over it, the coat's side followed the
  raised arm and stretched into a smear across the flank (7, 8, 12). The seam
  blend now fades with `shoulder_top`: full over the top of the shoulder,
  none under the arm. There the sleeve follows the arm alone and the seam's
  bridges open again, as before the second review.
- The fitted lining kept its own arm field and the body's waist, while the art
  over it was bound differently, so in the bow and the walk it came through
  the coat's sides and back. Each lining vertex now takes the weights of the
  art it lies under (`torso_remap.art_lining_weights`), except over the
  forearm's last stretch, which holds the wrist skin.

Share of art triangles stretched past 1.8× in Bow_Pull_Back:

| Torso | Male, second review | Male now | Female, second review | Female now |
| --- | ---: | ---: | ---: | ---: |
| Studded Jack | 4.29% | 2.31% | 3.57% | 1.70% |
| Scout Vest | 3.12% | 1.03% | 2.71% | 0.62% |
| Acolyte Tunic | 3.47% | 1.74% | 4.17% | 2.22% |
| Furtrim Coat | 2.63% | 1.48% | 2.40% | 1.67% |
| Phoenix Cuirass | 1.80% | 0.41% | 2.02% | 0.41% |

**The Studded Jack's shoulders (notes 4, 5).** `split_limbs` gave the jack's
studded shoulder cap to the sleeve, so it was carried and stretched with the
arm and its studs smeared away (note 4). In the bow the jack's side folded
into a strap shard (note 7). Seeding the jack's trunk on a strip 20 cm wide
instead of 12 (`trunk_seed_x`, Vanguard only) keeps the cap with the jack.
The studs now run continuously over the shoulder, and the shoulder edge is
clean in the walk (note 5).

**Holes at the top of the Ranger's shoulder (note 10).** Four seam triangles
over the top of the Scout Vest's shoulder were cut because the fit stretched
them in idle, and the lining showed through from above. Seam triangles over
the top of the shoulder (`SHOULDER_SEWN`) now stay sewn.

Evidence, before (as installed at the review) and after, on each noted view:
[trousers](design-fit/review3-trousers.jpg) and
[shoulders and sides](design-fit/review3-shoulders.jpg).

**Tests against clean develop.** The suites ran on this branch with all 15
pieces installed, and on a clean worktree of develop at `224bb9b9`, the commit
this branch started from:

| Suite | Branch | Develop `224bb9b9` |
| --- | --- | --- |
| Equipment, remapper and held-prop pytest | 9 failed, 70 passed | the same 9 IDs |
| torso_body_cover, LOD, registry tests | pass | pass |
| creation_class_equipment_fit | 54,666 checks, 0 failures | 52,202 checks, 0 failures |
| armour_body_cover | 60 failures (scalp under 3:120) | the same 60 |
| test_cape_cloth, test_cape_drape, test_cape_idle, rendered_cape_clipping | pass | pass |
| test_cape_cloth_capsule_cache, test_cape_cloth_pose_cache | pass | 2 failures each |
| test_cape_cloth_native_constraint | 17 failures | 19 failures |
| rendered_cape_over_armour | 4 bodies clip | the same 4 bodies |

The native-constraint failures on both are the missing native extension
(`NativeCapeConstraintKernel`). In rendered_cape_over_armour, bodies 184, 213
and 197 clip exactly as on develop. Body 225, the Scout Vest, clips the cape's
lower sheet by 69 mm, where develop shows none; it did so already at
`aa5709ca`, before this round. Its collar reaches 160 mm into the cape, against
141 mm at `aa5709ca` and 120 mm on develop.

**Not yet done.**

- **Note 9 (Ranger's right shoulder in the bow).** The vest's shoulder and
  the shirt sleeve still part at the top of the raised arm. The lining shows
  there; it is the sleeve's colour, so it reads as cloth.
- **Note 5 (Studded Jack, walk).** The cap is clean, but at the back of the
  upper arm the sleeve art parts in the swing and the sleeve-coloured lining
  shows.
- **Note 11.** Light slivers of the Sidelace Breeches' own inner edge at the
  border of the crotch fill.
- The Kneecops' front belt is now hidden under the jack. Restoring it would
  mean refitting it to ride over the jack's skirt.
- The Scout Vest came through the cape in rendered_cape_over_armour. Done
  on 2026-10-18 (see **The Scout Vest under a cape (2026-10-18)**): the vest's
  back tail, 25 cm behind the body at 0.82 m, is now held in with `hug`. The
  tail's 69 mm is gone from the fixture, and its part of the 17 mm on the
  solver's own output is gone too. What remains is 18 mm at the back of the
  shoulder, at the cape's side edge. It was there before as well, and it is
  within the fixture's tolerance.

### The cape in the owner's fourth review (2026-10-18)

Four notes, taken at `619a19f8` with the viewer's weapons and cape on
(session `equipment-review/2026-10-17_23-42-13`). The owner asked for notes
1–3 to be judged against the cape moving as it does in play, not in a frozen
frame.

How it was measured: for each frame, the furthest any arm, leg or weapon
vertex stands outside the cape's sheet. That is the distance past the
nearest cape vertex that a chain carries, outward from the spine. The rigid
yoke, which armour may stand through, is not counted, and nor is anything
within 3 cm of the cape's border. The cloth runs over a whole clip cycle.
"Moving" means the actor travels at the client's own speeds, with the clip
played at the speed the client would play it:

- walking: 1.67 m/s, Walk at 2.18×;
- running: 5.0 m/s, Run_Female at 1.81×.

The Warden's sleeves read up to 13 mm in idle, which is this measure's floor.

| Note | In place (the viewer) | Moving, whole cycle |
| --- | ---: | ---: |
| 1. Warden, Run_Female 0.59 s, arm | 35 mm (worst 38) | 0 mm |
| 2. Warden, Run_Female 0.28 s, leg | worst 40 mm | 0 mm |
| 3. Warden, Walk 0.06 s, hand | 38 mm (worst 38) | 0 mm |

**Notes 1–3 are motion-only and are left as they are.** The viewer played a
run or a walk on the spot, so the cloth never saw the actor travel. In
motion the cape streams back off the arms, legs and hands at both noted
times and through every sample.

The viewer now has a travel option (see **Reviewing fits in the client**).
`--replay notes.jsonl --notes 1,2,3 --travel yes` reshoots the three views
with the actor moving, and the cape streams clear of the arm, the leg and the
hand: [in place and travelling](design-fit/review4-travel.jpg).

**Note 4 (Phoenix set, Red Cape 2:12, Fighting_Idle 0.01 s) is fixed.**

The leg capsules ran hip to knee, so nothing collided the shins. In the
fighting stance the back leg's shin and greave stand behind the hem. With
the solver before the second-review fix the result was the same: 25 mm at
the noted frame and 37–40 mm over the cycle.

What changed (`cape_cloth.gd`, `cape_drape.gd`, `replicated_actor_3d.gd`):

- After the solve, the measured cloth line is kept off both shins, knee to
  ankle, the same way in both solvers. The native kernel takes four capsules
  and no more, so it is handed the same rests as before and the shins are
  handled afterwards in GDScript.
- Each chain point stands for the cloth 7.5 cm either side of it, and for
  that cloth's inner folds. `CapeDrape.fabric_line` now measures the folds:
  2–8 cm in front of the line.
- Links are also checked at their thirds. A link from beside the knee to
  below the calf had passed through a shin with both ends clear of it.
- Points move straight back, away from the chest, so a chain does not slide
  across its neighbour.
- `CapeDrape.shin_reach` measures each shin's reach per rig and per worn
  torso, legs and boots. It counts the body's own calf and whatever is worn
  over it, on that leg's side only, per 15° of bearing from the leg's back.
  A single radius was the round-capsule problem again: an Amberwood knee flap
  stands 0.31 m straight back, and as a single radius it bowed an idle cape
  45 mm. The other leg's back flap also had to be kept out.
- This applies only to a measured line, and never to a mounted rider.
- A change of legs or boots re-tells the cloth.

Results:

- Note 4: 0 mm at the noted frame. Over the cycle the worst is 17 mm, at
  0.70 s, and 11 of 52 samples are over 10 mm (before: all 52).
- The test kit's Amberwood legguards (4:171) stood 20–24 mm through the hem
  in idle. They now read 0 mm, and the cape drapes 15–45 mm out over the
  knee flap.
- The note-2 view (Vanguard) is unchanged within 3 mm.
- Cost: 110–140 µs per step with a measured line on the Phoenix kit, against
  58–82 µs without it (debug build, headless).

Tests:

- `test_cape_idle.gd` passes. Its check is now one-sided: the cape must not
  come in toward the legs. Being pushed out over leg armour is draping.
- These pass:
  - `test_cape_cloth.gd` (52 µs, under its 200 µs budget) and
    `test_cape_drape.gd`;
  - both parity suites (the shins act only on a measured line, which the
    harness clears);
  - `test_actor_render_quality.gd`;
  - the mount suites `test_mounted_cape.gd` (44 checks),
    `test_mounted_player.gd` (1,130) and `test_mount_preview_state.gd` (39),
    with no failures.
- The native suites fail only because the extension is not built here.

Evidence: [note 4, the idle drape and notes 1–3 in motion](design-fit/review4-cape.jpg).
Scratch harnesses: the client's
`.local/asset-authoring/working/equipment-cape-2026-10-17/review4/`.

**Not yet done.**

- Note 4 still reads up to 17 mm at a few frames of the Fighting_Idle cycle.
- Arms are not collided with the cape's sides. In place, a swinging elbow
  passes through them (notes 1 and 3); in motion it does not.

### The Scout Vest under a cape (2026-10-18)

Since the first kit fit (`b4ee06ed`), the refitted Scout Vest (5:225) has
come through a worn cape at the seat. The concept draws the vest's back
flaps flared out behind. Carried onto the body, the flaps' corners at the
centre vent stood 13 cm behind the seat at 0.83 m on the male (z −0.23 m)
and 11 cm behind it on the female (z −0.20 m). This is the 69 mm that
rendered_cape_over_armour reported 0.40-0.50 m below spine_03. On develop
before the kits (`224bb9b9`) the sheet read 0 mm.

**The fix.** The Ranger torso spec now carries the design fit's `hug` key:
design bone `trunk_lower`, the back arc 125-235°, heights 0.55-1.25 m,
`start` 6 cm, `max` 12 cm. The key comes from `98dcef4b` (equipment audit,
Sunmane batch 1). Only its two tool files were brought over (`0d9f185f`),
unchanged, and its batch was not. The kits' `make_specs.py` writes the key.
`hug` caps how far art stands off the body behind a bone. A vertex's standoff
d over the body (default clothes included), measured from the bone's posed
axis, becomes `start` + (`max` − `start`) tanh((d − `start`) / (`max` −
`start`)). The map is monotonic, so layers keep their order.

Two pieces were refitted on both bodies and installed: the vest, and the
Sidelace Breeches (4:230), whose back tucks under it. The Laced Fieldboots'
design fit changed only in its recorded spec hash; their GLBs are untouched.
`share_human_equipment_textures.py` reused the shipped textures, so the
registry and the catalogue are unchanged.

**Why 6/12 cm, not the Sunmane 3/6 cm.** The breeches' seat stands about
5 cm off the body. At 3/6 cm the flaps went up to 71 mm inside the breeches'
back: 85% of the tail's vertices lay behind it. At 6/12 cm, 98% lie over the
breeches (median 16 mm out), and the offline measure still clears the
fixture's sheet.

**What it costs.** Below the pelvis joint `trunk_lower`'s axis ends, so the
pull runs up as well as in:

- The vent corners rise 36 mm on the male (lowest point 0.834 → 0.870 m) and
  21 mm on the female (0.828 → 0.849 m).
- The flaps now hang straight down the seat, and the back hem runs level
  where it used to dip toward the vent.
- The vent still shows the breeches about as much as before (owner's second
  review, note 10).
- At 3/6 cm the corners rose 66 mm and curled under the seat.

| Male, body 225 | Before | After | Develop `224bb9b9` |
| --- | ---: | ---: | ---: |
| Flaps' furthest back (z, within 15 cm of the centre line) | −0.230 m | −0.186 m | — |
| rendered_cape_over_armour, sheet | 69 mm (tail) | 18 mm (shoulder) | 0 mm |
| The same, tail bands (−0.40 to −0.50 m) | 69 / 44 / 34 mm | 0 | 0 |
| Solver's own output, Idle_Subtle 2.03 s | 17 mm (tail 17, shoulder 17) | 18 mm (shoulder) | — |
| rendered_cape_over_armour, collar | 160 mm | 160 mm | 120 mm |

The solver row is the cape session's `armour_measure.gd` on the full Ranger
kit. On the solver's output the cape stands further back at the seat
(−0.22 m at 0.80 m, against −0.16 m in the fixture's bind hang), so there the
tail only reached 17 mm.

**What remains is not the tail.**

- **18 mm at +0.10 m.** This is the back of the shoulder, at the cape's side
  edge (bearing 40-50°). It is most likely the lining at the sleeve root:
  the design-fit art alone, scored against the same cape, does not reach the
  cape there. It was 17 mm before, it is within the fixture's 20 mm sheet
  tolerance, and `hug`'s band does not reach it.
- **The collar** (+0.15 to +0.25 m). It measures 140 mm headless and 160 mm
  windowed on the same fit, since the fixture's idle phase depends on the
  frame rate. Scored offline against one cape, the vest's design-fit shells
  read 125 mm up to `04109b51` and 146 mm from `8da16322` on. That commit added
  the `collar` key, which brings the collar's back out of the nape at the
  owner's request (the hood/collar gap). The fixture allows the collar band
  to stand through the cape, and all four bodies exceed its 55 mm tolerance
  on develop as well.

Checks:

- Stretch: share of art triangles past 1.8× and past 2.5×.
  - Bow_Pull_Back: unchanged on the vest (male 1.03% and 0.41%, female 0.62%
    and 0.07%).
  - Run_Female, male: the vest goes 0.76% → 0.97% past 1.8× but 0.28% → 0.14%
    past 2.5×; the breeches go 0.80% → 0.92% past 1.8×, with 2.5× unchanged.
  - Female breeches in the bow: one triangle past 2.5×.
- The Buckled Hood (3:159) was shaped against this vest. Its clip check is
  identical with the old and the new vest in all eight clips, on both bodies
  (hood through the vest, collar over the hood, hood through skin, stretch).
  The design fit moved nothing above 0.99 m, so the hood keeps its installed
  fit.
- The owner's Ranger notes were replayed with the old and the new vest
  (second review notes 8-12, third review notes 9-11). They are unchanged,
  except that in second-review note 10 and in side views the flaps no longer
  stand out behind.

Tests, compared by failing ID with a clean develop worktree at this branch's
develop base, `82ae2326`:

| Suite | This branch | Develop `82ae2326` |
| --- | --- | --- |
| Equipment, remapper and held-prop pytest | 9 failed, 70 passed | the same 9 IDs |
| torso_body_cover, LOD and registry snapshot tests | pass | pass |
| creation_class_equipment_fit | 54,666 checks, 0 failures | the same |
| armour_body_cover | 60 failures (scalp under 3:120) | the same 60 |
| test_cape_cloth, capsule and pose caches, drape, idle; rendered_cape_clipping | pass | pass |
| test_cape_cloth_native_constraint | 17 failures (no native extension here) | the same 17 |
| rendered_cape_over_armour | 4 bodies flagged on the collar; 184 also on its sheet (24 mm) | the same, and 225 also on its sheet (69 mm) |

Evidence: [the fixture's back and quarter views, side and back views of
both bodies, and note 10](design-fit/vest-hug-cape.jpg). Scratch (offline
measure `score.py`, the dump harness, trials, replays): the client's
`.local/asset-authoring/working/equipment-fit-2026-10-17-kits/hug/`.

## Two body shapes, preserved race identity

There are **two body equipment fits**, with 200 torso/leg/boot designs each,
and 64 headwear designs fitted to each of the sixteen retained heads: 1,424
equipment GLBs in total. The client still loads sixteen assembled race GLBs;
each contains the common body plus its individual head and optional tail.
This is geometry reuse in authoring, not a runtime modular-head loader.

The source Luminous shoulders, armpits, female chest and limbs are preserved
outside the localized neck transition. All bodies keep the same ordered 77
joints, inverse binds and canonical Rest_Pose. Head rest Y is
`1.5684900288581848`; pelvis rest Y is approximately `0.916700`.
Idle_Subtle, Walk, Jog, Run_Female and Fighting_Idle, runtime run selection,
hairFit, original head features and the Ssarathi pelvis-bound tail are retained.
Whitehorn uses `votary`. Mycelari eyebrows remain absent.

The neck joins the common upper chest to the retained head with several
anatomical rings. Boundary copies have identical positions, normals and skin
weights; all sixteen reports have zero unmatched boundary edges and zero
attribute deltas. A continuous cylindrical texture blends into the retained
head boundary. The original shirt collar is restored as a separate wardrobe
surface on unequip. Geometry is approximately 20,000 triangles per assembled
body. Original source triangles, UVs and skinning outside the explicit cut
remain intact, as verified by triangle-level comparison.

## Equipment fitting and visibility

Torso remapping measures source trunk walls, separates sleeves from the medial
seam and poses each source part into canonical limb frames. Per-band surface
envelopes fit the chest without parity saturation on overlapping closed shells.
Short ornaments travel whole. Low hem tabs stay with the trunk. The three
previously requested raised collars retain their 45 mm lift.

Original armour positions, normals, UVs, indices, texture bytes and skin weights
in the final neckline revision match all 128 reviewed male/female torso fits
exactly. They were rebuilt from original sources using the verified original
canonical Luminous templates as stable anatomical skin samples. Only the
replacement lining follows the reconstructed neck surface. This prevents new
neck tessellation from changing sleeve/plate weight inheritance.

The lining's central neckline is clipped before thickening, with the shoulder
coverage retained. This removes folded backing shards at the throat. Runtime
coverage keeps neck skin, hides the old shirt collar and preserves the default
torso region when adding that collar region. Body cover changes private index
buffers only; exact mesh/material restoration on unequip is tested.

Leg and boot fitting use original source parts, weighted foot chains and
continuous garment weight fields. Tail vertices cannot supply foot landmarks
or garment weights. The reported Bark Legguards 49.6 mm hem came from backing;
the test now measures original visible art, verifies that it clears the foot
and checks overlap with its matching boot. It does not merely loosen the old
absolute bound. Boot sink and floating limits are checked against each weighted
sole, including the former Amberwood 01 failure.

Lowercase split surfaces are selected explicitly. Shared attribute accessors
are read once and their relevant face buffers are united. Wardrobe samples
participate in fitting. Both authoring and runtime use the current head rest
reference for canonical fits. `fitProfiles.legacy` retains the old `1.5998`
reference for existing socketed props and applies its approximately `0.980429`
compensation once. Matching body templates bypass additional girth and sole
correction; slimmer bodies do not depend on the legacy `[1,2]` clamp.

BodyGirth, footAnchor, soleDrop and fitGroups were measured again. Shared-body
soles are approximately 2.56/0 mm for males and 0.72/0 mm for females. Per-race
stature remains an actor transform. Per-surface skin tints, wardrobe normal
grow, matching combined-set backings and lining variants remain active.
Closed headwear hides/restores hair and scalp; open bands preserve hair.

## Measurements and tests

Independent front-depth measurements use the actual current bodies. These
are distinct from the older 68% headline baseline on previous bodies.

| Template | Median covered chest width | Worst covered width | Proud cells, with backing |
| --- | ---: | ---: | ---: |
| Male | 100% | 95.008% | 407,751 |
| Female | 100% | 95.497% | 403,756 |

The final neckline change adds one male proud cell and leaves the female count
unchanged. Original-art proud counts remain 403,277 and 399,931 respectively;
original-art worst widths are 88.240% and 92.014%. The fitted backing fills the
remaining designed openings. Original-source, true-scale worn and gameplay
images are supplied separately so coverage cannot conceal silhouette errors.

Installed validation:

- 48 equipment/fitter tests pass, including all declared variants and boot/hem checks.
- 15 relevant body/binding tests pass, with 2,256 passing subtests.
- Animation looping passes.
- Torso cover and equip/unequip pass on all sixteen races.
- Combined armour passes 528 transitions and 1,144,460 checks.
- Fit profiles pass 23,205 checks, including material restoration and legacy sockets.
- Historical torso tests retain thirteen existing failures; sorted full identifiers
  with multiplicity show no new failures. The flat-decoration classifier failure
  is resolved. Retired visual-ID assumptions remain in that historical suite.

All sixteen changed bodies were replayed through five complete locomotion
cycles using FK and linear-blend skinning, sampling source keys plus 60 Hz.
The final 128 torso fits were replayed again: 1,280 surface/clip records,
maximum loop drift 0.00191 mm. Remaining stretch warnings are below.
The installed client supplies 90 front/side/gameplay captures across Luminous,
Ssarathi and Mycelari male/female through all five clips. Separate open-collar
front/side/back views cover every race; exception close-ups include 24-frame
cycles. These use the real actor, appearance, equipment and animation paths.

## Review evidence and storage

Current evidence is in [shared-equipment](shared-equipment/manifest.json):

- [Male neck joins](shared-equipment/sheets/neck-male-1.jpg) and
  [remaining males](shared-equipment/sheets/neck-male-2.jpg);
  [female neck joins](shared-equipment/sheets/neck-female-1.jpg) and
  [remaining females](shared-equipment/sheets/neck-female-2.jpg).
- [Male complete sets](shared-equipment/sheets/blender-sets-male.jpg),
  [female complete sets](shared-equipment/sheets/blender-sets-female.jpg),
  [Ssarathi/Mycelari complete sets](shared-equipment/sheets/blender-exceptions.jpg).
- Six `godot-<race>.jpg` sheets show installed gameplay through five clips.
- `comparisons/` contains both source and worn PNGs for Phoenix 01,
  Ranger 05 and Amberwood 04.
- `reports/` contains exact installed test logs, body geometry/motion reports,
  coverage, source-art identity checks, motion comparison and packed hashes.

Earlier equipment before/after sheets remain under
[canonical-equipment/sheets](canonical-equipment/sheets/). Their original
sixteen-fit measurements are historical and do not describe the shared-body set.

Equipment geometry plus shared textures totals **1,833,800,330 bytes (1.834 GB)**,
down from approximately 7.97 GB for the sixteen-body draft: about 77% smaller.
2,800 redundant body variants are omitted. Identical images share content-addressed
files; eligible indices use unsigned 16-bit storage without changing their values.
Every decoded accessor and image is checked during packing.

Large captures and editable `.blend` files remain in ignored local scratch,
not the delivered Git tree. Final complete-set scenes are in
`equipment-fit-build/shared-bodies/preview/shared-16-blender/`; each set has
armour-only and worn scenes. Historical full-resolution evidence is retained in
`equipment-fit-build/shared-bodies/archived-16-fit-qa/`. The evidence manifest
records local paths and hashes. Compact review sheets and required source/worn
PNGs are versioned. Clean delivery history excludes the oversized draft commits.

## Reproduction

Run from an isolated client worktree. Keep scratch input/output separate from
client assets. Recover the sixteen original canonical bodies from commit
`68f4f6e20e7c11051aecbb580c03b47b89a25393` into a new scratch input directory
(binary-safe Git extraction); retain them as read-only anatomical references.
Original Meshy `.glb.orig` files remain in the adjacent `generate_models` folder.

**Current path (2026-10).** Fit the Human bodies, then each race body's
headwear; both drive `refit_canonical_equipment.build_one` from the original
Meshy sources. Install order is pack, then share textures, then commit.

```powershell
python eloria-assets/tools/refit_human_bodies.py --bodies <dir holding luminous_male.glb and luminous_female.glb> --out <scratch> --pieces all --jobs 4
python eloria-assets/tools/install_human_equipment.py <scratch> --tag human
python eloria-assets/tools/share_human_equipment_textures.py
python eloria-assets/tools/refit_race_headwear.py fit --out <scratch> --tag <t> --pieces all --races all --jobs 4
python eloria-assets/tools/refit_race_headwear.py measure --out <scratch> --tag <t>
python eloria-assets/tools/refit_race_headwear.py human-check --out <scratch> --tag <t>
python eloria-assets/tools/refit_race_headwear.py install --out <scratch> --tag <t> --rigs <race slugs, comma separated>
```

`install_human_equipment.py` writes the two Human variants per piece, keeps a
piece's base fields equal to its `canonical_human_male` variant and sets
`fitGroups.luminous_<sex>` to the Human group alone. `refit_race_headwear.py
install` refuses fits whose recorded fitter, race-pass, body or policy hashes no
longer match the checkout, writes `variants["canonical_<race>"]` only and never
touches `fitGroups`. Race bodies come from `rebase_race_body.py`; race hair from
`fit_character_appearance.py --race`.

Headwear with a row in `eloria-assets/source/equipment-design-fit/headwear.json`
is reshaped inside the fitter (`headwear_fit.py`; see "Headwear review fixes").
Its cowls read the installed kit torso and its design-fit npz. After a change
to that torso, refit them into scratch and compare them with the installed ones
through the clip check (collar over hood, skin contact, both bodies) before
installing anything. Keep the installed fit unless the refit is better: the
cowl push leaves art more than `reach` (7 cm) outside the shell alone, so a
small torso change can flip part of a wrap between lifted over the collar and
tucked under it. After `9dca4c2d` changed the kit torsos (sleeves, waist twist,
cuffs), the refit moved the female Buckled Hood's front wrap 22 mm back on
average (up to 80 mm). In idle it let the collar through in 112 rays, where
the installed hood lets it through in 83. The male Antler Hood got slightly
worse too (+2 to +4 rays in most clips), and the rest were unchanged. The installed hoods measured the same on the new torsos as
on the old, so they were kept. `refit_race_headwear.py fit --races all` builds
the Human and race fits together. Install the two Human variants from a copy of
`<tag>-variants.json` reduced to the `canonical_human_*` groups
(`install_human_equipment.py`, then `share_human_equipment_textures.py`), and
then the race variants (`refit_race_headwear.py install`). Convert the registry
and catalogue back to LF after `install_human_equipment.py`.

**Refit before reinstalling.** `tool_hashes()` hashes
`refit_canonical_equipment.py` itself, and its retirement edit (2026-10-08)
changed that hash. Every fit recorded before it - the installed P5 headwear
fits, and any `refit_human_bodies.py` tag - now fails the fitter check:
`refit_race_headwear.py install` refuses it ("fitter changed since the fit")
and `--resume` will not reuse it ("Use a new tag; candidate is not an
unchanged resumable build"). The installed variants are unaffected; run the
fit again under a new tag before the next install. Run
`share_human_equipment_textures.py` after
`install_human_equipment.py` and before committing: it matches only shipped
(1024 px) textures, so after a commit a piece whose other scenes no longer name
the shipped texture is re-encoded into a duplicate.

The rest of this section is the September 2026 path, kept as history. Its
`build_shared_player_body_set.py`, `prepare_shared_registry.py`,
`refit_canonical_equipment.py build` and `pack_canonical_equipment.py
pack|install` steps are retired (see the top of this file).

```powershell
(Get-Process -Id $PID).ProcessorAffinity = [intptr]255
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:BLIS_NUM_THREADS = '1'
$env:NUMEXPR_NUM_THREADS = '1'
python eloria-assets/tools/build_shared_player_body_set.py --sources equipment-fit-build/shared-bodies/in --out equipment-fit-build/shared-bodies/rebuilt --jobs 4 --library godot-client/assets/actors/native/shared/Universal_Animation_Library.glb
```

`verify_shared_player_bodies.py` checks original head/tail/common-body triangles,
skeleton and every neck boundary. `prepare_shared_registry.py` prepared measured
equipment/model/catalogue metadata for reviewed scratch body candidates.
`install_shared_equipment.py install --plan <reviewed-plan.json>` installs only
explicit replacements/removals after validating all expected hashes. The plan
format is `replace: {path: {source, sha256, expected}}`, `remove: {path: sha256}`
and `protected: {path: sha256}`. Do not export Blender directly over client assets.

For equipment rebuilding on the installed shared bodies, use a fresh snapshot
and measurement path. **Both reference options matter**: head references retain
socket landmarks; anatomy references stabilize torso art and skin samples.

```powershell
python eloria-assets/tools/pack_canonical_equipment.py snapshot
python eloria-assets/tools/refit_canonical_equipment.py measure --measurements equipment-fit-build/reports/rebuild-measurements.json
python eloria-assets/tools/refit_canonical_equipment.py build --tag rebuilt --races all --pieces all --jobs 6 --measurements equipment-fit-build/reports/rebuild-measurements.json --head-reference equipment-fit-build/shared-bodies/in --anatomy-reference equipment-fit-build/shared-bodies/in
python eloria-assets/tools/audit_canonical_batch.py equipment-fit-build/out/rebuilt --out equipment-fit-build/reports/rebuilt-audit.json
python eloria-assets/tools/audit_canonical_coverage.py equipment-fit-build/out/rebuilt --jobs 2 --out equipment-fit-build/reports/rebuilt-coverage.json
python eloria-assets/tools/audit_canonical_motion.py equipment-fit-build/out/rebuilt --out equipment-fit-build/reports/rebuilt-motion
python eloria-assets/tools/pack_canonical_equipment.py pack rebuilt --out-tag reviewed
```

The builder deduplicates body-template work while retaining sixteen head fits.
`pack_equipment_revision.py` supports partial original-source revisions with
explicit parent, audit and body evidence, including original-art identity guards.
Installation remains separate from packing. Never regenerate item definitions;
always use `--meshes-only` if invoking the older batch driver (since 2026-10
also `--build-dir <scratch>`: it no longer rebuilds installed pieces in place).

`capture_canonical_equipment.ps1` and `canonical_equipment_preview.gd` reproduce
actual client views. `compare_conformed_piece.py --ensemble --save-blend`
produces complete-set Blender scenes; provide `--worn` for the body sheet and
`--worn-pose source` for posed arms. Renderer masking preserves imported corner
normals. Refresh the Godot editor import cache before integration tests.

## Remaining limitations

- This provides two common body shapes, not two physical race files. Headwear
  remains individual because head shapes, horns, crystals and mushrooms differ.
- Source texture charts still contain dark markings and stretched details,
  most apparent on Glasswarden neck skin and some armour. The neck has no open
  boundary or mismatched join normals; source texture cleanup is separate.
- Original long-cloth stretch warnings remain. Final torso maximum extension
  is 93.29 mm on the male Patched Workshirt. The neckline change leaves original
  art skinning identical but increases some lining warnings: maximum +4.67 mm
  on male Frontier 03 Jog and +6.20 mm on female Arcane 02 Fighting_Idle;
  largest lining p99 increase is +3.90 mm on female Militia 08 Jog.
- The pre-existing Ssarathi male upper-leg p99 warning remains approximately
  30–31 mm in Jog/Run_Female. A new internal tail-root closure edge reaches
  approximately 85.5 mm maximum extension; that cap is inside the pelvis.
- Battle Gauntlet `0:184` remains a rigid hand-socket prop with protruding
  fingers; it is not a finger-skinned glove and is outside the 264 generated
  torso/head/leg/boot designs. Existing socket behaviour is preserved.
- Headwear and hairstyle review is representative, not every possible pairing.
  No standalone executable export was tested; this checkout has no export preset.
