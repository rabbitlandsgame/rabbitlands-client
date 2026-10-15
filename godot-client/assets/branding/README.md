# Rabbit Lands brand assets

These assets adapt the user-selected Discord crest: a rabbit-ear RL monogram,
silver faces, warm gold edges and restrained blue star accents.

| Asset | Use |
| --- | --- |
| `rabbitlands-logo.png` | Transparent full logo for login, documentation and larger placements |
| `rabbitlands-mark.png` | Transparent compact RL mark for the in-game HUD |
| `rabbitlands-icon.png` | 1024px application/window icon source |
| `rabbitlands-icon.ico` | Windows game, updater and installer icon; 16–256px entries |
| `rabbitlands-icon.icns` | Matching macOS artwork export; no macOS packaging support is implied |
| `rabbitlands-mark-64.png` | Small updater splash |
| `rabbitlands-splash.png` | Bounded-size game startup splash |
| `rabbitlands-discord-crest.png` | Original selected circular Discord identity, preserved unchanged |

Keep the artwork proportions and transparency. Use the full name where it is
readable, and the compact mark at HUD/icon sizes. Place transparent versions
on a sufficiently contrasting background. Do not add the former product name
to new title cards. **Eloria** remains the world/lore name; **Nymara** remains
in authored content. Stable resource paths and saved-data identifiers remain
compatible.

The login and HUD select these files in `src/app/main.gd`. `project.godot`
selects the application icon and splash. `tools/package_client.py` configures
Windows export and installer icons, and `tools/client_release.py` copies the
same kit into the updater's small generated project. The old product-logo
bitmap is retired; other `eloria_*` UI artwork paths remain valid.

Fresh wiki gameplay media must be captured from the running branded client;
do not paint a new crest over old frames. Keep capture dates, source revisions,
staging/boosted-character notes and archive relationships in capture records.
Older source media may remain in Git history with accurate historical captions.

`provenance.json` records the built-in image-generation prompts, the selected
base and checksums. Resized icon formats contain the same approved artwork.
