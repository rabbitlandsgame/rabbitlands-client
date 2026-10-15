"""Ssarathi Ruins placement passes.

Built in the order the production guide prescribes - water first, then massing,
then landmarks, then dressing - so each pass can rely on everything coarser than
it already being final. The terrain was proven against the runtime grounding
contract before any of this was written.

Three rules run through the whole file:

* **Instance, do not duplicate.** One mesh per length class of balustrade, one
  per bridge span class, one per tree species and detail tier. A grown tree is
  three to four thousand triangles; authoring six hundred of them uniquely
  would cost more than the rest of the region put together.

* **Walk surfaces are registered, never assumed.** Almost all of Ssarathi's
  walkable ground is *terrain* - the causeways are stone embankments, not
  decks - so the only `add_walk` geometry in the region is the channel bridges,
  the docks, the temple stair and summit, the vault threshold, the stela plinth
  and the shrine steps. Everything else is structure.

* **`walk_surface=True` on `_add` is for a mesh walkable in its entirety.** A
  `MeshGroup` that declares its decks with `add_walk` must not set it: the flag
  renames the whole placement to `Walk_...` and the exporter names every child
  after its container, so a temple flagged that way makes its own roof a walk
  surface and the grounding ray snaps actors onto it.
"""
from __future__ import annotations

import math

import numpy as np

from amberwood import mesh as M
from amberwood import noise as N
from amberwood import stonework as SW
from amberwood import terrain as TER

import ssaratharch as A
import ssarathikit as SK
import region as REG


def _heading(dx: float, dz: float) -> float:
    """Rotation about Y that points a mesh's +X axis along (dx, dz).

    `M.rotation_y(theta)` maps +X to (cos theta, 0, -sin theta), so the heading
    is atan2(-dz, dx). Getting this sign wrong mirrors every placement on the
    map and is close to invisible until something reads backwards.
    """
    return math.atan2(-dz, dx)


def _add(build, node: str, mesh_name: str, mesh, position, rotation: float = 0.0,
         scale: float = 1.0, kind: str = "prop", collides: bool = False,
         walk_surface: bool = False, landmark: str | None = None):
    """Register a mesh once and place an instance of it."""
    if mesh_name not in build.meshes:
        build.meshes[mesh_name] = mesh
    return build.place(REG.Placement(
        node=node, mesh=mesh_name,
        position=(float(position[0]), float(position[1]), float(position[2])),
        rotation_y=rotation, scale=scale, collides=collides,
        walk_surface=walk_surface, kind=kind, landmark=landmark))


def _ground(build, x: float, z: float) -> float:
    return float(build.terrain.height_at(x, z))


def _walk_along(points: np.ndarray, spacing: float):
    """Yield (x, z, dx, dz, distance) at intervals along a polyline."""
    lengths = np.concatenate([[0.0], np.cumsum(
        np.linalg.norm(np.diff(points, axis=0), axis=1))])
    total = float(lengths[-1])
    if total < spacing:
        return
    count = max(int(total / spacing), 1)
    for i in range(count + 1):
        s = min(i * (total / count), total)
        index = int(np.searchsorted(lengths, s, side="right") - 1)
        index = min(max(index, 0), points.shape[0] - 2)
        span = max(float(lengths[index + 1] - lengths[index]), 1e-9)
        local = (s - float(lengths[index])) / span
        p = points[index] + (points[index + 1] - points[index]) * local
        d = points[index + 1] - points[index]
        yield float(p[0]), float(p[1]), float(d[0]), float(d[1]), s


def _near_crossing(x: float, z: float, spans, pad: float = 6.0) -> bool:
    """True inside a bridge's recut, where the ground is channel floor."""
    for span in spans:
        cx, cz = span["centre"]
        if math.hypot(x - cx, z - cz) < span["half_span"] + pad:
            return True
    return False


# ------------------------------------------------------------------ water
def build_water(build, lod: str | None = None) -> None:
    """The flooded basin's surface.

    One body of water clipped to wherever the terrain is actually below the
    waterline, which in this region is roughly half the map. Unlike Crownwater's
    lagoon it is *not* cut far outside the authored terrain: Ssarathi is a
    closed valley whose rim rises out of the water on every side, so water
    running past that rim to a horizon would be visible from the temple summit
    as a flood outside the mountains.
    """
    t=build.terrain
    # Continuous water is hidden by the actual banks; coarse whole-cell water
    # clipping exposed black grid steps in the baseline gameplay captures.
    # Fresh receiving bays meet the silted interior at the northern inlet and
    # eastern embankment. All rectangles form one non-overlapping water plane;
    # the real banks occlude it, never coarse water-cell cut-outs.
    for name,x0,z0,x1,z1,material in (
        ('Water_Basin',t.x0,-214,216,t.z0+t.size_z,SK.BASIN_WATER),
        ('Water_NorthInlet',t.x0,t.z0,t.x0+t.size_x,-214,'water_lake'),
        ('Water_EastInlet',216,-214,t.x0+t.size_x,t.z0+t.size_z,'water_lake')):
        mesh=M.quad([(x0,0,z0),(x0,0,z1),(x1,0,z1),(x1,0,z0)],material=material)
        mesh.uvs=mesh.positions[:,[0,2]]*.045
        build.water_meshes[name]=mesh



