"""publish_links.py: give the game client's streaming graph the isles' land links.

  python -B eloria-assets/maps/continent-v2/_continent_v2/publish_links.py [--check] [--checkout <worktree>]

The client streams a neighbour across a seam only where its streaming graph links the two maps
(src/world/exterior_region_stream.gd). Its graph is godot-client/data/maps/exterior_connections.json, which the
legacy continent publisher writes whole from its own publication (eloria-assets/tools/publish_diagonal_continent.py)
together with the server's config/eloria/exterior_connections.json, and which the legacy walk proof
(generate_continent_walk_proof.py) and continent audit (_continent/audit_continent.py) require to equal the server's
copy byte for byte. So the isles' links do not go into it: a legacy republication would drop them (serve plan D8), and
with them in it the legacy proof and audit fail.

They go into a file of their own, godot-client/data/maps/exterior_connections-continent-v2.json, which the stream
reads after the legacy graph: crossings.json's exteriorConnections (crossings_v2.py; the entries publish_server.py
writes into the server's overlay, config/eloria/continent-v2/exterior_connections.json) under the distances the
client uses for every link, serialized as the legacy publisher serializes (publish_continent_geography.json_bytes:
indent 2, ensure_ascii False, LF).

It refuses, writing nothing:
- crossings.json whose distances (exteriorSettings) are not the legacy graph's: the stream has one set for every link;
- crossings.json made from another served grid than the one a package ships (inputs.maps.<region>.servedGridSha256
  against the package's collision.servedGrid.sha256): run crossings_v2.py again first;
- a link whose end names a map with no continent-v2-served registry row, or whose frame translation is not the
  registry row's continentGeography.translation (the stream places the neighbour by it);
- a legacy graph that already links a continent-v2 map (the stream would hold two links for one seam).

--check exits 1 when the file differs from what this tool writes; godot-client/tests/test_continent_v2_links.py runs it.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

DEFAULT_CHECKOUT = Path(__file__).resolve().parents[4]
CATALOG = "godot-client/world_authoring/continent-v2/territories.json"
REGISTRY = "godot-client/data/maps/registry.json"
LEGACY_LINKS = "godot-client/data/maps/exterior_connections.json"
CLIENT_LINKS = "godot-client/data/maps/exterior_connections-continent-v2.json"
CROSSINGS = "eloria-assets/maps/continent-v2/_continent_v2/crossings.json"
SERVED_STATUS = "continent-v2-served"


class LinksError(ValueError):
    """An input disagrees with another, or a graph holds a link this tool cannot place."""


def read_json(path: Path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def json_bytes(data, checkout: Path) -> bytes:
    """The legacy publisher's serializer (publish_continent_geography.json_bytes), imported from the checkout."""
    tools = str(Path(checkout) / "eloria-assets" / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import publish_continent_geography as shared
    return shared.json_bytes(data)


def res_path(checkout: Path, resource: str) -> Path:
    if not resource.startswith("res://../"):
        raise LinksError(f"not a checkout resource path: {resource}")
    return checkout / resource[len("res://../"):]


def compose(checkout: Path = DEFAULT_CHECKOUT) -> tuple[bytes, dict]:
    """What the isles' links file should hold, and a report of it."""
    checkout = Path(checkout)
    v2_maps = [entry["id"] for entry in read_json(checkout / CATALOG)["entries"]]
    rows = read_json(checkout / REGISTRY).get("maps", {})
    crossings = read_json(checkout / CROSSINGS)
    legacy = read_json(checkout / LEGACY_LINKS)
    settings = dict(crossings["exteriorSettings"])
    for key, value in settings.items():
        if legacy.get(key) != value:
            raise LinksError(f"{LEGACY_LINKS} {key} is {legacy.get(key)!r}, crossings.json's exteriorSettings "
                             f"{value!r}: the stream has one value for every link")
    for link in legacy.get("connections", []) + legacy.get("visualConnections", []):
        touched = [end.get("map") for end in link.get("ends", []) if end.get("map") in v2_maps]
        if touched:
            raise LinksError(f"{LEGACY_LINKS} already links {touched} ({link.get('id')!r}): the stream would hold "
                             f"two links for one seam")
    for region, recorded in crossings["inputs"]["maps"].items():
        row = rows.get(region)
        if not row:
            raise LinksError(f"crossings.json crosses into {region}, which has no registry row")
        package = read_json(res_path(checkout, row["manifest"]))
        shipped = ((package.get("collision") or {}).get("servedGrid") or {}).get("sha256")
        if shipped != recorded.get("servedGridSha256"):
            raise LinksError(f"crossings.json was made from {region}'s served grid {recorded.get('servedGridSha256')}, "
                             f"but its package ships {shipped}: run crossings_v2.py again")
    links = list(crossings["exteriorConnections"])
    for link in links:
        for end in link["ends"]:
            row = rows.get(end["map"]) or {}
            if row.get("status") != SERVED_STATUS:
                raise LinksError(f"{link['id']}: {end['map']} has no {SERVED_STATUS} registry row, so the client "
                                 f"would stream a map it cannot travel to")
            want = [float(v) for v in (row.get("continentGeography") or {}).get("translation") or []]
            have = [float(v) for v in (end.get("frame") or {}).get("globalTranslation") or []]
            if want != have:
                raise LinksError(f"{link['id']}: {end['map']}'s frame translation {have} is not its registry row's "
                                 f"{want}")
    data = {**settings, "generator": "eloria-assets/maps/continent-v2/_continent_v2/publish_links.py",
            "connections": links}
    return json_bytes(data, checkout), {"links": [link["id"] for link in links]}


def check(checkout: Path = DEFAULT_CHECKOUT) -> list[str]:
    """[] when the isles' links file is what this tool writes, else why not."""
    try:
        wanted, _report = compose(checkout)
    except LinksError as error:
        return [str(error)]
    path = Path(checkout) / CLIENT_LINKS
    if not path.is_file():
        return [f"{CLIENT_LINKS} is missing; run _continent_v2/publish_links.py"]
    if path.read_bytes() != wanted:
        return [f"{CLIENT_LINKS} is not crossings.json's links; run _continent_v2/publish_links.py"]
    return []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 when the file is not what this tool writes")
    ap.add_argument("--checkout", type=Path, default=DEFAULT_CHECKOUT)
    args = ap.parse_args(argv)
    if args.check:
        problems = check(args.checkout)
        for problem in problems:
            print(problem)
        return 1 if problems else 0
    try:
        wanted, report = compose(args.checkout)
    except LinksError as error:
        print(f"refused: {error}")
        return 1
    path = args.checkout / CLIENT_LINKS
    before = path.read_bytes() if path.is_file() else b""
    if before != wanted:
        path.write_bytes(wanted)
    print(json.dumps({**report, "changed": before != wanted, "bytes": len(wanted)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
