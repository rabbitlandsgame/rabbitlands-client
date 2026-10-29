"""Audit and bake authored continent roads into validated terrain blend fields.

Authoring paths and bridge controls classify geometry before any visual removal.
Outputs are staging artifacts; publication is a separate deliberate operation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess

import numpy as np
from PIL import Image
import zstandard

import road_texture_trial as T
import road_terrain_blend_trial as B

SCHEMA = "rabbitlands-road-terrain-blend-v1"
COEFFICIENT_LAYOUT = ["u_at_grid_origin","v_at_grid_origin","dU_dX","dU_dZ",
                      "dV_dX","dV_dZ","style_id","reserved"]


def footstep_class(root, name):
    """Use the runtime's ordered name classification, including default dirt."""
    text=(Path(root)/"godot-client/src/audio/footstep_surface.gd").read_text()
    for surface,values in re.findall(r'"([a-z]+)": \[([^\]]+)\]',text):
        if any(keyword in name.lower() for keyword in re.findall(r'"([^"]+)"',values)):
            return surface
    return "dirt"


def authoring_catalog(root, region):
    """Read saved typed controls, rather than guessing semantics from node names."""
    path = Path(root)/f"godot-client/world_authoring/regions/{region}/{region}.tscn"
    text = path.read_text(encoding="utf-8-sig")
    ext = {identity:source for source,identity in re.findall(
        r'\[ext_resource[^\n]*path="([^"]+)"[^\n]*id="([^"]+)"\]',text)}
    roads, bridges, assets = {}, {}, {}
    for header,body in re.findall(r'\[node ([^\n]+)\]\n(.*?)(?=\n\[|\Z)',text,re.S):
        script = re.search(r'^script = ExtResource\("([^"]+)"\)',body,re.M)
        if not script:
            continue
        source = ext.get(script[1],"")
        if source.endswith("/map_authoring_region/path_control.gd"):
            identity = re.search(r'^path_id = "([^"]+)"',body,re.M)
            kind = re.search(r'^kind = "([^"]+)"',body,re.M)
            if identity and (kind[1] if kind else "road") == "road":
                roads[identity[1]] = dict(source_script=source,header=header)
        elif source.endswith("/bridge_control.gd"):
            identity = re.search(r'^bridge_id = "([^"]+)"',body,re.M)
            if identity:
                bridges[identity[1]] = dict(source_script=source,header=header)
        elif source.endswith("/asset_control.gd"):
            identity = re.search(r'^node_name = "([^"]+)"',body,re.M)
            scene = re.search(r'^scene_path = "([^"]+)"',body,re.M)
            if identity and scene:
                assets[identity[1]] = dict(source_script=source,scene_path=scene[1],header=header)
    return dict(path=str(path),sha256=T.sha(path.read_bytes()),roads=roads,bridges=bridges,assets=assets)


def served_regions(root):
    scope = json.loads((Path(root)/"godot-client/data/maps/geometry-cache-scope.json").read_text())
    return list(scope["groups"]["landfall_continent"])


def load_chunk(directory):
    manifest = json.loads((directory/"world.json").read_text(encoding="utf-8-sig"))
    path = directory/manifest["asset"]["glb"]
    document,body = T.SM.read_glb(path)
    frames,paths,parents = T.node_frames(document)
    return dict(directory=directory,manifest=manifest,path=path,document=document,body=body,
                frames=frames,paths=paths,parents=parents)


def load_chunk_for_glb(path):
    document,body=T.SM.read_glb(path)
    frames,paths,parents=T.node_frames(document)
    return dict(directory=path.parent,path=path,document=document,body=body,frames=frames,paths=paths,parents=parents)


def primitive_record(source, chunk, ni, pi, road_id):
    d,body = source["document"],source["body"]
    node = d["nodes"][ni]
    p = d["meshes"][node["mesh"]]["primitives"][pi]
    if p.get("mode",4) != 4 or p.get("targets"):
        raise ValueError("authored road requires static triangle geometry")
    a = p["attributes"]
    positions = T.accessor(d,body,a["POSITION"],False)
    if positions.dtype != np.dtype("<f4"):
        raise ValueError("road positions must already be float32")
    indices = T.accessor(d,body,p["indices"],False).reshape(-1) if "indices" in p else np.arange(len(positions))
    uv = T.accessor(d,body,a["TEXCOORD_0"])
    color = T.accessor(d,body,a["COLOR_0"]) if "COLOR_0" in a else np.ones((len(positions),4))
    if color.shape[1] == 3:
        color = np.column_stack((color,np.ones(len(color))))
    if not np.allclose(color[:,:3],color[0,:3],atol=0,rtol=0):
        raise ValueError("varying source road RGB requires an explicit color field")
    world = (source["frames"][ni]@np.column_stack((positions,np.ones(len(positions)))).T).T[:,:3]
    record = dict(chunk=chunk,road_id=road_id,node_index=ni,node_path=source["paths"][ni],
                  road_node_name=node["name"],parent_node_index=source["parents"].get(ni),
                  primitive_index=pi,mesh_index=node["mesh"],positions=positions,indices=indices,
                  triangles=world[indices].reshape(-1,3,3),uv=uv[indices].reshape(-1,3,2),
                  alpha=color[indices,3].reshape(-1,3),source_vertex_rgb=color[0,:3].tolist(),
                  world_matrix=source["frames"][ni].reshape(-1,order="F").tolist(),material_index=p.get("material"))
    if not all(np.isfinite(record[k]).all() for k in ("triangles","uv","alpha")):
        raise ValueError("nonfinite source road data")
    return record


