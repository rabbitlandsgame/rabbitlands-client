"""Reference-derived loose hair with independent scalp coverage and rooted detail.

Keep reference extractions immutable. ``prepare`` writes a neutral source copy;
run decimate_reference_surface.py --weld-geometry on that copy. Repair only
measured accidental holes; blanket filling can close intentional curl windows.
Optional ``backing`` prepares an inset volume for smooth_loose_backing.py.
``pack`` writes the three-level runtime module and its qualification report.
No provider, network or generation service is used.
"""
import argparse,copy,hashlib,json,re,struct
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial import ConvexHull,cKDTree
from scipy import sparse
from scipy.sparse.linalg import factorized
import assemble,hairgen,headref,paths,reference_surface as ref,rlglb
from reference_root_edges import geometric_boundary,root_colours
from reference_collar_repair import repair as repair_collar
from reference_temple_conform import conform_temples

GROOMS=['hl_length_p','hl_length_n','hl_volume_p','hl_volume_n']
def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def save_json(path,value):Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=True)+'\n',encoding='utf8')
def profile(path):return json.loads(Path(path).read_text(encoding='utf8'))
def unit(value):return headref.unit(value)

def public_source(source):
    allowed=['fit_sha256','reference_sha256','source_extraction_sha256','profile_sha256','source_head_sha256','head_sha256','body_sha256','garment_sha256']
    result={'method':'reference exterior with independent scalp coverage and surface-rooted detail'}
    for key in allowed:
        value=source.get(key)
        if value is not None:
            assert isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value),key
            result[key]=value
    return result

def closest_batched(mesh,X):
    chunks=[trimesh.proximity.closest_point(mesh,X[start:start+512]) for start in range(0,len(X),512)]
    return tuple(np.concatenate([chunk[index] for chunk in chunks],axis=0) for index in range(3))

class BoundedHead(headref.Head):
    """Limit temporary nearest-triangle arrays for dense reference exteriors."""
    def raycast(self,origins,dirs,surface='noear',outermost=True):
        chunks=[super(BoundedHead,self).raycast(origins[start:start+1024],dirs[start:start+1024],surface,outermost) for start in range(0,len(origins),1024)]
        return tuple(np.concatenate([chunk[index] for chunk in chunks],axis=0) for index in range(3))
    def bind(self,X,no_ears=False):
        X=np.asarray(X,float);mesh=self.mesh_noear if no_ears else self.mesh
        cp,distance,tri=closest_batched(mesh,X);T=self.T_noear if no_ears else self.T;tv=T[tri]
        return {'tv':tv,'bc':headref.barycentric(cp,self.P[tv[:,0]],self.P[tv[:,1]],self.P[tv[:,2]]),'dist':distance,'cp':cp}
    def closest(self,X,P=None):
        X=np.asarray(X,float);points=self.P if P is None else P;mesh=self.mesh if P is None else trimesh.Trimesh(points,self.T,process=False)
        cp,distance,tri=closest_batched(mesh,X);t=self.T[tri]
        return cp,distance,tri,headref.barycentric(cp,points[t[:,0]],points[t[:,1]],points[t[:,2]])
    def signed(self,X,D=None,mesh=None,with_rim=False,T=None,geometric_sign=False):
        X=np.asarray(X,float);P=self.P if D is None else self.P+D;Tm=self.T if T is None else T
        if mesh is None:mesh=self.mesh if D is None and T is None else trimesh.Trimesh(P,Tm,process=False)
        cp,distance,tri=closest_batched(mesh,X);t=Tm[tri];bc=headref.barycentric(cp,P[t[:,0]],P[t[:,1]],P[t[:,2]])
        Nv=self.N if D is None else headref.vertex_normals(P,self.T,self.weld);normal=unit((Nv[t]*bc[:,:,None]).sum(1))
        if geometric_sign:
            from geometric_surface_sign import GeometricSurfaceSign
            signature=hashlib.sha256(P.tobytes()+Tm.tobytes()).digest()
            if getattr(mesh,'_rl_geometric_sign_key',None)!=signature:
                mesh._rl_geometric_sign=GeometricSurfaceSign(P,Tm,self.weld)
                mesh._rl_geometric_sign_key=signature
            normal=mesh._rl_geometric_sign.normals(tri,bc)
        sign=np.sign(((X-cp)*normal).sum(1));sign[sign==0]=1
        rim=((bc*self.rim[t]).sum(1)>.97)&(X[:,1]<cp[:,1]+.002)
        if T is not None and T is self.T_clear:rim|=((bc*self.rim_clear[t]).sum(1)>.97)&~self.rim[t].any(1)
        sign[rim]=1
        return (sign*distance,cp,normal,rim) if with_rim else (sign*distance,cp,normal)

def body_hull(head):
    g,b=rlglb.read(paths.body_glb(head.sex));points=[]
    cut=head.gltf['asset']['extras']['rlHead']['bodyCut']
    for mesh in g['meshes']:
        if mesh.get('name') not in ['body','wardrobe_shirt']:continue
        for primitive in mesh['primitives']:
            P=rlglb.accessor(g,b,primitive['attributes']['POSITION'])
            T=rlglb.accessor(g,b,primitive['indices'],normalize=False).astype(int).reshape(-1,3)
            if mesh.get('name')=='body':
                keep=np.ones(len(T),bool)
                for start,count in cut['hiddenBodyTriangles']:keep[start:start+count]=False
                T=T[keep]
            P=P[np.unique(T)]
            points.append(P)
    garment=Path(paths.body_glb(head.sex)).with_name('luminous_'+head.sex+'_shirt.glb')
    if garment.is_file():
        gg,gb=rlglb.read(str(garment))
        for mesh in gg['meshes']:
            if mesh.get('name')=='wardrobe_shirt':
                for primitive in mesh['primitives']:
                    P=rlglb.accessor(gg,gb,primitive['attributes']['POSITION']);T=rlglb.accessor(gg,gb,primitive['indices'],normalize=False).astype(int)
                    points.append(P[np.unique(T)])
    points=np.vstack(points)
    # A convex envelope must not bridge the entire outstretched-arm span.
    # Long locks use the torso/inner-shoulder neighborhood, where they hang.
    points=points[(points[:,1]>head.eye_mid[1]-.60)&(points[:,1]<head.eye_mid[1]-.06)&(abs(points[:,0])<.25)]
    return ConvexHull(points).equations