# ------------------------------------------------------------- causeways
def populate_causeways(build, seed: int = 0) -> None:
    """Balustrades, serpent columns and obelisks along the streets.

    The causeway *surface* is terrain; what this pass adds is its edge. A stone
    embankment with nothing on its edge reads as a ramp, and the aerial's
    causeways are unmistakably kerbed and posted.
    """
    t = build.terrain
    spans = REG.bridge_spans()
    rng = N.Rng(seed + 101)

    routes = [("great_causeway", REG.GREAT_CAUSEWAY, REG.CAUSEWAY_WIDTH, 26.0)]
    routes += [(n, p, REG.LATERAL_WIDTH, 20.0) for n, p in REG.LATERALS.items()]
    routes += [(n, p, REG.SPUR_WIDTH, 16.0) for n, p in REG.SPURS.items()]

    for name, points, half_width, section in routes:
        for x, z, dx, dz, distance in _walk_along(points, section):
            if _near_crossing(x, z, spans):
                continue
            y = _ground(build, x, z)
            if y < REG.WATER_LEVEL + 0.4:
                continue        # the embankment is drowned here; no kerb
            heading = _heading(dx, dz)
            klass = int(round(section))
            key = f"Balustrade_{klass}"
            for sign in (-1.0, 1.0):
                # offset perpendicular to the street
                length = math.hypot(dx, dz) or 1.0
                px = x + (-dz / length) * half_width * sign
                pz = z + (dx / length) * half_width * sign
                _add(build, f"Kerb_{name}_{int(distance)}_{int(sign)}", key,
                     A.causeway_balustrade(section, seed=seed + klass),
                     (px, _ground(build, px, pz), pz), heading, kind="structure")

    # Serpent columns down the great axis, in pairs, at wide intervals. These
    # are the aerial's S-forms flanking the central causeway and they are what
    # makes the axis read as ceremonial rather than as a road.
    pair = 0
    for x, z, dx, dz, distance in _walk_along(REG.GREAT_CAUSEWAY, 46.0):
        if _near_crossing(x, z, spans, pad=12.0):
            continue
        y = _ground(build, x, z)
        if y < REG.WATER_LEVEL + 0.4:
            continue
        length = math.hypot(dx, dz) or 1.0
        for sign in (-1.0, 1.0):
            px = x + (-dz / length) * (REG.CAUSEWAY_WIDTH - 1.6) * sign
            pz = z + (dx / length) * (REG.CAUSEWAY_WIDTH - 1.6) * sign
            key = f"SerpentColumn_{pair % 4}"
            _add(build, f"SerpentColumn_{pair}_{int(sign)}", key,
                 A.serpent_column(6.4, seed=seed + pair % 4),
                 (px, _ground(build, px, pz), pz),
                 float(rng.uniform(0.0, math.tau)), kind="structure",
                 collides=True)
        pair += 1

    # Obelisks scattered along the lateral streets and out on the platforms.
    placed = 0
    for name, points in REG.LATERALS.items():
        for x, z, dx, dz, distance in _walk_along(points, 62.0):
            if _near_crossing(x, z, spans, pad=10.0):
                continue
            length = math.hypot(dx, dz) or 1.0
            px = x + (-dz / length) * (REG.LATERAL_WIDTH + 2.4)
            pz = z + (dx / length) * (REG.LATERAL_WIDTH + 2.4)
            y = _ground(build, px, pz)
            if y < REG.WATER_LEVEL + 0.5:
                continue
            key = f"Obelisk_{placed % 5}"
            _add(build, f"Obelisk_{name}_{int(distance)}", key,
                 A.obelisk(7.0 + (placed % 5) * 0.9, seed=seed + placed % 5),
                 (px, y, pz), float(rng.uniform(0.0, math.tau)),
                 kind="structure", collides=True)
            placed += 1


def populate_bridges(build, seed: int = 0) -> None:
    """The channel spans - the only walkable geometry that is not terrain.

    One mesh per (span, width) class, instanced. Each deck sits at the street's
    embankment level so a player walks straight on to it, and the arch hangs
    below into the channel the terrain pass re-cut.
    """
    import layout as PLAN
    PLAN.dress_crossings(build,seed)