def classify_walk(name, region, chunk, catalog, node_path=""):
    prefix,suffix = f"Walk_{region}_",f"_{region}_{chunk}"
    if name.startswith(prefix) and name.endswith(suffix):
        identity = name[len(prefix):-len(suffix)]
        if identity not in catalog["roads"]:
            raise ValueError(f"{region}/{chunk}: unverified authored road {name}")
        return "road",identity
    for identity in catalog["bridges"]:
        if name == f"Walk_AuthoredBridge_{region}__{identity}_{region}":
            return "bridge",identity
    if name.startswith("Walk_"):
        ancestors=node_path.split("/")[:-1]
        for ancestor in ancestors:
            if ancestor in catalog["assets"]:
                return "retained_asset_walk",ancestor
        raise ValueError(f"{region}/{chunk}: unclassified walk surface {name}")
    return None,None


def audit(root, regions=None):
    root = Path(root).resolve()
    report = dict(schema=SCHEMA,regions=[],styles={},failures=[])
    for region in regions or served_regions(root):
        catalog = authoring_catalog(root,region)
        region_manifest = root/f"eloria-assets/maps/continent-v2/{region}/client/world.json"
        manifest = json.loads(region_manifest.read_text())
        row = dict(region=region,authoring_scene_sha256=catalog["sha256"],authored_road_ids=sorted(catalog["roads"]),
                   authored_bridge_ids=sorted(catalog["bridges"]),chunks=[],styles=[],road_primitives=0,bridge_nodes=0)
        style_ids=set()
        for c in manifest["streamingChunks"]["chunks"]:
            chunk=c["id"];source=load_chunk((region_manifest.parent/c["manifest"]).parent)
            d=source["document"];styles=set();roads=[];bridges=[];cache={}
            for ni,node in enumerate(d.get("nodes",[])):
                if "mesh" not in node:
                    continue
                try:
                    role,identity=classify_walk(node.get("name",""),region,chunk,catalog,source["paths"][ni])
                except ValueError as error:
                    report["failures"].append(str(error));continue
                if role in ("bridge","retained_asset_walk"):
                    bridges.append(dict(node=node["name"],role=role,authoring_id=identity,node_path=source["paths"][ni]))
                if role!="road":continue
                for pi,p in enumerate(d["meshes"][node["mesh"]]["primitives"]):
                    record=primitive_record(source,chunk,ni,pi,identity)
                    canonical=T.SM._material_identity(d,source["body"],p.get("material"),source["path"],cache)
                    name=d["materials"][p["material"]].get("name","")
                    style=dict(material=canonical,vertex_rgb=record["source_vertex_rgb"],footstep_class=footstep_class(root,name))
                    digest=T.sha(json.dumps(style,sort_keys=True,separators=(",",":")).encode())
                    styles.add(digest);style_ids.add(digest)
                    entry=report["styles"].setdefault(digest,dict(canonical=style,names=[],regions=[]))
                    if name not in entry["names"]:entry["names"].append(name)
                    if region not in entry["regions"]:entry["regions"].append(region)
                    roads.append(dict(road_id=identity,node=node["name"],primitive=pi,style=digest,
                                      vertices=len(record["positions"]),triangles=len(record["triangles"])))
            ground=[n.get("name") for n in d["nodes"] if "mesh" in n and n.get("name")==f"AuthoredGround_{region}Base_{region}_{chunk}"]
            if roads and len(ground)!=1:report["failures"].append(f"{region}/{chunk}: expected exactly one authored Base")
            row["chunks"].append(dict(chunk=chunk,roads=roads,bridges=bridges,styles=sorted(styles),visible_ground_nodes=ground))
            row["road_primitives"]+=len(roads);row["bridge_nodes"]+=len(bridges)
        row["styles"]=sorted(style_ids);report["regions"].append(row)
    report["summary"]=dict(regions=len(report["regions"]),styles=len(report["styles"]),
                           chunks=sum(len(r["chunks"]) for r in report["regions"]),
                           road_chunks=sum(bool(c["roads"]) for r in report["regions"] for c in r["chunks"]),
                           maximum_styles_per_chunk=max((len(c["styles"]) for r in report["regions"] for c in r["chunks"]),default=0),
                           maximum_styles_per_region=max((len(r["styles"]) for r in report["regions"]),default=0))
    return report


def style_identity(source, record, cache, root):
    canonical=T.SM._material_identity(source["document"],source["body"],record["material_index"],source["path"],cache)
    name=source["document"]["materials"][record["material_index"]].get("name","")
    style=dict(material=canonical,vertex_rgb=record["source_vertex_rgb"],footstep_class=footstep_class(root,name))
    return T.sha(json.dumps(style,sort_keys=True,separators=(",",":")).encode())


def world_positions(source, ni, primitive):
    p=T.accessor(source["document"],source["body"],primitive["attributes"]["POSITION"],False)
    return (source["frames"][ni]@np.column_stack((p,np.ones(len(p)))).T).T[:,:3]


