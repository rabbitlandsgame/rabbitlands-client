"""Region build containers, shared by every Nymara region.

`Placement` and `RegionBuild` are the handoff between a region's composition
code and the GLB/manifest exporters. They carry no region-specific data, so
they live in the toolkit rather than in any one region's `region.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from amberwood import mesh as M
from amberwood import terrain as TER


@dataclass
class Placement:
    node: str
    mesh: str
    position: tuple[float, float, float]
    rotation_y: float = 0.0
    scale: float = 1.0
    collides: bool = False
    walk_surface: bool = False
    kind: str = "prop"
    landmark: str | None = None
    extras: dict | None = None


@dataclass
class RegionBuild:
    terrain: TER.Terrain
    meshes: dict[str, M.Mesh] = field(default_factory=dict)
    placements: list[Placement] = field(default_factory=list)
    terrain_meshes: dict[str, M.Mesh] = field(default_factory=dict)
    water_meshes: dict[str, M.Mesh] = field(default_factory=dict)
    landmarks: list[dict] = field(default_factory=list)
    interactives: list[dict] = field(default_factory=list)
    npc_markers: list[dict] = field(default_factory=list)
    harvestables: list[dict] = field(default_factory=list)
    portals: list[dict] = field(default_factory=list)
    spawns: list[dict] = field(default_factory=list)
    crossings: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    renames: dict[str, str] = field(default_factory=dict)

    def add_mesh(self, name: str, mesh: M.Mesh) -> str:
        if name not in self.meshes:
            self.meshes[name] = mesh
        return name

    def place(self, placement: Placement) -> Placement:
        # Walkable built surfaces must carry the navigation prefix, because the
        # client turns node names that match `navigation.surfaceNodePrefixes`
        # into the layer the grounding ray tests against.
        if placement.walk_surface and not placement.node.startswith("Walk_"):
            new_name = "Walk_" + placement.node
            self.renames[placement.node] = new_name
            placement.node = new_name
        self.placements.append(placement)
        return placement

    def resolve_names(self) -> None:
        """Rewrite metadata node references through the walk-surface renames."""
        for collection in (self.landmarks, self.interactives, self.npc_markers,
                           self.harvestables, self.portals, self.spawns):
            for entry in collection:
                node = entry.get("node")
                if node in self.renames:
                    entry["node"] = self.renames[node]
