"""Close the fitted shoulder-wave volume, preserving canonical skin/morphs.

Prepare a versioned ignored stage, smooth/decimate it with the companion Blender
helper, then pack a runtime candidate. Never overwrite the supplied source.
"""
import argparse,copy,hashlib,json
from pathlib import Path
import numpy as np
import trimesh
from scipy import ndimage as ndi
from scipy.spatial import ConvexHull
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import rlglb,headref,assemble,glbwriter

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def source_data(path):
    g,b=rlglb.read(str(path));m=g['meshes'][0];names=m['extras']['targetNames'];Ps=[];Ts=[];Ds={n:[] for n in names};offset=0
    for pr in m['primitives']:
        if g['materials'][pr['material']]['name']!='rl_hair_clump':continue
        P=rlglb.accessor(g,b,pr['attributes']['POSITION']);T=rlglb.accessor(g,b,pr['indices']).astype(int).reshape(-1,3)
        Ps.append(P);Ts.append(T+offset);offset+=len(P)
        for n,t in zip(names,pr['targets']):Ds[n].append(rlglb.accessor(g,b,t['POSITION']))
    return g,b,np.vstack(Ps),np.vstack(Ts),{n:np.vstack(d) for n,d in Ds.items()},names

def prepare(source,stage):
    stage.mkdir(parents=True,exist_ok=True);g,b,P,T,D,names=source_data(source)
    assert g['asset']['extras']['rlHair']['style']=='shoulder_waves'
    pitch=.0018;origin=P.min(0)-.045;shape=np.ceil((P.max(0)-origin+.045)/pitch).astype(int)+1
    mesh=trimesh.Trimesh(P,T,process=False);vox=mesh.voxelized(pitch)
    I=np.rint((vox.points-origin)/pitch).astype(int);grid=np.zeros(shape,bool);grid[tuple(I.T)]=True
    grid=ndi.distance_transform_edt(~grid)*pitch<=.0032
    dilation=ndi.distance_transform_edt(~grid)*pitch<=.011
    grid=ndi.distance_transform_edt(dilation)*pitch>.011
    grid=ndi.binary_fill_holes(grid)
    # Hanging curls need continuous depth beneath their visible front surface.
    # Fill their existing X/Y envelope, leaving the central face/neck open.
    projection=grid.any(2);closed=ndi.distance_transform_edt(ndi.distance_transform_edt(~projection)*pitch<=.009)*pitch>.009
    _,near=ndi.distance_transform_edt(~projection,return_indices=True)
    low=np.argmax(grid,axis=2);high=grid.shape[2]-1-np.argmax(grid[:,:,::-1],axis=2)
    xx=origin[0]+np.arange(shape[0])*pitch;yy=origin[1]+np.arange(shape[1])*pitch
    region=closed&(abs(xx[:,None])>.060)&(yy[None,:]>1.475)&(yy[None,:]<1.675)
    xs,ys=np.where(region)
    for x,y in zip(xs,ys):
        a,c=near[:,x,y];grid[x,y,low[a,c]:high[a,c]+1]=True
    # Reserve a convex cavity around the entire head, including the ears.
    # Merely clearing vertices lets the triangles between them cross an ear.
    head=headref.Head('female');hull=ConvexHull(head.P[np.unique(head.T_clear)]);eq=hull.equations
    occupied=np.argwhere(grid)
    for start in range(0,len(occupied),4096):
        ids=occupied[start:start+4096];Q=origin+ids*pitch
        inside=np.max(Q@eq[:,:3].T+eq[:,3],axis=1)<=.0048
        grid[tuple(ids[inside].T)]=False
    labels,count=ndi.label(grid);sizes=np.bincount(labels.ravel());sizes[0]=0
    keep=sizes>=max(120,sizes.max()*.003);grid=keep[labels]
    # Exposed voxel faces form a closed mesh; smoothing removes the grid steps.
    corners=[];quads=[];offset=0
    definitions=[(0,-1,[(0,0,0),(0,0,1),(0,1,1),(0,1,0)]),(0,1,[(1,0,0),(1,1,0),(1,1,1),(1,0,1)]),(1,-1,[(0,0,0),(1,0,0),(1,0,1),(0,0,1)]),(1,1,[(0,1,0),(0,1,1),(1,1,1),(1,1,0)]),(2,-1,[(0,0,0),(0,1,0),(1,1,0),(1,0,0)]),(2,1,[(0,0,1),(1,0,1),(1,1,1),(0,1,1)])]
    for axis,sign,face in definitions:
        neighbour=np.roll(grid,-sign,axis=axis);exposed=grid&~neighbour;ids=np.argwhere(exposed)
        C=ids[:,None,:]+np.array(face)[None,:,:];corners.append(C.reshape(-1,3));quads.append(np.arange(offset,offset+4*len(ids)).reshape(-1,4));offset+=4*len(ids)
    C=np.vstack(corners);U,inv=np.unique(C,axis=0,return_inverse=True);F=inv[np.vstack(quads)]
    Q=origin+(U-.5)*pitch
    np.savez_compressed(stage/'volume.npz',P=Q,F=F)
    (stage/'source.json').write_text(json.dumps({'source_sha256':sha(source),'pitch_mm':pitch*1000,'closing_radius_mm':11,'head_cavity_margin_mm':4.8,'head_cavity_includes_ears':True,'voxel_components':count,'occupied_voxels':int(grid.sum()),'surface_quads':len(F)},indent=2))
    print('CLOSED_WAVE_VOLUME',len(Q),len(F),flush=True)

