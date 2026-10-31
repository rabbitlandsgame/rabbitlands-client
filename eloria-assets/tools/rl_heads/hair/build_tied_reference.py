"""Painted tied hair using the shared reference/backing export contract.

The exterior stays painted, the scalp cap stays fixed, and knot Length and
Volume change radial mass and axial depth independently. No provider calls.
"""
from pathlib import Path
import copy,json
from functools import partial
import numpy as np
import trimesh
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
import assemble,glbwriter,hairgen,headref,paths,reference_surface as ref,rlglb
import build_loose_reference as shared
from reference_layer_uv import split_corner_uv
from bake_reference_paint import pack_chart_islands,bake_chart_paint
from reference_temple_conform import conform_temples
from native_hair_clearance import NativeHeadSurface

GROOMS=shared.GROOMS
PROOFS=[]
NATIVE={}

def native_surface(head,spec):
    if not spec.get('native_head_clearance_mm'):return None
    if head.sex not in NATIVE:NATIVE[head.sex]=NativeHeadSurface.from_current_head(head)
    return NATIVE[head.sex]

def parts_builder(stage,head,scalp,spec,lod):
    P,N,UV,T,COL,ranges,info=shared.all_parts(stage,head,scalp,spec,lod)
    if spec.get('painted_backing',False):
        oldP,oldT=P,T;parts=[];offset=0;new_ranges={}
        for kind in ['exterior','backing','shell','detail']:
            if ranges[kind][0]==ranges[kind][1]:
                new_ranges[kind]=[offset,offset]
                continue
            start,end=ranges[kind];mask=(T>=start).all(1)&(T<end).all(1);tri=T[mask]-start
            points=P[start:end];normals=N[start:end];colors=COL[start:end];uv=UV[start:end]
            if kind=='backing':
                cache=np.load(stage/f'backing-chart-source-lod{lod}.npz')
                assert np.array_equal(cache['P'],points) and np.array_equal(cache['T'],tri),'Re-author the hidden chart after a geometry change'
                chart=np.load(stage/f'backing-chart-lod{lod}.npz')['corner_uv']
                points,tri,uv,attrs,proof=split_corner_uv(points,tri,chart,{'N':normals,'COL':colors})
                normals=attrs['N'];colors=attrs['COL'];info['backing_uv_only']=proof
                uv,info['backing_chart']=pack_chart_islands(uv,tri,padding=.05)
            elif kind=='shell':uv,info['shell_chart']=pack_chart_islands(uv,tri)
            parts.append((points,normals,uv,tri+offset,colors));new_ranges[kind]=[offset,offset+len(points)];offset+=len(points)
        P,N,UV,T,COL=(np.concatenate([part[index] for part in parts]) for index in range(5));ranges=new_ranges
        assert np.array_equal(oldP[oldT],P[T]),'UV authoring must preserve every triangle position'
        info['backing_paint']='Unique recipient chart; paint baked after final geometry authoring'
    P,N,info['temple_conformance']=conform_temples(head,scalp,P,N,T,ranges,spec)
    if spec.get('native_head_clearance_mm'):info['native_guard_order']='After RL rest seating; raw inset backing is not yet a fitted surface'
    return P,N,UV,T,COL,ranges,info

def bake_hidden_layers(writer,source_gltf,source_blob,source_atlas,out_atlas):
    source_image=np.asarray(Image.open(source_atlas).convert('RGBA'))
    image=Image.new('RGBA',(2048,2048),(160,160,160,255))
    image.paste(Image.fromarray(source_image[:768]).resize((2048,1536),Image.Resampling.LANCZOS),(0,0))
    image.paste(Image.fromarray(source_image[922:]).resize((2048,204),Image.Resampling.LANCZOS),(0,1844))
    records=[];x=0
    for lod,(old_mesh,mesh) in enumerate(zip(source_gltf['meshes'],writer.g['meshes'])):
        for old,primitive in zip(old_mesh['primitives'],mesh['primitives']):
            if source_gltf['materials'][old['material']]['name']!='rl_hair_clump':continue
            attrs=old['attributes'];P=rlglb.accessor(source_gltf,source_blob,attrs['POSITION']);UV=rlglb.accessor(source_gltf,source_blob,attrs['TEXCOORD_0']);T=rlglb.accessor(source_gltf,source_blob,old['indices'],normalize=False).astype(int).reshape(-1,3)
            updated=UV.copy();ranges=old['extras']['partVertexRanges'];e0,e1=ranges['exterior'];donor=T[(T>=e0).all(1)&(T<e1).all(1)]-e0
            for kind in ['backing','shell']:
                width=512 if lod==0 else 256
                if kind not in ranges:
                    x+=width
                    continue
                start,end=ranges[kind];tri=T[(T>=start).all(1)&(T<end).all(1)]-start
                chart,receipt=bake_chart_paint(P[e0:e1],UV[e0:e1],donor,P[start:end],UV[start:end],tri,source_image,size=(width,256),force_opaque=True)
                image.paste(Image.fromarray(chart),(x,1536))
                updated[start:end,0]=(x+UV[start:end,0]*width)/2048
                updated[start:end,1]=(1536+UV[start:end,1]*256)/2048
                records.append({'lod':lod,'layer':kind,'tile':[x,1536,width,256],**receipt});x+=width
            assert np.array_equal(updated[e0:e1],UV[e0:e1])
            primitive['attributes']['TEXCOORD_0']=writer.accessor(updated,'VEC2',target=34962)
    assert x==2048
    image.save(out_atlas);view=writer._view(out_atlas.read_bytes())
    for source in writer.g.get('images',[]):source.update(bufferView=view,mimeType='image/png');source.pop('uri',None)
    return records

