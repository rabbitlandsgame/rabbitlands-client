"""publish_client.py: publish a continent-v2 territory for the GAME CLIENT as a chunk-streamed package.

  python -B eloria-assets/maps/continent-v2/_continent_v2/publish_client.py --region <catalog-id> \
         --snapshot <bake>/continent-authoring.json --out eloria-assets/maps/continent-v2/<region>/client \
         --shared eloria-assets/maps/continent-v2/_continent_v2/shared-assets \
         [--collision <export work dir>/<region>.collision.json] \
         [--work <scratch dir>] [--chunks 05_11,06_11] [--budget-mib 256] [--master] [--checkout <worktree>]

  python -B eloria-assets/maps/continent-v2/_continent_v2/publish_client.py --environment [--check] \
         --region <catalog-id> --out eloria-assets/maps/continent-v2/<region>/client [--checkout <worktree>]

--environment publishes the stub's environment block (sky, sun, ambient, fog, saturation and their variants) alone:
the territory manifest and every chunk manifest take <region>/world.json's `environment`, and nothing else in the
package is read or written. The block is copied from the stub verbatim by a full publish too, and no digest covers
it (chunks_digest hashes the chunk GLBs, the server pins the walk grids), so a sky change needs no re-bake, no new
chunks and no new map picture. A package not written by this tool is refused. --check writes nothing and exits 1
when any manifest's block differs from the stub's (tests/test_publish_client_environment.py checks every territory).

--region names an active catalog territory. The bake comes from the region bake
(src/dev/map_authoring_region/region_bake_cli.gd, or the editor-pass check of that territory) of the committed scene;
re-bake after every scene commit. The bootstrap owns <region>/world.json (the editor stub) and
_continent_v2/README.md, so this package lives in <region>/client/ and its images in _continent_v2/shared-assets
(never nymara-regions/_continent/shared-assets: the twelve-territory export prunes that pool). A territory's sea is
cut to its ownership polygon: a rectangle's cell by cell as before, any other polygon by clipping each cell's square
to it and triangulating the piece (shapely's constrained Delaunay).

What it writes (the shape build_continent.export_geometry gives the twelve-territory regions, so the client's loader,
streamer and look pass treat each isle exactly as they treat Amberwood):
  <out>/world.json                      continent-chunks-v1 territory manifest, streamingChunks, coordinateTransform
  <out>/chunks/<cx>_<cz>/world.json     one manifest per 96 m cell (territory-local lattice through -1023 m)
  <out>/chunks/<cx>_<cz>/world.glb      self-contained chunk GLB; images go to <shared> by sha256 (externalResources)
  <out>/world.glb (+ world.part<n>.<sha>.bin)   only with --master (digest only for the client; split at 90 MiB)
  <out>/publication.json                inputs, digests, sizes, timings
The territory manifest's harvestables, harvestGroupings and harvestablesSchema are every harvest marker's presentation
(variant, yaw, footprint, grouping, promoted-scenery binding) and the groupings the maps mark: harvest_presentation.py
holds the marker and package schema and its checks; chunk manifests carry none of the three.
The package's map picture (<out>/minimap.webp and the territory manifest's minimap block) is render_minimap.py's,
drawn from the chunks this tool writes: a republish keeps the block only while the chunks are the ones it was drawn
from (chunks_digest), and otherwise drops it, so build_continent_map.py refuses the served territory until the
picture is drawn again.
The served walk grid is export_collision.py's: one run over the island group writes <out>/collision.bin and
<out>/served-grid.escg.gz and a sidecar, and --collision stamps that sidecar as the territory manifest's `collision`
block (the binaries, gridAlignment tile-centres-v1, the height encoding and `servedGrid`, which the server's sync
vendors). The sidecar is refused unless it was exported from this very snapshot, for this region, by a whole-group
run, and its two binaries are the ones in <out>. Chunk manifests keep only the block's frame, format and rule
(CHUNK_COLLISION_KEYS), never its binaries, statistics, seam collar or provenance: a chunk folder holds no
collision.bin, package_client.py refuses a world.json that names a file the commit lacks, and a neighbour-only
re-export rewrites the territory manifest alone. Without --collision the package stays a client preview (a placeholder block), and a package folder
that already holds exported binaries is refused, so a republish cannot silently drop its served grid.
Reused, unchanged, from eloria-assets/maps/nymara-regions/_continent (checked against f61b437be):
  authoring.load_snapshot (production=False, _validate_gameplay bypassed: v2 has no portals yet),
  authoring.build_retained_library (12,665 kit placements under their saved matrices),
  terrain_export.authored_overlays (AuthoredGround_<region>Base, AuthoredGround_<region>_<id>, Walk_<region>_<road>),
  terrain_export._mesh_faces, bridge_export._authored_bridge_geometry (Walk_AuthoredBridge_*), scene_io.Exporter.
New here: the one-territory facade, Terrain_<region>_<cx>_<cz> (walk collision for the client), Water_<region>_<cx>_<cz>
(sea quad, lake ellipses, river ribbons, material water_sea), the chunking and the manifests, the territory
manifest's lighting.markers: one point light per placement of a kit model that declares a light (the client binds them
as OmniLight3D, light_marker_binder.gd), and the flat kit inlays and kit decks (WALK_KIT_STEMS: the garden town's
paving, the plaza rosette, the pier trestles' and causeway arches' spans) published as Walk_<region>_<stem> surfaces, so the client stands actors on them, OccluderFade keeps
them solid under the player, the look leaves their colours alone (an opaque deck without vertex colour) and its grass
does not grow through them (game-look review D7: tufts on 19 % of the garden walks' pixels, and three paving pieces
able to fade to glass under the player).

Provenance: the manifests name this tool by its path in the repository, and publication.json records the bake by its
SHA-256 and the committed scene's, not by the scratch path it was read from: re-bake the committed scene with
region_bake_cli.gd and run this again to reproduce the package. --checkout defaults to the repository
that holds this script."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

REGION = None
CHUNK = 96.0
# The 96 m territory-local grid keeps its historical anchor as the phase seed.
# Each publication selects a deterministic whole-metre phase that satisfies the
# instance/triangle limits, then extends that grid to cover the served frame.
# Saved geometry and server coordinates are unaffected.
CHUNK_LATTICE = -1023.0
CHUNK_ORIGIN = [CHUNK_LATTICE, CHUNK_LATTICE]
CELL = 2.0
DEFAULT_CHECKOUT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(DEFAULT_CHECKOUT / "eloria-assets" / "tools"))
import publish_finish as PF  # noqa: E402
TOOL = "eloria-assets/maps/continent-v2/_continent_v2/publish_client.py"
# Flat kit inlays and kit decks published as walk surfaces (see the module notes): their mesh nodes become
# Walk_<region>_<suffix>. The pier trestles' and causeway arches' decks are kit solids, which carry no client
# collision, so the look's grass rays went through them to the ground beneath and grew tufts through the planks (the
# B23 pier's far end, 16-22 % of its pixels, review D7).
WALK_KIT_STEMS = ("kit-sw-garden-paving-", "kit-sw-plaza-rosette", "kit-sw-trestle-pier-span",
                  "kit-sw-causeway-arch-span")
# The editor-pass check that bakes each territory's committed scene (publication.json's recipe).
SHIPPING_BUDGET = 268435456           # ContinentChunkStream.DEFAULT_RESIDENT_BYTES / every published region
# export_collision.py's outputs and sidecar schema (tests/test_publish_client.py keeps them equal).
COLLISION_BIN = "collision.bin"
SERVED_GRID = "served-grid.escg.gz"
SIDECAR_SCHEMA = "eloria-continent-v2-collision-v1"
PREVIEW_COLLISION = {"nodeNames": [], "cellMetres": 0.5, "authoredSurfaceExport": True,
                     "note": "client preview: no served EWCG grid yet (server stage); kit solids carry no client "
                             "collision, as the wrappers that name them are not meshes"}
SERVED_COLLISION_NOTE = ("kit solids carry no client collision (the wrappers that name them are not meshes); the "
                         "served grid blocks them")
# What a chunk manifest keeps of the territory's collision block: the frame, the format and the rule, never the
# files, their digests, the export's statistics, its seam collar or its provenance. Those live in the territory
# manifest only, so a re-export that changes only a neighbour (the collar, groupExport) rewrites one manifest, not
# every chunk's.
CHUNK_COLLISION_KEYS = ("nodeNames", "nodesAreProxies", "format", "formatVersion", "version", "width", "height",
                        "cellMetres", "serverCells", "serverStorageVersion", "serverTileMin", "originMetres",
                        "gridAlignment", "authoredSurfaceExport", "maxTerrainGrade", "maximumWadingDepth",
                        "actorVolume", "note")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# The package's map picture (render_minimap.py), and what it is drawn from.
MINIMAP = "minimap.webp"


def chunks_digest(out, chunks):
    """One SHA-256 over every chunk GLB a territory manifest lists, in its streamingChunks order (each chunk's id,
    then its GLB's own SHA-256): the geometry a map picture of the package was drawn from. render_minimap.py records
    it in the manifest's minimap block, and a republish keeps that block only while it still holds."""
    digest = hashlib.sha256()
    for chunk in chunks:
        manifest = Path(out) / chunk["manifest"]
        glb = manifest.parent / json.loads(manifest.read_text(encoding="utf-8"))["asset"]["glb"]
        digest.update(f"{chunk['id']} {sha(glb)}\n".encode("utf-8"))
    return digest.hexdigest()


def kept_minimap(out, chunks):
    """The map picture block of the package's current territory manifest, when a republish may keep it: the picture
    (render_minimap.py) stays only while it shows these very chunks and is the image it records. Otherwise None, and
    build_continent_map.py refuses the served territory until the picture is drawn again."""
    previous = Path(out) / "world.json"
    picture = (json.loads(previous.read_text(encoding="utf-8")).get("minimap") if previous.is_file() else None) or {}
    if not picture:
        return None
    image = Path(out) / MINIMAP
    if ((picture.get("cartographyRender") or {}).get("chunksSha256") == chunks_digest(out, chunks)
            and image.is_file() and sha(image) == picture.get("imageSha256")):
        return picture
    print(f"the map picture was drawn from other chunks: dropped; run render_minimap.py --region {REGION} --apply")
    return None


def json_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def point_in_polygon(x, z, polygon):
    """The exact union of the territory's ordered ownership components."""
    import ownership
    return ownership.contains(x, z, polygon)


def trim_extensions(exporter):
    """scene_io.Exporter.add copies the whole source document's extensionsUsed/extensionsRequired into every package
    it adds roots from, so one kit model's extension (the landing beacon's KHR_materials_emissive_strength) would be
    declared by, and rewrite, every chunk that holds any kit placement. Each package declares only the extensions
    its own objects use."""
    used = set()

    def walk(item):
        if isinstance(item, dict):
            if isinstance(item.get("extensions"), dict):
                used.update(item["extensions"])
            for value in item.values():
                walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)

    for key, value in exporter.doc.items():
        if key not in ("extensionsUsed", "extensionsRequired"):
            walk(value)
    for field in ("extensionsUsed", "extensionsRequired"):
        kept = sorted(set(exporter.doc.get(field, [])) & used)
        if kept:
            exporter.doc[field] = kept
        else:
            exporter.doc.pop(field, None)


