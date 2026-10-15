"""frames.py: the one frame source of continent v2's served tiles.

  python -B eloria-assets/maps/continent-v2/_continent_v2/frames.py [region ...]        print the checked frames
  python -B eloria-assets/maps/continent-v2/_continent_v2/frames.py tile <region> <x> <z>   a local point's tile

A continent-v2 territory's server frame is chosen once, by the bootstrap (godot-client/tools/
bootstrap_continent_v2_territory.py server_frame: the ownership window plus a 4 m pad, cells rounded up to a multiple
of 6), and copied into four places that the client, the editor and the publishers each read:

  <region>/world.json                    the bootstrap's editor stub: `server` and continentGeography.translation
  regions/<region>/region-authoring-spec.json   `server` and continentTranslation (what the bake records)
  godot-client/data/maps/registry.json   the row's coordinateTransform and continentGeography (what the GAME CLIENT
                                         uses to place every server tile: memory eloria-map-coordinate-transform-source)
  <region>/client/world.json             the published package's coordinateTransform and continentGeography

The copies have drifted on the legacy continent before, silently. load() therefore refuses to hand out a frame unless
all four agree, and everything that turns a position into a served tile (the server rows, the collision export, the
crossings) goes through it. The stub is bootstrap-owned: this module reads it and never writes anything.

The tile rule is the composer's own, authoring.server_tile (eloria-assets/maps/nymara-regions/_continent/authoring.py),
called with the territory's origin:

  tx = floor(x + origin_x)        ty = floor(origin_y - z)        (x, z territory-local metres, z south)
  continent = local + translation

so tile (tx, ty) covers local x in [tx - ox, tx - ox + 1) and z in (oy - ty - 1, oy - ty], and its centre is
(tx - ox + 0.5, oy - ty - 0.5). Row 0 is the south edge of the window. The isle frames put their tile edges on
whole continent metres (translation_x - origin_x and translation_z + origin_y are integers), so a border cell is the
same ground in both neighbours' numbering.

Before first publication, load_source() validates the stub/spec and every registry/package copy that already
exists. A served map still needs all four copies. The ordinary load() remains strict; source loading cannot hide
a disagreeing or missing served copy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace

DEFAULT_CHECKOUT = Path(__file__).resolve().parents[4]
CATALOG = "godot-client/world_authoring/continent-v2/territories.json"
REGISTRY = "godot-client/data/maps/registry.json"
CONTINENT = DEFAULT_CHECKOUT / "eloria-assets" / "maps" / "nymara-regions" / "_continent"
if str(CONTINENT) not in sys.path:
    sys.path.insert(0, str(CONTINENT))
import authoring  # noqa: E402  (the composer's tile rule, imported, never copied)

# The server's limits on a map: square, sides a multiple of 6 (MAP_TILES_WIDE = cells / 6, validate_generated_map),
# and an 11-bit position on the wire.
MAX_CELLS = 2048
CELL_MULTIPLE = 6


class FrameError(ValueError):
    """The copies of a territory's frame disagree, or a point lies outside the served window."""