# ---------------------------------------------------------------- temple
def populate_temple(build, seed: int = 0) -> None:
    """The ziggurat, its vault portal and the falls behind it - panels 2 and 3."""
    t = build.terrain
    tx, tz = REG.ANCHORS["temple"]
    ty = float(t.height_at(tx, tz))

    temple = A.ziggurat_temple(base=72.0, tiers=5, tier_height=7.0, seed=seed + 7,include_roof=False)
    _add(build, "Temple_Ssarathi", "ZigguratTemple", temple, (tx, ty, tz),
         0.0, kind="landmark", collides=True, landmark="great-temple")
    _add(build,"Structure_TempleSummitRoof","TempleSummitRoof",
         A.ziggurat_summit_roof(seed=seed+7),(tx,ty,tz),kind="structure")

    vx, vz = REG.ANCHORS["vault_door"]
    portal = A.vault_portal(width=11.0, height=9.5, seed=seed + 11)
    _add(build, "Temple_VaultPortal", "VaultPortal", portal,
         (vx, float(t.height_at(vx, vz)), vz), 0.0,
         kind="landmark", collides=True, landmark="sun-vault")

    # the terrace at the foot of the stair, with a guardian pair
    fx, fz = REG.ANCHORS["temple_terrace"]
    for sign in (-1.0, 1.0):
        px = fx + sign * 19.0
        # Rotation 0, not pi. `stone_face` carves its features on the +Z
        # face, and +Z is south; turning it through pi points the carving north
        # and leaves a plain box facing everyone who arrives up the causeway.
        _add(build, f"TempleGuardian_{int(sign)}", "TempleGuardian",
             A.stone_face(2.8, seed=seed + 13),
             (px, float(t.height_at(px, fz)), fz), 0.0,
             kind="structure", collides=True)

    # the falls off the north wall, behind and either side of the temple
    for name, anchor, width, drop in (
            ("north", REG.ANCHORS["north_falls"], 16.0, 26.0),
            ("east", REG.ANCHORS["east_falls"], 11.0, 20.0)):
        ax, az = anchor
        # the lip is up on the valley wall, north of the pool the terrain cut
        lip_z = az - 46.0
        lip_y = max(float(t.height_at(ax, lip_z)), REG.WATER_LEVEL + drop)
        _add(build, f"Waterfall_{name}", f"Waterfall_{name}",
             A.waterfall_sheet(width, lip_y - REG.WATER_LEVEL, seed=seed + 17),
             (ax, lip_y, lip_z), 0.0, kind="landmark",
             landmark=f"{name}-falls")


# ----------------------------------------------------------- pool courts
def populate_courts(build, seed: int = 0) -> None:
    """Panels 5 and 6: the two round colonnaded pool courts."""
    t = build.terrain
    for i, (name, court) in enumerate(REG.COURTS.items()):
        cx, cz = REG.ANCHORS[name]
        rim = float(t.height_at(cx + court["radius"] * 0.86, cz))
        colonnade = A.pool_colonnade(court["radius"] * 0.88,
                                     count=10 if i == 0 else 16,
                                     height=6.2 if i == 0 else 8.2,
                                     seed=seed + 23 + i)
        _add(build, f"Colonnade_{name}", f"Colonnade_{name}", colonnade,
             (cx, rim, cz), 0.0, kind="landmark", collides=True)

        # a stela or a shrine on the court's north side, as the panels have
        sx, sz = cx, cz - court["radius"] * 0.72
        # The court's landmark rides the rim shrine rather than the
        # colonnade. The colonnade is centred on the pool, so a landmark
        # recorded at its origin sits 3.3 m above the floor beneath it and
        # trips LANDMARK_FLOATING; the shrine stands on the paved rim, which
        # is also where a player would actually walk to.
        _add(build, f"CourtShrine_{name}", "CourtShrine",
             A.shrine(4.2, seed=seed + 29 + i),
             (sx, float(t.height_at(sx, sz)), sz), 0.0,
             kind="landmark", collides=True,
             landmark=name.replace("_", "-"))

        # lilies over the pool, which is the panels' whole subject
        rng = N.Rng(seed + 300 + i)
        for k in range(9):
            angle = float(rng.uniform(0.0, math.tau))
            r = court["pool_radius"] * math.sqrt(float(rng.uniform(0.0, 0.92)))
            px, pz = cx + math.cos(angle) * r, cz + math.sin(angle) * r
            _add(build, f"Lilies_{name}_{k}", f"LilyPatch_{k % 4}",
                 A.lily_patch(3.4, 46, seed=seed + 40 + k % 4,
                              level=court["pool_level"]),
                 (px, 0.0, pz), float(rng.uniform(0.0, math.tau)),
                 kind="foliage")


