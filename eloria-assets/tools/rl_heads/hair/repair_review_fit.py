"""Focused, reproducible repairs for the fitted pilot modules.

Preserves source binaries. Writes a candidate and a hash-bound report. The
shirt command produces a mesh override, leaving the canonical body/head cut
contract unchanged. Run from the client root with the normal RL head inputs.
"""
import argparse, copy, hashlib, json
from pathlib import Path
import numpy as np
import trimesh
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree
import rlglb, glbwriter, headref, assemble

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def clone_writer(g, b):
    w = glbwriter.GLB()
    w.g = copy.deepcopy(g)
    w.blob = bytearray(b)
    return w

def attrs(g, b, p):
    return {k: rlglb.accessor(g,b,v) for k,v in p['attributes'].items()}

def targets(g, b, p):
    return [rlglb.accessor(g,b,t['POSITION']) for t in p.get('targets',[])]

def write_attrs(w, a):
    out = {}
    for key, v in a.items():
        comp = 5121 if key.startswith('JOINTS') or key == 'COLOR_0' else 5126
        normalized = key == 'COLOR_0'
        if normalized: v = np.rint(v*255)
        out[key] = w.accessor(v,'VEC'+str(v.shape[1]),comp=comp,
            normalized=normalized,minmax=key=='POSITION',target=34962)
    return out

def replace_primitive(w, p, a, T, D=None):
    p['attributes'] = write_attrs(w,a)
    p['indices'] = w.accessor(T.reshape(-1),'SCALAR',comp=5125,target=34963)
    if D is not None:
        p['targets'] = [{'POSITION':w.sparse_vec3(d,minmax=True)} for d in D]

def clear_lips(a,T,D):
    """Clip the neutral lip opening exactly; interpolate its skin and morphs.

    The beard's root must follow the face, while the lips remain visible.
    Whole-triangle deletion alone would leave another jagged mouth outline.
    """
    from shapely.geometry import Polygon
    from shapely.ops import triangulate
    angle=np.arange(96)*2*np.pi/96
    mouth=Polygon(np.c_[.0285*np.cos(angle),1.578+.0118*np.sin(angle)])
    P=a['POSITION'];out={k:list(v) for k,v in a.items()};delta=[list(v) for v in D];faces=[]
    for t in T:
        q=P[t];poly=Polygon(q[:,:2])
        if not poly.is_valid or poly.area<1e-12 or not poly.intersects(mouth):
            faces.append(t.tolist());continue
        difference=poly.difference(mouth)
        for tri in triangulate(difference):
            if not difference.buffer(1e-12).covers(tri):continue
            face=[]
            for xy in np.asarray(tri.exterior.coords)[:3]:
                bc=np.linalg.solve(np.vstack([q[:,:2].T,np.ones(3)]),np.r_[xy,1])
                nearest=int(np.argmax(bc))
                if bc[nearest]>1-1e-7:face.append(int(t[nearest]));continue
                face.append(len(out['POSITION']))
                for key in a:
                    if key in ('JOINTS_0','WEIGHTS_0'):continue
                    out[key].append((a[key][t]*bc[:,None]).sum(0))
                dense={}
                for k in range(3):
                    for j,v in zip(a['JOINTS_0'][t[k]].astype(int),a['WEIGHTS_0'][t[k]]):dense[j]=dense.get(j,0)+v*bc[k]
                ranked=sorted(dense,key=dense.get,reverse=True)[:4];ranked += [0]*(4-len(ranked));weights=np.array([dense.get(j,0) for j in ranked]);weights/=weights.sum()
                out['JOINTS_0'].append(np.array(ranked));out['WEIGHTS_0'].append(weights)
                for k,d in enumerate(D):delta[k].append((d[t]*bc[:,None]).sum(0))
            faces.append(face)
    A={k:np.array(v) for k,v in out.items()};F=np.array(faces,int)
    # Shapely chooses its own winding. Retain the front-facing beard surface.
    n=headref.tri_normals(A['POSITION'],F);front=A['POSITION'][F].mean(1)[:,2]>.05
    flip=front&(n[:,2]<0);F[flip]=F[flip][:,[0,2,1]]
    return A,F,[np.array(v) for v in delta]

