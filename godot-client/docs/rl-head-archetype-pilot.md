# Selected human bases

This develop integration adds three explicit bases to the existing RL Head Lab:

| Preset | Sex | Grooming |
|---|---|---|
| `human_01` | female | Cornrows into a low knot |
| `human_20` | male | Rounded Afro |
| `human_34` | male | Bald elder with an attached grey full beard |

Run `godot-client/open-rl-head-lab.bat --preset human_01` or
`godot-client/open-rl-head-lab.bat --preset human_20`, or use `--preset human_34`.
You can also choose the appropriate
sex and preset in the lab. Use High quality for the fitted hair modules. The lab
uses each base's saved PC/3 body and garment appearance while editing its raw
head controls; existing head-only presets retain their previous behavior.

The catalog is `data/actors/rl_head_archetypes.json`. PC/2 fallback appearances
are retained exactly. Module IDs 4 and 5 are append-only; IDs 6–8 remain
unregistered here. Existing saves, NPC assignments and creation Randomize are
unchanged. This adds no character-creation popup; that interface is a separate
design task.

The source is the already generated pilot assets, not new paid generation.
The cornrows deliberately expose six scalp channels between seven rows. Afro
wisps are compact and root-attached. Both styles use one head-following hair
root and retain the current head's identity and grooming targets. Open headwear
fits for pieces 111, 112 and 119 are included for these two styles; full equipment
presentation remains subject to normal outfit review.

The neck transitions to the actual body dye using three existing colour-alpha
components, preserving the sixteen instance-uniform slots and face RGB. The
female default shirt has a smooth mirrored collar; its skin cover is active only
on the repaired luminous female shirt and is disabled for an equipped torso.
Canonical body/head files, Mira/Rowan assets and rules are preserved.

Human 34 uses a continuous skin-attached foundation around the chin and lips,
with the long painted reference mass retained below it. All three detail levels
retain the 75 identity/expression targets. The full-beard module uses continuous
alpha at its feathered margins; the other hair and beard modules retain their
existing rendering routes. Individual beard colour remains bound in both
instance-uniform and material-uniform rendering modes. Neutral, smile and
combined jaw/smile views are reviewed at the saved human34 fit and all three
detail levels. Artistic acceptance remains an owner review.

Humans 08, 14 and 27 stay outside this integration. Original source stages,
fit consensus, failed candidates and images remain in ignored authoring storage.

The selected fits are review bases with disputed controls recorded in the data;
this is not a claim that all historical synthetic likeness tests pass. Current
asset hashes and retained authoring checks are recorded in
`eloria-assets/tools/rl_heads/hair/pilot-provenance.json` from the client root.

Relevant checks:

```text
Godot --headless --path godot-client --script res://tests/test_rl_head_archetypes.gd
Godot --headless --path godot-client --script res://tests/test_female_shirt_neckline.gd
Godot --headless --path godot-client --script res://tests/test_rl_head.gd
Godot --headless --path godot-client --script res://tests/test_rl_head_portrait_map.gd
Godot --headless --path godot-client --script res://tests/test_rl_head_full_beard.gd
Godot --headless --path godot-client --script res://tests/test_rl_head_shader_values.gd
```
