"""Prepare unregistered rounded, reference-guided Mohawk upper locks.

The qualified cap is copied exactly. This writes authoring candidates only:
a continuous basal mass, Native fitting and independent qualification follow.
No paid generation, runtime registration or upload is performed.
"""
from pathlib import Path
import argparse, copy, json, hashlib
import numpy as np
import trimesh
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter
import paths, rlglb, glbwriter, headref, hairgen, assemble
from build_short_reference import BoundedHead, closest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--profile',default=str(Path(__file__).parent/'styles/feathered_mohawk.json'))
    parser.add_argument('--sex',choices=['female','male'])
    args=parser.parse_args()
    root=Path(paths.WORKTREE)
    profile=json.loads(Path(args.profile).read_text());outdir=Path(args.output);assert not outdir.exists();outdir.mkdir(parents=True);guide=profile['guide_samples'];gz=np.array([r['z_m'] for r in guide]);gy=np.array([r['source_profile_y_m'] for r in guide]);gr=np.array([r['cap_root_y_m'] for r in guide]);rng=np.random.default_rng(int(profile.get("seed",23110)));definitions=[]
    for band,zs in [(0,np.linspace(.077,-.086,11)),(-1,np.linspace(.068,-.073,9)),(1,np.linspace(.063,-.080,9))]:
     for i,z in enumerate(zs):
      definitions.append({'band':band,'z':float(z+rng.uniform(-.002,.002)),'x':float(band*(.0075+rng.uniform(-.0012,.0012))+rng.uniform(-.0006,.0006)),'sweep':float(rng.uniform(.014,.037)),'width':float(rng.uniform(.014,.019) if band==0 else rng.uniform(.011,.015)),'roundness':float(rng.uniform(.79,1.02)),'tip_x':float(rng.uniform(-.006,.006)),'height_scale':float(rng.uniform(.85,1.20) if band==0 else rng.uniform(.60,1.00)),'phase':float(rng.random())})
    # Longitudinal fibres are generated in the lock's own continuous chart. No old
    # tuft/fin paint or geometry is reused; reference guides supply sweep/profile.
    size=1024;noise=gaussian_filter(rng.normal(size=(size,size)),(24,5),mode='wrap');noise/=max(float(noise.std()),1e-6);rgb=np.repeat(np.clip(173+noise*3,155,187).astype('u1')[:,:,None],3,axis=2);image=Image.fromarray(rgb);draw=ImageDraw.Draw(image)
    for i in range(56):
     x=(i+.5+rng.uniform(-.3,.3))*size/56;start=rng.uniform(-700,900);length=rng.uniform(300,1400);phase=rng.uniform(0,6.28);slope=rng.uniform(-.007,.007);points=[(float(x+np.sin(y/180+phase)*1.6+slope*(y-start)),float(y)) for y in np.linspace(start,start+length,25)];shade=int(rng.integers(96,145));draw.line(points,fill=(shade,)*3,width=int(rng.integers(2,5)))
     if i%4==0:draw.line([(x+2,y) for x,y in points],fill=(194,)*3,width=1)
    paint_name='feathered_mohawk_crest_round.png';image.convert('RGBA').save(outdir/paint_name)
    
    def curve(d,surface):
     origin=np.array([[d['x'],2.,d['z']]]);hits,ray,face=surface.ray.intersects_location(origin,np.array([[0.,-1.,0.]]),multiple_hits=True);rootp=hits[np.argmax(hits[:,1])] if len(hits) else closest(surface,np.array([[d['x'],1.8,d['z']]]))[0][0];cp,_,tri=closest(surface,rootp[None]);normal=headref.unit(np.asarray(surface.face_normals)[tri])[0];rootp=cp[0]-normal*.00005;tz=max(-.128,float(rootp[2])-d['sweep']);height=max(.018,float(np.interp(tz,gz,gy)-np.interp(float(rootp[2]),gz,gr)))*d['height_scale'];tip=rootp+np.array([d['tip_x'],height,tz-float(rootp[2])]);c1=rootp+normal*height*.40+np.array([0,0,-d['sweep']*.06]);c2=tip+np.array([-d['tip_x']*.15,-height*.06,d['sweep']*.26]);return np.array([rootp,c1,c2,tip])
    def sample(B,n):
     t=np.linspace(0,1,n) if np.isscalar(n) else np.asarray(n);return (1-t[:,None])**3*B[0]+3*(1-t[:,None])**2*t[:,None]*B[1]+3*(1-t[:,None])*t[:,None]**2*B[2]+t[:,None]**3*B[3]
    for sex in ([args.sex] if args.sex else ['female','male']):
     cap=root/f'godot-client/assets/actors/native/rl_heads/hair/buzz_cut_{sex}.glb';assert hashlib.sha256(cap.read_bytes()).hexdigest()==profile['qualified_caps'][sex],'Use the reviewed cap matching this guide profile';g,b=rlglb.read(str(cap));w=glbwriter.GLB();w.g=copy.deepcopy(g);w.blob=bytearray(b);texture_index=len(w.g['textures']);w.g['images'].append({'bufferView':w._view((outdir/paint_name).read_bytes()),'mimeType':'image/png'});tex=copy.deepcopy(w.g['textures'][0]);tex['source']=len(w.g['images'])-1;w.g['textures'].append(tex);material=copy.deepcopy(w.g['materials'][0]);material.update(name='rl_hair_clump_crest');material['pbrMetallicRoughness']['baseColorTexture']={'index':texture_index};material['extras'].update(texture=paint_name,referenceSurface=True,softHairline=True,softRootCoverage=True,uvStrandHighlights=False,paintFlatness=0);material_index=len(w.g['materials']);w.g['materials'].append(material);info=w.g['asset']['extras']['rlHair'];name='feathered_mohawk_'+sex;info['style']=name;info['materials']['rl_hair_clump_crest']=paint_name;receipts=[]
     for lod,mesh in enumerate(w.g['meshes']):
      source=g['meshes'][lod]['primitives'][0];A=rlglb.accessor(g,b,source['attributes']['POSITION']);AN=rlglb.accessor(g,b,source['attributes']['NORMAL']);AC=rlglb.accessor(g,b,source['attributes']['COLOR_0']);AT=rlglb.accessor(g,b,source['indices']).reshape(-1,3).astype(int);end=source['extras']['partVertexRanges']['reference'][1];faces=AT[(AT<end).all(1)&(AC[AT,0]>=.35).all(1)];faces=faces[np.einsum('ij,ij->i',AN[faces].mean(1),A[faces].mean(1)-BoundedHead(sex).C)>0];surface=trimesh.Trimesh(A,faces,process=False);positions=[];normals=[];uvs=[];colors=[];triangles=[];offset=0;segments,sides=[(10,10),(6,6),(5,4)][lod];rgen=np.random.default_rng(23111);main_curves=[];part_ranges=[]
      for d in definitions:
       B=curve(d,surface);t=np.r_[0.,.04,np.linspace(.18,1,segments-2)];C=sample(B,t);width=hairgen.width_profile(t,d['width'],root=.34,belly=.23,tip_start=.58,tip_pow=1.35);P,N,UV,T,along=hairgen.tube_mesh(C,np.array([0.,0.,1.]),width,width*d['roundness'],sides,inner_flat=1,u_rep=.78,uoff=d['phase'],tip_point=True,t_param=t);distance=along*np.linalg.norm(np.diff(C,axis=0),axis=1).sum();color=np.c_[hairgen.smoothstep(np.clip(distance/.0017,0,1)),along,np.full(len(P),.96),np.ones(len(P))];positions.append(P);normals.append(N);uvs.append(UV);colors.append(color);triangles.append(T+offset);part_ranges.append((offset,offset+len(P)));offset+=len(P);main_curves.append(B)
      fine,messy=[(29,20),(20,12),(8,0)][lod]
      for j in range(fine+messy):
       B=main_curves[j%len(main_curves)];B2=B.copy();base=sample(B,21);start=base[10 if j<fine else 12];tip=B[-1]+rgen.uniform(-1,1,3)*np.array([.004,.004,.003] if j<fine else [.006,.006,.005]);B2=np.array([start,start+(B[2]-start)*.5,tip+[0,-.001,.002],tip]);C=sample(B2,4 if lod==0 else 3);t=np.linspace(0,1,len(C));width=hairgen.width_profile(t,rgen.uniform(.0006,.0011) if j<fine else rgen.uniform(.0008,.0015),root=.6,belly=.2,tip_start=.2,tip_pow=1.2);P,N,UV,T,along=hairgen.tube_mesh(C,np.array([0.,0.,1.]),width,width*.8,4 if lod==0 else 3,inner_flat=1,u_rep=.55,uoff=float(rgen.random()));keep=float(rgen.uniform(.66,.91) if j<fine else rgen.uniform(.14,.4));color=np.c_[hairgen.smoothstep(along/.16),along*.5+.5,np.full(len(P),.96),np.full(len(P),keep)];positions.append(P);normals.append(N);uvs.append(UV);colors.append(color);triangles.append(T+offset);offset+=len(P)
      P=np.vstack(positions);N=np.vstack(normals);UV=np.vstack(uvs);C=np.vstack(colors);T=np.vstack(triangles);CP,_,tri=closest(surface,P);tv=faces[tri];bc=headref.barycentric(CP,A[tv[:,0]],A[tv[:,1]],A[tv[:,2]]);relative=P-CP;names=mesh['extras']['targetNames'];targets=[];_,weld=np.unique(np.round(P/1e-6),axis=0,return_inverse=True)
      for i,target_name in enumerate(names):
       old=rlglb.accessor(g,b,source['targets'][i]['POSITION']);D=(old[tv]*bc[:,:,None]).sum(1)
       if target_name=='hl_length_p':D+=relative*.50
       if target_name=='hl_length_n':D-=relative*.30
       if target_name in ['hl_volume_p','hl_volume_n']:
        amount=.42 if target_name.endswith('_p') else -.28;fade=hairgen.smoothstep(np.clip(np.linalg.norm(relative,axis=1)/.014,0,1));D[:,0]+=(P[:,0]*.7+relative[:,0]*.3)*amount*fade;D[:,2]+=relative[:,2]*amount*.15*fade
       targets.append({'POSITION':w.sparse_vec3(D,eps=0),'NORMAL':w.sparse_vec3(assemble.morph_normals(P,T,N,D,weld))})
      J=np.zeros((len(P),4),dtype='u1');W=np.zeros((len(P),4),dtype='f4');W[:,0]=1;attrs={key:w.accessor(value,kind,**kw) for key,value,kind,kw in [('POSITION',P,'VEC3',{'target':34962,'minmax':True}),('NORMAL',N,'VEC3',{'target':34962}),('TEXCOORD_0',UV,'VEC2',{'target':34962}),('COLOR_0',np.rint(np.clip(C,0,1)*255).astype('u1'),'VEC4',{'comp':5121,'target':34962,'normalized':True}),('JOINTS_0',J,'VEC4',{'comp':5121,'target':34962}),('WEIGHTS_0',W,'VEC4',{'target':34962})]};mesh['primitives'].append({'attributes':attrs,'indices':w.accessor(T.reshape(-1),'SCALAR',comp=5123,target=34963),'material':material_index,'targets':targets,'extras':{'partVertexRanges':{'reference':[0,len(P)]},'unqualifiedCrestPilot':True,'roundedGuideLocks':len(definitions)}});receipts.append({'lod':lod,'crest_triangles':len(T),'crest_vertices':len(P),'core_locks':len(definitions),'fine':fine,'messy':messy})
     info['tris']={f'lod{i}':sum(w.g['accessors'][p['indices']]['count']//3 for p in m['primitives']) for i,m in enumerate(w.g['meshes'])};info['source']={'qualifiedCapSHA256':hashlib.sha256(cap.read_bytes()).hexdigest(),'referenceSHA256':profile['reference_sha256'],'roundGuideLockPilot':True,'unqualified':True};out=outdir/(name+'.glb');w.save(str(out));h,blob=rlglb.read(str(out));assert blob[:len(b)]==b
     for i in range(3):assert h['meshes'][i]['primitives'][:2]==g['meshes'][i]['primitives'][:2]
     report={'qualified':False,'sex':sex,'method':'Round curved tapered guide locks derived from approved donor crest profile and backward flow; no old fin reuse','qualified_cap_primitives_all_51_targets_blob_prefix_exact':True,'material':'Continuous longitudinal close-fibre chart; cap texture remains exact','lods':receipts,'total_triangles':info['tris'],'source_sha256':hashlib.sha256(out.read_bytes()).hexdigest()};out.with_suffix('.pilot.json').write_text(json.dumps(report,indent=2));print('ROUND_LOCK_PILOT',report,flush=True)
    (outdir/'guide-definitions.json').write_text(json.dumps(definitions,indent=2))
    
    
    


if __name__ == "__main__":
    main()
