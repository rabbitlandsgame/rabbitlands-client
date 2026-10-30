"""Fit hair surfaces from an existing reference; never calls a generation service.

extract --fit fit.json --out <ignored-stage>
build --fit fit.json --source <stage> --profile style.json --out draft.glb [--detail donor.glb] [--check]
Run decimate_reference_surface.py in Blender between extract and build.
All source references, textures and intermediate NPZs stay in ignored storage.
"""
import argparse, hashlib, json, os, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE=Path(__file__).resolve().parent
TOOL_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
sys.path.insert(0,str(HERE.parent/'fit'))
from fitcommon import Sim
from refmesh import RefMesh,Cloud
from rlmodel import RLModel
import segment
import headref,hairgen,assemble,rlglb
from build_hair import secure_groom

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def extract(args):
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    fit=json.loads(Path(args.fit).read_text());ref=RefMesh(fit['reference'])
    if len(ref.parts)!=1:raise ValueError('Expected one material reference; explicit material selection required')
    model=RLModel(fit['sex'],n_surface=40000)
    t=fit['transform'];sim=Sim(t['scale'],t['R'],t['t'])
    bary=np.full((len(ref.F),3),1/3)
    X=(ref.V[ref.F]).mean(1);C=ref.colour(np.arange(len(ref.F)),bary)
    cloud=Cloud(X,ref.fn,C,np.arange(len(ref.F)),bary)
    values=np.array([fit['controls'].get(n,0) for n in model.names])
    surface=model.surface(model.morph(v=values))
    labels,_,_,info=segment.classify(cloud,sim(X),sim.rot(ref.fn),model,surface,final=True)
    is_beard=getattr(args,'kind','hair')=='beard'
    keep=labels==(segment.BEARD if is_beard else segment.HAIR)
    # Clothing and incidental islands are outside the hair's head zone.
    center=sim(X);keep &= (center[:,1]>model.C[1]-.34)
    # Colour segmentation can call painted eyebrows "hair" on an off-model
    # face. Retain scalp-connected surfaces, with a close rear-knot exception.
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree
    candidate=np.flatnonzero(keep);candidate_faces=ref.F[candidate]
    _,weld=np.unique(np.round(sim(ref.V)/1e-6),axis=0,return_inverse=True)
    edges=weld[candidate_faces][:,[0,1,1,2,2,0]].reshape(-1,2)
    graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(weld.max()+1,weld.max()+1)).tocsr()
    _,components=connected_components(graph,directed=False)
    groups=components[weld[candidate_faces[:,0]]]
    scalp_components=np.unique(groups[center[candidate,1]>model.h.eye_mid[1]+.045])
    good=np.ones(len(candidate),bool) if is_beard else np.isin(groups,scalp_components)
    seed_points=center[candidate[good]]
    if len(seed_points):
        distance=cKDTree(seed_points).query(center[candidate])[0]
        rear=(center[candidate,2]<model.C[2]-.035)&(center[candidate,1]>model.h.eye_mid[1]-.10)
        good |= rear&(distance<.025)
    keep[:]=False;keep[candidate[good]]=True
    faces=ref.F[keep];used,inv=np.unique(faces,return_inverse=True)
    P=sim(ref.V[used]);UV=ref.UV[used]
    if is_beard:
        head=headref.Head(fit['sex']);binding=assemble.Binding(head,P,P,follow=.015,fade=.025,stretch=0)
        delta=np.zeros_like(head.P)
        for name,value in fit['controls'].items():
            key='id_'+name+('_p' if value>=0 else '_n')
            if key in head.id_names():delta+=abs(value)*head.delta(key)
        P-=binding.delta(delta,keep_clear=False)
    assert len(faces)>(100 if is_beard else 1000) and np.isfinite(UV).all()
    np.savez_compressed(out/'extracted.npz',P=P,N=sim.rot(ref.VN[used]),UV=UV,T=inv.reshape(-1,3))
    texture=np.clip(ref.parts[0]['tex']*255,0,255).astype(np.uint8)
    im=Image.fromarray(texture[:,:,:3]);mask=Image.new('L',im.size);draw=ImageDraw.Draw(mask)
    for tri in ref.UV[faces]:draw.polygon([(float(u)*im.width,float(v)*im.height) for u,v in tri],fill=255)
    mask=mask.filter(ImageFilter.MaxFilter(9))
    mask.save(out/'hair-mask.png')
    isolated=Image.new('RGB',im.size,(30,30,30));isolated.paste(im,mask=mask);isolated.save(out/'hair-only.png')
    # Preserve only hair texels, never the source face/clothing atlas.
    receipt={'sex':fit['sex'],'kind':'beard' if is_beard else 'hair','fit_sha256':digest(args.fit),'reference_sha256':digest(fit['reference']),
             'hair_triangles':int(keep.sum()),'source_triangles':len(ref.F),'segmentation':info['counts'],
             'discarded_incidental_hair_triangles':int(len(candidate)-keep.sum()),
             'method':'Final fitted-head hair segmentation, scalp component cleanup; retain original positions/UVs/painted strand detail'}
    (out/'source.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt),flush=True)

def roots(head,scalp,P):
    lon,lat=headref.dir_lonlat(P-head.C)
    lat=np.maximum(lat,scalp.hairline(lon)+2)
    Q,N=scalp.point(lon,lat,0)
    return Q,N

def neutralize(head, P, fit,scalp):
    Q,_=roots(head,scalp,P)
    bind=assemble.Binding(head,P,Q,follow=.015,fade=.025,stretch=.5)
    D=np.zeros_like(head.P)
    for name,value in fit['controls'].items():
        key='id_'+name+('_p' if value>=0 else '_n')
        if key in head.id_names():D+=abs(value)*head.delta(key)
    return P-bind.delta(D,keep_clear=False)

def fine_cards(path,lod):
    if not path:return None
    g,b=rlglb.read(path)
    for mesh in g['meshes']:
        if mesh['name']!=f'hair_lod{lod}':continue
        for primitive in mesh['primitives']:
            if g['materials'][primitive['material']]['name']!='rl_hair_card':continue
            a=primitive['attributes']
            return {k:rlglb.accessor(g,b,a[v]) for k,v in [('P','POSITION'),('N','NORMAL'),('UV','TEXCOORD_0'),('COL','COLOR_0')]}|{'T':rlglb.accessor(g,b,primitive['indices']).astype(int).reshape(-1,3)}
    return None

def conform_front_hairline(head,scalp,P,N,spec):
    """Seat tight scalp braids above the target head's front hairline.

    A reconstruction's residual forehead shape can leave blunt braid ends
    hanging on the fitted forehead. Reparameterize only that front strip,
    preserving strand stand-off and rotating its smooth shading normals.
    """
    config=spec.get('conform_front_hairline')
    if not config:return P,N
    lon,lat=headref.dir_lonlat(P-head.C)
    line=scalp.hairline(lon)+float(config.get('margin_degrees',1))
    width=float(config.get('softness_degrees',2))
    target=line+width*np.logaddexp(0,(lat-line)/width)
    sector=float(config.get('sector_degrees',75))
    blend=hairgen.smoothstep((sector-np.abs(lon))/15)
    target=lat+(target-lat)*blend
    changed=(target-lat)>.01
    if not changed.any():return P,N
    old,old_normal=scalp.point(lon[changed],lat[changed])
    new,new_normal=scalp.point(lon[changed],target[changed])
    stand=np.maximum(((P[changed]-old)*old_normal).sum(1),.0032)
    P=P.copy();P[changed]=new+new_normal*stand[:,None]
    axis=np.cross(old_normal,new_normal)
    angle=np.arctan2(np.linalg.norm(axis,axis=1),(old_normal*new_normal).sum(1))
    N=N.copy();N[changed]=hairgen.rotate(N[changed],axis,angle)
    return P,N

def joint_groom_clearance(head,P,target_d,names,margin,combos=None):
    """Only push outward until rest and both identity envelopes agree.

    Sequential closest-normal projections can pull a tuft back into the rest
    ear while clearing a different ear shape. A shared radial correction has
    one direction for every envelope and cannot undo the previous clearance.
    """
    states=[(np.zeros_like(head.P),np.zeros_like(P))]
    for suffix in ('_p','_n'):
        selected=[n for n in names if n.endswith(suffix)]
        states.append((sum(head.delta(n) for n in selected),sum(target_d[n] for n in selected)))
    for weights in (combos or {}).values():
        states.append((sum(head.delta(n)*w for n,w in weights.items()),sum(target_d[n]*w for n,w in weights.items())))
    meshes=[assemble.trimesh.Trimesh(head.P+D,head.T,process=False) for D,_ in states]
    result=P.copy();radial=headref.unit(result-head.C)
    for _ in range(16):
        step=np.zeros(len(P))
        for (D,V),mesh in zip(states,meshes):
            sd,_,normal,rim=head.signed(result+V,D=D,mesh=mesh,with_rim=True)
            bad=(sd<margin)&~rim
            amount=np.maximum(margin+.0003-sd,0)/np.maximum(np.abs((normal*radial).sum(1)),.3)
            step=np.maximum(step,np.where(bad,np.minimum(amount,.008),0))
        if not (step>0).any():break
        result+=radial*step[:,None]
    return result

def build(args):
    src=Path(args.source);out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    spec=json.loads(Path(args.profile).read_text());receipt=json.loads((src/'source.json').read_text())
    if (src/'topology-repair.json').exists():receipt['topology_repair']=json.loads((src/'topology-repair.json').read_text())
    head=headref.Head(receipt['sex']);scalp=hairgen.Scalp(head,spec.get('hairline'))
    fit=json.loads(Path(args.fit).read_text())
    names=head.id_names();grooms=['hl_length_p','hl_length_n','hl_volume_p','hl_volume_n']
    groom_clear=float(spec.get('groom_clearance_mm',3.2))/1000
    groom_safe=max(.0028,groom_clear-.0004)
    # These are dyeable, lighting-free hair textures. The reference's dark or
    # silver pigment must not multiply the chosen hair colour a second time.
    # Normalize local luminance to the existing clump atlas's linear range,
    # retaining painted strand contrast and leaving unused texels neutral.
    from scipy.ndimage import gaussian_filter
    source_rgb=np.asarray(Image.open(src/'hair-only.png').convert('RGB'),float)/255
    linear=np.where(source_rgb<=.04045,source_rgb/12.92,((source_rgb+.055)/1.055)**2.4)
    luminance=linear@np.array([.2126,.7152,.0722]);blur=gaussian_filter(luminance,6)
    normalized=np.clip(.35*(luminance/np.maximum(blur,1e-4))**.55,.13,.75)
    mask_path=src/'hair-mask.png'
    mask=np.asarray(Image.open(mask_path))>0 if mask_path.exists() else np.any(np.asarray(Image.open(src/'hair-only.png'))!=30,axis=2)
    normalized[~mask]=.35
    normalized=np.where(normalized<=.0031308,normalized*12.92,1.055*normalized**(1/2.4)-.055)
    normalized_image=Image.fromarray(np.repeat(np.clip(normalized[:,:,None]*255,0,255).astype('u1'),3,axis=2))
    atlas=Image.new('RGBA',(1024,1024),(160,160,160,255));atlas.paste(normalized_image.convert('RGBA').resize((1024,768),Image.Resampling.LANCZOS),(0,0))
    import paths
    atlas.paste(Image.open(Path(paths.HAIR_TEX)/'hair_clump.png').convert('RGB').resize((1024,154)),(0,768))
    atlas.paste(Image.open(Path(paths.HAIR_TEX)/'hair_strands.png').convert('RGBA').resize((1024,102)),(0,922))
    atlas_path=out.with_suffix('.png');atlas.save(atlas_path)
    writer=assemble.Writer('Rabbit Lands fitted reference hair surface')
    mat=writer.material('rl_hair_clump',[1,1,1,1],extras={'texture':atlas_path.name,'uv':'reference atlas plus covered under-shell','softHairline':bool(spec.get('soft_hairline_mm'))})
    writer.embed_texture(mat,str(atlas_path))
    card_mat=writer.material('rl_hair_card',[1,1,1,1],cutoff=.35,extras={'texture':atlas_path.name,'uv':'fine-strand strip in the shared atlas'})
    writer.embed_texture(card_mat,str(atlas_path))
    report={'style':spec['name'],'sex':receipt['sex'],'source':receipt,'tool_sha256':TOOL_SHA256,'profile_sha256':digest(args.profile),'detail_sha256':digest(args.detail) if args.detail else None,'lods':{},'clearance':{},'grooming':'Per-vertex scalp roots, length along root-to-tip; volume along scalp normals. Braids/buns keep their authored length.'}
    meshes=[]
    for lod in (0,1,2):
        a=np.load(src/f'lod{lod}.npz');P=a['P'];N=a['N'];UV=a['UV'].copy();T=a['T']
        # Keep the source's smooth shading after reduction, instead of making
        # every reduced curl cluster read as a new faceted sculpture.
        from scipy.spatial import cKDTree
        high=np.load(src/'extracted.npz');distance,nearest=cKDTree(high['P']).query(P,k=3)
        samples=high['N'][nearest];weight=1/np.maximum(distance,1e-5)
        weight*=np.maximum((samples*N[:,None,:]).sum(2),0)**2
        smooth=(samples*weight[:,:,None]).sum(1);length=np.linalg.norm(smooth,axis=1)
        use=length>1e-8;N=N.copy();N[use]=smooth[use]/length[use,None]
        lengths=np.linalg.norm(N,axis=1);bad=lengths<.5
        N[bad]=headref.unit(P[bad]-head.C);N=headref.unit(N)
        P=neutralize(head,P,fit,scalp)
        P,N=conform_front_hairline(head,scalp,P,N,spec)
        P=head.push_out(P,.0032,iters=4)
        UV[:,1]*=.75
        ref_n=len(P)
        fine=fine_cards(args.detail,lod)
        if fine is not None and spec['name']=='rounded_afro':
            # Donor flyaways must grow from the reference's mass, rather than
            # remaining suspended around the smaller procedural donor cap.
            ftree=cKDTree(P)
            from scipy.sparse import coo_matrix
            from scipy.sparse.csgraph import connected_components
            edges=fine['T'][:,[0,1,1,2,2,0]].reshape(-1,2)
            graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(fine['P']),len(fine['P']))).tocsr()
            _,labels=connected_components(graph,directed=False)
            for group in np.unique(labels):
                ids=np.flatnonzero(labels==group)
                g=fine['COL'][ids,1];root=fine['P'][ids[g<=g.min()+.05]].mean(0)
                distance,nearest=ftree.query(root)
                fine['P'][ids]=P[nearest]+.12*(fine['P'][ids]-root)
        if fine is not None:
            fine_uv=fine['UV'].copy();fine_uv[:,1]=.901+.098*fine_uv[:,1]
            T=np.vstack([T,fine['T']+len(P)]);P=np.vstack([P,fine['P']]);N=np.vstack([N,fine['N']]);UV=np.vstack([UV,fine_uv])
        shell_start=len(P)
        rows,cols=spec['shell']['lod'][str(lod)]
        shell_spec=dict(spec['shell'],offset_mm=[4.0,3.2],tip_band=0.,edge_inset=1.5)
        S,SN,SU,ST,_,_=hairgen.shell_mesh(scalp,shell_spec,rows,cols)
        SU[:,0]%=1.0;SU[:,1]=.75+.14*SU[:,1]
        P=np.vstack([P,S]);N=np.vstack([N,SN]);UV=np.vstack([UV,SU]);T=np.vstack([T,ST+shell_start])
        P=assemble.push_out_var(head,P,.003+assemble.headroom(head,P,names,frac=.5),iters=6)
        Q,root_norm=roots(head,scalp,P)
        binding=assemble.Binding(head,P,Q,follow=.015,fade=.025,stretch=.5,T=T)
        target_d={}
        for name in names:
            Dh=head.delta(name);D=binding.delta(Dh,margin=.0028)
            # Ear growth can overtake an adjacent tuft from the side; the
            # scalp-bound normal alone cannot push that tuft out of the ear.
            mesh=assemble.trimesh.Trimesh(head.P+Dh,head.T,process=False)
            for _ in range(5):
                sd,cp,n,rim=head.signed(P+D,D=Dh,mesh=mesh,with_rim=True)
                bad=(sd<.0028)&~rim
                if not bad.any():break
                D[bad]=cp[bad]+n[bad]*.0032-P[bad]
            target_d[name]=D
        # Pin shell duplicates to the same shape deltas so sector seams stay shut.
        shell_idx=np.arange(shell_start,len(P));_,weld=np.unique(np.round(P[shell_idx]/1e-6),axis=0,return_inverse=True)
        def seam_fix(D):
            accum=np.zeros((weld.max()+1,3));np.add.at(accum,weld,D[shell_idx]);count=np.bincount(weld)
            D[shell_idx]=accum[weld]/count[weld,None];return D
        for name in names:target_d[name]=seam_fix(target_d[name])
        delta=P-Q;stand=np.maximum((delta*root_norm).sum(1)-.0045,0)
        length_scale=np.clip(np.linalg.norm(delta,axis=1)/.10,0,1)
        is_fixed=spec['name'] in ('cornrows_low_knot','curly_twin_buns')
        for name,factor in [('hl_length_p',.6),('hl_length_n',-.4),('hl_volume_p',.8),('hl_volume_n',-.5)]:
            move=delta*length_scale[:,None]*factor if 'length' in name else root_norm*stand[:,None]*factor
            if 'length' in name and is_fixed:move[:ref_n]*=0
            move[shell_start:]=0
            Pm=assemble.push_out_var(head,P+move,np.full(len(P),groom_clear),iters=5)
            Pm=secure_groom(head,Pm,target_d,names,groom_safe,iters=4)
            if spec.get('joint_groom_clearance'):Pm=joint_groom_clearance(head,Pm,target_d,names,groom_safe)
            target_d[name]=seam_fix(Pm-P)
        # The two shortening operations share the same clearance allowance.
        # Reserve it under their combination, rather than spending it twice.
        pair=P+target_d['hl_length_n']+target_d['hl_volume_n']
        safe=assemble.push_out_var(head,pair,np.full(len(P),groom_clear),iters=5)
        safe=secure_groom(head,safe,target_d,names,groom_safe,iters=4)
        if spec.get('joint_groom_clearance'):safe=joint_groom_clearance(head,safe,target_d,names,groom_safe)
        target_d['hl_volume_n']=seam_fix(target_d['hl_volume_n']+safe-pair)
        if spec.get('joint_groom_clearance'):
            # The shared minimum-groom correction must not spend clearance
            # from the volume-only endpoint (especially beside the ear).
            safe=joint_groom_clearance(head,P+target_d['hl_volume_n'],target_d,names,groom_safe)
            target_d['hl_volume_n']=seam_fix(safe-P)
        colour=np.zeros((len(P),4),np.uint8);colour[:,0]=128;colour[:,1]=np.clip(length_scale*255,0,255).astype(np.uint8);colour[:,2]=230;colour[:,3]=255
        if spec.get('soft_hairline_mm'):
            edge=np.sort(T[(T<ref_n).all(1)][:,[0,1,1,2,2,0]].reshape(-1,2),axis=1)
            edge,count=np.unique(edge,axis=0,return_counts=True)
            lon,lat=headref.dir_lonlat(P[:ref_n]-head.C)
            eligible=(np.abs(lon)<80)&(lat<scalp.hairline(lon)+8)
            ids=np.unique(edge[count==1]);ids=ids[eligible[ids]]
            colour[:ref_n,0]=255
            if len(ids):
                dist=cKDTree(P[ids]).query(P[:ref_n])[0]
                colour[np.flatnonzero(eligible),0]=np.clip(dist[eligible]/.002*255,0,255).astype(np.uint8)
            colour[shell_start:,0]=255
        if fine is not None:colour[ref_n:shell_start]=np.clip(fine['COL']*255,0,255).astype(np.uint8)
        joints=np.zeros((len(P),4),np.uint8);weights=np.zeros((len(P),4),np.float32);weights[:,0]=1
        primitives=[]
        is_card=(T>=ref_n).all(1)&(T<shell_start).all(1)
        for mask,material in [(~is_card,mat),(is_card,card_mat)]:
            if not mask.any():continue
            used,inverse=np.unique(T[mask],return_inverse=True)
            primitives.append(writer.primitive(P[used].astype('f4'),N[used].astype('f4'),UV[used].astype('f4'),inverse.reshape(-1,3),colour[used],joints[used],weights[used],material,[(target_d[n][used],None) for n in names+grooms]))
        meshes.append(writer.mesh(f'hair_lod{lod}',primitives,names+grooms))
        report['lods'][f'lod{lod}']={'tris':len(T),'verts':len(P)}
        if args.check:
            combos=assemble.default_combos(names)
            for groom in grooms:
                for suffix in ('_p','_n'):combos[groom+'+all_id'+suffix]={n:1 for n in names if n.endswith(suffix)}|{groom:1}
            combos['groom_min']={'hl_length_n':1,'hl_volume_n':1}
            head_d={n:head.delta(n) for n in names}|{n:np.zeros_like(head.P) for n in grooms}
            report['clearance'][f'lod{lod}']=assemble.clearance(head,P,head_d,target_d,names+grooms,combos=combos)
        print(spec['name'],lod,report['lods'][f'lod{lod}'],flush=True)
    g=writer.g;node=g.node(name='hair_root',**rlglb.trs_from_matrix(head.head_G));g.g['scenes'][0]['nodes'].append(node)
    ibm=g.accessor(np.stack([rlglb.mat4_to_gltf(np.linalg.inv(head.head_G))]),'MAT4')
    g.g['skins']=[{'joints':[node],'inverseBindMatrices':ibm,'skeleton':node,'name':'RLHairSkin'}]
    for lod,mesh in enumerate(meshes):g.g['scenes'][0]['nodes'].append(g.node(name=f'hair_lod{lod}',mesh=mesh,skin=0))
    g.g['asset']['extras']={'rlHair':{'version':1,'style':spec['name'],'sex':receipt['sex'],'headSHA256':assemble.file_sha(head.glb_path),'springs':[],'collisions':[],'tris':{k:v['tris'] for k,v in report['lods'].items()},'grooming':{'shapes':grooms,'lengthRange':[-.4,.6],'volumeRange':[-.5,.8]},'source':receipt,'materials':{'rl_hair_clump':atlas_path.name}}}
    report['bytes']=writer.save(str(out));report['withinBudget']=all(report['lods'][f'lod{i}']['tris']<=limit for i,limit in enumerate([18000,7000,2500]))
    out.with_suffix('.report.json').write_text(json.dumps(report,indent=2));print('SAVED',out,report['withinBudget'],flush=True)
    # Keep failed geometry and its report for inspection, but never let a
    # checked build silently advance through an automated delivery pipeline.
    if not report['withinBudget']:
        raise SystemExit('Hair exceeds an LOD triangle budget; inspect the saved report')
    if args.check and any(c['rest']['violations'] or c['morphs']['violatingCases'] for c in report['clearance'].values()):
        raise SystemExit('Hair clearance failed; inspect the saved report')

def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('extract');p.add_argument('--fit',required=True);p.add_argument('--out',required=True);p.add_argument('--kind',choices=['hair','beard'],default='hair')
    p=sub.add_parser('build');p.add_argument('--fit',required=True);p.add_argument('--source',required=True);p.add_argument('--profile',required=True);p.add_argument('--out',required=True);p.add_argument('--detail');p.add_argument('--check',action='store_true')
    args=ap.parse_args();{'extract':extract,'build':build}[args.cmd](args)
if __name__=='__main__':main()
