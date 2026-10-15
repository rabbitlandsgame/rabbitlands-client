#!/usr/bin/env python3
"""Join the continent graph to the packages and write the server's portal table.

    python eloria-assets/tools/continent_portals.py --server ../dev-server \
        --maps <dir generate_nymara_maps.py wrote to> [--apply]

`maps/nymara-regions/region-connections.json` says which region touches which
and by which portal id. Each region package's `world.json` says where that
portal stands and which server tile it is, and it says the same of every door
into the region's insides. The insides package says where each door's arrival
is. The server's generated maps say which tiles a player can stand on. This
puts them together:

* every declared link resolves to a portal on both ends, or it is an error;
* each direction becomes `portal | map | x | y | dest | ax | ay` lines;
  reciprocal surveyed roads use a band of lanes that preserves lateral position,
  the trigger on the source portal's tile and the arrival two tiles in from
  the destination portal's tile, on ground the destination map lets a player
  stand on (the arrival is walked inward until it is);
* every door a region declares into its insides map becomes a pair: the
  region's door tile lands on the insides arrival for that door, and that
  arrival tile (where the insides package puts its return portal) lands two
  tiles from the door outside;
* `--apply` rewrites the block of `config/eloria/maps.txt` between its two
  markers, preserving unrelated bootstrap maps, other regions' lines and comments.

Crownwater's quays serve several routes each, so a quay may carry a second
portal a few tiles along the dock; the graph names those with a suffix and the
package declares them as separate portals on separate tiles.

Sunmane's two cave mouths now follow their authored section arrivals and return
posts too. Their previous hand-written links are replaced on scoped publication.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1]
REGIONS = ASSETS / "maps" / "nymara-regions"
INTERIORS = REGIONS / "interiors"
GRAPH = REGIONS / "region-connections.json"
PACKAGES = {"four_gates": ASSETS / "maps" / "four-gates"}
sys.path.insert(0, str(Path(__file__).resolve().parent))
import secret_doors as SD  # noqa: E402
from legacy_content import read_base_only  # noqa: E402

# region -> (insides package directory, the map id the server serves it as)
INSIDES = {
    "sunmane_steppe": ("sunmane_insides", "sunmane_wind_caves"),
    "amethyst_barrens": ("amethyst_barrens_insides", "resonant_vault"),
    "grey_moors": ("grey_moors_insides", "grey_moor_barrows"),
    "westhaven": ("westhaven_insides", "westhaven_insides"),
    "verdant_stair": ("verdant_stair_insides", "verdant_stair_insides"),
    "manymouth_delta": ("manymouth_delta_insides", "manymouth_flooded_labyrinth"),
    "whitehorn_range": ("whitehorn_insides", "whitehorn_glacier_temple"),
    "ssarathi_ruins": ("ssarathi_insides", "ssarathi_royal_archive"),
    "crownwater": ("crownwater_insides", "drowned_crown"),
    "mirrorhold": ("mirrorhold_interiors", "mirrorhold_interiors"),
    # Amberwood's four interiors are separate client packages composed onto
    # one server map; `amberwood_insides/world.json` records where each one's
    # tile origin lands on the composed grid.
    "amberwood": ("amberwood_insides", "amberwood_estate"),
}

BEGIN = "# --- Nymara exterior crossings: written by eloria-assets/tools/continent_portals.py ---"
END = "# --- end of the exterior crossings ---"


def package_dir(region: str) -> Path:
    return PACKAGES.get(region, REGIONS / region)


def read_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def to_tile(position, transform) -> tuple[int, int]:
    origin = transform["serverOrigin"]
    metres = float(transform.get("metresPerTile", 1.0))
    x, _, z = position
    return int(round(x / metres + origin[0])), int(round(origin[1] - z / metres))


def load_portals(region: str) -> dict[str, dict]:
    manifest = read_manifest(package_dir(region) / "world.json")
    transform = manifest["coordinateTransform"]
    out = {}
    entries = list(manifest.get("portals", []))
    # Sunmane declares its transitions among its interactives
    entries += [e for e in manifest.get("interactives", []) if e.get("kind") == "portal"]
    for entry in entries:
        if "id" not in entry:
            continue
        tile = entry.get("serverTile")
        if tile is None and entry.get("position"):
            tile = to_tile(entry["position"], transform)
        if tile is None:
            continue
        out[entry["id"]] = {"tile": (int(tile[0]), int(tile[1])),
                            "name": entry.get("name") or entry.get("label") or entry["id"],
                            "destination": entry.get("destinationMap") or entry.get("destination") or entry.get("targetMap"),
                            "spawn": entry.get("destinationSpawn") or entry.get("targetSpawn"),
                            "streaming": next((s for s in manifest.get("streamingBorders", [])
                                               if s["portal"] == entry["id"]), {})}
    return out


def load_arrivals(package: str) -> dict[str, tuple[int, int]]:
    """Spawn id -> server tile, for an insides package."""
    manifest = read_manifest(INTERIORS / package / "world.json")
    transform = manifest["coordinateTransform"]
    return {s["id"]: to_tile(s["position"], transform) for s in manifest.get("spawnPoints", [])}


def load_composed_arrivals(package: str) -> dict[str, dict[str, tuple[int, int]]]:
    """Amberwood: per sub-package, spawn id -> tile on the composed map."""
    manifest = read_manifest(INTERIORS / package / "world.json")
    out = {}
    for section in manifest.get("sections", []):
        sub = section["package"]
        base = section["serverTile"]
        sub_manifest = read_manifest(INTERIORS / sub / "world.json")
        transform = sub_manifest["coordinateTransform"]
        out[sub] = {}
        for spawn in sub_manifest.get("spawnPoints", []):
            tx, ty = to_tile(spawn["position"], transform)
            out[sub][spawn["id"]] = (int(base[0]) + tx, int(base[1]) + ty)
    return out


def load_collision(server: Path, maps_dir: Path, map_id: str):
    # The legacy crossing block is laid from the base map table only, never the continent-v2 overlay (serve plan
    # CV13): an isle portal arriving on a legacy map is not one of this tool's links.
    read_base_only(server)
    sys.path.insert(0, str(server))
    from eloria.collision import load_elm_collision, with_step_mask
    from eloria.maps import load_maps
    maps, _ = load_maps(str(server / "config" / "eloria" / "maps.txt"))
    return with_step_mask(load_elm_collision(maps_dir / maps[map_id].file), 2)


def arrival_tile(collision, tile, inward, minimum: int = 2, limit: int = 12):
    """The first walkable tile at least `minimum` steps in from the portal."""
    x, y = tile
    dx, dy = inward
    for step in range(minimum, limit + 1):
        ax, ay = x + dx * step, y + dy * step
        if collision.walkable(ax, ay):
            return ax, ay
        # a step to either side, for a portal on a diagonal road
        for sx, sy in ((dy, -dx), (-dy, dx)):
            if collision.walkable(ax + sx, ay + sy):
                return ax + sx, ay + sy
    return None


def nearest_open(collision, tile, minimum: int = 0, limit: int = 4):
    """The nearest walkable tile between `minimum` and `limit` steps out."""
    x, y = tile
    for radius in range(minimum, limit + 1):
        ring = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) == radius:
                    ring.append((x + dx, y + dy))
        # closest to the tile first, then a stable order
        ring.sort(key=lambda t: ((t[0] - x) ** 2 + (t[1] - y) ** 2, t))
        for candidate in ring:
            if collision.walkable(*candidate):
                return candidate
    return None


def inward_direction(tile, cells: int) -> tuple[int, int]:
    """Towards the map's centre, along whichever axis the portal is nearest an edge."""
    x, y = tile
    centre = cells / 2.0
    if min(x, cells - x) <= min(y, cells - y):
        return (1 if x < centre else -1), 0
    return 0, (1 if y < centre else -1)


