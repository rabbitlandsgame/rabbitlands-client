"""render_minimap.py: draw a continent-v2 territory's map picture from its published chunks.

  python -B eloria-assets/maps/continent-v2/_continent_v2/render_minimap.py --region <catalog-id> [--region ...] \
         [--work <scratch dir>] [--supersample 2] [--window 256] [--apply] [--checkout <worktree>]
  python -B eloria-assets/maps/continent-v2/_continent_v2/render_minimap.py --check [--region ...]

The game client's Tab map and minimap show a region's own top-down picture, minimap.webp (one pixel a metre, north
up), laid on the ground for the map cameras (src/world/map_picture.gd); cartography.json frames it
(eloria-assets/tools/build_continent_map.py). Without one, the cameras render the live world, and a chunk-streamed
territory holds only the chunks round the player: the Tab map of a 2 km isle showed a few hundred metres of ground in
a field of nothing. The twelve-territory continent draws its pictures from one master GLB
(nymara-regions/_continent/atlas_export.py, render_region_cartography.py); a continent-v2 package has no master, only
its chunks, so neither tool can take it (serve plan CV14).

This tool renders the picture from the package itself: the chunk GLBs its territory manifest lists, through the
twelve-territory atlas renderer's own scene reading, lighting, water ink, texture minification and native
rasteriser (render_region_cartography.py, imported, never copied). The frame is the one map_view.gd gives the live
Tab map (asset.mapBounds), so the picture needs no crop. The image is drawn in square windows; each window holds
every chunk whose bounds reach it (a tree that overhangs its chunk is drawn whole) and a margin that is cut off after
the supersampled image is reduced, so windows meet without a seam.

--apply writes <package>/minimap.webp and the territory manifest's `minimap` block: the frame, imageSha256, and
cartographyRender.chunksSha256 (publish_client.chunks_digest: every chunk GLB the manifest lists, in its order).
publish_client.py keeps the block through a republish only while that digest holds, so a picture never outlives the
geometry it shows; build_continent_map.py refuses a served territory without one. Without --apply the picture and a
report go to --work only. --check exits 1 when a package's picture is missing or stale (the image or its chunks).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True
import publish_client as PC  # noqa: E402  (the package format: chunks_digest, the minimap file name)

DEFAULT_CHECKOUT = PC.DEFAULT_CHECKOUT
TOOL = "eloria-assets/maps/continent-v2/_continent_v2/render_minimap.py"
REGISTRY = "godot-client/data/maps/registry.json"
RETIREMENT = "godot-client/data/assets/retired_procedural_models.json"
CHUNK_READER_VERSION = 2              # shared placements and the runtime retirement policy
ROAD_CHUNK_READER_VERSION = 3         # portable road fields, native depth-tested offline atlas
CATALOG = "godot-client/world_authoring/continent-v2/territories.json"
WEBP_QUALITY = 92                       # the region minimaps' encoding (render_region_cartography.py)
# One window covers every Landfall territory (the largest is 1,356 m): drawn in 256 m windows the pictures showed
# straight seams at the window lines, whole windows 10-14 levels brighter than their neighbours (not the depth
# range and not the chunk selection; a single window is seam-free, and faster: 21 s against 41 s for Warrenmead).
WINDOW_METRES = 2048
MARGIN_METRES = 8


class MinimapError(ValueError):
    """A package this tool cannot draw, or a picture that does not match its package."""


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def package_of(checkout: Path, region: str) -> Path:
    """The territory's client package folder: the folder its registry row's manifest names."""
    row = read_json(Path(checkout) / REGISTRY)["maps"].get(region)
    if not row or not str(row.get("manifest", "")).startswith("res://../"):
        raise MinimapError(f"{region} has no registry row naming its package")
    return (Path(checkout) / row["manifest"][len("res://../"):]).parent


def frame_of(manifest: dict) -> tuple[list[float], list[float], list[int]]:
    """The live Tab map's frame of a package (map_view.gd bounds_for: mapBounds first), as whole metres, and the
    picture size at one pixel a metre."""
    bounds = manifest["asset"].get("mapBounds") or manifest["asset"]["playableBounds"]
    low = [float(bounds["min"][0]), float(bounds["min"][2])]
    high = [float(bounds["max"][0]), float(bounds["max"][2])]
    if any(v != int(v) for v in low + high):
        raise MinimapError(f"{manifest['asset']['id']}: mapBounds {low}..{high} are not whole metres, so one pixel "
                           "a metre would not land on the server's tiles")
    size = [int(high[0] - low[0]), int(high[1] - low[1])]
    if min(size) <= 0:
        raise MinimapError(f"{manifest['asset']['id']}: empty mapBounds")
    return low, high, size


# --- reading the chunks (render_region_cartography.scene_from_glb, for many GLBs sharing one texture pool) -----------

class Pool:
    """Albedo images shared by every chunk: decoded once, linearised and reduced to the native renderer's 512 px
    layers (what Scene._pack_textures does to each layer), checked against the SHA-256 the manifest records."""

    def __init__(self, rc, asset_root=None):
        self.rc = rc
        self.asset_root = asset_root
        self.images = {}

    def key(self, doc, binary, index, glb, resources, chunk):
        spec = doc["images"][doc["textures"][index]["source"]]
        if "bufferView" in spec:
            key = f"{chunk}:{index}"
            if key not in self.images:
                self.images[key] = self._prepare(self.rc._texture(doc, binary, index))
            return key
        uri = spec.get("uri")
        if uri not in self.images:
            # _texture resolves the URI under eloria-assets and refuses one whose SHA-256 is not the recorded one
            self.images[uri] = self._prepare(self.rc._texture(doc, binary, index, glb, resources, self.asset_root))
        return uri

    @staticmethod
    def _prepare(rgba):
        import numpy as np
        from PIL import Image
        rgba = rgba.copy()
        rgba[..., :3] = np.rint((rgba[..., :3] / 255.) ** 2.2 * 255).astype(np.uint8)
        if rgba.shape[:2] != (512, 512):
            rgba = np.asarray(Image.fromarray(rgba, "RGBA").resize((512, 512), Image.BILINEAR))
        return np.ascontiguousarray(rgba, dtype=np.uint8)


def read_chunk(rc, pool, glb: Path, resources: dict, chunk: str, retirement=None, checkout=None,
               *, road_ground=None, manifest_path=None, hidden_nodes=(), node_label=None) -> dict:
    """One chunk's materials and its triangles in territory metres (scene_from_glb's rules: water ink on water
    materials, linear albedo, MASK for BLEND and soft ground, mirrored instances re-wound, invisible stream
    thresholds left out)."""
    import numpy as np
    R = rc.R
    import glb_reader
    doc, binary = glb_reader.load(glb, prototypes=False)
    if retirement:
        relative = glb.resolve().relative_to(Path(checkout).resolve()).as_posix()
        entry = retirement.get("mapMeshCopies", {}).get(relative, {})
        if entry and sha_bytes(glb.read_bytes()) != entry.get("sha256"):
            raise MinimapError(f"{relative}: retired mesh index needs refresh")
        retired_meshes = set(entry.get("meshes", []))
        retired_prototypes = set(retirement.get("retiredMapPrototypes", []))
        for node in doc.get("nodes", []):
            if node.get("mesh") in retired_meshes:
                node.pop("mesh")
            extras = node.get("extras", {}).get("eloria", {})
            if extras.get("prototype") in retired_prototypes:
                extras.pop("prototype")
                node.pop("mesh", None)
    previous_pool = glb_reader.SM.POOL
    try:
        if checkout is not None:
            glb_reader.SM.POOL = Path(checkout) / "eloria-assets/maps/_shared/meshes"
        doc, binary = glb_reader.SM.inline_prototypes(glb, doc, binary)
    finally:
        glb_reader.SM.POOL = previous_pool
    # Optional offline interior cutaway. Mutate this private decoded scene,
    # never source GLBs; ordinary regional rendering retains every node.
    hidden = set(hidden_nodes)
    if hidden:
        stack = [i for i, node in enumerate(doc.get("nodes", [])) if node.get("name", "") in hidden]
        seen = set()
        while stack:
            index = stack.pop()
            if index in seen:
                continue
            seen.add(index)
            node = doc["nodes"][index]
            node.pop("mesh", None)
            stack.extend(node.get("children", []))
    resources = dict(resources)
    # Restored pooled prototypes can name textures not present in the tiny
    # placement document. Their content-addressed filenames pin their bytes.
    for image in doc.get("images", []):
        uri = image.get("uri")
        if uri and uri not in resources:
            identity = Path(uri).stem
            if len(identity) != 64 or any(c not in "0123456789abcdef" for c in identity):
                raise MinimapError(f"{glb}: undeclared pooled texture {uri}")
            resources[uri] = identity
    materials, water = [], set()
    for i, material in enumerate(doc.get("materials", [])):
        name = material.get("name", str(i))
        if name.startswith("water_") or name in rc.WATER_NAMES:
            water.add(i)
            materials.append(R.RenderMaterial(f"{chunk}:{i}", rc.WATER, roughness=1., double_sided=True))
            continue
        pbr = material.get("pbrMetallicRoughness", {})
        albedo, wrap = None, (rc.REPEAT, rc.REPEAT)
        if "baseColorTexture" in pbr:
            texture = pbr["baseColorTexture"]
            if texture.get("texCoord", 0) != 0 or texture.get("extensions"):
                raise MinimapError(f"{glb}: unsupported texture coordinate transform in {name}")
            albedo = pool.key(doc, binary, texture["index"], glb, resources, chunk)
            wrap = rc.texture_wrap(doc, texture["index"])
        mode = material.get("alphaMode", "OPAQUE")
        made = R.RenderMaterial(f"{chunk}:{i}", tuple(pbr.get("baseColorFactor", [1, 1, 1, 1])),
                                roughness=max(.5, float(pbr.get("roughnessFactor", 1.))),
                                metallic=float(pbr.get("metallicFactor", 1.)), albedo=albedo,
                                alpha_mode="MASK" if mode == "BLEND" or name.endswith("_soft_ground") else mode,
                                alpha_cutoff=float(material.get("alphaCutoff", .5)),
                                double_sided=bool(material.get("doubleSided", False)))
        made.atlas_soft_ground = name.endswith("_soft_ground")
        made.atlas_wrap = wrap
        rc.clamp_flags(made)
        materials.append(made)
    if not materials:
        materials.append(R.RenderMaterial(f"{chunk}:0"))
    parts, cache, ground, labels = [], {}, [], []
    for name, mesh_index, transform in rc.visible_nodes(doc):
        label = node_label(name, mesh_index, transform, doc, binary) if node_label is not None else None
        for pi, primitive in enumerate(doc["meshes"][mesh_index]["primitives"]):
            if primitive.get("mode", 4) != 4:
                raise MinimapError(f"{glb}: non-triangle primitive in {name}")
            key = mesh_index, pi
            if key not in cache:
                a = primitive["attributes"]
                pos = rc.accessor(doc, binary, a["POSITION"]).astype(np.float64)
                indices = (rc.accessor(doc, binary, primitive["indices"]).reshape(-1).astype(np.int64)
                           if "indices" in primitive else np.arange(len(pos)))
                if not len(indices):
                    cache[key] = None
                    continue
                normal = (rc.accessor(doc, binary, a["NORMAL"]).astype(np.float64) if "NORMAL" in a
                          else np.tile([0., 1., 0.], (len(pos), 1)))
                uv = (rc.accessor(doc, binary, a["TEXCOORD_0"]).astype(np.float32) if "TEXCOORD_0" in a
                      else np.zeros((len(pos), 2), np.float32))
                color = (rc.accessor(doc, binary, a["COLOR_0"]).astype(np.float32) if "COLOR_0" in a
                         else np.ones((len(pos), 4), np.float32))
                if color.shape[1] == 3:
                    color = np.column_stack((color, np.ones(len(color), np.float32)))
                material = int(primitive.get("material", 0))
                if material in water:
                    color = np.ones((len(pos), 4), np.float32)
                cache[key] = (pos, normal, uv, indices, color, min(material, len(materials) - 1))
            if cache[key] is None:
                continue
            pos, normal, uv, indices, color, material = cache[key]
            world = pos @ transform[:3, :3].T + transform[:3, 3]
            normals = normal @ np.linalg.inv(transform[:3, :3])
            normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
            faces = indices
            if np.linalg.det(transform[:3, :3]) < 0:
                faces = indices.reshape(-1, 3)[:, ::-1].reshape(-1)
            parts.append((world.astype(np.float32), normals.astype(np.float32), uv, faces.astype(np.int32), color,
                          material))
            if node_label is not None:
                labels.append(label)
            if road_ground and name.startswith("AuthoredGround_"):
                ground.append((name, world, normals, faces))
    low = np.min([p[0].min(axis=0) for p in parts], axis=0) if parts else np.zeros(3)
    high = np.max([p[0].max(axis=0) for p in parts], axis=0) if parts else np.zeros(3)
    result = {"materials": materials, "parts": parts, "low": low, "high": high}
    if node_label is not None:
        result["part_labels"] = labels
    if road_ground is not None:
        if checkout is None or manifest_path is None:
            raise MinimapError("Road-field cartography requires its repository and chunk manifest")
        import road_ground_cartography
        road_ground_cartography.append(rc, pool, result, ground, checkout, manifest_path, road_ground, chunk)
    return result


def window_scene(rc, pool, pieces: list[tuple[dict, tuple[float, float]]]):
    """One Scene holding these chunks, each moved by its (x, z) offset into the drawn territory's metres, and its
    vertex colours."""
    import numpy as np
    R = rc.R
    scene = R.Scene()
    colors = []
    for chunk, (dx, dz) in pieces:
        first = len(scene.materials)
        for material in chunk["materials"]:
            if material.albedo:
                scene.add_texture(material.albedo, pool.images[material.albedo])
            scene.add_material(material)
        shift = np.asarray([dx, 0.0, dz], np.float32)
        for positions, normals, uvs, faces, color, material in chunk["parts"]:
            scene.positions.append(positions + shift if dx or dz else positions)
            scene.normals.append(normals)
            scene.uvs.append(uvs)
            scene.indices.append(faces + scene._offset)
            scene.tri_material.append(np.full(len(faces) // 3, first + material, dtype=np.int32))
            scene._offset += len(positions)
            colors.append(color)
    if not colors:
        return None, None
    return scene, np.ascontiguousarray(np.vstack(colors), dtype=np.float32)


# --- the picture -----------------------------------------------------------------------------------------------------

def sources(checkout: Path, region: str) -> list[dict]:
    """Every published territory on the drawn one's continent frame (registry continentGeography.frame), the drawn
    one first: its package, its chunks, and the (x, z) offset that moves its metres into the drawn territory's (the
    difference of their continent translations). A frame reaches past its own ground (the Gull Skerries' square holds
    the north coast of sw_isle), and the twelve-territory pictures are cut from one common render, so a neighbour's
    ground in the frame is drawn as it stands, not left as sea."""
    rows = read_json(Path(checkout) / REGISTRY)["maps"]
    here = rows[region]
    frame = (here.get("continentGeography") or {}).get("frame")
    origin = [float(v) for v in here["continentGeography"]["translation"]]
    found = []
    for identity, row in rows.items():
        if not row.get("continentGeography"):
            continue
        if (row.get("continentGeography") or {}).get("frame") != frame or not row.get("manifest"):
            continue
        package = package_of(checkout, identity)
        if not (package / "world.json").is_file():
            continue
        chunks = read_json(package / "world.json").get("streamingChunks", {}).get("chunks", [])
        if not chunks:
            continue
        translation = [float(v) for v in row["continentGeography"]["translation"]]
        found.append({"region": identity, "package": package,
                      "chunks": chunks,
                      "offset": (translation[0] - origin[0], translation[2] - origin[2])})
    found.sort(key=lambda source: source["region"] != region)
    if not found or found[0]["region"] != region:
        raise MinimapError(f"{region} has no published package")
    return found


def reader_version_for(checkout: Path, region: str, world_frame=None) -> int:
    """Preserve old pictures when no converted own/neighbour chunk reaches them."""
    drawn = sources(checkout, region)
    low, high = world_frame or frame_of(read_json(drawn[0]["package"] / "world.json"))[:2]
    for source in drawn:
        dx, dz = source["offset"]
        for chunk in source["chunks"]:
            bounds = chunk["bounds"]
            if not (bounds["min"][0] + dx <= high[0] and bounds["max"][0] + dx >= low[0]
                    and bounds["min"][2] + dz <= high[1] and bounds["max"][2] + dz >= low[1]):
                continue
            if "roadGround" in read_json(source["package"] / chunk["manifest"]):
                return ROAD_CHUNK_READER_VERSION
    return CHUNK_READER_VERSION


def render(checkout: Path, region: str, work: Path, supersample: int = 2, window: int = WINDOW_METRES,
           log=print, *, pixels_per_metre: int = 1, world_frame=None) -> dict:
    """Draw the picture of one package into work/<region>/minimap.webp and return its report."""
    import numpy as np
    from PIL import Image
    tools = str(Path(checkout) / "eloria-assets" / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import render_region_cartography as rc
    began = time.perf_counter()
    policy_path = Path(checkout) / RETIREMENT
    retirement = read_json(policy_path) if policy_path.is_file() else {}
    retirement_sha = PC.sha(policy_path) if policy_path.is_file() else None
    drawn = sources(checkout, region)
    package = drawn[0]["package"]
    # Capture each source before its first chunk read, then recheck after
    # rendering. A metadata edit during a long draw cannot certify old pixels
    # with a newly computed road-field digest.
    digests = {region: PC.chunks_digest(package, drawn[0]["chunks"])}
    manifest = read_json(package / "world.json")
    low, high, size = frame_of(manifest)
    if pixels_per_metre not in (1, 2, 4, 8):
        raise MinimapError("pixels_per_metre must be 1, 2, 4 or 8")
    if world_frame is not None:
        low, high = world_frame
        if any(v != int(v) for v in low + high):
            raise MinimapError("detail frame must use whole metres")
    size = [int((high[i] - low[i]) * pixels_per_metre) for i in range(2)]
    pool = Pool(rc, Path(checkout) / "eloria-assets")
    last_row, cache, used = {}, {}, set()
    picture = Image.new("RGB", tuple(size), tuple(rc.water_rgb()))
    stats = {"windows": 0, "emptyWindows": 0, "chunkReads": 0, "triangles": 0, "coveredSamples": 0, "samples": 0,
             "roadFieldChunks": 0, "roadFieldProxyTriangles": 0}
    native = Path(work) / "_atlas_native"
    for row, z0 in enumerate(range(int(low[1]), int(high[1]), window)):
        z1 = min(z0 + window, int(high[1]))
        for x0 in range(int(low[0]), int(high[0]), window):
            x1 = min(x0 + window, int(high[0]))
            lo = np.asarray([x0 - MARGIN_METRES, z0 - MARGIN_METRES], float)
            hi = np.asarray([x1 + MARGIN_METRES, z1 + MARGIN_METRES], float)
            pieces = []
            for source in drawn:
                dx, dz = source["offset"]
                for c in source["chunks"]:
                    b = c["bounds"]
                    if not (b["min"][0] + dx <= hi[0] and b["max"][0] + dx >= lo[0]
                            and b["min"][2] + dz <= hi[1] and b["max"][2] + dz >= lo[1]):
                        continue
                    key = (source["region"], c["id"])
                    if key not in cache:
                        if source["region"] not in digests:
                            digests[source["region"]] = PC.chunks_digest(source["package"], source["chunks"])
                        chunk_manifest = read_json(source["package"] / c["manifest"])
                        glb = (source["package"] / c["manifest"]).parent / chunk_manifest["asset"]["glb"]
                        for uri, expected in chunk_manifest.get("externalMeshes", {}).items():
                            rc.external_resource(glb, uri, expected)
                        cache[key] = read_chunk(rc, pool, glb, chunk_manifest.get("externalResources") or {},
                                                f"{source['region']}/{c['id']}", retirement, checkout,
                                                road_ground=chunk_manifest.get("roadGround"),
                                                manifest_path=source["package"] / c["manifest"])
                        if "road_fields" in cache[key]:
                            stats["roadFieldChunks"] += 1
                            stats["roadFieldProxyTriangles"] += cache[key]["road_fields"]["triangles"]
                        stats["chunkReads"] += 1
                    last_row[key] = row
                    used.add(source["region"])
                    pieces.append((cache[key], (dx, dz)))
            stats["windows"] += 1
            scene, colors = window_scene(rc, pool, pieces)
            if scene is None:
                stats["emptyWindows"] += 1
                continue
            stats["triangles"] += scene.triangle_count()
            pixels = (int(hi[0] - lo[0]) * pixels_per_metre, int(hi[1] - lo[1]) * pixels_per_metre)
            rgb, _, _, counts = rc.raster(scene, colors, lo, hi, pixels, supersample, native_cache=native)
            stats["coveredSamples"] += counts["coveredSamples"]
            stats["samples"] += counts["sampleCount"]
            stats["nativeRenderer"] = counts["nativeRenderer"]
            margin = MARGIN_METRES * pixels_per_metre
            piece = rgb.crop((margin, margin, margin + (x1 - x0) * pixels_per_metre,
                              margin + (z1 - z0) * pixels_per_metre))
            picture.paste(piece, ((x0 - int(low[0])) * pixels_per_metre, (z0 - int(low[1])) * pixels_per_metre))
        # a chunk this row did not reach lies behind the window rows still to come
        for key in [k for k in cache if last_row.get(k, -1) < row]:
            del cache[key]
    digests = {key: value for key, value in digests.items() if key in used or key == region}
    folder = Path(work) / region
    folder.mkdir(parents=True, exist_ok=True)
    encoded = io.BytesIO()
    picture.save(encoded, "WEBP", quality=WEBP_QUALITY, method=6)
    (folder / PC.MINIMAP).write_bytes(encoded.getvalue())
    report = {"region": region, "tool": TOOL, "styleVersion": rc.STYLE_VERSION, "package": str(package),
              "worldMin": low, "worldMax": high, "imageSize": size, "supersample": supersample,
              "pixelsPerMetre": pixels_per_metre,
              "chunkReaderVersion": reader_version_for(checkout, region, (low, high)), "retirementSha256": retirement_sha,
              "windowMetres": window, "marginMetres": MARGIN_METRES, "chunks": len(drawn[0]["chunks"]),
              "chunksSha256": digests[region],
              "neighbourChunksSha256": {k: v for k, v in sorted(digests.items()) if k != region},
              "imageSha256": sha_bytes(encoded.getvalue()), "imageBytes": len(encoded.getvalue()),
              "waterRGB": list(rc.water_rgb()), "textures": len(pool.images),
              "toolSha256": PC.sha(__file__), "rendererSha256": PC.sha(rc.__file__),
              "rasterSourceSha256": PC.sha(rc.TOOLKIT / "native" / "raster.c"), **stats,
              "seconds": round(time.perf_counter() - began, 1)}
    for source in drawn:
        if source["region"] not in digests:
            continue
        if PC.chunks_digest(source["package"], source["chunks"]) != digests[source["region"]]:
            raise MinimapError(f"{source['region']}'s chunks changed while {region} was drawn; draw it again")
    (folder / "render-report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    log(f"{region}: {size[0]}x{size[1]} px from {stats['chunkReads']} chunks of {sorted(used)}, "
        f"{stats['triangles']:,} triangles in {stats['windows']} windows, {report['seconds']} s")
    return report


def minimap_block(manifest: dict, report: dict) -> dict:
    """The territory manifest's minimap block (the legacy packages' shape; map_picture.gd and build_continent_map.py
    read worldMin/worldMax/imageSize/pixelsPerMetre/image, MapPicture.height_below reads bounds)."""
    bounds = manifest["asset"].get("mapBounds") or manifest["asset"]["playableBounds"]
    return {"file": PC.MINIMAP, "image": PC.MINIMAP, "bounds": bounds, "northUp": True,
            "worldMin": report["worldMin"], "worldMax": report["worldMax"], "imageSize": report["imageSize"],
            "pixelsPerMetre": 1, "imageSha256": report["imageSha256"],
            "renderedFrom": "the package's chunk GLBs (the shared cartography renderer, window by window)",
            "cartographyRender": {"generator": TOOL, "styleVersion": report["styleVersion"],
                                  "chunksSha256": report["chunksSha256"],
                                  "neighbourChunksSha256": report["neighbourChunksSha256"],
                                  "chunkReaderVersion": report["chunkReaderVersion"],
                                  "supersample": report["supersample"],
                                  "windowMetres": report["windowMetres"], "waterRGB": report["waterRGB"]}}


def drawn_from(checkout: Path, region: str, own: str | None, neighbours: dict) -> list[str]:
    """Which packages hold other chunks now than the picture of `region` was drawn from ([] when none)."""
    stale = []
    for source in sources(checkout, region):
        recorded = own if source["region"] == region else neighbours.get(source["region"])
        if recorded is None and source["region"] != region:
            continue
        if PC.chunks_digest(source["package"], source["chunks"]) != recorded:
            stale.append(source["region"])
    return stale


def apply(checkout: Path, region: str, work: Path, report: dict) -> None:
    """Copy the picture into the package and stamp the manifest, refusing a picture of other chunks."""
    package = package_of(checkout, region)
    path = package / "world.json"
    manifest = read_json(path)
    stale = drawn_from(checkout, region, report["chunksSha256"], report["neighbourChunksSha256"])
    if stale:
        raise MinimapError(f"{region}: the picture in {work} was drawn from other chunks of {stale}; draw it again")
    image = (Path(work) / region / PC.MINIMAP).read_bytes()
    if sha_bytes(image) != report["imageSha256"]:
        raise MinimapError(f"{region}: {work}/{region}/{PC.MINIMAP} changed after it was drawn")
    (package / PC.MINIMAP).write_bytes(image)
    manifest["minimap"] = minimap_block(manifest, report)
    PC.json_write(path, manifest)


def check(checkout: Path, regions: list[str]) -> list[str]:
    """Why a package's picture is missing or stale, or []."""
    problems = []
    for region in regions:
        try:
            package = package_of(checkout, region)
        except MinimapError as error:
            problems.append(str(error))
            continue
        manifest = read_json(package / "world.json")
        block = manifest.get("minimap") or {}
        if not block:
            problems.append(f"{region}: the package has no minimap block; run render_minimap.py --apply")
            continue
        image = package / str(block.get("image", ""))
        if not image.is_file() or PC.sha(image) != block.get("imageSha256"):
            problems.append(f"{region}: {image.name} is missing or not the picture the manifest records")
        render = block.get("cartographyRender") or {}
        if render.get("chunkReaderVersion", CHUNK_READER_VERSION) != reader_version_for(checkout, region):
            problems.append(f"{region}: the map reader version is stale")
        stale = drawn_from(checkout, region, render.get("chunksSha256"), render.get("neighbourChunksSha256") or {})
        if stale:
            problems.append(f"{region}: the picture was drawn from other chunks than {stale} hold now; run "
                            f"render_minimap.py --region {region} --apply")
        low, high, size = frame_of(manifest)
        if [block.get("worldMin"), block.get("worldMax"), block.get("imageSize")] != [low, high, size]:
            problems.append(f"{region}: the picture's frame is not the package's mapBounds")
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--region", action="append", help="a continent-v2 territory (default: every catalog entry)")
    ap.add_argument("--work", type=Path, help="where the pictures and reports are drawn (required to draw)")
    ap.add_argument("--supersample", type=int, choices=(1, 2, 3, 4), default=2)
    ap.add_argument("--window", type=int, default=WINDOW_METRES)
    ap.add_argument("--apply", action="store_true", help="copy each picture into its package and stamp its manifest")
    ap.add_argument("--check", action="store_true", help="exit 1 when a package's picture is missing or stale")
    ap.add_argument("--checkout", type=Path, default=DEFAULT_CHECKOUT)
    args = ap.parse_args(argv)
    regions = args.region or [e["id"] for e in read_json(args.checkout / CATALOG)["entries"]]
    if args.check:
        problems = check(args.checkout, regions)
        for problem in problems:
            print(problem)
        return 1 if problems else 0
    if args.work is None:
        ap.error("--work is required to draw")
    try:
        for region in regions:
            report = render(args.checkout, region, args.work, args.supersample, args.window)
            if args.apply:
                apply(args.checkout, region, args.work, report)
                print(f"{region}: applied ({report['imageBytes']:,} bytes)")
    except MinimapError as error:
        print(f"refused: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
