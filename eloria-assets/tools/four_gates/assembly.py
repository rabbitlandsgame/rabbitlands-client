"""Bridges the geometry/texture toolkits into a glTF document."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

import meshlib as M
import texturing
from gltf_writer import GLB
from kits import Palette
from meshlib import Geo


# Export resolution per material. Everything is synthesised at the hero size and
# downsampled on export, so texel density is spent where the player actually
# looks: monumental masonry and the plaza floor stay large, small props and
# distant terrain detail do not.
MATERIAL_RESOLUTIONS: Dict[str, int] = {
    "stone_ashlar": 1024,
    "paving_plaza": 1024,
    "stone_rubble": 512,
    "stone_trim": 512,
    "paving_road": 512,
    "roof_verdigris": 512,
    "roof_slate": 512,
    "plaster_warm": 512,
    "timber_dark": 512,
    "terrain_grass": 512,
    "terrain_rock": 512,
    "cloth_banner": 512,
    "paving_ceremonial": 1024,
}
DEFAULT_RESOLUTION = 256

# Interiors are seen close up but cover little surface, so they export smaller
# than the city does. Anything not listed falls back to INTERIOR_RESOLUTION.
INTERIOR_RESOLUTIONS: Dict[str, int] = {
    "stone_ashlar": 512,
    "plaster_warm": 512,
    "timber_dark": 512,
    "paving_road": 512,
}
INTERIOR_RESOLUTION = 256


class MaterialLibrary:
    """Registers the procedural PBR library into a GLB and hands back a Palette."""

    CACHE_VERSION = 5

    def __init__(self, glb: GLB, size: int = 512, hero: int = 1024,
                 seed: int = 20260827, cache_dir: Optional[str] = None,
                 subset: Optional[Sequence[str]] = None,
                 resolutions: Optional[Dict[str, int]] = None,
                 default_resolution: Optional[int] = None):
        """`subset` embeds only the named materials.

        A map pays texture memory for every material it registers, so an
        interior that uses eleven surfaces must not carry the city's thirty.
        Referencing a material outside the subset raises, which is the failure
        we want: loud, at build time, naming the material.
        """
        all_sets, encoded = self._load_or_build(size, hero, seed, cache_dir)
        if subset is not None:
            missing = [n for n in subset if n not in all_sets]
            if missing:
                raise KeyError(f"unknown material(s): {', '.join(sorted(missing))}")
            self.sets = {n: all_sets[n] for n in subset}
        else:
            self.sets = all_sets
        self.resolutions = dict(MATERIAL_RESOLUTIONS if resolutions is None
                                else resolutions)
        self.default_resolution = (DEFAULT_RESOLUTION if default_resolution is None
                                   else default_resolution)
        self.indices: Dict[str, int] = {}
        self.uv_scales: Dict[str, float] = {}
        for name, material in self.sets.items():
            maps = self._resize_maps(name, material)
            base = glb.add_texture_bytes(maps["base"], f"{name}_basecolor")
            normal = glb.add_texture_bytes(maps["normal"], f"{name}_normal")
            orm = glb.add_texture_bytes(maps["orm"], f"{name}_orm")
            emissive = (glb.add_texture_bytes(maps["emissive"], f"{name}_emissive")
                        if maps.get("emissive") is not None else None)
            self.indices[name] = glb.add_material(
                name,
                base_color=material.base_factor,
                base_color_texture=base,
                metallic=1.0, roughness=1.0,
                metallic_roughness_texture=orm,
                occlusion_texture=orm,
                normal_texture=normal,
                normal_scale=material.normal_scale,
                emissive=material.emissive_factor,
                emissive_texture=emissive,
                alpha_mode=material.alpha_mode,
                double_sided=material.double_sided,
            )
            self.uv_scales[name] = material.uv_scale
        self.palette = Palette(self.indices)
        # convenience: material index -> authored UV scale in metres per tile
        self.scale_by_index = {self.indices[n]: self.uv_scales[n] for n in self.sets}


    def target_resolution(self, name: str) -> int:
        return self.resolutions.get(name, self.default_resolution)

    def _resize_maps(self, name, material) -> dict:
        from PIL import Image
        target = self.target_resolution(name)

        def fit(image):
            if image is None or image.size[0] <= target:
                return image
            return image.resize((target, target), Image.LANCZOS)

        out = {"base": GLB.encode_png(fit(material.base)),
               "normal": GLB.encode_png(fit(material.normal)),
               "orm": GLB.encode_png(fit(material.orm))}
        if material.emissive is not None:
            out["emissive"] = GLB.encode_png(fit(material.emissive))
        return out

    def texture_memory_bytes(self) -> int:
        """Uncompressed RGBA8 footprint of the exported maps, including mips."""
        total = 0
        for name, material in self.sets.items():
            side = min(self.target_resolution(name), material.base.size[0])
            maps = 3 + (1 if material.emissive is not None else 0)
            total += int(side * side * 4 * maps * 4 / 3)
        return total

    @staticmethod
    def _encode(sets):
        from PIL import Image
        encoded = {}
        for name, material in sets.items():
            target = MATERIAL_RESOLUTIONS.get(name, DEFAULT_RESOLUTION)

            def fit(image):
                if image.size[0] <= target:
                    return image
                return image.resize((target, target), Image.LANCZOS)

            entry = {"base": GLB.encode_png(fit(material.base)),
                     "normal": GLB.encode_png(fit(material.normal)),
                     "orm": GLB.encode_png(fit(material.orm))}
            if material.emissive is not None:
                entry["emissive"] = GLB.encode_png(fit(material.emissive))
            encoded[name] = entry
        return encoded

    @classmethod
    def _load_or_build(cls, size, hero, seed, cache_dir):
        if not cache_dir:
            sets = texturing.build_materials(size=size, hero=hero, seed=seed)
            return sets, cls._encode(sets)
        import os
        import pickle
        os.makedirs(cache_dir, exist_ok=True)
        key = f"materials_v{cls.CACHE_VERSION}_{size}_{hero}_{seed}.pkl"
        path = os.path.join(cache_dir, key)
        source = os.path.join(os.path.dirname(os.path.abspath(texturing.__file__)),
                              "texturing.py")
        if os.path.exists(path) and os.path.getmtime(path) > os.path.getmtime(source):
            with open(path, "rb") as handle:
                return pickle.load(handle)
        sets = texturing.build_materials(size=size, hero=hero, seed=seed)
        payload = (sets, cls._encode(sets))
        with open(path, "wb") as handle:
            pickle.dump(payload, handle, protocol=4)
        return payload

    def apply_uv_scales(self, geo: Geo) -> Geo:
        """Divide the metre-space UVs by each material's authored tile size."""
        if geo.triangles == 0:
            return geo
        factor = np.ones(geo.v.shape[0], dtype=np.float32)
        for face_index in range(geo.f.shape[0]):
            scale = self.scale_by_index.get(int(geo.m[face_index]), 2.0)
            factor[geo.f[face_index]] = 1.0 / scale
        geo.t = (geo.t * factor[:, None]).astype(np.float32)
        return geo