def bind_mouth_expressions(head,a,T,D,names):
    """Keep the moustache on the upper lip and the chin on the lower jaw.

    Newly clipped edge vertices cannot inherit a blend of both mouth sides.
    """
    import build_beard
    P=a['POSITION'];used=np.zeros(len(P),bool);used[np.unique(T)]=True
    use=used&(abs(P[:,0])<.052)&(P[:,1]>1.540)&(P[:,1]<1.625)&(P[:,2]>.04)
    ids=np.flatnonzero(use);Q=P[ids];B=build_beard.beard_center(head)
    def side(points):
        lon,lat=build_beard.frame_lonlat(B,points)
        return (lat>np.interp(abs(lon),[0,17,32,180],[-5,-5,-22,-22])).astype(int)
    binding=head.bind_split(Q,side(Q),side(head.P[head.T].mean(1)))
    normal=head.bound_normal(binding)
    for i,name in enumerate(names):
        if not name.startswith('ex_'):continue
        dh=head.delta(name);move=head.bound_delta(binding,dh)
        nm=headref.vertex_normals(head.P+dh,head.T,head.weld)
        moved=headref.unit((nm[binding['tv']]*binding['bc'][:,:,None]).sum(1))
        cp=(head.P[binding['tv']]*binding['bc'][:,:,None]).sum(1)
        height=((Q-cp)*normal).sum(1)
        D[i][ids]=move+(moved-normal)*height[:,None]

def secure_mouth(head,a,T,D,names,pilot_controls=None):
    """A target-only forward allowance for identity/expression combinations.

    Neutral geometry and the lip-opening outline in X/Y stay fixed. It covers curvature
    between the bound vertices and the additive target combinations.
    """
    P=a['POSITION'];used=np.zeros(len(P),bool);used[np.unique(T)]=True
    use=used&(abs(P[:,0])<.050)&(P[:,1]>1.545)&(P[:,1]<1.625)&(P[:,2]>.04)
    ids=np.flatnonzero(use);Q=P[ids].copy();dv=dict(zip(names,D))
    mixes={n:{n:1} for n in names if n.startswith(('id_','ex_'))}
    mixes.update(assemble.default_combos(names));mixes['jaw_smile']={'ex_jaw_open':1,'ex_smile':1}
    if pilot_controls:
        pilot={'id_'+n+('_p' if v>0 else '_n'):abs(v) for n,v in pilot_controls.items() if abs(v)>1e-7}
        mixes.update(pilot=pilot,pilot_jaw=pilot|{'ex_jaw_open':1},pilot_smile=pilot|{'ex_smile':1},pilot_jaw_smile=pilot|{'ex_jaw_open':1,'ex_smile':1})
    states=[]
    for mix in mixes.values():
        dh=sum((head.delta(n)*v for n,v in mix.items()),np.zeros_like(head.P))
        states.append((mix,dh,trimesh.Trimesh(head.P+dh,head.T,process=False)))
    before=[x.copy() for x in D]
    for _ in range(5):
        maximum=0.
        for mix,dh,mesh in states:
            dp=sum((dv[n][ids]*v for n,v in mix.items()),np.zeros_like(Q))
            sd,_,normal,rim=head.signed(Q+dp,D=dh,mesh=mesh,with_rim=True)
            # Match the validator's outside test around the oral folds.
            # A closest-normal sign alone can falsely classify an exposed
            # whisker as inside and push it far in front of the open mouth.
            deep=np.flatnonzero((sd<-.0005)&~rim)
            if len(deep):
                directions=headref.unit(np.array([[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1],[1,1,1],[1,1,-1],[1,-1,1],[1,-1,-1],[-1,1,1],[-1,1,-1],[-1,-1,1],[-1,-1,-1]],float))
                escape=np.zeros(len(deep),bool);X=Q[deep]+dp[deep]
                for direction in directions:escape|=~mesh.ray.intersects_any(X+direction*.0001,np.tile(direction,(len(X),1)))
                sd[deep[escape]]=np.inf
            step=np.where((sd<.0023)&~rim,np.minimum(np.maximum(.0026-sd,0)/np.maximum(abs(normal[:,2]),.3),.006),0)
            maximum=max(maximum,float(step.max()))
            norm=sum(v*v for v in mix.values())
            for n,v in mix.items():dv[n][ids,2]+=step*v/norm
        if maximum<1e-7:break
    correction=max(float(np.abs(x-y).max()*1000) for x,y in zip(D,before))
    return correction