def territory_resources(out, names):
    """The territory manifest's externalResources: every image the named cells' chunk manifests list, by URI relative
    to the territory's own GLB directory (<out>), as build_continent.py writes them for the twelve territories.
    ContinentChunkStream.configure reads the VRAM sidecar index of each directory these name before it corrects a
    single cell's image figures (vram_textures.gd read_indexes_for); an empty map left every v2 image at its RGBA8
    figure even where a sidecar uploads it at a quarter of that. The client never verifies these files for a
    streamed territory (world_loader.gd returns before verify_external_resources)."""
    resources = {}
    for name in names:
        chunk_dir = Path(out) / "chunks" / name
        chunk = json.loads((chunk_dir / "world.json").read_text(encoding="utf-8"))
        glb_dir = (chunk_dir / chunk.get("asset", {}).get("glb", "world.glb")).parent
        for uri, digest in (chunk.get("externalResources") or {}).items():
            rebased = os.path.relpath(os.path.normpath(glb_dir / uri), Path(out)).replace("\\", "/")
            if resources.setdefault(rebased, digest) != digest:
                raise ValueError(f"{rebased}: chunk {name} names sha {digest}, another chunk {resources[rebased]}")
    return dict(sorted(resources.items()))


# What a v2 cell's geometry counts against the stream budget (geometryResidentBytes), as a multiple of its GLB's
# bytes. The village-mem captures measured the mesh memory a v2 cell really holds at 0.45-0.48 x its GLB, so 5 x
# (about ten times the truth) let 4-6 cells stay resident and left 46 framed holes in the wide and zoomed-out views.
# Owner call 2026-10-03: 1.0 x for continent-v2 (trials: 17 holes, 16-22 cells resident, 6-9 s to settle). The twelve
# legacy territories followed on 2026-10-16 (publish_finish.py LEGACY_RESIDENT_FACTOR, measured the same way).
# tests/test_publish_client_geometry.py.
GEOMETRY_RESIDENT_FACTOR = 1.0


def geometry_resident_bytes(glb_bytes):
    """A v2 cell's geometryResidentBytes: GEOMETRY_RESIDENT_FACTOR x its GLB's bytes, rounded up, at least 1."""
    return max(1, math.ceil(GEOMETRY_RESIDENT_FACTOR * int(glb_bytes)))


def chunk_key(local_x, local_z):
    cx = np.floor((np.asarray(local_x) - CHUNK_ORIGIN[0]) / CHUNK).astype(int)
    cz = np.floor((np.asarray(local_z) - CHUNK_ORIGIN[1]) / CHUNK).astype(int)
    return cx, cz


def chunk_name(cx, cz):
    return f"{int(cx):02d}_{int(cz):02d}"


def in_closed_window(inside_window, x, z):
    """A point inside the ownership polygon or on its edge (a kit placement's origin, continent metres): d1_check
    keeps origins ON the edge (kit-coastal-rock-3_168 stands at local x = 1019.0), so the test nudges 1 cm each way."""
    return any(bool(inside_window(x + ex, z + ez)) for ex, ez in ((0, 0), (-.01, 0), (.01, 0), (0, -.01), (0, .01)))


class CollisionRefused(ValueError):
    """A collision sidecar this publish will not stamp: stale, partial, for another map, or its binaries differ."""