def terrain_lattice(sources):
    pieces=[]
    for source in sources.values():
        for ni,node in enumerate(source["document"]["nodes"]):
            if "mesh" in node and node.get("name","").startswith("Terrain_"):
                for p in source["document"]["meshes"][node["mesh"]]["primitives"]:
                    pieces.append(world_positions(source,ni,p))
    if not pieces:raise ValueError("no retained Terrain geometry")
    p=np.concatenate(pieces);origin=p[:,[0,2]].min(axis=0)
    address=np.rint((p[:,[0,2]]-origin)/2).astype(int)
    if np.max(np.abs(origin+address*2-p[:,[0,2]]))>1e-5:
        raise ValueError("retained Terrain does not have the expected two-metre lattice")
    shape=address.max(axis=0)+1
    grid=np.full((shape[1],shape[0]),np.nan)
    grid[address[:,1],address[:,0]]=p[:,1]
    return origin,grid


def sample_lattice(points, origin, grid):
    address=(points[:,[0,2]]-origin)/2
    cell=np.floor(address).astype(int)
    cell[:,0]=np.clip(cell[:,0],0,grid.shape[1]-2)
    cell[:,1]=np.clip(cell[:,1],0,grid.shape[0]-2)
    tx,tz=(address-cell).T;x,z=cell.T
    a,b,c,d=grid[z,x],grid[z,x+1],grid[z+1,x],grid[z+1,x+1]
    # At ownership edges only one half may be present. Missing opposite corners
    # have zero weight and must not poison an otherwise exact surface sample.
    weights=np.where((tx+tz<=1)[:,None],np.column_stack((1-tx-tz,tx,tz,np.zeros(len(tx)))),
                     np.column_stack((np.zeros(len(tx)),1-tz,1-tx,tx+tz-1)))
    heights=np.column_stack((a,b,c,d))
    known=np.all(np.isfinite(heights)|(np.abs(weights)<1e-5),axis=1)
    sampled=np.sum(np.nan_to_num(heights)*weights,axis=1)
    valid=known&(np.min(weights,axis=1)>=-1e-5)
    return sampled,valid,weights,heights


_TERRAIN_CACHE={}


def continent_terrain_lattices(root):
    """Only terrain arrays survive this streaming scan, not all map documents."""
    key=str(root)
    if key in _TERRAIN_CACHE:return _TERRAIN_CACHE[key]
    result={}
    for region in served_regions(root):
        path=root/f"eloria-assets/maps/continent-v2/{region}/client/world.json"
        manifest=json.loads(path.read_text());pieces=[]
        for chunk in manifest["streamingChunks"]["chunks"]:
            source=load_chunk((path.parent/chunk["manifest"]).parent)
            for ni,node in enumerate(source["document"]["nodes"]):
                if "mesh" in node and node.get("name","").startswith("Terrain_"):
                    pieces.extend(world_positions(source,ni,p) for p in source["document"]["meshes"][node["mesh"]]["primitives"])
        # Feed just the terrain arrays through the same lattice contract.
        p=np.concatenate(pieces);origin=p[:,[0,2]].min(axis=0);address=np.rint((p[:,[0,2]]-origin)/2).astype(int)
        if np.max(np.abs(origin+address*2-p[:,[0,2]]))>1e-5:raise ValueError("neighbour Terrain has a noncanonical lattice")
        shape=address.max(axis=0)+1;grid=np.full((shape[1],shape[0]),np.nan);grid[address[:,1],address[:,0]]=p[:,1]
        result[region]=(origin,grid,np.asarray(manifest["continentGeography"]["translation"])[[0,2]])
    _TERRAIN_CACHE[key]=result
    return result


def terrain_clearance(roads, origin, grid, tolerance=.006, neighbors=()):
    """Verify typed road XYZ on retained own/adjacent Terrain + .055 m."""
    points=np.concatenate([r["triangles"].reshape(-1,3) for r in roads])
    sampled,valid,weights,heights=sample_lattice(points,origin,grid)
    own_count=int(valid.sum());neighbor_counts={}
    for name,other_origin,other_grid,delta in neighbors:
        missing=np.flatnonzero(~valid)
        if not len(missing):break
        shifted=points[missing].copy();shifted[:,[0,2]]+=delta
        values,known,_,_=sample_lattice(shifted,other_origin,other_grid)
        # Another territory may have an overlapping window. Accept only its
        # actual retained owned cells, with the expected road clearance.
        accepted=known&(np.abs(shifted[:,1]-values-.055)<=tolerance)
        chosen=missing[accepted];sampled[chosen]=values[accepted];valid[chosen]=True
        if len(chosen):neighbor_counts[name]=len(chosen)
    error=np.abs(points[:,1]-sampled-.055)
    result=dict(road_corner_samples=len(points),sampled_corner_count=int(valid.sum()),
                missing_corner_samples=int((~valid).sum()),expected_lift_metres=.055,
                tolerance_metres=tolerance,maximum_lift_error_metres=float(error[valid].max()) if valid.any() else None,
                failed_samples=int(np.count_nonzero(error[valid]>tolerance)),own_terrain_corner_samples=own_count,
                neighboring_terrain_corner_samples=neighbor_counts)
    if not valid.all() or result["failed_samples"]:
        result["missing_examples"]=[dict(position=p.tolist(),weights=w.tolist(),known_corners=np.isfinite(h).tolist()) for p,w,h in zip(points[~valid][:5],weights[~valid][:5],heights[~valid][:5])]
        raise ValueError(f"typed road is not verified Terrain+.055: {result}")
    return result