def wave(source, dest):
    g,b=rlglb.read(str(source)); w=clone_writer(g,b); head=headref.Head('female')
    core=g['meshes'][0]['primitives'][0]; A=attrs(g,b,core); P=A['POSITION']
    names=g['meshes'][0]['extras']['targetNames']; D=targets(g,b,core)
    # A continuous, opaque inner curtain beneath the imported open curls.
    # This covers hanging hair as well as the pre-existing scalp shell.
    cy=-.035
    theta=np.mod(np.arctan2(P[:,0],P[:,2]-cy),2*np.pi)
    radius=np.linalg.norm(P[:,[0,2]]-[0,cy],axis=1)
    query=np.c_[P[:,1],np.cos(theta)*.10,np.sin(theta)*.10]
    tree=cKDTree(query); spatial=cKDTree(P)
    report={'lods':{}}
    for lod,(ny,nt) in enumerate([(17,12),(11,7),(7,7)]):
        yy,tt=np.meshgrid(np.linspace(1.502,1.713,ny),np.linspace(np.deg2rad(55),np.deg2rad(305),nt),indexing='ij')
        # Join the hanging inner surface into the temple/forelock above the
        # cheek. A constant opening leaves a triangular hole in 3/4 views.
        column=np.tile(np.linspace(0,1,nt),(ny,1))
        front=np.deg2rad(55-20*assemble.smoothstep((yy-1.62)/.07))
        tt=front+column*(2*np.pi-2*front)
        # Follow the curl rhythm at the open front edges rather than exposing
        # a straight curtain down either cheek.
        edge_weight=np.abs((tt-np.pi)/(np.pi-np.deg2rad(55)))**4
        tt += np.sign(np.pi-tt)*np.deg2rad(12)*np.sin((yy-1.50)/.072*2*np.pi)*edge_weight
        q=np.c_[yy.ravel(),np.cos(tt.ravel())*.10,np.sin(tt.ravel())*.10]
        dist, near=tree.query(q,k=18)
        rr=np.quantile(radius[near],.30,axis=1).reshape(ny,nt)
        rr=gaussian_filter(rr,.8)
        # Keep the inner envelope inset beneath the outer curl silhouette.
        rr=np.clip(rr-.007+.003*np.cos((yy-1.50)/.072*2*np.pi+tt*2),.092,.154)
        Q=np.c_[(rr*np.sin(tt)).ravel(), yy.ravel(), (cy+rr*np.cos(tt)).ravel()]
        Q=assemble.push_out_var(head,Q,np.full(len(Q),.004),iters=3)
        dd,ii=spatial.query(Q,k=3); weight=1/np.maximum(dd,1e-4);weight/=weight.sum(1,keepdims=True)
        delta=[(v[ii]*weight[:,:,None]).sum(1) for v in D]
        # The face-side edge stays rooted horizontally when length changes.
        edge=np.minimum(tt.ravel()-tt.min(),tt.max()-tt.ravel())
        anchor=assemble.smoothstep(edge/np.deg2rad(23))
        for n,v in zip(names,delta):
            if n.startswith('hl_'):
                v[:,[0,2]]*=anchor[:,None]
                if n.startswith('hl_length'):
                    v*=assemble.smoothstep((1.70-Q[:,1])/.10)[:,None]
                elif n=='hl_volume_n':
                    # This is the inner coverage layer, already inset close
                    # to the skin. The outer locks own reduced volume.
                    v[:]=0
        dv=dict(zip(names,delta));combos=assemble.default_combos(names)
        for n in names:combos['single_'+n]={n:1}
        for groom in [n for n in names if n.startswith('hl_')]:
            for suffix in ('_p','_n'):combos[groom+suffix]={n:1 for n in names if n.startswith('id_') and n.endswith(suffix)}|{groom:1}
        combos['groom_min']={'hl_length_n':1,'hl_volume_n':1}
        states=[(np.zeros_like(head.P),np.zeros_like(Q),head.mesh)]
        for mix in combos.values():
            dh=sum((head.delta(n)*v for n,v in mix.items() if n in head.deltas),np.zeros_like(head.P))
            dp=sum((dv[n]*v for n,v in mix.items()),np.zeros_like(Q))
            states.append((dh,dp,trimesh.Trimesh(head.P+dh,head.T,process=False)))
        start=Q.copy();radial=headref.unit(Q-head.C)
        for _ in range(6):
            step=np.zeros(len(Q))
            for dh,dp,surface in states:
                sd,_,normal,rim=head.signed(Q+dp,D=dh,mesh=surface,with_rim=True)
                step=np.maximum(step,np.where((sd<.0025)&~rim,np.minimum(np.maximum(.0028-sd,0)/np.maximum(abs((normal*radial).sum(1)),.3),.006),0))
            if step.max()<1e-7:break
            Q+=radial*step[:,None]
        T=[]
        for y in range(ny-1):
            for t in range(nt-1):
                k=y*nt+t;T.extend([(k,k+nt,k+1),(k+1,k+nt,k+nt+1)])
        T=np.asarray(T,int)
        radial=np.c_[np.sin(tt).ravel(),np.zeros(len(Q)),np.cos(tt).ravel()]
        N=headref.unit(radial+np.array([0,.12,0]))
        if np.median((headref.vertex_normals(Q,T)*radial).sum(1))<0:T=T[:,[0,2,1]]
        # Continuous wavy strand flow in the opaque clump strip. UV seams in
        # the imported curls must not be interpolated across atlas islands.
        v=(yy.ravel()-1.502)/(1.713-1.502)
        u=np.tile(np.linspace(.04,.96,nt),(ny,1)).ravel()
        UV=np.c_[u,.756+.136*v]
        col=np.ones((len(Q),4));col[:,1]=.5;col[:,2]=.90
        nearest=ii[:,0]
        a={'POSITION':Q,'NORMAL':N,'TEXCOORD_0':UV,'COLOR_0':col,
            'JOINTS_0':A['JOINTS_0'][nearest],'WEIGHTS_0':A['WEIGHTS_0'][nearest]}
        p={'material':core['material']}
        replace_primitive(w,p,a,T,delta)
        w.g['meshes'][lod]['primitives'].append(p)
        old=sum(g['accessors'][pr['indices']]['count']//3 for pr in g['meshes'][lod]['primitives'])
        report['lods'][str(lod)]={'added_vertices':len(Q),'added_triangles':len(T),'triangles':old+len(T),'continuous_grid':[ny,nt],'joint_groom_allowance_max_mm':float(np.linalg.norm(Q-start,axis=1).max()*1000)}
    w.g['asset']['extras']['rlHair']['tris']={f'lod{k}':v['triangles'] for k,v in report['lods'].items()}
    w.save(str(dest));return report

def beard(source,dest,pilot_controls=None):
    g,b=rlglb.read(str(source));w=clone_writer(g,b);head=headref.Head('male')
    report={'lods':{}}
    for lod,m in enumerate(g['meshes']):
        p=m['primitives'][0];a=attrs(g,b,p);P=a['POSITION'];T=rlglb.accessor(g,b,p['indices']).astype(int).reshape(-1,3)
        D=targets(g,b,p);names=m['extras']['targetNames']
        blend=(1-assemble.smoothstep((np.abs(P[:,0])-.025)/.023))*assemble.smoothstep((P[:,1]-1.551)/.020)*(1-assemble.smoothstep((P[:,1]-1.607)/.012))*assemble.smoothstep((P[:,2]-.045)/.02)
        ids=np.flatnonzero(blend>0)
        origins=P[ids].copy();origins[:,2]=.30
        directions=np.tile([0,0,-1.],(len(ids),1))
        locations,rays,tris=head.mesh.ray.intersects_location(origins,directions,multiple_hits=True)
        cp=P[ids].copy();tri=np.zeros(len(ids),int);ok=np.zeros(len(ids),bool)
        for ray in np.unique(rays):
            j=np.flatnonzero(rays==ray);j=j[np.argmax(locations[j,2])]
            cp[ray]=locations[j];tri[ray]=tris[j];ok[ray]=True
        blend[ids[~ok]]=0
        bc=headref.barycentric(cp,head.P[head.T[tri,0]],head.P[head.T[tri,1]],head.P[head.T[tri,2]])
        # Offset along the skin normal, including the steep subnasal surface;
        # a Z-only gap becomes almost zero at the base of the nose.
        normal=headref.unit((head.N[head.T[tri]]*bc[:,:,None]).sum(1))
        gap=.005+np.clip(P[ids,2]-cp[:,2]-.015,-.0005,.0005)
        Q=P.copy();Q[ids]=P[ids]+blend[ids,None]*(cp+normal*gap[:,None]-P[ids])
        changes=[]
        for name,d in zip(names,D):
            skin=(head.delta(name)[head.T[tri]]*bc[:,:,None]).sum(1)
            morphed_n=headref.vertex_normals(head.P+head.delta(name),head.T,head.weld)
            morphed_n=headref.unit((morphed_n[head.T[tri]]*bc[:,:,None]).sum(1))
            skin+=(morphed_n-normal)*gap[:,None]
            value=d.copy();value[ids]=d[ids]*(1-blend[ids,None])+skin*blend[ids,None]
            changes.append(value)
        _,weld=np.unique(np.round(Q/.00015),axis=0,return_inverse=True)
        a['POSITION']=Q;a['NORMAL']=headref.vertex_normals(Q,T,weld)
        a,T,changes=clear_lips(a,T,changes)
        bind_mouth_expressions(head,a,T,changes,names)
        envelope_mm=secure_mouth(head,a,T,changes,names,pilot_controls)
        a['NORMAL']=headref.unit(a['NORMAL'])
        invalid=np.linalg.norm(a['NORMAL'],axis=1)<.5
        a['NORMAL'][invalid]=headref.unit(a['POSITION'][invalid]-head.C)
        replace_primitive(w,w.g['meshes'][lod]['primitives'][0],a,T,changes)
        fully=blend[ids]>.99
        report['lods'][str(lod)]={'affected_vertices':int((blend>0).sum()),
            'maximum_move_mm':float(np.linalg.norm(Q-P,axis=1).max()*1000),
            'mouth_normal_offset_mm':(np.quantile(gap[fully],[0,.5,1])*1000).tolist() if fully.any() else [],
            'outside_region_unchanged':bool(np.array_equal(Q[blend==0],P[blend==0]))}
        report['lods'][str(lod)]['triangles']=len(T)
        report['lods'][str(lod)]['combination_allowance_max_mm']=envelope_mm
    w.g['asset']['extras']['rlBeard']['tris']={f'lod{k}':v['triangles'] for k,v in report['lods'].items()}
    w.save(str(dest));return report

def shirt(source,dest):
    g,b=rlglb.read(str(source));w=clone_writer(g,b)
    mesh=next(m for m in g['meshes'] if m['name']=='wardrobe_shirt');p=mesh['primitives'][0];a=attrs(g,b,p)
    T=rlglb.accessor(g,b,p['indices']).astype(int).reshape(-1,3)
    # Cut below every damaged tooth, retaining the rest of the garment.
    rx,rz,cz,cut=.080,.095,-.030,1.95
    body=next(m for m in g['meshes'] if m['name']=='body')['primitives'][0]
    skin_a=attrs(g,b,body);BP=skin_a['POSITION'];BT=rlglb.accessor(g,b,body['indices']).astype(int).reshape(-1,3)
    body_surface=trimesh.Trimesh(BP,BT,process=False)
    head=headref.Head('female')
    rim_angles=np.arange(192)*2*np.pi/192
    rim_y=1.50+.010*np.sin(rim_angles)**2-.075*np.maximum(np.cos(rim_angles),0)**4
    origin=np.c_[np.zeros(192),rim_y,np.full(192,cz)]
    direction=np.c_[np.sin(rim_angles),np.zeros(192),np.cos(rim_angles)]
    rim_radius=np.zeros(192)
    for surface in (body_surface,head.mesh):
        loc,rays,_=surface.ray.intersects_location(origin,direction,multiple_hits=True)
        for k in range(192):
            values=np.linalg.norm(loc[rays==k]-origin[k],axis=1)
            values=values[(values>.015)&(values<.13)]
            if len(values):rim_radius[k]=max(rim_radius[k],values.max())
    assert (rim_radius>.015).all(), 'Missing anatomical collar support'
    rim_radius=np.maximum(rim_radius,rim_radius[(-np.arange(192))%192])
    rim_radius=np.maximum(rim_radius,gaussian_filter(rim_radius,1.5,mode='wrap'))+.002
    def skin_radius(y,t):
        f=np.mod(t,2*np.pi)/(2*np.pi)*192;i=int(np.floor(f))%192
        return (1-f%1)*rim_radius[i]+(f%1)*rim_radius[(i+1)%192]
    def radius(P):return np.sqrt((P[...,0]/rx)**2+((P[...,2]-cz)/rz)**2)
    def seam_height(P):
        theta=np.arctan2(P[...,0]/rx,(P[...,2]-cz)/rz)
        return 1.421+.015*np.sin(theta)**2-.105*np.maximum(np.cos(theta),0)**4
    def signed(P):return np.maximum(radius(P)-cut,seam_height(P)-P[...,1])
    keys=list(a);rows=[];faces=[]
    def sample(i):return {k:v[i].copy() for k,v in a.items()}
    def lerp(v,u,t):
        x={k:(1-t)*v[k]+t*u[k] for k in keys if k not in ('JOINTS_0','WEIGHTS_0')}
        dense={}
        for z,f in ((v,1-t),(u,t)):
            for j,ww in zip(z['JOINTS_0'].astype(int),z['WEIGHTS_0']):dense[j]=dense.get(j,0)+ww*f
        ranked=sorted(dense,key=dense.get,reverse=True)[:4];ranked+= [0]*(4-len(ranked))
        x['JOINTS_0']=np.array(ranked);x['WEIGHTS_0']=np.array([dense.get(j,0) for j in ranked]);x['WEIGHTS_0']/=x['WEIGHTS_0'].sum()
        return x
    for tri in T:
        poly=[sample(i) for i in tri]
        if np.max(a['POSITION'][tri,1])>1.29 and np.min(radius(a['POSITION'][tri]))<cut:
            clipped=[]
            for i,v in enumerate(poly):
                u=poly[(i+1)%3];fv=signed(v['POSITION']);fu=signed(u['POSITION'])
                if fv>=0:clipped.append(v)
                if (fv<0)!=(fu<0):
                    lo,hi=0.,1.
                    for _ in range(28):
                        mid=(lo+hi)/2;fm=signed((1-mid)*v['POSITION']+mid*u['POSITION'])
                        if (fm<0)==(fv<0):lo=mid
                        else:hi=mid
                    clipped.append(lerp(v,u,(lo+hi)/2))
            poly=clipped
        start=len(rows);rows.extend(poly)
        for k in range(1,len(poly)-1):faces.append([start,start+k,start+k+1])
    A={k:np.array([v[k] for v in rows]) for k in keys};F=np.array(faces,int)
    P=A['POSITION'];U,first,wel=np.unique(np.round(P,7),axis=0,return_index=True,return_inverse=True)
    E=np.sort(wel[F[:,[0,1,1,2,2,0]].reshape(-1,2)],axis=1);E,c=np.unique(E,axis=0,return_counts=True);E=E[c==1]
    seam=E[(np.abs(signed(U[E]))<1e-5).all(1)&(U[E,1]>1.29).all(1)]
    seam_ids=np.unique(seam);assert len(seam_ids)>30
    # One ordered outer seam, then a regularly sampled mirrored inner rim.
    theta=np.mod(np.arctan2(U[seam_ids,0]/rx,(U[seam_ids,2]-cz)/rz),2*np.pi)
    order=np.argsort(theta);outer=first[seam_ids[order]];theta=theta[order]
    gaps=np.diff(np.r_[theta,theta[0]+2*np.pi])
    assert gaps.max()<.8, ('Incomplete collar seam',float(np.degrees(gaps.max())))
    nt=192;angle=np.arange(nt)*2*np.pi/nt
    inner=[];inner_rows=[];outer_samples=[]
    for t in angle:
        right=np.searchsorted(theta,t)%len(theta);left=(right-1)%len(theta)
        span=(theta[right]-theta[left])%(2*np.pi);f=((t-theta[left])%(2*np.pi))/max(span,1e-8)
        v=lerp({k:A[k][outer[left]] for k in keys},{k:A[k][outer[right]] for k in keys},f)
        outer_samples.append(copy.deepcopy(v))
        # Smooth rounded scoop, with a shallow central front dip.
        y=1.50+.010*np.sin(t)**2-.075*max(np.cos(t),0)**4
        radial=skin_radius(y,t)
        v['POSITION']=np.array([radial*np.sin(t),y,cz+radial*np.cos(t)])
        v['NORMAL']=headref.unit(np.array([np.sin(t)*.30,.9,np.cos(t)*.30]))
        inner.append(len(rows));rows.append(v);inner_rows.append(v)
    bridge=inner;base_count=len(faces)
    # Zipper triangulation joins the exact clipped seam to the smooth ring.
    i=j=0;no=len(outer)
    while i<no or j<nt:
        oi=i%no;ij=j%nt
        next_o=theta[(i+1)%no]+(2*np.pi if i+1>=no else 0)
        next_i=angle[(j+1)%nt]+(2*np.pi if j+1>=nt else 0)
        # Start both loops at angle zero by rotating the seam nearest zero.
        if i<no and (j>=nt or next_o<next_i):
            faces.append([int(outer[oi]),int(outer[(i+1)%no]),bridge[ij]]);i+=1
        else:
            faces.append([int(outer[oi]),bridge[(j+1)%nt],bridge[ij]]);j+=1
    A={k:np.array([v[k] for v in rows]) for k in keys};F=np.array(faces,int)
    # Correct the strip winding by requiring its top-facing normals.
    count=base_count;new=F[count:];norm=headref.tri_normals(A['POSITION'],new)
    flip=norm[:,1]<0;new[flip]=new[flip][:,[0,2,1]];F[count:]=new
    # Weld identical position/UV/skin tuples without losing UV seams.
    packed=np.c_[np.round(A['POSITION'],7),np.round(A['TEXCOORD_0'],7),A['JOINTS_0'],np.round(A['WEIGHTS_0'],6)]
    _,take,inv=np.unique(packed,axis=0,return_index=True,return_inverse=True);A={k:v[take] for k,v in A.items()};F=inv[F]
    _,wel=np.unique(np.round(A['POSITION'],7),axis=0,return_inverse=True);A['NORMAL']=headref.vertex_normals(A['POSITION'],F,wel)
    rim_points=np.array([v['POSITION'] for v in inner_rows]);is_rim=cKDTree(rim_points).query(A['POSITION'])[0]<1e-6
    tt=np.arctan2(A['POSITION'][is_rim,0],A['POSITION'][is_rim,2]-cz)
    A['NORMAL'][is_rim]=headref.unit(np.c_[np.sin(tt)*.3,np.full(len(tt),.9),np.cos(tt)*.3])
    repaired=w.g['meshes'][g['meshes'].index(mesh)]
    replace_primitive(w,repaired['primitives'][0],A,F[:count])
    # New fabric has its own continuous weave-free base; interpolating across
    # disconnected source-atlas islands would paint dark seam streaks here.
    material=w.material('Shirt collar fabric',[1,1,1,1],double=True)
    collar={'material':material}
    replace_primitive(w,collar,A,F[count:]);repaired['primitives'].append(collar)
    # Deliver only this mesh, retaining the exact canonical skeleton and binds.
    mi=g['meshes'].index(mesh)
    for node in w.g['nodes']:
        if 'mesh' in node:
            if node['mesh']==mi:node['mesh']=0
            else:node.pop('mesh');node.pop('skin',None)
    w.g['meshes']=[w.g['meshes'][mi]]
    w.g['asset']['generator']='Rabbit Lands symmetric female shirt neckline repair'
    w.save(str(dest))
    rim=np.array([v['POSITION'] for v in inner_rows]);mirror=rim.copy();mirror[:,0]*=-1
    symmetry=cKDTree(rim).query(mirror)[0]
    return {'triangles':len(F),'vertices':len(A['POSITION']),'rim_vertices':nt,
        'rim_mirror_max_mm':float(symmetry.max()*1000),'largest_rim_edge_mm':float(np.linalg.norm(rim-np.roll(rim,1,axis=0),axis=1).max()*1000),
        'canonical_body_unchanged':True,'skeleton_and_inverse_binds_preserved':True}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('kind',choices=['wave','beard','shirt']);ap.add_argument('--source',required=True);ap.add_argument('--out',required=True);ap.add_argument('--presets');ap.add_argument('--preset');args=ap.parse_args()
    source=Path(args.source);dest=Path(args.out);assert source.resolve()!=dest.resolve();dest.parent.mkdir(parents=True,exist_ok=True)
    if args.kind=='beard' and args.presets:
        controls=json.loads(Path(args.presets).read_text())['presets'][args.preset]['controls']
        report=beard(source,dest,controls);report.update(preset=args.preset,presets_sha256=sha(args.presets))
    else:report=globals()[args.kind](source,dest)
    report.update(kind=args.kind,source_sha256=sha(source),output_sha256=sha(dest),tool_sha256=sha(__file__))
    dest.with_suffix('.repair.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