# -------------------------------------------------------------- landmarks
def populate_landmarks(build, seed: int = 0) -> None:
    """The stela, the root arch, the water gate and the outlying shrines."""
    t = build.terrain

    sx, sz = REG.ANCHORS["sun_stela"]
    # Rotation 0. `sun_stela` puts its disc on the slab's +Z face and +Z is
    # south, which is where the approach spur comes from; turned through pi the
    # panel-7 subject faces the empty north rim and the capture is of a blank
    # slab. Same defect the guardians had.
    _add(build, "SunStela", "SunStela", A.sun_stela(15.0, seed=seed + 31),
         (sx, float(t.height_at(sx, sz)), sz), 0.0,
         kind="landmark", collides=True, landmark="sun-stela")

    rx, rz = REG.ANCHORS["root_arch"]
    _add(build, "RootArch", "RootArch",
         A.ruin_arch_rooted(span=13.0, height=13.5, seed=seed + 37),
         (rx, float(t.height_at(rx, rz)), rz), math.radians(24.0),
         kind="landmark", collides=True, landmark="root-arch")

    gx, gz = REG.ANCHORS["south_gate"]
    span=REG.CAUSEWAY_WIDTH*2.0
    gate=_add(build,"WaterGate","WaterGate",
         A.water_gate(span=span,height=14.0,seed=seed+41),
         (gx,float(t.height_at(gx,gz)),gz),0.0,
         kind="landmark",collides=True,landmark="south-water-gate")
    # The gateway opens along the ceremonial axis. Each pylon blocks its
    # own base; the overhead lintel does not turn the opening into a wall.
    pylon=span*0.34;half=pylon*0.78
    gate.extras={"solidRects":[[sign*(span+pylon)/2-half,-half,
                                sign*(span+pylon)/2+half,half]
                               for sign in (-1,1)]}

    sgx, sgz = REG.ANCHORS["serpent_gate"]
    for sign in (-1.0, 1.0):
        px = sgx + sign * (REG.CAUSEWAY_WIDTH + 2.2)
        _add(build, f"SerpentGateColumn_{int(sign)}", "SerpentGateColumn",
             A.serpent_column(9.0, seed=seed + 43),
             (px, float(t.height_at(px, sgz)), sgz), 0.0,
             kind="landmark", collides=True,
             landmark="serpent-gate" if sign < 0 else None)

    for name in ("west_shrine", "east_shrine", "south_shrine"):
        x, z = REG.ANCHORS[name]
        _add(build, f"Shrine_{name}", "RoadShrine",
             A.shrine(4.6, seed=seed + 47),
             (x, float(t.height_at(x, z)), z),
             _heading(REG.ANCHORS["temple"][0] - x, REG.ANCHORS["temple"][1] - z),
             kind="landmark", collides=True,
             landmark=name.replace("_", "-"))


# ------------------------------------------------------- working quarters
def populate_quarters(build, seed: int = 0) -> None:
    """The market, the docks and the drowned quarter."""
    t = build.terrain
    rng = N.Rng(seed + 211)

    mx,mz=REG.ANCHORS["market"]
    # Face two rows into a clear trading aisle, with the shrine at its head.
    for i in range(10):
        x=mx+(i%5-2)*7.0;z=mz+(-1 if i<5 else 1)*8.0
        _add(build,f"MarketStall_{i}",f"MarketStall_{i%4}",
             A.market_stall(3.6,seed=seed+60+i%4),(x,float(t.height_at(x,z)),z),
             0 if i<5 else math.pi,kind="structure",collides=True)
    _add(build,"MarketShrine","MarketShrine",A.shrine(3.8,seed=seed+63),
         (mx+18,float(t.height_at(mx+18,mz)),mz),0,kind="structure",collides=True)

    # The drowned quarter: rubble, half-standing walls and drowned columns
    # standing in shallow water. This is the part of the aerial that says the
    # city was flooded rather than built on stilts.
    qx, qz = REG.ANCHORS["drowned_quarter"]
    for i in range(26):
        angle = float(rng.uniform(0.0, math.tau))
        r = float(rng.uniform(3.0, 42.0))
        px, pz = qx + math.cos(angle) * r, qz + math.sin(angle) * r
        y = float(t.height_at(px, pz))
        if i % 3 == 0:
            _add(build, f"DrownedColumn_{i}", f"DrownedColumn_{i % 3}",
                 SW.column(float(rng.uniform(2.4, 5.2)), radius=0.32,
                           flutes=9, material=SK.JADE_ASHLAR),
                 (px, y, pz), float(rng.uniform(0.0, math.tau)),
                 kind="structure", collides=True)
        else:
            _add(build, f"DrownedRubble_{i}", f"RubbleHeap_{i % 5}",
                 A.rubble_heap(2.8, seed=seed + 80 + i % 5), (px, y, pz),
                 float(rng.uniform(0.0, math.tau)), kind="prop")