def collision_block(sidecar_path, snapshot_sha, region, server, out):
    """The territory manifest's collision block and the publication record's collision entry.

    With a sidecar (export_collision.py's <region>.collision.json): its block, refused unless it is this region's,
    from a whole-group run, exported from the snapshot this publish reads (sourceSnapshotSha256), on the bake's
    server frame, tile-centres-v1, and its collision.bin and served-grid.escg.gz are in <out> with the digests it
    records. Without one: the client-preview placeholder, refused if <out> already holds exported binaries."""
    out = Path(out)
    if sidecar_path is None:
        held = [name for name in (COLLISION_BIN, SERVED_GRID) if (out / name).exists()]
        if held:
            raise CollisionRefused(f"{out} holds {', '.join(held)} from export_collision.py: publish with "
                                   "--collision <that run's sidecar>, or the manifest would drop the served grid")
        return copy.deepcopy(PREVIEW_COLLISION), None
    sidecar_path = Path(sidecar_path)
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    if sidecar.get("schema") != SIDECAR_SCHEMA:
        raise CollisionRefused(f"{sidecar_path}: schema {sidecar.get('schema')!r}, not {SIDECAR_SCHEMA}")
    if sidecar.get("region") != region:
        raise CollisionRefused(f"{sidecar_path} is {sidecar.get('region')!r}'s, not {region}'s")
    if sidecar.get("partial"):
        raise CollisionRefused(f"{sidecar_path} comes from a --partial export: its seam collars are not the group's")
    block = sidecar.get("collision") or {}
    exported_from = block.get("sourceSnapshotSha256")
    if exported_from != snapshot_sha:
        raise CollisionRefused(f"{sidecar_path} is stale: exported from snapshot {exported_from}, and this publish "
                               f"reads {snapshot_sha}; re-run export_collision.py on this bake")
    cells, origin = list(server["cells"]), [float(v) for v in server["collisionOriginMetres"]]
    if list(block.get("serverCells", [])) != cells or [float(v) for v in block.get("originMetres", [])] != origin:
        raise CollisionRefused(f"{sidecar_path}: frame {block.get('serverCells')} at {block.get('originMetres')}, "
                               f"the bake's {cells} at {origin}")
    if block.get("gridAlignment") != "tile-centres-v1" or block.get("format") != "EWCG-v2":
        raise CollisionRefused(f"{sidecar_path}: {block.get('format')} {block.get('gridAlignment')}, not EWCG-v2 "
                               "tile-centres-v1")
    served = block.get("servedGrid") or {}
    if served.get("format") != "ESCG-v2":
        raise CollisionRefused(f"{sidecar_path}: servedGrid format {served.get('format')!r}, not ESCG-v2")
    for name, expected in ((block.get("binary"), block.get("sha256")), (served.get("binary"), served.get("sha256"))):
        if name not in (COLLISION_BIN, SERVED_GRID):
            raise CollisionRefused(f"{sidecar_path}: unexpected binary {name!r}")
        path = out / name
        if not path.is_file():
            raise CollisionRefused(f"{path} is missing: export_collision.py writes it beside this package")
        found = sha(path)
        if found != expected:
            raise CollisionRefused(f"{path} has sha256 {found}, the sidecar records {expected}: another run's file")
    group = (block.get("groupExport") or {}).get("maps") or {}
    if group.get(region) != {"snapshotSha256": exported_from, "servedGridSha256": served.get("sha256")}:
        raise CollisionRefused(f"{sidecar_path}: its groupExport does not record this map's own snapshot and served "
                               "grid; re-run export_collision.py over the whole group")
    stamped = {"nodeNames": [], **copy.deepcopy(block), "note": SERVED_COLLISION_NOTE}
    record = {"sidecarSha256": sha(sidecar_path), "collisionSha256": block["sha256"],
              "servedGridSha256": served["sha256"], "walkableCells": block.get("walkableCells"),
              "openTiles": served.get("openTiles"), "sourceSnapshotSha256": exported_from}
    return stamped, record


def chunk_collision(block):
    """A chunk manifest's collision block: the territory's frame and format (CHUNK_COLLISION_KEYS, an allow-list)
    without its binaries (a chunk folder holds no collision.bin, and package_client.py refuses a world.json naming a
    file the commit lacks) and without what changes when only a neighbour is re-exported."""
    return {key: value for key, value in block.items() if key in CHUNK_COLLISION_KEYS}


def known_limitations(region, collision_record):
    window = "outside the ownership polygons nothing is exported (the neighbouring territory publishes it)"
    if collision_record is None:
        return ["no server map: collision.bin, served heights, contracts and the map digest wait for the server "
                "stage", window]
    return [SERVED_COLLISION_NOTE, "no map digest: the master world.glb is not committed, so the server's client "
            "content manifest names no packageSha256 for this map", window]


def harvest_package(doc, placements, top_of):
    """The territory manifest's harvestables and harvestGroupings (harvest_presentation.py, whose docstring is the
    marker and package schema) from the bake's harvest markers. `placements` are the territory's published kit
    placements ({"node", "authoringId", "position", "chunk", "groupedNodes"}); `top_of(groupedNodes)` measures the
    highest point of one, asked only for a placement a node binds. Raises ValueError for a marker it refuses."""
    import harvest_presentation as HP
    records = doc.get("gameplay", {}).get("harvestables", [])
    origin = doc["server"]["origin"]
    bound = set()
    for record in records:
        reference = HP.marker_hints(record).get("bindPlacement")
        if reference is not None:
            bound.add(HP.resolve_placement(reference, placements)["node"])
    measured = [dict(p, top=float(top_of(p["groupedNodes"]))) if p["node"] in bound else p for p in placements]
    return HP.package_entries(records, measured, origin)


HARVEST_SCHEMA = "eloria-harvest-presentation-v1"     # harvest_presentation.SCHEMA (the tests keep them equal)


def environment_restamp(out, region, checkout=DEFAULT_CHECKOUT, write=True):
    """The environment publish (--environment): the stub's `environment` into the territory manifest at <out> and
    into every chunk manifest it lists, exactly as a full publish copies it (manifest and chunk_manifest). Returns
    the manifests whose block differed (and, with `write`, now matches). A package this tool did not write, or a chunk
    manifest that is not this territory's, is refused before anything is written."""
    out = Path(out)
    stub = json.loads((Path(checkout) / "eloria-assets/maps/continent-v2" / region / "world.json")
                      .read_text(encoding="utf-8"))
    environment = stub["environment"]
    territory_path = out / "world.json"
    territory = json.loads(territory_path.read_text(encoding="utf-8"))
    if territory.get("asset", {}).get("id") != region or territory.get("provenance", {}).get("tool") != TOOL:
        raise SystemExit(f"refused: {territory_path} is not a {region} package written by {TOOL}")
    documents = [(territory_path, territory)]
    for chunk in territory["streamingChunks"]["chunks"]:
        path = out / chunk["manifest"]
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("asset", {}).get("id") != f"{region}__chunk_{chunk['id']}":
            raise SystemExit(f"refused: {path} is not {region}'s cell {chunk['id']}")
        documents.append((path, document))
    changed = [path for path, document in documents if document.get("environment") != environment]
    if write:
        for path, document in documents:
            if path in changed:
                document["environment"] = copy.deepcopy(environment)
                json_write(path, document)
    return changed


def chunk_manifest(manifest, region, name, stats, bounds):
    """One 96 m cell's package manifest: the territory's, without what only the territory carries."""
    c = copy.deepcopy(manifest)
    for key in ("streamingChunks", "landmarks", "interactives", "portals", "spawnPoints", "harvestables",
                "harvestablesSchema", "harvestGroupings", "npcMarkers", "serviceMarkers", "spawns", "lighting"):
        c.pop(key, None)
    c["asset"].update(id=f"{region}__chunk_{name}", glb="world.glb", bounds=bounds)
    c["bounds"] = bounds
    c["performance"] = stats
    c["externalResources"] = stats["externalResources"]
    c["biomeBlend"] = None
    c["objectMaterialOverrides"] = {"schema": "eloria-object-material-overrides-v1", "entries": []}
    c["collision"] = chunk_collision(c.get("collision", {}))
    return c


