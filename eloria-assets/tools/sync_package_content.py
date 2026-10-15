#!/usr/bin/env python3
"""Move a package's server-authority markers to where the server puts them.

A map package declares its harvest nodes and NPC markers twice: a `position`
in metres, which is where the client draws the thing, and a `serverTile`,
which is the tile the server runs it on. Entries marked `"authority":
"server"` say outright which of the two decides.

They can disagree. Some of these were authored on tiles the package's own walk
grid blocks - a harvest node a few tiles inside a building - so when the server
started enforcing that collision the node had to move, and the model it is
drawn as stayed behind. The four Four Gates harvestables were fixed this way
before, by hand, and `test_the_four_gates_harvestables_are_where_the_server_puts_them`
was written to hold the two together; this does the same for the rest.

    python eloria-assets/tools/sync_package_content.py [--manifest <path>] [--apply]

The manifest is the server's `config/eloria/client_content_manifest.json`,
which `dev-server/tools/relocate_map_content.py` keeps current. Position moves
with the tile: the horizontal part is exact, and the vertical part follows the
package's own terrain over the distance moved, so a node keeps whatever height
above the ground it was authored with.

The same tool also publishes the digest of each map package:

    python eloria-assets/tools/sync_package_content.py --digests [--apply]

The maps ship with the client, so the server cannot hand one over; what it can
do is say which package it was built against, and it does that by carrying a
`packageSha256` per map in the same manifest. The client hashes the package it
actually has - the same bytes, the same order, the same normalisation, because
this is the value its map cache is keyed on - and says so in the console if
the two disagree. That is all it does: a mismatch is a wrong install, not a
reason to distrust a cache that was keyed locally in the first place.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent
REPO = ASSETS.parent
REGISTRY = REPO / "godot-client" / "data" / "maps" / "registry.json"

#: Wrapped into every package digest so the hash of a map cannot be confused
#: with the hash of anything else, and so the recipe can be revised without
#: colliding with values a previous client wrote. Must stay in step with
#: `MapSceneCache.PACKAGE_DIGEST_VERSION` in the client.
PACKAGE_DIGEST_VERSION = "eloria-map-package-v1"


def four_gates_terrain():
    sys.path.insert(0, str(HERE / "four_gates"))
    import terrain

    field = terrain.TerrainField()
    return lambda x, z: float(np.ravel(field.height(np.array([x]), np.array([z])))[0])


def amberwood_terrain():
    sys.path.insert(0, str(ASSETS / "maps" / "nymara-regions" / "_toolkit"))
    from amberwood import region

    field = region.build_terrain(20260827)
    return lambda x, z: float(np.ravel(field.height_at(np.array([x]), np.array([z])))[0])


# package directory -> (manifest keys it answers, terrain factory)
def sunmane_terrain():
    sys.path.insert(0, str(ASSETS / "maps/nymara-regions/sunmane_steppe/source"))
    import terrain

    import settlement
    landform = terrain.build(pads=settlement.compose_layout(None).pads())
    return lambda x, z: float(np.ravel(landform.sample(
        np.array([x]), np.array([z])))[0])


class Section:
    """One list of markers in a package manifest, and the key it answers.

    `path` walks into the manifest, because a package may declare its markers
    at the top level or nested - Sunmane keeps its under `runtimePopulation` -
    and `position` names the field the placement lives in, which is `position`
    for a point and `center` for something with an extent.
    """

    def __init__(self, manifest_key, path, tile="serverTile", position="position"):
        self.manifest_key = manifest_key
        self.path = path
        self.tile = tile
        self.position = position

    def entries(self, data: dict):
        node = data
        for step in self.path:
            node = node.get(step) if isinstance(node, dict) else None
            if node is None:
                return ()
        return node if isinstance(node, list) else ()


# The markers each package holds that the server decides the tile for. The
# server's content manifest is the list; these say where the package keeps its
# own copy of it.
PACKAGES = {
    "four-gates": (
        [Section("four_gates_harvestables", ("harvestables",))],
        four_gates_terrain,
    ),
    "nymara-regions/amberwood": (
        [Section("amberwood_harvestables", ("harvestables",)),
         Section("amberwood_npcs", ("npcMarkers",), tile="server_tile")],
        amberwood_terrain,
    ),
    "nymara-regions/sunmane_steppe": (
        [Section("sunmane_npcs", ("npcMarkers",)),
         Section("sunmane_resources", ("harvestables",),
                 position="center")],
        sunmane_terrain,
    ),
}


def wanted_tiles(manifest: dict, section: "Section") -> dict[str, tuple[int, int]]:
    """The server's tile for every marker this section is answerable for."""
    out = {}
    for entry in manifest.get(section.manifest_key, ()):
        tile = entry.get(section.tile) or entry.get("serverTile")
        if entry.get("id") and tile and len(tile) == 2:
            out[entry["id"]] = (int(tile[0]), int(tile[1]))
    return out


