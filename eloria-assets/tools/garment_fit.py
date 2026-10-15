#!/usr/bin/env python3
"""Does a garment actually contain the body inside it?

Skin poking through a garment is invisible in a wireframe, obvious on a player
and impossible to settle by eye at sixty-four designs, so it is measured here
instead.  For every body vertex under the garment the question is whether the
point lies inside the garment's shell, answered by ray-cast parity: a ray from
an enclosed point crosses a closed surface an odd number of times.

Nothing here is specific to footwear: a shell is a shell, and a trouser leg
poking a knee out through its side fails the same test a boot does.  Callers
scope *which* body vertices a piece is answerable for by passing a region.

**The trap this module exists to avoid.**  A garment is not one closed volume.
A boot's shaft and its foot shell are two overlapping closed volumes living in
a single glTF primitive, and a point inside *both* of them is crossed an even
number of times by any ray, so whole-primitive parity reports it as outside.
Run that way the shell this replaces reports a hundred and forty-two vertices
poking through when fourteen actually do.  Each primitive is therefore split
into connected components - union-find over edges welded by position - and a
point counts as enclosed when it is inside *any* closed component.  The same
applies to a trouser: two legs and a seat are three volumes, not one.
"""
from __future__ import annotations

import argparse
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

WELD = 5           # decimal places positions are welded at
RIM_MARGIN = .001  # how far under the rim the covered region starts, in metres


# ---------------------------------------------------------------------------
# glTF reading
# ---------------------------------------------------------------------------

def _document(path: Path) -> tuple[dict, bytes]:
    raw = Path(path).read_bytes()
    json_size = struct.unpack_from("<I", raw, 12)[0]
    document = json.loads(raw[20:20 + json_size])
    offset = 20 + json_size
    binary_size = struct.unpack_from("<I", raw, offset)[0]
    return document, raw[offset + 8:offset + 8 + binary_size]


_DTYPES = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2",
           5125: "<u4", 5126: "<f4"}
_WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def mesh_primitives(path: Path, names: set[str] | None = None):
    """POSITION and triangle arrays of every primitive, optionally by mesh name."""
    document, binary = _document(path)

    def read(index: int) -> np.ndarray:
        spec = document["accessors"][index]
        view = document["bufferViews"][spec["bufferView"]]
        dtype = np.dtype(_DTYPES[spec["componentType"]])
        width = _WIDTHS[spec["type"]]
        start = view.get("byteOffset", 0) + spec.get("byteOffset", 0)
        stride = view.get("byteStride", dtype.itemsize * width)
        shape = (spec["count"],) if width == 1 else (spec["count"], width)
        strides = (stride,) if width == 1 else (stride, dtype.itemsize)
        return np.ndarray(shape, dtype=dtype, buffer=binary, offset=start,
                          strides=strides).copy()

    for mesh in document.get("meshes", []):
        if names is not None and str(mesh.get("name", "")) not in names:
            continue
        for primitive in mesh["primitives"]:
            yield (read(primitive["attributes"]["POSITION"]).astype(np.float64),
                   read(primitive["indices"]).astype(np.int64).reshape(-1, 3))


def mesh_names(path: Path) -> list[str]:
    document, _ = _document(path)
    return [str(mesh.get("name", "")) for mesh in document.get("meshes", [])]


def body_points(path: Path) -> np.ndarray:
    """The wearer's own skin: the body mesh, never what it is already wearing.

    A race GLB carries its wardrobe as extra skinned surfaces.  Measuring those
    would ask whether the boot covers the *other* boot painted on the body,
    which is not the question and which no boot can answer.
    """
    names = {name for name in mesh_names(path) if name.lower() == "body"}
    chunks = [points for points, _ in mesh_primitives(path, names or None)]
    if not chunks:
        raise ValueError(f"{path} has no body mesh")
    # Welded by position: a body mesh splits its vertices along every UV seam,
    # and a place where skin shows through is one place however many indices
    # the exporter gave it.  Counting indices instead reports the same hole two
    # or three times and makes one design look worse than another for no reason
    # but its seam layout.
    return np.unique(np.round(np.concatenate(chunks), WELD), axis=0)


# ---------------------------------------------------------------------------
# Connected components
# ---------------------------------------------------------------------------

@dataclass
class Component:
    """One connected piece of a mesh, welded by position."""

    points: np.ndarray
    triangles: np.ndarray
    boundary_edges: int
    volume: float

    @property
    def closed(self) -> bool:
        return self.boundary_edges == 0

    def vertices(self) -> np.ndarray:
        return self.points[self.triangles]


