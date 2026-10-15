"""Replay original-art equipment through the approved library's complete clips.

The body supplies the actual canonical TRS rest, rather than assuming that
matrix-authored equipment nodes contain the library's animation defaults.
"""
from __future__ import annotations
import argparse
import json
import sys
import hashlib
from pathlib import Path
import numpy as np

import equipment_authoring as ea

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS / 'tpose_bodies'))
import verify as body_verify

ROOT = TOOLS.parents[1]
CLIENT = ROOT / 'godot-client'
NATIVE = CLIENT / 'assets/actors/native'
CLIPS = ('Idle_Subtle', 'Walk', 'Jog', 'Run_Female', 'Fighting_Idle')


def skin_operator(points, joints, weights, bone_count):
    """Precompute the constant coefficients of linear-blend skinning.

    CSR multiplication performs the same four weighted affine transforms as
    the direct formula, without allocating a matrix copy for every vertex at
    every frame. All original samples, edge denominators and times remain.
    """
    from scipy.sparse import coo_matrix
    p = np.column_stack([points, np.ones(len(points))])
    columns = joints[:, :, None] * 4 + np.arange(4)
    rows = np.broadcast_to(np.arange(len(points))[:, None, None], columns.shape)
    values = weights[:, :, None] * p[:, None, :]
    operator = coo_matrix((values.ravel(), (rows.ravel(), columns.ravel())),
                          shape=(len(points), bone_count * 4)).tocsr()
    operator.eliminate_zeros()
    return operator


