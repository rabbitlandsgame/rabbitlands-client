#!/usr/bin/env python3
"""CPU-only, source-built pilot atlas and physical invariants; no package writes.

Run each region in a fresh process because legacy builders import local modules.
"""
from pathlib import Path
import argparse, hashlib, importlib.util, json, sys, time
import numpy as np

HERE=Path(__file__).resolve().parent
REGIONS=HERE.parent
ROOT=REGIONS.parents[2]
sys.path[:0]=[str(REGIONS/'_toolkit'),str(HERE),str(ROOT/'eloria-assets/tools')]
import outer_aprons as O
import continent_geography as G
from verify_runtime import VerticalRayIndex


def ray(build):
    meshes=[m for n,m in build.terrain_meshes.items() if n.startswith('Terrain_') and '_StreamThreshold_' not in n and m.triangle_count]
    return VerticalRayIndex(np.concatenate([m.positions[m.indices].reshape(-1,3,3) for m in meshes]))


def atlas(build,region,path):
    import preview
    from amberwood import render as R
    import render_region_cartography as C
    colors=[];original=R.Scene.add_mesh
    def add(self,mesh,transform=None):
        if mesh.triangle_count:
            colors.append(np.ones((mesh.vertex_count,4)) if mesh.colors is None or mesh.material.startswith('water_') else mesh.colors)
        return original(self,mesh,transform)
    R.Scene.add_mesh=add
    try:scene=preview.scene_from_build(build)
    finally:R.Scene.add_mesh=original
    for i,m in enumerate(scene.materials):
        if m.name.startswith('water_') or m.name in C.WATER_NAMES:
            scene.materials[i]=R.RenderMaterial(m.name,C.WATER,roughness=1.,double_sided=True)
    spec=G.plan()['regions'][region]
    polygon=np.array(spec['ownershipPolygon'])-np.array(spec['translation'])[[0,2]]
    lo,hi=polygon.min(axis=0),polygon.max(axis=0)
    size=tuple(np.ceil((hi-lo)*1.5).astype(int))
    rgb,rgba,coverage,stats=C.raster(scene,np.ascontiguousarray(np.vstack(colors),dtype=np.float32),lo,hi,size,supersample=1)
    rgb.save(path);rgba.save(path.with_name(path.stem+'-coverage.png'))
    return {'worldMin':lo.tolist(),'worldMax':hi.tolist(),'imageSize':list(size),'triangles':scene.triangle_count(),**stats}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--region',choices=['amberwood','whitehorn_range'],required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    began=time.perf_counter();original=O.apply;report={}
    def audited(build,region,snapshot):
        print('PILOT pre-apron geometry ready',flush=True)
        before=ray(build)
        xs=np.linspace(snapshot.low[0]+.25,snapshot.high[0]-.25,35);zs=np.linspace(snapshot.low[1]+.25,snapshot.high[1]-.25,35)
        core=np.array([(x,z) for x in xs for z in zs]);heights=[before.top_hit(x,z) for x,z in core]
        points=([[-129,-300],[-79,-300],[-79,-280],[-79,-275]] if region=='amberwood' else [[-58,-288],[142,-288],[0,-275],[0,-285]])
        report['samplesBefore']=[{'xz':p,'y':before.top_hit(*p)} for p in points]
        report['beforeAtlas']=atlas(build,region,args.output/'before.png')
        print('PILOT before atlas written; shaping',flush=True)
        report['apron']=original(build,region,snapshot)
        print('PILOT shaping done; testing physical rays',flush=True)
        after=ray(build);deltas=[];misses=0
        for p,y in zip(core,heights):
            final=after.top_hit(*p)
            if y is None or final is None:
                misses+=int(y!=final);continue
            deltas.append(abs(y-final))
        report['coreRaySamples']=len(core);report['coreRayMissingChanges']=misses;report['coreRayMaximumDelta']=max(deltas,default=0)
        report['samplesAfter']=[{'xz':p,'y':after.top_hit(*p)} for p in points]
        report['afterAtlas']=atlas(build,region,args.output/'after.png')
        if misses or max(deltas,default=0)>1e-7:raise ValueError('Pilot moved native playable surface')
        return report['apron']
    O.apply=audited
    filename={'amberwood':'build_amberwood.py','whitehorn_range':'build_whitehorn.py'}[args.region]
    source=REGIONS/args.region/'source'/filename
    spec=importlib.util.spec_from_file_location('pilot_region_builder',source);builder=importlib.util.module_from_spec(spec);sys.modules[spec.name]=builder;spec.loader.exec_module(builder)
    build=builder.build_region()
    if not report:raise ValueError('Source did not call the installed outer apron hooks')
    report.update(region=args.region,elapsedSeconds=time.perf_counter()-began,helperSha256=hashlib.sha256((HERE/'outer_aprons.py').read_bytes()).hexdigest(),geographySha256=hashlib.sha256((REGIONS/'continent-geography.json').read_bytes()).hexdigest(),packageWritten=False)
    (args.output/'report.json').write_text(json.dumps(report,indent=2,default=lambda v:v.item() if isinstance(v,np.generic) else v)+'\n',encoding='utf-8')
    print(json.dumps(report,default=lambda v:v.item() if isinstance(v,np.generic) else v),flush=True)

if __name__=='__main__':main()