def compressed_array(directory, name, raw, **metadata):
    encoded=zstandard.ZstdCompressor(level=8).compress(raw)
    if zstandard.ZstdDecompressor().decompress(encoded,max_output_size=len(raw))!=raw:
        raise AssertionError("lossless field roundtrip failed")
    (directory/name).write_bytes(encoded)
    return dict(file=name,compression="zstd",uncompressed_bytes=len(raw),sha256=T.sha(raw),file_sha256=T.sha(encoded),
                codec_roundtrip_byte_identical=True,**metadata)


def decode_array(directory, metadata):
    encoded=(directory/metadata["file"]).read_bytes()
    if T.sha(encoded)!=metadata["file_sha256"]:raise ValueError("stored field SHA mismatch")
    raw=zstandard.ZstdDecompressor().decompress(encoded,max_output_size=metadata["uncompressed_bytes"])
    if len(raw)!=metadata["uncompressed_bytes"] or T.sha(raw)!=metadata["sha256"]:
        raise ValueError("decoded field size/SHA mismatch")
    return raw


def pack_ids(ids):
    ids=np.asarray(ids,dtype=np.uint32)
    maximum=int(ids.max(initial=0))
    channels=2 if maximum<=65535 else 3
    if maximum>0xffffff:raise ValueError("triangle ID exceeds RGB8 capacity")
    packed=np.stack([(ids>>(8*i))&255 for i in range(channels)],axis=-1).astype(np.uint8)
    return packed,"RG8" if channels==2 else "RGB8"


def unpack_ids(packed):
    result=np.zeros(packed.shape[:2],np.uint32)
    for channel in range(packed.shape[2]):result|=packed[...,channel].astype(np.uint32)<<(8*channel)
    return result


def dominant_raster(triangles, uv, alpha, grid):
    """World-pixel results must not depend on crop size or BLAS batch layout."""
    h,w,ppm=grid["height"],grid["width"],grid["pixels_per_metre"]
    if ppm<=0 or w*h>B.MAX_PIXELS:raise ValueError("invalid production field bounds")
    first=np.rint(np.asarray(grid["origin_xz"])*ppm).astype(np.int64)
    result=dict(uv=np.zeros((h,w,2),float),alpha=np.zeros((h,w),float),valid=np.zeros((h,w),bool),
                selected_triangle=np.full((h,w),-1,np.int32),contributors=np.zeros((h,w),np.uint32),ambiguous_uv=np.zeros((h,w),bool))
    for ordinal,(tri,values,cover) in enumerate(zip(triangles,uv,alpha)):
        projected=tri[:,[0,2]];pixel=projected*ppm-first-.5
        lo=np.maximum(0,np.ceil(pixel.min(axis=0)-1e-7).astype(int))
        hi=np.minimum([w-1,h-1],np.floor(pixel.max(axis=0)+1e-7).astype(int))
        if np.any(hi<lo):continue
        ax,az=projected[0];bx,bz=projected[1];cx,cz=projected[2]
        determinant=(bz-cz)*(ax-cx)+(cx-bx)*(az-cz)
        if abs(determinant)<1e-16:continue
        xx,zz=np.meshgrid(np.arange(lo[0],hi[0]+1),np.arange(lo[1],hi[1]+1))
        wx,wz=(first[0]+xx+.5)/ppm,(first[1]+zz+.5)/ppm
        a=((bz-cz)*(wx-cx)+(cx-bx)*(wz-cz))/determinant
        b=((cz-az)*(wx-cx)+(ax-cx)*(wz-cz))/determinant;c=1-a-b
        inside=(a>=-1e-7)&(b>=-1e-7)&(c>=-1e-7)
        zz,xx=zz[inside],xx[inside];a,b,c=a[inside],b[inside],c[inside]
        # Matrix multiplication kernels may change accumulation order with N;
        # tiny constant-alpha rounding then changes the overlap winner. These
        # explicit pointwise operations have the same order in every window.
        mapped=a[:,None]*values[0]+b[:,None]*values[1]+c[:,None]*values[2]
        coverage=np.clip(a*cover[0]+b*cover[1]+c*cover[2],0,1)
        active=coverage>0;zz,xx,mapped,coverage=zz[active],xx[active],mapped[active],coverage[active]
        if not len(xx):continue
        occupied=result["valid"][zz,xx];result["contributors"][zz,xx]+=1
        result["ambiguous_uv"][zz,xx]|=occupied&(np.max(np.abs(result["uv"][zz,xx]-mapped),axis=1)>2e-4)
        wins=~occupied|(coverage>=result["alpha"][zz,xx]);yy,xxx=zz[wins],xx[wins]
        result["uv"][yy,xxx]=mapped[wins];result["alpha"][yy,xxx]=coverage[wins]
        result["valid"][yy,xxx]=True;result["selected_triangle"][yy,xxx]=ordinal
    return result


