"""Shared preview harness: build a Scene with the full Amberwood material set."""
import sys, os, hashlib, pickle, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from amberwood import materials as MAT, render as R

def _cache_path() -> str:
    """Cache file keyed by the source that generates the textures.

    This cache is read by the package build, not just by previews, so a stale
    entry silently ships textures that no longer match the recipes. Keying on a
    digest of the recipe sources means editing textures.py or materials.py
    invalidates it, and two regions never share one file.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    digest = hashlib.sha256()
    for name in ("textures.py", "materials.py"):
        with open(os.path.join(here, "amberwood", name), "rb") as handle:
            digest.update(handle.read())
    region = os.path.basename(os.getcwd())
    return os.path.join(tempfile.gettempdir(),
                        f"nymara_textures_{region}_{digest.hexdigest()[:12]}.pkl")


_CACHE = _cache_path()


def texture_sets(force: bool = False):
    if not force and os.path.exists(_CACHE):
        with open(_CACHE, "rb") as handle:
            return pickle.load(handle)
    t = time.time()
    sets = MAT.build_texture_sets()
    # Concurrent regional builders may share a working-directory label. Publish
    # only complete cache files so another reader never sees a partial pickle.
    with tempfile.NamedTemporaryFile(dir=os.path.dirname(_CACHE), delete=False) as handle:
        temporary = handle.name
        pickle.dump(sets, handle)
    os.replace(temporary, _CACHE)
    print(f"[textures] generated {len(sets)} sets in {time.time() - t:.1f}s")
    return sets


def new_scene(sets=None):
    scene = R.Scene()
    MAT.register_preview_materials(scene, sets or texture_sets())
    return scene


def scene_from_build(build, sets=None, include_kinds=None):
    """Fill a preview Scene from a RegionBuild (same materials as the GLB)."""
    from amberwood import mesh as M
    scene = new_scene(sets)
    # The GLB uses alpha-tested ground copies. Without their names here the
    # preview silently assigns material zero (timber) to every terrain class.
    from dataclasses import replace
    by_name = {material.name: material for material in scene.materials}
    for name, piece in build.terrain_meshes.items():
        if name.startswith('StreamView_') or '_StreamThreshold_' in name or not piece.triangle_count: continue
        if piece.material not in by_name:
            base = by_name.get(MAT.base_material(piece.material))
            if base is None:
                raise ValueError(f"no preview material for {piece.material}")
            alias = replace(base, name=piece.material, alpha_mode="MASK")
            scene.add_material(alias)
            by_name[piece.material] = alias
        scene.add_mesh(piece)
    for name, piece in build.water_meshes.items():
        if name.startswith('StreamView_') or '_StreamThreshold_' in name or not piece.triangle_count: continue
        scene.add_mesh(piece)
    for placement in build.placements:
        if placement.node.startswith('StreamView_'): continue
        if include_kinds is not None and placement.kind not in include_kinds:
            continue
        transform = (M.translation(*placement.position)
                     @ M.rotation_y(placement.rotation_y)
                     @ M.scaling(placement.scale))
        target = build.meshes[placement.mesh]
        # `all_parts`, not `parts`. Two bugs, one line:
        #
        # 1. `parts` omits `walk_parts`, so every walkable deck a landmark
        #    carries - a causeway deck, a quay, a canopy platform floor,
        #    a boardwalk - was missing from every offline preview in every
        #    region. The previews were of the structure without its floor.
        # 2. A MeshGroup that has *only* walk parts (a flight of steps, say)
        #    has an empty `parts`, which is falsy, so the group itself was
        #    passed to `add_mesh`. `MeshGroup.triangle_count` reports its parts'
        #    total while the group's own index buffer is empty, so the packed
        #    geometry claimed triangles it had no indices for and the C
        #    rasteriser read past the end of the buffer. On Manymouth, whose
        #    walkway landings are exactly that shape, this segfaulted the
        #    preview and the minimap render.
        #
        # `MeshGroup.all_parts` is parts + walk_parts and is already the
        # property `export_glb` uses for its material scan.
        parts = getattr(target, "all_parts", None)
        if parts:
            for part in parts:
                scene.add_mesh(part, transform)
        else:
            scene.add_mesh(target, transform)
    return scene