def outside_hull(P,equations,margin,mask=None):
    result=P.copy()
    ids=np.arange(len(P)) if mask is None else np.flatnonzero(mask)
    for start in range(0,len(ids),2048):
        batch=ids[start:start+2048];Q=result[batch]
        distance=Q@equations[:,:3].T+equations[:,3]
        face=np.argmax(distance,axis=1);value=distance[np.arange(len(Q)),face]
        amount=np.maximum(margin-value,0)
        result[batch]+=equations[face,:3]*amount[:,None]
    return result

def body_safe(head,P,equations,margin=.0035,radial=False):
    return P+shared_body_correction(head,P,[P],equations,margin,radial=radial)

def shared_body_correction(head,P,states,equations,margin=.0035,radial=False):
    """Exit forward/backward on a stable side; preserve hanging X and Y."""
    correction=np.zeros_like(P);margin=np.broadcast_to(np.asarray(margin,float),(len(P),))
    for start in range(0,len(P),2048):
        sl=slice(start,start+2048);base=P[sl]
        divide=head.C[2]-.05
        direction=np.zeros_like(base);direction[:,2]=np.where(base[:,2]>=divide,1.,-1.)
        if radial:
            direction=unit(np.c_[base[:,0]*.35,np.zeros(len(base)),base[:,2]-divide])
            if radial in ['nearest','drape']:
                horizontal=equations[:,:3].copy();horizontal[:,1]=0
                norm=np.linalg.norm(horizontal,axis=1);distance=base@equations[:,:3].T+equations[:,3]
                cost=np.where(norm>1e-6,np.maximum(margin[sl,None]-distance,0)/np.maximum(norm,1e-6),np.inf)
                outside=distance.max(1)>=margin[sl]
                cost[outside]=np.where(norm>1e-6,-distance[outside]/np.maximum(norm,1e-6),np.inf)
                direction=unit(horizontal[np.argmin(cost,axis=1)])
                if radial=='drape':
                    vertical=hairgen.smoothstep((base[:,1]-(head.eye_mid[1]-.20))/.035)
                    direction*=1-vertical[:,None];direction[:,1]=vertical;direction=unit(direction)
        slope=direction@equations[:,:3].T
        amount=np.zeros(len(base))
        for state in states:
            points=state[sl];distance=points@equations[:,:3].T+equations[:,3]
            tolerance=.00025 if radial else 0.
            inside=(distance.max(1)<margin[sl]-tolerance)&(points[:,1]<head.eye_mid[1]-.055)
            exits=np.where(slope>1e-6,np.maximum(margin[sl,None]-distance,0)/np.maximum(slope,1e-6),np.inf)
            need=exits.min(1);assert np.isfinite(need).all()
            amount=np.maximum(amount,np.where(inside,need,0))
        correction[sl]=direction*amount[:,None]
    return correction

def layer_margins(P,ranges,spec):
    head_margin=np.full(len(P),.0032);body_margin=np.full(len(P),.0035)
    head_margin[slice(*ranges['exterior'])]=float(spec.get('outer_head_margin_mm',5.5))/1000
    body_margin[slice(*ranges['exterior'])]=float(spec.get('outer_body_margin_mm',8.0))/1000
    body_margin[slice(*ranges['detail'])]=float(spec.get('outer_body_margin_mm',8.0))/1000-.0015
    return head_margin,body_margin

def curtain_body_safe(head,P,hull,margin=.0035,T=None):
    """Expand the lower mass smoothly around the torso without a side divide."""
    if T is not None:
        fitted,fixed=coherent_lower_depth(head,P,T,hull,margin)
        return fair_body_clearance(head,fitted,T,hull,margin,fixed=fixed)
    radial=np.c_[P[:,0]*.35,np.zeros(len(P)),P[:,2]-(head.C[2]-.05)]
    raw=body_safe(head,P,hull,margin,radial=True);needed=np.linalg.norm(raw-P,axis=1)
    fade=hairgen.smoothstep((head.eye_mid[1]-.055-P[:,1])/.10)
    lower=P[:,1]<head.eye_mid[1]-.13
    amount=np.max(needed[lower]/np.maximum(fade[lower],.05)) if lower.any() else 0
    displacement=unit(radial)*(amount*fade)[:,None]
    assert np.linalg.norm(displacement,axis=1).max()<.25,'Reference requires an excessive torso displacement'
    return body_safe(head,P+displacement,hull,margin,radial=True)

def mesh_laplacian(P,T):
    """Weld only coincident positions, retaining all original attribute loops."""
    _,first,weld=np.unique(np.round(P/1e-6),axis=0,return_index=True,return_inverse=True)
    base=P[first];tri=weld[T];edge=np.sort(tri[:,[0,1,1,2,2,0]].reshape(-1,2),axis=1)
    edge=np.unique(edge[edge[:,0]!=edge[:,1]],axis=0);length=np.linalg.norm(base[edge[:,0]]-base[edge[:,1]],axis=1)
    weight=np.minimum((.020/np.maximum(length,.0005))**2,1600)
    rows=np.r_[edge[:,0],edge[:,1]];cols=np.r_[edge[:,1],edge[:,0]];weights=np.r_[weight,weight]
    degree=np.bincount(rows,weights=weights,minlength=len(base))
    lap=sparse.diags(degree)-sparse.csr_matrix((weights,(rows,cols)),shape=(len(base),len(base)))
    return base,first,weld,lap

def coherent_lower_depth(head,P,T,hull,margin):
    """Move complete lower locks in depth, with a harmonic shoulder transition."""
    base,first,weld,lap=mesh_laplacian(P,T)
    lower=base[:,1]<head.eye_mid[1]-.20
    fixed=lower[weld]
    if not lower.any():return P.copy(),fixed
    raw=body_safe(head,base,hull,margin);front=base[:,2]>=head.C[2]-.05
    target=np.zeros(len(base));amounts=[]
    for side in [False,True]:
        selected=lower&(front==side);amount=float(np.max(np.abs((raw-base)[selected,2]))) if selected.any() else 0.
        target[selected]=amount*(1 if side else -1);amounts.append(amount*1000)
    anchor=lower|(base[:,1]>head.eye_mid[1]-.08)
    matrix=lap+sparse.diags(anchor.astype(float)*1e8+.0001)
    delta=factorized(matrix.tocsc())(target*anchor*1e8);delta[anchor]=target[anchor]
    fitted=P.copy();fitted[:,2]+=delta[weld]
    signed=(fitted[fixed]@hull[:,:3].T+hull[:,3]).max(1)
    assert (signed>=margin-.0003).all(),'Coherent lower locks must clear the torso before locking their shape'
    print('COHERENT_LOWER_DEPTH_MM',amounts,flush=True)
    return fitted,fixed