def composer_modules(checkout):
    """The twelve-territory composer's modules, imported from this checkout and refused from any other."""
    checkout = Path(checkout).resolve()
    continent = str(checkout / "eloria-assets/maps/nymara-regions/_continent")
    if continent not in sys.path:
        sys.path.insert(0, continent)
    sys.dont_write_bytecode = True
    import authoring as A
    import authoring_catalog as C
    import terrain_export as T
    import bridge_export as BX
    import scene_io as S
    from world_layout import triangle_sample
    from amberwood import gltf as G, mesh as M
    if Path(A.CLIENT).resolve() != checkout:
        raise SystemExit(f"composer modules resolve to {A.CLIENT}, not {checkout}")
    return SimpleNamespace(A=A, C=C, T=T, BX=BX, S=S, G=G, M=M, triangle_sample=triangle_sample)


def open_territory(snapshot_path, region, checkout):
    """Steps 1 and 2 of the publish: the snapshot, the stub's ownership polygon and the one-territory facade world
    the composer's exporters take. export_collision.py opens a bake the same way, so the walk surfaces it rasterises
    are the ones this publisher draws."""
    mods = composer_modules(checkout)
    A, C = mods.A, mods.C
    checkout = Path(checkout).resolve()
    timings = {}
    # 1. Snapshot. Registered v2 contracts validate their authored or hash-bound
    # generated arrival while retaining every ordinary gameplay/source check.
    catalog = checkout / "godot-client/world_authoring/continent-v2/territories.json"
    contract = next(c for c in C.authored_contracts(catalog) if c.id == region)
    t = time.time()
    snapshot = A.load_snapshot(snapshot_path, production=False, contract=contract)
    timings["snapshot_s"] = round(time.time() - t, 1)
    doc = snapshot.document
    translation = snapshot.translation
    stub_path = checkout / "eloria-assets/maps/continent-v2" / region / "world.json"
    stub = json.loads(stub_path.read_text(encoding="utf-8"))
    import ownership
    rings = ownership.rings(stub["continentGeography"])
    polygon = rings[0] if len(rings) == 1 else rings
    if list(stub["continentGeography"]["translation"]) != list(map(float, translation)):
        raise SystemExit("stub manifest translation differs from the snapshot")

    def inside_window(cx_, cz_):
        return point_in_polygon(cx_, cz_, polygon)

    # 2. The one-territory facade (the fields tests/test_authoring.py's facade gives authored_overlays).
    terrain = doc["terrain"]
    origin = np.asarray(terrain["origin"], float) + translation[[0, 2]]
    nx, nz = snapshot.terrain_width, snapshot.terrain_height
    gx1 = origin[0] + np.arange(nx) * CELL
    gz1 = origin[1] + np.arange(nz) * CELL
    gx, gz = np.meshgrid(gx1, gz1)
    height = snapshot.effective_heights()
    cell_inside = inside_window(gx + CELL / 2, gz + CELL / 2)
    world = SimpleNamespace(authoring_snapshots={region: snapshot}, ids=[region],
                            owner=np.where(cell_inside, 0, -1), gx=gx, gz=gz, height=height, x=gx1, z=gz1,
                            x0=float(origin[0]), z0=float(origin[1]), x1=float(gx1[-1]), z1=float(gz1[-1]),
                            plan={"seed": 0, "rivers": [], "lakes": [], "sea_level": 0.0})
    world.owner_at = lambda px, pz: np.where(inside_window(px, pz), 0, -1)
    world.height_at = lambda px, pz: mods.triangle_sample(height, px, pz, world.x0, world.z0)
    return SimpleNamespace(modules=mods, snapshot=snapshot, doc=doc, translation=translation, stub=stub,
                           polygon=polygon, inside_window=inside_window, world=world, height=height, gx=gx, gz=gz,
                           nx=nx, nz=nz, cell_inside=cell_inside, timings=timings)


def bind_certified_texture_aliases(snapshot, checkout, image_paths, addressed_images=None):
    """Bind omitted image paths only to cryptographically certified bytes.

    Godot's imported-resource cache can deduplicate identical kit models across
    sw_isle/gull_skerries/tollholms, recording only the first texture path in a
    bake. The source GLBs retain their own relative paths. Preserve the bake's
    exact image hash requirement when resolving those byte-identical aliases.
    Missing dependencies may also be certified transitively by a complete
    SHA-256 filename recorded inside a hash-pinned source model. Neither
    snapshot bytes nor collision provenance change.
    """
    checkout = Path(checkout).resolve()
    certified = dict(snapshot.source_sha256)
    addressed_images = addressed_images or {}
    images_by_hash = {}
    for path, digest in sorted(certified.items()):
        if Path(path).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            images_by_hash.setdefault(digest, path)
    aliases = []
    for image_path in sorted(set(Path(p).resolve() for p in image_paths)):
        try:
            key = image_path.relative_to(checkout).as_posix()
        except ValueError as error:
            raise ValueError("external texture alias escapes the client checkout") from error
        if key in snapshot.source_sha256:
            continue
        digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
        address = addressed_images.get(image_path)
        if address is not None:
            if digest != address["sha256"]:
                raise ValueError(f"texture bytes differ from their model's content address: {key}")
            snapshot.source_sha256[key] = digest
            aliases.append({"path": key, **address})
            continue
        canonical = images_by_hash.get(digest)
        if canonical is None:
            # Keep the ordinary strict embedding refusal for an unbound image.
            continue
        if hashlib.sha256((checkout / canonical).read_bytes()).hexdigest() != digest:
            raise ValueError(f"certified texture changed after the bake: {canonical}")
        snapshot.source_sha256[key] = digest
        aliases.append({"path": key, "certifiedPath": canonical, "sha256": digest})
    return aliases


def source_texture_paths(snapshot, authoring, reader):
    paths, addressed = set(), {}
    sources, verified = {}, set()
    for entry in snapshot.document.get("objects", []):
        binding = entry["bakedSource"]
        identity = (binding["path"], binding["sha256"])
        if identity in verified:
            continue
        verified.add(identity)
        source = authoring.baked_asset_path(entry, snapshot)
        sources[source] = binding
    for source, binding in sources.items():
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"source model changed after the bake: {source}")
        document, _ = reader.load(source)
        for image in document.get("images", []):
            uri = image.get("uri")
            if uri is not None:
                if ":" in uri or uri.startswith(("/", "\\")):
                    raise ValueError(f"{source}: external image URI must be relative")
                path = (source.parent / uri).resolve()
                paths.add(path)
                # The complete SHA-256 image filename is itself inside the
                # hash-pinned model JSON. Verify it before accepting bytes that
                # Godot's imported dependency cache omitted.
                if re.fullmatch(r"[0-9a-f]{64}", path.stem):
                    addressed[path] = {"sha256": path.stem,
                                       "sourceModel": binding["path"],
                                       "sourceModelSha256": binding["sha256"]}
    return paths, addressed


