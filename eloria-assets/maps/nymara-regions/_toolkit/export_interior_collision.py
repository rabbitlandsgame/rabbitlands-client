"""Export a standalone room's real floors and declared solids to a half-metre grid.

Usage: python export_interior_collision.py --package <directory> --cells 36
Run after its authored GLB/manifest build, before server collision publication.
No guessed room rectangle or blanket open mask substitutes for rendered floors.
"""
from pathlib import Path
import argparse
import json
import numpy as np
import glb_reader as GLB
from open_walk_surfaces import encode


def export(package: Path, cells: int):
    path=package/'world.json'
    manifest=json.loads(path.read_text(encoding='utf-8'))
    if not manifest.get('asset',{}).get('interior'):
        raise ValueError('This exporter requires an authored standalone interior.')
    document,body=GLB.load(package/manifest['asset'].get('glb','world.glb'))
    prefixes=manifest.get('navigation',{}).get('surfaceNodePrefixes',[])
    if not prefixes:
        raise ValueError('Interior has no declared rendered walking surfaces.')
    floor_nodes=set(i for prefix in prefixes for i in GLB.named(document,prefix))
    solid_nodes=set(i for name in manifest.get('collision',{}).get('nodeNames',[])
                    for i in GLB.named(document,name))
    ox,oy=map(float,manifest['coordinateTransform']['serverOrigin'])
    size=cells*2
    floor,heights=GLB.rasterise(GLB.triangles(document,body,sorted(floor_nodes)),
                              size,size,-ox,oy,.5)
    # Declared solids exclude roofs and floors. Their actual horizontal faces
    # retain door gaps even when a wall node contains several separate pieces.
    solid,_=GLB.rasterise(GLB.triangles(document,body,sorted(solid_nodes)),
                         size,size,-ox,oy,.5,upward=-1.0)
    heights=np.where(floor & ~solid,heights,np.nan)
    if not np.isfinite(heights).any():
        raise ValueError('No exposed walkable floor remains.')
    low=float(np.nanmin(heights))
    grid,encoding=encode(heights,{'origin':low-.2,'step':.2,'range':[1,255]})
    manifest.setdefault('collision',{}).update(binary='collision.bin',
        format='EWCG',version=2,cellSize=.5,width=size,height=size,
        originMetres=[-ox,oy],heightEncoding=encoding,
        authoredSurfaceExport={'floorMeshNodes':len(floor_nodes),'solidMeshNodes':len(solid_nodes),
                              'walkableCells':int(np.count_nonzero(grid))})
    manifest['collision'].pop('actorSurfaceGuard', None)
    manifest['coordinateTransform']['serverCells']=[cells,cells]
    manifest['coordinateTransform']['addressableWorldBounds']={
        'min':[-ox,oy-cells+1],'max':[cells-1-ox,oy]}
    payload=GLB.HEADER.pack(b'EWCG',2,0,size,size)+grid.tobytes()
    (package/'collision.bin').write_bytes(payload)
    GLB.write_manifest(path,manifest)
    from guard_actor_surfaces import guard
    guard(package)
    return manifest['collision']['authoredSurfaceExport']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--cells',type=int,required=True)
    args=parser.parse_args()
    if args.cells<=0 or args.cells%6:
        parser.error('Server extent must be a positive multiple of six.')
    print(json.dumps(export(args.package.resolve(),args.cells),indent=2))