def sync(package: Path, sections, terrain, manifest: dict, moves: list) -> str | None:
    path = package / "world.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    transform = data["coordinateTransform"]
    origin_x, origin_y = transform["serverOrigin"]
    metres = transform["metresPerTile"]

    ground = None
    if data.get('landscapeRevision'):
        # Compact authored ground no longer follows the old terrain factory.
        # Read the same final surfaces that ground the traveller in the client.
        sys.path.insert(0, str(ASSETS / 'maps/nymara-regions/_toolkit'))
        import glb_reader as geometry
        from verify_runtime import VerticalRayIndex
        document, body = geometry.load(package / 'world.glb')
        names = geometry.named(document, 'Terrain_') + geometry.named(document, 'Walk_')
        index = VerticalRayIndex(geometry.triangles(document, body, names), cell=4)
        def ground(x, z):
            y = index.top_hit(x, z)
            if y is None:
                raise ValueError(f'{package.name}: no authored marker ground at {(x,z)}')
            return y
    changed = False
    for section in sections:
        wanted = wanted_tiles(manifest, section)
        for entry in section.entries(data):
            tile = wanted.get(entry.get("id"))
            if tile is None or list(tile) == list(entry.get("serverTile", ())):
                continue
            placement = entry.get(section.position)
            if not placement or len(placement) != 3:
                continue
            old_x, old_y, old_z = placement
            new_x = (tile[0] - origin_x) * metres
            # invertServerY: the server's y runs north to south.
            new_z = -(tile[1] - origin_y) * metres
            if ground is None:
                ground = terrain()
            # Keep whatever the marker was authored to stand above the ground,
            # and let the ground itself carry it to the new tile.
            new_y = ground(new_x, new_z) if data.get('landscapeRevision') else (
                old_y + ground(new_x, new_z) - ground(old_x, old_z))
            entry[section.position] = [round(new_x, 2), round(new_y, 2),
                                       round(new_z, 2)]
            entry["serverTile"] = [tile[0], tile[1]]
            moves.append((package.name, entry["id"], (old_x, old_z), (new_x, new_z)))
            changed = True
    return json.dumps(data, indent=2) + "\n" if changed else None


