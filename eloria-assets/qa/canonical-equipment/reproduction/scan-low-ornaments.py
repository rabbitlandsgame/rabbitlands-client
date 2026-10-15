from pathlib import Path
import sys,json
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'eloria-assets/tools'))
import refit_canonical_equipment as r
import torso_remap as t

def scan(piece):
    source=piece.source.with_name(piece.source.name+'.orig')
    mesh,_=r.ce.read_source(source);p=mesh.positions;f=mesh.indices.reshape(-1,3)
    canon,edges,count=r.ce._weld(p,f);labels=r.ce._components(edges,count)[canon]
    height=np.ptp(p[:,1]);frames=t.source_skeleton(p);found=[]
    for side,sign in [('l',1),('r',-1)]:
        root,wrist=frames[side]
        for label in np.unique(labels):
            block=p[labels==label];c=np.unique(np.round(block,5),axis=0).mean(axis=0)
            if block[:,0].min()<-.075*height and block[:,0].max()>.075*height:continue
            if c[0]*sign<.17*height:continue
            if block[:,1].max()<wrist[1]-.16*height:
                found.append(dict(side=side,label=int(label),vertices=len(block),min=block.min(axis=0).tolist(),max=block.max(axis=0).tolist(),centroid=c.tolist(),wrist=wrist.tolist(),height=float(height),was_arm=bool(c[0]*sign>.25*height or t.long_sleeve_island(block,c,root,wrist,height))))
    return dict(slug=piece.slug,source=str(source),source_sha256=r.digest(source),low_ornaments=found)

if __name__=='__main__':
    rows=[scan(p) for p in r.batch.roster() if p.part==5]
    r.write_json(ROOT/'equipment-fit-build/reports/low-ornament-source-scan.json',rows)
    for row in rows:
        if row['low_ornaments']:print(json.dumps(row),flush=True)
    print('SCANNED',len(rows),'AFFECTED',sum(bool(x['low_ornaments']) for x in rows))