def atlas_builder(stage,out,spec):
    spec=spec['paint']
    rgb=np.asarray(Image.open(stage/'hair-only.png').convert('RGB'),float)/255
    mask=np.asarray(Image.open(stage/'hair-mask.png'))>0
    linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
    luminance=linear@np.array([.2126,.7152,.0722]);sigma=spec['sigma_source_pixels']
    support=ndi.gaussian_filter(mask.astype(float),sigma)
    mean=ndi.gaussian_filter(luminance*mask,sigma)/np.maximum(support,1e-8)
    low,high=spec['luminance_bounds']
    neutral=np.clip(.35*(luminance/np.maximum(mean,1e-6))**spec['contrast_exponent'],low,high)
    distance,nearest=ndi.distance_transform_edt(~mask,return_indices=True)
    neutral=np.where(mask,neutral,np.where(distance<=128,neutral[tuple(nearest)],.35))
    srgb=np.where(neutral<=.0031308,neutral*12.92,1.055*neutral**(1/2.4)-.055)
    paint=Image.fromarray(np.repeat(np.clip(srgb[:,:,None]*255,0,255).astype('u1'),3,axis=2))
    atlas=Image.new('RGBA',(1024,1024),(160,160,160,255))
    atlas.paste(paint.convert('RGBA').resize((1024,768),Image.Resampling.LANCZOS),(0,0))
    atlas.paste(Image.open(Path(paths.HAIR_TEX)/'hair_clump.png').convert('RGBA').resize((1024,154)),(0,768))
    atlas.paste(Image.open(Path(paths.HAIR_TEX)/'hair_strands.png').convert('RGBA').resize((1024,102)),(0,922))
    atlas.save(out);return shared.sha(out)

def knot_field(P,Q,head,scalp,spec,kind,positive):
    config=spec['tied_mass']
    if config.get('kind')=='tail':return tail_field(P,Q,head,scalp,spec,kind,positive)
    if 'centers' in config:return multiple_knot_field(P,Q,head,scalp,spec,kind,positive)
    base,normal=scalp.point(*config['center'])
    axis=headref.unit(normal[0]);anchor=base[0]+axis*config['attachment_mm']*.001
    relative=P-anchor;axial=relative@axis;radial=relative-axial[:,None]*axis
    lon,lat=headref.dir_lonlat(P-head.C);a,b=config['rear_sector'];top,bottom=config['lower_latitude']
    near,far=np.asarray(spec['groom']['root_fade_mm'])*.001
    attached=hairgen.smoothstep((np.linalg.norm(P-Q,axis=1)-near)/(far-near))
    region=hairgen.smoothstep((abs(lon)-a)/(b-a))*hairgen.smoothstep((top-lat)/(top-bottom))
    r0,r1=np.asarray(config['root_ramp_mm'])*.001
    weight=attached*region*hairgen.smoothstep((axial-r0)/(r1-r0))
    amount=spec['groom'][kind+('_positive' if positive else '_negative')]*(1 if positive else -1)
    direction=radial if kind=='length' else np.maximum(axial,0)[:,None]*axis
    return direction*(weight*amount)[:,None]

