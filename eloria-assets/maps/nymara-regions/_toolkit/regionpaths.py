"""Locating a region package from a toolkit script.

The toolkit used to live inside `amberwood/source/`, so every script could
assume `Path(__file__).parent.parent` was the region package. It now lives in
`_toolkit/`, shared by every region, so the package has to be named instead of
inferred from the script's own location.

Resolution order: an explicit `--package`, then `$NYMARA_REGION_PACKAGE`, then
the nearest enclosing directory that looks like a region package (one holding a
`world.json`), starting from the working directory.
"""
from __future__ import annotations

import os
from pathlib import Path

TOOLKIT = Path(__file__).resolve().parent
REGIONS = TOOLKIT.parent


def looks_like_package(path: Path) -> bool:
    return (path / "world.json").is_file()


def package_root(explicit: str | os.PathLike | None = None) -> Path:
    """Return the region package directory, or raise with a usable message."""
    if explicit:
        path = Path(explicit).resolve()
        if not path.is_dir():
            raise SystemExit(f"--package is not a directory: {path}")
        return path

    env = os.environ.get("NYMARA_REGION_PACKAGE")
    if env:
        return Path(env).resolve()

    here = Path.cwd().resolve()
    for candidate in (here, *here.parents):
        if candidate == REGIONS:
            break
        if looks_like_package(candidate):
            return candidate

    raise SystemExit(
        "cannot tell which region package to act on: run from inside one, "
        "pass --package <dir>, or set NYMARA_REGION_PACKAGE")


def region_source(package: Path) -> Path:
    """The region's own build sources, which the toolkit imports for VIEWS etc."""
    return package / "source"


def load_region_views(package: Path):
    """Import the region's `source/views.py`.

    VIEWS (camera set) and PANELS (detail-board panel -> capture mapping) are
    per-region data, not toolkit data, so they live with the region that owns
    them. Kept out of the toolkit so a new region does not have to edit it.
    """
    import importlib.util

    path = region_source(package) / "views.py"
    if not path.is_file():
        raise SystemExit(f"region has no camera/panel table: {path}")
    spec = importlib.util.spec_from_file_location(
        f"_region_views_{package.name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_module(path: Path, name: str):
    import importlib.util
    import sys

    source = path.parent
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_region_plan(package: Path):
    """The region's plan module: extents, anchors, routes, terrain sculpting.

    A region authored after the toolkit extraction keeps this in its own
    `source/region.py`. Amberwood predates that and still has its plan inside
    the shared package, reached through its build module's `REG`, so fall back
    to that rather than failing on the older layout.
    """
    path = region_source(package) / "region.py"
    if path.is_file():
        return _load_module(path, "region")
    plan = getattr(load_region_build(package), "REG", None)
    if plan is None:
        raise SystemExit(
            f"region has no plan: expected {path}, and its build module "
            f"exposes no REG")
    return plan


def load_region_build(package: Path):
    """Import the region's own `build_<region>.py`.

    The toolkit cannot know its name, and a region may carry more than one
    build script, so the interior builds are excluded and the rest must be
    unambiguous.

    `build_insides` as well as `build_interior`: the single-map interiors layout
    added a third script per region, and excluding only the older name leaves
    two candidates and makes every toolkit script that resolves a region fail.
    Crownwater is in that state on develop - `export_source_elm.py` cannot run
    against it - and Ssarathi Ruins would have been the moment it gained its own
    insides build.
    """
    source = region_source(package)
    interior_prefixes = ("build_interior", "build_insides")
    candidates = [c for c in sorted(source.glob("build_*.py"))
                  if not c.stem.startswith(interior_prefixes)]
    if len(candidates) != 1:
        raise SystemExit(
            f"expected exactly one build_*.py in {source}, found "
            f"{[c.name for c in candidates]}")
    return _load_module(candidates[0], candidates[0].stem)
