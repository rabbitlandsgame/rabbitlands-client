"""Build the separate symmetric female shirt mesh; canonical body stays exact.

Set RL_HEADS_BUILD and RL_MPFB_GROUPS to matching local head authoring inputs.
Preserve source and output in separate authoring stages.
"""
import argparse,copy,hashlib,json
from pathlib import Path
import numpy as np
import trimesh
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree
import rlglb,glbwriter,headref,assemble

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def clone_writer(g, b):
    w = glbwriter.GLB()
    w.g = copy.deepcopy(g)
    w.blob = bytearray(b)
    return w

def attrs(g, b, p):
    return {k: rlglb.accessor(g,b,v) for k,v in p['attributes'].items()}

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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    source=Path(a.source);dest=Path(a.out);assert source.resolve()!=dest.resolve();dest.parent.mkdir(parents=True,exist_ok=True)
    report=shirt(source,dest);report.update(source_sha256=sha(source),output_sha256=sha(dest),tool_sha256=sha(__file__))
    dest.with_suffix('.repair.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