def main():
    global REGION
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", type=Path, help="the bake (required unless --environment)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--shared", type=Path, help="the shared image pool (required unless --environment)")
    ap.add_argument("--environment", action="store_true",
                    help="publish only the stub's environment block into the package at --out")
    ap.add_argument("--check", action="store_true", help="with --environment: write nothing, exit 1 on a difference")
    ap.add_argument("--work", type=Path, default=None)
    ap.add_argument("--chunks", default="", help="comma list cx_cz: export only these cells (a test publish)")
    ap.add_argument("--budget-mib", type=float, default=None, help="streamingChunks.maximumResidentBytes (default 256)")
    ap.add_argument("--master", action="store_true", help="also write the region master (digest only for the client)")
    ap.add_argument("--checkout", type=Path, default=DEFAULT_CHECKOUT)
    ap.add_argument("--region", required=True, help="the active catalog territory to publish")
    ap.add_argument("--collision", type=Path, default=None,
                    help="export_collision.py's <region>.collision.json for this bake (stamps the served grid)")
    a = ap.parse_args()
    REGION = a.region
    if a.environment:
        changed = environment_restamp(a.out, REGION, a.checkout.resolve(), write=not a.check)
        verb = "differ from" if a.check else "now carry"
        print(f"{REGION}: {len(changed)} manifest(s) {verb} the stub's environment")
        raise SystemExit(1 if a.check and changed else 0)
    if a.check:
        ap.error("--check needs --environment")
    if a.snapshot is None or a.shared is None:
        ap.error("--snapshot and --shared are required for a publish")
    t_start = time.time()
    timings = {}
    checkout = a.checkout.resolve()
    work = (a.work or (a.out.parent / (a.out.name + ".work"))).resolve()
    work.mkdir(parents=True, exist_ok=True)
    out = a.out.resolve(); shared = a.shared.resolve()

    # 0. The served walk grid's sidecar, checked before the slow part.
    snapshot_sha = sha(a.snapshot)
    server_block = json.loads(Path(a.snapshot).read_text(encoding="utf-8"))["server"]
    try:
        collision, collision_record = collision_block(a.collision, snapshot_sha, REGION, server_block, out)
    except CollisionRefused as error:
        raise SystemExit(f"refused: {error}") from None

    # 1-2. The snapshot and the one-territory facade (open_territory).
    territory = open_territory(a.snapshot, REGION, checkout)
    mods = territory.modules
    A, T, BX, S, G, M = mods.A, mods.T, mods.BX, mods.S, mods.G, mods.M
    timings.update(territory.timings)
    snapshot, doc, translation = territory.snapshot, territory.doc, territory.translation
    image_paths, addressed_images = source_texture_paths(snapshot, A, S.GR)
    texture_aliases = bind_certified_texture_aliases(snapshot, checkout, image_paths, addressed_images)
    stub, polygon, inside_window, world = territory.stub, territory.polygon, territory.inside_window, territory.world
    height, gx, gz, nx, nz = territory.height, territory.gx, territory.gz, territory.nx, territory.nz
    cell_inside = territory.cell_inside
    frame_origin, frame_cells = doc["server"]["collisionOriginMetres"], doc["server"]["cells"]
    CHUNK_ORIGIN[:] = [CHUNK_LATTICE - CHUNK * max(0, math.ceil((CHUNK_LATTICE - corner) / CHUNK))
                       for corner in (float(frame_origin[0]), float(frame_origin[1]) - float(frame_cells[1]))]

    wanted = {c for c in a.chunks.split(",") if c} or None

    def keep(name):
        return wanted is None or name in wanted

    builder = G.GltfBuilder("Eloria continent v2: " + REGION + " surface (" + TOOL + ")")
    # partition_surface's two shared materials (terrain_export.py partition_surface), by the same names: the loader
    # keys the sea shader on 'water_sea' and the look pass paints Terrain_* as terrain.
    rng = np.random.default_rng(19)
    grain = rng.uniform(.84, 1., (128, 128))
    builder.add_image("continental-ground", T.png(np.repeat((grain[..., None] * 255).astype(np.uint8), 3, axis=2)))
    builder.add_material(G.Material("continental_ground", base_color_texture="continental-ground", roughness=.95))
    xx, zz = np.meshgrid(np.arange(128), np.arange(128))
    ripple = .9 + .06 * np.sin(xx * .34 + np.sin(zz * .15)) + .025 * np.sin(zz * .7)
    builder.add_image("continental-water", T.png(np.clip(ripple[..., None] * np.array([104, 161, 166]), 0, 255)
                                                 .astype(np.uint8)))
    builder.add_material(G.Material("water_sea", base_color_texture="continental-water", roughness=.55,
                                    double_sided=True))
    # Budget the saved instances and actual overlay faces before choosing the
    # lattice phase. Four triangles per terrain cell reserve both land and sea.
    import chunk_budget as CB
    A.build_retained_library(snapshot, work / "library")
    ldoc, lbody = S.GR.load(work / "library" / "library.glb")
    library = json.loads((work / "library" / "library.json").read_text(encoding="utf-8"))
    by_name = {ldoc["nodes"][i].get("name"): i for i in ldoc["scenes"][0]["nodes"]}
    budget_points, budget_placements, budget_triangles = [], [], []
    for placement in library["placements"]:
        budget_points.append(np.asarray(placement["position"])[[0, 2]])
        budget_placements.append(1)
        budget_triangles.append(sum(CB.subtree_triangles(ldoc, by_name[n])
                                    for n in placement["groupedNodes"]))
    terrain_centres = np.stack([gx[:-1, :-1]+CELL/2-translation[0],
                               gz[:-1, :-1]+CELL/2-translation[2]], axis=-1)[cell_inside[:-1, :-1]]
    budget_points.extend(terrain_centres)
    budget_placements.extend(np.zeros(len(terrain_centres)))
    budget_triangles.extend(np.full(len(terrain_centres), 4))
    overlays = T.authored_overlays(world, builder)
    for item in overlays:
        mesh = item["mesh"]
        centres = np.asarray(mesh.positions, float)[np.asarray(mesh.indices).reshape(-1, 3)].mean(axis=1)
        centres = centres[inside_window(centres[:, 0], centres[:, 2])]
        budget_points.extend(centres[:, [0, 2]]-translation[[0, 2]])
        budget_placements.extend(np.zeros(len(centres)))
        budget_triangles.extend(np.ones(len(centres)))
    parts, _walk, _records = BX._authored_bridge_geometry(world, builder)
    for _region, _node, mesh, _walks, _identity in parts:
        centre = np.asarray(mesh.positions, float).mean(axis=0)
        if inside_window(centre[0], centre[2]):
            budget_points.append(centre[[0, 2]]-translation[[0, 2]])
            budget_placements.append(0)
            budget_triangles.append(len(mesh.indices)//3)
    CHUNK_ORIGIN[:], chunk_budget_record = CB.choose_origin(
        budget_points, budget_placements, budget_triangles,
        [float(frame_origin[0]), float(frame_origin[1])-float(frame_cells[1])], lattice=CHUNK_LATTICE)
    roots = {}          # chunk -> surface root node indices
    bounds = {}         # chunk -> [lo, hi] territory-local

    def note_bounds(name, positions):
        local = np.asarray(positions, float) - translation
        lo, hi = local.min(axis=0), local.max(axis=0)
        if name in bounds:
            bounds[name] = [np.minimum(bounds[name][0], lo), np.maximum(bounds[name][1], hi)]
        else:
            bounds[name] = [lo, hi]

    def add_node(name, chunk, mesh, tangents):
        builder.add_mesh(name, mesh, with_tangents=tangents)
        roots.setdefault(chunk, []).append(builder.add_node(G.Node(name, mesh=name)))
        note_bounds(chunk, mesh.positions)

    # 3. Terrain_<region>_<cx>_<cz>: the walk surface (navigation.surfaceNodePrefixes) the client grounds actors on and
    # the grass beds ray against; drawn 0.006 m under the authored base, as partition_surface draws it.
    t = time.time()
    dz, dx = np.gradient(height, CELL, CELL)
    normals = np.stack([-dx, np.ones_like(dx), -dz], axis=-1)
    normals /= np.linalg.norm(normals, axis=-1, keepdims=True)
    colours = snapshot.base_colors()
    vertex_colours = (np.concatenate([colours[..., :3].astype(float) / 255.0, np.ones((nz, nx, 1))], axis=-1)
                      if colours is not None else None)
    local_cx = gx[:-1, :-1] + CELL / 2 - translation[0]
    local_cz = gz[:-1, :-1] + CELL / 2 - translation[2]
    ccx, ccz = chunk_key(local_cx, local_cz)
    owned = cell_inside[:-1, :-1]
    keys = np.where(owned, ccx * 1000 + ccz, -1)
    for key in np.unique(keys[keys >= 0]):
        name = chunk_name(key // 1000, key % 1000)
        if not keep(name):
            continue
        row, col = np.nonzero(keys == key)
        a_idx = row * nx + col
        tri = np.stack([a_idx, a_idx + nx, a_idx + 1, a_idx + 1, a_idx + nx, a_idx + nx + 1], axis=1).ravel()
        unique, inverse = np.unique(tri, return_inverse=True)
        positions = np.c_[gx.ravel()[unique], height.ravel()[unique], gz.ravel()[unique]]
        mesh = M.Mesh(positions=positions, normals=normals.reshape(-1, 3)[unique],
                      uvs=np.c_[gx.ravel()[unique], gz.ravel()[unique]] * .17,
                      colors=None if vertex_colours is None else vertex_colours.reshape(-1, 4)[unique],
                      indices=inverse.astype(np.int64), material="continental_ground")
        add_node(f"Terrain_{REGION}_{name}", name, mesh, False)
    timings["terrain_s"] = round(time.time() - t, 1)

    # 4. Water_<region>_<cx>_<cz>: one water_sea mesh per cell (the loader swaps in continent_water.gdshader by this
    # name and material: world_loader.gd _apply_continent_water). Sea: the cell's window rectangle at 0 m wherever the
    # cell has ground below +0.5 m (terrain hides it elsewhere, as the viewer's sea plane is hidden). Lakes: the
    # saved ellipses at their level. Rivers: the saved ribbons at their surface. Faces go to the cell of their centroid.
    t = time.time()
    water_faces = {}

    def put_water(faces):
        faces = np.asarray(faces, float).reshape(-1, 3, 3)
        if not len(faces):
            return
        cent = faces.mean(axis=1)
        ok = inside_window(cent[:, 0], cent[:, 2])
        cx_, cz_ = chunk_key(cent[:, 0] - translation[0], cent[:, 2] - translation[2])
        for i in np.flatnonzero(ok):
            water_faces.setdefault(chunk_name(cx_[i], cz_[i]), []).append(faces[i])

    low = np.where(owned, height[:-1, :-1] < .5, False)
    import ownership
    rings = ownership.rings(polygon)
    flat = ownership.points(polygon)
    poly_xs = sorted(set(flat[:, 0])); poly_zs = sorted(set(flat[:, 1]))
    rectangle = len(rings) == 1 and len(rings[0]) == 4 and len(poly_xs) == 2 and len(poly_zs) == 2
    if not rectangle:
        import shapely
        from shapely.geometry import box
        window_shape = ownership.geometry(polygon)
    for key in np.unique(keys[(keys >= 0) & low]):
        cx_, cz_ = key // 1000, key % 1000
        x0 = CHUNK_ORIGIN[0] + cx_ * CHUNK + translation[0]; z0 = CHUNK_ORIGIN[1] + cz_ * CHUNK + translation[2]
        if rectangle:
            px = np.clip([x0, x0 + CHUNK], min(poly_xs), max(poly_xs))
            pz = np.clip([z0, z0 + CHUNK], min(poly_zs), max(poly_zs))
            a0, b0, c0, d0 = (px[0], 0, pz[0]), (px[1], 0, pz[0]), (px[1], 0, pz[1]), (px[0], 0, pz[1])
            water_faces.setdefault(chunk_name(cx_, cz_), []).extend([np.array([a0, d0, b0]), np.array([b0, d0, c0])])
            continue
        piece = window_shape.intersection(box(x0, z0, x0 + CHUNK, z0 + CHUNK))
        for tri in shapely.constrained_delaunay_triangles(piece).geoms if not piece.is_empty else []:
            (ta, tb, tc) = list(tri.exterior.coords)[:3]
            water_faces.setdefault(chunk_name(cx_, cz_), []).append(
                np.array([(ta[0], 0, ta[1]), (tb[0], 0, tb[1]), (tc[0], 0, tc[1])]))
    for lake in doc.get("waterRegions", []):
        if lake.get("shape") != "ellipse":
            continue
        centre = np.asarray(lake["center"], float) + translation[[0, 2]]
        level = float(lake["level"]) + translation[1]
        rx, rz = map(float, lake["radii"])
        n = 96
        ang = np.linspace(0, 2 * math.pi, n + 1)[:-1]
        ring = np.c_[centre[0] + rx * np.cos(ang), np.full(n, level), centre[1] + rz * np.sin(ang)]
        middle = np.array([centre[0], level, centre[1]])
        put_water([np.array([middle, ring[(i + 1) % n], ring[i]]) for i in range(n)])
    for path in doc.get("paths", []):
        if path.get("kind") != "river":
            continue
        pts = np.asarray([p["position"] for p in path["points"]], float) + translation
        widths = np.asarray([float(p["width"]) for p in path["points"]])
        faces = []
        for i in range(len(pts) - 1):
            d = pts[i + 1][[0, 2]] - pts[i][[0, 2]]
            length = np.linalg.norm(d)
            if length < 1e-6:
                continue
            side = np.array([-d[1], d[0]]) / length
            l0 = pts[i].copy(); r0 = pts[i].copy(); l1 = pts[i + 1].copy(); r1 = pts[i + 1].copy()
            l0[[0, 2]] += side * widths[i] / 2; r0[[0, 2]] -= side * widths[i] / 2
            l1[[0, 2]] += side * widths[i + 1] / 2; r1[[0, 2]] -= side * widths[i + 1] / 2
            faces += [np.array([l0, r0, l1]), np.array([r0, r1, l1])]
        put_water(faces)
    for name, faces in water_faces.items():
        if not keep(name):
            continue
        faces = np.asarray(faces, float)
        up = np.cross(faces[:, 1] - faces[:, 0], faces[:, 2] - faces[:, 0])[:, 1]
        faces[up < 0] = faces[up < 0][:, [0, 2, 1]]          # every water face upward (glTF CCW from above)
        vertices = faces.reshape(-1, 3)
        mesh = M.Mesh(positions=vertices, normals=np.tile([0., 1., 0.], (len(vertices), 1)),
                      uvs=vertices[:, [0, 2]] * .17, indices=np.arange(len(vertices), dtype=np.int64),
                      material="water_sea")
        add_node(f"Water_{REGION}_{name}", name, mesh, False)
    timings["water_s"] = round(time.time() - t, 1)

    # 5. The authored overlays, exactly as the twelve-territory exporter builds them, cut into the cells.
    t = time.time()
    for item in overlays:
        mesh = item["mesh"]
        faces = np.asarray(mesh.indices).reshape(-1, 3)
        cent = np.asarray(mesh.positions, float)[faces].mean(axis=1)
        ok = inside_window(cent[:, 0], cent[:, 2])
        cx_, cz_ = chunk_key(cent[:, 0] - translation[0], cent[:, 2] - translation[2])
        key = np.where(ok, cx_ * 1000 + cz_, -1)
        order = np.argsort(key, kind="stable")
        sorted_keys = key[order]
        starts = np.flatnonzero(np.r_[True, sorted_keys[1:] != sorted_keys[:-1]])
        ends = np.r_[starts[1:], len(order)]
        for s0, e0 in zip(starts, ends):
            k = int(sorted_keys[s0])
            if k < 0:
                continue                                    # outside the window: the second map's (D2), not ours
            name = chunk_name(k // 1000, k % 1000)
            if not keep(name):
                continue
            piece = T._mesh_faces(mesh, order[s0:e0])
            add_node(f"{item['name']}_{REGION}_{name}", name, piece, True)
    del overlays
    timings["overlays_s"] = round(time.time() - t, 1)

    # 6. Saved bridges (deck strips are Walk_ surfaces; supports and edges are visual).
    t = time.time()
    for _region, node, mesh, _walks, _identity in parts:
        cent = np.asarray(mesh.positions, float).mean(axis=0)
        if not inside_window(cent[0], cent[2]):
            continue
        cx_, cz_ = chunk_key(cent[0] - translation[0], cent[2] - translation[2])
        name = chunk_name(cx_, cz_)
        if keep(name):
            add_node(node, name, mesh, True)
    timings["bridges_s"] = round(time.time() - t, 1)
    surface_path = work / "surface.glb"
    builder.write_glb(str(surface_path))
    del builder
    sdoc, sbody = S.GR.load(surface_path)
    # image_policy.json, applied to both source documents before the exporter hashes, counts and writes any image:
    # the 1254 px ground albedos become their recorded 1256 px copies, which a BC7 sidecar can hold.
    import image_policy as IP
    v2_dir = checkout / "eloria-assets/maps/continent-v2/_continent_v2"
    policy = IP.load_policy(v2_dir / "image_policy.json")
    sdoc, sbody, surface_policy = IP.apply(sdoc, sbody, v2_dir / "shared-assets", policy)
    timings["surface_glb_bytes"] = surface_path.stat().st_size

    # 7. Kit placements: the retained library (wrappers at the saved local matrices), by the cell of their origin
    # (as g1_budget counts them).
    t = time.time()
    ldoc, lbody, library_policy = IP.apply(ldoc, lbody, v2_dir / "shared-assets", policy)
    walk_kit = 0
    for node in ldoc["nodes"]:
        name_ = node.get("name", "")
        if "mesh" in node and name_.startswith(WALK_KIT_STEMS):
            node["name"] = f"Walk_{REGION}_" + name_[len("kit-sw-"):].replace("-", "_")
            walk_kit += 1
    timings["walk_kit_nodes"] = walk_kit
    matrices = S.GR.hierarchy(ldoc)[0]
    lib_roots = {}
    outside = 0
    markers = []
    # Every placement this territory publishes, for promoted-scenery harvest nodes (harvest_presentation.py): the
    # node it is, the cell that holds it and its highest point, whichever cells this run writes.
    published_placements = []
    for placement in library["placements"]:
        x, _y, z = placement["position"]
        # Closed window (in_closed_window): origins ON the edge are kept.
        if not in_closed_window(inside_window, x + translation[0], z + translation[2]):
            outside += 1
            continue
        name = chunk_name(*chunk_key(x, z))
        published_placements.append({"node": placement["node"], "authoringId": placement.get("authoringId", ""),
                                     "position": [float(v) for v in placement["position"]], "chunk": name,
                                     "groupedNodes": list(placement["groupedNodes"])})
        if not keep(name):
            continue
        for node_name in placement["groupedNodes"]:
            index = by_name[node_name]
            lib_roots.setdefault(name, []).append(index)
            # A prototype root may declare a point light (extras.eloria.light: kind, anchor in kit metres, color,
            # energyHint, rangeHint; the N20 landing beacon's crystal). Each placement of it becomes one of the
            # territory manifest's lighting.markers, which the client binds as an OmniLight3D under the map's root
            # (src/world/light_marker_binder.gd, main.gd _bind_light_markers).
            for child in ldoc["nodes"][index].get("children", []):
                light = ldoc["nodes"][child].get("extras", {}).get("eloria", {}).get("light")
                if not light:
                    continue
                at = matrices[child] @ np.array([*map(float, light["anchor"]), 1.0])
                markers.append({"id": f"Light_{str(light.get('kind', 'lamp')).title()}_{node_name}",
                                "kind": str(light.get("kind", "lamp")), "node": node_name,
                                "position": [round(float(v), 3) for v in at[:3]],
                                "color": [float(v) for v in light["color"]],
                                "energyHint": float(light["energyHint"]), "rangeHint": float(light["rangeHint"])})
            lo, hi = S.subtree_bounds(ldoc, lbody, index, matrices)
            if name in bounds:
                bounds[name] = [np.minimum(bounds[name][0], lo), np.maximum(bounds[name][1], hi)]
            else:
                bounds[name] = [lo, hi]
    timings["library_s"] = round(time.time() - t, 1)

    # 7b. Harvest presentation (harvest_presentation.py): every harvest marker's variant, yaw, footprint, grouping
    # and promoted-scenery binding, and the groupings the maps mark. Only a bound placement's height is measured.
    try:
        harvestables, harvest_groupings = harvest_package(
            doc, published_placements,
            lambda nodes: max(S.subtree_bounds(ldoc, lbody, by_name[n], matrices)[1][1] for n in nodes))
    except ValueError as error:
        raise SystemExit(f"refused: {error}") from None
    timings["harvest_nodes"] = len(harvestables)

    # 8. The territory manifest and one package per cell (build_continent.export_geometry's shape).
    import arrivals
    import frames
    spawn = arrivals.resolve(doc, frames.load_source(REGION, checkout), checkout)
    server = doc["server"]
    win = ownership.points(polygon) - translation[[0, 2]]
    inside_heights = height[cell_inside]
    tops = [b[1][1] for b in bounds.values()] or [float(inside_heights.max())]
    asset_bounds = {"min": [float(win[:, 0].min()), float(inside_heights.min()), float(win[:, 1].min())],
                    "max": [float(win[:, 0].max()), float(max(inside_heights.max(), max(tops))),
                            float(win[:, 1].max())]}
    half = [int(server["cells"][0]) // 2, int(server["cells"][1]) // 2]
    coordinate = {"metresPerTile": 1.0, "serverOrigin": list(server["origin"]), "serverCells": list(server["cells"]),
                  "origin": [0, 0, 0], "walkingHeight": float(spawn["position"][1]), "invertServerY": True,
                  "serverStorageVersion": 1, "serverTileMin": [0, 0],
                  "addressableWorldBounds": {"min": [-int(server["origin"][0]), -(int(server["cells"][1])
                                                                                  - int(server["origin"][1]))],
                                             "max": [int(server["cells"][0]) - int(server["origin"][0]),
                                                     int(server["origin"][1])]}}
    spawn_record = {"default": True, "id": spawn["id"], "position": spawn["position"],
                    "facing": spawn.get("facing", [0.0, 0.0, -1.0]), "serverTile": spawn.get("serverTile")}
    if spawn.get("generated"):
        spawn_record["generated"] = True
    landmarks = []
    for mark in doc["gameplay"].get("landmarks", []):
        p = mark["position"]
        if inside_window(p[0] + translation[0], p[2] + translation[2]):
            landmarks.append({"id": mark["id"], "name": mark.get("name", mark["id"]),
                              "label": mark.get("label", mark.get("name", mark["id"])),
                              "type": "landmark", "position": p, "serverTile": mark.get("serverTile")})
    # Every NPC marker with a map category keeps its shop dot (map_categories.py); an unknown category is refused,
    # never dropped.
    import map_categories as MC
    try:
        service_markers = MC.service_markers(doc["gameplay"].get("npcMarkers", []))
    except MC.CategoryError as error:
        raise SystemExit(f"refused: {error}") from None
    manifest = {
        "schemaVersion": "1.0.0", "assetVersion": "1.0.0",
        "asset": {"id": REGION, "name": stub["asset"]["name"], "glb": "world.glb", "units": "meters",
                  "coordinateSystem": {"handedness": "right", "upAxis": "Y", "northAxis": "-Z"}, "origin": [0, 0, 0],
                  "bounds": asset_bounds, "playableBounds": asset_bounds, "mapBounds": asset_bounds,
                  "seaLevel": 0.0, "serverCells": int(server["cells"][0])},
        "coordinateTransform": coordinate,
        "spawnPoints": [spawn_record], "spawns": [spawn_record],
        "collision": collision,
        "navigation": {"surfaceNodePrefixes": ["Terrain_", "Walk_"], "terrainConforming": True,
                       "authority": "server", "defaultSpawn": spawn["id"]},
        "landmarks": landmarks,
        "interactives": [{key: mark[key] for key in
                          ("id", "name", "label", "type", "objectId", "position", "serverTile") if key in mark}
                         for mark in doc["gameplay"].get("interactives", []) if mark.get("type") == "storage"],
        "npcMarkers": [], "harvestablesSchema": HARVEST_SCHEMA, "harvestables": harvestables,
        "harvestGroupings": harvest_groupings, "portals": [],
        "serviceMarkers": service_markers,
        "environment": stub["environment"],
        "lighting": {"markers": sorted(markers, key=lambda m: m["id"])},
        "continentGeography": {"revision": stub["continentGeography"]["revision"],
                               "translation": list(map(float, translation)), "ownershipPolygon": rings[0],
                               "ownershipPolygons": rings,
                               "geometryMode": "continent-chunks-v1"},
        "productionStatus": ("chunk-streamed for the game client, with the served walk grid export_collision.py "
                             "wrote (collision.bin, served-grid.escg.gz); the server rows are publish_server.py's"
                             if collision_record else
                             "client preview: chunk-streamed for the game client; no server map, no contracts"),
        "knownLimitations": known_limitations(REGION, collision_record),
        "provenance": {"tool": TOOL, "snapshotSha256": snapshot_sha,
                       "sceneSha256": doc["sources"]["scene"]["sha256"]},
        "externalResources": {},
        "streamingChunks": {"schemaVersion": "1.0", "coordinateSpace": "territory-local", "preloadDistance": 240,
                            "retainDistance": 320, "maximumLoadedChunks": 64,
                            "maximumResidentBytes": int(a.budget_mib * 1048576) if a.budget_mib else SHIPPING_BUDGET,
                            "chunks": []},
    }
    t = time.time()
    names = sorted(set(roots) | set(lib_roots))
    for name in names:
        chunk_root = out / "chunks" / name
        exporter = S.Exporter(chunk_root / "world.glb", shared)
        surface_roots = roots.get(name, [])
        if surface_roots:
            exporter.add(sdoc, sbody, surface_roots,
                         transforms={r: [-float(translation[0]), 0.0, -float(translation[2])] for r in surface_roots})
        if lib_roots.get(name):
            exporter.add(ldoc, lbody, lib_roots[name])
        trim_extensions(exporter)
        placements_count = sum(1 for p in library["placements"]
                               if chunk_name(*chunk_key(p["position"][0], p["position"][2])) == name)
        triangle_count = sum(CB.subtree_triangles(exporter.doc, r)
                             for r in exporter.doc["scenes"][0]["nodes"])
        if placements_count > CB.PLACEMENTS or triangle_count > CB.TRIANGLES:
            raise ValueError(f"{REGION}/{name}: chunk budget exceeded: {placements_count} placements, "
                             f"{triangle_count} triangles (limits {CB.PLACEMENTS}/{CB.TRIANGLES})")
        stats = exporter.write()
        lo, hi = bounds[name]
        cb = {"min": [float(v) for v in lo], "max": [float(v) for v in hi]}
        json_write(chunk_root / "world.json", chunk_manifest(manifest, REGION, name, stats, cb))
        geometry = geometry_resident_bytes(stats["glbBytes"])
        manifest["streamingChunks"]["chunks"].append({
            "id": name, "manifest": f"chunks/{name}/world.json", "bounds": cb,
            "estimatedResidentBytes": geometry + sum(stats["sharedResourceResidentBytes"].values()),
            "glbBytes": stats["glbBytes"], "geometryResidentBytes": geometry,
            "placements": placements_count, "triangles": triangle_count,
            "sharedResourceResidentBytes": stats["sharedResourceResidentBytes"]})
    timings["chunks_s"] = round(time.time() - t, 1)
    picture = kept_minimap(out, manifest["streamingChunks"]["chunks"])
    if picture:
        manifest["minimap"] = picture
    # Every image the cells name, listed on the territory too, so the client's chunk budget reads the sidecar indexes
    # before the first cell import (territory_resources).
    manifest["externalResources"] = territory_resources(out, names)
    json_write(out / "world.json", manifest)
    if wanted is None:
        for directory in (out / "chunks").iterdir():
            if directory.is_dir() and re.fullmatch(r"\d+_\d+", directory.name) and directory.name not in names:
                old = directory / "world.json"
                if old.is_file() and json.loads(old.read_text(encoding="utf-8")).get("asset", {}).get("id", "") \
                        == f"{REGION}__chunk_{directory.name}":
                    shutil.rmtree(directory)
    if a.master:
        t = time.time()
        master = S.Exporter(out / "world.glb", shared, part_bytes=S.PACKAGE_PART_BYTES)
        every_surface = [r for n in names for r in roots.get(n, [])]
        master.add(sdoc, sbody, every_surface,
                   transforms={r: [-float(translation[0]), 0.0, -float(translation[2])] for r in every_surface})
        master.add(ldoc, lbody, [r for n in names for r in lib_roots.get(n, [])])
        trim_extensions(master)
        master.write()
        timings["master_s"] = round(time.time() - t, 1)
    # Published as baked, every cell carries its own copy of each repeated kit
    # prop and its normals at 32 bits. The space passes settle that, and the
    # figures the manifests record about their own GLBs with it, including the
    # pooled prototypes each cell now draws (sharedMeshResidentBytes) - so they
    # run before the record below measures what shipped. GEOMETRY_RESIDENT_FACTOR
    # goes with them: on a territory's first publish there is no
    # publication.json yet to read it from, and the prototypes count at it too.
    t = time.time()
    PF.finish([out], factor=GEOMETRY_RESIDENT_FACTOR)
    timings["space_passes_s"] = round(time.time() - t, 1)
    manifest = json.loads((out / "world.json").read_text(encoding="utf-8"))
    glbs = sorted((out / "chunks").glob("*/world.glb"))
    sizes = [p.stat().st_size for p in glbs]
    record = {"region": REGION, "tool": TOOL,
              "snapshot": {"sha256": snapshot_sha, "sceneSha256": doc["sources"]["scene"]["sha256"],
                           "recipe": "region_bake_cli.gd --scene %s --output <bake>/continent-authoring.json"
                                     % doc["sources"]["scene"]["path"]},
              "collision": collision_record,
              "chunks": len(names), "kitPlacementsOutsideWindow": outside,
              "lightingMarkers": len(manifest["lighting"]["markers"]),
              "chunkGlbBytes": {"total": sum(sizes), "max": max(sizes) if sizes else 0,
                                "over100MiB": [str(p) for p, s in zip(glbs, sizes) if s > 100 * 2 ** 20]},
              "estimatedResidentMiB": {c["id"]: round(c["estimatedResidentBytes"] / 1048576, 1)
                                       for c in manifest["streamingChunks"]["chunks"]},
              "timings": timings, "seconds": round(time.time() - t_start, 1)}
    record["imagePolicy"] = {"surface": surface_policy, "library": library_policy}
    if doc.get("sources", {}).get("generatedArrival"):
        record["generatedArrival"] = doc["sources"]["generatedArrival"]
    record["geometryResidentFactor"] = GEOMETRY_RESIDENT_FACTOR
    record["chunkBudget"] = chunk_budget_record
    if texture_aliases:
        record["certifiedTextureAliases"] = texture_aliases
    json_write(out / "publication.json", record)
    print(json.dumps({k: v for k, v in record.items() if k != "estimatedResidentMiB"}, indent=1))


if __name__ == "__main__":
    main()
