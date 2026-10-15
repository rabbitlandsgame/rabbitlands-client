#!/usr/bin/env python3
"""Choose replayable defaults for spawnless sections from pinned served collision.

The original three arrival markers are conserved by the scene splitter. Other
sections choose the nearest safe, owned, hub-reached baseline tile to an exact
interior representative. This never adds markers, opens collision or relocates
content at publication time. Source grids are read from pinned Git history so
retiring their working-tree packages cannot change the result.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import breadth_first_order

import freeze_continent_v2_terrain as F

META = F.CHECKOUT / "eloria-assets/maps/continent-v2/_continent_v2"
sys.path.insert(0, str(META))
import arrivals as A
import export_collision as E
import frames
import ownership as O


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def baseline(reader, codec, catalog, sections):
    """Exact collision fold and directed hub reach across the original crossing lanes."""
    maps = {}
    sources, targets, offset = [], [], 0
    crossing = json.loads(reader.read("eloria-assets/maps/continent-v2/_continent_v2/crossings.json"))
    for entry in catalog["entries"]:
        rid = entry["id"]
        prefix = f"eloria-assets/maps/continent-v2/{rid}/client/"
        world_raw = reader.read(prefix + "world.json")
        manifest = json.loads(world_raw)
        collision_raw = reader.read(prefix + "collision.bin")
        served_raw = reader.read(prefix + "served-grid.escg.gz")
        magic, version, flags, width, height = struct.unpack_from("<4sHHII",collision_raw)
        if (magic,version,flags) != (b"EWCG",2,0):
            raise ValueError(f"{rid}: unsupported baseline collision")
        raw = np.frombuffer(collision_raw,np.uint8,offset=16).reshape(height,width)
        folded = (raw.reshape(height//2,2,width//2,2)!=0).all(axis=(1,3))
        served = codec.served_grid.decode_file(served_raw)
        codes = np.asarray(served.codes,np.uint16).reshape(served.height,served.width)
        block = manifest["collision"]
        if not np.array_equal(folded,codes!=0) or sha(collision_raw)!=block["sha256"] or sha(served_raw)!=block["servedGrid"]["sha256"]:
            raise ValueError(f"{rid}: pinned collision fold/hash disagrees with served grid")
        coordinate = manifest["coordinateTransform"]
        frame = frames.Frame(rid,entry["label"],tuple(coordinate["serverOrigin"]),tuple(coordinate["serverCells"]),tuple(manifest["continentGeography"]["translation"]))
        legal = E.legal_steps(codes,served.climb_units)
        safe = codes != 0
        for mask in legal.values():
            safe &= mask
        ids = np.full(codes.shape,-1,np.int32)
        count = int((codes!=0).sum())
        ids[codes!=0] = np.arange(offset,offset+count,dtype=np.int32)
        for (dy,dx), mask in legal.items():
            ys,xs = np.nonzero(mask)
            sources.append(ids[ys,xs]); targets.append(ids[ys+dy,xs+dx])
        maps[rid] = {"frame":frame,"codes":codes,"safe":safe,"ids":ids,"manifest":manifest,
                     "worldSha":sha(world_raw),"collisionSha":sha(collision_raw),"servedSha":sha(served_raw),"grid":served}
        offset += count
        del raw,folded,legal
    for rid,x,y,dest,u,v in crossing["portals"]:
        src,dst = int(maps[rid]["ids"][y,x]),int(maps[dest]["ids"][v,u])
        if min(src,dst) < 0:
            raise ValueError("baseline crossing has a closed endpoint")
        sources.append(np.asarray([src],np.int32));targets.append(np.asarray([dst],np.int32))
    hub = next(s for s in sections if s["mapId"] == "landfall")
    seeds = []
    for entry in catalog["entries"]:
        rid = entry["id"]; frame = maps[rid]["frame"]
        scene = F.parse_scene(reader.read(F.git_path(entry["scenePath"])))
        for path,node in scene.nodes.items():
            if json.loads(node.properties.get("kind",'""')) != "spawn" or node.properties.get("default_spawn") != "true":
                continue
            point = scene.world(path)[:3,3]
            continent = frame.to_continent(point[0],point[2])
            if O.contains(*continent,hub["ownershipPolygons"],boundary=True):
                seeds.append((rid,*frame.tile(point[0],point[2])))
    if len(seeds) != 1:
        raise ValueError("baseline requires exactly one authored hub arrival")
    rid,x,y = seeds[0]
    seed = int(maps[rid]["ids"][int(y),int(x)])
    if seed < 0:
        raise ValueError("baseline plaza arrival is closed")
    src,dst = np.concatenate(sources),np.concatenate(targets)
    del sources,targets
    graph = coo_matrix((np.ones(len(src),np.int8),(src,dst)),shape=(offset,offset)).tocsr()
    del src,dst
    gc.collect()
    reached = np.zeros(offset,bool)
    reached[breadth_first_order(graph,seed,directed=True,return_predecessors=False)] = True
    del graph
    for record in maps.values():
        mask = record["ids"] >= 0
        record["reached"] = np.zeros(mask.shape,bool)
        record["reached"][mask] = reached[record["ids"][mask]]
        del record["ids"]
    return maps


def generate(server, checkout=F.CHECKOUT):
    checkout = Path(checkout)
    provenance = json.loads((META/"partition-inputs/input-provenance.json").read_text())
    reader = F.GitInputs(checkout,provenance["sourceCommit"])
    catalog = json.loads(reader.read(F.CATALOG_PATH))
    spec_raw = (META/"partition-inputs/sections_spec.json").read_bytes()
    sections = json.loads(spec_raw)["sections"]
    # Selection only decodes immutable baseline grids; do not import generation
    # modules while the independently owned server rewrite is in progress.
    sys.path.insert(0,str(Path(server).resolve()))
    from eloria import served_grid
    codec = SimpleNamespace(served_grid=served_grid)
    maps = baseline(reader,codec,catalog,sections)
    authored, exclusions = set(), []
    for entry in catalog["entries"]:
        rid = entry["id"]; record = maps[rid]
        scene = F.parse_scene(reader.read(F.git_path(entry["scenePath"])))
        tx,_,tz = record["frame"].translation
        for path,node in scene.nodes.items():
            if scene.script_of(node) != "res://src/dev/map_authoring_region/gameplay_marker.gd":
                continue
            kind = json.loads(node.properties.get("kind",'"landmark"'))
            point = scene.world(path)[:3,3] + [tx,0,tz]
            if kind == "spawn" and node.properties.get("default_spawn") == "true":
                owner = next((s["mapId"] for s in sections if O.contains(point[0],point[2],s["ownershipPolygons"],boundary=True)),None)
                if owner is None or owner in authored:
                    raise ValueError("authored arrival missing or duplicated ownership")
                authored.add(owner)
            if kind in ("npc_marker","interactive","portal","harvestable"):
                exclusions.append(point[[0,2]])
        source_spawns = json.loads(reader.read(f"eloria-assets/maps/continent-v2/{rid}/content/spawns.json"))
        exclusions.extend(np.asarray(r["local"],float)+[tx,tz] for r in source_spawns["spawns"])
    output, summary = {}, {}
    for section in sections:
        rid = section["mapId"]
        if rid in authored:
            continue
        print(f"Selecting {rid} arrival",file=sys.stderr,flush=True)
        representative = O.geometry(section["ownershipPolygons"]).representative_point()
        best = None
        prior = [s for s in sections[:sections.index(section)]]
        candidate_count = 0
        for source_index,(source,record) in enumerate(maps.items()):
            old = record["frame"]
            x0,z0,x1,z1 = section["bounds"]
            rows,columns = record["codes"].shape
            c0,c1 = max(0,int(np.floor(x0-old.lattice[0]))-1),min(columns,int(np.ceil(x1-old.lattice[0]))+1)
            r0,r1 = max(0,int(np.floor(old.lattice[1]-z1))-1),min(rows,int(np.ceil(old.lattice[1]-z0))+1)
            if c0 >= c1 or r0 >= r1:
                continue
            xs = (old.lattice[0]+np.arange(c0,c1)+.5)[None,:]
            zs = (old.lattice[1]-np.arange(r0,r1)-.5)[:,None]
            owned = O.contains(xs,zs,section["ownershipPolygons"],boundary=True)
            for previous in prior:
                px0,pz0,px1,pz1 = previous["bounds"]
                if px1 < x0 or px0 > x1 or pz1 < z0 or pz0 > z1:
                    continue
                owned &= ~O.contains(xs,zs,previous["ownershipPolygons"],boundary=True)
            safe = record["safe"][r0:r1,c0:c1] & record["reached"][r0:r1,c0:c1] & owned
            for dy,dx in E.ORTHOGONAL+E.DIAGONAL:
                safe &= E._neighbour(owned,dy,dx,False)
            ys,cols = np.nonzero(safe)
            cx = xs[0,cols]; cz = zs[ys,0]
            keep = np.ones(len(cols),bool)
            for ex,ez in exclusions:
                keep &= (np.abs(cx-ex)>2.5) | (np.abs(cz-ez)>2.5)
            ys,cols,cx,cz = ys[keep],cols[keep],cx[keep],cz[keep]
            candidate_count += len(cols)
            if not len(cols):
                continue
            distance = (cx-representative.x)**2+(cz-representative.y)**2
            idx = np.lexsort((cz,cx,distance))[0]
            key = (float(distance[idx]),float(cx[idx]),float(cz[idx]),source_index)
            if best is None or key < best[0]:
                best = (key,source,int(cols[idx])+c0,int(ys[idx])+r0)
        if best is None:
            raise ValueError(f"{rid}: no owned hub-reached safe 3x3 baseline arrival candidate")
        _,source,x,y = best; record = maps[source]
        frame = frames.load_source(rid,checkout)
        continent = record["frame"].continent(x,y)
        lx,lz = frame.to_local(*continent)
        position = [lx,record["grid"].elevation_metres(x,y),lz]
        result = {"schema":A.SCHEMA,"map":rid,"id":f"generated-arrival-{rid}","default":True,"generated":True,
                  "position":position,"serverTile":list(frame.tile(lx,lz)),"facing":[0.,0.,-1.],"frame":A.frame_record(frame),
                  "provenance":{"algorithm":A.ALGORITHM,"clientBaseCommit":reader.commit,"sectionsSpecSha256":sha(spec_raw),
                                "frameSha256":A.frame_sha256(frame),"sourceMap":source,"sourceTile":[x,y],
                                "sourceWorldSha256":record["worldSha"],"sourceCollisionSha256":record["collisionSha"],
                                "sourceServedGridSha256":record["servedSha"],"representativeContinent":[representative.x,representative.y],
                                "tieRule":"squared-distance, continent-x, continent-z, pinned-source-catalog-order",
                                "safeOwnedReachedCandidates":candidate_count}}
        path = checkout/f"eloria-assets/maps/continent-v2/{rid}/content/arrival.json"
        output[path] = F.json_bytes(result)
        summary[rid] = {"path":path.relative_to(checkout).as_posix(),"sha256":sha(output[path])}
    return output,summary,sorted(authored)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server",required=True,type=Path)
    parser.add_argument("--check",action="store_true")
    args = parser.parse_args()
    output,summary,authored = generate(args.server)
    problems = []
    for path,raw in output.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != raw:
                problems.append(f"differs: {path}")
        else:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    print(json.dumps({"authoredArrivalMaps":authored,"generatedArrivalBindings":summary,"problems":problems},indent=1))
    return int(bool(problems))


if __name__ == "__main__":
    raise SystemExit(main())