def compact_field(sheet, grid, triangles, flow, jacobians, triangle_styles):
    """Keep the selected triangle, evaluating its affine map instead of a UV image."""
    valid=sheet["valid"]
    if not valid.any():raise ValueError("cannot store an empty road field")
    selected=sheet["selected_triangle"]
    unique=np.unique(selected[valid])
    lookup=np.full(len(triangles),-1,np.int32);lookup[unique]=np.arange(len(unique))+1
    nearest=T.distance_transform_edt(~valid,return_distances=False,return_indices=True)
    ids=lookup[selected[tuple(nearest)]]
    if np.any(ids<=0):raise AssertionError("halo has no selected affine map")
    j=jacobians[unique]
    delta=np.asarray(grid["origin_xz"])-triangles[unique,0][:,[0,2]]
    anchor=flow[unique,0]+np.column_stack((j[:,0]*delta[:,0]+j[:,1]*delta[:,1],
                                        j[:,2]*delta[:,0]+j[:,3]*delta[:,1]))
    rows=np.column_stack((anchor,j,triangle_styles[unique],np.zeros(len(unique)))).astype("<f4")
    if not np.isfinite(rows).all():raise ValueError("nonfinite packed affine coefficients")
    # Emulate the shader's float32 operations, including cancellation from the
    # chosen common origin. J is exactly the same float32 derivative as v3.
    yy,xx=np.indices(valid.shape);dx=(xx+.5)/grid["pixels_per_metre"];dz=(yy+.5)/grid["pixels_per_metre"]
    chosen=rows[ids-1];dx,dz=dx.astype("<f4"),dz.astype("<f4")
    reconstructed=np.stack((chosen[...,0]+chosen[...,2]*dx+chosen[...,3]*dz,
                            chosen[...,1]+chosen[...,4]*dx+chosen[...,5]*dz),axis=-1)
    expected=B.affine_halo_uv(T.fill_uv(sheet["uv"],valid),T.fill_uv(jacobians[selected.clip(0)],valid),
                              valid,grid["pixels_per_metre"])
    error=np.max(np.abs(reconstructed-expected),axis=-1)
    report=dict(maximum_covered_uv_abs_error=float(error[valid].max()),maximum_halo_uv_abs_error=float(error[~valid].max()) if (~valid).any() else 0,
                source_jacobian_float32_byte_identical=rows[:,2:6].tobytes()==jacobians[unique].astype("<f4").tobytes(),
                selected_triangle_count=len(unique),maximum_triangle_id=int(ids.max()),
                coverage_policy="maximum_raw_interpolated_source_alpha",uv_policy="highest_alpha_then_last_stable_authored_triangle",
                affine_halo_policy="nearest_valid_selected_triangle_evaluated_at_fragment_position")
    if not report["source_jacobian_float32_byte_identical"]:raise AssertionError("source Jacobian changed")
    if max(report["maximum_covered_uv_abs_error"],report["maximum_halo_uv_abs_error"])>.002:
        raise ValueError(f"affine coefficient encoding exceeds UV error limit: {report}")
    return ids,rows,report


def store_field(directory, sheet, grid, triangles, flow, jacobians, triangle_styles):
    ids,rows,validation=compact_field(sheet,grid,triangles,flow,jacobians,triangle_styles)
    packed,fmt=pack_ids(ids)
    idmeta=compressed_array(directory,"triangle-ids.bin.zst",packed.tobytes(),format=fmt,byte_order="little",
                            width=ids.shape[1],height=ids.shape[0],mipmaps=False,id_zero="reserved",id_base=1)
    per_row=min(len(rows),1024);height=(len(rows)+per_row-1)//per_row
    table=np.zeros((height*per_row,8),dtype="<f4");table[:len(rows)]=rows
    coeff=compressed_array(directory,"affine-coefficients.rgba32f.zst",table.tobytes(),format="RGBA32F",byte_order="little",
                           width=per_row*2,height=height,records_per_row=per_row,record_count=len(rows),texels_per_record=2,
                           mipmaps=False,layout=COEFFICIENT_LAYOUT)
    mips=[]
    for level,(_,coverage) in enumerate(T.mip_chain(np.zeros((*sheet["alpha"].shape,2)),sheet["alpha"])):
        pixels=np.rint(np.clip(coverage,0,1)*255).astype(np.uint8)
        name=f"coverage-mip{level}.png";Image.fromarray(pixels).save(directory/name,optimize=True)
        mips.append(dict(level=level,width=pixels.shape[1],height=pixels.shape[0],file=name,
                         sha256=T.sha((directory/name).read_bytes()),decoded_sha256=T.sha(pixels.tobytes())))
    result=dict(grid=grid,coverage_mips=mips,triangle_ids=idmeta,affine_coefficients=coeff,validation=validation)
    read_field(directory,result)
    return result


