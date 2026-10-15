"""Reapply server-owned marker tiles after deterministic region builds."""
import json
from pathlib import Path
import glb_reader as G
from verify_runtime import VerticalRayIndex


def native_tile_delta(manifest, package):
    """Sidecars keep the authored tile frame across an expanded server grid.

    A native builder and a published package read the same source posts. The
    origin difference changes their served tile, never their world position.
    """
    path = Path(__file__).resolve().parents[1] / 'continent-geography.json'
    if not path.is_file(): return [0., 0.]
    region = package.name.replace('-', '_')
    plan = json.loads(path.read_text(encoding='utf-8'))['regions'].get(region)
    if plan is None: return [0., 0.]
    origin = manifest['coordinateTransform']['serverOrigin']
    return [origin[i] - plan['nativeServerOrigin'][i] for i in (0,1)]

def apply(manifest, package, posts, glb_name="world.glb"):
    document, body = G.load(package / glb_name)
    selected = G.named(document, "Terrain_") + G.named(document, "Walk_")
    ground = VerticalRayIndex(G.triangles(document, body, selected), cell=4)
    transform = manifest["coordinateTransform"]
    ox, oy = transform["serverOrigin"]
    metres = transform["metresPerTile"]
    delta = native_tile_delta(manifest, package)
    for bucket, entries in posts.items():
        target = manifest
        for part in bucket.split("."):
            target = target.get(part, {})
        for entry in target if isinstance(target,list) else []:
            tile = entries.get(entry.get("id"))
            if tile is None:
                continue
            tile = [int(tile[i] + delta[i]) for i in (0,1)]
            x, z = (tile[0]-ox)*metres, -(tile[1]-oy)*metres
            height = ground.top_hit(x, z)
            if height is None:
                raise ValueError(f"{entry['id']}: no standing surface at {tile}")
            entry["serverTile"] = list(tile)
            field = "center" if "center" in entry else "position"
            entry[field] = [round(x, 2), round(height, 2), round(z, 2)]


def apply_runtime(manifest, package):
    """Carry the served roster as a reproducible, explicitly authoritative survey.

    Region design markers keep their lore IDs; this separate roster records the
    actual live NPC, encounter and resource IDs after server placement.
    """
    source = package / 'source/runtime-content.json'
    if source.is_file():
        roster = json.loads(source.read_text(encoding='utf-8'))
        delta = native_tile_delta(manifest, package)
        for bucket in ('npcs', 'resources', 'encounters'):
            for entry in roster.get(bucket, []):
                if 'serverTile' in entry:
                    entry['serverTile'] = [int(entry['serverTile'][i] + delta[i]) for i in (0,1)]
        manifest['runtimePopulation'] = roster