def components(points: np.ndarray, triangles: np.ndarray) -> list[Component]:
    """Split a primitive into its connected pieces.

    Connectivity is decided on welded positions, not on vertex indices: a loft
    duplicates its seam ring, so index-space connectivity would cut every tube
    open down one side and call the two halves separate shells.
    """
    if not len(triangles):
        return []
    _, inverse = np.unique(np.round(points, WELD), axis=0, return_inverse=True)
    inverse = inverse.reshape(-1)
    welded = inverse[triangles]
    parent = np.arange(int(inverse.max()) + 1)

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for tri in welded:
        roots = [find(int(vertex)) for vertex in tri]
        for other in roots[1:]:
            if other != roots[0]:
                parent[other] = roots[0]
    labels = np.array([find(node) for node in range(len(parent))])
    tri_label = labels[welded[:, 0]]

    result = []
    for label in np.unique(tri_label):
        mask = tri_label == label
        local_welded, local_raw = welded[mask], triangles[mask]
        # Boundary edges: an undirected edge used by exactly one triangle.
        edges = np.sort(np.concatenate([
            local_welded[:, [0, 1]], local_welded[:, [1, 2]],
            local_welded[:, [2, 0]]]), axis=1)
        _, counts = np.unique(edges, axis=0, return_counts=True)
        verts = points[local_raw]
        local = verts - verts.reshape(-1, 3).mean(axis=0)
        volume = float(np.einsum("ij,ij->i", local[:, 0],
                                 np.cross(local[:, 1], local[:, 2])).sum() / 6.)
        result.append(Component(points=points, triangles=local_raw,
                                boundary_edges=int((counts == 1).sum()),
                                volume=volume))
    return result


def garment_components(path: Path) -> list[Component]:
    result: list[Component] = []
    for points, triangles in mesh_primitives(path):
        result.extend(components(points, triangles))
    return result


# ---------------------------------------------------------------------------
# Enclosure
# ---------------------------------------------------------------------------

# Three directions that share no plane with the rig's axes, so a ray never runs
# along a ring seam or a sole slab and lands exactly on an edge.  Parity is
# taken as the majority, which absorbs the occasional grazing hit.
_RAYS = np.array([[.7211, .3907, .5710],
                  [-.4363, .8112, .3893],
                  [.3121, -.4507, .8365]])
_RAYS = _RAYS / np.linalg.norm(_RAYS, axis=1, keepdims=True)


def _crossings(origins: np.ndarray, verts: np.ndarray,
               direction: np.ndarray, chunk: int = 2048) -> np.ndarray:
    """Moller-Trumbore hit counts along one direction, for many origins at once."""
    corner = verts[:, 0]
    edge1 = verts[:, 1] - corner
    edge2 = verts[:, 2] - corner
    pvec = np.cross(direction, edge2)
    det = np.einsum("ij,ij->i", edge1, pvec)
    live = np.abs(det) > 1e-12
    if not live.any():
        return np.zeros(len(origins), dtype=np.int64)
    corner, edge1, edge2 = corner[live], edge1[live], edge2[live]
    inv = 1.0 / det[live]
    pvec = pvec[live]

    hits = np.empty(len(origins), dtype=np.int64)
    for start in range(0, len(origins), chunk):
        block = origins[start:start + chunk]
        tvec = block[:, None, :] - corner[None, :, :]
        u = np.einsum("nmj,mj->nm", tvec, pvec) * inv
        qvec = np.cross(tvec, edge1)
        v = np.einsum("nmj,j->nm", qvec, direction) * inv
        distance = np.einsum("nmj,mj->nm", qvec, edge2) * inv
        del qvec, tvec
        crossing = ((u >= 0.) & (v >= 0.) & (u + v <= 1.) & (distance > 1e-7))
        hits[start:start + chunk] = crossing.sum(axis=1)
    return hits


def inside(points: np.ndarray, shell: Component) -> np.ndarray:
    """Boolean per point: is it enclosed by this closed component?"""
    verts = shell.vertices()
    flat = verts.reshape(-1, 3)
    low, high = flat.min(axis=0) - 1e-4, flat.max(axis=0) + 1e-4
    within = np.all((points >= low) & (points <= high), axis=1)
    result = np.zeros(len(points), dtype=bool)
    if not within.any():
        return result
    candidates = points[within]
    votes = np.zeros(len(candidates), dtype=np.int64)
    for direction in _RAYS:
        votes += _crossings(candidates, verts, direction) % 2
    result[within] = votes >= 2
    return result


