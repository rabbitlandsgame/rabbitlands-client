"""Frontmost-surface chest coverage, with an absolute proud-cell denominator.

Rasterize the same body and XY ray grid for both builds. Source art and backing
are reported separately. No left/right split, winding, enclosure parity or
runtime body hiding participates in this metric.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import equipment_authoring as ea
import import_generated_equipment as batch

CLIENT = Path(__file__).resolve().parents[2] / 'godot-client'


def front_depth(triangles, xs, ys):
    depth = np.full((len(ys), len(xs)), -np.inf)
    low, high = triangles.min(axis=1), triangles.max(axis=1)
    valid = (high[:,0]>=xs[0]) & (low[:,0]<=xs[-1]) & (high[:,1]>=ys[0]) & (low[:,1]<=ys[-1])
    for tri,lo,hi in zip(triangles[valid],low[valid],high[valid]):
        x0,x1=np.searchsorted(xs,[lo[0],hi[0]],side='left');x1=min(x1+1,len(xs))
        y0,y1=np.searchsorted(ys,[lo[1],hi[1]],side='left');y1=min(y1+1,len(ys))
        if x0>=x1 or y0>=y1: continue
        a,b,c=tri; den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(den)<1e-12: continue
        xx,yy=np.meshgrid(xs[x0:x1],ys[y0:y1])
        u=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/den
        v=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/den
        w=1.-u-v; inside=(u>=-1e-7)&(v>=-1e-7)&(w>=-1e-7)
        z=u*a[2]+v*b[2]+w*c[2]
        target=depth[y0:y1,x0:x1]
        np.maximum(target,np.where(inside,z,-np.inf),out=target)
    return depth


def surfaces(path, rig, runtime=None):
    doc,buf=ea.read_glb(path);out=[]
    for node in doc['nodes']:
        if 'mesh' not in node: continue
        mesh=doc['meshes'][node['mesh']];name=mesh.get('name',node.get('name',''))
        for primitive in mesh['primitives']:
            attr=primitive['attributes'];p=ea.accessor_array(doc,buf,attr['POSITION']).astype(float)
            f=ea.accessor_array(doc,buf,primitive['indices']).reshape(-1,3)
            if runtime and 'skin' in node:
                skin=doc['skins'][node['skin']];names=[doc['nodes'][j]['name'] for j in skin['joints']]
                data=runtime['surfaces'][node.get('name',name)]
                if data['names']!=names: raise ValueError('Runtime joint ordering mismatch')
                matrices=np.array([rig.rest[n] for n in names]) @ np.asarray(data['binds'])
                j=ea.accessor_array(doc,buf,attr['JOINTS_0']);w=ea.accessor_array(doc,buf,attr['WEIGHTS_0'])
                divisor=np.iinfo(w.dtype).max if doc['accessors'][attr['WEIGHTS_0']].get('normalized') and w.dtype.kind in 'ui' else 1.
                w=w.astype(float)/divisor;q=np.zeros_like(p)
                for k in range(4):q+=(np.einsum('nij,nj->ni',matrices[j[:,k],:3,:3],p)+matrices[j[:,k],:3,3])*w[:,k,None]
                p=q
            out.append((name,p[f]))
    return out


def measure(before, after, race, runtime_path, out, pieces=None):
    rig=ea.load_rig(CLIENT/f'assets/actors/native/races/{race}.glb', ea.BODY_SURFACES)
    runtime=json.loads(runtime_path.read_text())
    if runtime['body_sha256']!=hashlib.sha256((CLIENT/f'assets/actors/native/races/{race}.glb').read_bytes()).hexdigest():
        raise ValueError('Stale body in runtime evidence')
    chest=rig.origin('spine_03')[1]
    xs=np.linspace(-.235,.235,189);ys=np.linspace(chest-.065,chest+.055,49)
    body=front_depth(rig.positions[rig.faces],xs,ys);on_body=np.isfinite(body)
    at_chest=abs(ys-chest)<.011
    rows=[]
    for piece in batch.roster():
        if piece.part!=5 or (pieces and piece.slug not in pieces):continue
        row={'slug':piece.slug}
        for tag,root in [('before',before),('after',after)]:
            path=root/f'{piece.slug}.glb';actual=runtime['assets'][path.name] if tag=='before' else None
            sha=hashlib.sha256(path.read_bytes()).hexdigest()
            if actual and actual['sha256']!=sha:raise ValueError(f'Stale runtime asset {path}')
            meshes=surfaces(path,rig,actual);all_tri=np.concatenate([v for _,v in meshes])
            art=meshes[0][1]
            values={}
            for layer,tri in [('art',art),('all',all_tri)]:
                depth=front_depth(tri,xs,ys);proud=on_body & (depth>body+.001)
                values[layer]={'proud_cells':int(proud.sum()),'covered_width':float(proud[at_chest].sum()/on_body[at_chest].sum())}
            row[tag]=dict(values,sha256=sha)
        rows.append(row)
        print(piece.slug,round(row['before']['all']['covered_width'],3),round(row['after']['all']['covered_width'],3),flush=True)
    result={'race':race,'chest_y':float(chest),'grid':{'x':xs.tolist(),'y':ys.tolist(),'body_cells':int(on_body.sum()),'proud_clearance_m':.001},'pieces':rows}
    for tag in ('before','after'):
        result[tag]={layer:{'median_covered_width':float(np.median([r[tag][layer]['covered_width'] for r in rows])),
            'minimum_covered_width':min(r[tag][layer]['covered_width'] for r in rows),
            'total_proud_cells':sum(r[tag][layer]['proud_cells'] for r in rows)} for layer in ('art','all')}
    out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ('before','after')},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True)
    p.add_argument('--race',default='luminous_male');p.add_argument('--runtime-bindings',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--pieces',nargs='*',help='Optional explicit subset for a pilot comparison')
    a=p.parse_args();measure(a.before,a.after,a.race,a.runtime_bindings,a.out,a.pieces)