@dataclass(frozen=True)
class Frame:
    region: str
    label: str
    origin: tuple[int, int]
    cells: tuple[int, int]
    translation: tuple[float, float, float]
    sources: dict = field(default_factory=dict, compare=False)

    # --- the tile rule -----------------------------------------------------------------------------------------
    def tile(self, x: float, z: float) -> tuple[int, int]:
        """The served tile of a territory-local point (authoring.server_tile); refused outside the window."""
        tx, ty = authoring.server_tile([x, 0.0, z], SimpleNamespace(contract=SimpleNamespace(server_origin=self.origin)))
        if not self.contains(tx, ty):
            raise FrameError(f"{self.region}: local ({x}, {z}) is tile ({tx}, {ty}), outside the "
                             f"{self.cells[0]}x{self.cells[1]} window")
        return int(tx), int(ty)

    def tile_of_continent(self, x: float, z: float) -> tuple[int, int]:
        lx, lz = self.to_local(x, z)
        return self.tile(lx, lz)

    def contains(self, tx: int, ty: int) -> bool:
        return 0 <= tx < self.cells[0] and 0 <= ty < self.cells[1]

    # --- conversions -------------------------------------------------------------------------------------------
    def local(self, tx: int, ty: int) -> tuple[float, float]:
        """The tile's centre in territory-local metres."""
        return tx - self.origin[0] + 0.5, self.origin[1] - ty - 0.5

    def continent(self, tx: int, ty: int) -> tuple[float, float]:
        """The tile's centre in continent metres."""
        return self.to_continent(*self.local(tx, ty))

    def to_continent(self, x: float, z: float) -> tuple[float, float]:
        return x + self.translation[0], z + self.translation[2]

    def to_local(self, x: float, z: float) -> tuple[float, float]:
        return x - self.translation[0], z - self.translation[2]

    @property
    def collision_origin(self) -> tuple[float, float]:
        """collisionOriginMetres: the local x of tile column 0's west edge and the local z of row 0's south edge."""
        return float(-self.origin[0]), float(self.origin[1])

    @property
    def lattice(self) -> tuple[float, float]:
        """Continent x of column 0's west edge and continent z of row 0's south edge (edges step by 1 m from them)."""
        return self.translation[0] - self.origin[0], self.translation[2] + self.origin[1]

    def describe(self) -> dict:
        return {"region": self.region, "label": self.label, "origin": list(self.origin), "cells": list(self.cells),
                "translation": list(self.translation), "collisionOriginMetres": list(self.collision_origin),
                "lattice": list(self.lattice), "sources": self.sources}


# --- reading and agreeing --------------------------------------------------------------------------------------------

def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FrameError(f"missing {path}") from None


def _res(resource: str, checkout: Path) -> Path:
    if resource.startswith("res://../"):
        return checkout / resource[len("res://../"):]
    if resource.startswith("res://"):
        return checkout / "godot-client" / resource[len("res://"):]
    return checkout / resource


def _rel(path: Path, checkout: Path) -> str:
    try:
        return path.resolve().relative_to(checkout.resolve()).as_posix()
    except ValueError:
        return str(path)


def _pair(value, kind=float):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        return tuple(kind(v) for v in value)
    except (TypeError, ValueError):
        return None


def catalog_entries(checkout: Path = DEFAULT_CHECKOUT) -> list[dict]:
    return list(_read(Path(checkout) / CATALOG).get("entries", []))


def regions(checkout: Path = DEFAULT_CHECKOUT) -> list[str]:
    return [entry["id"] for entry in catalog_entries(checkout)]