def enclosed_by_any(points: np.ndarray, shells: list[Component]) -> np.ndarray:
    """Inside *any* closed component - the whole point of splitting them.

    Biggest first.  A boot is one or two large shells and several dozen studs,
    buckles and gems, and a body vertex that is inside anything is almost always
    inside one of the large ones; testing those first settles nearly every point
    before the small ones are reached, and the rest are then rejected by their
    bounding boxes without a single ray being cast.
    """
    result = np.zeros(len(points), dtype=bool)
    ordered = sorted((shell for shell in shells if shell.closed),
                     key=lambda shell: -abs(shell.volume))
    for shell in ordered:
        todo = np.flatnonzero(~result)
        if not len(todo):
            break
        result[todo] = inside(points[todo], shell)
    return result


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------

@dataclass
class FitReport:
    garment: str
    rig: str
    exposed: int = 0
    covered: int = 0
    sink_mm: float = 0.0
    sole_y: float = 0.0
    boot_low_y: float = 0.0
    boundary_edges: int = 0
    components: int = 0
    closed_components: int = 0
    volume: float = 0.0
    exposed_points: np.ndarray = field(
        default_factory=lambda: np.zeros((0, 3)), repr=False)

    #: Acceptance: nothing showing through, nothing under the floor, every
    #: shell closed and wound outwards.
    MAX_SINK_MM = 8.0

    @property
    def ok(self) -> bool:
        return (self.exposed == 0 and self.sink_mm <= self.MAX_SINK_MM
                and self.boundary_edges == 0 and self.volume > 0.0)

    def line(self) -> str:
        return (f"{self.garment:<38} {self.rig:<18} "
                f"exposed {self.exposed:>4}/{self.covered:<5} "
                f"sink {self.sink_mm:>6.1f}mm  "
                f"bnd {self.boundary_edges:>4}  "
                f"shells {self.closed_components}/{self.components}  "
                f"vol {self.volume * 1e6:>7.1f}cm3  "
                f"{'ok' if self.ok else 'FAIL'}")

    def as_dict(self) -> dict:
        return {key: value for key, value in self.__dict__.items()
                if key != "exposed_points"} | {"ok": self.ok}


def covered_region(body: np.ndarray, shells: list[Component],
                   below_rim: bool = True) -> np.ndarray:
    """Which body vertices a garment is answerable for.

    Everything inside a closed shell's own footprint, one shell at a time.  A
    garment makes no promise about the body above its own opening, and the rim
    is a knife edge whose vertices sit exactly on the surface, so the region
    stops just short of it.

    ``below_rim`` is what makes this right for a piece that opens upwards - a
    boot, a trouser leg - and is turned off for one that is open at both ends,
    where the shell's own bounding box is the whole answer.
    """
    mask = np.zeros(len(body), dtype=bool)
    for shell in shells:
        if not shell.closed:
            continue
        flat = shell.vertices().reshape(-1, 3)
        low, high = flat.min(axis=0), flat.max(axis=0)
        plan = ((body[:, 0] >= low[0]) & (body[:, 0] <= high[0])
                & (body[:, 2] >= low[2] - .04) & (body[:, 2] <= high[2] + .04))
        under = body[:, 1] <= high[1] - RIM_MARGIN
        if not below_rim:
            under &= body[:, 1] >= low[1] + RIM_MARGIN
        mask |= plan & under
    return mask


def check(garment_path: Path, rig_path: Path,
          shells: list[Component] | None = None,
          body: np.ndarray | None = None,
          region: np.ndarray | None = None,
          below_rim: bool = True) -> FitReport:
    """Measure one garment against one body."""
    if shells is None:
        shells = garment_components(garment_path)
    if body is None:
        body = body_points(rig_path)
    report = FitReport(
        garment=Path(garment_path).name, rig=Path(rig_path).stem,
        components=len(shells),
        closed_components=sum(1 for shell in shells if shell.closed),
        boundary_edges=sum(shell.boundary_edges for shell in shells),
        volume=sum(shell.volume for shell in shells if shell.closed))
    if region is None:
        region = covered_region(body, shells, below_rim=below_rim)
    report.covered = int(region.sum())
    subject = body[region]
    if len(subject):
        held = enclosed_by_any(subject, shells)
        report.exposed = int((~held).sum())
        report.exposed_points = subject[~held]
    report.sole_y = float(body[:, 1].min())
    report.boot_low_y = min(
        float(shell.vertices().reshape(-1, 3)[:, 1].min()) for shell in shells
    ) if shells else 0.0
    report.sink_mm = (report.sole_y - report.boot_low_y) * 1000.0
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("garment", type=Path)
    parser.add_argument("rig", type=Path, nargs="+")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    shells = garment_components(args.garment)
    reports = [check(args.garment, rig, shells=shells) for rig in args.rig]
    if args.json:
        print(json.dumps([report.as_dict() for report in reports], indent=2))
    else:
        for report in reports:
            print(report.line())


if __name__ == "__main__":
    main()


#: The logic was never boot-specific; the old name still resolves so a caller
#: written against it keeps working.
boot_components = garment_components
