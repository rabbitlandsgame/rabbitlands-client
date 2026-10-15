"""Place the Sunmane Steppe kit across the landform.

Layout authority, in order: the written region description (four Orun clan
camps around a shared seasonal market and ceremonial crossroads, with
caravanserais on the travel axes and windmills, wells, animal pens, banner
shrines and burial mounds through the wider pastoral landscape), then the
aerial overview's composition, then the ten-panel board's player-scale detail.

Every kit asset becomes one glTF mesh and is instanced by node transform, so
repeated structures cost nodes rather than vertices.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_toolkit"))
import secretrooms as SR  # noqa: E402
import secrets_design as SECRETS  # noqa: E402

import kit
import terrain
import layout as DESIGN
from glb import Geometry, compose
from noise import stable_seed
from shapes import UV_SCALE, beam, box, frustum, polygon_points, ribbon, sphere

TAU = math.pi * 2.0

# ---------------------------------------------------------------- materials
# key -> (texture family, base colour, metallic, roughness, double sided, normal map)
MATERIALS = {
    kit.CANVAS_PALE: ("canvas", (0.98, 0.91, 0.77, 1.0), 0.0, 0.88, False),
    kit.CANVAS_RED: ("canvas", (0.74, 0.24, 0.19, 1.0), 0.0, 0.90, False),
    kit.CANVAS_OCHRE: ("canvas", (0.88, 0.64, 0.30, 1.0), 0.0, 0.90, False),
    kit.TIMBER_DARK: ("timber", (0.78, 0.74, 0.70, 1.0), 0.0, 0.92, False),
    kit.TIMBER_WARM: ("timber", (1.00, 0.84, 0.62, 1.0), 0.0, 0.88, False),
    kit.STONE_PALE: ("stone", (0.90, 0.80, 0.66, 1.0), 0.0, 0.86, False),
    # Menhirs are a darker, greyer stone than the pale sandstone of the mesas,
    # which is what makes them read as set monoliths in the concept art.
    "stone_menhir": ("stone", (0.52, 0.48, 0.44, 1.0), 0.0, 0.90, False),
    kit.STONE_DARK: ("stone", (0.88, 0.50, 0.32, 1.0), 0.0, 0.78, False),
    kit.THATCH: ("thatch", (1.00, 0.94, 0.76, 1.0), 0.0, 0.92, False),
    kit.LEATHER: ("leather", (1.00, 1.00, 1.00, 1.0), 0.0, 0.70, False),
    kit.TEXTILE: ("textile", (1.00, 1.00, 1.00, 1.0), 0.0, 0.86, True),
    kit.METAL: ("metal", (1.00, 1.00, 1.00, 1.0), 1.0, 0.44, False),
    kit.GOLD: ("metal", (1.00, 0.80, 0.34, 1.0), 1.0, 0.26, False),
    kit.BONE: ("bone", (1.00, 1.00, 1.00, 1.0), 0.0, 0.52, False),
    # Amethyst reads as a translucent-looking mineral through a low roughness
    # and a cool violet tint rather than a transmission extension the client
    # loader does not support.
    # Underground limestone: warm but desaturated, so a brazier tints it
    # rather than the material arriving pre-tinted.
    kit.CAVE_ROCK_PALE: ("cavern", (0.66, 0.62, 0.56, 1.0), 0.0, 0.93, False),
    kit.CAVE_ROCK_WARM: ("cavern", (0.56, 0.50, 0.44, 1.0), 0.0, 0.94, False),
    kit.CRYSTAL: ("crystal", (0.72, 0.56, 0.86, 1.0), 0.0, 0.18, False),
    # Vegetation skips the normal map: at blade and leaf scale it contributes
    # nothing, and dropping it lets those primitives ship without tangents.
    kit.FOLIAGE: ("thatch", (0.50, 0.56, 0.32, 1.0), 0.0, 0.94, False, False),
    kit.GRASS: ("thatch", (0.92, 0.84, 0.48, 1.0), 0.0, 0.94, True, False),
    kit.WHEAT: ("thatch", (0.94, 0.80, 0.44, 1.0), 0.0, 0.92, True, False),
    "ground_mound": ("ground", (0.90, 0.88, 0.66, 1.0), 0.0, 0.94, False),
    "road_surface": ("ground", (1.00, 0.84, 0.62, 1.0), 0.0, 0.94, False),
    "plaza_surface": ("stone", (0.74, 0.64, 0.49, 1.0), 0.0, 0.93, False),
}

CAMP_RADIUS = 25.0
CAMP_SIDES = 14
# The hall stood at (0, -13) with a 23 m drum: its plinth ran through the
# palisade and the north gate opened into its back wall, and the camp's
# north half was sealed in the walk grid. Smaller, and a little further
# from the gate, it leaves a lane round either side and a way out north.
HALL_CENTER = (0.0, -12.0)


@dataclass
class Placement:
    """One instanced kit asset on the map."""
    asset: str
    name: str
    x: float
    z: float
    rotation: float = 0.0
    scale: float = 1.0
    sink: float = 0.12
    collide: bool = False
    landmark: str | None = None
    interactive: dict | None = None
    footprint: float = 2.0
    cave: str | None = None


class Layout:
    def __init__(self, landform) -> None:
        self.landform = landform
        self.placements: list[Placement] = []

    def pads(self, minimum_footprint: float = 2.4) -> list[tuple[float, float, float]]:
        """Footprints that need the ground levelled under them."""
        pads = [(placement.x, placement.z, placement.footprint)
                for placement in self.placements
                if placement.footprint >= minimum_footprint]
        pads.append((0.0, 0.0, CAMP_RADIUS + 1.5))       # the enclosure itself
        return pads

    # ------------------------------------------------------------- grounding
    def ground(self, x: float, z: float, footprint: float) -> float:
        """Seating height for a flat-bottomed structure.

        The ground under anything with a real footprint has already been
        levelled by a terrain pad, so this takes the lowest sample but never
        lets a structure drop more than a small step below its centre - which
        is what previously buried wide buildings such as the great hall.
        """
        centre = self.landform.height_at(x, z)
        if footprint <= 0.1:
            return centre
        samples = [centre]
        for index in range(8):
            angle = TAU * index / 8
            for reach in (footprint, footprint * 0.55):
                samples.append(self.landform.height_at(x + math.cos(angle) * reach,
                                                       z + math.sin(angle) * reach))
        return max(float(min(samples)), centre - 0.45)

    def add(self, asset: str, name: str, x: float, z: float, **kwargs) -> Placement:
        placement = Placement(asset, name, x, z, **kwargs)
        self.placements.append(placement)
        return placement


# --------------------------------------------------------------- the layout
def compose_layout(landform: terrain.Landform) -> Layout:
    layout = Layout(landform)
    rng = np.random.default_rng(20260827)

    # === central encampment: ceremonial crossroads and shared market ======
    layout.add("great_hall", "Landmark_sunmane_great_hall", HALL_CENTER[0],
               HALL_CENTER[1], rotation=0.0, collide=True, footprint=9.6, sink=0.35,
               landmark="great-hall",
               interactive={"id": "great-hall-entrance", "kind": "entrance",
                            "label": "Hall of the Sunmane"})
    market_slots = ((-8.5, 7.0, 0.35), (8.5, 7.5, -0.32), (-9.5, 16.0, 0.12),
                    (9.0, 16.5, -0.15))
    for index, (x, z, spin) in enumerate(market_slots):
        layout.add("market_canopy_%d" % (index % 3), "Landmark_orun_seasonal_market_%02d"
                   % index, x, z, rotation=spin, collide=True, footprint=4.0,
                   landmark="seasonal-market",
                   interactive={"id": "market-stall-%02d" % index, "kind": "market",
                                "label": "Seasonal market stall"})
    for index, (x, z, spin) in enumerate((
            (-17.0, -6.0, 0.9), (17.5, -5.0, -0.8), (-16.0, -16.0, 0.4),
            (16.0, -15.0, -0.5), (-19.0, 6.0, 1.4), (19.0, 7.0, -1.3))):
        layout.add("camp_pavilion_%d" % (index % 2), "Encampment_Pavilion_%02d" % index,
                   x, z, rotation=spin, collide=True, footprint=3.4)
    layout.add("steppe_well", "Landmark_sunmane_well_00", -7.5, 12.0, rotation=0.2,
               collide=True, footprint=2.0, landmark="well",
               interactive={"id": "well-crossroads", "kind": "water",
                            "label": "Crossroads well"})
    for index, (x, z, spin) in enumerate(((-13.0, 21.0, 0.4), (13.5, 21.0, -0.4))):
        layout.add("tool_rack", "Encampment_ToolRack_%02d" % index, x, z, rotation=spin,
                   footprint=1.2)
    for index, (x, z) in enumerate(((-5.0, 21.5), (5.5, 22.0), (-20.0, -1.0),
                                    (20.0, 0.5))):
        layout.add("fire_pit", "Encampment_FirePit_%02d" % index, x, z,
                   rotation=float(rng.random()) * TAU, footprint=1.2)
    for index, (x, z, spin) in enumerate(((-12.0, 12.0, 0.7), (12.5, 12.5, -0.6),
                                          (-11.0, 21.0, 1.55))):
        layout.add("cart", "Encampment_Cart_%02d" % index, x, z, rotation=spin,
                   collide=True, footprint=1.6)
    for index, (x, z, spin) in enumerate(((-21.0, 12.0, 0.3), (21.0, 13.0, -0.3))):
        layout.add("hitching_post", "Encampment_Hitching_%02d" % index, x, z,
                   rotation=spin, footprint=1.8)
    layout.add("drying_rack", "Encampment_DryingRack_00", -18.0, 18.0, rotation=0.6,
               footprint=1.6)

    # Palisade gate bays where each cardinal road crosses the wall.
    gates = (("south", 0.0, 1.0), ("east", 1.0, 0.0), ("north", 0.0, -1.0),
             ("west", -1.0, 0.0))
    for name, dx, dz in gates:
        x, z = dx * CAMP_RADIUS, dz * CAMP_RADIUS
        layout.add("palisade_gate", "Gate_%s" % name.capitalize(), x, z,
                   rotation=math.atan2(dx, dz) + math.pi, collide=True, footprint=5.0,
                   sink=0.30, landmark="gate",
                   interactive={"id": "gate-%s" % name, "kind": "gate",
                                "label": "%s gate" % name.capitalize()})
    for index in range(4):
        angle = TAU * (index + 0.5) / 4
        x, z = math.cos(angle) * CAMP_RADIUS, math.sin(angle) * CAMP_RADIUS
        layout.add("gate_tower", "Encampment_WallTower_%02d" % index, x, z,
                   rotation=-angle, collide=True, footprint=2.4, sink=0.35)

    # === four Orun clan camps ============================================
    clan_names = ("Windmane", "Redgrass", "Saltmane", "Duskrider")
    tent_index = 0
    for camp_index, (cx, cz, radius) in enumerate(terrain.CAMP_CLEARINGS):
        facing = math.atan2(-cz, -cx)                 # doorways face the crossroads
        for slot in range(3):
            angle = facing + math.pi + (slot - 1) * 0.85
            tx = cx + math.cos(angle) * radius * 0.46
            tz = cz + math.sin(angle) * radius * 0.46
            layout.add("round_tent_%d" % (tent_index % 3),
                       "Landmark_orun_round_tent_%02d" % tent_index, tx, tz,
                       rotation=math.atan2(cz - tz, cx - tx), collide=True,
                       footprint=3.8, sink=0.18, landmark="round-tent",
                       interactive={"id": "tent-%02d" % tent_index, "kind": "dwelling",
                                    "label": "%s clan tent" % clan_names[camp_index]})
            tent_index += 1
        layout.add("banner_shrine_%d" % (camp_index % 3),
                   "Landmark_orun_banner_shrine_%02d" % camp_index,
                   cx + math.cos(facing) * radius * 0.62,
                   cz + math.sin(facing) * radius * 0.62,
                   rotation=facing + math.pi / 2, collide=True, footprint=2.6,
                   landmark="banner-shrine",
                   interactive={"id": "shrine-%02d" % camp_index, "kind": "shrine",
                                "label": "%s clan shrine" % clan_names[camp_index]})
        layout.add("fire_pit", "Camp%02d_FirePit" % camp_index, cx, cz,
                   rotation=float(rng.random()) * TAU, footprint=1.2)
        layout.add("drying_rack", "Camp%02d_DryingRack" % camp_index,
                   cx + math.cos(facing + 2.2) * radius * 0.55,
                   cz + math.sin(facing + 2.2) * radius * 0.55,
                   rotation=facing + 2.2, footprint=1.6)
        layout.add("cart", "Camp%02d_Cart" % camp_index,
                   cx + math.cos(facing - 2.0) * radius * 0.6,
                   cz + math.sin(facing - 2.0) * radius * 0.6,
                   rotation=facing - 2.0, collide=True, footprint=1.6)
        layout.add("hitching_post", "Camp%02d_Hitching" % camp_index,
                   cx + math.cos(facing + 1.2) * radius * 0.7,
                   cz + math.sin(facing + 1.2) * radius * 0.7,
                   rotation=facing + 1.2, footprint=1.8)
        layout.add("tool_rack", "Camp%02d_ToolRack" % camp_index,
                   cx + math.cos(facing - 1.1) * radius * 0.66,
                   cz + math.sin(facing - 1.1) * radius * 0.66,
                   rotation=facing - 1.1, footprint=1.2)

    # Four more banner shrines marking the road forks.
    for index, (x, z, spin) in enumerate((
            (-24.0, -21.0, 0.8), (25.0, -20.0, -0.7),
            (-25.0, 22.0, 2.3), (26.0, 24.0, -2.2))):
        layout.add("banner_shrine_%d" % (index % 3),
                   "Landmark_orun_banner_shrine_%02d" % (4 + index), x, z,
                   rotation=spin, collide=True, footprint=2.6, landmark="banner-shrine",
                   interactive={"id": "shrine-%02d" % (4 + index), "kind": "shrine",
                                "label": "Wayside banner shrine"})

    # === caravanserais on the travel axes =================================
    # Placed inboard of each portal tile, never on it: a traveller arrives on
    # the open road at the gate rather than inside the hall.
    axes = (("west", -42.0, 0.0, math.pi / 2), ("east", 42.0, 0.0, -math.pi / 2),
            ("north", 0.0, -40.0, math.pi), ("south", 2.0, 50.0, 0.0))
    for index, (name, x, z, spin) in enumerate(axes):
        layout.add("caravanserai_%d" % (index % 2),
                   "Landmark_sunmane_caravanserai_%02d" % index, x, z, rotation=spin,
                   collide=True, footprint=9.0, sink=0.30, landmark="caravanserai",
                   interactive={"id": "caravanserai-%s" % name, "kind": "waystation",
                                "label": "%s caravanserai" % name.capitalize()})

    # === windmills, wells, pens, barrows ==================================
    for index, (x, z, spin) in enumerate((
            (44.0, 36.0, 0.4), (56.0, 46.0, -0.6), (-46.0, 24.0, 1.2),
            (30.0, -56.0, 2.4), (-36.0, -48.0, -1.1), (62.0, 14.0, 0.9))):
        layout.add("windmill", "Landmark_sunmane_windmill_%02d" % index, x, z,
                   rotation=spin, collide=True, footprint=3.4, sink=0.25,
                   landmark="windmill",
                   interactive={"id": "windmill-%02d" % index, "kind": "production",
                                "label": "Steppe windmill"})
    for index, (x, z, spin) in enumerate((
            (-33.0, 30.0, 0.3), (47.0, -28.0, -0.9), (62.0, 22.0, 1.7))):
        layout.add("steppe_well", "Landmark_sunmane_well_%02d" % (index + 1), x, z,
                   rotation=spin, collide=True, footprint=2.0, landmark="well",
                   interactive={"id": "well-%02d" % (index + 1), "kind": "water",
                                "label": "Steppe well"})
    # The fourth well, filled in because the water hummed (thread H). The
    # well-digger and the crossroads keeper both point at it.
    layout.add("filled_well", "Landmark_sunmane_filled_well", -9.0, 40.0, rotation=0.7,
               collide=True, footprint=2.4, landmark="lore-site",
               interactive={"id": "fourth-well", "kind": "landmark",
                            "label": "The fourth well, filled"})
    for index, (x, z, radius, gate) in enumerate((
            (-30.0, -30.0, 7.0, 3), (40.0, -18.0, 6.5, 7), (56.0, 28.0, 6.8, 1),
            (-44.0, 40.0, 7.2, 5), (18.0, 40.0, 6.4, 9), (-16.0, -52.0, 6.6, 2))):
        layout.add("animal_pen_%d" % (index % 2),
                   "Landmark_sunmane_animal_pen_%02d" % index, x, z,
                   rotation=TAU * gate / 11.0, collide=True, footprint=radius,
                   landmark="animal-pen",
                   interactive={"id": "pen-%02d" % index, "kind": "livestock",
                                "label": "Horse paddock"})
    for index, (x, z, entrance) in enumerate((
            (0.0, -42.0, True), (-11.0, -46.0, False), (11.0, -47.0, False),
            (-6.0, -54.0, False), (7.0, -55.0, False), (-46.0, -14.0, False))):
        layout.add("burial_mound_%s" % ("entrance" if entrance else "plain"),
                   "Landmark_sunmane_burial_mound_%02d" % index, x, z,
                   rotation=math.pi if entrance else float(rng.random()) * TAU,
                   collide=True, footprint=5.4, sink=0.0, landmark="burial-mound",
                   interactive={"id": "barrow-%02d" % index, "kind": "landmark",
                                "label": ("Orun barrow, the sealed passage" if entrance
                                          else "Orun barrow")})

    # === remote outposts, stone circles, coast ============================
    for index, (x, z, spin) in enumerate((
            (-54.0, -60.0, 0.4), (58.0, -64.0, -0.8), (74.0, 44.0, 1.9),
            (-53.0, 14.0, 2.7), (44.0, -52.0, 0.9))):
        layout.add("watchtower", "Landmark_sunmane_outpost_%02d" % index, x, z,
                   rotation=spin, collide=True, footprint=3.0, sink=0.35,
                   landmark="outpost",
                   interactive={"id": "outpost-%02d" % index, "kind": "lookout",
                                "label": "Rider outpost"})
    stone_circles = ((-44.0, -18.0, 8.0, 7), (26.0, 44.0, 6.6, 6))
    for circle_index, (cx, cz, radius, count) in enumerate(stone_circles):
        for index in range(count):
            angle = TAU * index / count + 0.3 * circle_index
            layout.add("standing_stone_%d" % (index % 3),
                       "Landmark_sunmane_standing_stone_%d%02d" % (circle_index, index),
                       cx + math.cos(angle) * radius, cz + math.sin(angle) * radius,
                       rotation=-angle + 0.2, collide=True, footprint=1.0, sink=0.35,
                       landmark="standing-stones")
        layout.add("fire_pit", "StoneCircle%02d_Hearth" % circle_index, cx, cz,
                   rotation=0.5, footprint=1.2)
    compose_expansion(layout, rng)
    layout.add("dock", "Landmark_sunmane_landing_00", -55.0, 46.0,
               rotation=0.62, collide=True, footprint=3.0, sink=1.5,
               landmark="landing",
               interactive={"id": "cove-landing", "kind": "dock",
                            "label": "Saltmane cove landing"})
    # Roads remain outside the built footprints. Stable IDs keep their portals.
    for index,(x,z,spin) in enumerate(DESIGN.INNS):
        p=next(p for p in layout.placements if p.name=="Landmark_sunmane_caravanserai_%02d"%index)
        p.x,p.z,p.rotation=x,z,spin
    moves={
        "Landmark_sunmane_windmill_02":(-53,-7),
        "Landmark_sunmane_windmill_01":(58,50),
        "Landmark_sunmane_windmill_05":(83,6),
        "Landmark_sunmane_animal_pen_00":(-39,-59),
        "Landmark_sunmane_animal_pen_03":(-28,45),
        "Landmark_sunmane_animal_pen_02":(57,37),
        "Landmark_sunmane_animal_pen_05":(43,-51),
        "Landmark_sunmane_outpost_04":(51,-61),
        "Landmark_sunmane_burial_mound_05":(-4,-63),
        "Landmark_sunmane_desert_station_00":(0,-92),
        "Landmark_sunmane_desert_station_01":(56,-103),
        "Encampment_Cart_00":(-17,12),
        "Encampment_Cart_01":(17,13),
        "Encampment_Cart_02":(-16,18),
    }
    for p in layout.placements:
        if p.name in moves:p.x,p.z=moves[p.name]
    return layout


# --------------------------------------------------------------- kit meshes
def _asset_builders() -> dict:
    """Named kit variants. Variation is authored, not randomised at export."""
    def tent(variant: int):
        return lambda: kit.round_tent(
            radius=3.2 + 0.30 * variant, wall=2.45 + 0.12 * variant,
            peak=4.75 + 0.28 * variant, variant=variant)

    def prop(function, *args, **kwargs):
        def build():
            parts = kit.Parts()
            function(parts, *args, **kwargs)
            return parts
        return build

    builders = {
        "great_hall": lambda: kit.great_hall(6.5),
        "palisade_gate": lambda: kit.palisade_gate(5.2, 4.4),
        "gate_tower": lambda: kit.gate_tower(7.2, 2.4),
        "watchtower": kit.watchtower,
        "windmill": kit.windmill,
        "steppe_well": kit.steppe_well,
        "dock": kit.dock,
        "drying_rack": kit.drying_rack,
        "tool_rack": kit.tool_rack,
        "cart": lambda: kit.cart(kit.Parts()),
        "fire_pit": prop(kit.fire_pit, (0.0, 0.0), 0.85),
        "hitching_post": prop(kit.hitching_post, (0.0, 0.0), 3.2),
        "burial_mound_entrance": lambda: kit.burial_mound(5.4, 2.5, True),
        "burial_mound_plain": lambda: kit.burial_mound(4.4, 2.0, False),
        "filled_well": kit.filled_well,
        "march_gate": kit.march_gate,
        "secret_hatch": kit.secret_hatch,
    }
    for index in range(3):
        builders["round_tent_%d" % index] = tent(index)
        builders["market_canopy_%d" % index] = (
            lambda v=index: kit.market_canopy(6.4 + 0.5 * v, 4.0 + 0.25 * v, v))
        builders["banner_shrine_%d" % index] = (lambda v=index: kit.banner_shrine(v))
        builders["standing_stone_%d" % index] = (
            lambda v=index: kit.standing_stone(4.8 + 0.9 * v, 1.05 + 0.20 * v,
                                               0.06 + 0.04 * v, seed=v))
    for index in range(2):
        builders["camp_pavilion_%d" % index] = (
            lambda v=index: kit.camp_pavilion(5.2 + 0.5 * v, 4.2 + 0.3 * v, v))
        builders["caravanserai_%d" % index] = (lambda v=index: kit.caravanserai(v))
        builders["animal_pen_%d" % index] = (
            lambda v=index: kit.animal_pen(6.6 + 0.4 * v, 11 + v, 3 + 4 * v))
    for identifier, framed, crystal in (("framed", True, False),
                                       ("plain", False, False),
                                       ("crystal", False, True)):
        builders["cave_mouth_%s" % identifier] = (
            lambda f=framed, c=crystal: kit.cave_mouth(
                5.4, 4.6, 6.8, framed=f, crystal=c, seed=int(f)))
    builders["desert_water_station"] = kit.desert_water_station
    for index in range(3):
        builders["desert_waystone_%d" % index] = (
            lambda v=index: kit.desert_waystone(3.0 + 0.4 * v, seed=v))
        builders["crystal_cluster_%d" % index] = (
            lambda v=index: kit.crystal_cluster(0.9 + 0.35 * v, seed=v))
        builders["mountain_scree_%d" % index] = (
            lambda v=index: kit.mountain_scree(2.6 + 0.7 * v, seed=v))
        builders["dead_scrub_%d" % index] = (
            lambda v=index: kit.dead_scrub(0.7 + 0.25 * v, seed=v))
        builders["bleached_bones_%d" % index] = (
            lambda v=index: kit.bleached_bones(seed=v))
    for index in range(4):
        builders["badland_spire_%d" % index] = (
            lambda v=index: kit.badland_spire(9.0 + 2.4 * v, 2.0 + 0.5 * v,
                                              seed=v, crystal=v % 2 == 1))
    for index in range(3):
        builders["wheat_stand_%d" % index] = prop(
            kit.wheat_stand, (0.0, 0.0), 0.95 + 0.12 * index, stems=6 + index,
            seed=40 + index)
        builders["shrub_%d" % index] = (lambda v=index: kit.shrub(0.7 + 0.2 * v, seed=v))
        builders["steppe_tree_%d" % index] = (
            lambda v=index: kit.steppe_tree(5.4 + 0.9 * v, seed=v + 4))
        builders["shore_rock_%d" % index] = (
            lambda v=index: kit.shore_rock(1.2 + 0.6 * v, seed=v + 9))
    return builders


# ------------------------------------------------------------- in-place work
def _palisade(layout: Layout) -> tuple[Geometry, Geometry]:
    """The encampment palisade: a battered timber wall with a stake crest.

    The ring is walked as a dense polyline and only the gate openings
    themselves are omitted, so the wall meets each gate jamb instead of leaving
    a segment-wide hole beside it.
    """
    from shapes import wall_run

    timber = Geometry()
    stone = Geometry()
    landform = layout.landform
    corners = polygon_points((0, 0, 0), CAMP_RADIUS, CAMP_SIDES,
                             rotation=math.pi / CAMP_SIDES)
    gate_centres = [(0.0, CAMP_RADIUS), (CAMP_RADIUS, 0.0), (0.0, -CAMP_RADIUS),
                    (-CAMP_RADIUS, 0.0)]
    opening = 3.4                       # half-width of a gate opening in metres

    def in_opening(x: float, z: float) -> bool:
        return any(math.hypot(x - gx, z - gz) < opening for gx, gz in gate_centres)

    base = min(landform.height_at(x, z) for x, z in corners) - 0.55

    # Walk the ring at a fixed step and collect the runs that are not openings.
    step = 0.55
    samples: list[tuple[float, float]] = []
    for index in range(CAMP_SIDES):
        start_point = np.array(corners[index], dtype="float64")
        end_point = np.array(corners[(index + 1) % CAMP_SIDES], dtype="float64")
        length = float(np.linalg.norm(end_point - start_point))
        count = max(2, int(round(length / step)))
        for sub in range(count):
            point = start_point + (end_point - start_point) * (sub / count)
            samples.append((float(point[0]), float(point[1])))
    samples.append(samples[0])

    runs: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for x, z in samples:
        if in_opening(x, z):
            if len(current) > 1:
                runs.append(current)
            current = []
        else:
            current.append((x, z))
    if len(current) > 1:
        runs.append(current)

    for run in runs:
        # Simplify each run back to its corner points plus the run ends, so the
        # wall keeps the polygon's facets without a vertex every 0.55 m.
        simplified = [run[0]]
        for point in run[1:-1]:
            for corner in corners:
                if math.hypot(point[0] - corner[0], point[1] - corner[1]) < step:
                    simplified.append(point)
                    break
        simplified.append(run[-1])
        wall_run(stone, simplified, 0.75, 1.15, uv_scale=UV_SCALE["stone"],
                 base_y=base)
        wall_run(timber, simplified, 3.9, 0.62, uv_scale=UV_SCALE["timber"],
                 base_y=base + 0.7)
        # Stake crest and inner wall-walk along the run.
        travelled = 0.0
        for index in range(len(simplified) - 1):
            start_point = np.array(simplified[index], dtype="float64")
            end_point = np.array(simplified[index + 1], dtype="float64")
            length = float(np.linalg.norm(end_point - start_point))
            if length < 1e-6:
                continue
            direction = (end_point - start_point) / length
            inward = -np.array([(start_point[0] + end_point[0]) * 0.5,
                                (start_point[1] + end_point[1]) * 0.5])
            norm = float(np.linalg.norm(inward))
            inward = inward / norm if norm > 1e-6 else np.array([0.0, 1.0])
            stakes = max(1, int(length / 0.66))
            for stake in range(stakes):
                point = start_point + direction * (length * (stake + 0.5) / stakes)
                top = base + 4.6 + 0.13 * ((stake * 7 + index) % 3)
                frustum(timber, (point[0], base + 4.35, point[1]),
                        (point[0], top, point[1]), 0.30, 0.17, sides=6,
                        uv_scale=UV_SCALE["timber"])
            posts = max(1, int(length / 2.6))
            for post in range(posts):
                point = (start_point + direction * (length * (post + 0.5) / posts)
                         + inward * 0.95)
                beam(timber, (point[0], base, point[1]),
                     (point[0], base + 2.85, point[1]), 0.20,
                     uv_scale=UV_SCALE["timber"])
            walk_start = start_point + inward * 0.85
            walk_end = end_point + inward * 0.85
            beam(timber, (walk_start[0], base + 2.95, walk_start[1]),
                 (walk_end[0], base + 2.95, walk_end[1]), 1.5, 0.18,
                 uv_scale=UV_SCALE["timber"], roll=math.pi / 2)
            travelled += length
    return timber, stone


def _plaza(layout: Layout) -> Geometry:
    """The ceremonial crossroads pavement inside the enclosure."""
    geometry = Geometry()
    landform = layout.landform
    radius = 21.0
    steps = 34
    lift = 0.11
    for ring in range(steps):
        for segment in range(steps):
            x0 = -radius + 2 * radius * segment / steps
            x1 = -radius + 2 * radius * (segment + 1) / steps
            z0 = -radius + 2 * radius * ring / steps
            z1 = -radius + 2 * radius * (ring + 1) / steps
            cx, cz = (x0 + x1) * 0.5, (z0 + z1) * 0.5
            distance = math.hypot(cx, cz)
            if distance > radius:
                continue
            # Leave the hall podium and the gate thresholds clear.
            if math.hypot(cx - HALL_CENTER[0], cz - HALL_CENTER[1]) < 9.8:
                continue
            corners, uvs = [], []
            for px, pz in ((x0, z0), (x0, z1), (x1, z1), (x1, z0)):
                corners.append([px, landform.height_at(px, pz) + lift, pz])
                uvs.append([px / UV_SCALE["stone"], pz / UV_SCALE["stone"]])
            geometry.add(corners, [[0.0, 1.0, 0.0]] * 4, uvs, [0, 1, 2, 0, 2, 3])
    return geometry


def _road_dressing(layout: Layout) -> dict[str, Geometry]:
    """Wayposts, kerb stones and wheel-worn margin detail along the road network.

    The caravan roads themselves are terrain: the landform grades a corridor and
    classifies it, so there is no overlaid road decal to z-fight with the ground.
    """
    parts: dict[str, Geometry] = {kit.TIMBER_DARK: Geometry(), kit.STONE_PALE: Geometry(),
                                  kit.TEXTILE: Geometry()}
    landform = layout.landform
    rng = np.random.default_rng(5150)
    for name, path in terrain.ROADS.items():
        travelled = 0.0
        for index in range(len(path) - 1):
            ax, az = path[index]
            bx, bz = path[index + 1]
            length = math.hypot(bx - ax, bz - az)
            steps = max(1, int(length / 8.0))
            for step in range(steps):
                t = (step + 0.5) / steps
                x = ax + (bx - ax) * t
                z = az + (bz - az) * t
                if math.hypot(x, z) < CAMP_RADIUS + 3.0:
                    continue
                side = 1.0 if (step + index) % 2 == 0 else -1.0
                direction = ((bx - ax) / length, (bz - az) / length)
                across = (-direction[1] * side, direction[0] * side)
                px = x + across[0] * (terrain.ROAD_WIDTH * 0.5 + 0.9)
                pz = z + across[1] * (terrain.ROAD_WIDTH * 0.5 + 0.9)
                ground = landform.height_at(px, pz)
                if travelled % 24.0 < 8.0:
                    # A carved wayppost with a small pennant.
                    height = 2.2 + 0.4 * float(rng.random())
                    frustum(parts[kit.TIMBER_DARK], (px, ground - 0.4, pz),
                            (px, ground + height, pz), 0.16, 0.11, sides=6,
                            uv_scale=UV_SCALE["timber"])
                    from shapes import sheet
                    sheet(parts[kit.TEXTILE],
                          [(px, ground + height, pz),
                           (px + across[0] * 0.7, ground + height, pz + across[1] * 0.7),
                           (px + across[0] * 0.7, ground + height - 0.55,
                            pz + across[1] * 0.7),
                           (px, ground + height - 0.55, pz)],
                          uv_rect=(0.0, 0.0, 1.0, 0.8))
                else:
                    for stone_index in range(3):
                        offset = (stone_index - 1) * 1.1
                        sx = px + direction[0] * offset
                        sz = pz + direction[1] * offset
                        sphere(parts[kit.STONE_PALE],
                               (sx, landform.height_at(sx, sz) + 0.05, sz),
                               0.22 + 0.10 * float(rng.random()), rings=5, sides=7,
                               uv_scale=UV_SCALE["stone"], squash=0.6)
                travelled += length / steps
    return parts


# --------------------------------------------------------------- scatter pass
SCATTER_CHUNKS = 10
GRASS_PER_CHUNK = 300


def _scatter(layout: Layout) -> tuple[list[dict], list[tuple[str, float, float, float, float]]]:
    """Ground cover for the region.

    Only grass tufts are baked into per-chunk meshes: they are tiny, need to be
    dense, and instancing thousands of them would cost far more in nodes than
    the triangles are worth. Everything larger - shrubs, boulders, crop stands -
    is returned as an instance list so it shares one mesh per variant.
    """
    landform = layout.landform
    rng = np.random.default_rng(90210)
    span = terrain.HALF_EXTENT * 2.0 / SCATTER_CHUNKS
    origin_x = terrain.CENTRE[0] - terrain.HALF_EXTENT
    origin_z = terrain.CENTRE[1] - terrain.HALF_EXTENT
    slope = terrain.slope_field(landform)

    keep_out = [(placement.x, placement.z, placement.footprint + 1.6)
                for placement in layout.placements]
    keep_out.append((0.0, 0.0, CAMP_RADIUS + 1.0))

    def blocked(x: float, z: float) -> bool:
        for cx, cz, radius in keep_out:
            if (x - cx) ** 2 + (z - cz) ** 2 < radius * radius:
                return True
        return False

    def plantable(x: float, z: float,
                  max_slope: float = 1.05) -> tuple[int, float] | None:
        height = landform.height_at(x, z)
        if height < 0.5 or blocked(x, z):
            return None
        iz, ix = landform.index_of(x, z)
        if slope[iz, ix] > max_slope:
            return None
        return landform.class_at(x, z), height

    chunks: list[dict] = []
    instances: list[tuple[str, float, float, float, float]] = []
    for chunk_z in range(SCATTER_CHUNKS):
        for chunk_x in range(SCATTER_CHUNKS):
            x0 = origin_x + chunk_x * span
            z0 = origin_z + chunk_z * span
            parts = kit.Parts()
            for _ in range(GRASS_PER_CHUNK):
                x = x0 + float(rng.random()) * span
                z = z0 + float(rng.random()) * span
                found = plantable(x, z)
                if found is None:
                    continue
                terrain_class, height = found
                if terrain_class in (terrain.CLASS_ROCK, terrain.CLASS_SAND,
                                     terrain.CLASS_DESERT,
                                     terrain.CLASS_MOUNTAIN):
                    continue
                # The badland carries a thin, stressed fringe of grass rather
                # than the steppe's cover, so most tufts there are dropped.
                if terrain_class == terrain.CLASS_BADLAND and rng.random() < 0.82:
                    continue
                staging = kit.Parts()
                kit.grass_tuft(staging, (0.0, 0.0),
                               0.22 + 0.20 * float(rng.random()),
                               blades=4 + int(rng.integers(0, 3)),
                               seed=int(rng.integers(0, 99999)))
                _merge(parts, staging, x, height - 0.05, z, float(rng.random()) * TAU)
            if parts.triangles:
                chunks.append({"name": "Scatter_Chunk_%02d_%02d" % (chunk_x, chunk_z),
                               "parts": parts})

    # Crop stands inside the authored field blocks.
    for field_index, (cx, cz, half_x, half_z) in enumerate(terrain.FIELDS):
        rows = 7
        columns = 9
        for row in range(rows):
            for column in range(columns):
                x = cx - half_x * 0.82 + 2 * half_x * 0.82 * column / (columns - 1)
                z = cz - half_z * 0.82 + 2 * half_z * 0.82 * row / (rows - 1)
                x += float(rng.normal()) * 0.35
                z += float(rng.normal()) * 0.35
                found = plantable(x, z)
                if found is None:
                    continue
                instances.append(("wheat_stand_%d" % ((row + column) % 3), x,
                                  found[1] - 0.05, z, float(rng.random()) * TAU))

    # Shrubs and boulders, thinned so they read as accents rather than noise.
    for _ in range(1400):
        x = float(rng.uniform(origin_x, origin_x + terrain.HALF_EXTENT * 2.0))
        z = float(rng.uniform(origin_z, origin_z + terrain.HALF_EXTENT * 2.0))
        found = plantable(x, z)
        if found is None:
            continue
        terrain_class, height = found
        roll = float(rng.random())
        if terrain_class in (terrain.CLASS_STEPPE, terrain.CLASS_DRY_GRASS):
            if roll < 0.30:
                instances.append(("shrub_%d" % int(rng.integers(0, 3)), x,
                                  height - 0.08, z, float(rng.random()) * TAU))
            elif roll < 0.42:
                instances.append(("shore_rock_%d" % int(rng.integers(0, 3)), x,
                                  height - 0.22, z, float(rng.random()) * TAU))
        elif terrain_class in (terrain.CLASS_ROCK, terrain.CLASS_SAND):
            if roll < 0.34:
                instances.append(("shore_rock_%d" % int(rng.integers(0, 3)), x,
                                  height - 0.24, z, float(rng.random()) * TAU))

    # The new ground north and east reads as desert, badland and scree, so it
    # gets its own cover: dead scrub and sun-bleached bone in the dunes, crystal
    # shards and scrub on the badland, loose stone on the mountain slopes. It is
    # sampled separately from the steppe pass so the density can be tuned for
    # ground that should feel sparse without thinning the steppe as well.
    for _ in range(7200):
        x = float(rng.uniform(origin_x, origin_x + terrain.HALF_EXTENT * 2.0))
        z = float(rng.uniform(origin_z, origin_z + terrain.HALF_EXTENT * 2.0))
        # Loose stone belongs on ground the steppe pass rejects, so this pass
        # accepts a steeper slope; nothing planted here needs a flat footing.
        found = plantable(x, z, max_slope=1.8)
        if found is None:
            continue
        terrain_class, height = found
        roll = float(rng.random())
        rotation = float(rng.random()) * TAU
        if terrain_class == terrain.CLASS_DESERT:
            if roll < 0.16:
                instances.append(("dead_scrub_%d" % int(rng.integers(0, 3)), x,
                                  height - 0.06, z, rotation))
            elif roll < 0.21:
                instances.append(("bleached_bones_%d" % int(rng.integers(0, 3)),
                                  x, height - 0.04, z, rotation))
            elif roll < 0.25:
                instances.append(("shore_rock_%d" % int(rng.integers(0, 3)), x,
                                  height - 0.30, z, rotation))
        elif terrain_class == terrain.CLASS_BADLAND:
            if roll < 0.22:
                instances.append(("shore_rock_%d" % int(rng.integers(0, 3)), x,
                                  height - 0.26, z, rotation))
            elif roll < 0.34:
                instances.append(("dead_scrub_%d" % int(rng.integers(0, 3)), x,
                                  height - 0.06, z, rotation))
            elif roll < 0.40:
                instances.append(("crystal_cluster_%d" % int(rng.integers(0, 3)),
                                  x, height - 0.18, z, rotation))
        elif terrain_class == terrain.CLASS_MOUNTAIN:
            if roll < 0.30:
                instances.append(("shore_rock_%d" % int(rng.integers(0, 3)), x,
                                  height - 0.28, z, rotation))
            elif roll < 0.36:
                instances.append(("mountain_scree_%d" % int(rng.integers(0, 3)),
                                  x, height - 0.34, z, rotation))
            elif roll < 0.40:
                instances.append(("bleached_bones_%d" % int(rng.integers(0, 3)),
                                  x, height - 0.04, z, rotation))
    return chunks, instances


def _merge(target: kit.Parts, source: kit.Parts, x: float, y: float, z: float,
           rotation: float, scale: float = 1.0) -> None:
    matrix = compose((x, y, z), rotation_y=rotation, scale=scale)
    for key, geometry in source.items():
        target.geometry(key).extend(geometry, matrix)


# --------------------------------------------------------------------- entry
def populate(builder, landform: terrain.Landform, layout: Layout | None = None,
             lod: int = 1) -> dict:
    """Build every structure, prop and scatter mesh and attach it to the world.

    LOD2 keeps the terrain, the architecture and the landmark inventory, and
    drops the ground clutter and roadside dressing that cost draw calls without
    changing the region's silhouette at distance.
    """
    if layout is None:
        layout = compose_layout(landform)
    layout.landform = landform
    class _Materials(dict):
        """Create each material on first use, so nothing unused is embedded."""

        def __missing__(self, key: str) -> int:
            spec = MATERIALS[key]
            family, color, metallic, roughness, double_sided = spec[:5]
            normal_map = spec[5] if len(spec) > 5 else True
            index = builder.material(
                key, family, base_color=color, metallic=metallic,
                roughness=roughness, double_sided=double_sided,
                normal_map=normal_map)
            self[key] = index
            return index

    materials = _Materials()

    # --- instance the kit ------------------------------------------------
    meshes: dict[str, int] = {}
    unique_triangles = 0
    # Only build the kit assets this LOD actually places.
    wanted = {placement.asset for placement in layout.placements}
    wanted.update("steppe_tree_%d" % index for index in range(3))
    if lod == 1:
        wanted.update("%s_%d" % (family, index) for index in range(3)
                      for family in ("shrub", "shore_rock", "wheat_stand"))
    for asset, build_asset in _asset_builders().items():
        if asset not in wanted:
            continue
        parts = build_asset()
        ordered = [(geometry, materials[key]) for key, geometry in sorted(parts.items())
                   if geometry.triangle_count]
        if not ordered:
            continue
        welded = [(geometry.weld(), material) for geometry, material in ordered]
        for index, (geometry, _) in enumerate(welded):
            import checks
            checks.assert_well_formed(geometry, f"kit:{asset}[{index}]")
        mesh = builder.glb.mesh("Kit_" + asset, welded)
        if mesh is None:
            continue
        meshes[asset] = mesh
        unique_triangles += sum(geometry.triangle_count for geometry, _ in welded)

    instance_count = 0
    for placement in layout.placements:
        mesh = meshes.get(placement.asset)
        if mesh is None:
            continue
        ground = layout.ground(placement.x, placement.z, placement.footprint)
        matrix = compose((placement.x, ground - placement.sink, placement.z),
                         rotation_y=placement.rotation, scale=placement.scale)
        builder.instance(placement.name, mesh, matrix, collide=placement.collide)
        instance_count += 1
        if placement.landmark:
            tile = _server_tile(placement.x, placement.z)
            # Content past the addressable tile band is scenery that closes the
            # horizon - far spires, the range itself - and is declared as such
            # so nothing downstream mistakes it for somewhere a player can go.
            reachable = _addressable(tile)
            if placement.interactive and not reachable:
                raise ValueError(
                    "%s carries an interaction but sits outside the server's "
                    "addressable band at tile %s" % (placement.name, tile))
            builder.landmarks.append({
                "id": placement.name,
                "kind": placement.landmark,
                "node": placement.name,
                "position": [round(placement.x, 2), round(ground, 2),
                             round(placement.z, 2)],
                "serverTile": tile,
                "reachable": reachable,
                "rotationDegrees": round(math.degrees(placement.rotation), 1)})
        if placement.interactive:
            entry = dict(placement.interactive)
            entry.update({"node": placement.name,
                          "position": [round(placement.x, 2), round(ground + 1.0, 2),
                                       round(placement.z, 2)],
                          "serverTile": _server_tile(placement.x, placement.z)})
            builder.interactives.append(entry)

    # --- palisade, plaza, bridges, road dressing --------------------------
    timber_wall, stone_plinth = _palisade(layout)
    builder.emit("Structure_Palisade",
                 [(timber_wall, materials[kit.TIMBER_DARK]),
                  (stone_plinth, materials[kit.STONE_PALE])], collide=True)
    plaza = _plaza(layout)
    builder.emit("Terrain_Plaza_Crossroads", [(plaza, materials["plaza_surface"])])

    DESIGN.emit_bridges(builder,materials,landform)

    dressing = _road_dressing(layout) if lod == 1 else {}
    builder.emit("Detail_RoadDressing",
                 [(geometry, materials[key]) for key, geometry in sorted(dressing.items())
                  if geometry.triangle_count])

    # --- coastal trees and shoreline stacks --------------------------------
    tree_spots = ((-64.0, 62.0), (-60.0, 68.0), (-66.0, 44.0), (-56.0, 36.0),
                  (66.0, 76.0), (72.0, 70.0), (-52.0, -70.0), (-46.0, -66.0),
                  (78.0, 48.0), (-58.0, 24.0), (34.0, 74.0), (26.0, 78.0))
    rng = np.random.default_rng(31415)
    for index, (x, z) in enumerate(tree_spots):
        mesh = meshes.get("steppe_tree_%d" % (index % 3))
        if mesh is None:
            continue
        ground = layout.ground(x, z, 1.4)
        if ground < 0.6:
            continue
        builder.instance("Detail_Tree_%02d" % index, mesh,
                         compose((x, ground - 0.2, z),
                                 rotation_y=float(rng.random()) * TAU), collide=True)
        instance_count += 1

    # --- vegetation and ground clutter -------------------------------------
    scatter_chunks, scatter_instances = _scatter(layout) if lod == 1 else ([], [])
    scatter_triangles = 0
    for chunk in scatter_chunks:
        parts = chunk["parts"]
        ordered = [(geometry.weld(), materials[key])
                   for key, geometry in sorted(parts.items())
                   if geometry.triangle_count]
        scatter_triangles += sum(geometry.triangle_count for geometry, _ in ordered)
        builder.emit(chunk["name"], ordered, weld=False)
    for index, (asset, x, y, z, rotation) in enumerate(scatter_instances):
        mesh = meshes.get(asset)
        if mesh is None:
            continue
        builder.instance("Detail_%s_%04d" % (asset, index), mesh,
                         compose((x, y, z), rotation_y=rotation))
        instance_count += 1

    # --- lighting and environment markers ----------------------------------
    _lighting(builder, layout)

    builder.population = population_records(layout)
    return {"kitAssets": len(meshes), "kitUniqueTriangles": unique_triangles,
            "instances": instance_count, "scatterTriangles": scatter_triangles,
            "landmarks": len(builder.landmarks),
            "interactives": len(builder.interactives)}


def _server_tile(x: float, z: float) -> list[int]:
    return [int(round(x + 58.0)), int(round(58.0 - z))]


def _addressable(tile: list[int]) -> bool:
    """Whether a server tile exists: tiles are non-negative and 192 to a side."""
    return 0 <= tile[0] <= 191 and 0 <= tile[1] <= 191


def _lighting(builder, layout: Layout) -> None:
    """Warm landmark lights and transition lights, as described by the region QA.

    Emitted as named marker nodes plus manifest records rather than glTF light
    extensions, so the package needs no loader change; the client can bind them
    when regional lighting lands.
    """
    warm = (("great-hall", 0.0, -13.0, 7.0), ("market", 0.0, 10.0, 4.0),
            ("camp-windmane", -30.0, -40.0, 3.2), ("camp-redgrass", 46.0, -26.0, 3.2),
            ("camp-saltmane", 64.0, 20.0, 3.2), ("camp-duskrider", -40.0, 34.0, 3.2),
            ("cove-landing", -55.0, 46.0, 3.0), ("barrowfield", 0.0, -46.0, 3.0))
    transition = (("gate-south", 0.0, 25.0), ("gate-north", 0.0, -25.0),
                  ("gate-east", 25.0, 0.0), ("gate-west", -25.0, 0.0))
    builder.lights = []
    for identifier, x, z, height in warm:
        ground = layout.landform.height_at(x, z)
        name = "Light_Warm_" + identifier
        builder.glb.node(name, matrix=compose((x, ground + height, z)))
        builder.lights.append({
            "id": name, "kind": "warm-landmark", "node": name,
            "position": [x, round(ground + height, 2), z],
            "color": [1.0, 0.79, 0.53], "energyHint": 3.2, "rangeHint": 18.0})
    for identifier, x, z in transition:
        ground = layout.landform.height_at(x, z)
        name = "Light_Transition_" + identifier
        builder.glb.node(name, matrix=compose((x, ground + 4.6, z)))
        builder.lights.append({
            "id": name, "kind": "transition", "node": name,
            "position": [x, round(ground + 4.6, 2), z],
            "color": [1.0, 0.86, 0.66], "energyHint": 2.4, "rangeHint": 12.0})


# ------------------------------------------------------- runtime population
# Grazing herds, hitched mounts and paddock stock. These are declared for the
# client's ambient population system rather than baked into the world mesh, so
# they never become part of the static collision surface.
HERDS = (
    ("herd-north-pasture", "sunmane_steppe_horse", 7, (-39.0, -59.0), 5.4, "Idle_A"),
    ("herd-east-paddock", "sunmane_dun_mare", 6, (40.0, -18.0), 5.6, "Idle_A"),
    ("herd-saltmane-paddock", "sunmane_steppe_horse", 6, (57.0, 37.0), 5.8, "Idle_A"),
    ("herd-duskrider-paddock", "sunmane_dun_mare", 6, (-28.0, 45.0), 6.2, "Idle_A"),
    ("herd-south-paddock", "sunmane_steppe_horse", 5, (18.0, 40.0), 5.4, "Idle_A"),
    ("herd-barrow-paddock", "sunmane_grey_pony", 5, (43.0, -51.0), 5.6, "Idle_A"),
    ("herd-open-steppe-west", "sunmane_steppe_horse", 8, (-50.0, -8.0), 13.0, "Idle_A"),
    ("herd-open-steppe-east", "sunmane_dun_mare", 8, (66.0, -8.0), 12.0, "Idle_A"),
    ("herd-open-steppe-north", "sunmane_steppe_horse", 7, (-6.0, -64.0), 12.0, "Idle_A"),
    ("herd-open-steppe-south", "sunmane_dun_mare", 7, (24.0, 50.0), 12.0, "Idle_A"),
    ("mounts-crossroads", "sunmane_grey_pony", 4, (-21.0, 12.0), 2.6, "Idle_A"),
    ("mounts-east-hitching", "sunmane_grey_pony", 4, (21.0, 13.0), 2.6, "Idle_A"),
    ("mounts-west-caravanserai", "sunmane_grey_pony", 4, (-45.0, 12.0), 2.2, "Idle_A"),
    ("mounts-east-caravanserai", "sunmane_grey_pony", 4, (45.0, 11.0), 2.2, "Idle_A"),
    ("mounts-market", "sunmane_steppe_horse", 3, (-20.0, 12.0), 1.8, "Idle_A"),
    # The desert road: strings of ponies waiting out the heat at the two water
    # stations, and the picket lines of the three dune camps.
    ("mounts-dune-station-west", "sunmane_grey_pony", 3, (4.0, -88.0), 2.8, "Idle_A"),
    ("mounts-dune-station-east", "sunmane_grey_pony", 3, (64.0, -96.0), 2.8, "Idle_A"),
    ("mounts-dune-camp-north", "sunmane_dun_mare", 3, (-19.0, -108.0), 3.0, "Idle_A"),
    ("mounts-dune-camp-mid", "sunmane_grey_pony", 3, (46.0, -99.0), 3.0, "Idle_A"),
    ("mounts-dune-camp-east", "sunmane_dun_mare", 3, (86.0, -79.0), 3.0, "Idle_A"),
    ("herd-dune-margin", "sunmane_dun_mare", 6, (30.0, -78.0), 11.0, "Idle_A"),
    ("herd-foothill-pasture", "sunmane_steppe_horse", 6, (104.0, -60.0), 11.0, "Idle_A"),
)

# Server-owned population: NPCs, harvestables and hostile spawns the server
# profile must register. Recorded here so the server pull request has an exact
# list rather than a description.
# DESIGN owns the authored posts; server-content.json preserves final server
# tiles after collision-aware placement and is reapplied by the builder.
NPC_POSTS = (
    ("khan-of-the-sunmane", "Orun khan", (14.0, -21.0), "quest"),
    ("market-broker", "Seasonal market broker", (-15.0, 22.0), "trade"),
    ("horse-master", "Camp horse master", (-30.0, -34.0), "trade"),
    ("caravan-master-west", "West caravan master", (-42.0, 9.0), "travel"),
    ("caravan-master-east", "East caravan master", (42.0, 9.0), "travel"),
    ("shrine-keeper", "Banner shrine keeper", (-25.4, -33.8), "quest"),
    ("miller", "Steppe miller", (44.0, 33.0), "trade"),
    ("well-keeper", "Crossroads well keeper", (0.0, 28.0), "service"),
    ("barrow-warden", "Barrow warden", (1.0, -33.0), "quest"),
    ("cove-factor", "Cove landing factor", (-53.0, 44.0), "trade"),
    ("dune-well-keeper", "Dune well keeper", (4.0, -88.0), "service"),
    ("salt-factor", "Salt-pan factor", (65.0, -96.0), "trade"),
    ("wind-cave-watch", "Wind caves watch", (70.0, -112.0), "quest"),
    ("amethyst-prospector", "Amethyst prospector", (124.0, -96.0), "trade"),
    ("range-warden", "Whitehorn range warden", (103.0, -83.0), "quest"),
)

HARVESTABLES = (
    # Initial field seeds keep legacy marker identities. Final server-owned
    # tiles are reapplied from source/server-content.json after geometry export.
    ("sunmane-wheat", "Wheat", "crop",
     tuple((x, z - 5.0, w, d) if index == 1 else (x, z, w, d)
           for index, (x, z, w, d) in enumerate(terrain.FIELDS))),
    ("steppe-herbs", "Sage", "herb",
     ((-48.0, -20.0, 8.0, 8.0), (62.0, -40.0, 8.0, 8.0), (-24.0, 56.0, 8.0, 8.0))),
    ("shore-clay", "Clay", "mineral",
     ((-52.0, 47.0, 6.0, 6.0), (-52.0, -46.0, 6.0, 6.0))),
    ("mesa-flint", "Flint", "mineral",
     ((-6.0, -69.0, 7.0, 7.0), (67.0, -55.0, 7.0, 7.0))),
    ("amethyst-shard", "Crystal", "mineral",
     ((118.0, -103.0, 8.0, 8.0), (119.0, -63.0, 7.0, 7.0))),
    ("pan-salt", "Salt", "mineral",
     ((6.0, -124.0, 9.0, 9.0), (62.0, -110.0, 7.0, 7.0))),
    ("dune-sage", "Sage", "herb",
     ((-20.0, -108.0, 8.0, 8.0), (40.0, -96.0, 8.0, 8.0))),
    ("scree-ore", "Iron", "mineral",
     ((124.0, -40.0, 6.0, 6.0), (-46.0, -126.0, 6.0, 6.0))),
)

CREATURE_SPAWNS = (
    # Species keys are the server's, and every one draws a reviewed model in
    # the client. The old placeholder herds (elk, wild boar, mountain goat) are
    # gone: the steppe is horse and bison country, with the wolves and the
    # lion that follow the herds and the griffins that watch from the mesas.
    ("golden_plains_horse", "northern pasture", (-52.0, -50.0), 12.0, 3),
    ("golden_bison", "open steppe", (30.0, -50.0), 14.0, 3),
    ("dunrunner", "south-west scrub", (-48.0, 50.0), 11.0, 4),
    ("steppe_aurochs", "eastern pasture", (60.0, 30.0), 12.0, 3),
    ("red_fox", "dune margin scrub", (-24.0, -92.0), 12.0, 5),
    ("dire_wolf", "north mesa breaks", (-30.0, -68.0), 10.0, 2),
    ("dire_wolf", "wind cave approach", (56.0, -108.0), 11.0, 2),
    ("sunmane_cat", "eastern breaks", (74.0, -34.0), 10.0, 3),
    ("stormmane_lion", "amethyst badland", (114.0, -78.0), 12.0, 2),
    ("plains_griffin", "Whitehorn foothills", (92.0, -120.0), 12.0, 2),
    ("suncrest_heron", "coastal watering holes", (-52.0, 12.0), 9.0, 3),
    ("giant_mole", "crop ground", (34.0, 30.0), 8.0, 1),
)


def population_records(layout: Layout) -> dict:
    landform = layout.landform
    groups = []
    for identifier, model, count, (x, z), radius, animation in HERDS:
        groups.append({
            "id": identifier, "model": model, "count": count,
            "center": [x, round(landform.height_at(x, z), 2), z],
            "radius": radius, "animation": animation,
            "seed": stable_seed(identifier, 100000),
            "serverTile": _server_tile(x, z)})
    npcs = []
    for identifier, label, (x, z), role in NPC_POSTS:
        x,z=DESIGN.NPCS.get(label,(x,z))
        npcs.append({"id": identifier, "label": label, "role": role,
                     "position": [x, round(landform.height_at(x, z), 2), z],
                     "serverTile": _server_tile(x, z),
                     "spawnHook": "npcs.nymara.sunmane_steppe"})
    resources = []
    for identifier, label, kind, blocks in HARVESTABLES:
        for index, (x, z, half_x, half_z) in enumerate(blocks):
            resources.append({
                "id": "%s-%02d" % (identifier, index), "label": label, "kind": kind,
                "center": [x, round(landform.height_at(x, z), 2), z],
                "extent": [half_x, half_z], "serverTile": _server_tile(x, z),
                "harvestHook": "harvest.nymara.sunmane_steppe"})
    creatures = []
    for model, where, (x, z), radius, count in CREATURE_SPAWNS:
        creatures.append({
            "model": model, "area": where, "count": count, "radius": radius,
            "center": [x, round(landform.height_at(x, z), 2), z],
            "serverTile": _server_tile(x, z),
            "spawnHook": "spawns.nymara.sunmane_steppe"})
    return {
        "ambientPopulation": {
            "note": ("Scenery livestock instanced by the client's ambient "
                     "population system. They carry no actor id and no "
                     "collision, and are deliberately not baked into the world "
                     "mesh."),
            "groups": groups,
        },
        "runtimePopulation": {
            "note": ("Server-owned placements. The client does not spawn these; "
                     "they are recorded so the eloria-server region profile can "
                     "register them against the hooks in "
                     "maps/nymara-regions/region-connections.json."),
            "npcs": npcs, "resources": resources, "creatures": creatures,
            "hooks": {"npc": "npcs.nymara.sunmane_steppe",
                      "spawn": "spawns.nymara.sunmane_steppe",
                      "hazard": "hazards.nymara.sunmane_steppe",
                      "harvest": "harvest.nymara.sunmane_steppe"},
        },
    }


# ---------------------------------------------------------- expansion layout
# The desert basin, the Amethyst-influenced badlands and the mountain boundary
# that closes the region's north and east. Placement follows the continent
# master concept, which puts dry ochre badland and the Barrens' violet rock
# between the steppe and the northern ranges.

# Where the interior package puts an arriving player, so the two sides of each
# transition are declared together rather than inferred at runtime. The tiles
# come from `caves.py`, which places its entrance chamber on these coordinates.
CAVE_ARRIVALS = {
    "wind_caves": ("entrance-hall", (30, 12)),
    "crystal_hollow": ("adit-mouth", (30, 13)),
}

CAVE_SITES = (
    # id, x, z, facing (radians, the direction the mouth looks out toward),
    # width, height, depth, framed, crystal, destination map, label
    # Set into the south face of the eastern butte, a few metres off the desert
    # road, so the entrance is inside the server's addressable tile band and a
    # player can actually walk to the portal.
    # Destinations are map ids. They were Eternal Lands `.elm` paths until the
    # C client was retired and the server started sending ids, and the manifest
    # was being corrected by hand after every build because this table was not.
    ("wind_caves", 70.0, -117.0, 0.0, 5.6, 4.8, 7.0, True, False,
     "sunmane_wind_caves", "Sunmane Wind Caves"),
    ("crystal_hollow", 124.0, -96.0, -math.pi * 0.62, 5.0, 4.4, 6.4, False, True,
     "sunmane_crystal_hollow", "Amethyst Crystal Hollow"),
    ("drovers_shelter", -34.0, -126.0, math.pi * 0.15, 4.4, 3.8, 5.4, True, False,
     None, "Drovers' shelter"),
    ("east_adit", 132.0, -30.0, -math.pi * 0.5, 4.6, 4.0, 5.8, True, False,
     None, "Eastern adit"),
)

DESERT_STATIONS = ((4.0, -92.0, 0.2), (64.0, -100.0, 2.6))

# Which of the steppe's own assets stands for each kind of secret entrance.
SECRET_ASSETS = {
    "loose_stone": "standing_stone_2", "cairn": "desert_waystone_2",
    "cellar_hatch": "secret_hatch", "cracked_slab": "secret_hatch",
    "well_shaft": "steppe_well", "sand_sink": "cave_mouth_plain",
    "shrine_slab": "banner_shrine_0",
}

# Where the steppe hands over to its neighbours (region-connections.json). The
# west caravan road runs west to Mirrorhold, the desert track
# climbs north into the Barrens, and the shore road goes south to the Verdant
# Stair. Each gate stands inside the server's addressable band, astride the
# road it ends; the crossing tile is the gap between its two stones.
# id, x, z, rotation (stones flank the road), destination map, label
CROSSING_SITES = (
    ("west-landing", -52.0, 0.0, math.pi * 0.5, "mirrorhold",
     "The west road to Mirrorhold"),
    ("north-track", 8.0, -126.0, 0.0, "amethyst_barrens",
     "The desert track into the Amethyst Barrens"),
    ("south-track", 4.0, 40.0, 0.0, "verdant_stair",
     "The shore road to the Verdant Stair"),
)

WAYSTONE_SITES = ((2.0, -70.0, 0.4), (5.0, -104.0, 1.7), (30.0, -86.0, 3.0),
                  (56.0, -96.0, 5.1), (92.0, -106.0, 0.9), (12.0, -130.0, 2.2),
                  (120.0, -18.0, 4.4), (104.0, 0.0, 1.1))


def compose_expansion(layout: Layout, rng) -> None:
    """Add the desert, badland and mountain content to an existing layout."""
    # --- cave entrances ---------------------------------------------------
    for (identifier, x, z, facing, width, height, depth, framed, crystal,
         destination, label) in CAVE_SITES:
        asset = "cave_mouth_%s" % ("crystal" if crystal
                                   else ("framed" if framed else "plain"))
        placement = layout.add(
            asset, "Landmark_sunmane_cave_%s" % identifier, x, z,
            rotation=facing, collide=True, footprint=5.0, sink=0.20,
            landmark="cave-entrance",
            interactive={"id": "cave-%s" % identifier,
                         "kind": "portal" if destination else "shelter",
                         "label": label,
                         **({"destinationMap": destination,
                             "destinationSpawn": CAVE_ARRIVALS[identifier][0],
                             "destinationTile": list(
                                 CAVE_ARRIVALS[identifier][1])}
                            if destination else {})})
        placement.cave = identifier

    # --- the marches: the three gates out of the steppe --------------------
    for identifier, x, z, facing, destination, label in CROSSING_SITES:
        layout.add("march_gate", "Landmark_sunmane_march_%s" % identifier, x, z,
                   rotation=facing, collide=True, footprint=3.2, sink=0.1,
                   landmark="transition",
                   interactive={"id": identifier, "kind": "portal", "label": label,
                                "destinationMap": destination})

    # --- the secrets: the ways down the steppe keeps to itself --------------
    # Each stands inside the server's addressable band and is one of the
    # steppe's own assets; the interactive of kind `secret` is what the server
    # turns into a use-to-enter portal (see _toolkit/secretrooms.py).
    for index, secret in enumerate(SECRETS.SECRETS):
        asset = SECRET_ASSETS.get(secret.entrance, "standing_stone_1")
        x = float(secret.at[0]) + secret.offset[0]
        z = float(secret.at[1]) + secret.offset[1]
        if secret.kind == "mouth":
            target_map, target_spawn = secret.links[0][0], secret.links[0][1]
        else:
            target_map, target_spawn = "sunmane_steppe_secrets", secret.id
        layout.add(asset, "Landmark_sunmane_secret_%s" % secret.id, x, z,
                   rotation=(index * 1.9) % TAU, collide=True, footprint=1.8, sink=0.15,
                   landmark="secret",
                   interactive={"id": "secret-%s" % secret.id, "kind": "secret",
                                "secret": secret.id, "name": secret.name,
                                "label": SR.label_for(secret), "prop": secret.entrance,
                                "key": secret.key, "destinationMap": target_map,
                                "destinationSpawn": target_spawn})

    # --- desert water stations on the sand road ---------------------------
    for index, (x, z, spin) in enumerate(DESERT_STATIONS):
        layout.add("desert_water_station",
                   "Landmark_sunmane_desert_station_%02d" % index, x, z,
                   rotation=spin, collide=True, footprint=4.0, sink=0.25,
                   landmark="water-station",
                   interactive={"id": "desert-station-%02d" % index,
                                "kind": "water",
                                "label": "Desert water station"})

    # --- waystones marking the sand and badland tracks --------------------
    for index, (x, z, spin) in enumerate(WAYSTONE_SITES):
        layout.add("desert_waystone_%d" % (index % 3),
                   "Landmark_sunmane_waystone_%02d" % index, x, z, rotation=spin,
                   collide=True, footprint=1.4, landmark="waystone")

    # --- badland spires ----------------------------------------------------
    for index, (x, z, radius) in enumerate(terrain.SPIRE_SITES):
        layout.add("badland_spire_%d" % (index % 4),
                   "Landmark_sunmane_spire_%02d" % index, x, z,
                   rotation=float(rng.random()) * TAU, collide=True,
                   footprint=radius, sink=0.5, landmark="badland-spire")

    # --- amethyst crystal clusters through the badlands -------------------
    for index, (x, z) in enumerate((
            (112.0, -88.0), (120.0, -104.0), (104.0, -120.0), (134.0, -118.0),
            (96.0, -96.0), (142.0, -100.0), (128.0, -76.0), (88.0, -126.0),
            (116.0, -132.0), (150.0, -128.0), (108.0, -66.0), (140.0, -142.0))):
        layout.add("crystal_cluster_%d" % (index % 3),
                   "Detail_Amethyst_%02d" % index, x, z,
                   rotation=float(rng.random()) * TAU, footprint=1.0, sink=0.3)

    # --- outposts watching the new ground ---------------------------------
    for index, (x, z, spin) in enumerate((
            (18.0, -118.0, 0.3), (98.0, -92.0, 2.4), (124.0, -22.0, 4.0))):
        layout.add("watchtower", "Landmark_sunmane_outpost_%02d" % (5 + index),
                   x, z, rotation=spin, collide=True, footprint=3.0, sink=0.35,
                   landmark="outpost",
                   interactive={"id": "outpost-%02d" % (5 + index),
                                "kind": "lookout", "label": "Desert watch"})

    # --- desert camps ------------------------------------------------------
    for index, (cx, cz, facing) in enumerate(((-19.0, -113.0, 1.1),
                                              (46.0, -104.0, 3.9),
                                              (86.0, -84.0, 5.4))):
        for slot in range(2):
            angle = facing + (slot - 0.5) * 1.5
            layout.add("camp_pavilion_%d" % (slot % 2),
                       "Detail_DesertCamp_%02d_Pavilion_%d" % (index, slot),
                       cx + math.cos(angle) * 4.4, cz + math.sin(angle) * 4.4,
                       rotation=angle + math.pi, collide=True, footprint=3.4)
        layout.add("fire_pit", "Detail_DesertCamp_%02d_Fire" % index, cx, cz,
                   rotation=float(rng.random()) * TAU, footprint=1.2)
        layout.add("cart", "Detail_DesertCamp_%02d_Cart" % index,
                   cx + math.cos(facing + 2.3) * 5.2,
                   cz + math.sin(facing + 2.3) * 5.2,
                   rotation=facing + 2.3, collide=True, footprint=1.6)
        layout.add("hitching_post", "Detail_DesertCamp_%02d_Picket" % index,
                   cx + math.cos(facing - 1.8) * 5.4,
                   cz + math.sin(facing - 1.8) * 5.4,
                   rotation=facing - 1.8, footprint=1.8)

    # --- scree fans at the mountain foot -----------------------------------
    for index, (x, z) in enumerate((
            (-40.0, -146.0), (-6.0, -152.0), (36.0, -148.0), (74.0, -144.0),
            (114.0, -150.0), (146.0, -132.0), (152.0, -86.0), (150.0, -44.0),
            (146.0, 4.0), (-64.0, -140.0), (96.0, -156.0), (24.0, -158.0))):
        layout.add("mountain_scree_%d" % (index % 3),
                   "Detail_Scree_%02d" % index, x, z,
                   rotation=float(rng.random()) * TAU, footprint=2.4, sink=0.4)