def multiple_knot_field(P,Q,head,scalp,spec,kind,positive):
    config=spec['tied_mass'];near,far=np.asarray(spec['groom']['root_fade_mm'])*.001
    attached=hairgen.smoothstep((np.linalg.norm(P-Q,axis=1)-near)/(far-near))
    direction=headref.unit(P-head.C);move=np.zeros_like(P);total=np.zeros(len(P))
    radius=float(config['angular_radius_degrees']);feather=float(config['angular_feather_degrees']);assert 0<feather<radius<90
    amount=spec['groom'][kind+('_positive' if positive else '_negative')]*(1 if positive else -1)
    for center in config['centers']:
        base,normal=scalp.point(*center);axis=headref.unit(normal[0]);anchor=base[0]+axis*config['attachment_mm']*.001
        angle=np.degrees(np.arccos(np.clip(direction@headref.lonlat_dir(*center),-1,1)))
        angular=hairgen.smoothstep((radius+feather-angle)/(2*feather))
        relative=P-anchor;axial=relative@axis;radial=relative-axial[:,None]*axis
        r0,r1=np.asarray(config['root_ramp_mm'])*.001
        weight=attached*angular*hairgen.smoothstep((axial-r0)/(r1-r0));total+=weight
        field=radial if kind=='length' else np.maximum(axial,0)[:,None]*axis
        move+=field*(weight*amount)[:,None]
    return move/np.maximum(total,1)[:,None]

def tail_field(P,Q,head,scalp,spec,kind,positive):
    """Resize a whole hanging mass about a pinned attachment and smooth spine."""
    config=spec['tied_mass'];base,normal=scalp.point(*config['center']);anchor=base[0]+normal[0]*config['attachment_mm']*.001
    axis=headref.unit(np.asarray(config.get('direction',[0,-1,0]),float));relative=P-anchor;axial=relative@axis
    a,b=config['rear_sector'];lon,_=headref.dir_lonlat(P-head.C)
    near,far=np.asarray(spec['groom']['root_fade_mm'])*.001;r0,r1=np.asarray(config['root_ramp_mm'])*.001
    weight=hairgen.smoothstep((abs(lon)-a)/(b-a))*hairgen.smoothstep((axial-r0)/(r1-r0))
    weight*=hairgen.smoothstep((np.linalg.norm(P-Q,axis=1)-near)/(far-near))
    if kind=='length':field=axis*np.maximum(axial,0)[:,None]
    else:
        spine=np.asarray(config['spine'],float);assert spine.ndim==2 and spine.shape[1]==3 and (np.diff(spine[:,0])>0).all()
        centre=anchor+np.maximum(axial,0)[:,None]*axis
        centre[:,0]+=np.interp(axial,spine[:,0],spine[:,1]);centre[:,2]+=np.interp(axial,spine[:,0],spine[:,2])
        field=P-centre;field-=axis*(field@axis)[:,None]
    amount=spec['groom'][kind+('_positive' if positive else '_negative')]*(1 if positive else -1)
    return field*(weight*amount)[:,None]

