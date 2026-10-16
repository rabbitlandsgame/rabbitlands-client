# Reference motion for bear creatures

Moss Bear uses the approved Walk, Jog, forepaw attack and side-fall death clips.
The installed GLB is the exact reviewed file. Walk and Jog retain their accepted
animation payloads; Idle_A, Fighting_Idle and Hit_Chest retain the previous game
payloads. Geometry, skin weights, binds, rest transforms, materials and hierarchy
are unchanged. All seven existing clip names remain available.

The dedicated `data/animations/ursine/moss_bear.json` map supplies measured stride
speeds after the existing import scale: 0.7966527690 m/s for Walk and 1.7748486590
m/s for Jog. The existing resolver adjusts playback to travel speed and actor
scale. Facing, attachments, actor IDs and server behavior retain their previous
settings. The reference durations are 3.5 seconds for attack and 3.75 seconds for
death; this asset update does not change server combat scheduling or damage timing.

The tracked import policy and GLB metadata declare a 1536 Hz animation bake, with
optimizer and compression disabled. Do not reduce those settings without new
contact and independent world-pose checks. Localized dorsal leaf-plate stretching
in the strongest poses remains as reviewed; this update does not repair skinning.

`docs/qa/ursine-motion` binds preservation, authoring validation, fresh Blender
review and current client component playback to the installed model hash. The
engine probe covers all seven clips, four-influence skin, imported/native
agreement, independent off-grid GLB poses, action switching, RESET, Idle
restoration and one-shot endpoint holds. It is a focused integration check,
not a complete client/server play session.

After importing the project, run:

```powershell
godot --headless --path godot-client --script tests/test_ursine_video_motion.gd
```

Black Bear and Ice Bear are old procedural models. The user rejected them as
animation targets; their gait candidates and generators are archived and their
game visuals are retired. They must not be selected for further animation work.
Obsidian Bear, Crystal Polar Bear and Owlbear are updated models and remain
eligible for a separate anatomical audit. Consult the current development roster
and `docs/procedural-model-archive.md` before choosing another input.