# ------------------------------------------------------------- quarters
def populate_ruin_blocks(build, seed: int = 0) -> None:
    """Ruined buildings on the blocks the massing pass raised.

    The single densest pass in the region and the one that decides whether the
    basin reads as the painting or as a lake with paving in it. Blocks are
    quantised into a small number of size classes so a few hundred placements
    share a dozen unique meshes.
    """
    t = build.terrain
    rng = N.Rng(seed + 811)
    made: set[str] = set()
    placed = 0
    for block in REG.RUIN_BLOCKS:
        # Leave a share of blocks as bare platform. Building on every one of
        # them makes a solid slab of masonry with no courts or squares in it,
        # and the aerial plainly has open paved ground between its blocks.
        if float(rng.uniform(0.0, 1.0)) < 0.18:
            continue
        cx, cz = block["centre"]
        # quantise to 3 m classes so the mesh table stays small
        hx = max(round(block["half_x"] / 3.0) * 3.0, 4.5)
        hz = max(round(block["half_z"] / 3.0) * 3.0, 4.5)
        variant = placed % 3
        storeys = 2 if (block["paved"] and float(rng.uniform(0, 1)) < 0.28) else 1
        key = f"RuinBuilding_{int(hx)}_{int(hz)}_{storeys}_{variant}"
        if key not in made:
            build.meshes[key] = A.ruin_building(hx * 0.86, hz * 0.86,
                                                seed=seed + 900 + len(made),
                                                storeys=storeys)
            made.add(key)
        _add(build, f"Ruin_{placed}", key, build.meshes[key],
             (cx, block["level"], cz), block["rotation"], kind="structure",
             collides=True)
        # A tower on some blocks. The concept's skyline is towers; a field of
        # one-storey blocks reads flat from any camera above head height.
        if float(rng.uniform(0.0, 1.0)) < 0.26 and min(hx, hz) >= 6.0:
            storeys = int(rng.uniform(3, 7))
            variant = placed % 4
            half_t = min(hx, hz) * 0.52
            tkey = f"RuinTower_{int(half_t)}_{storeys}_{variant}"
            if tkey not in build.meshes:
                build.meshes[tkey] = A.ruin_tower(half_t, storeys,
                                                  seed=seed + 950 + variant)
            _add(build, f"RuinTower_{placed}", tkey, build.meshes[tkey],
                 (cx, block["level"], cz), block["rotation"],
                 kind="structure", collides=True)

        # A tree through the masonry on some of them. This is the concept's
        # single most repeated motif after the water itself - the jungle is
        # taking the city back - and without it the blocks read as a tidy
        # archaeological site rather than as a ruin.
        if float(rng.uniform(0.0, 1.0)) < 0.55:
            angle = float(rng.uniform(0.0, math.tau))
            r = max(hx, hz) * float(rng.uniform(0.25, 0.80))
            tx = cx + math.cos(angle) * r
            tz = cz + math.sin(angle) * r
            species = ("ssarathi_strangler" if float(rng.uniform(0, 1)) < 0.62
                       else "ssarathi_kapok")
            variant = placed % 3
            tier = "near" if placed % 3 == 0 else "mid"
            tkey = f"RuinTree_{species}_{tier}_{variant}"
            if tkey not in build.meshes:
                build.meshes[tkey] = A.jungle_tree(
                    float(rng.uniform(11.0, 17.0)), seed=seed + 700 + variant,
                    tier=tier, species=species)
            _add(build, f"RuinTree_{placed}", tkey, build.meshes[tkey],
                 (tx, block["level"], tz), float(rng.uniform(0.0, math.tau)),
                 scale=float(rng.uniform(0.85, 1.25)), kind="tree",
                 collides=True)
        placed += 1