def split_by_material(geo: Geo) -> List[Tuple[int, np.ndarray]]:
    order = np.argsort(geo.m, kind="stable")
    sorted_materials = geo.m[order]
    boundaries = np.flatnonzero(np.diff(sorted_materials)) + 1
    groups = np.split(order, boundaries)
    return [(int(geo.m[g[0]]), g) for g in groups if g.size]


def build_primitives(geo: Geo, tangents: bool = True) -> List[dict]:
    """Compact one Geo into per-material glTF primitives with tangents."""
    primitives = []
    for material, face_indices in split_by_material(geo):
        faces = geo.f[face_indices]
        used, remapped = np.unique(faces.reshape(-1), return_inverse=True)
        positions = geo.v[used]
        normals = geo.n[used]
        uvs = geo.t[used]
        indices = remapped.reshape(-1, 3).astype(np.uint32)
        prim = {
            "positions": positions,
            "normals": normals,
            "uvs": uvs,
            "indices": indices,
            "material": material,
        }
        if tangents:
            prim["tangents"] = M.tangents_for(positions, normals, uvs, indices)
        primitives.append(prim)
    return primitives


class SceneBuilder:
    """Accumulates named nodes and de-duplicates identical kit meshes."""

    def __init__(self, glb: GLB, library: MaterialLibrary):
        self.glb = glb
        self.library = library
        self._mesh_cache: Dict[str, int] = {}
        self.stats = {"instances": 0, "visibleTriangles": 0}
        self._mesh_triangles: Dict[int, int] = {}

    def mesh(self, key: str, geo_factory, tangents: bool = True,
             uv_locked: bool = False) -> int:
        """Register (or reuse) a mesh by cache key."""
        if key in self._mesh_cache:
            return self._mesh_cache[key]
        geo = geo_factory() if callable(geo_factory) else geo_factory
        if not uv_locked:
            self.library.apply_uv_scales(geo)
        primitives = build_primitives(geo, tangents=tangents)
        index = self.glb.add_mesh(key, primitives)
        self._mesh_cache[key] = index
        self._mesh_triangles[index] = geo.triangles
        return index

    def instance(self, name: str, mesh_index: int, position=(0, 0, 0),
                 yaw: float = 0.0, scale=None, extras: Optional[dict] = None) -> int:
        rotation = None
        if abs(yaw) > 1e-9:
            rotation = [0.0, float(np.sin(yaw * 0.5)), 0.0, float(np.cos(yaw * 0.5))]
        node = self.glb.add_node(name, mesh=mesh_index, translation=position,
                                 rotation=rotation, scale=scale, extras=extras)
        self.stats["instances"] += 1
        self.stats["visibleTriangles"] += self._mesh_triangles.get(mesh_index, 0)
        return node

    def group(self, name: str, children: Iterable[int]) -> int:
        return self.glb.add_node(name, children=list(children))