def pack(source,stage,out):
    g,b,SP,ST,SD,names=source_data(source);head=headref.Head('female');surface=trimesh.Trimesh(SP,ST,process=False)
    w=glbwriter.GLB();w.g=copy.deepcopy(g);w.blob=bytearray(b);report={'source_sha256':sha(source),'lods':{}}
    for lod,mesh in enumerate(g['meshes']):
        d=np.load(stage/f'lod{lod}.npz');P=d['P'].astype(float);T=d['T'].astype(int)
        # VDB/decimation can leave coincident two-face slivers at a resolved
        # voxel pinch. They carry no visible area and are not hair clumps.
        area=np.linalg.norm(np.cross(P[T[:,1]]-P[T[:,0]],P[T[:,2]]-P[T[:,0]]),axis=1)*.5
        T=T[area>1e-12]
        edges=T[:,[0,1,1,2,2,0]].reshape(-1,2);graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(P),len(P))).tocsr();_,label=connected_components(graph,directed=False)
        groups=label[T[:,0]];counts=np.bincount(groups);T=T[counts[groups]>=24]
        used,inv=np.unique(T,return_inverse=True);P=P[used];T=inv.reshape(-1,3)
        P=assemble.push_out_var(head,P,np.full(len(P),.0028),iters=3)
        cp,dist,tri=trimesh.proximity.closest_point(surface,P)
        bc=headref.barycentric(cp,SP[ST[tri,0]],SP[ST[tri,1]],SP[ST[tri,2]])
        hp,hd,hti,hbc=head.closest(P);blend=1-assemble.smoothstep((hd-.004)/.025)
        delta={}
        for n in names:
            old=(SD[n][ST[tri]]*bc[:,:,None]).sum(1)
            if n.startswith('id_') and not n.startswith('id_ear_size'):
                own=(head.delta(n)[head.T[hti]]*hbc[:,:,None]).sum(1)
                old=old*(1-blend[:,None])+own*blend[:,None]
            delta[n]=old
        loose=assemble.smoothstep((1.685-P[:,1])/.16)*assemble.smoothstep((hd-.020)/.040)
        delta['hl_length_p']=np.c_[np.zeros(len(P)),-.055*loose,np.zeros(len(P))]
        delta['hl_length_n']=np.c_[np.zeros(len(P)),.034*loose,np.zeros(len(P))]
        radial=headref.unit(np.c_[P[:,0],np.zeros(len(P)),P[:,2]+.035]);stand=np.maximum(hd-.020,0)
        delta['hl_volume_p']=radial*stand[:,None]*.32;delta['hl_volume_n']=-radial*stand[:,None]*.22
        # Hair is rooted on the scalp, not the ear. Preserve that ownership
        # and reserve space where either ear-size endpoint approaches it.
        binding=assemble.Binding(head,P,P,T=T,no_ears=True,stretch=0)
        for n in names:
            if n.startswith('id_ear_size'):
                delta[n]=binding.delta(head.delta(n),margin=.0026)
        adjacency=assemble.adjacency(T,len(P))
        for _ in range(3):
            for mix in [{'hl_length_n':1,'hl_volume_n':1},{'hl_length_n':1},{'hl_volume_n':1},{'hl_length_p':1},{'hl_volume_p':1}]:
                move=sum((delta[n]*v for n,v in mix.items()),np.zeros_like(P));candidate=P+move
                safe=assemble.push_out_var(head,candidate,np.full(len(P),.0028),iters=3)
                correction=assemble.spread(safe-candidate,adjacency,iters=3)
                for n,v in mix.items():delta[n]+=correction*v/sum(x*x for x in mix.values())
        # At the ear/neck rim the nearest skin face can change when the ear
        # grows. Reserve clearance for that changed face, including grooming
        # and stacked identity endpoints, without moving the neutral coiffure.
        for _ in range(3):
            for suffix in ('_p','_n'):
                ear='id_ear_size'+suffix
                for identity in [{ear:1},{n:1 for n in names if n.startswith('id_') and n.endswith(suffix)}]:
                    Dh=sum((head.delta(n)*v for n,v in identity.items()),np.zeros_like(head.P))
                    for groom in [None,'hl_length_p','hl_length_n','hl_volume_p','hl_volume_n']:
                        mix=identity|({groom:1} if groom else {})
                        move=sum((delta[n]*v for n,v in mix.items()),np.zeros_like(P))
                        # Only this ear/neck transition needs the extra mixed
                        # correction; the full export is audited separately.
                        ids=np.flatnonzero((abs(P[:,0])>.05)&(P[:,1]>1.57)&(P[:,1]<1.68))
                        sd,_,normal,rim=head.signed(P[ids]+move[ids],D=Dh,with_rim=True)
                        bad=(sd<.0028)&~rim
                        correction=np.zeros_like(P)
                        correction[ids[bad]]=normal[bad]*(.0032-sd[bad])[:,None]
                        delta[ear]+=assemble.spread(correction,adjacency,iters=4)
        # New root positions follow the head locally; retain outer curl motion.
        # A periodic projection keeps both front and rear continuous without
        # crossing the reference atlas's nonmatching left/right image edges.
        theta=np.arctan2(P[:,0],P[:,2]+.035);u=.5+.24*np.sin(theta);v=np.clip((1.82-P[:,1])/.35,0,1)
        UV=np.c_[u,.756+.136*v]
        N=headref.vertex_normals(P,T)
        col=np.ones((len(P),4));col[:,0]=.50;col[:,1]=v;col[:,2]=.90
        original=mesh['primitives'][0];JA=rlglb.accessor(g,b,original['attributes']['JOINTS_0'])[0];WA=rlglb.accessor(g,b,original['attributes']['WEIGHTS_0'])[0]
        a=assemble.Writer('unused');a.g=w
        pr=a.primitive(P,N,UV,T,(col*255).astype('u1'),np.tile(JA,(len(P),1)).astype('u1'),np.tile(WA,(len(P),1)),original['material'],[(delta[n],None) for n in names])
        # Keep the original optional fine cards, but replace every torn core
        # surface and earlier open curtain with this closed body.
        cards=[];new_surface=trimesh.Trimesh(P,T,process=False)
        for card in mesh['primitives']:
            if g['materials'][card['material']]['name']!='rl_hair_card':continue
            ca={k:rlglb.accessor(g,b,v) for k,v in card['attributes'].items()};CT=rlglb.accessor(g,b,card['indices']).astype(int).reshape(-1,3);CD=[rlglb.accessor(g,b,t['POSITION']) for t in card['targets']]
            edges=CT[:,[0,1,1,2,2,0]].reshape(-1,2);graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(ca['POSITION']),len(ca['POSITION']))).tocsr();_,labels=connected_components(graph,directed=False)
            for group in np.unique(labels[CT]):
                ids=np.flatnonzero(labels==group);along=ca['COLOR_0'][ids,1];roots=ids[along<=along.min()+.05];root=ca['POSITION'][roots].mean(0)
                point,_,face=trimesh.proximity.closest_point(new_surface,root[None]);face=face[0];point=point[0]
                direction=headref.unit(root-head.C)
                hits,_,faces=new_surface.ray.intersects_location(head.C[None],direction[None],multiple_hits=True)
                if len(hits):
                    far=np.argmax(np.linalg.norm(hits-head.C,axis=1));point=hits[far];face=faces[far]
                weight=headref.barycentric(point[None],P[T[face,0]][None],P[T[face,1]][None],P[T[face,2]][None])[0]
                ca['POSITION'][ids]=point+.5*(ca['POSITION'][ids]-root)
                for i,n in enumerate(names):CD[i][ids]=(delta[n][T[face]]*weight[:,None]).sum(0)+.5*(CD[i][ids]-CD[i][roots].mean(0))
            cp=a.primitive(ca['POSITION'],headref.unit(ca['NORMAL']),ca['TEXCOORD_0'],CT,np.rint(ca['COLOR_0']*255).astype('u1'),ca['JOINTS_0'].astype('u1'),ca['WEIGHTS_0'],card['material'],[(d,None) for d in CD]);cards.append(cp)
        w.g['meshes'][lod]['primitives']=[pr]+cards
        faces=trimesh.Trimesh(P,T,process=False);report['lods'][str(lod)]={'core_triangles':len(T),'triangles':len(T)+sum(w.g['accessors'][p['indices']]['count']//3 for p in cards),'watertight':bool(faces.is_watertight),'body_count':int(faces.body_count)}
        assert faces.is_watertight and faces.body_count==1
        assert report['lods'][str(lod)]['triangles']<=[18000,7000,2500][lod]
    w.g['asset']['generator']='Rabbit Lands closed shoulder-wave volume repair'
    w.g['asset']['extras']['rlHair']['tris']={f'lod{k}':v['triangles'] for k,v in report['lods'].items()}
    out.parent.mkdir(parents=True,exist_ok=True);w.save(str(out));report.update(output_sha256=sha(out),tool_sha256=sha(__file__))
    out.with_suffix('.volume.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('step',choices=['prepare','pack']);ap.add_argument('--source',required=True,type=Path);ap.add_argument('--stage',required=True,type=Path);ap.add_argument('--out',type=Path);a=ap.parse_args()
    if a.step=='prepare':prepare(a.source,a.stage)
    else:
        assert a.out and a.source.resolve()!=a.out.resolve();pack(a.source,a.stage,a.out)
if __name__=='__main__':main()