def groom_builder(head,scalp,P,names,spec,hull,ranges):
    shell=slice(*ranges['shell']);before_cap=P[shell].copy()
    native=native_surface(head,spec);native_margin=float(spec.get('native_head_clearance_mm',2.8))/1000
    native_proofs=[]
    if native is not None:
        before=P.copy();P[:],proof=native.push_out(P,native_margin)
        proof['parts']={kind:{'changed_vertices':int((np.linalg.norm(P[start:end]-before[start:end],axis=1)>0).sum()),'max_shift_mm':float(np.linalg.norm(P[start:end]-before[start:end],axis=1).max()*1000) if end>start else 0.} for kind,(start,end) in ranges.items()}
        native_proofs.append({'stage':'after_shared_rest_guard',**proof})
    # Reuse the shared identity attachment contract without constructing and
    # then discarding the unrelated loose-curtain grooming shapes.
    Q,normal=ref.roots(head,scalp,P)
    binding=assemble.Binding(head,P,Q,follow=.015,fade=.025,stretch=.5,no_ears=True)
    # A close cap follows the skin directly. Clamping its root up to the
    # exterior hairline can leave its edge behind when the temples expand.
    cap_binding=head.bind(P[shell],no_ears=True)
    head_margin,body_margin=shared.layer_margins(P,ranges,spec);delta={}
    # Keep the same continuous torso exit through preparation and every
    # identity/groom guard; an unopted profile keeps the exact old calls.
    body_options={'radial':True} if spec.get('preserve_curtain_depth',False) else {}
    for name in names:
        Dh=head.delta(name);D=binding.delta(Dh,margin=.0028)
        D[shell]=head.bound_delta(cap_binding,Dh)
        mesh=trimesh.Trimesh(head.P+Dh,head.T,process=False);moving=np.linalg.norm(Dh,axis=1)>1e-5
        near=np.flatnonzero(np.isfinite(cKDTree(head.P[moving]).query(P,distance_upper_bound=np.linalg.norm(Dh,axis=1).max()+.04)[0])) if moving.any() else np.array([],int)
        for _ in range(5):
            if not len(near):break
            sd,cp,n,rim=head.signed(P[near]+D[near],D=Dh,mesh=mesh,with_rim=True)
            bad=(sd<head_margin[near])&~rim
            if not bad.any():break
            indices=near[bad];D[indices]=cp[bad]+n[bad]*(head_margin[indices]+.0006)[:,None]-P[indices]
        delta[name]=shared.body_safe(head,P+D,hull,body_margin,**body_options)-P
        print('TIED_ID_BOUND',len(PROOFS),name,flush=True)
    near=np.flatnonzero(binding.dist<.05)
    if len(near):
        P[near]=ref.joint_groom_clearance(head,P[near],{n:delta[n][near] for n in names},names,head_margin[near],combos=assemble.default_combos(names))
        P[:]=shared.body_safe(head,P,hull,body_margin,**body_options)
    Q,normal=ref.roots(head,scalp,P);distance=np.linalg.norm(P-Q,axis=1)
    cap=np.zeros(len(P),bool);cap[shell]=True;active=np.flatnonzero(~cap)
    d0,d1=ranges['detail'];segments=spec['details']['segments'][min(len(PROOFS),2)];stride=2*(segments+1)
    assert (d1-d0)%stride==0
    for name in GROOMS:
        kind='length' if 'length' in name else 'volume';positive=name.endswith('_p')
        move=knot_field(P,Q,head,scalp,spec,kind,positive)
        if kind=='volume':
            stand=np.maximum(np.einsum('ij,ij->i',P-Q,normal)-.0045,0)
            amount=.20 if positive else -.15
            move+=normal*(stand*amount)[:,None]
        # A whole detail strip follows the point it grows from. Its length
        # then varies about that root; no loose root drifts off the surface.
        for start in range(d0,d1,stride):
            ids=np.arange(start,min(start+stride,d1));root=ids[:2]
            centre=P[root].mean(0);source_root=Q[root].mean(0)
            translation=knot_field(centre[None],source_root[None],head,scalp,spec,kind,positive)[0]
            if kind=='volume':
                translation+=normal[root].mean(0)*max(float(np.einsum('ij,ij->i',P[root]-Q[root],normal[root]).mean())-.0045,0)*amount
            move[ids]=translation
            if kind=='length':move[ids]+=(P[ids]-centre)*(.35 if positive else -.25)
        move[cap]=0
        safe=P+move
        safe[active]=assemble.push_out_var(head,safe[active],head_margin[active],iters=5)
        safe[active]=ref.joint_groom_clearance(head,safe[active],{n:delta[n][active] for n in names},names,head_margin[active])
        safe[active]=shared.body_safe(head,safe[active],hull,body_margin[active],**body_options)
        if native is not None:safe[active],_=native.push_out(safe[active],native_margin)
        delta[name]=safe-P;delta[name][cap]=0
    for _ in range(5):
        largest=0.
        for length in GROOMS[:2]:
            for volume in GROOMS[2:]:
                position=P[active]+delta[length][active]+delta[volume][active]
                safe=ref.joint_groom_clearance(head,position,{n:delta[n][active] for n in names},names,head_margin[active])
                if native is not None:safe,_=native.push_out(safe,native_margin)
                correction=safe-position
                largest=max(largest,float(np.linalg.norm(correction,axis=1).max()))
                delta[volume][active]+=correction
        for volume in GROOMS[2:]:
            states=[P+delta[volume],P+delta[volume]+delta['hl_length_p'],P+delta[volume]+delta['hl_length_n']]
            correction=shared.shared_body_correction(head,P,states,hull,body_margin,**body_options)
            correction[cap]=0;largest=max(largest,float(np.linalg.norm(correction,axis=1).max()))
            delta[volume]+=correction
        if largest<1e-6:break
    _,weld=np.unique(np.round(P/1e-6),axis=0,return_inverse=True);counts=np.bincount(weld)
    for name in names+GROOMS:
        total=np.zeros((len(counts),3));np.add.at(total,weld,delta[name]);delta[name]=total[weld]/counts[weld,None]
    for name in GROOMS:
        delta[name][cap]=0
        assert not np.any(delta[name][cap])
    native_cases={}
    if native is not None:
        # Native identities use a different ten-field rest sculpture. Only
        # evaluated native fixtures with their exact mapped hair controls may
        # qualify them; arbitrary High-head identity stacks are not that gate.
        cases={'rest':{}}|{name:{name:1} for name in GROOMS}
        for length in GROOMS[:2]:
            for volume in GROOMS[2:]:cases[length+'+'+volume]={length:1,volume:1}
        for label,mix in cases.items():
            points=P+sum((delta[name]*weight for name,weight in mix.items()),np.zeros_like(P));signed,_,_=native.signed(points)
            native_cases[label]={'min_mm':float(signed.min()*1000),'violations':int((signed<.002).sum())}
    PROOFS.append({'cap_groom_max_mm':{n:float(np.linalg.norm(delta[n][cap],axis=1).max()*1000) for n in GROOMS},
        'cap_base_preflight_shift_max_mm':float(np.linalg.norm(P[cap]-before_cap,axis=1).max()*1000),
        'independent_knot_motion_mm':{n:float(np.linalg.norm(delta[n][:d0],axis=1).max()*1000) for n in GROOMS},
        'native_static_head_clearance':native_cases,'native_guard_receipts':native_proofs})
    return Q,distance,delta