def exterior_lines(graph, portals, collisions, load, errors, selected=None) -> tuple[list[str], int]:
    lines = ["# Directions and surveyed road lanes from region-connections.json. The",
             "# trigger is the package's portal tile; the arrival is the first tile a",
             "# player can stand on, two or more tiles in from the far portal, so a",
             "# crossing never lands anyone back on the tile that sent them.", ""]
    written = 0
    for link in graph["connections"]:
        if selected and selected not in (link["from"], link["to"]):
            continue
        pairs = ((link["from"], link["from_portal"], link["to"], link["to_portal"]),
                 (link["to"], link["to_portal"], link["from"], link["from_portal"]))
        lines.append(f"# {link['from']} <-> {link['to']} ({link['type']}): {link.get('note', '')}")
        for source, source_portal, destination, destination_portal in pairs:
            for region in (source, destination):
                if region not in portals:
                    portals[region] = load_portals(region)
                    collisions[region] = load(region)
            if source_portal not in portals[source]:
                errors.append(f"{source} has no portal {source_portal!r}")
                continue
            if destination_portal not in portals[destination]:
                errors.append(f"{destination} has no portal {destination_portal!r}")
                continue
            trigger = portals[source][source_portal]["tile"]
            far = portals[destination][destination_portal]["tile"]
            if not collisions[source].walkable(*trigger):
                errors.append(f"{source} portal {source_portal} trigger {trigger} is not walkable")
            frame=portals[destination][destination_portal].get('streaming', {})
            inward=(-frame['outward'][0],frame['outward'][1]) if frame else inward_direction(far,collisions[destination].width)
            arrival = arrival_tile(collisions[destination], far, inward)
            if arrival is None:
                errors.append(f"{destination} portal {destination_portal} at {far}: no walkable arrival")
                continue
            a = portals[source][source_portal].get('streaming', {})
            b = portals[destination][destination_portal].get('streaming', {})
            width = min(a.get('halfWidthTiles', 0), b.get('halfWidthTiles', 0)) if a and b and a['id'] == b['id'] else 0
            # A surveyed road crosses across its whole width, maintaining the
            # traveller's lateral position. The opposite frame reverses sides.
            sa = (-a['outward'][1], -a['outward'][0]) if width else (0, 0)
            sb = (-b['outward'][1], -b['outward'][0]) if width else (0, 0)
            for offset in range(-width, width + 1):
                start = (trigger[0] + offset * sa[0], trigger[1] + offset * sa[1])
                end = (arrival[0] - offset * sb[0], arrival[1] - offset * sb[1])
                if not collisions[source].walkable(*start) or not collisions[destination].walkable(*end):
                    errors.append(f'{source} streaming lane {offset} has blocked trigger/arrival {start}/{end}')
                    continue
                lines.append(f"portal | {source} | {start[0]} | {start[1]} | {destination} | {end[0]} | {end[1]}")
                written += 1
        lines.append("")
    return lines, written


