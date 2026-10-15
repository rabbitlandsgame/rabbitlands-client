# Four Gates NPC and equipment QA

This stage replaces the generic service-NPC variants used by Four Gates and
refines its six-piece Luminous civic equipment set while preserving actor,
item, skeleton, and attachment contracts.

## Runtime assets

| ID | Asset | Contract | Generated topology |
| --- | --- | --- | ---: |
| 307 | Luminous Official M | `actors/nymara/npcs/luminous_official_m.xmf` | 1,094 vertices / 2,120 faces |
| 309 | Luminous Merchant M | `actors/nymara/npcs/luminous_merchant_m.xmf` | 1,018 vertices / 1,976 faces |
| 1000 | Civic Blade | weapon / `lower_arm_r` | 128 vertices / 64 faces |
| 1001 | Lakeguard Spear | weapon / `lower_arm_r` | 104 vertices / 52 faces |
| 1002 | Mirror Shield | shield / `lower_arm_l` | 200 vertices / 100 faces |
| 1003 | Ceremonial Mail | body / `spine` | 240 vertices / 120 faces |
| 1004 | Civic Mantle | cape / `spine` | 120 vertices / 60 faces |
| 1005 | Ferry Hook | weapon / `lower_arm_r` | 136 vertices / 68 faces |

The official receives an intentional shoulder mantle and civic headpiece. The
merchant receives a soft hood silhouette and belt pouches. Equipment shapes
are distinct rather than aliases of the former primitive presets.

## Reproduction and validation

> Reproduction commands removed: this stage was validated against the
> Eternal Lands format data pack, which was deleted with the C client
> on 2026-09-03. The evidence below is kept as the record of it.

Validation asserted the exact actor paths for IDs 307
and 309, and the exact names, slots, attachment bones, topology floors,
material sizes, and icon sizes for item IDs 1000 through 1005.

## Visual evidence

- `four_gates_npc_wireframes.png`: official and merchant silhouette/topology
- `four_gates_equipment_wireframes.png`: six representative equipment meshes
- `four_gates_equipment_materials.png`: generated material sheets at source resolution

Shaded in-client character/equipment switching captures remain pending a
GPU-capable client session. This stage does not change the renderer, protocol,
actor IDs, item IDs, or server configuration.