def main():
    args=shared.parser().parse_args()
    if args.step=='prepare':shared.prepare(args);return
    if args.step=='backing':shared.backing(args);return
    assert args.step=='pack' and args.out
    out=Path(args.out);assert not out.exists();draft=out.with_name(out.stem+'.draft.glb')
    invocation=copy.copy(args);invocation.out=str(draft)
    report=shared.pack(invocation,groom_builder=groom_builder,atlas_builder=partial(atlas_builder,spec=shared.profile(args.profile)),parts_builder=parts_builder)
    g,b=rlglb.read(str(draft));writer=glbwriter.GLB();writer.g=copy.deepcopy(g);writer.blob=bytearray(b)
    baked=bake_hidden_layers(writer,g,b,draft.with_suffix('.png'),out.with_suffix('.png')) if shared.profile(args.profile).get('painted_backing',False) else []
    for material in writer.g['materials']:material.setdefault('extras',{})['texture']=out.with_suffix('.png').name
    writer.g['asset']['extras']['rlHair']['materials']={material['name']:out.with_suffix('.png').name for material in writer.g['materials']}
    groom=writer.g['asset']['extras']['rlHair']['grooming']
    mass=shared.profile(args.profile)['tied_mass']
    if mass.get('kind')=='tail':
        groom.update(lengthMeaning='Hanging-tail length about its pinned attachment and rooted loose-strand length.',volumeMeaning='Tail cross-section about its authored spine and swept-hair stand-off.')
    elif 'centers' in mass:
        groom.update(lengthMeaning='Each tied knot radial mass and rooted loose-strand length.',volumeMeaning='Each tied knot axial depth and swept-hair stand-off.')
    else:
        groom.update(lengthMeaning='Wrapped knot radial mass and rooted loose-strand length.',volumeMeaning='Knot axial depth and swept-hair stand-off.')
    groom['capGrooming']='Fixed for all four grooming shapes.'
    if shared.profile(args.profile).get('backing_mode')=='none':
        writer.g['asset']['extras']['rlHair']['source']['method']='Painted reference exterior with scalp coverage and rooted detail; no mass backing'
    writer.g['asset']['generator']='Rabbit Lands painted tied-hair builder'
    writer.save(str(out))
    if not baked:out.with_suffix('.png').write_bytes(draft.with_suffix('.png').read_bytes())
    report.update(output_sha256=shared.sha(out),bytes=out.stat().st_size,source_atlas_sha256=report['atlas_sha256'],atlas_sha256=shared.sha(out.with_suffix('.png')),tied_tool_sha256=shared.sha(__file__),tied_groom_proofs=PROOFS,continuous_hidden_paint_bakes=baked,qualified=False)
    shared.save_json(out.with_suffix('.report.json'),report)
    assert not any(case['violations'] for proof in PROOFS for case in proof.get('native_static_head_clearance',{}).values()),'Inspect saved native static-head contact report'
    print('PAINTED_TIED_HAIR_READY',str(out),report['output_sha256'],flush=True)

if __name__=='__main__':main()