def interior_lines(portals, collisions, load, errors, selected=None) -> tuple[list[str], int]:
    lines = ["# --- the doors: one pair per door a region declares into its insides map ---",
             "# The region's door tile lands on the insides arrival the door names, and",
             "# that arrival tile - where the insides package puts its return portal -",
             "# lands two tiles from the door outside. Combined insides maps carry every",
             "# section of a region on one map; which section you get is which door you",
             "# used.", ""]
    written = 0
    for region, (package, map_id) in INSIDES.items():
        if selected and region != selected:
            continue
        if region not in portals:
            portals[region] = load_portals(region)
            collisions[region] = load(region)
        if map_id not in collisions:
            collisions[map_id] = load(map_id)
        composed = None
        arrivals = None
        if region == "amberwood":
            composed = load_composed_arrivals(package)
        else:
            arrivals = load_arrivals(package)
        accepted = {map_id, package} | (set(composed) if composed else set())
        doors = [(pid, p) for pid, p in portals[region].items() if p["destination"] in accepted]
        lines.append(f"# {region} <-> {map_id} ({len(doors)} doors)")
        for door_id, door in sorted(doors):
            spawn = door["spawn"] or "default"
            table = composed[door["destination"]] if composed else arrivals
            if spawn not in table:
                errors.append(f"{region} door {door_id}: insides has no arrival {spawn!r}")
                continue
            inside = table[spawn]
            if not collisions[map_id].walkable(*inside):
                moved = nearest_open(collisions[map_id], inside, 1, 2)
                if moved is None:
                    errors.append(f"{map_id} arrival {spawn} at {inside} is not walkable")
                    continue
                inside = moved
            trigger = door["tile"]
            if not collisions[region].walkable(*trigger):
                moved = nearest_open(collisions[region], trigger, 1, 2)
                if moved is None:
                    errors.append(f"{region} door {door_id} at {trigger} is not walkable")
                    continue
                trigger = moved
            exit_tile=inside
            outside = nearest_open(collisions[region], trigger, 2, 5)
            if region=='sunmane_steppe':
                room=read_manifest(INTERIORS/package/'world.json')
                exit_=next((p for p in room['portals'] if p['id']=='exit-'+spawn),None)
                if exit_ is None or 'destinationTile' not in exit_:
                    errors.append(f'{region} door {door_id}: missing authored return');continue
                exit_tile=tuple(exit_.get('serverTile') or to_tile(exit_['position'],room['coordinateTransform']))
                outside=tuple(exit_['destinationTile'])
                if not collisions[map_id].walkable(*exit_tile) or not collisions[region].walkable(*outside):
                    errors.append(f'{region} door {door_id}: blocked authored return {exit_tile}/{outside}');continue
            if outside is None:
                errors.append(f"{region} door {door_id}: no open ground within five tiles")
                continue
            lines.append(f"portal | {region} | {trigger[0]} | {trigger[1]} | {map_id} | "
                         f"{inside[0]} | {inside[1]}")
            lines.append(f"portal | {map_id} | {exit_tile[0]} | {exit_tile[1]} | {region} | "
                         f"{outside[0]} | {outside[1]}")
            written += 2
        lines.append("")
    standalone, count = standalone_interior_lines(portals, collisions, load, errors, selected)
    return lines + standalone, written + count