def read_field(directory, metadata):
    im=metadata["triangle_ids"];cm=metadata["affine_coefficients"];grid=metadata["grid"]
    channels={"RG8":2,"RGB8":3}.get(im["format"])
    if channels is None or im.get("mipmaps") is not False or im.get("id_base")!=1:raise ValueError("invalid triangle ID format")
    if cm.get("format")!="RGBA32F" or cm.get("layout")!=COEFFICIENT_LAYOUT or cm.get("mipmaps") is not False:
        raise ValueError("invalid coefficient format")
    if im["width"]!=grid["width"] or im["height"]!=grid["height"]:raise ValueError("ID grid dimension mismatch")
    raw=decode_array(directory,im)
    if len(raw)!=im["width"]*im["height"]*channels:raise ValueError("ID decoded byte length mismatch")
    ids=unpack_ids(np.frombuffer(raw,np.uint8).reshape(im["height"],im["width"],channels))
    raw=decode_array(directory,cm)
    if len(raw)!=cm["width"]*cm["height"]*16:raise ValueError("coefficient byte length mismatch")
    rows=np.frombuffer(raw,dtype="<f4").reshape(-1,8)[:cm["record_count"]]
    if not np.isfinite(rows).all() or np.any(ids<1) or np.any(ids>len(rows)):raise ValueError("invalid affine map reference")
    for mip in metadata["coverage_mips"]:
        path=directory/mip["file"];pixels=np.asarray(Image.open(path))
        if T.sha(path.read_bytes())!=mip["sha256"] or T.sha(pixels.tobytes())!=mip["decoded_sha256"]:
            raise ValueError("coverage SHA mismatch")
        if pixels.shape!=(mip["height"],mip["width"]):raise ValueError("coverage dimensions mismatch")
    return ids,rows


def prune_roads(source, roads, destination):
    """Remove typed road nodes, without changing any retained mesh's bytes/frame."""
    d=T.prune_visual_roads(source,roads,destination)
    removed={r["node_index"] for r in roads}
    changed=True
    while changed:
        changed=False
        for ni,node in enumerate(d["nodes"]):
            if ni not in removed and node.get("children") and all(c in removed for c in node["children"]) \
                    and node.get("name","").endswith("_WorldPlacement") and not any(k in node for k in ("mesh","camera","skin","extras")):
                removed.add(ni);changed=True
    mapping={old:new for new,old in enumerate(i for i in range(len(d["nodes"])) if i not in removed)}
    d["nodes"]=[n for i,n in enumerate(d["nodes"]) if i not in removed]
    for node in d["nodes"]:
        if "children" in node:node["children"]=[mapping[c] for c in node["children"] if c in mapping]
    for scene in d.get("scenes",[]):scene["nodes"]=[mapping[n] for n in scene.get("nodes",[]) if n in mapping]
    destination.write_bytes(T.SM.write_glb(d,T.SM.read_glb(destination)[1]))
    if any(n.get("name") in {r["road_node_name"] for r in roads} for n in d["nodes"]):
        raise AssertionError("typed road node retained")
    return d


def retained_walk_snapshot(source, retained):
    """Exact attribute/index bytes and scene frames for every retained walk."""
    wanted={r["node_path"] for r in retained};result={}
    for ni,node in enumerate(source["document"]["nodes"]):
        path=source["paths"][ni]
        if path not in wanted:continue
        parts=[source["frames"][ni].astype("<f8").tobytes()]
        for primitive in source["document"]["meshes"][node["mesh"]]["primitives"]:
            parts.append(str(primitive.get("mode",4)).encode())
            for semantic,ai in sorted(primitive["attributes"].items()):
                parts.extend((semantic.encode(),T.accessor(source["document"],source["body"],ai,False).tobytes()))
            if "indices" in primitive:parts.append(T.accessor(source["document"],source["body"],primitive["indices"],False).tobytes())
        result[path]=T.sha(b"".join(parts))
    if len(result)!=len(wanted):raise ValueError("retained walk geometry was not found")
    return result


def validate_seams(out, chunks, tolerance=.002):
    samples=[]
    for row in chunks:
        path=out/row["metadata"];metadata=json.loads(path.read_text());field=metadata["field"]
        ids,coeff=read_field(path.parent,field);coverage=np.asarray(Image.open(path.parent/field["coverage_mips"][0]["file"]))
        grid=field["grid"];first=np.rint(np.array(grid["origin_xz"])*4).astype(int)
        samples.append(dict(chunk=row["chunk"],first=first,last=first+[grid["width"],grid["height"]],ids=ids,rows=coeff,coverage=coverage))
    checks=[]
    for ai,a in enumerate(samples):
        for b in samples[ai+1:]:
            lower=np.maximum(a["first"],b["first"]);upper=np.minimum(a["last"],b["last"])
            if np.any(upper<=lower):continue
            def view(sample):
                lo=lower-sample["first"];hi=upper-sample["first"]
                ids=sample["ids"][lo[1]:hi[1],lo[0]:hi[0]]
                color=sample["coverage"][lo[1]:hi[1],lo[0]:hi[0]]
                yy,xx=np.indices(ids.shape);dx=(lo[0]+xx+.5).astype("<f4")/4;dz=(lo[1]+yy+.5).astype("<f4")/4
                coeff=sample["rows"][ids-1]
                uv=np.stack((coeff[...,0]+coeff[...,2]*dx+coeff[...,3]*dz,coeff[...,1]+coeff[...,4]*dx+coeff[...,5]*dz),axis=-1)
                return color,uv,coeff
            ac,au,at=view(a);bc,bu,bt=view(b);active=(ac>0)|(bc>0)
            if not active.any():continue
            uv_error=float(np.max(np.abs(au[active]-bu[active])))
            check=dict(chunks=[a["chunk"],b["chunk"]],covered_pixel_samples=int(active.sum()),maximum_uv_abs_error=uv_error,
                       coverage_mismatches=int(np.count_nonzero(ac[active]!=bc[active])),
                       jacobian_mismatches=int(np.count_nonzero(np.any(at[active,2:6]!=bt[active,2:6],axis=1))),
                       style_mismatches=int(np.count_nonzero(at[active,6]!=bt[active,6])))
            if uv_error>tolerance or any(check[k] for k in ("coverage_mismatches","jacobian_mismatches","style_mismatches")):
                raise ValueError(f"shared road field gutter mismatch: {check}")
            checks.append(check)
    return checks


