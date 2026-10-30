# Selected human bases

This develop integration adds two explicit bases to the existing RL Head Lab:

| Preset | Sex | Grooming |
|---|---|---|
| `human_01` | female | Cornrows into a low knot |
| `human_20` | male | Rounded Afro |

Run `godot-client/open-rl-head-lab.bat --preset human_01` or
`godot-client/open-rl-head-lab.bat --preset human_20`, or choose the appropriate
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

Humans 08, 14 and 27 remain in repair. Human 34 is also held: the proposed beard
replacement and the existing full beard both failed the combined mouth-opening
review. No beard asset is replaced by this integration. Original source stages,
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
```