def replay(paths, race, out, runtime_bindings=None):
    runtime = json.loads(runtime_bindings.read_text()) if runtime_bindings else None
    if runtime and runtime["race"] != race:
        raise ValueError("Runtime binding report belongs to another wearer")
    inputs = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in [*paths, NATIVE / f'races/{race}.glb',
                           NATIVE / 'shared/Universal_Animation_Library.glb']}
    body, bb = ea.read_glb(NATIVE / f'races/{race}.glb')
    library, lb = ea.read_glb(NATIVE / 'shared/Universal_Animation_Library.glb')
    body_names = {n.get('name'): i for i,n in enumerate(body['nodes'])}
    assets = []
    if runtime:
        paths = [path for path in paths if path.name in runtime['assets']]
    for path in paths:
        d,b = ea.read_glb(path)
        if not d.get('skins'):
            continue
        for block in body_verify.groups(d,b):
            # Full outfits activate the paired lining instead of the default
            # clothing transition. Both variants remain covered by structure tests.
            if set(block['nodes']) & {'GeneratedBootBacking', 'GeneratedLegBacking'}:
                continue
            skin = d['skins'][block['skin']]
            names = [d['nodes'][j]['name'] for j in skin['joints']]
            block['body_nodes'] = [body_names[n] for n in names]
            block['bone_names'] = names
            block['binds'] = ea.accessor_array(d,b,skin['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1)
            if runtime:
                asset = runtime['assets'][path.name]
                if asset['sha256'] != hashlib.sha256(path.read_bytes()).hexdigest():
                    raise ValueError(f'Stale runtime binding evidence: {path}')
                surfaces = [asset['surfaces'][n] for n in block['nodes']]
                actual = surfaces[0]
                if any(q != actual for q in surfaces[1:]):
                    raise ValueError(f'Shared attributes have differing runtime bindings: {path}')
                if actual['names'] != names:
                    raise ValueError(f'Runtime joint order mismatch: {path}')
                block['binds'] = np.asarray(actual['binds'])
            # UV-split copies with identical positions and weights deform
            # identically. Transform each tuple once, while retaining every
            # original edge sample so the percentile denominator is unchanged.
            block['source_vertices'] = len(block['v'])
            keys = np.column_stack([block['v'], block['j'], block['w']])
            _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
            for field in ('v', 'j', 'w'):
                block[field] = block[field][first]
            block['edges'] = inverse[block['edges']]
            p,e=block['v'],block['edges']
            block['rest_length']=np.linalg.norm(p[e[:,0]]-p[e[:,1]],axis=1)
            block['path']=path.name
            block['operator'] = skin_operator(block['v'], block['j'], block['w'], len(names))
            block['binding_key'] = (tuple(block['body_nodes']), block['binds'].tobytes())
            assets.append(block)
    result = {'race':race,'clips':{},'scope':'full locomotion, paired linings, actual runtime binds' if runtime else 'full locomotion, paired linings, authored body'}
    for name in CLIPS:
        clip=next(a for a in library['animations'] if a['name']==name)
        channels=body_verify.retarget.clip_channels(library,lb,clip)
        keys=body_verify.retarget.clip_times(channels)
        times=np.unique(np.round(np.r_[keys,np.linspace(0,keys.max(),int(np.ceil(keys.max()*60))+1)],5))
        for block in assets:
            block['gain']=np.zeros(len(block['edges']));block['ratio']=np.ones(len(block['edges']))
            block['floor']=float('inf');block['loop']=0.;block['worst']={'extension_mm': -1.}
        for index,world in enumerate(body_verify.sample_worlds(body,library,lb,clip,times)):
            transforms = {}
            for block in assets:
                key = block['binding_key']
                if key not in transforms:
                    matrices = np.asarray([world[n] for n in block['body_nodes']]) @ block['binds']
                    transforms[key] = matrices[:, :3, :].transpose(0, 2, 1).reshape(-1, 3)
                p,j,w=block['v'],block['j'],block['w']
                posed = block['operator'] @ transforms[key]
                block['floor']=min(block['floor'],float(posed[:,1].min()))
                if index==0: block['first']=posed.copy()
                if index==len(times)-1: block['loop']=float(np.linalg.norm(posed-block['first'],axis=1).max())
                e=block['edges'];length=np.linalg.norm(posed[e[:,0]]-posed[e[:,1]],axis=1)
                gain=length-block['rest_length']; worst=int(gain.argmax())
                if gain[worst]*1000 > block['worst']['extension_mm']:
                    edge=e[worst];block['worst']={'extension_mm':float(gain[worst]*1000),'time':float(times[index]),
                        'points':p[edge].tolist(),'weights':[[[block['bone_names'][int(bone)],float(weight)] for bone,weight in zip(j[v],w[v]) if weight>.001] for v in edge]}
                block['gain']=np.maximum(block['gain'],gain)
                block['ratio']=np.maximum(block['ratio'],np.divide(length,block['rest_length'],out=np.ones_like(length),where=block['rest_length']>1e-5))
        rows=[]
        for block in assets:
            rows.append({'asset':block['path'],'surfaces':block['nodes'],'frames':len(times),
                         'source_vertices':block['source_vertices'], 'deformation_samples':len(block['v']),
                         'p99_extension_mm':float(np.percentile(block['gain'],99)*1000),
                         'max_extension_mm':float(block['gain'].max()*1000),
                         'max_edge_ratio':float(block['ratio'].max()),
                         'worst_edge':block['worst'],'min_y':block['floor'],'loop_error_mm':block['loop']*1000})
        result['clips'][name]=rows
        print(name, 'max extension mm', round(max(r['max_extension_mm'] for r in rows),2), flush=True)
    for filename, expected in inputs.items():
        if hashlib.sha256(Path(filename).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Motion input changed during replay: {filename}')
    result['input_sha256'] = inputs
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path);p.add_argument('--race',default='luminous_male')
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--runtime-bindings',type=Path,help='Actual Godot rebound skins, required for a compensated legacy baseline')
    p.add_argument('--assets',nargs='*',help='Optional source filenames')
    args=p.parse_args()
    paths=sorted(args.directory.glob('*.glb'))
    if args.assets: paths=[q for q in paths if q.name in args.assets]
    replay(paths,args.race,args.out,args.runtime_bindings)
