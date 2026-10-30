"""Repair the twin-bun front hairline and internal coverage without changing its rig.

Prepare preserves a clipped copy of the imported curls for LOD reduction.
Finish adds a dense feathered scalp cap and closed bun underforms. Intermediate
files belong in ignored authoring storage; source and output must differ.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
import trimesh
import assemble, glbwriter, hairgen, headref, rlglb

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def scalp_for(head):
    return hairgen.Scalp(head,{'adjust':[[-180,0],[-110,0],[-70,-1],[-45,-3],[0,-3],[45,-3],[70,-1],[110,0],[180,0]]})

def read(g,b,p):
    a={k:rlglb.accessor(g,b,v) for k,v in p['attributes'].items()}
    t=rlglb.accessor(g,b,p['indices']).astype(int).reshape(-1,3)
    d=[rlglb.accessor(g,b,v['POSITION']) for v in p['targets']]
    return a,t,d

def scalar(scalp,p):
    lon,lat=headref.dir_lonlat(p-scalp.C)
    # Keep the rear curl mass, but remove the ragged face/temple segmentation.
    limit=scalp.hairline(lon)+3.0*assemble.smoothstep((115-abs(lon))/15)
    return np.where(abs(lon)<115,lat-limit,100.)

def prepare(source,stage):
    g,b=rlglb.read(str(source));head=headref.Head('female');scalp=scalp_for(head)
    a,T,D=read(g,b,g['meshes'][0]['primitives'][0])
    uv=a['TEXCOORD_0'];keep=~((uv[T,1]>=.7499).all(1)&(uv[T,1]<=.9).all(1));T=T[keep]
    rows={k:list(v) for k,v in a.items()};delta=[list(v) for v in D];faces=[]
    def add(i,j,f):
        n=len(rows['POSITION'])
        for k,v in a.items():
            if k in ('JOINTS_0','WEIGHTS_0'):rows[k].append(v[i].copy())
            else:rows[k].append(v[i]*(1-f)+v[j]*f)
        for k,v in enumerate(D):delta[k].append(v[i]*(1-f)+v[j]*f)
        return n
    for tri in T:
        poly=[]
        for k,i in enumerate(tri):
            j=tri[(k+1)%3];fi=float(scalar(scalp,a['POSITION'][i]));fj=float(scalar(scalp,a['POSITION'][j]))
            if fi>=0:poly.append(int(i))
            if (fi>=0)!=(fj>=0):
                lo,hi=0.,1.
                for _ in range(24):
                    mid=(lo+hi)/2;fm=scalar(scalp,a['POSITION'][i]*(1-mid)+a['POSITION'][j]*mid)
                    if (fm>=0)==(fi>=0):lo=mid
                    else:hi=mid
                poly.append(add(i,j,(lo+hi)/2))
        for k in range(1,len(poly)-1):faces.append([poly[0],poly[k],poly[k+1]])
    A={k:np.asarray(v) for k,v in rows.items()};F=np.asarray(faces,int);used,inv=np.unique(F,return_inverse=True)
    A={k:v[used] for k,v in A.items()};DD=np.array([np.asarray(v)[used] for v in delta]);F=inv.reshape(-1,3)
    stage.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(stage/'clipped.npz',**A,T=F,D=DD)
    (stage/'source.json').write_text(json.dumps({'source_sha256':sha(source),'clipped_triangles':len(F),'head_sha256':sha(head.glb_path)},indent=2))
    print('CLIPPED_CURLS',len(F),flush=True)

def lift_cap_chords(head,p,t,margin=.003,D=None):
    """Keep triangle interiors outside the ear/skull, not only their corners."""
    p=p.copy()
    for _ in range(8):
        q=p[t]
        samples=np.concatenate([q.mean(1),(q[:,0]+q[:,1])/2,(q[:,1]+q[:,2])/2,(q[:,2]+q[:,0])/2])
        sd,_,_,rim=head.signed(samples,D=D,with_rim=True)
        need=np.maximum(margin-sd,0);need[rim]=0
        need=need.reshape(4,-1).max(0)
        if need.max()<.00001:break
        lift=np.zeros(len(p));np.maximum.at(lift,t.ravel(),np.repeat(need,3))
        p+=headref.unit(p-head.C)*lift[:,None]*1.15
    return p

def cap(head,scalp,lod):
    # Even distant caps need latitude bands: long chords cut through skull.
    cols,rows=[(144,12),(72,12),(36,12)][lod]
    lon=np.linspace(-180,180,cols+1);lower=scalp.hairline(lon)
    # Dense bands at the visible hem avoid a low-poly serrated contour.
    fraction=np.r_[0,.015,.035,.065,np.linspace(.11,1,rows-3)]
    lat=lower[None]+(89.8-lower[None])*fraction[:,None]
    ll=np.broadcast_to(lon,lat.shape)
    p,n=scalp.point(ll.ravel(),lat.ravel(),.0045)
    t=[]
    for y in range(len(fraction)-1):
        for x in range(cols):
            k=y*(cols+1)+x;t.extend([[k,k+1,k+cols+1],[k+1,k+cols+2,k+cols+1]])
    t=np.asarray(t,int)
    radial=headref.unit(p-head.C)
    if np.median((headref.vertex_normals(p,t)*radial).sum(1))<0:t=t[:,[0,2,1]]
    distance=np.radians((lat-lower[None]).ravel())*head.R
    colour=np.ones((len(p),4));colour[:,0]=np.clip(distance/.007,0,1);colour[:,1]=np.clip(distance/.045,0,1);colour[:,2]=.85
    uv=np.c_[np.mod(ll.ravel()/60,1)*.72+.14,.756+.136*fraction.repeat(cols+1)]
    pole=len(p);last=(len(fraction)-1)*(cols+1)
    p=np.vstack([p,p[last:last+cols].mean(0)]);n=np.vstack([n,headref.unit(n[last:last+cols].mean(0))]);uv=np.vstack([uv,[.5,.89]]);colour=np.vstack([colour,[1,1,.85,1]])
    t=np.vstack([t,[[last+x,last+x+1,pole] for x in range(cols)]])
    if lod>0:p=lift_cap_chords(head,p,t)
    return p,n,uv,t,colour

def bun(side,lod):
    # Closed underforms remain inside the retained curl silhouette.
    center=np.array([side*.098,1.754,-.067]);radius=np.array([.033,.036,.047])
    m=trimesh.creation.icosphere(subdivisions=[2,1,1][lod]);p=np.asarray(m.vertices)*radius+center;t=np.asarray(m.faces)
    n=headref.unit((p-center)/radius**2)
    uv=np.c_[np.mod(np.arctan2(n[:,0],n[:,2])/(2*np.pi),1)*.72+.14,.756+.136*(n[:,1]+1)*.5]
    c=np.ones((len(p),4));c[:,1]=.5;c[:,2]=.82
    return p,n,uv,t,c

def fringe(head,scalp,lod):
    rng=np.random.default_rng(14414);count=[120,60,24][lod];segments=[4,3,2][lod]
    lon=np.linspace(-103,103,count)+rng.uniform(-.45,.45,count)
    P=[];N=[];UV=[];T=[]
    for i,lo in enumerate(lon):
        start=len(P);curve=rng.uniform(-1.3,1.3);column=1 if i%3 else 6;tip=rng.uniform(.10,.55)
        for j in range(segments+1):
            t=j/segments;angle=lo+curve*np.sin(np.pi*t);lat=float(scalp.hairline(angle))-tip+4.0*t
            center,n=scalp.point(np.array([angle]),np.array([lat]),np.array([.0007+.0014*t*t]))
            side,_=scalp.point(np.array([angle-.1,angle+.1]),np.array([lat,lat]),.001)
            width=headref.unit(side[1]-side[0])*.0011*(.10+.90*t)*.5
            for x,sgn in enumerate([-1,1]):
                P.append(center[0]+width*sgn);N.append(n[0]);UV.append([(column+.03+.94*x)/8,.999-.098*t])
        for j in range(segments):
            k=start+j*2;T.extend([[k,k+2,k+1],[k+1,k+2,k+3]])
    P=np.asarray(P);N=np.asarray(N);UV=np.asarray(UV);T=np.asarray(T,int)
    c=np.ones((len(P),4));c[:,0]=.5;c[:,1]=np.tile(np.repeat(np.linspace(0,1,segments+1),2),count);c[:,2]=.95
    return P,N,UV,T,c

def optional_curl_keep(p,t,colours,lod):
    """Let Messy reveal attached ornamental curls, never a coverage surface."""
    if lod:return colours
    _,weld=np.unique(np.round(p*1e6).astype(int),axis=0,return_inverse=True)
    adjacency=trimesh.graph.face_adjacency(weld[t])
    groups=trimesh.graph.connected_components(adjacency,min_len=1,nodes=np.arange(len(t)))
    mass=max(groups,key=len);anchor=np.unique(weld[t[mass]])
    colours=colours.copy()
    for faces in groups:
        if not 20<=len(faces)<=100:continue
        ids=np.unique(t[faces]);lo=p[ids].min(0);hi=p[ids].max(0)
        # Existing small curl tips on the left bun and right outer edge.
        left=hi[0]<-.04 and lo[1]>1.785
        right=lo[0]>.132 and lo[1]>1.70 and hi[1]<1.73
        if not (left or right):continue
        rest=np.ones(len(t),bool);rest[faces]=False
        # UV-seam duplicates root these tips in the main curl mass. Their
        # actual indices are private, so changing keep cannot fade that mass.
        if len(np.intersect1d(ids,t[rest])):continue
        if len(np.intersect1d(weld[ids],anchor))<3:continue
        colours[ids,3]=.36 if left else .26
    return colours

def write_primitive(w,a,T,D,material):
    return w.primitive(a['POSITION'].astype('f4'),headref.unit(a['NORMAL']).astype('f4'),a['TEXCOORD_0'].astype('f4'),T,np.clip(np.rint(a['COLOR_0']*255),0,255).astype('u1'),a['JOINTS_0'].astype('u1'),a['WEIGHTS_0'].astype('f4'),material,[(v,None) for v in D])

def finish(source,stage,out):
    g,b=rlglb.read(str(source));head=headref.Head('female');scalp=scalp_for(head)
    m0=g['meshes'][0];names=m0['extras']['targetNames'];base=np.load(stage/'clipped.npz')
    reference={k:base[k] for k in ['POSITION','NORMAL','TEXCOORD_0','COLOR_0','JOINTS_0','WEIGHTS_0']};P=reference['POSITION'];tree=cKDTree(P)
    D=base['D'];w=assemble.Writer('Rabbit Lands repaired curly twin-bun hairline')
    # Use the existing embedded atlas and canonical material flags.
    for mat in g['materials']:w.g.g['materials'].append(copy.deepcopy(mat))
    w.g.g['materials'][1].setdefault('extras',{})['softRootDetails']=True
    for image in g.get('images',[]):
        v=g['bufferViews'][image['bufferView']];png=b[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]
        view=w.g._view(png);im=copy.deepcopy(image);im['bufferView']=view;w.g.g.setdefault('images',[]).append(im)
    for key in ['textures','samplers']:w.g.g[key]=copy.deepcopy(g.get(key,[]))
    report={'source_sha256':sha(source),'tool_sha256':sha(__file__),'head_sha256':sha(head.glb_path),'lods':{}}
    for lod in range(3):
        q=np.load(stage/f'lod{lod}.npz');p=assemble.push_out_var(head,q['P'],.0045 if lod==2 else .0034);t=q['T'];uv=q['UV']
        dd,ii=tree.query(p,k=3);weight=1/np.maximum(dd,1e-5);weight/=weight.sum(1,keepdims=True)
        n=headref.unit((reference['NORMAL'][ii]*weight[:,:,None]).sum(1));nearest=ii[:,0]
        a={'POSITION':p,'NORMAL':n,'TEXCOORD_0':uv,'COLOR_0':np.ones((len(p),4)),'JOINTS_0':reference['JOINTS_0'][nearest],'WEIGHTS_0':reference['WEIGHTS_0'][nearest]}
        deltas=[(d[ii]*weight[:,:,None]).sum(1) for d in D]
        # Collapse can move a sparse temple vertex away from its old curl root.
        # Keep the existing groom while correcting just its buried endpoints.
        for index,nm in enumerate(names):
            if nm not in ('hl_length_n','hl_volume_n'):continue
            moved=assemble.push_out_var(head,p+deltas[index],.0033)
            deltas[index]=moved-p
        lon,lat=headref.dir_lonlat(p-head.C);edge=np.radians(np.maximum(lat-scalp.hairline(lon),0))*head.R
        eligible=abs(lon)<115;a['COLOR_0'][eligible,0]=np.clip(edge[eligible]/.007,0,1);a['COLOR_0'][:,1]=.5;a['COLOR_0'][:,2]=.90
        a['COLOR_0']=optional_curl_keep(p,t,a['COLOR_0'],lod)
        primitives=[write_primitive(w,a,t,deltas,0)];counts={'retained_curls':len(t)}
        for tag,data in [('cap',cap(head,scalp,lod)),('bun_left',bun(-1,lod)),('bun_right',bun(1,lod)),('root_fringe',fringe(head,scalp,lod))]:
            pp,nn,uu,tt,cc=data
            _,ni=tree.query(pp);aa={'POSITION':pp,'NORMAL':nn,'TEXCOORD_0':uu,'COLOR_0':cc,'JOINTS_0':reference['JOINTS_0'][ni],'WEIGHTS_0':reference['WEIGHTS_0'][ni]}
            if tag in ('cap','root_fringe'):
                bind=head.bind(pp,no_ears=True);normal=head.bound_normal(bind);height=((pp-bind['cp'])*normal).sum(1);ddeltas=[]
                exact=assemble.Binding(head,pp,bind['cp'],T=tt) if tag=='cap' else None
                for nm in names:
                    if not nm.startswith('id_'):ddeltas.append(np.zeros_like(pp));continue
                    dh=head.delta(nm);skin=head.bound_delta(bind,dh);moved_n=headref.vertex_normals(head.P+dh,head.T,head.weld);moved_n=headref.unit((moved_n[bind['tv']]*bind['bc'][:,:,None]).sum(1))
                    fitted=skin+(moved_n-normal)*height[:,None]
                    if tag=='cap':
                        fitted=exact.exact_clear(dh,fitted,.0025)
                        if lod==2 and nm=='id_ear_size_p':
                            fitted=lift_cap_chords(head,pp+fitted,tt,margin=.0015,D=dh)-pp
                    ddeltas.append(fitted)
            else:
                # Underforms shrink around their own attached scalp roots. A
                # nearest outer curl delta would over-shrink this smaller shell.
                roots=head.bind(pp,no_ears=True);root=roots['cp'];strand=pp-root
                ddeltas=[]
                for nm,d in zip(names,D):
                    if nm.startswith('id_'):ddeltas.append(head.bound_delta(roots,head.delta(nm)))
                    elif nm in ('hl_length_n','hl_volume_n'):ddeltas.append(-.30*strand)
                    else:ddeltas.append(d[ni].copy())
            primitives.append(write_primitive(w,aa,tt,ddeltas,1 if tag=='root_fringe' else 0));counts[tag]=len(tt)
        # Retain only details rooted inside the curl mass, not chopped face cards.
        cards,ct,cd=read(g,b,g['meshes'][lod]['primitives'][1]);lo,la=headref.dir_lonlat(cards['POSITION']-head.C)
        # Old front-cap cards form detached crown flecks at high detail.
        # The new attached fringe replaces them; keep only rear flyaways.
        kept=(abs(lo)>110)&(cards['COLOR_0'][:,3]>=.5)
        ct=ct[kept[ct].all(1)]
        if len(ct):primitives.append(write_primitive(w,cards,ct,cd,1))
        counts['fine_cards']=len(ct)
        w.mesh(g['meshes'][lod]['name'],primitives,names)
        counts['total']=sum(counts.values());report['lods'][f'lod{lod}']=counts
        print('REPAIRED_LOD',lod,counts,flush=True)
    w.g.g['nodes']=copy.deepcopy(g['nodes']);w.g.g['scenes']=copy.deepcopy(g['scenes']);w.g.g['scene']=g.get('scene',0)
    skin=copy.deepcopy(g['skins'][0]);skin['inverseBindMatrices']=w.g.accessor(rlglb.accessor(g,b,skin['inverseBindMatrices']).astype('f4'),'MAT4');w.g.g['skins']=[skin]
    w.g.g['asset']['extras']=copy.deepcopy(g['asset']['extras']);w.g.g['asset']['extras']['rlHair']['tris']={k:v['total'] for k,v in report['lods'].items()}
    w.g.g['asset']['extras']['rlHair']['hairlineRepair']={'smooth_front_clip':True,'root_feather_mm':7,'closed_bun_underforms':True}
    out.parent.mkdir(parents=True,exist_ok=True);w.save(str(out));report['output_sha256']=sha(out);out.with_suffix('.repair.json').write_text(json.dumps(report,indent=2))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('phase',choices=['prepare','finish']);parser.add_argument('--source',type=Path,required=True);parser.add_argument('--stage',type=Path,required=True);parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    if args.phase=='prepare':prepare(args.source,args.stage)
    else:
        if args.out is None or args.out.resolve()==args.source.resolve():parser.error('Finish requires a separate --out')
        finish(args.source,args.stage,args.out)
if __name__=='__main__':main()
