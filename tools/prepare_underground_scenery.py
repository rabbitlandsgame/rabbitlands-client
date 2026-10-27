"""Package reviewed Meshy scenery for underground use without rebuilding models.

Reuses source geometry and UVs. Selected lantern faces remove the unused post;
stone material variants use generated atlases. An outer transform sets gameplay
size and aligns the physical passage or base with the floor.

  python -B tools/prepare_underground_scenery.py [--check] [--map <interior> ...] [--configs-only]

Writes godot-client/assets/world/underground/<name>.glb for every SELECTION row
(and every TOWN_SELECTION row an interior places),
eloria-assets/source/world_objects/underground/reused-scenery.json, and one
scenery config per interior map (INTERIORS: the map's plan source, the builder
whose dressing and themes it reads, and its config file):
  landfall_insides  content/underground.json   build_underground     data/world/underground-scenery.json
  landfall_town     content/landfall_town.json build_town_interiors  data/world/town-scenery.json
A config holds every section's placements (<builder>.dressing: the source's
props and the theme's wall pieces), `harvestPresentation` (the caves' nodes)
and `surfaces` (<builder>.surfaces: each section's theme styling, which
underground_scenery.gd applies), plus, for the caves, the objects.json harvest
entries the underground needs. An interior whose plan source is absent is
skipped. The caves' config lists every SELECTION asset, as it always has (so
its bytes do not move when the town's pieces are added); another interior's
lists the assets it places. A new cave's kit piece is a SELECTION row, a town
piece a TOWN_SELECTION row (region or kit, slug, 'height' or 'length', target
metres); only pieces whose glTF generator is prepare_meshy_kit are accepted.
--check computes every config and compares it with its file, packaging nothing
and writing nothing; it exits 1 when a config would change. --configs-only (or
--map <interior>, which names the configs) writes only the scenery configs: no
model is packaged and reused-scenery.json and objects.json stay as they are (a
config placing a piece not packaged yet is refused), so a town edit need not
touch the caves' files.

Wall veins (pass 2, 2026-10-21): every node a section's `veins` names is
presented set into its rock face, {placement: 'wall', yaw, inset, variant}
from build_underground.vein_faces (a hand HARVEST_PRESENTATION entry for a vein
node is refused), and WALL_SEAMS gives each ore label its wall seam art:
objects.json `harvestables.wallVariants[label]`, models `rl_<label>_wall_<k>`
in the label's mineral palette, never standing alone (MapObject3D stands them
only on a wall node). A vein's nodes alternate through their label's seams.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'eloria-assets/tools'))
from video_motion.asset import accessor, read_glb, write_glb  # noqa: E402
from video_motion.packing import append_array  # noqa: E402
from imported_world_objects import measure_glb  # noqa: E402

SELECTION = {
    'crystal_arch': ('amethyst_barrens', 'crystal-rock-arch-1', 'height', 5.2),
    'crystal_cluster': ('amethyst_barrens', 'crystal-growth-1', 'height', 1.7),
    'mine_rail': ('amethyst_barrens', 'mine-rail-straight-1', 'length', 3.0),
    'wall_lantern': ('amethyst_barrens', 'lantern-post-1', 'height', .8),
    'mossy_rock': ('grey_moors', 'mossy-boulder-2', 'length', 3.0),
    'cave_mouth': ('whitehorn_range', 'whitehorn-ice-cave-mouth-v001', 'height', 5.2),
    'resource_rock_1': ('amethyst_barrens','veined-boulder-1','height',.8),
    'resource_rock_2': ('amethyst_barrens','veined-boulder-2','height',.8),
    'resource_rock_3': ('amethyst_barrens','veined-boulder-3','height',.8),
    # The Cenote Deeps (owner 2026-10-20): Landfall A3's own jungle kit, lf-biomes.
    'mossy_crag_1': ('lf-biomes','mossy-crag-1','height',6.0),
    'mossy_crag_2': ('lf-biomes','mossy-crag-2','height',7.0),
    'mossy_boulder_1': ('lf-biomes','mossy-boulder-1','height',2.4),
    'mossy_boulder_2': ('lf-biomes','mossy-boulder-2','height',3.2),
    'mossy_boulder_3': ('lf-biomes','mossy-boulder-3','length',3.0),
    'waterfall_rocks': ('lf-biomes','waterfall-rocks-1','length',11.0),
    'jade_lantern_shrine': ('lf-biomes','jade-shrine-1','height',2.0),
    'jade_cairn': ('lf-biomes','jade-shrine-2','height',2.2),
    'jade_lantern_pole': ('lf-biomes','jade-lantern-pole-1','height',2.8),
    'incense_brazier': ('lf-biomes','serpent-incense-brazier-1','height',1.6),
    'serpent_arch': ('lf-biomes','serpent-ruin-8','length',6.6),
    'serpent_altar': ('lf-biomes','serpent-ruin-7','length',2.6),
    'serpent_pillar': ('lf-biomes','serpent-ruin-3','height',3.2),
    'serpent_obelisk': ('lf-biomes','serpent-ruin-6','height',3.0),
    'serpent_frieze': ('lf-biomes','serpent-ruin-4','length',3.5),
    'lotus_pads': ('lf-biomes','lotus-flower-pads-1','length',3.0),
    'lagoon_reed': ('lf-biomes','lagoon-reed-1','height',1.4),
    'tree_fern': ('lf-biomes','tree-fern-1','height',4.5),
    'jungle_undergrowth': ('lf-biomes','jungle-undergrowth-1','height',2.2),
    'jungle_undergrowth_2': ('lf-biomes','jungle-undergrowth-2','height',1.8),
    'split_geode': ('lf-biomes','split-geode-1','height',2.0),
    'toadstool_ring': ('lf-biomes','toadstool-ring-1','length',2.5),
    'mossy_log': ('lf-biomes','mossy-log-1','length',5.0),
    # The Landfall underground programme (owner 2026-10-20), wave 1: the mine, barrow, warren and geode themes
    # (build_underground.THEMES) and their set pieces. Rendered and chosen from the reviewed kits; no new models.
    'veined_crag_1': ('lf-biomes','veined-crag-1','height',5.5),
    'veined_crag_2': ('lf-biomes','veined-crag-2','height',6.2),
    'veined_crag_4': ('lf-biomes','veined-crag-4','height',6.8),
    'veined_boulder_1': ('lf-biomes','veined-boulder-1','height',2.0),
    'veined_boulder_2': ('lf-biomes','veined-boulder-2','height',2.6),
    'veined_boulder_3': ('lf-biomes','veined-boulder-3','height',2.4),
    'veined_boulder_4': ('lf-biomes','veined-boulder-4','height',2.0),
    'veined_boulder_5': ('lf-biomes','veined-boulder-5','height',2.8),
    'vein_scree_1': ('lf-biomes','vein-scree-1','length',2.8),
    'vein_scree_3': ('lf-biomes','vein-scree-3','length',3.2),
    'ore_cart': ('lf-biomes','ore-cart-1','length',2.0),
    'mine_headframe': ('lf-biomes','mine-headframe-1','height',6.0),
    'supply_sledge': ('lf-biomes','supply-sledge-1','length',2.6),
    'supply_crate': ('lf-biomes','supply-crate-1','height',1.0),
    'crate_stack': ('four_gates','crate-stack-1','height',1.3),
    'barrel_stack': ('four_gates','barrel-stack-1','height',1.2),
    'tool_rack': ('lf-biomes','tool-rack-1','height',1.7),
    'feed_sacks': ('lf-biomes','feed-sacks-1','length',1.3),
    'iron_lantern': ('lf-biomes','lantern-post-1','height',2.6),
    'drystone_dyke': ('grey_moors','drystone-dyke-1','length',5.0),
    'coastal_boulders_1': ('lf-biomes','coastal-boulders-1','height',4.4),
    'coastal_boulders_3': ('lf-biomes','coastal-boulders-3','height',3.6),
    'moor_stone_1': ('lf-biomes','moor-standing-stone-1','height',3.2),
    'moor_stone_2': ('lf-biomes','moor-standing-stone-2','height',2.6),
    'moor_stone_3': ('lf-biomes','moor-standing-stone-3','height',1.8),
    'giant_skeleton': ('grey_moors','giant-skeleton-1','length',9.0),
    'grave_markers': ('lf-biomes','grave-markers-1','length',3.0),
    'candle_stake': ('grey_moors','candle-stake-1','height',1.4),
    'wisp_lantern': ('grey_moors','wisp-lantern-1','height',2.4),
    'lichen_mat': ('grey_moors','lichen-stone-mat-2','length',2.0),
    'bog_oak_stump': ('grey_moors','bog-oak-stump-1','length',3.0),
    'mossy_stump_1': ('lf-biomes','mossy-stump-1','height',2.0),
    'mossy_stump_2': ('lf-biomes','mossy-stump-2','height',1.4),
    'hollow_log': ('amberwood','hollow-log-1','length',3.2),
    'warren_mound': ('lf-biomes','warren-mound-1','length',5.0),
    'warren_mound_2': ('lf-biomes','warren-mound-2','length',2.6),
    'peat_barrow': ('grey_moors','peat-barrow-1','length',1.8),
    'peat_stack': ('lf-biomes','peat-stack-1','height',1.5),
    'amber_lantern': ('lf-biomes','amber-lantern-post-1','height',2.6),
    'bracken': ('lf-biomes','bracken-patch-1','length',2.6),
    'fallen_leaves': ('lf-biomes','fallen-leaves-1','length',3.0),
    'great_amethyst_cluster': ('lf-biomes','great-amethyst-cluster-1','height',7.0),
    'split_geode_2': ('lf-biomes','split-geode-2','height',2.4),
    'split_geode_3': ('lf-biomes','split-geode-3','height',2.6),
    'crystal_vent': ('lf-biomes','crystal-vent-1','length',2.8),
    'crystal_vent_2': ('lf-biomes','crystal-vent-2','length',3.0),
    'crystal_sluice': ('amethyst_barrens','crystal-sluice-1','length',2.4),
    'crystal_growth_4': ('lf-biomes','crystal-growth-4','height',1.2),
    'crystal_growth_5': ('lf-biomes','crystal-growth-5','height',.8),
    # Harvest art for resources whose own model was retired (variant models: only laid-out nodes stand them).
    'resource_moss': ('grey_moors','mossy-boulder-4','length',1.3),
    'resource_toadstool': ('lf-biomes','toadstool-ring-1','length',1.3),
    # wave 2
    # The Landfall underground programme (owner 2026-10-20), wave 2: the cellar, sea_cave, roots, basalt and sandstone
    # themes, their set pieces and door art. Rendered and chosen from the reviewed kits; no new models.
    'stone_windbreak': ('lf-biomes','stone-windbreak-1','length',5.0),
    'terracotta_pots': ('lf-biomes','terracotta-pots-1','height',.9),
    'cider_press': ('lf-biomes','cider-press-1','height',2.5),
    'harvest_baskets': ('lf-biomes','harvest-baskets-1','length',.9),
    'wooden_pail': ('lf-biomes','wooden-pail-1','height',.45),
    'supply_chest': ('lf-biomes','supply-crate-2','length',1.1),
    'trilithon': ('lf-biomes','trilithon-1','height',3.6),
    'ruined_chapel': ('grey_moors','ruined-chapel-1','length',9.0),
    'coastal_rock_1': ('crownwater','coastal-rock-1','length',4.4),
    'coastal_rock_2': ('crownwater','coastal-rock-2','length',4.0),
    'beach_rocks': ('crownwater','beach-rocks-1','height',1.9),
    'weed_rocks': ('grey_moors','weed-rocks-1','height',1.8),
    'sea_arch': ('crownwater','sea-stack-2','length',11.0),
    'rowing_boat': ('lf-biomes','rowing-boat-1','length',4.0),
    'beached_rowboat': ('grey_moors','beached-rowboat-1','length',4.0),
    'lobster_pots': ('westhaven','lobster-pots-1','height',1.4),
    'sunken_statue_head': ('crownwater','sunken-statue-head-1','height',2.6),
    'rope_coils': ('crownwater','rope-coils-1','length',1.6),
    'cargo_net': ('westhaven','cargo-net-pile-1','height',1.4),
    'kelp_wrack': ('grey_moors','kelp-wrack-1','length',3.0),
    'shell_scree': ('westhaven','shell-scree-1','length',1.6),
    'driftwood': ('grey_moors','driftwood-1','length',4.0),
    'anchor': ('westhaven','anchor-display-1','height',2.4),
    'mooring_posts': ('crownwater','mooring-posts-1','height',1.4),
    'lamp_buoy': ('crownwater','lamp-buoy-1','height',2.0),
    'mossy_log_2': ('lf-biomes','mossy-log-2','length',5.0),
    'hollow_root': ('amberwood','hollow-log-1','length',6.0),
    'amber_drying_rack': ('lf-biomes','amber-drying-rack-1','length',2.2),
    'mushroom_basket': ('lf-biomes','mushroom-basket-1','height',.6),
    'resin_pine': ('lf-biomes','resin-tapped-pine-1','height',6.0),
    'leaf_pile': ('lf-biomes','leaf-pile-1','length',2.0),
    'autumn_fern': ('lf-biomes','autumn-fern-1','length',2.0),
    'basalt_columns_1': ('lf-biomes','basalt-columns-1','height',4.6),
    'basalt_columns_2': ('lf-biomes','basalt-columns-2','height',5.2),
    'basalt_columns_3': ('lf-biomes','basalt-columns-3','height',4.2),
    'ashen_brush': ('lf-biomes','ashen-brush-2','length',1.1),
    'vein_scree_2': ('lf-biomes','vein-scree-2','length',2.6),
    'mesa_face_1': ('lf-biomes','mesa-face-1','height',4.6),
    'mesa_face_3': ('lf-biomes','mesa-face-3','height',4.6),
    'mesa_corner_1': ('lf-biomes','mesa-corner-1','height',4.6),
    'mesa_corner_2': ('lf-biomes','mesa-corner-2','height',4.6),
    'mesa_hoodoo': ('lf-biomes','mesa-hoodoo-1','height',6.0),
    'mesa_talus_1': ('lf-biomes','mesa-talus-1','length',2.6),
    'salt_heap': ('lf-biomes','salt-heap-1','length',2.9),
    'salt_mound': ('lf-biomes','salt-mound-1','length',4.0),
    'shrine_cairn': ('lf-biomes','shrine-cairn-1','height',2.2),
    # Harvest art for Pearl, Sap and Ember Crystal (laid-out variants only, as wave 1's Moss, Toadstool, Stormglass).
    'resource_pearl': ('crownwater','oyster-baskets-1','height',.8),
    'resource_sap': ('lf-biomes','wooden-pail-1','height',.55),
    'resource_ember_crystal': ('lf-biomes','crystal-growth-3','height',1.0),
    # wave 3 (owner 2026-10-20): the ice, catacomb and vault themes (build_underground.THEMES), their set pieces and
    # door art, and laid-out harvest art for Verdigris, Venom Bulb and Lichen. Rendered and chosen from the reviewed
    # kits; no new models.
    'icicle_arch': ('whitehorn_range','icicle-rock-arch-1','height',5.2),
    'glacier_block': ('lf-biomes','glacier-block-1','height',3.4),
    'ice_shards': ('lf-biomes','ice-shards-1','height',3.2),
    'ice_shards_2': ('lf-biomes','ice-shards-2','height',1.8),
    'snowcap_boulder_1': ('lf-biomes','snowcap-boulder-1','height',3.2),
    'snowy_boulder_2': ('lf-biomes','snowy-boulder-2','height',2.8),
    'frozen_waterfall': ('whitehorn_range','frozen-waterfall-1','height',8.0),
    'icicle_fringe': ('lf-biomes','icicle-fringe-1','length',4.0),
    'frozen_pond': ('whitehorn_range','frozen-pond-1','length',8.0),
    'snow_drift': ('lf-biomes','snow-drift-1','length',5.0),
    'snow_scree': ('lf-biomes','snow-scree-1','length',3.0),
    'climbing_gear': ('lf-biomes','climbing-gear-basket-1','height',1.0),
    'prospector_lean_to': ('lf-biomes','prospector-lean-to-1','length',3.0),
    'temple_sanctum': ('lf-biomes','temple-sanctum-1','height',5.5),
    'sun_vault_door': ('lf-biomes','sun-vault-door-1','height',5.2),
    'serpent_gate_column': ('lf-biomes','serpent-gate-column-1','height',4.6),
    'serpent_rubble': ('lf-biomes','serpent-ruin-5','height',2.6),
    'serpent_column_ruin': ('lf-biomes','serpent-ruin-2','height',3.4),
    'sun_stela': ('lf-biomes','sun-stela-1','height',3.0),
    'clay_jars': ('manymouth_delta','clay-water-jars-1','height',1.1),
    'giant_lens_stand': ('lf-biomes','giant-lens-stand-1','height',4.2),
    'mirror_obelisk': ('lf-biomes','mirror-obelisk-1','height',4.6),
    'sun_mirror': ('lf-biomes','sun-mirror-1','height',2.8),
    'reflecting_pool': ('crownwater','reflecting-pool-1','length',6.0),
    'mirror_basin': ('lf-biomes','mirror-basin-1','length',6.0),
    'colonnade_arch': ('lf-biomes','ring-colonnade-1','height',4.4),
    'obelisk_lamp': ('crownwater','obelisk-lamp-1','height',3.2),
    'lens_tripod': ('lf-biomes','lens-tripod-1','height',1.6),
    'lens_grinder': ('lf-biomes','lens-grinder-bench-1','height',1.3),
    'lens_crate': ('lf-biomes','lens-crate-basket-1','height',.8),
    'sundial_plinth': ('lf-biomes','sundial-plinth-1','height',1.3),
    'resource_verdigris': ('lf-biomes','vein-scree-4','length',1.4),
    'resource_venom_bulb': ('lf-biomes','samphire-clump-1','height',.9),
    'resource_lichen': ('lf-biomes','lichen-stone-mat-3','length',1.5),
    # pass 2 (owner 2026-10-21): wall seam art for the ores (WALL_SEAMS), chosen from Godot renders of reviewed kit
    # pieces set into the Lantern Mine's wall (work-output/underground-pass2/platform/seams/); no new models.
    'seam_boulder_3': ('lf-biomes','veined-boulder-3','height',1.15),
    'seam_boulder_4': ('lf-biomes','veined-boulder-4','height',1.15),
    'seam_boulder_5': ('lf-biomes','veined-boulder-5','height',1.15),
    'seam_crystal_4': ('lf-biomes','crystal-growth-4','height',1.1),
    'seam_crystal_5': ('lf-biomes','crystal-growth-5','height',1.2),
    'seam_geode_3': ('lf-biomes','split-geode-3','height',1.1),
    # pass 2 wave A (owner 2026-10-21): door art for the Mill Race (the watermill over its race) and the Old Well (the
    # croft's well head), and the culvert's sluice gates, plank walk and fish trap. Rendered and chosen from the
    # reviewed kits (work-output/underground-pass2/wave-a/candidates/); no new models.
    'watermill': ('amberwood','watermill-1','length',8.0),
    'stone_well': ('four_gates','stone-well-1','height',3.2),
    'timber_sluice_gate': ('lf-biomes','timber-sluice-gate-1','length',4.0),
    'plank_jetty': ('sw_isle','sw-trestle-pier-span','length',4.5),
    'fish_trap_basket': ('lf-biomes','fish-trap-basket-1','height',1.1),
}
KITS = {'lf-biomes': 'godot-client/world_authoring/continent-v2/kits/lf-biomes/prototypes'}
# The Landfall town's rooms (owner 2026-10-27, chat: "Implement your plan"): reviewed kit pieces reused as furniture
# and dressing, at the size they were reviewed at (the kit's own measured height or length). A row is packaged only
# once an interior places it (main), so the shared folder holds no unused town art. No new models.
TOWN_SELECTION = {
    'flower_cart': ('four_gates','flower-cart-1','length',2.4),
    'produce_stall': ('lf-biomes','produce-stall-1','length',2.4),
    'flower_planter': ('crownwater','flower-planter-1','length',2.0),
    'flower_shrub_1': ('crownwater','flower-shrub-1','height',1.4),
    'flower_shrub_2': ('crownwater','flower-shrub-2','height',1.2),
    'citrus_planter': ('crownwater','citrus-planter-1','height',2.8),
    'potted_cypress': ('crownwater','potted-cypress-tree-1','height',2.4),
    'pearl_sorting_table': ('crownwater','pearl-sorting-table-1','length',2.4),
    'stone_bench': ('crownwater','stone-bench-1','length',2.0),
    'herb_drying_rack': ('amberwood','herb-drying-rack-1','length',2.16),
    'cooking_hearth': ('manymouth_delta','cooking-hearth-1','length',1.2),
    'offering_baskets': ('manymouth_delta','offering-baskets-1','length',1.2),
    'milk_churn': ('lf-biomes','milk-churn-1','height',.9),
    'fish_crates': ('crownwater','fish-crates-1','length',1.8),
    'woodcutter_block': ('lf-biomes','woodcutter-block-1','length',1.5),
    'sawhorse': ('lf-biomes','sawhorse-1','length',2.0),
    'glassware_cart': ('lf-biomes','glassware-handcart-1','length',2.4),
    'apple_cart': ('lf-biomes','apple-cart-1','length',2.4),
    'notice_board': ('lf-biomes','notice-board-1','height',2.2),
}
OUTPUT = 'godot-client/assets/world/underground'
CONTENT = 'eloria-assets/maps/continent-v2/_continent_v2/content'
# The interiors this tool dresses: map id -> its plan source, the builder module whose load_design(), dressing() and
# surfaces() it reads, its scenery config, whether the config lists every SELECTION asset ('all', the caves' contract)
# or only the assets it places ('placed'), and whether it presents harvest nodes (HARVEST_PRESENTATION and veins).
INTERIORS = {
    'landfall_insides': {'plan': f'{CONTENT}/underground.json', 'builder': 'build_underground',
                         'config': 'godot-client/data/world/underground-scenery.json', 'assets': 'all',
                         'harvest': True},
    'landfall_town': {'plan': f'{CONTENT}/landfall_town.json', 'builder': 'build_town_interiors',
                      'config': 'godot-client/data/world/town-scenery.json', 'assets': 'placed',
                      'harvest': False},
}
# Optional dressing keys a placement carries over, in this order: `outward` (the facing of the wall the piece is cut
# away with: a cave's wall rock, a town prop standing against a wall) and `palette`. A dressing item's other keys (the
# caves' `wall` flag among them) stay the builder's.
PLACEMENT_KEYS = ('outward', 'palette')

# The underground's laid-out nodes (Quartz, Salt, Clay, Flint, Moss, Toadstool,
# Stormglass), presented as a continent-v2 package presents its nodes
# (harvest_presentation.py): `variant` indexes objects.json
# harvestables.variants[label] (quartz_seam_a/b, salt_pan_a/b, ...) and `yaw` is in
# degrees about +Y. build_underground.py (retired) writes no presentation into
# the package, and seams and pans do not stand alone, so without this the
# client draws these nodes as rings. The values are the art the 2026-10-19
# playtest reviewed: the variant and yaw each object id seeded (the scale
# stays seeded). A node moved in underground.json needs its own values.
HARVEST_PRESENTATION = {
    1010: {'variant': 1, 'yaw': 226.336},
    # Wave 1 of the Landfall underground programme (owner 2026-10-20). Seams and banks face +Z, so each yaw turns
    # the face toward the node's open neighbours on the builder's walk grid; variants alternate by object id. Moss,
    # Toadstool and Stormglass have one variant each (their art is laid-out only; see `laid_out` in main()).
    1404: {'variant': 0, 'yaw': 90.0},  # Moss, The Old Warren (regrown in pass 2 wave A)
    1405: {'variant': 0, 'yaw': 180.0},
    1406: {'variant': 0, 'yaw': 180.0},
    1407: {'variant': 0, 'yaw': 180.0},  # Toadstool
    1408: {'variant': 0, 'yaw': 0.0},
    1409: {'variant': 0, 'yaw': 180.0},
    # wave 2
    # Wave 2 of the Landfall underground programme (owner 2026-10-20), as wave 1: seams, banks, strands, beds,
    # pails and crystals face their open neighbours; Pearl, Sap and Ember Crystal have one variant each (their
    # art is laid-out only; see `laid_out` in main()).
    1604: {'variant': 0, 'yaw': 0.0},   # Toadstool
    1605: {'variant': 0, 'yaw': 90.0},
    1606: {'variant': 0, 'yaw': 0.0},
    1607: {'variant': 0, 'yaw': 270.0},  # Moss
    1608: {'variant': 0, 'yaw': 315.0},
    1609: {'variant': 0, 'yaw': 90.0},
    1804: {'variant': 0, 'yaw': 135.0},  # Sap, The Resin Hollow
    1805: {'variant': 0, 'yaw': 90.0},
    1806: {'variant': 0, 'yaw': 0.0},
    1807: {'variant': 0, 'yaw': 225.0},  # Toadstool
    1808: {'variant': 0, 'yaw': 0.0},
    1809: {'variant': 0, 'yaw': 315.0},
    1810: {'variant': 0, 'yaw': 90.0},  # Moss
    1811: {'variant': 0, 'yaw': 90.0},
    1812: {'variant': 0, 'yaw': 180.0},
    # wave 3 (owner 2026-10-20): the Rimewater Ice Caves, the Serpent Catacombs and the Mirror Vaults, laid out the
    # same way (node_presentation.py); Verdigris, Venom Bulb and Lichen have one laid-out variant each.
    2201: {'variant': 0, 'yaw': 90.0},  # Lichen serpent_catacombs
    2202: {'variant': 0, 'yaw': 180.0},  # Lichen serpent_catacombs
    2203: {'variant': 0, 'yaw': 180.0},  # Lichen serpent_catacombs
    2204: {'variant': 0, 'yaw': 90.0},  # Lichen serpent_catacombs
    2205: {'variant': 0, 'yaw': 0.0},  # Venom Bulb serpent_catacombs
    2206: {'variant': 0, 'yaw': 270.0},  # Venom Bulb serpent_catacombs
    2207: {'variant': 0, 'yaw': 0.0},  # Venom Bulb serpent_catacombs
    # pass 2 wave A (owner 2026-10-21): laid-out organics of the regrown Old Warren, the Deep Workings and the new
    # pockets, facing their open neighbours (node_presentation.py's rule); the ore of wave A's caves is in wall veins.
    3179: {'variant': 0, 'yaw': 0.0},  # Toadstool deep_workings
    3180: {'variant': 0, 'yaw': 180.0},  # Toadstool deep_workings
    3181: {'variant': 0, 'yaw': 0.0},  # Moss deep_workings
    3182: {'variant': 0, 'yaw': 180.0},  # Moss deep_workings
    3360: {'variant': 0, 'yaw': 180.0},  # Moss old_warren
    3361: {'variant': 0, 'yaw': 0.0},  # Moss old_warren
    3362: {'variant': 0, 'yaw': 180.0},  # Moss old_warren
    3363: {'variant': 0, 'yaw': 270.0},  # Moss old_warren
    3364: {'variant': 0, 'yaw': 180.0},  # Toadstool old_warren
    3365: {'variant': 0, 'yaw': 180.0},  # Toadstool old_warren
    3366: {'variant': 0, 'yaw': 180.0},  # Toadstool old_warren
    3367: {'variant': 0, 'yaw': 90.0},  # Toadstool old_warren
    3404: {'variant': 0, 'yaw': 270.0},  # Lichen heath_barrow
    3405: {'variant': 0, 'yaw': 180.0},  # Lichen heath_barrow
    3424: {'variant': 0, 'yaw': 270.0},  # Moss mill_race
    3425: {'variant': 0, 'yaw': 180.0},  # Moss mill_race
    3444: {'variant': 0, 'yaw': 180.0},  # Moss old_well
    3445: {'variant': 0, 'yaw': 180.0},  # Toadstool old_well
    # pass 2 wave B
    4032: {'variant': 0, 'yaw': 144.0},  # Ember Crystal basalt_tubes
    4033: {'variant': 0, 'yaw': 191.0},  # Ember Crystal basalt_tubes
    4133: {'variant': 1, 'yaw': 211.0},  # Salt saltwind_caves
    4134: {'variant': 0, 'yaw': 258.0},  # Salt saltwind_caves
    4241: {'variant': 1, 'yaw': 247.0},  # Quartz amethyst_geode
    4242: {'variant': 0, 'yaw': 294.0},  # Quartz amethyst_geode
    4331: {'variant': 1, 'yaw': 157.0},  # Kelp smugglers_grotto
    4332: {'variant': 0, 'yaw': 0.0},  # Kelp smugglers_grotto
    4333: {'variant': 1, 'yaw': 0.0},  # Kelp smugglers_grotto
    4334: {'variant': 0, 'yaw': 298.0},  # Kelp smugglers_grotto
    4335: {'variant': 1, 'yaw': 345.0},  # Shell smugglers_grotto
    4336: {'variant': 0, 'yaw': 32.0},  # Shell smugglers_grotto
    4337: {'variant': 1, 'yaw': 270.0},  # Shell smugglers_grotto
    4338: {'variant': 0, 'yaw': 126.0},  # Shell smugglers_grotto
    4339: {'variant': 0, 'yaw': 0.0},  # Pearl smugglers_grotto
    4340: {'variant': 0, 'yaw': 220.0},  # Pearl smugglers_grotto
    4341: {'variant': 0, 'yaw': 267.0},  # Pearl smugglers_grotto
    # pass 2 wave C
    # Pass 2 wave C (owner 2026-10-21): the laid-out organics of the Undercity and the Sunken Sanctum, facing their
    # open neighbours (Lichen and Venom Bulb have one laid-out variant each).
    5257: {'variant': 0, 'yaw': 353.2},  # Lichen serpent_undercity
    5258: {'variant': 0, 'yaw': 0.0},  # Lichen serpent_undercity
    5259: {'variant': 0, 'yaw': 180.0},  # Lichen serpent_undercity
    5260: {'variant': 0, 'yaw': 90.0},  # Lichen serpent_undercity
    5261: {'variant': 0, 'yaw': 90.0},  # Lichen serpent_undercity
    5262: {'variant': 0, 'yaw': 90.0},  # Lichen serpent_undercity
    5263: {'variant': 0, 'yaw': 258.7},  # Lichen serpent_undercity
    5264: {'variant': 0, 'yaw': 180.0},  # Lichen serpent_undercity
    5265: {'variant': 0, 'yaw': 90.0},  # Lichen serpent_undercity
    5266: {'variant': 0, 'yaw': 180.0},  # Lichen serpent_undercity
    5267: {'variant': 0, 'yaw': 139.0},  # Lichen serpent_undercity
    5268: {'variant': 0, 'yaw': 276.0},  # Lichen serpent_undercity
    5269: {'variant': 0, 'yaw': 53.0},  # Lichen serpent_undercity
    5270: {'variant': 0, 'yaw': 190.0},  # Lichen serpent_undercity
    5271: {'variant': 0, 'yaw': 327.0},  # Lichen serpent_undercity
    5272: {'variant': 0, 'yaw': 104.0},  # Lichen serpent_undercity
    5273: {'variant': 0, 'yaw': 241.0},  # Lichen serpent_undercity
    5274: {'variant': 0, 'yaw': 18.0},  # Lichen serpent_undercity
    5275: {'variant': 0, 'yaw': 155.0},  # Lichen serpent_undercity
    5276: {'variant': 0, 'yaw': 292.0},  # Lichen serpent_undercity
    5277: {'variant': 0, 'yaw': 180.0},  # Venom Bulb serpent_undercity
    5278: {'variant': 0, 'yaw': 260.3},  # Venom Bulb serpent_undercity
    5279: {'variant': 0, 'yaw': 180.0},  # Venom Bulb serpent_undercity
    5280: {'variant': 0, 'yaw': 90.0},  # Venom Bulb serpent_undercity
    5281: {'variant': 0, 'yaw': 270.0},  # Venom Bulb serpent_undercity
    5282: {'variant': 0, 'yaw': 180.0},  # Venom Bulb serpent_undercity
    5283: {'variant': 0, 'yaw': 68.2},  # Venom Bulb serpent_undercity
    5284: {'variant': 0, 'yaw': 339.6},  # Venom Bulb serpent_undercity
    5285: {'variant': 0, 'yaw': 85.0},  # Venom Bulb serpent_undercity
    5286: {'variant': 0, 'yaw': 222.0},  # Venom Bulb serpent_undercity
    5287: {'variant': 0, 'yaw': 359.0},  # Venom Bulb serpent_undercity
    5288: {'variant': 0, 'yaw': 136.0},  # Venom Bulb serpent_undercity
    5289: {'variant': 0, 'yaw': 273.0},  # Venom Bulb serpent_undercity
    5290: {'variant': 0, 'yaw': 50.0},  # Venom Bulb serpent_undercity
    5291: {'variant': 0, 'yaw': 187.0},  # Venom Bulb serpent_undercity
    5292: {'variant': 0, 'yaw': 324.0},  # Venom Bulb serpent_undercity
    5297: {'variant': 0, 'yaw': 0.0},  # Venom Bulb sunken_sanctum
    5298: {'variant': 0, 'yaw': 0.0},  # Venom Bulb sunken_sanctum
    5299: {'variant': 0, 'yaw': 180.0},  # Venom Bulb sunken_sanctum
    5300: {'variant': 0, 'yaw': 340.0},  # Venom Bulb sunken_sanctum
    5301: {'variant': 0, 'yaw': 117.0},  # Venom Bulb sunken_sanctum
    5302: {'variant': 0, 'yaw': 111.8},  # Lichen sunken_sanctum
    5303: {'variant': 0, 'yaw': 270.0},  # Lichen sunken_sanctum
    5304: {'variant': 0, 'yaw': 168.0},  # Lichen sunken_sanctum
    5305: {'variant': 0, 'yaw': 305.0},  # Lichen sunken_sanctum
}


# Wall seam art for the ore labels (pass 2, 2026-10-21): label -> [(SELECTION asset, MineralAppearance palette), ...].
# Chosen from renders of reviewed kit pieces set into the Lantern Mine's wall (work-output/underground-pass2/platform/
# seams/); a vein alternates through its label's list. Organics (Moss, Toadstool, Lichen, Venom Bulb, Kelp, Shell,
# Pearl, Resin, Sap) keep their own art and stay open.
ROCK_SEAMS = ('seam_boulder_5', 'seam_boulder_3', 'seam_boulder_4')
CRYSTAL_SEAMS = ('seam_crystal_5', 'seam_crystal_4')
SEAM_PALETTES = {  # MineralAppearance {stone, mineral}: the floor ores' palettes where the label has one
    'Coal': ('#25282b', '#171a1d'), 'Iron Ore': ('#777979', '#8d5d3c'), 'Copper': ('#777471', '#b87333'),
    'Sulfur': ('#777468', '#d8b94c'), 'Slate': ('#5d656d', '#77818a'), 'Flint': ('#5a5852', '#34343a'),
    'Clay': ('#7a6a58', '#b5835a'), 'Salt': ('#8c8a84', '#f2efe6'), 'Verdigris': ('#6b6258', '#3fae8a'),
    'Crystal': ('#77748a', '#9b74d5'), 'Quartz': ('#8a8a8e', '#efeaf6'), 'Stormglass': ('#56606a', '#86c4e4'),
    'Ember Crystal': ('#3e3836', '#ff7a2c'), 'Geode': ('#666572', '#b093d0'),
}
WALL_SEAMS = {label: [(asset, {'stone': stone, 'mineral': mineral})
                      for asset in (('seam_geode_3', 'seam_crystal_5') if label == 'Geode' else
                                    CRYSTAL_SEAMS if label in ('Crystal', 'Quartz', 'Stormglass', 'Ember Crystal')
                                    else ROCK_SEAMS)]
              for label, (stone, mineral) in SEAM_PALETTES.items()}


def wall_presentation(plan, seams=None):
    """{object id: {resource, placement 'wall', yaw, inset, variant}} for every vein node of the plan (veins and
    build_underground.vein_faces); a vein's nodes alternate through their label's WALL_SEAMS."""
    from build_underground import vein_faces
    import underground_source as S
    seams = WALL_SEAMS if seams is None else seams
    result = {}
    for section in plan['sections']:
        faces = vein_faces(section)
        resources = {oid: res for oid, res, _x, _y in section['nodes']}
        for vein in S.veins(section):
            count = max(1, len(seams.get(vein['resource'], [])))
            for index, oid in enumerate(vein['nodes']):
                face = faces[oid]
                result[oid] = {'resource': resources[oid], 'placement': 'wall', 'variant': index % count,
                               'yaw': face['yaw'], 'inset': face['inset']}
    return result


def harvest_presentation(plan):
    """underground-scenery.json `harvestPresentation`: object id -> its resource and HARVEST_PRESENTATION entry, and
    every vein node's wall presentation (wall_presentation())."""
    nodes = {oid: res for section in plan['sections'] for oid, res, _x, _y in section['nodes']}
    unknown = sorted(set(HARVEST_PRESENTATION) - set(nodes))
    if unknown:
        raise ValueError(f'HARVEST_PRESENTATION names no underground node: {unknown}')
    walls = wall_presentation(plan)
    both = sorted(set(walls) & set(HARVEST_PRESENTATION))
    if both:
        raise ValueError(f'vein nodes are presented set into the wall; drop their HARVEST_PRESENTATION rows: {both}')
    listed = {oid: {'resource': nodes[oid], **hint} for oid, hint in HARVEST_PRESENTATION.items()}
    listed.update(walls)
    return {str(oid): listed[oid] for oid in sorted(listed)}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, document):
    # LF on every platform: a Windows text-mode write turns a one-entry change
    # into a whole-file diff of the shared registry.
    path.write_text(json.dumps(document, indent=2)+'\n', encoding='utf-8', newline='\n')


