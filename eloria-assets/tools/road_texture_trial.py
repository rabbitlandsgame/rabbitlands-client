"""Bake an isolated Suncoil road-mask experiment, without publishing map assets.

The treatment removes only explicitly selected authored road visual meshes.
Their exact float32 collision triangles remain in compact position/index files.
Road masks retain separate materials and overlapping UV sheets; they reuse the
authored detail images. RG32F flow fields and every stored mip count toward the
storage comparison. This is an experimental producer, not a production loader.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import zlib

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt
import zstandard

import shared_meshes as SM

SCHEMA = "rabbitlands-road-texture-trial-v1"
DTYPES = {5120: "i1", 5121: "u1", 5122: "<i2", 5123: "<u2", 5125: "<u4", 5126: "<f4"}
COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
DEFAULT_ROADS = ("suncoil--a3-trail-01", "suncoil--a3-trail-02")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def relative(path, base):
    return os.path.relpath(path, base).replace("\\", "/")


def accessor(document, body, index, normalized=True):
    a = document["accessors"][index]
    if "sparse" in a or "bufferView" not in a:
        raise ValueError("trial requires ordinary nonsparse accessors")
    view = document["bufferViews"][a["bufferView"]]
    dtype = np.dtype(DTYPES[a["componentType"]])
    width = COMPONENTS[a["type"]]
    data = np.ndarray((a["count"], width), dtype=dtype, buffer=body,
                      offset=view.get("byteOffset", 0) + a.get("byteOffset", 0),
                      strides=(view.get("byteStride", width * dtype.itemsize), dtype.itemsize)).copy()
    if normalized and a.get("normalized"):
        maximum = np.iinfo(dtype).max
        data = np.maximum(-1, data.astype(np.float64) / maximum)
    return data


def node_matrix(node):
    if "matrix" in node:
        return np.asarray(node["matrix"], float).reshape(4, 4, order="F")
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    rotation = np.array([[1-2*y*y-2*z*z, 2*x*y-2*z*w, 2*x*z+2*y*w],
                         [2*x*y+2*z*w, 1-2*x*x-2*z*z, 2*y*z-2*x*w],
                         [2*x*z-2*y*w, 2*y*z+2*x*w, 1-2*x*x-2*y*y]])
    result = np.eye(4)
    result[:3, :3] = rotation @ np.diag(node.get("scale", [1, 1, 1]))
    result[:3, 3] = node.get("translation", [0, 0, 0])
    return result


def node_frames(document):
    parents = {}
    for i, node in enumerate(document.get("nodes", [])):
        for child in node.get("children", []):
            if child in parents:
                raise ValueError("trial requires a scene tree, not multiply parented nodes")
            parents[child] = i
    frames, paths = {}, {}
    def visit(i, active):
        if i in active:
            raise ValueError("cyclic node hierarchy")
        if i in frames:
            return
        node = document["nodes"][i]
        parent = parents.get(i)
        if parent is not None:
            visit(parent, active | {i})
        frames[i] = (frames[parent] if parent is not None else np.eye(4)) @ node_matrix(node)
        paths[i] = (paths[parent] + "/" if parent is not None else "") + node.get("name", str(i))
    for i in range(len(document.get("nodes", []))):
        visit(i, set())
    return frames, paths, parents


def compact_collision(positions, indices):
    """Preserve indexed corner bytes, including signed zero, while sharing XYZ."""
    positions = np.asarray(positions, dtype="<f4")
    records = np.ascontiguousarray(positions).view(np.dtype((np.void, 12))).reshape(-1)
    used = np.unique(indices)
    _, first, inverse = np.unique(records[used], return_index=True, return_inverse=True)
    packed = positions[used[first]]
    mapping = np.full(len(positions), -1, dtype=np.int64)
    mapping[used] = inverse
    remapped = mapping[indices]
    dtype = "<u2" if len(packed) <= 65536 else "<u4"
    remapped = remapped.astype(dtype)
    if packed[remapped].tobytes() != positions[indices].tobytes():
        raise AssertionError("collision triangle corner bytes changed")
    return packed, remapped


def source_roads(root, region, chunks, road_ids):
    records, sources = [], {}
    for chunk in chunks:
        directory = root / f"eloria-assets/maps/continent-v2/{region}/client/chunks/{chunk}"
        manifest = json.loads((directory / "world.json").read_text(encoding="utf-8-sig"))
        path = directory / manifest["asset"]["glb"]
        document, body = SM.read_glb(path)
        frames, paths, parents = node_frames(document)
        sources[chunk] = dict(directory=directory, manifest=manifest, path=path,
                              document=document, body=body, frames=frames)
        for ni, node in enumerate(document["nodes"]):
            match = next((rid for rid in road_ids if node.get("name") == f"Walk_{region}_{rid}_{region}_{chunk}"), None)
            if match is None or "mesh" not in node:
                continue
            mesh = document["meshes"][node["mesh"]]
            for pi, primitive in enumerate(mesh["primitives"]):
                if primitive.get("mode", 4) != 4 or primitive.get("targets"):
                    raise ValueError("road trial requires static triangle primitives")
                attributes = primitive["attributes"]
                positions = accessor(document, body, attributes["POSITION"], False)
                if positions.dtype != np.dtype("<f4"):
                    raise ValueError("road collision positions must already be float32")
                indices = (accessor(document, body, primitive["indices"], False).reshape(-1)
                           if "indices" in primitive else np.arange(len(positions)))
                uv = accessor(document, body, attributes["TEXCOORD_0"])
                colors = (accessor(document, body, attributes["COLOR_0"])
                          if "COLOR_0" in attributes else np.ones((len(positions), 4)))
                if colors.shape[1] == 3:
                    colors = np.column_stack((colors, np.ones(len(colors))))
                if not np.allclose(colors[:, :3], colors[0, :3], atol=0, rtol=0):
                    raise ValueError("varying RGB requires an explicit additional color field")
                world = (frames[ni] @ np.column_stack((positions, np.ones(len(positions)))).T).T[:, :3]
                records.append(dict(chunk=chunk, road_id=match, node_index=ni, node_path=paths[ni],
                                    road_node_name=node["name"], parent_node_index=parents.get(ni),
                                    primitive_index=pi, mesh_index=node["mesh"], positions=positions,
                                    indices=indices, triangles=world[indices].reshape(-1, 3, 3),
                                    uv=uv[indices].reshape(-1, 3, 2), alpha=colors[indices, 3].reshape(-1, 3),
                                    source_vertex_rgb=colors[0, :3].tolist(),
                                    world_matrix=frames[ni].reshape(-1, order="F").tolist(),
                                    material_index=primitive.get("material")))
        found = {r["road_id"] for r in records if r["chunk"] == chunk}
        if found != set(road_ids):
            raise ValueError(f"{chunk}: expected explicit roads {road_ids}, found {sorted(found)}")
    return sources, records


def grid_for(triangles, ppm, gutter=2):
    xz = triangles[..., [0, 2]].reshape(-1, 2)
    first = np.floor(xz.min(axis=0) * ppm).astype(int) - gutter
    last = np.ceil(xz.max(axis=0) * ppm).astype(int) + gutter
    return dict(origin_xz=(first / ppm).tolist(), width=int(last[0]-first[0]),
                height=int(last[1]-first[1]), pixels_per_metre=ppm, gutter_pixels=gutter,
                axis_order="row_increasing_z,column_increasing_x", sample="pixel_centres")


def rasterize(triangles, uv, alpha, grid, max_sheets=8):
    """Retain distinct overlapping UV/alpha sheets rather than flatten junctions."""
    h, w = grid["height"], grid["width"]
    ppm = grid["pixels_per_metre"]
    origin = np.asarray(grid["origin_xz"])
    sheets, overlap_pixels = [], 0
    def add_sheet():
        sheets.append(dict(uv=np.zeros((h, w, 2), np.float64), alpha=np.zeros((h, w), np.float64),
                           valid=np.zeros((h, w), bool)))
    add_sheet()
    for tri, values, cover in zip(triangles, uv, alpha):
        pixel = (tri[:, [0, 2]] - origin) * ppm - .5
        lo = np.maximum(0, np.ceil(pixel.min(axis=0)-1e-7).astype(int))
        hi = np.minimum([w-1, h-1], np.floor(pixel.max(axis=0)+1e-7).astype(int))
        if np.any(hi < lo):
            continue
        ax, ay = pixel[0]; bx, by = pixel[1]; cx, cy = pixel[2]
        determinant = (by-cy)*(ax-cx)+(cx-bx)*(ay-cy)
        if abs(determinant) < 1e-12:
            continue
        xx, yy = np.meshgrid(np.arange(lo[0], hi[0]+1), np.arange(lo[1], hi[1]+1))
        a = ((by-cy)*(xx-cx)+(cx-bx)*(yy-cy))/determinant
        b = ((cy-ay)*(xx-cx)+(ax-cx)*(yy-cy))/determinant
        c = 1-a-b
        inside = (a >= -1e-7) & (b >= -1e-7) & (c >= -1e-7)
        yy, xx = yy[inside], xx[inside]
        weights = np.column_stack((a[inside], b[inside], c[inside]))
        if not len(xx):
            continue
        mapped, coverage = weights @ values, np.clip(weights @ cover, 0, 1)
        active = coverage > 0
        yy, xx, mapped, coverage = yy[active], xx[active], mapped[active], coverage[active]
        if not len(xx):
            continue
        sheet_index = 0
        for i, sheet in enumerate(sheets):
            occupied = sheet["valid"][yy, xx]
            different = ((np.max(np.abs(sheet["uv"][yy, xx]-mapped), axis=1) > 2e-4)
                         | (np.abs(sheet["alpha"][yy, xx]-coverage) > 1/255))
            conflicts = occupied & different
            if conflicts.any():
                sheet_index = max(sheet_index, i+1)
                overlap_pixels += int(conflicts.sum())
        if sheet_index >= max_sheets:
            raise ValueError("road overlap exceeds eight ordered sheets; no visual fallback is allowed")
        while len(sheets) <= sheet_index:
            add_sheet()
        sheet = sheets[sheet_index]
        sheet["uv"][yy, xx], sheet["alpha"][yy, xx], sheet["valid"][yy, xx] = mapped, coverage, True
    return sheets, overlap_pixels


def fill_uv(uv, valid):
    if not valid.any():
        return np.zeros_like(uv, dtype="<f4")
    nearest = distance_transform_edt(~valid, return_distances=False, return_indices=True)
    return np.asarray(uv[tuple(nearest)], dtype="<f4")


def mip_chain(uv, coverage):
    """Coverage-weighted flow mips; void texels cannot pull valid UV toward zero."""
    result = []
    while True:
        uv = fill_uv(uv, coverage > 0)
        result.append((uv, coverage.copy()))
        h, w = coverage.shape
        if h == 1 and w == 1:
            return result
        # Godot's mip dimensions floor odd sides. Average the corresponding
        # equal world-space bins so every original texel contributes.
        nh, nw = max(1, h//2), max(1, w//2)
        rows = np.minimum(nh-1, np.arange(h)*nh//h)
        cols = np.minimum(nw-1, np.arange(w)*nw//w)
        slots = (rows[:, None]*nw+cols[None, :]).reshape(-1)
        weight = np.bincount(slots, weights=coverage.reshape(-1), minlength=nh*nw)
        count = np.bincount(slots, minlength=nh*nw)
        next_uv = np.column_stack([np.bincount(slots, weights=(uv[...,i]*coverage).reshape(-1),
                                              minlength=nh*nw) for i in range(2)])
        next_uv /= np.maximum(weight[:, None], 1e-30)
        uv = next_uv.reshape(nh, nw, 2)
        coverage = (weight/count).reshape(nh, nw)


def crop_sheet(sheet, grid):
    """Keep a two-texel halo around this sheet, not the other overlap sheets."""
    rows, cols = np.nonzero(sheet["valid"])
    if not len(rows):
        return sheet, grid
    gutter = grid.get("gutter_pixels", 2)
    x0, x1 = max(0, int(cols.min())-gutter), min(grid["width"], int(cols.max())+gutter+1)
    z0, z1 = max(0, int(rows.min())-gutter), min(grid["height"], int(rows.max())+gutter+1)
    cropped = {k:v[z0:z1,x0:x1].copy() for k,v in sheet.items()}
    frame = copy.deepcopy(grid)
    frame["origin_xz"] = (np.asarray(grid["origin_xz"])+np.array([x0,z0])/grid["pixels_per_metre"]).tolist()
    frame.update(width=x1-x0, height=z1-z0)
    return cropped, frame


def store_fields(directory, stem, sheet, codec="zstd"):
    levels, flow, offset = [], bytearray(), 0
    coverage_error = 0.0
    for i, (uv, coverage) in enumerate(mip_chain(sheet["uv"], sheet["alpha"])):
        pixels = np.rint(np.clip(coverage, 0, 1)*255).astype(np.uint8)
        coverage_error = max(coverage_error, float(np.max(np.abs(pixels/255-coverage))))
        name = f"{stem}.coverage-mip{i}.png"
        Image.fromarray(pixels).save(directory/name, optimize=True)
        body = uv.astype("<f4").tobytes()
        levels.append(dict(level=i, width=uv.shape[1], height=uv.shape[0], coverage=name,
                           coverage_sha256=sha((directory/name).read_bytes()),
                           coverage_decoded_sha256=sha(pixels.tobytes()),
                           uv_offset_bytes=offset, uv_bytes=len(body)))
        flow.extend(body); offset += len(body)
    raw = bytes(flow)
    encoded = zstandard.ZstdCompressor(level=8).compress(raw) if codec == "zstd" else raw
    decoded = zstandard.ZstdDecompressor().decompress(encoded, max_output_size=len(raw)) if codec == "zstd" else encoded
    if decoded != raw:
        raise AssertionError("stored flow codec changed float32 mip bytes")
    name = f"{stem}.uv.f32" + (".zst" if codec == "zstd" else "")
    (directory/name).write_bytes(encoded)
    return dict(uv_file=name, uv_format="RG32F", uv_byte_order="little", coverage_format="R8_UNORM_PNG",
                uv_compression=codec, uv_uncompressed_bytes=len(raw), uv_sha256=sha(raw), uv_file_sha256=sha(encoded),
                uv_codec_roundtrip_byte_identical=True,
                uv_outside="nearest_valid", mip_filter="coverage_weighted_uv,area_average_coverage", mips=levels,
                max_coverage_quantization_error=1/510,
                measured_coverage_quantization_error=coverage_error,
                measured_base_uv_float32_error=float(np.max(np.abs(sheet["uv"].astype("<f4")-sheet["uv"])[sheet["valid"]])),
                covered_pixel_count=int(np.count_nonzero(sheet["valid"])))


def material_document(source, record):
    d = source["document"]
    material = copy.deepcopy(d["materials"][record["material_index"]])
    textures, images, samplers = [], [], []
    texture_map, image_map, sampler_map = {}, {}, {}
    def texture(index):
        if index not in texture_map:
            value = copy.deepcopy(d["textures"][index])
            if "source" in value:
                old = value["source"]
                if old not in image_map:
                    image_map[old] = len(images); images.append(copy.deepcopy(d["images"][old]))
                value["source"] = image_map[old]
            if "sampler" in value:
                old = value["sampler"]
                if old not in sampler_map:
                    sampler_map[old] = len(samplers); samplers.append(copy.deepcopy(d["samplers"][old]))
                value["sampler"] = sampler_map[old]
            texture_map[index] = len(textures); textures.append(value)
        return texture_map[index]
    def walk(value):
        if isinstance(value, dict):
            for k,v in value.items():
                if k.endswith("Texture") and isinstance(v, dict) and "index" in v:
                    v["index"] = texture(v["index"])
                else: walk(v)
        elif isinstance(value, list):
            for v in value: walk(v)
    walk(material)
    return dict(asset={"version":"2.0"}, materials=[material],
                textures=textures, images=images, samplers=samplers)


def rebase_manifest(source, directory, glb_path):
    manifest = copy.deepcopy(source["manifest"])
    original = source["directory"]
    def walk(value):
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, str) and not value.startswith(("res://", "user://", "http:" , "https:")):
            candidate = original/value
            if len(value) < 512 and re.search(r"\.[a-zA-Z0-9]{2,6}$", value) and candidate.is_file():
                return relative(candidate, directory)
        return value
    manifest = walk(manifest)
    manifest["asset"]["glb"] = relative(glb_path, directory)
    manifest["externalMeshes"] = {relative(original/u, directory):h for u,h in source["manifest"].get("externalMeshes", {}).items()}
    # Image URIs are resolved from the GLB directory, not the manifest's.
    manifest["externalResources"] = {relative(original/u, glb_path.parent):h
                                     for u,h in source["manifest"].get("externalResources", {}).items()}
    manifest.setdefault("performance", {})["glbBytes"] = glb_path.stat().st_size
    manifest["roadTextureTrial"] = {"schema":SCHEMA, "metadata":"trial.json", "production":False}
    return manifest


def prune_visual_roads(source, records, destination):
    d = copy.deepcopy(source["document"])
    selected = {r["node_index"] for r in records}
    for ni in selected:
        d["nodes"][ni].pop("mesh")
    used = {n["mesh"] for n in d["nodes"] if "mesh" in n}
    mapping = {old:new for new,old in enumerate(sorted(used))}
    d["meshes"] = [d["meshes"][i] for i in sorted(used)]
    for node in d["nodes"]:
        if "mesh" in node:
            node["mesh"] = mapping[node["mesh"]]
    d, body = SM._prune(d, source["body"])
    for image in d.get("images", []):
        if "uri" in image and not image["uri"].startswith("data:"):
            image["uri"] = relative(source["directory"]/image["uri"], destination.parent)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(SM.write_glb(d, body))
    for ni in selected:
        if "mesh" in d["nodes"][ni]:
            raise AssertionError("original visual road retained")
    return d


def source_closure(root, region, chunks):
    files = set()
    for chunk in chunks:
        directory = root/f"eloria-assets/maps/continent-v2/{region}/client/chunks/{chunk}"
        path = directory/"world.json"
        d = json.loads(path.read_text(encoding="utf-8-sig"))
        glb = directory/d["asset"]["glb"]
        files.update((path, glb))
        files.update(glb.parent/u for u in d.get("externalResources", {}))
        for uri in d.get("externalMeshes", {}):
            p = directory/uri
            files.update((p, p.parent/"index.json"))
        def collect(value):
            if isinstance(value, dict):
                for v in value.values(): collect(v)
            elif isinstance(value, list):
                for v in value: collect(v)
            elif isinstance(value, str) and value.startswith("res://"):
                p = root/"godot-client"/value.removeprefix("res://")
                if p.is_file(): files.add(p)
        collect(d.get("biomeBlend", {}))
        collect(d.get("objectMaterialOverrides", {}))
    return files


def inventory(paths):
    unique, seen = {}, set()
    stored_bytes = compressed_bytes = 0
    for path in paths:
        canonical = os.path.normcase(os.path.abspath(path))
        if canonical in seen:
            continue
        seen.add(canonical)
        data = path.read_bytes()
        compressed = len(zlib.compress(data, 6))
        stored_bytes += len(data)
        compressed_bytes += compressed
        key = sha(data)
        entry = unique.setdefault(key, dict(bytes=len(data), zlib6_bytes=compressed, paths=[]))
        entry["paths"].append(str(path))
    return dict(unique_files=len(seen), unique_contents=len(unique), bytes=stored_bytes,
                zlib6_bytes=compressed_bytes,
                content_deduplicated_bytes=sum(r["bytes"] for r in unique.values()),
                content_deduplicated_zlib6_bytes=sum(r["zlib6_bytes"] for r in unique.values()),
                policy="each_normalized_file_path_once;fullfiles,zlib6_eachfile;all_stored_mips_counted;content_dedup_is_separate_potential",
                files=unique)


def validate_variant(variant):
    """Verify actual stored bytes, collider corners, and adjacent mask halos."""
    index = json.loads((variant/"trial.json").read_text())
    failures, nodes, fields, samples = [], 0, 0, []
    for name in index["chunks"]:
        path = variant/name
        metadata = json.loads(path.read_text())
        directory = path.parent
        manifest = json.loads((directory/"world.json").read_text())
        base, _ = SM.read_glb(directory/manifest["asset"]["glb"])
        for node in metadata["nodes"]:
            collision = node["collision"]
            raw_positions = (directory/collision["positions"]).read_bytes()
            raw_indices = (directory/collision["indices"]).read_bytes()
            positions = np.frombuffer(raw_positions, dtype="<f4").reshape(-1,3)
            indices = np.frombuffer(raw_indices, dtype=DTYPES[collision["index_component_type"]])
            if sha(raw_positions) != collision["positions_sha256"] or sha(raw_indices) != collision["indices_sha256"]:
                failures.append("collision_file_hash:"+node["road_node_name"])
            if sha(positions[indices].tobytes()) != collision["expanded_triangle_positions_sha256"]:
                failures.append("collision_corner_bytes:"+node["road_node_name"])
            if "mesh" in base["nodes"][node["node_index"]]:
                failures.append("original_visual_retained:"+node["road_node_name"])
            nodes += 1
        by_road = {}
        for layer in metadata["layers"]:
            encoded = (directory/layer["uv_file"]).read_bytes()
            raw = (zstandard.ZstdDecompressor().decompress(encoded, max_output_size=layer["uv_uncompressed_bytes"])
                   if layer["uv_compression"] == "zstd" else encoded)
            if sha(encoded) != layer["uv_file_sha256"] or sha(raw) != layer["uv_sha256"]:
                failures.append("flow_hash:"+layer["uv_file"])
            if len(raw) != layer["uv_uncompressed_bytes"]:
                failures.append("flow_size:"+layer["uv_file"])
            for mip in layer["mips"]:
                png = (directory/mip["coverage"]).read_bytes()
                pixels = np.asarray(Image.open(directory/mip["coverage"]).convert("L"))
                if sha(png) != mip["coverage_sha256"] or sha(pixels.tobytes()) != mip["coverage_decoded_sha256"]:
                    failures.append("coverage_hash:"+mip["coverage"])
                if pixels.shape != (mip["height"],mip["width"]):
                    failures.append("coverage_dimensions:"+mip["coverage"])
                if mip["uv_bytes"] != mip["width"]*mip["height"]*8:
                    failures.append("flow_mip_dimensions:"+layer["uv_file"])
            mip = layer["mips"][0]
            uv = np.frombuffer(raw, dtype="<f4", count=mip["width"]*mip["height"]*2,
                               offset=mip["uv_offset_bytes"]).reshape(mip["height"],mip["width"],2)
            coverage = np.asarray(Image.open(directory/mip["coverage"]).convert("L"))
            grid = layer["grid"]
            origin = np.rint(np.asarray(grid["origin_xz"])*grid["pixels_per_metre"]).astype(int)
            road = by_road.setdefault(layer["road_id"], {})
            yy, xx = np.nonzero(coverage)
            for y,x in zip(yy,xx):
                road.setdefault((int(origin[0]+x),int(origin[1]+y)), []).append((int(coverage[y,x]),uv[y,x].copy()))
            fields += 1
        for node in metadata["nodes"]:
            grid = node["raster_grid"]
            origin = np.rint(np.asarray(grid["origin_xz"])*grid["pixels_per_metre"]).astype(int)
            samples.append(dict(chunk=metadata["chunk"], road_id=node["road_id"],
                                first=origin, last=origin+[grid["width"],grid["height"]],
                                pixels=by_road.get(node["road_id"], {})))
    seam_checks = []
    for ai,a in enumerate(samples):
        for b in samples[ai+1:]:
            if a["chunk"] == b["chunk"] or a["road_id"] != b["road_id"]:
                continue
            first,last = np.maximum(a["first"],b["first"]),np.minimum(a["last"],b["last"])
            keys = [k for k in a["pixels"].keys()|b["pixels"].keys()
                    if np.all(np.asarray(k)>=first) and np.all(np.asarray(k)<last)]
            mismatch, max_uv_error, max_alpha_error = 0,0.,0
            for key in keys:
                aa,bb = a["pixels"].get(key,[]),b["pixels"].get(key,[])
                if len(aa) != len(bb):
                    mismatch += 1
                    continue
                for x,y in zip(aa,bb):
                    max_alpha_error=max(max_alpha_error,abs(x[0]-y[0]))
                    max_uv_error=max(max_uv_error,float(np.max(np.abs(x[1]-y[1]))))
                    mismatch += int(abs(x[0]-y[0])>1 or np.max(np.abs(x[1]-y[1]))>1e-3)
            seam_checks.append(dict(road_id=a["road_id"], chunks=[a["chunk"],b["chunk"]],
                                   covered_pixel_samples=len(keys),mismatched_fragments=mismatch,
                                   maximum_uv_error=max_uv_error,maximum_alpha_lsb_error=max_alpha_error))
            if mismatch:
                failures.append("adjacent_gutter_fragments:"+a["road_id"])
    return dict(ok=not failures,failures=failures,exact_collision_primitives=nodes,
                stored_flow_and_all_mips_verified=fields,seam_checks=seam_checks)


def bake(root, original_root, out, region, chunks, road_ids, ppms=(2,4), uv_codec="zstd"):
    root, original_root, out = Path(root).absolute(), Path(original_root).absolute(), Path(out).absolute()
    if out.exists():
        raise ValueError("output must be a fresh ignored directory")
    asset_root = root/"eloria-assets/maps"
    if not out.is_relative_to(asset_root) or ".local" not in out.relative_to(asset_root).parts:
        raise ValueError("output must be under this source's eloria-assets/maps/**/.local/")
    checked = subprocess.run(["git", "check-ignore", "--quiet", str(out/"trial.json")], cwd=root)
    if checked.returncode:
        raise ValueError("trial destination is not Git ignored")
    sources, roads = source_roads(root, region, chunks, road_ids)
    out.mkdir(parents=True)
    common = []
    for chunk, source in sources.items():
        chunk_roads = [r for r in roads if r["chunk"] == chunk]
        directory = out/"common"/chunk
        base = directory/"base.glb"
        prune_visual_roads(source, chunk_roads, base)
        common.append(base)
        for r in chunk_roads:
            positions, indices = compact_collision(r["positions"], r["indices"])
            stem = f"collision-{r['node_index']}-{r['primitive_index']}"
            p, i = directory/(stem+".positions.f32"), directory/(stem+".indices.bin")
            p.write_bytes(positions.tobytes()); i.write_bytes(indices.tobytes())
            common.extend((p,i))
            r["collision"] = dict(positions=str(p), indices=str(i), vertex_count=len(positions),
                                  index_count=len(indices), index_component_type=5123 if indices.dtype.itemsize==2 else 5125,
                                  positions_sha256=sha(p.read_bytes()), indices_sha256=sha(i.read_bytes()),
                                  expanded_triangle_positions_sha256=sha(r["positions"][r["indices"]].tobytes()),
                                  expanded_triangle_positions_byte_identical=True, space="original_node_local")
    dependencies = source_closure(root, region, chunks)
    source_payloads = {s["path"] for s in sources.values()} | {s["directory"]/"world.json" for s in sources.values()}
    dependencies -= source_payloads
    report = dict(schema=SCHEMA, region=region, chunks=chunks, road_ids=list(road_ids),
                  original=inventory(source_closure(original_root, region, chunks)),
                  consolidated=inventory(source_closure(root, region, chunks)), variants={})
    for ppm in ppms:
        variant = out/f"{ppm}ppm"
        generated = list(common)
        chunk_metadata = []
        for chunk, source in sources.items():
            directory = variant/"chunks"/chunk
            directory.mkdir(parents=True)
            chunk_roads = [r for r in roads if r["chunk"] == chunk]
            metadata = dict(schema=SCHEMA, chunk=chunk, region=region, pixels_per_metre=ppm,
                            source_directory=str(source["directory"]), source_glb_sha256=sha(source["path"].read_bytes()),
                            terrain_node_names=[n.get("name") for n in source["document"]["nodes"]
                                                if n.get("name", "").startswith("Terrain_") and "mesh" in n],
                            road_visual_lift_metres=.055, normal_policy="underlying_terrain_flat_derivative_and_source_detail_normal",
                            geometry_policy="no_source_coordinate_or_material_changes;no_original_visual_road_fallback",
                            layers=[], nodes=[])
            for r in chunk_roads:
                same = [s for s in roads if (s["road_id"],s["primitive_index"]) == (r["road_id"],r["primitive_index"])]
                grid = grid_for(r["triangles"], ppm)
                sheets, conflicts = rasterize(np.concatenate([s["triangles"] for s in same]),
                                              np.concatenate([s["uv"] for s in same]),
                                              np.concatenate([s["alpha"] for s in same]), grid)
                collision = copy.deepcopy(r["collision"])
                for key in ("positions","indices"):
                    collision[key] = relative(Path(collision[key]), directory)
                node = {k:r[k] for k in ("node_index","node_path","road_node_name","parent_node_index",
                                         "primitive_index","world_matrix")}
                node["collision"] = collision
                node["original_material_name"] = source["document"]["materials"][r["material_index"]].get("name", "")
                node.update(road_id=r["road_id"], raster_grid=grid)
                metadata["nodes"].append(node)
                for sheet_index, sheet in enumerate(sheets):
                    if not sheet["valid"].any(): continue
                    stem = f"road-{r['node_index']}-{r['primitive_index']}-{sheet_index}"
                    sheet, sheet_grid = crop_sheet(sheet, grid)
                    fields = store_fields(directory, stem, sheet, uv_codec)
                    material = material_document(source,r)
                    selected_images = {im["uri"] for im in material["images"] if "uri" in im}
                    external = {u:h for u,h in source["manifest"].get("externalResources", {}).items() if u in selected_images}
                    metadata["layers"].append(dict(**node, **fields, grid=sheet_grid,
                                                  sheet_index=sheet_index, draw_order=len(metadata["layers"]),
                                                  source_vertex_rgb=r["source_vertex_rgb"],
                                                  source_directory=str(source["directory"]),
                                                  material_document=material, externalResources=external,
                                                  overlap_conflict_pixel_events=conflicts))
            write_json(directory/"trial.json", metadata)
            manifest = rebase_manifest(source, directory, out/"common"/chunk/"base.glb")
            write_json(directory/"world.json", manifest)
            chunk_metadata.append(relative(directory/"trial.json", variant))
        write_json(variant/"trial.json", dict(schema=SCHEMA, region=region, ppm=ppm, chunks=chunk_metadata))
        validation = validate_variant(variant)
        write_json(out/f"validation-{ppm}ppm.json", validation)
        if not validation["ok"]:
            raise ValueError(f"stored trial validation failed: {validation['failures']}")
        generated.extend(p for p in variant.rglob("*") if p.is_file())
        variant_inventory = inventory(set(generated)|dependencies)
        variant_inventory["generated_only"] = inventory(set(generated))
        variant_inventory["validation"] = validation
        report["variants"][str(ppm)] = variant_inventory
    write_json(out/"storage-report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--original-root", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--region", default="suncoil")
    parser.add_argument("--chunk", action="append", dest="chunks")
    parser.add_argument("--road-id", action="append", dest="roads")
    parser.add_argument("--uv-codec", choices=("none","zstd"), default="zstd")
    args = parser.parse_args()
    out = args.out or args.source_root/f"eloria-assets/maps/continent-v2/{args.region}/client/.local/road-texture-trial"
    report = bake(args.source_root, args.original_root or args.source_root, out, args.region,
                  args.chunks or ["06_09","06_10"], args.roads or DEFAULT_ROADS, uv_codec=args.uv_codec)
    print(json.dumps({"out":str(out), "original_bytes":report["original"]["bytes"],
                      "consolidated_bytes":report["consolidated"]["bytes"],
                      "variants":{k:{f:v[f] for f in ("bytes","zlib6_bytes")} for k,v in report["variants"].items()}}, indent=2))


if __name__ == "__main__":
    main()
