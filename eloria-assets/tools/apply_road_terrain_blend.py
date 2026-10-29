"""Plan or apply a validated road-ground stage, with complete local recovery.

The dry run is the default. Publication accounting and cartography restamping
belong to publish_finish; this helper only promotes the runtime leaf closure.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import uuid

import road_terrain_blend as P

SCHEMA="rabbitlands-road-ground-apply-v1"


def checked_asset(root, base, uri):
    if not isinstance(uri,str) or "://" in uri or Path(uri).is_absolute():
        raise ValueError(f"nonportable asset URI: {uri}")
    path=(base/uri).resolve()
    if not path.is_relative_to(root/"eloria-assets") or not path.is_file():
        raise ValueError(f"asset URI escapes the asset root or is missing: {uri}")
    return path


def source_checkout(stage):
    for parent in (stage,*stage.parents):
        if parent.name=="eloria-assets":return parent.parent
    raise ValueError("runtime stage must be inside a checkout's eloria-assets scope")


def logical_asset(source_root, root, source):
    relative=source.relative_to(source_root/"eloria-assets")
    if ".local" in relative.parts:raise ValueError("shared runtime image must not come from a private staging directory")
    target=root/"eloria-assets"/relative
    if not target.is_file() or P.T.sha(target.read_bytes())!=P.T.sha(source.read_bytes()):
        raise ValueError(f"target checkout asset differs from staged source: {relative}")
    return target


def json_bytes(value):
    return (json.dumps(value,indent=2,allow_nan=False)+"\n").encode("utf-8")


def stage_chunks(stage, regions=None, chunk_scope=None):
    paths=[]
    for path in Path(stage).rglob("roads.json"):
        data=json.loads(path.read_text())
        if data.get("schema")!=P.SCHEMA:continue
        if regions and data["region"] not in regions:continue
        if chunk_scope and data["chunk"] not in chunk_scope:continue
        paths.append((path,data))
    return sorted(paths,key=lambda row:(row[1]["region"],row[1]["chunk"]))


def field_files(metadata):
    field=metadata["field"]
    return {field["triangle_ids"]["file"],field["affine_coefficients"]["file"]} | {m["file"] for m in field["coverage_mips"]}


def validate_metadata(root, path, metadata=None):
    data=metadata or json.loads(path.read_text())
    if data.get("schema")!=P.SCHEMA or data.get("pixels_per_metre")!=4:
        raise ValueError("unsupported production road-ground metadata")
    P.read_field(path.parent,data["field"])
    resources=data.get("resources")
    if not isinstance(resources,dict):raise ValueError("road-ground metadata has no canonical resource closure")
    required=field_files(data)
    for style in data["styles"]:
        for image in style["material_document"].get("images",[]):
            if "uri" in image:required.add(image["uri"])
    if required!=set(resources):raise ValueError("road-ground resource closure is incomplete or has unreferenced files")
    for uri,digest in resources.items():
        source=checked_asset(root,path.parent,uri)
        if P.T.sha(source.read_bytes())!=digest:raise ValueError(f"road-ground resource hash mismatch: {uri}")
    return data


def valid_existing_leaf(root, directory):
    manifest=json.loads((directory/"world.json").read_text())
    config=manifest.get("roadGround")
    if not config:return False
    uri=config.get("metadata","")
    if not uri or Path(uri).is_absolute() or ".." in Path(uri).parts or ":" in uri:
        raise ValueError("roadGround metadata must be a local leaf file")
    path=directory/uri
    if P.T.sha(path.read_bytes())!=config.get("sha256"):raise ValueError("existing roadGround metadata SHA mismatch")
    metadata=validate_metadata(root,path)
    source=P.load_chunk(directory)
    names={n.get("name") for n in source["document"]["nodes"] if "mesh" in n}
    if names.intersection(metadata["removed_road_node_names"]):raise ValueError("existing roadGround leaf still contains removed road geometry")
    return True


def image_resources(root, document, source_directory, destination_directory, source_root=None):
    resources={}
    for image in document.get("images",[]):
        if "uri" not in image or image["uri"].startswith("data:"):continue
        path=checked_asset(source_root or root,source_directory,image["uri"])
        if source_root:path=logical_asset(source_root,root,path)
        image["uri"]=P.T.relative(path,destination_directory)
        resources[image["uri"]]=P.T.sha(path.read_bytes())
    return resources


def prototype_resources(root, manifest, directory, document):
    used={n.get("extras",{}).get("eloria",{}).get("prototype") for n in document.get("nodes",[])}-{None}
    meshes={};images={}
    for uri,digest in manifest.get("externalMeshes",{}).items():
        if Path(uri).stem not in used:continue
        path=checked_asset(root,directory,uri)
        if P.T.sha(path.read_bytes())!=digest:raise ValueError(f"source prototype hash mismatch: {uri}")
        meshes[P.T.relative(path,directory)]=digest
        proto,body=P.T.SM.read_glb(path)
        for image in proto.get("images",[]):
            if "uri" in image and not image["uri"].startswith("data:"):
                texture=checked_asset(root,path.parent,image["uri"])
                images[P.T.relative(texture,directory)]=P.T.sha(texture.read_bytes())
    if {Path(uri).stem for uri in meshes}!=used:raise ValueError("retained GLB prototype has no verified manifest resource")
    return meshes,images


def build_plan(root, stage, regions=None, chunk_scope=None):
    root,stage=Path(root).resolve(),Path(stage).resolve()
    source_root=source_checkout(stage)
    writes={};deletes=set();chunks=[];skipped=[]
    def write(path,content):
        if not path.resolve().is_relative_to(root):raise ValueError("write target escapes checkout")
        if path in writes and writes[path]!=content:raise ValueError("conflicting stage writes")
        writes[path]=content
    for path,metadata in stage_chunks(stage,regions,chunk_scope):
        validate_metadata(source_root,path,metadata)
        region,chunk=metadata["region"],metadata["chunk"]
        if not region or not chunk or "/" in region+chunk or "\\" in region+chunk or ".." in (region,chunk):
            raise ValueError("invalid region or chunk identity")
        destination=root/f"eloria-assets/maps/continent-v2/{region}/client/chunks/{chunk}"
        manifest_path=destination/"world.json";current=json.loads(manifest_path.read_text())
        source_glb=checked_asset(source_root,path.parent,"world.glb")
        document,body=P.T.SM.read_glb(source_glb)
        inline_images=image_resources(root,document,path.parent,destination,source_root)
        glb=P.T.SM.write_glb(document,body)
        updated=copy.deepcopy(metadata);resources={}
        for uri,digest in metadata["resources"].items():
            source=checked_asset(source_root,path.parent,uri)
            if uri in field_files(metadata):
                if Path(uri).name!=uri:raise ValueError("runtime field payload must be a local leaf filename")
                target=destination/uri;write(target,source.read_bytes());new_uri=uri
            else:new_uri=P.T.relative(logical_asset(source_root,root,source),destination)
            resources[new_uri]=digest
        for style in updated["styles"]:
            for image in style["material_document"].get("images",[]):
                if "uri" in image:image["uri"]=P.T.relative(logical_asset(source_root,root,checked_asset(source_root,path.parent,image["uri"])),destination)
            style["externalResources"]={P.T.relative(logical_asset(source_root,root,checked_asset(source_root,path.parent,uri)),destination):digest
                                        for uri,digest in style["externalResources"].items()}
        updated["resources"]=resources
        metadata_bytes=json_bytes(updated);metadata_path=destination/"roads.json"
        manifest=copy.deepcopy(current)
        manifest["asset"]["glb"]="world.glb"
        manifest.setdefault("performance",{})["glbBytes"]=len(glb)
        meshes,prototype_images=prototype_resources(root,current,destination,document)
        manifest["externalMeshes"]=meshes
        manifest["externalResources"]={**prototype_images,**inline_images}
        manifest["roadGround"]=dict(schema=P.SCHEMA,metadata="roads.json",sha256=P.T.sha(metadata_bytes),pixelsPerMetre=4)
        manifest.pop("roadTextureTrial",None);manifest.pop("roadTerrainBlend",None)
        write(destination/"world.glb",glb);write(metadata_path,metadata_bytes);write(manifest_path,json_bytes(manifest))
        # Remove only files explicitly owned by the previous roadGround closure,
        # confined to this chunk. Shared source images and unrelated files stay.
        old=current.get("roadGround",{})
        if old.get("metadata"):
            old_path=checked_asset(root,destination,old["metadata"])
            old_data=json.loads(old_path.read_text())
            old_fields=field_files(old_data) if old_data.get("schema")==P.SCHEMA and "field" in old_data else set()
            new_resources={(destination/uri).resolve() for uri in resources}
            for uri in old_fields:
                candidate=(old_path.parent/uri).resolve()
                if candidate.parent==destination and candidate not in writes and candidate not in new_resources:deletes.add(candidate)
            if old_path!=metadata_path and old_path.parent==destination:deletes.add(old_path)
        before_glb=checked_asset(root,destination,current["asset"]["glb"])
        same=all(p.is_file() and p.read_bytes()==content for p,content in writes.items() if p.parent==destination) and not any(p.exists() for p in deletes if p.parent==destination)
        if not same and P.T.sha(before_glb.read_bytes())!=metadata["source_glb_sha256"]:
            raise ValueError(f"{region}/{chunk}: source GLB changed after staging")
        chunks.append(dict(region=region,chunk=chunk,files=len([p for p in writes if p.parent==destination]),
                           road_nodes_removed=len(metadata["removed_road_node_names"])))
        if same:skipped.append(f"{region}/{chunk}")
    changed={path:content for path,content in writes.items() if not path.is_file() or path.read_bytes()!=content}
    deletions=sorted(p for p in deletes if p.exists())
    before={str(path):P.T.sha(path.read_bytes()) if path.exists() else None for path in sorted(set(changed)|set(deletions))}
    return dict(schema=SCHEMA,root=str(root),stage=str(stage),writes=changed,deletes=deletions,before_sha256=before,chunks=chunks,skipped=skipped)


def plan_summary(plan):
    return dict(schema=SCHEMA,chunks=len(plan["chunks"]),skipped=plan["skipped"],files_written=len(plan["writes"]),files_deleted=len(plan["deletes"]),
                bytes_written=sum(map(len,plan["writes"].values())),bytes_before=sum(Path(p).stat().st_size for p,digest in plan["before_sha256"].items() if digest is not None))


def apply_plan(plan, recovery_root=None):
    root=Path(plan["root"]);summary=plan_summary(plan)
    if not plan["writes"] and not plan["deletes"]:return dict(**summary,applied=True,recovery=None)
    recovery=Path(recovery_root).resolve() if recovery_root else root/".local/road-ground-recovery"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:10])
    if recovery.exists() or not recovery.is_relative_to(root/".local"):
        raise ValueError("recovery must be a fresh directory inside this checkout's ignored .local")
    if subprocess.run(["git","check-ignore","--quiet",str(recovery/"receipt.json")],cwd=root).returncode:
        raise ValueError("recovery directory is not ignored")
    # Verify every optimistic input first, and copy every original before the
    # first write/delete. The receipt also records newly created files.
    for text,digest in plan["before_sha256"].items():
        path=Path(text);actual=P.T.sha(path.read_bytes()) if path.exists() else None
        if actual!=digest:raise ValueError(f"destination changed after plan: {path}")
    recovery.mkdir(parents=True)
    originals=[]
    for text,digest in plan["before_sha256"].items():
        path=Path(text);relative=path.relative_to(root)
        if digest is not None:
            target=recovery/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
            if P.T.sha(target.read_bytes())!=digest:raise AssertionError("recovery copy did not preserve original bytes")
        originals.append(dict(path=relative.as_posix(),sha256=digest))
    P.T.write_json(recovery/"receipt.json",dict(schema=SCHEMA,originals=originals,planned=summary,complete=False))
    for path,content in plan["writes"].items():
        path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(path.name+".road-ground-"+uuid.uuid4().hex+".tmp")
        temporary.write_bytes(content);os.replace(temporary,path)
    for path in plan["deletes"]:path.unlink()
    for chunk in plan["chunks"]:
        directory=root/f"eloria-assets/maps/continent-v2/{chunk['region']}/client/chunks/{chunk['chunk']}"
        if not valid_existing_leaf(root,directory):raise AssertionError("promoted road-ground leaf failed validation")
    P.T.write_json(recovery/"receipt.json",dict(schema=SCHEMA,originals=originals,planned=summary,complete=True))
    return dict(**summary,applied=True,recovery=str(recovery))


def finish_region(root, region, chunk_scope=None, *, work=None, apply=True):
    """Publishing hook after geometry processing, before final bookkeeping."""
    root=Path(root).resolve();manifest=root/f"eloria-assets/maps/continent-v2/{region}/client/world.json"
    source=json.loads(manifest.read_text());selected=[];skipped=[];unstripped=[]
    catalog=P.authoring_catalog(root,region)
    for row in source["streamingChunks"]["chunks"]:
        if chunk_scope and row["id"] not in chunk_scope:continue
        directory=(manifest.parent/row["manifest"]).parent;leaf=P.load_chunk(directory)
        has_roads=any("mesh" in n and P.classify_walk(n.get("name",""),region,row["id"],catalog,leaf["paths"][i])[0]=="road"
                      for i,n in enumerate(leaf["document"]["nodes"]))
        if has_roads:unstripped.append(row["id"])
        elif valid_existing_leaf(root,directory):skipped.append(row["id"])
        selected.append(row["id"])
    if not unstripped:return dict(region=region,applied=apply,chunks=0,skipped=skipped)
    work=Path(work).resolve() if work else root/f"eloria-assets/maps/continent-v2/{region}/client/.local/road-ground-finish"/uuid.uuid4().hex
    P.bake_region(root,work/region,region,selected_chunks=unstripped)
    plan=build_plan(root,work,[region],unstripped)
    report=apply_plan(plan) if apply else dict(**plan_summary(plan),applied=False)
    report.update(region=region,skipped_existing_leaves=skipped)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root",type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument("--stage",type=Path,required=True)
    parser.add_argument("--region",action="append",dest="regions")
    parser.add_argument("--chunk",action="append",dest="chunks")
    parser.add_argument("--apply",action="store_true")
    parser.add_argument("--recovery",type=Path)
    args=parser.parse_args();plan=build_plan(args.source_root,args.stage,args.regions,args.chunks)
    result=apply_plan(plan,args.recovery) if args.apply else dict(**plan_summary(plan),applied=False)
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