def matrix(node):
    if 'matrix' in node:
        return np.array(node['matrix']).reshape(4, 4).T
    from scipy.spatial.transform import Rotation
    result = np.eye(4)
    result[:3, :3] = Rotation.from_quat(node.get('rotation', [0, 0, 0, 1])).as_matrix()
    result[:3, :3] *= np.array(node.get('scale', [1, 1, 1]))[None, :]
    result[:3, 3] = node.get('translation', [0, 0, 0])
    return result


def bounds(document, blob):
    points = []

    def visit(index, parent):
        node = document['nodes'][index]
        world = parent @ matrix(node)
        if 'mesh' in node:
            for primitive in document['meshes'][node['mesh']]['primitives']:
                vertices = accessor(document, blob, primitive['attributes']['POSITION'])
                if 'indices' in primitive:
                    vertices = vertices[accessor(document, blob, primitive['indices']).astype(int).ravel()]
                points.append(vertices @ world[:3, :3].T + world[:3, 3])
        for child in node.get('children', []):
            visit(child, world)

    for index in document['scenes'][document.get('scene', 0)]['nodes']:
        visit(index, np.eye(4))
    vertices = np.concatenate(points)
    return vertices.min(0), vertices.max(0)


def package(name, spec, output):
    region, slug, measure, size = spec
    source = ROOT / KITS.get(region, f'godot-client/world_authoring/regions/{region}/assets/prototypes') / f'kit-{slug}.glb'
    if name == 'cave_mouth':
        source = ROOT / f'eloria-assets/maps/nymara-regions/{region}/assets/{slug}/model-reference.glb'
    source_bytes = source.read_bytes()
    document, original_blob = read_glb(source)
    preserved_cave = name == 'cave_mouth' and sha(source_bytes) == '8f7861af0f32d5ff561f2c6112c45136c9f917682e2a226739326a5e12d6a1e6'
    if not preserved_cave and 'prepare_meshy_kit' not in document['asset'].get('generator', ''):
        raise ValueError(f'{source.name}: selection must be an imported Meshy model')
    blob = bytearray(original_blob)
    if preserved_cave:
        # The game has a quantization extension, but the editor's standalone
        # importer does not. Expand the same normalized attribute values so
        # both paths can load this reused source without a custom plugin.
        expanded = {}
        for mesh in document['meshes']:
            for primitive in mesh['primitives']:
                for key,index in list(primitive['attributes'].items()):
                    spec = document['accessors'][index]
                    if spec['componentType'] == 5126 or key.startswith(('JOINTS_','WEIGHTS_')): continue
                    if index not in expanded:
                        values = accessor(document,blob,index)
                        new_index = append_array(document,blob,values,spec['type'])
                        assert np.allclose(accessor(document,blob,new_index),values,atol=1e-7)
                        expanded[index] = new_index
                    primitive['attributes'][key] = expanded[index]
        for key in ('extensionsRequired','extensionsUsed'):
            document[key] = [v for v in document.get(key,[]) if v != 'KHR_mesh_quantization']
    if name == 'wall_lantern':
        # Reuse the imported lantern head and its bracket. The tall freestanding
        # post cannot sit outside a cutaway wall without appearing to float.
        for mesh in document['meshes']:
            for primitive in mesh['primitives']:
                positions = accessor(document, blob, primitive['attributes']['POSITION'])
                indices = accessor(document, blob, primitive['indices']).astype(int).reshape(-1,3)
                threshold = positions[:,1].min()+np.ptp(positions[:,1])*.63
                kept = indices[(positions[indices,1] >= threshold).all(axis=1)].astype('<u4').ravel()
                if not len(kept): raise ValueError('Lantern head selection is empty')
                blob.extend(b'\0'*(-len(blob)%4))
                document['bufferViews'].append({'buffer':0,'byteOffset':len(blob),'byteLength':kept.nbytes,'target':34963})
                blob.extend(kept.tobytes())
                document['accessors'].append({'bufferView':len(document['bufferViews'])-1,'componentType':5125,
                                             'count':len(kept),'type':'SCALAR','min':[int(kept.min())],'max':[int(kept.max())]})
                primitive['indices'] = len(document['accessors'])-1
    before = bounds(document, blob)
    extent = before[1] - before[0]
    factor = size / (extent[1] if measure == 'height' else max(extent[0], extent[2]))
    images = []
    changed_material = name == 'cave_mouth'
    base_image = None
    if changed_material:
        material = document['materials'][0]
        pbr = material['pbrMetallicRoughness']
        base_image = document['textures'][pbr['baseColorTexture']['index']]['source']
        pbr.pop('metallicRoughnessTexture', None)
        pbr['roughnessFactor'] = 1
        if 'normalTexture' in material: material['normalTexture']['scale'] = .35
    for image_index, image in enumerate(document.get('images', [])):
        if 'uri' not in image:
            continue
        image_path = (source.parent / image.pop('uri')).resolve()
        if image_index == base_image:
            image_path = ROOT/'eloria-assets/source/world_objects/underground/cave-earth-basecolor-v001.png'
            image['mimeType'] = 'image/png'
        if not image_path.is_relative_to(ROOT):
            raise ValueError('Image escaped the client checkout')
        payload = image_path.read_bytes()
        blob.extend(b'\0' * (-len(blob) % 4))
        image['bufferView'] = len(document['bufferViews'])
        document['bufferViews'].append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': len(payload)})
        blob.extend(payload)
        images.append({'sha256': sha(payload), 'bytes': len(payload)})
    scene = document['scenes'][document.get('scene', 0)]
    wrapper = len(document['nodes'])
    centre = np.array([(before[0][0]+before[1][0])/2, before[0][1], (before[0][2]+before[1][2])/2])
    if name == 'cave_mouth':
        # Align the original passage floor, rather than the lowest stones,
        # so its walk-in surface meets the served outdoor ground.
        centre[1] = -.23254863242764562
    document['nodes'].append({'name': f'RL_{name}', 'children': scene['nodes'],
                              'scale': [factor]*3, 'translation': (-centre*factor).tolist()})
    scene['nodes'] = [wrapper]
    document['buffers'][0]['byteLength'] = len(blob)
    document['asset']['extras'] = {'sourceModelSha256': sha(source_bytes),
                                  'processing': 'Reused geometry and UVs; embedded textures, optional stone atlas or lantern-face selection; outer size/floor transform'}
    destination = output / f'{name}.glb'
    write_glb(destination, document, blob)
    saved_document, saved_blob = read_glb(destination)
    if saved_blob[:len(original_blob)] != original_blob:
        raise ValueError('Source geometry or material data changed')
    if any('uri' in i for i in saved_document.get('images', [])):
        raise ValueError('Runtime model still needs an external image')
    low, high = bounds(saved_document, saved_blob)
    return {'id': name, 'source': source.relative_to(ROOT).as_posix(), 'sourceSha256': sha(source_bytes),
            'output': destination.relative_to(ROOT).as_posix(), 'sha256': sha(destination.read_bytes()),
            'bounds': [low.tolist(), high.tolist()], 'images': images,
            'sourceBinaryPrefixPreserved': True, 'newModelGeneration': False,
            'materialVariant': 'Generated matte stone atlas; reduced normal strength' if changed_material else None,
            'geometrySelection': 'Original upper lantern/bracket faces only' if name == 'wall_lantern' else 'Complete source model'}


