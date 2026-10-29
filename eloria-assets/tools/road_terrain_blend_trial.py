"""Produce a fresh, single-field Suncoil terrain-road blending experiment.

This deliberately approximates overlapping road appearances: coverage is the
maximum interpolated source alpha, and UV comes from the highest-alpha source
fragment, with the last authored triangle winning ties. It does not combine
independent source texture samples or claim appearance equality. All selected
roads must have exactly equivalent PBR/image/sampler definitions. Collision
corner bytes and original placeholder names are retained without approximation.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image
import zstandard

import road_texture_trial as T

SCHEMA = "rabbitlands-road-terrain-blend-trial-v1"
MAX_PIXELS = 4_194_304
JACOBIAN_COMPONENTS = ["dU_dX","dU_dZ","dV_dX","dV_dZ"]


def affine_uv_jacobians(triangles, uv):
    """Authored affine UV derivatives in the same world-XZ frame as the mask."""
    xz = np.asarray(triangles,float)[...,[0,2]]
    delta = np.asarray(uv,float)[:,1:] - np.asarray(uv,float)[:,:1]
    edge = xz[:,1:] - xz[:,:1]
    determinant = edge[:,0,0]*edge[:,1,1]-edge[:,0,1]*edge[:,1,0]
    valid = np.abs(determinant) >= 1e-16
    result = np.zeros((len(xz),4),float)
    # Degenerate projected faces have no raster samples. Keep a finite unused
    # sentinel rather than manufacturing a footprint for those faces.
    a,b = edge[valid,0,0],edge[valid,0,1]
    c,d = edge[valid,1,0],edge[valid,1,1]
    du,dv = delta[valid,:,0],delta[valid,:,1]
    det = determinant[valid]
    result[valid] = np.column_stack(((d*du[:,0]-b*du[:,1])/det,
                                     (-c*du[:,0]+a*du[:,1])/det,
                                     (d*dv[:,0]-b*dv[:,1])/det,
                                     (-c*dv[:,0]+a*dv[:,1])/det))
    if not np.isfinite(result).all():
        raise ValueError("nonfinite source affine UV Jacobian")
    return result


def store_jacobian(directory, stem, sheet, table):
    selected = sheet["selected_triangle"]
    valid = sheet["valid"]
    if np.any(selected[valid]<0):
        raise ValueError("covered field pixel has no authored triangle")
    values = np.zeros((*selected.shape,4),float)
    values[valid] = table[selected[valid]]
    packed = T.fill_uv(values,valid)
    if not np.isfinite(packed).all():
        raise ValueError("source Jacobian cannot be represented as finite RGBA32F")
    raw = packed.astype("<f4").tobytes()
    encoded = zstandard.ZstdCompressor(level=8).compress(raw)
    if zstandard.ZstdDecompressor().decompress(encoded,max_output_size=len(raw)) != raw:
        raise AssertionError("Jacobian codec changed authored derivative bytes")
    name = stem+".jacobian.rgba32f.zst"
    (directory/name).write_bytes(encoded)
    return dict(file=name,format="RGBA32F",byte_order="little",compression="zstd",
                width=selected.shape[1],height=selected.shape[0],components=JACOBIAN_COMPONENTS,
                mipmaps=False,uncompressed_bytes=len(raw),sha256=T.sha(raw),file_sha256=T.sha(encoded),
                codec_roundtrip_byte_identical=True,outside="nearest_valid",space="gltf_scene_world_xz",
                maximum_float32_abs_error=float(np.max(np.abs(packed[valid]-values[valid]))))


def read_jacobian(directory, metadata):
    if metadata.get("format") != "RGBA32F" or metadata.get("components") != JACOBIAN_COMPONENTS \
            or metadata.get("compression") != "zstd" or metadata.get("mipmaps") is not False:
        raise ValueError("invalid Jacobian format")
    encoded = (directory/metadata["file"]).read_bytes()
    if T.sha(encoded) != metadata["file_sha256"]:
        raise ValueError("Jacobian stored hash mismatch")
    raw = zstandard.ZstdDecompressor().decompress(encoded,max_output_size=metadata["uncompressed_bytes"])
    expected = metadata["width"]*metadata["height"]*16
    if len(raw) != expected or len(raw) != metadata["uncompressed_bytes"] or T.sha(raw) != metadata["sha256"]:
        raise ValueError("Jacobian decoded size or hash mismatch")
    values = np.frombuffer(raw,dtype="<f4").reshape(metadata["height"],metadata["width"],4)
    if not np.isfinite(values).all():
        raise ValueError("nonfinite stored Jacobian")
    return values


def field_plan(triangles, ppm):
    if not isinstance(ppm, int) or isinstance(ppm, bool) or ppm <= 0:
        raise ValueError("pixels per metre must be a positive integer")
    grid = T.grid_for(triangles, ppm)
    w, h = grid["width"], grid["height"]
    mip_pixels = 0
    levels = []
    while True:
        levels.append(dict(width=w, height=h))
        mip_pixels += w*h
        if w == 1 and h == 1:
            break
        w, h = max(1,w//2),max(1,h//2)
    return dict(grid=grid, fits_runtime_cap=grid["width"]*grid["height"] <= MAX_PIXELS,
                runtime_pixel_cap=MAX_PIXELS, mip_levels=levels,
                planned_rg32f_mip_bytes=mip_pixels*8, planned_r8_mip_bytes=mip_pixels,
                planned_rgba32f_jacobian_nomip_bytes=grid["width"]*grid["height"]*16,
                size_scope="uncompressed upper bound before sparse cropping; actual PNG/ZSTD files measured separately")


def dominant_raster(triangles, uv, alpha, grid):
    """One field; source UV is never averaged across overlapping fragments."""
    h,w,ppm = grid["height"],grid["width"],grid["pixels_per_metre"]
    if w*h > MAX_PIXELS:
        raise ValueError("single field exceeds the runtime 4M-pixel cap")
    if ppm <= 0:
        raise ValueError("pixels per metre must be positive")
    first = np.rint(np.asarray(grid["origin_xz"])*ppm).astype(np.int64)
    result = dict(uv=np.zeros((h,w,2),float),alpha=np.zeros((h,w),float),
                  valid=np.zeros((h,w),bool),selected_triangle=np.full((h,w),-1,np.int32),
                  contributors=np.zeros((h,w),np.uint32),ambiguous_uv=np.zeros((h,w),bool))
    for ordinal,(tri,values,cover) in enumerate(zip(triangles,uv,alpha)):
        projected = tri[:,[0,2]]
        pixel = projected*ppm-first-.5
        lo = np.maximum(0,np.ceil(pixel.min(axis=0)-1e-7).astype(int))
        hi = np.minimum([w-1,h-1],np.floor(pixel.max(axis=0)+1e-7).astype(int))
        if np.any(hi < lo):
            continue
        ax,az = projected[0];bx,bz = projected[1];cx,cz = projected[2]
        determinant = (bz-cz)*(ax-cx)+(cx-bx)*(az-cz)
        if abs(determinant) < 1e-16:
            continue
        xx,zz = np.meshgrid(np.arange(lo[0],hi[0]+1),np.arange(lo[1],hi[1]+1))
        # Evaluate from global integer texel addresses, so adjacent cropped
        # fields calculate exactly the same world point, including odd PPMs.
        wx,wz = (first[0]+xx+.5)/ppm,(first[1]+zz+.5)/ppm
        a = ((bz-cz)*(wx-cx)+(cx-bx)*(wz-cz))/determinant
        b = ((cz-az)*(wx-cx)+(ax-cx)*(wz-cz))/determinant
        c = 1-a-b
        inside = (a>=-1e-7)&(b>=-1e-7)&(c>=-1e-7)
        zz,xx = zz[inside],xx[inside]
        weights = np.column_stack((a[inside],b[inside],c[inside]))
        mapped,coverage = weights@values,np.clip(weights@cover,0,1)
        active = coverage>0
        zz,xx,mapped,coverage = zz[active],xx[active],mapped[active],coverage[active]
        if not len(xx):
            continue
        occupied = result["valid"][zz,xx]
        result["contributors"][zz,xx] += 1
        result["ambiguous_uv"][zz,xx] |= occupied & (np.max(np.abs(result["uv"][zz,xx]-mapped),axis=1)>2e-4)
        wins = ~occupied | (coverage >= result["alpha"][zz,xx])
        yy,xxx = zz[wins],xx[wins]
        result["uv"][yy,xxx] = mapped[wins]
        result["alpha"][yy,xxx] = coverage[wins]
        result["valid"][yy,xxx] = True
        result["selected_triangle"][yy,xxx] = ordinal
    return result


def material_identity(source, record):
    canonical = T.SM._material_identity(source["document"],source["body"],record["material_index"],source["path"],{})
    return T.sha(json.dumps(canonical,sort_keys=True,separators=(",",":")).encode())


def common_material(sources, roads):
    identities = {material_identity(sources[r["chunk"]],r) for r in roads}
    rgb = {tuple(r["source_vertex_rgb"]) for r in roads}
    if len(identities) != 1 or len(rgb) != 1:
        raise ValueError("single material field requires equivalent source PBR/images/samplers and vertex RGB")
    return next(iter(identities))


def validate_variant(variant):
    result = T.validate_variant(variant)
    # Every retained collider has the combined field's frame. The generic
    # validator verifies each collider, but that repeats the same seam pair.
    unique = {}
    for row in result["seam_checks"]:
        unique[(tuple(row["chunks"]),row["road_id"])] = row
    result["seam_checks"] = list(unique.values())
    index = json.loads((variant/"trial.json").read_text())
    jacobian_samples = []
    for relative in index["chunks"]:
        path = variant/relative
        d = json.loads(path.read_text())
        if d.get("schema") != SCHEMA or len(d.get("layers",[])) != 1:
            result["failures"].append("expected_one_combined_field:"+relative)
            continue
        layer = d["layers"][0]
        grid = layer["grid"]
        try:
            jacobian = read_jacobian(path.parent,layer["uv_jacobian"])
            if jacobian.shape[:2] != (grid["height"],grid["width"]):
                raise ValueError("Jacobian dimensions differ from field")
            coverage = np.asarray(Image.open(path.parent/layer["mips"][0]["coverage"]).convert("L"))
            origin = np.rint(np.asarray(grid["origin_xz"])*grid["pixels_per_metre"]).astype(int)
            jacobian_samples.append(dict(chunk=d["chunk"],origin=origin,jacobian=jacobian,coverage=coverage))
        except (ValueError,KeyError) as error:
            result["failures"].append("jacobian:"+relative+":"+str(error))
    result["jacobian_seam_checks"] = []
    for i,a in enumerate(jacobian_samples):
        for b in jacobian_samples[i+1:]:
            first = np.maximum(a["origin"],b["origin"])
            last = np.minimum(a["origin"]+[a["coverage"].shape[1],a["coverage"].shape[0]],
                              b["origin"]+[b["coverage"].shape[1],b["coverage"].shape[0]])
            if np.any(last<=first):
                continue
            samples=[]
            for item in (a,b):
                lo,hi = first-item["origin"],last-item["origin"]
                samples.append((item["jacobian"][lo[1]:hi[1],lo[0]:hi[0]],
                                item["coverage"][lo[1]:hi[1],lo[0]:hi[0]]))
            mask = (samples[0][1]>0)|(samples[1][1]>0)
            mismatch = int(np.count_nonzero(np.any(samples[0][0][mask]!=samples[1][0][mask],axis=1)))
            result["jacobian_seam_checks"].append(dict(chunks=[a["chunk"],b["chunk"]],
                                                       covered_pixel_samples=int(mask.sum()),mismatched_pixels=mismatch))
            if mismatch:
                result["failures"].append("Jacobian shared-gutter mismatch")
    result["stored_jacobians_verified"] = len(jacobian_samples)
    result["ok"] = not result["failures"]
    return result


def bake(root, original_root, out, region, chunks, road_ids, ppms=(2,4)):
    ppms = tuple(dict.fromkeys(ppms))
    if not ppms:
        raise ValueError("at least one pixels-per-metre variant is required")
    root,original_root,out = Path(root).resolve(),Path(original_root).resolve(),Path(out).resolve()
    if out.exists():
        raise ValueError("output must be a fresh ignored directory; prior generations are preserved")
    maps = root/"eloria-assets/maps"
    if not out.is_relative_to(maps) or ".local" not in out.relative_to(maps).parts:
        raise ValueError("trial output must remain in this source's eloria-assets/maps/**/.local/")
    if subprocess.run(["git","check-ignore","--quiet",str(out/"trial.json")],cwd=root).returncode:
        raise ValueError("trial output is not Git ignored")
    sources,roads = T.source_roads(root,region,chunks,road_ids)
    identity = common_material(sources,roads)
    triangles = np.concatenate([r["triangles"] for r in roads])
    flow = np.concatenate([r["uv"] for r in roads])
    alpha = np.concatenate([r["alpha"] for r in roads])
    if not all(np.isfinite(v).all() for v in (triangles,flow,alpha)):
        raise ValueError("source positions, UVs and alpha must be finite")
    jacobians = affine_uv_jacobians(triangles,flow)
    plans = {str(ppm):{chunk:field_plan(np.concatenate([r["triangles"] for r in roads if r["chunk"]==chunk]),ppm)
                      for chunk in chunks} for ppm in sorted(set(ppms)|{8})}
    if any(not plans[str(ppm)][chunk]["fits_runtime_cap"] for ppm in ppms for chunk in chunks):
        raise ValueError("requested field exceeds runtime pixel cap")
    out.mkdir(parents=True)
    common = []
    for chunk,source in sources.items():
        selected = [r for r in roads if r["chunk"]==chunk]
        directory = out/"common"/chunk
        base = directory/"base.glb"
        T.prune_visual_roads(source,selected,base)
        common.append(base)
        for r in selected:
            positions,indices = T.compact_collision(r["positions"],r["indices"])
            stem = f"collision-{r['node_index']}-{r['primitive_index']}"
            p,i = directory/(stem+".positions.f32"),directory/(stem+".indices.bin")
            p.write_bytes(positions.tobytes());i.write_bytes(indices.tobytes())
            common.extend((p,i))
            r["collision"] = dict(positions=str(p),indices=str(i),vertex_count=len(positions),index_count=len(indices),
                                  index_component_type=5123 if indices.dtype.itemsize==2 else 5125,
                                  positions_sha256=T.sha(p.read_bytes()),indices_sha256=T.sha(i.read_bytes()),
                                  expanded_triangle_positions_sha256=T.sha(r["positions"][r["indices"]].tobytes()),
                                  expanded_triangle_positions_byte_identical=True,space="original_node_local")
    dependencies = T.source_closure(root,region,chunks)
    dependencies -= {s["path"] for s in sources.values()}|{s["directory"]/"world.json" for s in sources.values()}
    report = dict(schema=SCHEMA,region=region,chunks=chunks,road_ids=list(road_ids),field_plans=plans,
                  material_identity_sha256=identity,
                  original=T.inventory(T.source_closure(original_root,region,chunks)),
                  consolidated=T.inventory(T.source_closure(root,region,chunks)),variants={},
                  appearance_limit="Dominant UV and maximum raw alpha collapse independent overlapping road samples; no appearance-equality claim.")
    for ppm in ppms:
        variant = out/f"{ppm}ppm"
        generated,chunk_paths = list(common),[]
        for chunk,source in sources.items():
            directory = variant/"chunks"/chunk
            directory.mkdir(parents=True)
            selected = [r for r in roads if r["chunk"]==chunk]
            record = selected[0]
            grid = plans[str(ppm)][chunk]["grid"]
            sheet = dominant_raster(triangles,flow,alpha,grid)
            overlap = dict(covered_pixels=int(sheet["valid"].sum()),
                           multiply_covered_pixels=int(np.count_nonzero(sheet["contributors"]>1)),
                           different_uv_overlap_pixels=int(sheet["ambiguous_uv"].sum()),
                           maximum_source_fragments_per_pixel=int(sheet["contributors"].max()))
            sheet,sheet_grid = T.crop_sheet(sheet,grid)
            fields = T.store_fields(directory,"combined-road",sheet,"zstd")
            fields["uv_jacobian"] = store_jacobian(directory,"combined-road",sheet,jacobians)
            material = T.material_document(source,record)
            images = {im["uri"] for im in material["images"] if "uri" in im}
            layer = dict(**fields,grid=sheet_grid,road_id="combined",road_node_name=record["road_node_name"],
                         road_node_names=[r["road_node_name"] for r in selected],node_index=record["node_index"],
                         node_path=record["node_path"],world_matrix=record["world_matrix"],primitive_index=0,
                         source_directory=str(source["directory"]),source_vertex_rgb=record["source_vertex_rgb"],
                         original_material_name=source["document"]["materials"][record["material_index"]].get("name",""),
                         material_document=material,externalResources={u:h for u,h in source["manifest"].get("externalResources",{}).items() if u in images},
                         sheet_index=0,draw_order=0,material_selection="one_equivalent_common_material",
                         mask_space="gltf_scene_world",coverage_policy="maximum_raw_interpolated_source_alpha",
                         uv_policy="highest_alpha_then_last_stable_authored_triangle",overlap=overlap,
                         source_alpha_float32_sha256=T.sha(alpha.astype("<f4").tobytes()),
                         source_uv_float32_sha256=T.sha(flow.astype("<f4").tobytes()),
                         source_jacobian_float32_sha256=T.sha(jacobians.astype("<f4").tobytes()),
                         selected_triangle_int32_sha256=T.sha(sheet["selected_triangle"].astype("<i4").tobytes()))
            metadata = dict(schema=SCHEMA,technique="terrain_single_pass",region=region,chunk=chunk,
                            pixels_per_metre=ppm,source_directory=str(source["directory"]),
                            source_glb_sha256=T.sha(source["path"].read_bytes()),material_identity_sha256=identity,
                            terrain_node_names=[n.get("name") for n in source["document"]["nodes"] if n.get("name","").startswith("Terrain_") and "mesh" in n],
                            visible_ground_node_names=[n.get("name") for n in source["document"]["nodes"] if n.get("name","").startswith("AuthoredGround_") and n.get("name","").endswith("Base_"+region+"_"+chunk) and "mesh" in n],
                            retained_geometry_space="original_node_local",mask_space="gltf_scene_world",
                            road_visual_lift_metres=0.0,source_road_visual_lift_metres=.055,
                            appearance_limit=report["appearance_limit"],layers=[layer],nodes=[])
            metadata["ground_node_names"] = list(metadata["visible_ground_node_names"])
            if len(metadata["ground_node_names"]) != 1:
                raise ValueError("single-pass trial requires exactly one visible authored Base ground node")
            for r in selected:
                collision = copy.deepcopy(r["collision"])
                for key in ("positions","indices"):
                    collision[key] = T.relative(Path(collision[key]),directory)
                node = {k:r[k] for k in ("node_index","node_path","road_node_name","parent_node_index","primitive_index","world_matrix")}
                node.update(collision=collision,original_material_name=source["document"]["materials"][r["material_index"]].get("name",""),
                            road_id="combined",source_road_id=r["road_id"],raster_grid=grid)
                metadata["nodes"].append(node)
            T.write_json(directory/"trial.json",metadata)
            manifest = T.rebase_manifest(source,directory,out/"common"/chunk/"base.glb")
            manifest["roadTextureTrial"] = dict(schema=SCHEMA,metadata="trial.json",technique="terrain_single_pass",production=False)
            T.write_json(directory/"world.json",manifest)
            chunk_paths.append(T.relative(directory/"trial.json",variant))
        T.write_json(variant/"trial.json",dict(schema=SCHEMA,technique="terrain_single_pass",region=region,ppm=ppm,chunks=chunk_paths))
        validation = validate_variant(variant)
        T.write_json(out/f"validation-{ppm}ppm.json",validation)
        if not validation["ok"]:
            raise ValueError(f"stored single-field validation failed: {validation['failures']}")
        generated.extend(p for p in variant.rglob("*") if p.is_file())
        result = T.inventory(set(generated)|dependencies)
        result.update(generated_only=T.inventory(generated),validation=validation)
        report["variants"][str(ppm)] = result
    T.write_json(out/"storage-report.json",report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root",type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument("--original-root",type=Path)
    parser.add_argument("--out",type=Path)
    parser.add_argument("--region",default="suncoil")
    parser.add_argument("--chunk",action="append",dest="chunks")
    parser.add_argument("--road-id",action="append",dest="roads")
    parser.add_argument("--ppm",type=int,action="append",dest="ppms",help="Repeatable; default 2 and 4; 8 is supported")
    args = parser.parse_args()
    out = args.out or args.source_root/f"eloria-assets/maps/continent-v2/{args.region}/client/.local/road-terrain-blend-trial"
    report = bake(args.source_root,args.original_root or args.source_root,out,args.region,args.chunks or ["06_09","06_10"],
                  args.roads or T.DEFAULT_ROADS,tuple(args.ppms or [2,4]))
    print(json.dumps(dict(out=str(out),original=report["original"]["bytes"],consolidated=report["consolidated"]["bytes"],
                         variants={k:{f:v[f] for f in ("bytes","zlib6_bytes")} for k,v in report["variants"].items()}),indent=2))


if __name__ == "__main__":
    main()