def standalone_interior_lines(portals, collisions, load, errors, selected=None):
    """Four Gates' named shops are separate authored rooms with real exit doors."""
    if selected and selected != 'four_gates':
        return [], 0
    region='four_gates'
    portals.setdefault(region, load_portals(region))
    if region not in collisions:
        collisions[region]=load(region)
    outside_manifest=read_manifest(package_dir(region)/'world.json')
    lines=['# Four Gates: standalone shops, workrooms and the ferry office.']
    written=0
    for door_id,door in sorted(portals[region].items()):
        map_id=door['destination']
        if not map_id or not map_id.startswith('four-gates-'):
            continue
        path=ASSETS/'maps'/map_id/'world.json'
        room=read_manifest(path)
        if not room.get('asset',{}).get('interior'):
            errors.append(f'{door_id}: target {map_id} is not an authored interior')
            continue
        if map_id not in collisions:
            collisions[map_id]=load(map_id)
        spawn=next((s for s in room.get('spawnPoints',[]) if s['id']==door['spawn']),None)
        exit_=next((p for p in room.get('portals',[]) if p.get('id')=='exit'),None)
        if not spawn or not exit_ or not exit_.get('targetPosition'):
            errors.append(f'{map_id}: missing named arrival or explicit exterior return')
            continue
        arrival=to_tile(spawn['position'],room['coordinateTransform'])
        exit_tile=to_tile(exit_['position'],room['coordinateTransform'])
        outside=to_tile(exit_['targetPosition'],outside_manifest['coordinateTransform'])
        trigger=door['tile']
        posts=((region,trigger,'entrance'),(map_id,arrival,'arrival'),
               (map_id,exit_tile,'exit'),(region,outside,'return'))
        if any(not collisions[m].walkable(*tile) for m,tile,_ in posts):
            errors.extend(f'{door_id}: blocked {label} {m} {tile}' for m,tile,label in posts
                          if not collisions[m].walkable(*tile))
            continue
        if arrival==exit_tile or outside==trigger:
            errors.append(f'{door_id}: arrival overlaps its return trigger')
            continue
        lines.extend([f'portal | {region} | {trigger[0]} | {trigger[1]} | {map_id} | {arrival[0]} | {arrival[1]}',
                      f'portal | {map_id} | {exit_tile[0]} | {exit_tile[1]} | {region} | {outside[0]} | {outside[1]}'])
        written+=2
    return lines, written