def asset_path(name):
    """The res:// path every packaged piece is written to (package())."""
    return f'res://assets/world/underground/{name}.glb'


def scenery_config(map_id):
    """The scenery config of one interior (INTERIORS[map_id]), from its plan source and its builder's dressing and
    themes: {schemaVersion, map, sourcePlanSha256, assets, harvestPresentation, surfaces, placements}."""
    spec = INTERIORS[map_id]
    plan_path = ROOT / spec['plan']
    # Every section's dressing is the builder's: the same list decides what the walk grid blocks, and the
    # builder's theme table decides each section's surfaces (underground_scenery.gd reads them as data).
    if str(plan_path.parents[1]) not in sys.path:
        sys.path.insert(0, str(plan_path.parents[1]))
    builder = importlib.import_module(spec['builder'])
    plan = builder.load_design(plan_path)
    if plan['map']['id'] != map_id:
        raise ValueError(f"{spec['plan']} authors {plan['map']['id']}, not {map_id}")
    cells = plan['map']['cells']
    placements = []
    for section in plan['sections']:
        for item in builder.dressing(section):
            placement = {'asset': item['asset'], 'position': [item['x'], item['height'], cells-item['y']],
                         'yaw': item['yaw']}
            if item['scale'] != 1:
                placement['scale'] = item['scale']
            for key in PLACEMENT_KEYS:
                if key in item:
                    placement[key] = item[key]
            placements.append(placement)
    placed = {p['asset'] for p in placements}
    unknown = sorted(placed - set(SELECTION) - set(TOWN_SELECTION))
    if unknown:
        raise ValueError(f"{spec['plan']} or its builder's theme table places unpackaged assets: {unknown}")
    if spec['assets'] == 'all':
        town = sorted(placed & set(TOWN_SELECTION))
        if town:
            raise ValueError(f'{map_id} lists every SELECTION piece; give its TOWN_SELECTION pieces a SELECTION row '
                             f'instead: {town}')
        names = list(SELECTION)
    else:
        names = [name for name in (*SELECTION, *TOWN_SELECTION) if name in placed]
    return {'schemaVersion': 1, 'map': plan['map']['id'], 'sourcePlanSha256': sha(plan_path.read_bytes()),
            'assets': {name: asset_path(name) for name in names},
            'harvestPresentation': harvest_presentation(plan) if spec['harvest'] else {},
            'surfaces': builder.surfaces(plan),
            'placements': placements}


