"""Dressing for The Barrow Run (build_trail.py loads this): the shared trail dresser
(_toolkit/trail_dressing.py) over this road's layout.json `dressing` block."""
import trail_dressing as T


def kit_paths(checkout, route_dir):
    return T.kit_paths(checkout, route_dir, _spec(route_dir)["kits"])


def dress(props, layout, lattice, kits, groups, kit_paths_by_key):
    T.dress(layout.data["dressing"], props, layout, lattice, kits, groups, kit_paths_by_key)


def objects(layout, height_at):
    return T.objects(layout, height_at, layout.data["dressing"]["labels"])


def _spec(route_dir):
    import json
    return json.loads((route_dir / "source" / "layout.json").read_text(encoding="utf-8"))["dressing"]