# ------------------------------------------------------------ vegetation
def populate_vegetation(build, seed: int = 0, lod: str | None = None) -> None:
    """The jungle: canopy on the rim, palms at the waterline, undergrowth.

    Density is per-area, not per-region, and the whole pass instances a small
    number of unique trees. Detail tier is chosen by distance from the axis,
    which is where the player spends their time: near-tier trees line the
    streets, far-tier trees fill the rim.
    """
    t = build.terrain
    rng = N.Rng(seed + 401)
    spans = REG.bridge_spans()

    tiers = ("far",) if lod == "far" else ("near", "mid", "far")
    unique: dict[str, str] = {}

    def tree_key(species: str, tier: str, variant: int) -> str:
        key = f"Tree_{species}_{tier}_{variant}"
        if key not in unique:
            height = {"near": 21.0, "mid": 18.0, "far": 15.0}[tier] \
                * (0.82 + 0.30 * (variant / 3.0))
            build.meshes[key] = A.jungle_tree(height, seed=seed + variant * 7,
                                              tier=tier, species=species)
            unique[key] = key
        return key

    def palm_key(tier: str, variant: int) -> str:
        key = f"Palm_{tier}_{variant}"
        if key not in unique:
            build.meshes[key] = A.palm(8.0 + variant * 1.6,
                                       seed=seed + 200 + variant, tier=tier)
            unique[key] = key
        return key

    # Poisson-ish scatter on a jittered grid over the whole terrain.
    # 8.5 m rather than 11: the rim is the region's whole horizon and at the
    # wider spacing it read as scattered trees on bare ground rather than as
    # closed jungle. Most instances are far-tier, which is what keeps the
    # triangle count from tracking the coverage.
    spacing = 9.3 if lod is None else 15.0
    xs = np.arange(t.x0 + 6.0, t.x0 + t.size_x - 6.0, spacing)
    zs = np.arange(t.z0 + 6.0, t.z0 + t.size_z - 6.0, spacing)
    axis_x, axis_z = REG.ANCHORS["causeway_mid"]
    planted = 0
    for gx in xs:
        for gz in zs:
            x = float(gx + rng.uniform(-spacing * 0.42, spacing * 0.42))
            z = float(gz + rng.uniform(-spacing * 0.42, spacing * 0.42))
            y = float(t.height_at(x, z))
            if y < REG.WATER_LEVEL + 0.15:
                continue                      # nothing grows in the basin
            if bool(t.blocked_at(x, z)):
                continue                      # streets, plazas and precincts
            surface = int(t.surface_at(x, z))
            if surface in (REG.JADE_PAVING, REG.MOSS_STONE):
                continue
            # Rock is the valley's cliff faces. A quarter of them still carry
            # something: in the concept even the wet rock behind the falls has
            # growth on it, and skipping rock entirely left a bald horizon.
            if surface == TER.ROCK and float(rng.uniform(0, 1)) > 0.42:
                continue
            if _near_crossing(x, z, spans, pad=4.0):
                continue

            # Detail tier by distance from the ceremonial axis, which is where
            # a player actually spends their time. Distance is radial, not just
            # in x: the axis runs north-south, so an |x| test alone gave the far
            # north and south ends of the map near-tier trees.
            distance = math.hypot(x - axis_x, z - axis_z)
            if distance < 110.0:
                tier = tiers[0]
            elif distance < 240.0:
                tier = tiers[min(1, len(tiers) - 1)]
            else:
                tier = tiers[-1]

            # palms hug the waterline, canopy trees stand back from it
            roll = float(rng.uniform(0.0, 1.0))
            if y < REG.WATER_LEVEL + 3.0 and roll < 0.55:
                key = palm_key(tier if tier != "mid" else "near",
                               int(rng.uniform(0, 3)))
                kind = "tree"
            else:
                species = ("ssarathi_kapok" if roll < 0.72
                           else "ssarathi_strangler")
                key = tree_key(species, tier, int(rng.uniform(0, 4)))
                kind = "tree"
            _add(build, f"Tree_{planted}", key, build.meshes[key],
                 (x, float(t.mesh_height_at(x, z)), z),
                 float(rng.uniform(0.0, math.tau)),
                 scale=float(rng.uniform(0.86, 1.18)), kind=kind, collides=True)
            planted += 1

    if lod == "far":
        return

    # Undergrowth cards on the dry ground, and vine curtains on the rim rock.
    under = M.merge([
        M.quad([(-1.5, 0.0, 0.0), (1.5, 0.0, 0.0), (1.5, 2.0, 0.0), (-1.5, 2.0, 0.0)],
               material=SK.UNDERGROWTH),
        M.quad([(0.0, 0.0, -1.5), (0.0, 0.0, 1.5), (0.0, 2.0, 1.5), (0.0, 2.0, -1.5)],
               material=SK.UNDERGROWTH)], SK.UNDERGROWTH)
    under.sanitise_normals()
    clumps = 0
    for gx in np.arange(t.x0 + 4.0, t.x0 + t.size_x - 4.0, 15.0):
        for gz in np.arange(t.z0 + 4.0, t.z0 + t.size_z - 4.0, 15.0):
            x = float(gx + rng.uniform(-6.0, 6.0))
            z = float(gz + rng.uniform(-6.0, 6.0))
            y = float(t.height_at(x, z))
            if y < REG.WATER_LEVEL + 0.25 or bool(t.blocked_at(x, z)):
                continue
            if int(t.surface_at(x, z)) in (REG.JADE_PAVING, REG.MOSS_STONE):
                continue
            if float(rng.uniform(0, 1)) > 0.45:
                continue
            _add(build, f"Undergrowth_{clumps}", "Undergrowth", under,
                 (x, y, z), float(rng.uniform(0.0, math.tau)),
                 scale=float(rng.uniform(0.7, 1.5)), kind="foliage")
            clumps += 1


