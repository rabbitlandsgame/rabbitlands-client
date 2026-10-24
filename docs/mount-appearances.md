# Mounts and coat choices

The mount collection includes Moor Pony, Golden Plains Horse, Crystalback
Tortoise, Giant Meadow Rabbit, Jadefeather Raptor, Giant Rat, Cave Salamander,
Lantern Stag and Cheetah. The current test server configuration grants the full
collection to every character when they connect. Updated client and server
builds are required for the three new entries.

Open Mounts with the mount icon on the bottom HUD. Select a card and choose
Ride. R mounts or dismounts; Space toggles fast movement. Every mount shares
normal travel at 1.5 times running speed and fast travel at twice running speed.
The new mounts reuse the current imported creatures and their native Idle_A,
Walk and Jog clips, with mount-specific size, saddle, rider, rein and cape fits.

The Coat menu previews Original, Ashen, Snow, Woodland Dapple and Ember Stripes.
Apply coat saves the choice for that animal. Applying a coat while mounted
keeps the rider seated and preserves movement and endurance. Other players
receive the chosen coat. Browsing a card or coat sends no command. Original
restores the original mesh and materials. These starter coats are material
variations over the imported textures, rather than newly painted texture sets.

## Adding textures or palettes

`godot-client/data/mounts/coats.json` defines palette, pattern and optional
replacement albedo textures. `mountOverrides` can customize a preset for one
mount. For example, a mount override can contain:

```json
{
  "snow": {
    "colour": "e4dfd1",
    "strength": 0.0,
    "pattern": 0,
    "textures": {
      "material": "res://assets/mount-coats/example-albedo.png"
    }
  }
}
```

This example path is illustrative. Add the actual texture to the repository
and use the imported material's resource name as the key. A strength of zero
shows the replacement's own colors. Keep existing UVs and normal/roughness/
metallic maps aligned; unrelated source actors and their materials are shared
and must remain unchanged. New appearance IDs must be added to both client
`mount_coats.gd` and server `mounts.COATS` before players can save them.

Only stable IDs travel over the network. The server validates ownership and
appearance IDs and persists per-mount choices in `mount_profiles.coats`. The
store automatically upgrades existing tables without resetting selection or
endurance. Full and delta mount rows include `coat_id`; an owner's row also
includes `mount_coats`. Older clients ignore the extra coat field and receive
only mount species their capabilities support. An older server leaves Apply
coat disabled. The new client advertises `wild_mounts_v1` and `mount_coats_v1`
alongside the existing riding and selection capabilities.

`mount_coat_visual.gd` builds per-instance masked surfaces, retaining vertex
positions, UVs, skin, eight influences, morphs and LODs. It excludes borrowed
tack and protects head/saddle ownership where configured. Rest coordinates
in a custom vertex attribute keep patterns attached through animation. The
original texture's dark markings remain visible. Starter palettes and patterns
are ready for visual review; they are not recorded as user-approved artwork.

Focused checks are `test_mount_coats.gd`, `test_mounts_window.gd` and
`test_mounted_actions.gd -- --mount=<id>`. Native rider and coat captures use
`tests/integration/rendered_wild_mounts.gd` with `--video` or `--coats`.