def secret_lines(collisions, load, errors, link_proofs=None) -> tuple[list[str], int]:
    """Entrances, exits and links of every `<region>_secrets` map.

    An entrance is a portal bound to the object a player uses (the eighth
    field is the object id), so it fires only for the player who used it; its
    trigger is the first walkable tile beside the prop. A section's exit is
    its arrival tile, back to that trigger. A stone or a tunnel end is a link
    onto another secrets map's spawn, or back up beside a mouth on a region.
    """
    lines = ["# --- the secrets: use-to-enter doors bound to their objects ---",
             "# `portal | map | object | x | y | dest | ax | ay`: a portal with an object",
             "# id fires only for the player who used that object, so a secret stays",
             "# secret from anyone walking over its tile. Written from the packages by",
             "# eloria-assets/tools/secret_doors.py; the same tool numbers the objects",
             "# the content tool declares in interactives.txt.", ""]
    manifests = SD.secrets_manifests(ASSETS)
    entrances = SD.entrances(ASSETS)
    written = 0

    def walkable(map_id):
        if map_id not in collisions:
            collisions[map_id] = load(map_id)
        return collisions[map_id].walkable

    triggers: dict[tuple[str, str], tuple[int, int]] = {}
    for map_id, records in sorted(entrances.items()):
        for entrance in records:
            spot = SD.nearest_open(walkable(map_id), entrance.tile, 1, 3)
            if spot is None:
                errors.append(f"{map_id} secret {entrance.id}: no walkable tile beside {entrance.tile}")
                continue
            triggers[(map_id, entrance.id)] = spot

    def arrival_for(target_map: str, spawn: str):
        if target_map in manifests:
            tile = SD.spawn_tile(manifests[target_map], spawn)
            if tile is None:
                return None
            if not walkable(target_map)(*tile):
                tile = SD.nearest_open(walkable(target_map), tile, 1, 2)
            return tile
        return triggers.get((target_map, spawn))

    for map_id, records in sorted(entrances.items()):
        lines.append(f"# {map_id}: {len(records)} entrances")
        for entrance in records:
            trigger = triggers.get((map_id, entrance.id))
            if trigger is None:
                continue
            arrival = arrival_for(entrance.destination, entrance.spawn)
            if arrival is None:
                errors.append(f"{map_id} secret {entrance.id}: {entrance.destination} has no arrival {entrance.spawn!r}")
                continue
            lines.append(f"portal | {map_id} | {entrance.object_id} | {trigger[0]} | {trigger[1]} | "
                         f"{entrance.destination} | {arrival[0]} | {arrival[1]}")
            written += 1
        lines.append("")
    for secrets_map, manifest in sorted(manifests.items()):
        lines.append(f"# {secrets_map}: exits and links")
        floor=None
        for section in SD.sections(manifest):
            back = triggers.get((section["entranceMap"], f"secret-{section['id']}"))
            if back is None:
                errors.append(f"{secrets_map} section {section['id']}: no entrance on {section['entranceMap']}")
            else:
                ax, ay = section["arrivalTile"]
                lines.append(f"portal | {secrets_map} | {ax} | {ay} | {section['entranceMap']} | {back[0]} | {back[1]}")
                written += 1
            reserved={tuple(e['tile']) for e in section.get('exits',[])}
            reserved.add(tuple(section['arrivalTile']))
            for exit_ in section.get("exits", []):
                target = arrival_for(exit_["map"], exit_["spawn"])
                if target is None:
                    errors.append(f"{secrets_map} section {section['id']}: link to {exit_['map']}/{exit_['spawn']} has no arrival")
                    continue
                from secret_link_access import RoomFloor,select_link
                walkable(secrets_map)  # Load the actual served staged ELM.
                if floor is None:floor=RoomFloor(INTERIORS/secrets_map/manifest['asset']['glb'],manifest)
                try:
                    (ex,ey),proof=select_link(collisions[secrets_map],section['arrivalTile'],exit_['tile'],
                                              floor,forbidden=reserved)
                except ValueError as error:
                    errors.append(f"{secrets_map} section {section['id']}: {error}");continue
                reserved.add((ex,ey))
                if link_proofs is not None:link_proofs.append({'map':secrets_map,'section':section['id'],
                    'destinationMap':exit_['map'],'destinationSpawn':exit_['spawn'],**proof})
                lines.append(f"portal | {secrets_map} | {ex} | {ey} | {exit_['map']} | {target[0]} | {target[1]}")
                written += 1
        lines.append("")
    return lines, written