# ---------------------------------------------------------------- dressing
def populate_props(build, seed: int = 0) -> None:
    """Lilies over the open basin, vines on the masonry, rubble in the ruins."""
    t = build.terrain
    rng = N.Rng(seed + 503)

    # Lily rafts. The single most identifying feature of the aerial after the
    # temple: without them the basin reads as an empty lake. Placed only where
    # the water is genuinely shallow, which is where they grow.
    rafts = 0
    for gx in np.arange(t.x0 + 20.0, t.x0 + t.size_x - 20.0, 26.0):
        for gz in np.arange(t.z0 + 20.0, t.z0 + t.size_z - 20.0, 26.0):
            x = float(gx + rng.uniform(-9.0, 9.0))
            z = float(gz + rng.uniform(-9.0, 9.0))
            y = float(t.height_at(x, z))
            depth = REG.WATER_LEVEL - y
            if depth < 0.25 or depth > 2.2:
                continue
            if float(rng.uniform(0, 1)) > 0.62:
                continue
            _add(build, f"LilyRaft_{rafts}", f"LilyRaft_{rafts % 5}",
                 A.lily_patch(float(rng.uniform(4.0, 8.0)), 60,
                              seed=seed + 90 + rafts % 5,
                              level=REG.WATER_LEVEL),
                 (x, 0.0, z), float(rng.uniform(0.0, math.tau)), kind="foliage")
            rafts += 1

    # Vine curtains on the rim rock and the drowned quarter's standing walls.
    vines = 0
    for gx in np.arange(t.x0 + 10.0, t.x0 + t.size_x - 10.0, 34.0):
        for gz in np.arange(t.z0 + 10.0, t.z0 + t.size_z - 10.0, 34.0):
            x = float(gx + rng.uniform(-12.0, 12.0))
            z = float(gz + rng.uniform(-12.0, 12.0))
            y = float(t.height_at(x, z))
            if int(t.surface_at(x, z)) != TER.ROCK or y < REG.WATER_LEVEL + 2.0:
                continue
            if float(rng.uniform(0, 1)) > 0.35:
                continue
            _add(build, f"VineCurtain_{vines}", f"VineCurtain_{vines % 4}",
                 A.vine_curtain(4.0, 5.5, seed=seed + 110 + vines % 4),
                 (x, y + float(rng.uniform(2.0, 5.0)), z),
                 float(rng.uniform(0.0, math.tau)), kind="foliage")
            vines += 1

    # Rubble along the streets, and fallen fragments in the jungle.
    heaps = 0
    for name, points in list(REG.LATERALS.items()) + list(REG.SPURS.items()):
        for x, z, dx, dz, distance in _walk_along(points, 38.0):
            length = math.hypot(dx, dz) or 1.0
            side = 1.0 if heaps % 2 else -1.0
            px = x + (-dz / length) * (REG.LATERAL_WIDTH + 3.5) * side
            pz = z + (dx / length) * (REG.LATERAL_WIDTH + 3.5) * side
            y = float(t.height_at(px, pz))
            if y < REG.WATER_LEVEL - 0.8:
                continue
            if float(rng.uniform(0, 1)) > 0.42:
                continue
            _add(build, f"Rubble_{name}_{int(distance)}", f"RubbleHeap_{heaps % 5}",
                 A.rubble_heap(2.4, seed=seed + 80 + heaps % 5), (px, y, pz),
                 float(rng.uniform(0.0, math.tau)), kind="prop")
            heaps += 1

    # Lamps along the great axis. The aerial has lit points down the causeway.
    lamps = 0
    for x, z, dx, dz, distance in _walk_along(REG.GREAT_CAUSEWAY, 23.0):
        y = float(t.height_at(x, z))
        if y < REG.WATER_LEVEL + 0.4:
            continue
        length = math.hypot(dx, dz) or 1.0
        side = 1.0 if lamps % 2 else -1.0
        px = x + (-dz / length) * (REG.CAUSEWAY_WIDTH - 0.9) * side
        pz = z + (dx / length) * (REG.CAUSEWAY_WIDTH - 0.9) * side
        _add(build, f"AxisLamp_{lamps}", "AxisLamp", SW.lamp_post(3.2),
             (px, float(t.height_at(px, pz)), pz), 0.0, kind="prop")
        lamps += 1

    # Panel 10's material board, staged as real objects on the temple terrace:
    # a scale-tiled fragment, a gilt scroll boss and a shell. Not decoration -
    # it is what the panel is a close-up *of*, and it gives the comparison
    # capture something to frame.
    fx, fz = REG.ANCHORS["temple_terrace"]
    fy = float(t.height_at(fx, fz))
    for i, (dx, dz, piece) in enumerate((
            (-7.0, 5.0, A.shell_boss(1.1)),
            (7.0, 5.0, A.sun_disc(1.3, seed=seed + 51)),
            (0.0, 8.0, A.stone_face(1.5, seed=seed + 53)))):
        _add(build, f"TerraceRelic_{i}", f"TerraceRelic_{i}", piece,
             (fx + dx, fy + (0.6 if i == 1 else 0.0), fz + dz),
             0.0, kind="prop", collides=True)


