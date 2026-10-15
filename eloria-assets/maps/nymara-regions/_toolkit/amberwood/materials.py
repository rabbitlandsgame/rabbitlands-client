"""Single source of truth for Amberwood's material set.

Both the runtime GLB export and the offline preview renderer are built from
this table, so what is art-directed in a preview is exactly what ships.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import gltf, noise as N, textures as T


@dataclass(frozen=True)
class MaterialSpec:
    name: str
    texture: str                       # key into the generated texture set table
    roughness: float = 1.0
    metallic: float = 0.0
    base_color: tuple = (1.0, 1.0, 1.0, 1.0)
    emissive: tuple = (0.0, 0.0, 0.0)
    alpha_mode: str = "OPAQUE"
    alpha_cutoff: float = 0.45
    double_sided: bool = False
    normal_scale: float = 1.0


SPECS: tuple[MaterialSpec, ...] = (
    MaterialSpec("bark_oak", "bark_oak", roughness=1.0),
    MaterialSpec("bark_dark", "bark_dark", roughness=1.0),
    MaterialSpec("bark_pale", "bark_pale", roughness=0.98),
    MaterialSpec("foliage_amber", "foliage_amber", roughness=0.92,
                 alpha_mode="MASK", double_sided=True),
    MaterialSpec("foliage_gold", "foliage_gold", roughness=0.92,
                 alpha_mode="MASK", double_sided=True),
    MaterialSpec("foliage_rust", "foliage_rust", roughness=0.92,
                 alpha_mode="MASK", double_sided=True),
    MaterialSpec("foliage_green", "foliage_green", roughness=0.94,
                 alpha_mode="MASK", double_sided=True),
    MaterialSpec("foliage_dead", "foliage_dead", roughness=0.98,
                 alpha_mode="MASK", double_sided=True),
    MaterialSpec("undergrowth", "undergrowth", roughness=0.94,
                 alpha_mode="MASK", double_sided=True),
    MaterialSpec("timber_warm", "timber_warm", roughness=0.94),
    MaterialSpec("timber_grey", "timber_grey", roughness=0.96),
    MaterialSpec("timber_dark", "timber_dark", roughness=0.94),
    MaterialSpec("carved_wood", "carved_wood", roughness=0.90),
    MaterialSpec("shingles", "shingles", roughness=0.96),
    MaterialSpec("thatch_reed", "thatch_reed", roughness=1.0),
    MaterialSpec("ashlar", "ashlar", roughness=0.96),
    MaterialSpec("lime_plaster", "lime_plaster", roughness=0.94),
    MaterialSpec("packed_earth", "packed_earth", roughness=1.0),
    MaterialSpec("sooted_plaster", "sooted_plaster", roughness=0.97),
    MaterialSpec("charred_timber", "charred_timber", roughness=0.99),
    MaterialSpec("rubble_stone", "rubble_stone", roughness=0.98),
    MaterialSpec("cliff_rock", "cliff_rock", roughness=0.98),
    MaterialSpec("cobble_paving", "cobble_paving", roughness=0.94),
    MaterialSpec("forest_floor", "forest_floor", roughness=1.0),
    MaterialSpec("leaf_path", "leaf_path", roughness=1.0),
    MaterialSpec("shore_shingle", "shore_shingle", roughness=0.92),
    MaterialSpec("meadow_grass", "meadow_grass", roughness=1.0),
    MaterialSpec("scorched_ground", "scorched_ground", roughness=1.0),
    MaterialSpec("dark_iron", "dark_iron", roughness=0.72, metallic=1.0),
    MaterialSpec("woven_cloth", "woven_cloth", roughness=0.96, double_sided=True),
    MaterialSpec("canvas_awning", "canvas_awning", roughness=0.94, double_sided=True),
    MaterialSpec("amber_resin", "amber_resin", roughness=0.22,
                 emissive=(0.20, 0.085, 0.012)),
    MaterialSpec("amber_glass", "amber_glass", roughness=0.20,
                 emissive=(0.16, 0.070, 0.010)),
    MaterialSpec("water_sea", "water_sea", roughness=0.14,
                 base_color=(1.0, 1.0, 1.0, 0.86), alpha_mode="BLEND"),
    MaterialSpec("water_pool", "water_pool", roughness=0.18,
                 base_color=(1.0, 1.0, 1.0, 0.82), alpha_mode="BLEND"),
    MaterialSpec("water_stream", "water_stream", roughness=0.16,
                 base_color=(1.0, 1.0, 1.0, 0.78), alpha_mode="BLEND"),
    # Standing water underground: the same surface, unlit by any sky.
    MaterialSpec("water_deep", "water_pool", roughness=0.12,
                 base_color=(0.20, 0.30, 0.32, 0.90), alpha_mode="BLEND"),

    # -- Mirrorhold. Appended, never inserted: a region pins the material set
    # it embeds by name, and reordering this tuple would rewrite its GLB.
    MaterialSpec("snow_pack", "snow_pack", roughness=0.74),
    # Solid ice, and opaque for it. This carries whole terrain classes -
    # Mirrorhold's frozen lake, Whitehorn's glacier river - as well as the
    # seracs and cascades standing on them. Blended, none of that wrote depth,
    # each mesh sorted as one instance so a sheet drew over the props on it and
    # over its own nearer folds, and the shadow map skipped it entirely. The 6%
    # of translucency it used to carry never showed: ice a metre thick reads
    # through its texture and its 0.30 roughness, not through alpha.
    MaterialSpec("glacier_ice", "glacier_ice", roughness=0.30),
    MaterialSpec("blue_crystal", "blue_crystal", roughness=0.12,
                 emissive=(0.048, 0.152, 0.268)),
    MaterialSpec("veined_marble", "veined_marble", roughness=0.36),
    MaterialSpec("pale_ashlar", "pale_ashlar", roughness=0.90),
    MaterialSpec("gilt_brass", "gilt_brass", roughness=0.28, metallic=1.0),
    MaterialSpec("slate_roof", "slate_roof", roughness=0.84),
    MaterialSpec("alpine_turf", "alpine_turf", roughness=0.94),
    MaterialSpec("water_lake", "water_lake", roughness=0.13,
                 base_color=(1.0, 1.0, 1.0, 0.84), alpha_mode="BLEND"),
    # The mirror-sphere: the same crystal, darkened and polished, so it reads
    # as a polished dark mirror rather than a bright blue ball.
    MaterialSpec("mirror_glass", "blue_crystal", roughness=0.05, metallic=0.35,
                 base_color=(0.30, 0.38, 0.50, 1.0),
                 emissive=(0.012, 0.030, 0.058)),
    # -- Amethyst Barrens. Appended, never inserted: a region pins the material
    # set it embeds by name, and reordering this tuple would rewrite its GLB.
    # The region's sea reuses `water_sea` rather than adding a fourth water.
    MaterialSpec("amethyst_barrens_dust", "amethyst_barrens_dust", roughness=0.96),
    MaterialSpec("amethyst_storm_rock", "amethyst_storm_rock", roughness=0.90,
                 emissive=(0.020, 0.008, 0.036)),
    MaterialSpec("amethyst_crystal_field", "amethyst_crystal_field", roughness=0.42,
                 emissive=(0.088, 0.036, 0.152)),
    MaterialSpec("amethyst_resonant_road", "amethyst_resonant_road", roughness=0.66,
                 emissive=(0.072, 0.028, 0.128)),
    # The crystal itself carries the region's light. Emissive rather than
    # transmissive: KHR_materials_transmission is an extension, and the package
    # must load with none.
    MaterialSpec("amethyst_crystal", "amethyst_crystal", roughness=0.10,
                 emissive=(0.196, 0.088, 0.320)),
    MaterialSpec("amethyst_pale_stone", "amethyst_pale_stone", roughness=0.82),
    # Verdigris is a mineral crust, not bare metal, so a low metallic value is
    # both physically right and what keeps it readable: in a client with no
    # reflection probe a metallic surface facing away from the sky goes black,
    # which turned every spire cap into a charcoal cone.
    MaterialSpec("amethyst_verdigris", "amethyst_verdigris", roughness=0.68,
                 metallic=0.12),
    # Not metallic=1.0: a fully metallic surface has no diffuse term, so with
    # no environment probe it renders black - every brass pole, crane and
    # tripod came out as a charcoal stick. 0.62 still reads as metal and
    # survives a renderer without image-based lighting.
    MaterialSpec("amethyst_brass", "amethyst_brass", roughness=0.36, metallic=0.40),
    MaterialSpec("amethyst_banner", "amethyst_banner", roughness=0.90,
                 double_sided=True),
    # -- Amethyst Barrens interiors
    MaterialSpec("amethyst_vault_floor", "amethyst_vault_floor", roughness=0.30,
                 metallic=0.35),

    # -- Whitehorn interiors. Appended, never inserted.
    MaterialSpec("whitehorn_silver", "whitehorn_silver", roughness=0.34,
                 metallic=0.45),

    # -- Verdant Stair. Appended, never inserted: a region pins the material set
    # it embeds by name, and reordering this tuple would rewrite its GLB.
    MaterialSpec("verdant_jungle_floor", "verdant_jungle_floor", roughness=0.95),
    MaterialSpec("verdant_jungle_trail", "verdant_jungle_trail", roughness=0.95),
    MaterialSpec("verdant_terrace_stone", "verdant_terrace_stone", roughness=0.90),
    MaterialSpec("verdant_mossy_stone", "verdant_mossy_stone", roughness=0.94),
    # The one low-roughness ground in the region: rock that is never dry.
    MaterialSpec("verdant_wet_limestone", "verdant_wet_limestone", roughness=0.52),
    MaterialSpec("verdant_limestone_cliff", "verdant_limestone_cliff", roughness=0.92),
    MaterialSpec("verdant_lagoon_sand", "verdant_lagoon_sand", roughness=0.92),
    MaterialSpec("verdant_fern_glade", "verdant_fern_glade", roughness=0.90),
    # Jade is a cut stone, not a metal and not verdigris: metallic stays at zero
    # so it does not go black in a client with no reflection probe, the way the
    # Amethyst spire caps did.
    MaterialSpec("verdant_jade", "verdant_jade", roughness=0.44),
    MaterialSpec("verdant_carved_jade", "verdant_carved_jade", roughness=0.50),
    MaterialSpec("verdant_rope", "verdant_rope", roughness=0.97),
    MaterialSpec("verdant_frond", "verdant_frond", roughness=0.86,
                 alpha_mode="MASK", double_sided=True),
    MaterialSpec("verdant_vine", "verdant_vine", roughness=0.88,
                 alpha_mode="MASK", double_sided=True),
    MaterialSpec("water_lagoon", "water_lagoon", roughness=0.12,
                 base_color=(1.0, 1.0, 1.0, 0.80), alpha_mode="BLEND"),
    MaterialSpec("water_cenote", "water_cenote", roughness=0.11,
                 base_color=(1.0, 1.0, 1.0, 0.78), alpha_mode="BLEND"),
    # -- Grey Moors. Appended, never inserted: a region pins the material set
    # it embeds by name, and reordering this tuple would rewrite its GLB.
    # The region's sea reuses `water_sea`; its bog pools do not, because peat
    # water is a near-black mirror rather than anything blue.
    MaterialSpec("grey_heather_moor", "grey_heather_moor", roughness=0.98),
    MaterialSpec("grey_peat_bog", "grey_peat_bog", roughness=0.74),
    MaterialSpec("grey_causeway", "grey_causeway", roughness=0.78),
    MaterialSpec("grey_barrow_turf", "grey_barrow_turf", roughness=0.96),
    MaterialSpec("grey_moor_granite", "grey_moor_granite", roughness=0.92),
    MaterialSpec("grey_carved_stone", "grey_carved_stone", roughness=0.88),
    MaterialSpec("grey_bog_timber", "grey_bog_timber", roughness=0.80),
    MaterialSpec("grey_drystone", "grey_drystone", roughness=0.96),
    MaterialSpec("grey_turf_roof", "grey_turf_roof", roughness=0.97),
    MaterialSpec("grey_dead_bark", "grey_dead_bark", roughness=0.94),
    # NOT double-sided: the scrub cards carry their own back faces, so both
    # sides are front faces and Godot does not invert their normals.
    MaterialSpec("grey_moor_scrub", "grey_moor_scrub", roughness=0.95,
                 alpha_mode="MASK", double_sided=False),
    # Bog water is opaque, unlike the region's sea. Peat stain kills every ray
    # that enters it, and a BLEND surface over a carved basin only showed the
    # basin through it.
    MaterialSpec("grey_bog_water", "grey_bog_water", roughness=0.16,
                 base_color=(0.62, 0.66, 0.62, 1.0)),
    # The two lights of the region. Emissive rather than any real light source:
    # the package ships no KHR_lights_punctual, and the client lights the scene
    # from the manifest's environment block.
    MaterialSpec("grey_wisp", "grey_wisp", roughness=0.34,
                 emissive=(0.216, 0.404, 0.520)),
    MaterialSpec("grey_votive_flame", "grey_votive_flame", roughness=0.42,
                 emissive=(0.520, 0.320, 0.104)),
    # The worn moor track reuses the toolkit's packed-earth texture rather than
    # adding a recipe, but that texture is a warm red clay and read as a dirt
    # road cut across a cold wet moor. Tinted down and cooled here, which is
    # what `base_color` is for.
    MaterialSpec("grey_moor_track", "packed_earth", roughness=0.97,
                 base_color=(0.52, 0.53, 0.50, 1.0)),
    # Added for the barrows insides: an ossuary needs bone.
    MaterialSpec("grey_bone", "grey_bone", roughness=0.86),
    # Hatchery furnishings; append so existing region material order is stable.
    MaterialSpec("hatchery_eggshell", "hatchery_eggshell", roughness=0.72),
    MaterialSpec("lily_pad", "lily_pad", roughness=0.64),
    MaterialSpec("woodland_loam", "woodland_loam", roughness=1.0),
    MaterialSpec("woodland_track", "woodland_track", roughness=.97),
    MaterialSpec("alpine_snowfield", "alpine_snowfield", roughness=.98,
                 base_color=(.79,.82,.87,1),normal_scale=.12),
    MaterialSpec("alpine_blue_ice", "alpine_blue_ice", roughness=.66,
                 base_color=(.68,.80,.89,1),normal_scale=.15),
    MaterialSpec("alpine_gravel", "packed_earth", roughness=.98,
                 base_color=(.91,.94,.96,1),normal_scale=.22),
    MaterialSpec("alpine_bedrock", "alpine_bedrock", roughness=.95,
                 base_color=(.90,.94,1,1),normal_scale=.25),
    MaterialSpec("woodland_sward", "meadow_grass", roughness=1.0,
                 base_color=(.72, .98, .76, 1.0)),
    MaterialSpec("steppe_sward", "steppe_sward", roughness=1.0, normal_scale=.28),
    MaterialSpec("steppe_dust", "steppe_dust", roughness=.98, normal_scale=.22),
)

BY_NAME = {spec.name: spec for spec in SPECS}


def build_texture_sets() -> dict[str, T.TextureSet]:
    """Generate every texture set once. Deterministic and seeded."""
    sets: dict[str, T.TextureSet] = {}
    for hue in ("oak", "dark", "pale"):
        sets[f"bark_{hue}"] = T.bark(512, seed=11 + N.stable_hash(hue) % 97, hue=hue)
    for palette, seed in (("amber", 47), ("gold", 149), ("rust", 151),
                          ("green", 157), ("dead", 163)):
        sets[f"foliage_{palette}"] = T.foliage_atlas(512, seed=seed, palette=palette)
    sets["undergrowth"] = T.undergrowth_atlas(512, seed=127)
    for tone, seed in (("warm", 23), ("grey", 167), ("dark", 173)):
        sets[f"timber_{tone}"] = T.timber(512, seed=seed, tone=tone)
    sets["carved_wood"] = T.carved_wood(512, seed=29)
    sets["shingles"] = T.shingles(512, seed=37)
    sets["thatch_reed"] = T.thatch_reed(512, seed=107)
    sets["ashlar"] = T.ashlar(512, seed=53)
    sets["lime_plaster"] = T.lime_plaster(512, seed=211)
    sets["packed_earth"] = T.packed_earth(512, seed=223)
    sets["sooted_plaster"] = T.sooted_plaster(512, seed=233)
    sets["charred_timber"] = T.charred_timber(512, seed=241)
    sets["rubble_stone"] = T.rubble_stone(512, seed=61)
    sets["cliff_rock"] = T.cliff_rock(512, seed=67)
    sets["cobble_paving"] = T.cobble_paving(512, seed=83)
    sets["forest_floor"] = T.forest_floor(512, seed=71)
    sets["leaf_path"] = T.leaf_path(512, seed=79)
    sets["shore_shingle"] = T.shore_shingle(512, seed=113)
    sets["meadow_grass"] = T.meadow_grass(512, seed=131)
    # Mirrorhold
    sets["snow_pack"] = T.snow_pack(512, seed=401)
    sets["glacier_ice"] = T.glacier_ice(512, seed=409)
    sets["blue_crystal"] = T.blue_crystal(256, seed=419)
    sets["veined_marble"] = T.veined_marble(512, seed=421)
    sets["pale_ashlar"] = T.pale_ashlar(512, seed=431)
    sets["gilt_brass"] = T.gilt_brass(256, seed=433)
    sets["slate_roof"] = T.slate_roof(512, seed=439)
    sets["alpine_turf"] = T.alpine_turf(512, seed=443)
    sets["water_lake"] = T.water_surface(512, seed=449, tone="lake")
    sets["scorched_ground"] = T.scorched_ground(512, seed=109)
    sets["dark_iron"] = T.dark_iron(256, seed=101)
    sets["woven_cloth"] = T.woven_cloth(256, seed=103)
    sets["canvas_awning"] = T.canvas_awning(256, seed=139)
    sets["amber_resin"] = T.amber_resin(256, seed=97)
    sets["amber_glass"] = T.amber_glass(256, seed=137)
    for tone, seed in (("sea", 89), ("pool", 181), ("stream", 191)):
        sets[f"water_{tone}"] = T.water_surface(512, seed=seed, tone=tone)
    # Amethyst Barrens
    sets["amethyst_barrens_dust"] = T.amethyst_barrens_dust(512, seed=501)
    sets["amethyst_crystal_field"] = T.amethyst_crystal_field(512, seed=509)
    sets["amethyst_resonant_road"] = T.amethyst_resonant_road(512, seed=521)
    sets["amethyst_storm_rock"] = T.amethyst_storm_rock(512, seed=523)
    sets["amethyst_crystal"] = T.amethyst_crystal(256, seed=541)
    # Whitehorn
    sets["whitehorn_silver"] = T.whitehorn_silver(256, seed=601)
    sets["amethyst_pale_stone"] = T.amethyst_pale_stone(512, seed=547)
    sets["amethyst_verdigris"] = T.amethyst_verdigris(256, seed=557)
    sets["amethyst_brass"] = T.amethyst_brass(256, seed=563)
    sets["amethyst_banner"] = T.amethyst_banner(256, seed=569)
    sets["amethyst_vault_floor"] = T.amethyst_vault_floor(512, seed=577)
    # Verdant Stair
    sets["verdant_jungle_floor"] = T.verdant_jungle_floor(512, seed=601)
    sets["verdant_jungle_trail"] = T.verdant_jungle_trail(512, seed=607)
    sets["verdant_terrace_stone"] = T.verdant_terrace_stone(512, seed=613)
    sets["verdant_mossy_stone"] = T.verdant_mossy_stone(512, seed=617)
    sets["verdant_wet_limestone"] = T.verdant_wet_limestone(512, seed=619)
    sets["verdant_limestone_cliff"] = T.verdant_limestone_cliff(512, seed=631)
    sets["verdant_lagoon_sand"] = T.verdant_lagoon_sand(512, seed=641)
    sets["verdant_fern_glade"] = T.verdant_fern_glade(512, seed=643)
    sets["verdant_jade"] = T.verdant_jade(512, seed=647)
    sets["verdant_carved_jade"] = T.verdant_carved_jade(512, seed=653)
    sets["verdant_rope"] = T.verdant_rope(256, seed=659)
    sets["verdant_frond"] = T.verdant_frond_atlas(512, seed=661)
    sets["verdant_vine"] = T.verdant_vine_atlas(512, seed=673)
    for tone, seed in (("lagoon", 677), ("cenote", 683)):
        sets[f"water_{tone}"] = T.water_surface(512, seed=seed, tone=tone)

    # -- Grey Moors
    sets["grey_heather_moor"] = T.grey_heather_moor(512, seed=601)
    sets["grey_peat_bog"] = T.grey_peat_bog(512, seed=607)
    sets["grey_causeway"] = T.grey_causeway(512, seed=613)
    sets["grey_barrow_turf"] = T.grey_barrow_turf(512, seed=617)
    sets["grey_moor_granite"] = T.grey_moor_granite(512, seed=619)
    sets["grey_carved_stone"] = T.grey_carved_stone(512, seed=631)
    sets["grey_bog_timber"] = T.grey_bog_timber(512, seed=641)
    sets["grey_drystone"] = T.grey_drystone(512, seed=643)
    sets["grey_turf_roof"] = T.grey_turf_roof(512, seed=647)
    sets["grey_dead_bark"] = T.grey_dead_bark(512, seed=653)
    sets["grey_bog_water"] = T.grey_bog_water(512, seed=659)
    sets["grey_moor_scrub"] = T.grey_moor_scrub(512, seed=661)
    sets["grey_bone"] = T.grey_bone(512, seed=683)
    sets["grey_wisp"] = T.grey_wisp(128, seed=673)
    sets["grey_votive_flame"] = T.grey_votive_flame(128, seed=677)

    # trim the maps that do not need to ship at full resolution
    alpha_cut = {"foliage_amber", "foliage_gold", "foliage_rust", "foliage_green",
                 "foliage_dead", "undergrowth", "woven_cloth", "canvas_awning",
                 "verdant_frond", "verdant_vine", "grey_moor_scrub"}
    for name, texture_set in sets.items():
        texture_set.compact(orm_size=256, drop_normal=name in alpha_cut,
                            normal_size=256 if name.startswith("water") else None)
    sets["hatchery_eggshell"] = T.hatchery_eggshell(256, seed=719)
    sets["lily_pad"] = T.lily_pad(256, seed=727)
    sets["woodland_loam"] = T.forest_floor(512, seed=71, leaf_count=55, leaf_strength=.25)
    sets["woodland_loam"].name = "woodland_loam"
    sets["woodland_track"] = T.leaf_path(512, seed=79, leaf_count=18)
    sets["woodland_track"].name = "woodland_track"
    for name in ('alpine_snowfield','alpine_blue_ice','alpine_bedrock'):
        sets[name]=T.alpine_ground(name)
    for name in ('steppe_sward', 'steppe_dust'):
        sets[name] = T.steppe_ground(name)
    return sets


def register_gltf_materials(builder: "gltf.GltfBuilder",
                            sets: dict[str, T.TextureSet],
                            only: set[str] | None = None) -> dict[str, int]:
    """Embed textures and register materials in the GLB.

    `only` restricts the set to the materials a package actually uses. A small
    interior that draws on a dozen materials should not carry the whole region's
    texture library: embedding all of them costs about ten megabytes of images
    nothing references.
    """
    out: dict[str, int] = {}
    for spec in SPECS:
        if only is not None and spec.name not in only:
            continue
        texture_set = sets[spec.texture]
        images = texture_set.images()
        for name, blob in images.items():
            builder.add_image(name, blob)
        out[spec.name] = builder.add_material(gltf.Material(
            name=spec.name,
            base_color=spec.base_color,
            metallic=spec.metallic,
            roughness=spec.roughness,
            base_color_texture=f"{spec.texture}_basecolor",
            orm_texture=f"{spec.texture}_orm",
            normal_texture=(f"{spec.texture}_normal"
                            if f"{spec.texture}_normal" in images else None),
            normal_scale=spec.normal_scale,
            emissive=spec.emissive,
            alpha_mode=spec.alpha_mode,
            alpha_cutoff=spec.alpha_cutoff,
            double_sided=spec.double_sided))
    return out


def register_preview_materials(scene, sets: dict[str, T.TextureSet]) -> None:
    """Mirror the same table into the offline preview renderer."""
    from .render import RenderMaterial
    for spec in SPECS:
        texture_set = sets[spec.texture]
        alpha = texture_set.alpha
        if alpha is None:
            alpha = np.full(texture_set.base_color.shape[:2], 255, np.uint8)
        scene.add_texture(spec.texture + "_albedo",
                          np.dstack([texture_set.base_color, alpha]))
        scene.add_texture(spec.texture + "_orm",
                          np.dstack([texture_set.orm,
                                     np.full(texture_set.orm.shape[:2], 255, np.uint8)]))
        scene.add_material(RenderMaterial(
            name=spec.name,
            base_color=spec.base_color,
            roughness=spec.roughness,
            metallic=spec.metallic,
            emissive=spec.emissive,
            albedo=spec.texture + "_albedo",
            orm=spec.texture + "_orm",
            alpha_mode=spec.alpha_mode,
            alpha_cutoff=spec.alpha_cutoff,
            double_sided=spec.double_sided))


# Terrain classes are drawn with alpha-tested copies of the ground materials, so
# a class can be cut against its neighbour inside a cell rather than at the cell
# corner. The copies share the originals' textures - only the alpha mode differs
# - and they are separate entries so that a prop standing on packed earth is not
# alpha-tested for the sake of the road.
GROUND_SUFFIX = "_ground"
SOFT_GROUND_SUFFIX = "_soft_ground"


def base_material(name: str) -> str:
    """The pinned material an alpha-tested ground copy was made from.

    A region pins the materials it embeds and checks that every material its
    geometry references is on that list. A ground copy is not a new material -
    it carries the pinned one's textures and differs only in alpha mode - so
    the check has to look through the suffix or every region fails its own pin.
    """
    if name.endswith(SOFT_GROUND_SUFFIX):return name[:-len(SOFT_GROUND_SUFFIX)]
    return name[:-len(GROUND_SUFFIX)] if name.endswith(GROUND_SUFFIX) else name


def register_ground_materials(builder: "gltf.GltfBuilder",
                              sets: dict[str, T.TextureSet],
                              wanted: set[str]) -> None:
    """Register an alpha-tested copy of each named ground material.

    `wanted` is the set of material names the terrain meshes reference, which
    already carry `GROUND_SUFFIX`; anything else in it is ignored.
    """
    by_name = {spec.name: spec for spec in SPECS}
    for name in sorted(wanted):
        if not name.endswith(GROUND_SUFFIX):
            continue
        spec = by_name[base_material(name)]
        texture_set = sets[spec.texture]
        images = texture_set.images()
        for image_name, blob in images.items():
            builder.add_image(image_name, blob)
        builder.add_material(gltf.Material(
            name=name,
            base_color=spec.base_color,
            metallic=spec.metallic,
            roughness=spec.roughness,
            base_color_texture=f"{spec.texture}_basecolor",
            orm_texture=f"{spec.texture}_orm",
            normal_texture=(f"{spec.texture}_normal"
                            if f"{spec.texture}_normal" in images else None),
            normal_scale=spec.normal_scale,
            emissive=spec.emissive,
            alpha_mode="MASK",
            alpha_cutoff=0.5,
            double_sided=spec.double_sided))