def fair_body_clearance(head,P,T,hull,margin=.0035,fixed=None):
    """Spread actual contact corrections over connected locks, with fixed roots."""
    base,first,weld,lap=mesh_laplacian(P,T)
    pinned=base[:,1]>=head.eye_mid[1]-.045;delta=np.zeros_like(base);target=np.zeros_like(base);active=np.zeros(len(base),bool)
    fixed_horizontal=np.zeros(len(base),bool) if fixed is None else fixed[first]
    proof=[]
    for iteration in range(8):
        correction=shared_body_correction(head,base,[base+delta],hull,margin,radial='drape');safe=base+delta+correction
        contact=np.linalg.norm(correction,axis=1)>1e-7;contact[pinned]=False
        active|=contact;target[contact]=safe[contact]-base[contact];target[pinned]=0
        if not active.any():return P.copy()
        contact_weight=25*10**min(iteration,5)
        penalty=active.astype(float)*contact_weight+pinned.astype(float)*1000+.0001
        matrix=lap+sparse.diags(penalty);solve=factorized((matrix+sparse.diags(fixed_horizontal.astype(float)*1e8)).tocsc())
        delta=solve(target*(active*contact_weight)[:,None])
        lower=base[:,1]<head.eye_mid[1]-.24
        solve_y=factorized((matrix+sparse.diags(lower.astype(float)*1e6)).tocsc())
        delta[:,1]=solve_y(target[:,1]*active*contact_weight);delta[lower,1]=0
        delta[fixed_horizontal,0]=0;delta[fixed_horizontal,2]=0
        assert np.isfinite(delta).all()
        delta[pinned]=0
        proof.append({'iteration':iteration,'contacts':int(contact.sum()),'max_contact_mm':float(np.linalg.norm(correction,axis=1).max()*1000)})
        print('FAIR_BODY_ITERATION',proof[-1],flush=True)
    result=base+delta;safe=result+shared_body_correction(head,base,[result],hull,margin,radial='drape')
    final=np.linalg.norm(safe-result,axis=1).max()*1000
    assert final<3.,('Body contact correction remains too local',final)
    print('FAIR_BODY_CLEARANCE',proof,'final_projection_mm',final,flush=True)
    return P+(safe-base)[weld]

def prepare(args):
    src=Path(args.source);out=Path(args.stage);assert not out.exists();out.mkdir(parents=True)
    spec=profile(args.profile);fit=profile(args.fit);sex=args.sex or fit['sex']
    source_head=BoundedHead(fit['sex']);source_scalp=hairgen.Scalp(source_head,spec.get('hairline'))
    a=np.load(src/'extracted.npz');P=ref.neutralize(source_head,a['P'],fit,source_scalp);N=a['N'].copy()
    if sex!=fit['sex']:
        target_head=BoundedHead(sex);target_scalp=hairgen.Scalp(target_head,spec.get('hairline'))
        Q,_=ref.roots(source_head,source_scalp,P)
        lon,lat=headref.dir_lonlat(Q-source_head.C)
        target_Q,target_N=target_scalp.point(lon,lat,0)
        radial=P-Q;ratio=target_head.R/source_head.R
        P=target_Q+radial*np.array([ratio,1.,ratio])
        if not spec.get('transport_normals',False):N=unit(N*np.array([1/ratio,1.,1/ratio]))
    head=BoundedHead(sex);hull=body_hull(head)
    P=assemble.push_out_var(head,P,np.full(len(P),.0032),iters=5)
    np.savez_compressed(out/'pre-body.npz',P=P,N=N,UV=a['UV'],T=a['T'])
    body_fit=curtain_body_safe if spec.get('preserve_curtain_depth',False) else body_safe
    options={'T':a['T']} if spec.get('preserve_curtain_depth',False) else {}
    P=body_fit(head,P,hull,float(spec.get('outer_body_margin_mm',8.0))/1000,**options)
    if spec.get('transport_normals',False):
        _,weld=np.unique(np.round(a['P']/1e-6),axis=0,return_inverse=True)
        N=unit(a['N']+assemble.morph_normals(a['P'],a['T'],a['N'],P-a['P'],weld))
    P,N,T,collar=repair_collar(head,P,N,a['UV'],a['T'],spec,np.asarray(Image.open(src/'hair-mask.png')))
    ranges={'exterior':[0,len(P)],'shell':[len(P),len(P)]}
    P,N,temple=conform_temples(head,hairgen.Scalp(head,spec.get('hairline')),P,N,T,ranges,spec)
    np.savez_compressed(out/'extracted.npz',P=P,N=N,UV=a['UV'],T=T)
    for name in ['hair-only.png','hair-mask.png']:copy_path=out/name;copy_path.write_bytes((src/name).read_bytes())
    source=profile(src/'source.json')
    source.update(sex=sex,source_sex=fit['sex'],neutralized=True,source_extraction_sha256=sha(src/'extracted.npz'),
                  profile_sha256=sha(args.profile),source_head_sha256=sha(source_head.glb_path),head_sha256=sha(head.glb_path),body_sha256=sha(paths.body_glb(sex)))
    garment=Path(paths.body_glb(sex)).with_name('luminous_'+sex+'_shirt.glb')
    if garment.is_file():source['garment_sha256']=sha(garment)
    source['fitting']={'preserve_curtain_depth':bool(spec.get('preserve_curtain_depth',False)),'transport_normals':bool(spec.get('transport_normals',False)),'collar_repair':collar,'temple_conformance':temple}
    save_json(out/'source.json',source);save_json(out/'lod-budgets.json',spec['outer_triangles'])
    print('PREPARED_LOOSE_REFERENCE',sex,len(P),len(a['T']),flush=True)