# ------------------------------------------------------------------ doors
# The three interior entrances that are not the Sun Vault need something on the
# surface to be. A portal floating over open paving is not a door, and the
# region's own landmarks do not happen to sit where the insides are.
def populate_interior_doors(build, seed: int = 0) -> None:
    """Well-head, stair-head and broken mouth: the three lesser ways in.

    The Royal Archive is entered through the Sun Vault, which is already built
    and already a landmark, so it needs nothing here.
    """
    t = build.terrain

    import layout as PLAN
    PLAN.dress_cistern(build,seed)

    # The hatchery descent, on the ritual plaza's north rim: a stepped mouth
    # between two serpent columns, so it reads as a way in and not a drain.
    px, pz = REG.ANCHORS["ritual_plaza"]
    court = REG.COURTS["ritual_plaza"]
    hx, hz = px, pz - court["radius"] * 0.80
    hy = float(t.height_at(hx, hz))
    _add(build, "HatcheryDescent", "HatcheryDescent",
         A.stair_mouth(5.2, 3.2, seed=seed + 302), (hx, hy, hz), math.pi,
         kind="landmark", collides=True, landmark="hatchery-descent")
    for sign in (-1.0, 1.0):
        cx2 = hx + sign * 5.0
        _add(build, f"HatcheryColumn_{int(sign)}", "SerpentColumn_0",
             A.serpent_column(6.4, seed=seed + 0),
             (cx2, float(t.height_at(cx2, hz)), hz), 0.0,
             kind="structure", collides=True)

    # The undercroft mouth, at the root arch: a collapsed opening rather than a
    # built door, because nothing down there was built by the same people.
    rx, rz = REG.ANCHORS["root_arch"]
    ux, uz = rx - 14.0, rz + 12.0
    uy = float(t.height_at(ux, uz))
    _add(build, "UndercroftMouth", "UndercroftMouth",
         A.broken_mouth(4.6, 2.8, seed=seed + 303), (ux, uy, uz),
         math.radians(24.0), kind="landmark", collides=True,
         landmark="undercroft-mouth")


# ---------------------------------------------------------------- metadata
def populate_metadata(build, seed: int = 0) -> None:
    """Interactives and harvestables - editor metadata, server authoritative."""
    t = build.terrain
    rng = N.Rng(seed + 313)

    # The optional fifth field is a height above the terrain: an interactive
    # that lives on top of a landmark rather than at its foot. Without it the
    # summit altar records 22 m under the temple it is supposed to be on.
    for entry in (
            ("ssarathi-sun-vault-door", "Sun Vault Door", "vault_door", "door"),
            ("ssarathi-temple-altar", "Temple Summit Altar", "temple", "altar",
             34.0),
            ("ssarathi-sun-stela", "Sun Stela", "sun_stela", "glyph"),
            ("ssarathi-water-gate", "South Water Gate", "south_gate", "gate"),
            ("ssarathi-lily-court-basin", "Lily Court Basin", "lily_court",
             "fountain"),
            ("ssarathi-ritual-pool", "Ritual Pool", "ritual_plaza", "fountain"),
            ("ssarathi-root-arch", "Root-grown Arch", "root_arch", "glyph"),
            ("ssarathi-market-well", "Market Well", "market", "well")):
        interactive_id, name, anchor, kind = entry[:4]
        lift = entry[4] if len(entry) > 4 else 0.0
        x, z = REG.ANCHORS[anchor]
        y = float(t.height_at(x, z)) + lift
        build.interactives.append({
            "id": interactive_id, "name": name, "type": kind,
            "position": [round(x, 2), round(y + 0.4, 2), round(z, 2)],
            "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                           int(round(REG.SERVER_ORIGIN[1] - z))],
            "authority": "server"})

    anchors = ("drowned_quarter", "lily_court", "ritual_plaza", "market",
               "east_dock", "west_dock", "root_arch", "west_shrine",
               "east_shrine", "north_terrace")
    for k in range(34):
        anchor = REG.ANCHORS[anchors[k % len(anchors)]]
        angle = float(rng.uniform(0, math.tau))
        r = float(rng.uniform(6.0, 34.0))
        x = anchor[0] + math.cos(angle) * r
        z = anchor[1] + math.sin(angle) * r
        y = float(t.height_at(x, z))
        # Harvestables in this region are as often *in* the water as out of it -
        # lotus root and reed are shallow-water crops - so the filter is on
        # depth, not on being dry.
        if y > REG.WATER_LEVEL + 6.0 or y < REG.WATER_LEVEL - 2.4:
            continue
        build.harvestables.append({
            "id": f"ssarathi-harvest-{k}",
            "resource": ("lotus-root" if k % 4 == 0 else
                         "reed" if k % 4 == 1 else
                         "jade-shard" if k % 4 == 2 else "orchid"),
            "position": [round(x, 2), round(y, 2), round(z, 2)],
            "serverTile": [int(round(x + REG.SERVER_ORIGIN[0])),
                           int(round(REG.SERVER_ORIGIN[1] - z))],
            "authority": "server"})