def config_bytes(config):
    """A config as write_json writes it."""
    return (json.dumps(config, indent=2)+'\n').encode('utf-8')


def configs(maps=None):
    """{map id: config} of every interior whose plan source is present (or of `maps`), in INTERIORS order (the caves
    first: a later builder imports build_underground and may set its frame)."""
    unknown = sorted(set(maps or ()) - set(INTERIORS))
    if unknown:
        raise SystemExit(f'no interior {unknown}: give one of {sorted(INTERIORS)}')
    return {map_id: scenery_config(map_id) for map_id, spec in INTERIORS.items()
            if (ROOT / spec['plan']).is_file() and (not maps or map_id in maps)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true', help='compare the configs with their files; write nothing')
    parser.add_argument('--map', action='append', choices=sorted(INTERIORS),
                        help="only this interior's config (repeatable); implies --configs-only")
    parser.add_argument('--configs-only', action='store_true',
                        help='write the scenery configs and nothing else: no model is packaged, reused-scenery.json '
                             'and objects.json are left as they are (refused while a config places a piece that is '
                             'not packaged yet)')
    args = parser.parse_args(argv)
    found = configs(args.map)
    if args.check:
        stale = [INTERIORS[m]['config'] for m, config in found.items()
                 if not (ROOT / INTERIORS[m]['config']).is_file()
                 or (ROOT / INTERIORS[m]['config']).read_bytes() != config_bytes(config)]
        print(json.dumps({'interiors': list(found), 'stale': stale}, indent=1))
        return 1 if stale else 0
    if args.map or args.configs_only:
        missing = sorted({name for config in found.values() for name in config['assets']
                          if not (ROOT / 'godot-client' / asset_path(name).removeprefix('res://')).is_file()})
        if missing:
            raise SystemExit(f'not packaged yet: {missing}; run the whole tool once to package them')
        for map_id, config in found.items():
            write_json(ROOT / INTERIORS[map_id]['config'], config)
        print(json.dumps({'written': [INTERIORS[m]['config'] for m in found]}, indent=1))
        return 0
    output = ROOT / OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    placed = {name for config in found.values() for name in config['assets']}
    rows = {**SELECTION, **{name: spec for name, spec in TOWN_SELECTION.items() if name in placed}}
    records = [package(name, spec, output) for name, spec in rows.items()]
    for record in records:
        if 'res://'+record['output'].split('godot-client/', 1)[1] != asset_path(record['id']):
            raise ValueError(f"{record['id']}: packaged at {record['output']}, not {asset_path(record['id'])}")
    report = ROOT / 'eloria-assets/source/world_objects/underground/reused-scenery.json'
    report.parent.mkdir(parents=True, exist_ok=True)
    write_json(report, {'schema': 'rabbitlands-reused-underground-scenery-v1', 'assets': records})
    for map_id, config in found.items():
        write_json(ROOT / INTERIORS[map_id]['config'], config)
    # the objects.json harvest entries are the caves' (their minerals, laid-out organics and wall seams)
    config = found.get('landfall_insides')
    if config is None:
        return 0
    catalog_path = ROOT/'godot-client/data/world/objects.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    harvest = catalog['harvestables']
    minerals = {
        'Coal':('1','25282b','171a1d'), 'Iron Ore':('2','777979','8d5d3c'),
        'Copper':('3','777471','b87333'), 'Sulfur':('1','777468','d8b94c'),
        'Slate':('2','5d656d','77818a'), 'Geode':('3','666572','b093d0'),
        'Crystal':('cluster','77748a','9b74d5'),
    }
    for label,(shape,stone,vein) in minerals.items():
        identity = 'rl_'+label.lower().replace(' ','_')+'_v1'
        asset = 'crystal_cluster' if shape == 'cluster' else 'resource_rock_'+shape
        # Reused scenery, not a row of imported_world_objects: several labels
        # share one packaged GLB and draw it in their own resource palette.
        # The retired procedural model it replaces keeps the label's tier.
        replaced = next(model for model, entry in harvest['models'].items()
                        if entry['label'] == label and entry.get('retired'))
        harvest['models'][identity] = {'label':label,'kind':'mineral','tier':harvest['models'][replaced]['tier'],
            'reusedScenery':True,'scene':config['assets'][asset],
            **measure_glb(ROOT/'godot-client'/config['assets'][asset].removeprefix('res://')),
            'resourcePalette':{'stone':'#'+stone,'mineral':'#'+vein},
            'source':'eloria-assets/source/world_objects/underground/reused-scenery.json','replaces':replaced}
        harvest['resources'][label] = identity
    # Labels whose own model stays retired everywhere else get underground art as a variant only: a node stands it
    # where a package (or this file's HARVEST_PRESENTATION) lays the node out, so every other map keeps its ring.
    laid_out = {
        'Moss': ('resource_moss', None), 'Toadstool': ('resource_toadstool', None),
        'Stormglass': ('crystal_cluster', {'stone': '#56606a', 'mineral': '#86c4e4'}),
        # wave 2
        'Pearl': ('resource_pearl', None), 'Sap': ('resource_sap', None),
        'Ember Crystal': ('resource_ember_crystal', {'stone': '#3e3836', 'mineral': '#ff7a2c'}),
        # wave 3: verdigris crusts (the scree's veins in copper green), venom bulbs, lichen-crusted stones
        'Verdigris': ('resource_verdigris', {'stone': '#6b6258', 'mineral': '#3fae8a'}),
        'Venom Bulb': ('resource_venom_bulb', None), 'Lichen': ('resource_lichen', None),
    }
    for label, (asset, palette) in laid_out.items():
        identity = 'rl_'+label.lower().replace(' ','_')+'_v1'
        own = harvest['models'][harvest['resources'][label]]
        harvest['models'][identity] = {'label':label,'kind':own['kind'],'tier':own['tier'],'reusedScenery':True,
            'scene':config['assets'][asset],
            **measure_glb(ROOT/'godot-client'/config['assets'][asset].removeprefix('res://')),
            **({'resourcePalette':palette} if palette else {}),
            'source':'eloria-assets/source/world_objects/underground/reused-scenery.json',
            # never on an undescribed node: the label's other maps keep their ring
            'standsAlone':False}
        harvest['variants'][label] = [identity]
    harvest['variants'] = dict(sorted(harvest['variants'].items()))
    # pass 2: the ores' wall seams, stood only on a wall node (MapObject3D.is_wall_placed)
    walls = {}
    for label, seams in WALL_SEAMS.items():
        own = harvest['models'][harvest['resources'][label]]
        walls[label] = []
        for index, (asset, palette) in enumerate(seams):
            identity = 'rl_'+label.lower().replace(' ','_')+f'_wall_{index+1}'
            harvest['models'][identity] = {'label':label,'kind':own['kind'],'tier':own['tier'],'reusedScenery':True,
                'scene':config['assets'][asset],
                **measure_glb(ROOT/'godot-client'/config['assets'][asset].removeprefix('res://')),
                'resourcePalette':palette,
                'source':'eloria-assets/source/world_objects/underground/reused-scenery.json',
                'placement':'wall','standsAlone':False}
            walls[label].append(identity)
    for stale in [m for m, entry in harvest['models'].items() if entry.get('placement') == 'wall'
                  and m not in {i for ids in walls.values() for i in ids}]:
        del harvest['models'][stale]
    if walls:
        harvest['wallVariants'] = dict(sorted(walls.items()))
    else:
        harvest.pop('wallVariants', None)
    write_json(catalog_path, catalog)
    for record in records:
        print(record['id'], record['bounds'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