def portable_style(source, record, directory, style_id, identity):
    material=T.material_document(source,record);resources={}
    for image in material["images"]:
        if "uri" in image:
            path=(source["directory"]/image["uri"]).resolve()
            image["uri"]=T.relative(path,directory);resources[image["uri"]]=T.sha(path.read_bytes())
    name=source["document"]["materials"][record["material_index"]].get("name","")
    return dict(id=style_id,identity_sha256=identity,material_document=material,externalResources=resources,
                original_material_names=[name],vertex_rgb=record["source_vertex_rgb"])


def bake_region(root, out, region, ppm=4, selected_chunks=None):
    """Stage one territory; source assets and collision maps are never replaced."""
    root,out=Path(root).resolve(),Path(out).resolve()
    if ppm!=4:raise ValueError("production policy is exactly four pixels per metre")
    if out.exists():raise ValueError("output must be a fresh staging directory")
    if not out.is_relative_to(root) or subprocess.run(["git","check-ignore","--quiet",str(out/"roads.json")],cwd=root).returncode:
        raise ValueError("staging output must be ignored inside the task checkout")
    catalog=authoring_catalog(root,region)
    manifest_path=root/f"eloria-assets/maps/continent-v2/{region}/client/world.json"
    region_manifest=json.loads(manifest_path.read_text());sources={};roads=[];retained={};style_records={}
    for c in region_manifest["streamingChunks"]["chunks"]:
        chunk=c["id"];source=load_chunk((manifest_path.parent/c["manifest"]).parent);sources[chunk]=source;retained[chunk]=[];cache={}
        for ni,node in enumerate(source["document"]["nodes"]):
            if "mesh" not in node:continue
            role,identity=classify_walk(node.get("name",""),region,chunk,catalog,source["paths"][ni])
            if role in ("bridge","retained_asset_walk"):
                retained[chunk].append(dict(name=node["name"],role=role,authoring_id=identity,node_path=source["paths"][ni]))
            if role!="road":continue
            for pi in range(len(source["document"]["meshes"][node["mesh"]]["primitives"])):
                r=primitive_record(source,chunk,ni,pi,identity);r["style_identity"]=style_identity(source,r,cache,root)
                style_records.setdefault(r["style_identity"],r);roads.append(r)
    if not roads:
        out.mkdir(parents=True);T.write_json(out/"region-report.json",dict(schema=SCHEMA,region=region,road_chunks=0,chunks=[]))
        return dict(region=region,road_chunks=0,chunks=[])
    identities=sorted(style_records);style_ids={identity:i for i,identity in enumerate(identities)}
    if len(identities)>2:raise ValueError("more than two source styles requires a deliberate runtime extension")
    origin,terrain=terrain_lattice(sources)
    try:
        clearance=terrain_clearance(roads,origin,terrain)
    except ValueError:
        translation=np.asarray(region_manifest["continentGeography"]["translation"])[[0,2]]
        neighbors=[(name,other_origin,other_grid,translation-other_translation)
                   for name,(other_origin,other_grid,other_translation) in continent_terrain_lattices(root).items() if name!=region]
        clearance=terrain_clearance(roads,origin,terrain,neighbors=neighbors)
    triangles=np.concatenate([r["triangles"] for r in roads]);flow=np.concatenate([r["uv"] for r in roads]);alpha=np.concatenate([r["alpha"] for r in roads])
    triangle_styles=np.concatenate([np.full(len(r["triangles"]),style_ids[r["style_identity"]],np.int32) for r in roads])
    jacobians=B.affine_uv_jacobians(triangles,flow)
    lo,hi=triangles[:,:,[0,2]].min(axis=1),triangles[:,:,[0,2]].max(axis=1)
    out.mkdir(parents=True);chunk_reports=[]
    for chunk,source in sources.items():
        selected=[r for r in roads if r["chunk"]==chunk]
        if not selected or selected_chunks and chunk not in selected_chunks:continue
        directory=out/"chunks"/chunk;directory.mkdir(parents=True)
        grid=T.grid_for(np.concatenate([r["triangles"] for r in selected]),ppm)
        lower=np.asarray(grid["origin_xz"]);upper=lower+np.array([grid["width"],grid["height"]])/ppm
        nearby=np.flatnonzero(np.all(hi>=lower,axis=1)&np.all(lo<=upper,axis=1))
        sheet=dominant_raster(triangles[nearby],flow[nearby],alpha[nearby],grid)
        sheet["selected_triangle"][sheet["valid"]]=nearby[sheet["selected_triangle"][sheet["valid"]]]
        overlap=dict(covered_pixels=int(sheet["valid"].sum()),multiply_covered_pixels=int(np.count_nonzero(sheet["contributors"]>1)),
                     different_uv_overlap_pixels=int(sheet["ambiguous_uv"].sum()),maximum_source_fragments_per_pixel=int(sheet["contributors"].max()))
        sheet,grid=T.crop_sheet(sheet,grid)
        field=store_field(directory,sheet,grid,triangles,flow,jacobians,triangle_styles)
        retained_before=retained_walk_snapshot(source,retained[chunk])
        base=directory/"world.glb";prune_roads(source,selected,base)
        if retained_walk_snapshot(load_chunk_for_glb(base),retained[chunk])!=retained_before:
            raise AssertionError("retained bridge/kit walk attributes, indices or world frames changed")
        targets=[dict(name=n["name"],world_matrix=source["frames"][i].reshape(-1,order="F").tolist())
                 for i,n in enumerate(source["document"]["nodes"]) if "mesh" in n and n.get("name","").startswith("AuthoredGround_")]
        expected=f"AuthoredGround_{region}Base_{region}_{chunk}"
        frame=next((t for t in targets if t["name"]==expected),None)
        if frame is None:raise ValueError("missing authored Base frame")
        active_styles=sorted(set(int(v) for v in triangle_styles[np.unique(sheet["selected_triangle"][sheet["valid"]])]))
        styles=[]
        for identity in identities:
            sid=style_ids[identity]
            # Keep the region table's stable IDs even where only one style is
            # visible. At most two materials are needed and neighbour gutters
            # may select either saved road class.
            r=style_records[identity];style=portable_style(sources[r["chunk"]],r,directory,sid,identity)
            style["original_material_names"]=sorted({sources[v["chunk"]]["document"]["materials"][v["material_index"]].get("name","") for v in roads if v["style_identity"]==identity})
            classes={footstep_class(root,name) for name in style["original_material_names"]}
            if len(classes)!=1:raise ValueError("source footstep classes were incorrectly merged")
            style["footstep_class"]=next(iter(classes))
            styles.append(style)
        metadata=dict(schema=SCHEMA,region=region,chunk=chunk,pixels_per_metre=ppm,
                      source_glb_sha256=T.sha(source["path"].read_bytes()),source_manifest_sha256=T.sha((source["directory"]/"world.json").read_bytes()),
                      authoring_scene_sha256=catalog["sha256"],mask_space="gltf_scene_world_xz",source_frame_node=frame["name"],source_frame_matrix=frame["world_matrix"],
                      targets=targets,removed_road_node_names=sorted({r["road_node_name"] for r in selected}),
                      source_road_ids=sorted({r["road_id"] for r in selected}),retained_walk_nodes=retained[chunk],
                      collision_policy="retained_terrain_only_for_removed_road_ribbons;structural_walks_unchanged",
                      styles=styles,field=field,overlap=overlap,active_style_ids=active_styles,
                      appearance_limit="Dominant UV and maximum raw alpha collapse independent overlapping road samples at four pixels per metre.")
        resources={T.relative(p,directory):T.sha(p.read_bytes()) for p in directory.iterdir() if p.is_file() and p.suffix not in (".json",".glb")}
        for style in styles:resources.update(style["externalResources"])
        metadata["resources"]=resources
        T.write_json(directory/"roads.json",metadata)
        manifest=T.rebase_manifest(source,directory,base);manifest.pop("roadTextureTrial",None)
        manifest["roadGround"]=dict(schema=SCHEMA,metadata="roads.json",sha256=T.sha((directory/"roads.json").read_bytes()),pixelsPerMetre=ppm)
        T.write_json(directory/"world.json",manifest)
        chunk_reports.append(dict(chunk=chunk,metadata=T.relative(directory/"roads.json",out),removed_road_node_names=metadata["removed_road_node_names"],
                                  retained_walk_nodes=retained[chunk],retained_walk_geometry_sha256=retained_before,field_validation=field["validation"]))
    generated=[p for p in out.rglob("*") if p.is_file()]
    report=dict(schema=SCHEMA,region=region,pixels_per_metre=ppm,road_chunks=len(chunk_reports),chunks=chunk_reports,
                styles=len(identities),terrain_clearance=clearance,generated=T.inventory(generated),shared_gutters=validate_seams(out,chunk_reports))
    T.write_json(out/"region-report.json",report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root",type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument("--region",action="append",dest="regions")
    parser.add_argument("--audit-out",type=Path)
    parser.add_argument("--out",type=Path)
    parser.add_argument("--chunk",action="append",dest="chunks")
    args=parser.parse_args()
    if args.audit_out:
        result=audit(args.source_root,args.regions)
        T.write_json(args.audit_out,result)
        print(json.dumps(dict(**result["summary"],failures=result["failures"]),indent=2))
        if result["failures"]:raise SystemExit(1)
    elif args.out:
        reports=[]
        for region in args.regions or served_regions(args.source_root):
            report=bake_region(args.source_root,args.out/region,region,selected_chunks=args.chunks)
            reports.append({k:report[k] for k in ("region","road_chunks","styles") if k in report})
            print(json.dumps(reports[-1]),flush=True)
        T.write_json(args.out/"production-report.json",dict(schema=SCHEMA,regions=reports))
    else:parser.error("--audit-out or --out is required")


if __name__=="__main__":main()