def remove_legacy_cave_links(text):
    """Replace only the four old ordinary Sunmane links, keeping map definitions."""
    kept=[]
    for line in text.splitlines(keepends=True):
        fields=[part.strip() for part in line.split('|')]
        if len(fields)==7 and fields[0]=='portal' and {fields[1],fields[4]}=={'sunmane_steppe','sunmane_wind_caves'}:
            continue
        kept.append(line)
    return ''.join(kept)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--maps", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument('--report',type=Path,help='Write exact secret-link publication choices and physical evidence')
    parser.add_argument("--region", choices=sorted(set(INSIDES) | {"sunmane_steppe", "four_gates"}),
                        help="rebuild this region and both ends of its links only")
    args = parser.parse_args()

    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    portals: dict[str, dict] = {}
    collisions: dict[str, object] = {}
    errors: list[str] = []

    def load(map_id: str):
        return load_collision(args.server, args.maps, map_id)

    lines = [BEGIN]
    outside, crossings = exterior_lines(graph, portals, collisions, load, errors, args.region)
    inside, doors = interior_lines(portals, collisions, load, errors, args.region)
    link_proofs=[]
    hidden, secrets = secret_lines(collisions, load, errors, link_proofs)
    lines += outside + inside + hidden + [END]
    for error in errors:
        print("ERROR", error)
    if args.report:args.report.write_text(json.dumps({'errors':errors,'secretLinks':link_proofs},indent=2)+'\n',encoding='utf-8')
    print(f"{crossings} crossing lines from {len(graph['connections'])} links, {doors} door lines, "
          f"{secrets} secret lines")
    if errors:
        return 1
    block = "\n".join(lines)
    maps_txt = args.server / "config" / "eloria" / "maps.txt"
    text = maps_txt.read_text(encoding="utf-8")
    if args.region in (None,'sunmane_steppe'):
        text=remove_legacy_cave_links(text)
    if BEGIN in text and END in text:
        head = text[:text.index(BEGIN)]
        tail = text[text.index(END) + len(END):]
        new_text = head + block + tail
    else:
        new_text = text.rstrip("\n") + "\n\n" + block + "\n"
    if args.region:
        chosen = {args.region, args.region + "_secrets"}
        if args.region in INSIDES:
            chosen.add(INSIDES[args.region][1])
        def belongs(line):
            fields = [part.strip() for part in line.split("|")]
            if not fields or fields[0] != "portal":
                return False
            return (len(fields) == 7 and bool({fields[1], fields[4]} & chosen)
                    or len(fields) == 8 and bool({fields[1], fields[5]} & chosen))
        # Keep the rest of the continent's authored block byte-for-byte in
        # meaning. Every incoming/outgoing selected link is replaced together.
        old_block = text[text.index(BEGIN):text.index(END)]
        kept = [line for line in old_block.splitlines() if not belongs(line)]
        selected_lines = [line for line in lines if belongs(line)]
        block = "\n".join(kept + selected_lines + [END])
        new_text = text[:text.index(BEGIN)] + block + text[text.index(END) + len(END):]
    if args.apply:
        maps_txt.write_text(new_text, encoding="utf-8", newline="\n")
        print(f"wrote {maps_txt}")
    else:
        print(block)
    return 0


if __name__ == "__main__":
    sys.exit(main())