def backing(args):
    stage=Path(args.stage);spec=profile(args.profile);source=profile(stage/'source.json');head=BoundedHead(source['sex'])
    target=stage/'backing';assert not target.exists();target.mkdir()
    data=np.load(stage/'extracted.npz');P=data['P'];T=data['T'];config=spec['backing'];pitch=config['pitch_mm']/1000
    origin=P.min(0)-.025;shape=np.ceil((P.max(0)-origin+.025)/pitch).astype(int)+1
    assert np.prod(shape)<30_000_000,'Use a bounded head-and-shoulders extraction'
    voxel=trimesh.Trimesh(P,T,process=False).voxelized(pitch)
    ids=np.rint((voxel.points-origin)/pitch).astype(int);grid=np.zeros(shape,bool);grid[tuple(ids.T)]=True
    grid=ndi.distance_transform_edt(~grid)*pitch<=config['inflate_mm']/1000
    radius=config['close_mm']/1000
    grid=ndi.distance_transform_edt(ndi.distance_transform_edt(~grid)*pitch<=radius)*pitch>radius
    grid=ndi.binary_fill_holes(grid)
    # Fill depth only inside the existing hanging silhouette, around the face.
    projection=grid.any(2);closed=ndi.distance_transform_edt(ndi.distance_transform_edt(~projection)*pitch<=.006)*pitch>.006
    _,nearest=ndi.distance_transform_edt(~projection,return_indices=True)
    low=np.argmax(grid,axis=2);high=grid.shape[2]-1-np.argmax(grid[:,:,::-1],axis=2)
    xx=origin[0]+np.arange(shape[0])*pitch;yy=origin[1]+np.arange(shape[1])*pitch
    hang=closed&(abs(xx[:,None])>.057)&(yy[None,:]<head.eye_mid[1]-.02)
    for x,y in zip(*np.where(hang)):
        a,c=nearest[:,x,y];grid[x,y,low[a,c]:high[a,c]+1]=True
    grid=ndi.distance_transform_edt(grid)*pitch>config['erode_mm']/1000
    head_equations=ConvexHull(head.P[np.unique(head.T_clear)]).equations;body_equations=body_hull(head)
    occupied=np.argwhere(grid)
    for start in range(0,len(occupied),2048):
        ids=occupied[start:start+2048];Q=origin+ids*pitch
        head_inside=np.max(Q@head_equations[:,:3].T+head_equations[:,3],axis=1)<=config['head_margin_mm']/1000
        body_inside=(np.max(Q@body_equations[:,:3].T+body_equations[:,3],axis=1)<=config['body_margin_mm']/1000)&(Q[:,1]<head.eye_mid[1]-.055)
        grid[tuple(ids[head_inside|body_inside].T)]=False
    labels,count=ndi.label(grid);sizes=np.bincount(labels.ravel());sizes[0]=0
    assert sizes.max()>0,'No closed backing survived the body/head cavity'
    grid=(sizes>=max(80,sizes.max()*.002))[labels]
    corners=[];quads=[];offset=0
    definitions=[(0,-1,[(0,0,0),(0,0,1),(0,1,1),(0,1,0)]),(0,1,[(1,0,0),(1,1,0),(1,1,1),(1,0,1)]),(1,-1,[(0,0,0),(1,0,0),(1,0,1),(0,0,1)]),(1,1,[(0,1,0),(0,1,1),(1,1,1),(1,1,0)]),(2,-1,[(0,0,0),(0,1,0),(1,1,0),(1,0,0)]),(2,1,[(0,0,1),(1,0,1),(1,1,1),(0,1,1)])]
    for axis,sign,face in definitions:
        ids=np.argwhere(grid&~np.roll(grid,-sign,axis=axis));C=ids[:,None,:]+np.array(face)[None,:,:]
        corners.append(C.reshape(-1,3));quads.append(np.arange(offset,offset+4*len(ids)).reshape(-1,4));offset+=4*len(ids)
    U,inverse=np.unique(np.vstack(corners),axis=0,return_inverse=True)
    np.savez_compressed(target/'volume.npz',P=origin+(U-.5)*pitch,F=inverse[np.vstack(quads)])
    save_json(target/'config.json',{'pitch':pitch,'triangles':spec['backing_triangles']})
    save_json(target/'source.json',{'neutral_source_sha256':sha(stage/'extracted.npz'),'tool_sha256':sha(__file__),'config':config,'components_before_filter':int(count),'quads':int(offset//4),'method':'Inset closed backing; original painted exterior retained'})
    print('PREPARED_LOOSE_BACKING',len(U),offset//4,flush=True)

def make_atlas(stage,out):
    rgb=np.asarray(Image.open(stage/'hair-only.png').convert('RGB'),float)/255
    linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
    luminance=linear@np.array([.2126,.7152,.0722]);blur=ndi.gaussian_filter(luminance,6)
    neutral=np.clip(.35*(luminance/np.maximum(blur,1e-4))**.55,.13,.75)
    neutral[np.asarray(Image.open(stage/'hair-mask.png'))==0]=.35
    srgb=np.where(neutral<=.0031308,neutral*12.92,1.055*neutral**(1/2.4)-.055)
    paint=Image.fromarray(np.repeat(np.clip(srgb[:,:,None]*255,0,255).astype('u1'),3,axis=2))
    atlas=Image.new('RGBA',(1024,1024),(160,160,160,255));atlas.paste(paint.convert('RGBA').resize((1024,768),Image.Resampling.LANCZOS),(0,0))
    atlas.paste(Image.open(Path(paths.HAIR_TEX)/'hair_clump.png').convert('RGBA').resize((1024,154)),(0,768))
    atlas.paste(Image.open(Path(paths.HAIR_TEX)/'hair_strands.png').convert('RGBA').resize((1024,102)),(0,922))
    atlas.save(out);return sha(out)

def detail_cards(head,surface,source_normals,spec,lod):
    """Grow short strips on the actual exterior; their first row is inset."""
    config=spec['details'];rng=np.random.default_rng(spec['seed'])
    points=surface.vertices;radial=points-head.C;normals=source_normals
    eligible=(np.einsum('ij,ij->i',radial,normals)>-.002)&((abs(points[:,0])>.035)|(points[:,2]<head.C[2]-.025))
    eligible&=np.linalg.norm(normals,axis=1)>.5
    eligible&=(points[:,1]>points[:,1].min()+.025)&(points[:,1]<head.C[1]+.200)
    candidates=rng.permutation(np.flatnonzero(eligible));roots=[]
    fine_count=int(config['fine_count'][lod]);messy_count=int(config['messy_count'][lod]);count=fine_count+messy_count
    for row in candidates:
        if roots and np.linalg.norm(points[roots]-points[row],axis=1).min()<.008:continue
        roots.append(row)
        if len(roots)==count:break
    P=[];N=[];UV=[];T=[];COL=[];root_points=[];segments=int(config['segments'][lod])
    for number,row in enumerate(roots):
        messy=number>=fine_count;length=rng.uniform(*(config['messy_length_mm'] if messy else config['fine_length_mm']))/1000
        width=rng.uniform(*config['width_mm'])/1000;lift=config['messy_lift_mm' if messy else 'fine_lift_mm']/1000
        keep=rng.uniform(.08,.42) if messy else rng.uniform(.62,.95)
        column=int(rng.choice([4,5] if messy else [0,1]))
        rand=float(rng.uniform(.15,.85));phase=float(rng.uniform(0,2*np.pi))
        curve=[points[row]-normals[row]*config['root_inset_mm']/1000];along_normals=[normals[row]];base=points[row].copy()
        for step in range(1,segments+1):
            normal=along_normals[-1];flow=np.asarray(config.get('flow',[0.,-1.,0.]),float)
            direction=flow-normal*np.dot(flow,normal)
            if np.linalg.norm(direction)<.2:direction=np.array([np.sign(base[0]) or 1.,-.35,-.2])
            direction=unit(direction);guess=base+direction*(length/segments)
            cp,_,face=closest_batched(surface,guess[None]);tri=surface.faces[face[0]]
            bary=headref.barycentric(cp,surface.vertices[tri[0]][None],surface.vertices[tri[1]][None],surface.vertices[tri[2]][None])[0]
            normal=unit((source_normals[tri]*bary[:,None]).sum(0));base=cp[0]
            t=step/segments;outward=lift*hairgen.smoothstep(t)
            side=unit(np.cross(direction,normal));wave=side*np.sin(t*np.pi*1.5+phase)*lift*.25*np.sin(t*np.pi)
            curve.append(base+normal*outward+wave);along_normals.append(normal)
        curve=np.asarray(curve);along_normals=np.asarray(along_normals)
        start=len(P);root_points.append(curve[0])
        for step,(point,normal) in enumerate(zip(curve,along_normals)):
            t=step/segments;tangent=curve[min(step+1,segments)]-curve[max(step-1,0)];side=unit(np.cross(unit(tangent),normal))
            taper=max(.02,(.32+.68*np.sin(np.pi*min(t/.5,1)*.5))*(1-t)**.7)
            for edge in [-1,1]:
                P.append(point+side*width*.5*taper*edge);N.append(normal);UV.append([(column+.04+.92*(edge+1)/2)/8,.901+.098*t])
                COL.append([rand,t,.90,keep])
        for step in range(segments):
            a=start+step*2;T.extend([[a,a+1,a+2],[a+1,a+3,a+2]])
    return {'P':np.asarray(P).reshape(-1,3),'N':np.asarray(N).reshape(-1,3),'UV':np.asarray(UV).reshape(-1,2),'T':np.asarray(T,int).reshape(-1,3),'COL':np.asarray(COL).reshape(-1,4),'roots':np.asarray(root_points),'fine':min(fine_count,len(roots)),'messy':max(0,len(roots)-fine_count)}

def backing_part(stage,head,spec,lod,P,T):
    if spec.get('backing_mode','closed')=='none':
        return np.empty((0,3)),np.empty((0,3)),np.empty((0,2)),np.empty((0,3),int),{'backing_closed':False,'backing_components':0,'backing_omitted':True}
    volume=np.load(stage/'backing'/f'lod{lod}.npz');BP=volume['P'].astype(float);BT=volume['T'].astype(int)
    area=np.linalg.norm(np.cross(BP[BT[:,1]]-BP[BT[:,0]],BP[BT[:,2]]-BP[BT[:,0]]),axis=1)*.5
    BT=BT[area>1e-12];used,inverse=np.unique(BT,return_inverse=True);BP=BP[used];BT=inverse.reshape(-1,3)
    mesh=trimesh.Trimesh(BP,BT,process=False);assert mesh.is_watertight,'Backing must be closed at every LOD'
    exterior=trimesh.Trimesh(P,T,process=False);face_normal=unit(np.cross(P[T[:,1]]-P[T[:,0]],P[T[:,2]]-P[T[:,0]]))
    inset=float(spec.get('backing_inset_mm',2.5))/1000
    for _ in range(3):
        cp,dist,face=closest_batched(exterior,BP);normal=face_normal[face]
        signed=np.einsum('ij,ij->i',BP-cp,normal);bad=(signed>-inset)&(dist<.02)
        if not bad.any():break
        BP[bad]=cp[bad]-normal[bad]*inset
    BN=headref.vertex_normals(BP,BT);theta=np.arctan2(BP[:,0],BP[:,2]-head.C[2]);v=np.clip((head.C[1]+.10-BP[:,1])/.43,0,1)
    BU=np.c_[.5+.24*np.sin(theta),.756+.086*v]
    return BP,BN,BU,BT,{'backing_closed':True,'backing_components':int(mesh.body_count)}

def all_parts(stage,head,scalp,spec,lod):
    exterior=np.load(stage/f'lod{lod}.npz');high=np.load(stage/'extracted.npz')
    P=exterior['P'].astype(float);N=unit(exterior['N'].astype(float));T=exterior['T'].astype(int);UV=exterior['UV'].copy();UV[:,1]*=.75
    distance,nearest=cKDTree(high['P']).query(P,k=3);samples=high['N'][nearest];weight=1/np.maximum(distance,1e-5)
    weight*=np.maximum((samples*N[:,None,:]).sum(2),0)**2;smoothed=(samples*weight[:,:,None]).sum(1)
    good=np.linalg.norm(smoothed,axis=1)>1e-8;N[good]=unit(smoothed[good])
    source_surface=trimesh.Trimesh(high['P'],high['T'],process=False)
    cards=detail_cards(head,source_surface,unit(high['N']),spec,lod)
    BP,BN,BU,BT,backing_info=backing_part(stage,head,spec,lod,P,T)
    shell_spec=spec['shell'];rows,cols=shell_spec['lod'][str(lod)];SP,SN,SU,ST,_,_=hairgen.shell_mesh(scalp,shell_spec,rows,cols)
    SU[:,0]%=1.;SU[:,1]=.756+.086*SU[:,1]
    parts=[{'P':P,'N':N,'UV':UV,'T':T,'kind':'exterior'},{'P':BP,'N':BN,'UV':BU,'T':BT,'kind':'backing'},{'P':SP,'N':SN,'UV':SU,'T':ST,'kind':'shell'},cards]
    positions=[];normals=[];uv=[];triangles=[];colours=[];ranges={};offset=0
    for part in parts:
        count=len(part['P']);kind=part.get('kind','detail');ranges[kind]=[offset,offset+count]
        positions.append(part['P']);normals.append(part['N']);uv.append(part['UV']);triangles.append(part['T']+offset)
        colour=part.get('COL',np.tile([1.,0.,.92,1.],(count,1)));colours.append(colour);offset+=count
    P=np.vstack(positions);N=unit(np.vstack(normals));T=np.vstack(triangles)
    bad=np.abs(np.linalg.norm(N,axis=1)-1)>1e-6
    if bad.any():
        geometric=headref.vertex_normals(P,T);fallback=unit(P-head.C)
        valid=np.linalg.norm(geometric,axis=1)>.5;N[bad]=np.where(valid[bad,None],unit(geometric[bad]),fallback[bad])
    N=unit(N)
    assert np.abs(np.linalg.norm(N,axis=1)-1).max()<1e-6,'Invalid normals before expensive morph work'
    return P,N,np.vstack(uv),T,np.vstack(colours),ranges,backing_info|{'fine_cards':cards['fine'],'messy_cards':cards['messy'],'exterior_triangles':len(exterior['T']),'backing_triangles':len(BT),'detail_triangles':len(cards['T'])}

def groom_fields(head,scalp,P,names,spec,hull,ranges,triangles=None):
    Q,normal=ref.roots(head,scalp,P);binding=assemble.Binding(head,P,Q,follow=.015,fade=.025,stretch=.5,no_ears=True)
    head_margin,body_margin=layer_margins(P,ranges,spec)
    shell=slice(*ranges['shell']);cap_binding=head.bind(P[shell],no_ears=True)
    delta={};radial=bool(spec.get('preserve_curtain_depth',False))
    for name in names:
        Dh=head.delta(name);D=binding.delta(Dh,margin=.0028)
        D[shell]=head.bound_delta(cap_binding,Dh)
        mesh=trimesh.Trimesh(head.P+Dh,head.T,process=False)
        moving=np.linalg.norm(Dh,axis=1)>1e-5
        near=np.flatnonzero(np.isfinite(cKDTree(head.P[moving]).query(P,distance_upper_bound=np.linalg.norm(Dh,axis=1).max()+.04)[0])) if moving.any() else np.array([],int)
        # Ear-side tangents can defeat the scalp-bound normal; use actual
        # morphed surface normals for the final small attachment correction.
        for _ in range(5):
            if not len(near):break
            sd,cp,n,rim=head.signed(P[near]+D[near],D=Dh,mesh=mesh,with_rim=True)
            bad=(sd<head_margin[near])&~rim
            if not bad.any():break
            indices=near[bad];D[indices]=cp[bad]+n[bad]*(head_margin[indices]+.0006)[:,None]-P[indices]
        D=body_safe(head,P+D,hull,body_margin,radial=radial)-P;delta[name]=D
    # Reserve only the near-head neighborhood for stacked identity envelopes.
    # Keep the dense original extraction/LOD stages unchanged during repairs.
    near=np.flatnonzero(binding.dist<.05)
    if len(near):
        P[near]=ref.joint_groom_clearance(head,P[near],{n:delta[n][near] for n in names},names,head_margin[near],combos=assemble.default_combos(names))
        P[:]=body_safe(head,P,hull,body_margin,radial=radial);Q,normal=ref.roots(head,scalp,P)
    root_distance=np.linalg.norm(P-Q,axis=1);low,high=np.asarray(spec['groom']['root_fade_mm'])/1000
    fade=hairgen.smoothstep((root_distance-low)/(high-low));shell=slice(*ranges['shell']);fade[shell]=0
    lon,lat=headref.dir_lonlat(P-head.C)
    scalp_depth=np.maximum((lat-scalp.hairline(lon))*np.pi/180*head.R,0)
    volume_fade=np.maximum(fade,hairgen.smoothstep((scalp_depth-.001)/.025));volume_fade[shell]=0
    horizontal=unit(np.c_[P[:,0],np.zeros(len(P)),P[:,2]-head.C[2]])
    horizontal_radius=np.linalg.norm(np.c_[P[:,0],P[:,2]-head.C[2]],axis=1)
    hanging=hairgen.smoothstep((head.eye_mid[1]+.015-P[:,1])/.09)
    # Low curtains widen horizontally; upward scalp normals cannot erase volume.
    volume_direction=unit(normal*(1-hanging[:,None])+horizontal*hanging[:,None])
    stand=np.maximum(np.einsum('ij,ij->i',P-Q,normal)-.0045,0)
    volume_size=np.maximum(stand,.012)*(1-hanging)+horizontal_radius*hanging
    if 'hanging_volume_mm' in spec['groom']:
        volume_size=np.maximum(stand,.012)*(1-hanging)+np.minimum(horizontal_radius,spec['groom']['hanging_volume_mm']/1000)*hanging
    for name in GROOMS:
        positive=name.endswith('_p');config=spec['groom']
        if 'length' in name:
            move=(P-Q)*fade[:,None]*config['length_positive' if positive else 'length_negative']*(1 if positive else -1)
            if config.get('hanging_axis_length',False):move[:,[0,2]]*=1-hanging[:,None]
        else:move=volume_direction*(volume_size*volume_fade*config['volume_positive' if positive else 'volume_negative']*(1 if positive else -1))[:,None]
        move[shell]=0
        safe=assemble.push_out_var(head,P+move,head_margin,iters=5)
        if 'length' in name and config.get('coherent_length',False):
            assert triangles is not None,'Coherent lock motion requires source connectivity'
            safe=curtain_body_safe(head,safe,hull,float(spec.get('outer_body_margin_mm',8.0))/1000,T=triangles)
        else:safe=body_safe(head,safe,hull,body_margin,radial=radial)
        safe=ref.joint_groom_clearance(head,safe,delta,names,head_margin)
        safe+=shared_body_correction(head,P,[safe],hull,body_margin,radial=radial)
        delta[name]=safe-P
    # Volume shortening shares its clearance with length shortening. Alternate
    # the two endpoint envelopes; body corrections share one outward direction.
    for _ in range(3):
        volume=P+delta['hl_volume_n'];pair=volume+delta['hl_length_n']
        safe=ref.joint_groom_clearance(head,pair,delta,names,head_margin)
        delta['hl_volume_n']+=safe-pair
        volume=P+delta['hl_volume_n'];safe=ref.joint_groom_clearance(head,volume,delta,names,head_margin)
        delta['hl_volume_n']+=safe-volume
        volume=P+delta['hl_volume_n'];pair=volume+delta['hl_length_n']
        delta['hl_volume_n']+=shared_body_correction(head,P,[volume,pair,volume+delta['hl_length_p']],hull,body_margin,radial=radial)
    volume=P+delta['hl_volume_p']
    delta['hl_volume_p']+=shared_body_correction(head,P,[volume,volume+delta['hl_length_p'],volume+delta['hl_length_n']],hull,body_margin,radial=radial)
    # All duplicated geometric seams receive exactly the same deformation.
    _,weld=np.unique(np.round(P/1e-6),axis=0,return_inverse=True);counts=np.bincount(weld)
    for name in names+GROOMS:
        total=np.zeros((len(counts),3));np.add.at(total,weld,delta[name]);delta[name]=total[weld]/counts[weld,None]
    # The scalp coverage surface follows identity, while grooming affects
    # only the visible locks. Endpoint guards must not move this fixed cap.
    for name in GROOMS:delta[name][shell]=0
    return Q,root_distance,delta

def patch_roots(args):
    """Recolour root coverage only; retain geometry and morph bytes exactly."""
    source=Path(args.source);out=Path(args.out);spec=profile(args.profile)
    assert source.name==out.name and source.resolve()!=out.resolve()
    assert not out.exists() and not out.with_suffix('.png').exists()
    original=source.read_bytes();g,b=rlglb.read(str(source));extras=g['asset']['extras']['rlHair']
    assert extras['style']==spec['name'];head=BoundedHead(extras['sex']);scalp=hairgen.Scalp(head,spec.get('hairline'))
    assert extras['headSHA256']==sha(head.glb_path)
    result=bytearray(original);binary_start=20+struct.unpack_from('<I',original,12)[0]+8
    allowed=np.zeros(len(original),bool);records=[]
    for mesh in g['meshes']:
        for primitive in mesh['primitives']:
            material=g['materials'][primitive['material']]
            if material.get('name')!='rl_hair_clump':continue
            P=rlglb.accessor(g,b,primitive['attributes']['POSITION']);UV=rlglb.accessor(g,b,primitive['attributes']['TEXCOORD_0'])
            T=rlglb.accessor(g,b,primitive['indices'],normalize=False).astype(int).reshape(-1,3)
            index=primitive['attributes']['COLOR_0'];accessor=g['accessors'][index]
            assert accessor['componentType']==5121 and accessor['type']=='VEC4' and 'sparse' not in accessor
            COL=rlglb.accessor(g,b,index);part_ranges=primitive.get('extras',{}).get('partVertexRanges',{})
            if 'exterior' in part_ranges:e0,e1=part_ranges['exterior']
            else:
                e0=0;e1=int((UV[:,1]<.75).sum());assert (UV[:e1,1]<.75).all() and (UV[e1:,1]>=.75).all()
            Q,_=ref.roots(head,scalp,P);distance=np.linalg.norm(P-Q,axis=1)
            colour_ranges=copy.deepcopy(part_ranges) if part_ranges else {'exterior':[e0,e1]}
            colour_ranges['detail']=[len(P),len(P)]
            updated=root_colours(head,scalp,P,T,COL,colour_ranges,distance,spec)
            view=g['bufferViews'][accessor['bufferView']];stride=view.get('byteStride',4);start=binary_start+view.get('byteOffset',0)+accessor.get('byteOffset',0)
            values=np.rint(np.clip(updated[:,0],0,1)*255).astype('u1')
            for row,value in enumerate(values):allowed[start+row*stride]=True;result[start+row*stride]=int(value)
            records.append({'mesh':mesh.get('name'),'changed_vertices':int((np.rint(COL[:,0]*255).astype('u1')!=values).sum())})
    changed=np.frombuffer(original,dtype='u1')!=np.frombuffer(result,dtype='u1');assert not (changed&~allowed).any()
    out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(result)
    if source.with_suffix('.png').exists():out.with_suffix('.png').write_bytes(source.with_suffix('.png').read_bytes())
    report={'source_sha256':sha(source),'output_sha256':sha(out),'profile_sha256':sha(args.profile),'tool_sha256':sha(__file__),'only_root_coverage_bytes_changed':True,'geometry_skin_morphs_material_metadata_unchanged':True,'changed_bytes':int(changed.sum()),'lods':records,'qualified':False}
    save_json(out.with_suffix('.roots.json'),report);print(json.dumps(report),flush=True)

def pack(args,groom_builder=None,atlas_builder=None,colour_builder=None,parts_builder=None):
    stage=Path(args.stage);spec=profile(args.profile);source=profile(stage/'source.json');head=BoundedHead(source['sex']);scalp=hairgen.Scalp(head,spec.get('hairline'))
    assert not source.get('held',False),'Source stage is held by its authoring review'
    assert source['profile_sha256']==sha(args.profile),'Prepare a fresh stage for a changed style profile'
    assert source['head_sha256']==sha(head.glb_path),'Prepared head inputs changed'
    body_sha=sha(paths.body_glb(source['sex']))
    assert source.get('body_sha256',body_sha)==body_sha,'Prepared body inputs changed'
    source['body_sha256']=body_sha
    garment=Path(paths.body_glb(source['sex'])).with_name('luminous_'+source['sex']+'_shirt.glb')
    if garment.is_file():
        assert source.get('garment_sha256',sha(garment))==sha(garment),'Prepared garment input changed'
        source['garment_sha256']=sha(garment)
    out=Path(args.out);assert not out.exists() and not out.with_suffix('.png').exists();out.parent.mkdir(parents=True,exist_ok=True)
    atlas=out.with_suffix('.png');atlas_sha=(atlas_builder or make_atlas)(stage,atlas);writer=assemble.Writer('Rabbit Lands reference-derived loose hair')
    core_extras={'texture':atlas.name,'softHairline':True,'softRootCoverage':True,'uvStrandHighlights':False}
    if 'paint_flatness' in spec:
        value=float(spec['paint_flatness']);assert 0<=value<=1 and np.isfinite(value)
        core_extras['paintFlatness']=value
    core=writer.material('rl_hair_clump',[1,1,1,1],extras=core_extras)
    card=writer.material('rl_hair_card',[1,1,1,1],cutoff=.35,extras={'texture':atlas.name,'softRootDetails':True})
    writer.embed_texture(core,str(atlas));writer.g.g['materials'][card]['pbrMetallicRoughness']['baseColorTexture']=copy.deepcopy(writer.g.g['materials'][core]['pbrMetallicRoughness']['baseColorTexture'])
    names=head.id_names();hull=body_hull(head);meshes=[];report={'style':spec['name'],'sex':source['sex'],'source':source,'profile_sha256':sha(args.profile),'tool_sha256':sha(__file__),'atlas_sha256':atlas_sha,'head_sha256':sha(head.glb_path),'checked_head_clearance':bool(args.check),'qualified':False,'lods':{},'clearance':{},'body_clearance':{}}
    for lod in (0,1,2):
        P,N,UV,T,COL,ranges,info=(parts_builder or all_parts)(stage,head,scalp,spec,lod)
        head_margin,body_margin=layer_margins(P,ranges,spec)
        P=assemble.push_out_var(head,P,head_margin+.0008+assemble.headroom(head,P,names,frac=.6,no_ears=False),iters=5);P=body_safe(head,P,hull,body_margin,radial=bool(spec.get('preserve_curtain_depth',False)))
        if getattr(args,'neutral_only',False):
            assert not args.check,'Neutral previews do not qualify morphs'
            Q,_=ref.roots(head,scalp,P);distance=np.linalg.norm(P-Q,axis=1);delta={n:np.zeros_like(P) for n in names+GROOMS}
            report['neutral_geometry_preview']=True
        elif groom_builder:Q,distance,delta=groom_builder(head,scalp,P,names,spec,hull,ranges)
        else:Q,distance,delta=groom_fields(head,scalp,P,names,spec,hull,ranges,triangles=T)
        core_end=ranges['detail'][0];COL=(colour_builder or root_colours)(head,scalp,P,T,COL,ranges,distance,spec)
        joints=np.zeros((len(P),4),np.uint8);weights=np.zeros((len(P),4),'f4');weights[:,0]=1
        is_detail=(T>=core_end).all(1);primitives=[]
        for mask,material in [(~is_detail,core),(is_detail,card)]:
            if not mask.any():continue
            used,inverse=np.unique(T[mask],return_inverse=True)
            primitive=writer.primitive(P[used].astype('f4'),N[used].astype('f4'),UV[used].astype('f4'),inverse.reshape(-1,3),np.rint(np.clip(COL[used],0,1)*255).astype('u1'),joints[used],weights[used],material,[(delta[name][used],None) for name in names+GROOMS])
            exported={}
            for kind,(start,end) in ranges.items():
                local=np.flatnonzero((used>=start)&(used<end))
                if len(local):
                    assert np.array_equal(local,np.arange(local[0],local[-1]+1))
                    exported[kind]=[int(local[0]),int(local[-1]+1)]
            primitive['extras']={'partVertexRanges':exported};primitives.append(primitive)
        meshes.append(writer.mesh(f'hair_lod{lod}',primitives,names+GROOMS))
        info.update(tris=len(T),vertices=len(P),groom_displacement_mm={name:float(np.linalg.norm(delta[name],axis=1).max()*1000) for name in GROOMS})
        report['lods'][str(lod)]=info
        if args.check:
            combos=assemble.default_combos(names)
            for groom in GROOMS:
                for suffix in ['_p','_n']:combos[groom+'+all_id'+suffix]={name:1 for name in names if name.endswith(suffix)}|{groom:1}
            combos['groom_min']={'hl_length_n':1,'hl_volume_n':1};head_delta={name:head.delta(name) for name in names}|{name:np.zeros_like(head.P) for name in GROOMS}
            for length in ['hl_length_p','hl_length_n']:
                for volume in ['hl_volume_p','hl_volume_n']:combos[length+'+'+volume]={length:1,volume:1}
            report['clearance'][str(lod)]=assemble.clearance(head,P,head_delta,delta,names+GROOMS,combos=combos)
        body_cases={}
        for label,mix in {'rest':{},'length_min':{'hl_length_n':1},'length_max':{'hl_length_p':1},'volume_min':{'hl_volume_n':1},'volume_max':{'hl_volume_p':1},'groom_min':{'hl_length_n':1,'hl_volume_n':1}}.items():
            points=P+sum((delta[name]*weight for name,weight in mix.items()),np.zeros_like(P));points=points[points[:,1]<head.eye_mid[1]-.055]
            signed=np.max(points@hull[:,:3].T+hull[:,3],axis=1) if len(points) else np.array([])
            body_cases[label]={'min_mm':float(signed.min()*1000) if len(signed) else None,'violations':int((signed<.002).sum())}
        for length in ['hl_length_p','hl_length_n']:
            for volume in ['hl_volume_p','hl_volume_n']:
                points=P+delta[length]+delta[volume];points=points[points[:,1]<head.eye_mid[1]-.055]
                signed=np.max(points@hull[:,:3].T+hull[:,3],axis=1) if len(points) else np.array([])
                body_cases[length+'+'+volume]={'min_mm':float(signed.min()*1000) if len(signed) else None,'violations':int((signed<.002).sum())}
        report['body_clearance'][str(lod)]=body_cases
        print('LOOSE_HAIR_LOD',lod,info,flush=True)
    g=writer.g;node=g.node(name='hair_root',**rlglb.trs_from_matrix(head.head_G));g.g['scenes'][0]['nodes'].append(node)
    ibm=g.accessor(np.stack([rlglb.mat4_to_gltf(np.linalg.inv(head.head_G))]),'MAT4');g.g['skins']=[{'joints':[node],'inverseBindMatrices':ibm,'skeleton':node,'name':'RLHairSkin'}]
    for lod,mesh in enumerate(meshes):g.g['scenes'][0]['nodes'].append(g.node(name=f'hair_lod{lod}',mesh=mesh,skin=0))
    g.g['asset']['extras']={'rlHair':{'version':1,'style':spec['name'],'sex':source['sex'],'headSHA256':sha(head.glb_path),'springs':[],'collisions':[],'tris':{f'lod{k}':v['tris'] for k,v in report['lods'].items()},'grooming':{'shapes':GROOMS,'lengthRange':[-spec['groom']['length_negative'],spec['groom']['length_positive']],'volumeRange':[-spec['groom']['volume_negative'],spec['groom']['volume_positive']]},'source':public_source(source),'materials':{'rl_hair_clump':atlas.name}}}
    report['bytes']=writer.save(str(out));report['output_sha256']=sha(out)
    report['within_budget']=all(report['lods'][str(lod)]['tris']<=budget for lod,budget in enumerate([18000,7000,2500]))
    save_json(out.with_suffix('.report.json'),report)
    assert report['within_budget'],'Inspect saved LOD budgets'
    assert not any(case['violations'] for lod in report['body_clearance'].values() for case in lod.values()),'Inspect saved body-clearance report'
    if args.check:assert not any(value['rest']['violations'] or value['morphs']['violatingCases'] for value in report['clearance'].values()),'Inspect saved head-clearance report'
    print('SAVED_LOOSE_HAIR',str(out),report['output_sha256'],flush=True)
    return report

def parser():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('step',choices=['prepare','backing','pack','root-edges'])
    ap.add_argument('--source');ap.add_argument('--fit');ap.add_argument('--stage');ap.add_argument('--profile',required=True)
    ap.add_argument('--sex',choices=['female','male']);ap.add_argument('--out');ap.add_argument('--check',action='store_true');ap.add_argument('--neutral-only',action='store_true')
    return ap
def main():
    args=parser().parse_args()
    if args.step=='root-edges':assert args.source and args.out;patch_roots(args);return
    assert args.stage
    if args.step=='prepare':assert args.source and args.fit;prepare(args)
    elif args.step=='backing':backing(args)
    else:assert args.out;pack(args)
if __name__=='__main__':main()