def load(region: str, checkout: Path = DEFAULT_CHECKOUT, *, require_published: bool = True) -> Frame:
    """The territory's frame, refused (FrameError) unless the stub, the authoring spec, the registry row and the
    published manifest agree on origin, cells, translation and the collision origin."""
    checkout = Path(checkout)
    entry = next((e for e in catalog_entries(checkout) if e.get("id") == region), None)
    if entry is None:
        raise FrameError(f"{region} is not in {CATALOG}")
    stub_path = _res(entry["manifestPath"], checkout)
    spec_path = _res(entry["authoringSpecPath"], checkout)
    stub, spec = _read(stub_path), _read(spec_path)
    registry_path = checkout / REGISTRY
    registry = _read(registry_path) if require_published or registry_path.is_file() else {"maps": {}}
    row = registry.get("maps", {}).get(region)
    if row is None and require_published:
        raise FrameError(f"{region} has no row in {REGISTRY}")
    resource = (row or {}).get("manifest") or entry.get("publishedManifestPath", "")
    if not resource:
        raise FrameError(f"{region} has no published manifest path")
    manifest_path = _res(resource, checkout)
    manifest = _read(manifest_path) if require_published or manifest_path.is_file() else None
    served = (row or {}).get("status") == "continent-v2-served" or bool(
        ((manifest or {}).get("collision") or {}).get("servedGrid"))
    if served and (row is None or manifest is None):
        raise FrameError(f"{region}: a served frame needs its registry row and published manifest")
    if row is not None and row.get("manifest") != entry.get("publishedManifestPath"):
        raise FrameError(f"{region}: registry manifest differs from the catalog's published manifest path")

    copies = {}   # name -> (origin, cells, translation, collision origin)
    stub_server = stub.get("server", {})
    copies["stub"] = (_pair(stub_server.get("origin"), int), _pair(stub_server.get("cells"), int),
                      stub.get("continentGeography", {}).get("translation"),
                      _pair(stub_server.get("collisionOriginMetres")))
    spec_server = spec.get("server", {})
    copies["region-authoring-spec"] = (_pair(spec_server.get("origin"), int), _pair(spec_server.get("cells"), int),
                                       spec.get("continentTranslation"),
                                       _pair(spec_server.get("collisionOriginMetres")))
    problems = []
    for name, doc in (("registry row", row), ("published manifest", manifest)):
        if doc is None:
            continue
        ct = doc.get("coordinateTransform", {})
        origin = _pair(ct.get("serverOrigin"), int)
        copies[name] = (origin, _pair(ct.get("serverCells"), int), doc.get("continentGeography", {}).get("translation"),
                        (float(-origin[0]), float(origin[1])) if origin else None)
        if ct.get("metresPerTile") != 1.0 or ct.get("invertServerY") is not True:
            problems.append(f"{name}: metresPerTile {ct.get('metresPerTile')!r} invertServerY "
                            f"{ct.get('invertServerY')!r} (a v2 frame is 1 m tiles, y inverted)")
        if list(ct.get("serverTileMin", [0, 0])) != [0, 0]:
            problems.append(f"{name}: serverTileMin {ct.get('serverTileMin')!r}")
        geo_cells = _pair(doc.get("continentGeography", {}).get("serverCells"), int)
        if name == "registry row" and geo_cells is not None and geo_cells != copies[name][1]:
            problems.append(f"{name}: continentGeography.serverCells {list(geo_cells)} != coordinateTransform "
                            f"serverCells {list(copies[name][1])}")

    def translation_of(value):
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            return None
        try:
            return tuple(float(v) for v in value)
        except (TypeError, ValueError):
            return None

    stub_origin, stub_cells, stub_translation, stub_collision = copies["stub"]
    reference = (stub_origin, stub_cells, translation_of(stub_translation), stub_collision)
    for name, (origin, cells, translation, collision) in copies.items():
        got = (origin, cells, translation_of(translation), collision)
        for label, mine, theirs in zip(("origin", "cells", "translation", "collisionOriginMetres"), got, reference):
            if mine is None:
                problems.append(f"{name}: no {label}")
            elif mine != theirs:
                problems.append(f"{name}: {label} {list(mine)} != the stub's {list(theirs) if theirs else theirs}")
    if None not in reference:
        origin, cells, translation, collision = reference
        if collision != (float(-origin[0]), float(origin[1])):
            problems.append(f"stub: collisionOriginMetres {list(collision)} is not (-origin x, origin y)")
        if cells[0] != cells[1] or cells[0] % CELL_MULTIPLE or not 0 < cells[0] <= MAX_CELLS:
            problems.append(f"stub: cells {list(cells)} (the server needs a square side, a multiple of "
                            f"{CELL_MULTIPLE}, at most {MAX_CELLS})")
        if not all(math.isfinite(v) for v in translation):
            problems.append("stub: continent translation must be finite")
        else:
            lattice = (translation[0] - origin[0], translation[2] + origin[1])
            if any(v != math.floor(v) for v in lattice):
                problems.append("stub: tile edges must fall on whole continent metres")
    if problems:
        raise FrameError(f"{region}: the frame's copies disagree: " + "; ".join(problems))
    sources = {"stub": _rel(stub_path, checkout), "region-authoring-spec": _rel(spec_path, checkout),
               "registry": REGISTRY, "published manifest": _rel(manifest_path, checkout)}
    return Frame(region, str(entry.get("label", region)), reference[0], reference[1], reference[2], sources)


def load_source(region: str, checkout: Path = DEFAULT_CHECKOUT) -> Frame:
    """Validate an unserved bootstrap frame before a package exists; served frames remain strict."""
    return load(region, checkout, require_published=False)


def load_all(checkout: Path = DEFAULT_CHECKOUT) -> dict[str, Frame]:
    return {region: load(region, checkout) for region in regions(checkout)}


def main(argv: list[str]) -> int:
    if argv[:1] == ["tile"]:
        frame = load(argv[1])
        print(json.dumps(list(frame.tile(float(argv[2]), float(argv[3])))))
        return 0
    try:
        frames = [load(r) for r in argv] if argv else list(load_all().values())
    except FrameError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    print(json.dumps({f.region: f.describe() for f in frames}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