def package_digest(manifest_path: Path, glb_path: Path) -> str:
    """sha256 over a map package's own bytes: the glb, then the manifest.

    This is the client's `MapSceneCache.package_digest()`, written twice
    because the two sides have to agree and neither can call the other. The
    manifest is folded to LF before it is hashed: it is a text file that git
    and Python both rewrite the line endings of, so hashing it raw would make
    the same package hash differently in two checkouts and the cross-check
    would report a mismatch that is not one. The glb is binary and is hashed
    exactly as it sits. The server's own catalog digests normalise the same
    way, for the same reason.
    """
    glb_hash = hashlib.sha256(glb_path.read_bytes()).hexdigest()
    manifest_hash = hashlib.sha256(
        manifest_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    return hashlib.sha256(
        f"{PACKAGE_DIGEST_VERSION}\n{glb_hash}\n{manifest_hash}\n".encode()
    ).hexdigest()


def normalize_map_id(value: str) -> str:
    """`MapRegistry.normalize_server_map_id`, in Python.

    The registry tolerates a map named as a path with an extension, because
    the server used to send one. Reducing an id that is already an id is a
    no-op, which is what makes it safe to do to everything.
    """
    normalized = value.strip().replace("\\", "/").lstrip("/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    normalized = normalized.rsplit("/", 1)[-1]
    if "." in normalized:
        normalized = normalized.rsplit(".", 1)[0]
    return normalized.lower()


def resolve_map(maps: dict, map_id: str) -> dict:
    """`MapRegistry.resolve`, in Python: the entry, following any alias."""
    wanted = normalize_map_id(map_id)
    seen: set[str] = set()
    while True:
        key = next((k for k in maps if normalize_map_id(k) == wanted), None)
        if key is None or key in seen:
            return {}
        entry = maps.get(key)
        if not isinstance(entry, dict):
            return {}
        if "alias" not in entry:
            return entry
        seen.add(key)
        wanted = normalize_map_id(str(entry["alias"]))


def registry_packages() -> dict[str, Path]:
    """Every registry id the client ships, and the manifest it resolves to."""
    if not REGISTRY.is_file():
        return {}
    maps = json.loads(REGISTRY.read_text(encoding="utf-8")).get("maps", {})
    out: dict[str, Path] = {}
    for map_id in maps:
        entry = resolve_map(maps, map_id)
        relative = str(entry.get("manifest", ""))
        if not relative:
            continue
        # The registry addresses packages from the Godot project directory.
        path = REPO / "godot-client" / relative.removeprefix("res://")
        try:
            path = path.resolve()
        except OSError:
            continue
        if path.is_file():
            out[map_id] = path
    return out


def digest_for(manifest_path: Path) -> str | None:
    """The digest of the package `manifest_path` heads, or None if it is not
    whole - a manifest whose glb is missing is not a package."""
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    glb = manifest_path.parent / str(data.get("asset", {}).get("glb", ""))
    if not glb.is_file():
        return None
    return package_digest(manifest_path, glb)


def publish_digests(manifest: dict) -> tuple[str | None, list, list, int]:
    """Splices `packageSha256` into every map entry the client has a package
    for, and returns the rewritten manifest, what was set, and what was not.

    Only the maps the server actually runs get a digest, because those are the
    only ones it can ever send one for - the manifest's `maps` list is that
    list, and it is 12 of the 53 packages the client registry knows. The rest
    are hashed anyway, so the count in the report is the truth rather than an
    assumption.
    """
    packages = registry_packages()
    digests = {}
    for map_id, path in packages.items():
        digest = digest_for(path)
        if digest is not None:
            digests[normalize_map_id(map_id)] = digest

    published, missing = [], []
    changed = False
    entries = manifest.get("maps", [])
    for index, entry in enumerate(entries):
        map_id = str(entry.get("id", ""))
        digest = digests.get(normalize_map_id(map_id))
        if digest is None:
            missing.append(map_id)
            continue
        published.append((map_id, digest, entry.get("packageSha256") != digest))
        if entry.get("packageSha256") == digest:
            continue
        # Rebuilt so the digest sits with the other scalars rather than after
        # the portal list; JSON objects keep their insertion order here and the
        # file is read by people.
        rebuilt = {}
        for key, value in entry.items():
            if key == "packageSha256":
                continue  # An existing value must not overwrite the new digest.
            rebuilt[key] = value
            if key == "arrival":
                rebuilt["packageSha256"] = digest
        if "packageSha256" not in rebuilt:
            rebuilt["packageSha256"] = digest
        entries[index] = rebuilt
        changed = True

    text = json.dumps(manifest, indent=2) + "\n" if changed else None
    # Registry ids outnumber packages: several ids are aliases of one, and the
    # interiors of a region share a package between them.
    return text, published, missing, len(set(digests.values()))


def run_digests(path: Path, manifest: dict, apply: bool) -> int:
    text, published, missing, hashed = publish_digests(manifest)
    for map_id, digest, moved in published:
        print(f"[digest] {map_id:24s} {digest}{'  (changed)' if moved else ''}")
    for map_id in missing:
        print(f"[skip  ] {map_id:24s} no package in the client registry",
              file=sys.stderr)
    print(f"[done] {hashed} distinct packages hashed, {len(published)} carried "
          f"by the server's map list, {len(missing)} of its maps with no package")
    if text is None:
        print("[same] every digest in the manifest is already current")
        return 0
    if not apply:
        print("[dry ] nothing written; pass --apply to rewrite the manifest")
        return 0
    path.write_text(text, encoding="utf-8")
    print(f"[write] {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=None,
                        help="the server's config/eloria/client_content_manifest.json")
    parser.add_argument("--digests", action="store_true",
                        help="publish each map's packageSha256 instead of "
                             "moving the packages' markers")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--package", choices=PACKAGES, help="only update this package")
    parser.add_argument("--write-source-posts", action="store_true",
                        help="record stable source tiles for a builder using contentposts.apply")
    args = parser.parse_args()

    path = Path(args.manifest) if args.manifest else (
        REPO.parent / "dev-server" / "config" / "eloria" / "client_content_manifest.json")
    if not path.is_file():
        print(f"cannot find the server content manifest at {path}; pass --manifest",
              file=sys.stderr)
        return 1
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if args.digests:
        return run_digests(path, manifest, args.apply)

    moves: list = []
    written = {}
    for relative, (sections, terrain) in PACKAGES.items():
        if args.package and relative != args.package:
            continue
        package = ASSETS / "maps" / relative
        if args.write_source_posts:
            sys.path.insert(0, str(ASSETS / "maps/nymara-regions/_toolkit"))
            import contentposts
            posts = {".".join(section.path): wanted_tiles(manifest, section) for section in sections}
            data = json.loads((package / "world.json").read_text(encoding="utf-8"))
            delta = contentposts.native_tile_delta(data, package)
            posts = {bucket: {identity: [int(tile[i]-delta[i]) for i in (0,1)]
                              for identity, tile in entries.items()}
                     for bucket, entries in posts.items()}
            if data.get('landscapeRevision'):
                posts['landscapeRevision'] = data['landscapeRevision']
            contentposts.apply(data, package, posts)
            print(f"[posts] {sum(len(entries) for entries in posts.values() if isinstance(entries,dict))} markers for {package.name}")
            text = json.dumps(data, indent=2) + chr(10)
            written[package / "source/server-content.json"] = json.dumps(posts, indent=2) + chr(10)
        else:
            text = sync(package, sections, terrain, manifest, moves)
        if text is not None:
            written[package / "world.json"] = text

    for name, marker, old, new in moves:
        distance = max(abs(new[0] - old[0]), abs(new[1] - old[1]))
        print(f"[move] {name:12s} {marker:24s} "
              f"({old[0]:8.2f}, {old[1]:8.2f}) -> ({new[0]:8.2f}, {new[1]:8.2f})"
              f"  {distance:5.1f} m")
    print(f"[done] {len(moves)} markers in {len(written)} files")
    if not args.apply:
        print("[dry ] nothing written; pass --apply to rewrite the packages")
        return 0
    for target, text in written.items():
        target.write_text(text, encoding="utf-8")
        print(f"[write] {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
