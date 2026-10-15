# Character colors and expanded hair

All sixteen canonical player models now use measured skin references per
material. The shader applies the selected color to the original texture detail;
faces, eyelids, scalp, hands, neck bridges, and Ssarathi tails follow one palette.
Eye and eyebrow masks remain independent. Skin ID 0 still renders old saved
characters as authored, but the creation menu no longer offers it. Menu swatches
use actual color values, and garment labels describe each culture's cloth dyes.
The creation preview uses neutral, reduced lighting to avoid bleaching colors.

Five additional silhouettes are available for both sexes and every race: bob,
ponytail, long braid, topknot, and mohawk. This adds 10 raw meshes and 80 fitted
meshes. All share the existing 77-joint bind pose. Horns and crystals remain
exposed. The approved body geometry, animations and earlier hairstyles are
unchanged. Registry rebuilds and the buzzcut installer preserve the extra styles.

## Saved appearances

Historical hair values 0–199 retain their meanings. The added five styles use
internal values 200–299. Creation stores the low byte in `hair` and a tag plus
high bit in the retired cosmetic `head` byte (`0x80` or `0x81`). The server already
persists and echoes these bytes. The client reconstructs the value when decoding
an enhanced actor. Actual equipment helmets use their existing equipment field.
Do not reuse the retired head field without migrating this encoding.

## Reproduction and checks

- `calibrate_skin_palettes.py --root <checkout>` measures the original UV-mapped
  skin albedo and records each source GLB hash in `models.json`.
- `expand_hairstyles.py` authored the five raw styles; its refit is retired
  (2026-10) and refuses to run. Fit Human hair with `fit_human_hair.py` and
  race hair with `fit_character_appearance.py --race <slug>`.
- `appearance_palette_preview.gd` captures every skin or hair choice using the
  actual client renderer; select `ELORIA_PALETTE_MODE=skin` or `hair` and set
  `ELORIA_ARTIFACT_DIR` to a scratch output directory.
- `appearance_options.gd` checks descriptive choices and all saved IDs, then
  exports 200 creation packets. `verify_hair_server_roundtrip.py --server
  <server-checkout> --artifacts <directory>` replays them through actual creation,
  SQLite persistence and actor serialization. Rerun the Godot test to verify
  decoding: 3,518 checks passed.
- `face_texture_mapping.gd`: all 16 models and 1,920 skin/eye combinations,
  37,995 checks passed, including equipment cycling and immutable source atlases.
- `rendered_character_creation_models.gd`: real creation controls, all 200
  style/color combinations on both Luminous models, and roster previews passed.
- The geometric crown/skin-binding checks pass for all 144 fitted hairstyles.
  Catalog inventory, raw hair, registry preservation and creation linkage pass.

The broader native asset suite has existing failures for creature skeletons and
facing, NPC counts, legacy equipment IDs, and the old slim-body measurement.
Those assets and non-player model entries are unchanged; the metadata failures
were reproduced against the starting revision. The stale catalog inventory and
player registry preservation issues encountered here were corrected.
The general protocol suite still reports its two existing capability/facing
failures (`magic_book_v2` and walk/run facing); the focused appearance protocol
and real server round-trip checks pass.

All authoring, rendering and validation processes were restricted to CPU 0–7.
