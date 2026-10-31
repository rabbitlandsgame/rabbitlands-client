"""Support a reference module's hidden RL cap without changing painted locks.

The input must be a High-only asset. Native fitting belongs in a subsequent,
separate corrective. Default support changes only cap POSITION/NORMAL rows.
Explicit profile rebuilding can also rebind cap identity deltas and root colour;
all painted-lock attributes and targets, indices, UVs and skin stay exact.
"""
import argparse,copy,json,shutil
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
import assemble,glbwriter,rlglb,hairgen,headref
from build_loose_reference import BoundedHead,sha,save_json,unit,profile,body_safe,body_hull,ref
from reference_root_edges import root_colours,geometric_boundary
from short_surface_guard import guard


def cap_body_clearance(head,P,equations,margin=.0035):
    """Clear the local torso horizontally, preserving the physical nape height."""
    Q=P.copy();divide=head.C[2]-.05
    direction=unit(np.c_[P[:,0]*.35,np.zeros(len(P)),P[:,2]-divide])
    distance=P@equations[:,:3].T+equations[:,3]
    inside=(distance.max(1)<margin-.00025)&(P[:,1]<head.eye_mid[1]-.055)
    slope=direction@equations[:,:3].T
    exits=np.where(slope>1e-6,np.maximum(margin-distance,0)/np.maximum(slope,1e-6),np.inf)
    amount=exits.min(1);assert np.isfinite(amount).all()
    Q[inside]+=direction[inside]*amount[inside,None]
    np.testing.assert_array_equal(Q[~inside],P[~inside]);np.testing.assert_array_equal(Q[:,1],P[:,1])
    return Q


def pin_nape_height(head,P,T,hairline):
    """Restore only low rear boundary rows to the declared physical nape height."""
    assert hairline.get('nape',True)
    ny=float(hairline.get('nape_y',head.P[head.vgroups['ears'],1].min()-hairline.get('nape_below_lobe_mm',20)*.001))
    border=geometric_boundary(P,T);lon,_=headref.dir_lonlat(P-head.C)
    selected=border[(abs(lon[border])>=135)&(P[border,1]>ny)&(P[border,1]<=ny+.025)]
    if not len(selected):return P,{'enabled':True,'nape_y':ny,'changed_vertices':0,'maximum_shift_mm':0.}
    distance,nearest=cKDTree(P[selected]).query(P);fade=1-hairgen.smoothstep(distance/.025)
    fade*=hairgen.smoothstep((abs(lon)-120)/15)
    shift=(P[selected[nearest],1]-ny)*fade;Q=P.copy();Q[:,1]-=shift
    assert (shift>=0).all() and shift.max()<=.025+1e-10
    np.testing.assert_array_equal(Q[shift==0],P[shift==0])
    return Q,{'enabled':True,'nape_y':ny,'selected_boundary_vertices':len(selected),'changed_vertices':int((shift>0).sum()),'maximum_shift_mm':float(shift.max()*1000),'outside_positions_exact':True}


def cap_edge_override(spec,value):
    """Apply an explicit bounded footprint change to a copied profile only."""
    if value is None:return spec
    assert spec is not None,'A cap edge override requires the original validated profile'
    values=np.asarray(value,float)
    assert np.isfinite(values).all(),'Cap edge override must be finite'
    if values.ndim==0:
        assert abs(float(values))<=8
        value=float(values)
    else:
        assert values.ndim==2 and values.shape[1]==2 and len(values)>=2
        assert values[0,0]==-180 and values[-1,0]==180 and (np.diff(values[:,0])>0).all()
        assert values[0,1]==values[-1,1] and (abs(values[:,1])<=8).all()
        value=values.tolist()
    result=copy.deepcopy(spec);result['shell']['edge_inset']=value
    return result


def repair(source,out,extra_controls=None,margin_mm=2.8,max_shift_mm=14,profile_path=None,pin_nape=False,edge_inset_override=None):
    source,out=Path(source),Path(out)
    assert source.name==out.name and source.resolve()!=out.resolve()
    assert not out.exists() and not out.with_suffix('.png').exists()
    assert 2<margin_mm<=4 and 0<max_shift_mm<=14
    g,b=rlglb.read(str(source));meta=g['asset']['extras']['rlHair']
    head=BoundedHead(meta['sex']);assert meta['headSHA256']==sha(head.glb_path)
    ids=head.id_names();combos=assemble.default_combos(ids)
    spec=profile(profile_path) if profile_path else None
    if spec:assert spec['name']==meta['style'] and sha(profile_path)==meta['source']['profile_sha256']
    spec=cap_edge_override(spec,edge_inset_override)
    if extra_controls:
        assert isinstance(extra_controls,dict)
        extra={}
        for key,value in extra_controls.items():
            value=float(value);name='id_'+key+('_p' if value>=0 else '_n')
            assert name in ids and np.isfinite(value) and abs(value)<=1
            if value:extra[name]=abs(value)
        combos['explicit_identity']=extra
    writer=glbwriter.GLB();writer.g=copy.deepcopy(g);writer.blob=bytearray(b);records=[]
    for lod,(before,mesh) in enumerate(zip(g['meshes'],writer.g['meshes'])):
        names=before.get('extras',{}).get('targetNames',[])
        assert 'hl_native_fit' not in names,'Repair the High baseline before authoring Native fitting'
        for old,pr in zip(before['primitives'],mesh['primitives']):
            ranges=old.get('extras',{}).get('partVertexRanges',{})
            if 'shell' not in ranges:continue
            s,e=ranges['shell'];P=rlglb.accessor(g,b,old['attributes']['POSITION']);N=rlglb.accessor(g,b,old['attributes']['NORMAL'])
            T=rlglb.accessor(g,b,old['indices'],normalize=False).astype(int).reshape(-1,3);capT=T[(T>=s).all(1)&(T<e).all(1)]-s
            assert len(capT) and e>s
            decoded=[{key:rlglb.accessor(g,b,index) for key,index in target.items()} for target in old['targets']]
            delta={name:target['POSITION'][s:e] for name,target in zip(names,decoded)}
            base=P[s:e].copy();normal=N[s:e].copy()
            nape={'enabled':False}
            if spec:
                scalp=hairgen.Scalp(head,spec.get('hairline'));rows,cols=spec['shell']['lod'][str(lod)]
                SP,SN,_,ST,_,_=hairgen.shell_mesh(scalp,spec['shell'],rows,cols)
                used,inverse=np.unique(ST,return_inverse=True)
                assert len(used)==e-s and np.array_equal(capT,inverse.reshape(-1,3)),'Profile cap topology differs from the authored module'
                base=SP[used]
                if pin_nape:base,nape=pin_nape_height(head,base,capT,spec.get('hairline',{}))
                base=assemble.push_out_var(head,base,np.full(e-s,.0032),iters=5)
                base=(cap_body_clearance if spec.get('preserve_curtain_depth',False) else body_safe)(head,base,body_hull(head),.0035)
                normal=SN[used];binding=head.bind(base,no_ears=True)
                assert set(names)==set(ids+['hl_length_p','hl_length_n','hl_volume_p','hl_volume_n'])
                delta={name:(head.bound_delta(binding,head.delta(name)) if name in ids else np.zeros_like(base)) for name in names}
            Q,proof=guard(head,base,capT,delta,ids,combos,margin=margin_mm/1000,max_shift_mm=max_shift_mm,max_iterations=10)
            D=Q-base;_,weld=np.unique(np.round(base/1e-6),axis=0,return_inverse=True)
            updated=P.copy();updated[s:e]=Q
            normals=N.copy();normals[s:e]=unit(normal+assemble.morph_normals(base,capT,normal,D,weld))
            for a,z in [(0,s),(e,len(P))]:
                np.testing.assert_array_equal(updated[a:z],P[a:z]);np.testing.assert_array_equal(normals[a:z],N[a:z])
            pr['attributes']['POSITION']=writer.accessor(updated,'VEC3',target=34962,minmax=True)
            pr['attributes']['NORMAL']=writer.accessor(normals,'VEC3',target=34962)
            if spec:
                colour=rlglb.accessor(g,b,old['attributes']['COLOR_0']);roots,_=ref.roots(head,scalp,Q)
                colour[s:e]=root_colours(head,scalp,Q,capT,colour[s:e],{'exterior':[0,0],'shell':[0,e-s],'detail':[e-s,e-s]},np.linalg.norm(Q-roots,axis=1),spec)
                pr['attributes']['COLOR_0']=writer.accessor(np.rint(np.clip(colour,0,1)*255).astype('u1'),'VEC4',5121,target=34962,normalized=True)
                pr['targets']=[]
                for name,target in zip(names,decoded):
                    target={key:value.copy() for key,value in target.items()};target['POSITION'][s:e]=delta[name]
                    if 'NORMAL' in target:target['NORMAL'][s:e]=assemble.morph_normals(Q,capT,normals[s:e],delta[name],weld)
                    pr['targets'].append({key:writer.sparse_vec3(value,eps=0) for key,value in target.items()})
            records.append({'mesh':mesh['name'],'cap_vertices':e-s,'rebuilt_from_profile_without_identity_envelope':bool(spec),'nape_boundary':nape,'total_cap_rebuild_shift_mm':float(np.linalg.norm(Q-P[s:e],axis=1).max()*1000),**proof})
    assert records
    writer.g['asset']['extras']['rlHair']['rlCapSupport']={'sourceSHA256':sha(source),'toolSHA256':sha(__file__),'method':'local RL cap support; painted exterior and existing shapes retained','edgeInsetOverride':edge_inset_override}
    out.parent.mkdir(parents=True,exist_ok=True);writer.save(str(out));shutil.copy2(source.with_suffix('.png'),out.with_suffix('.png'))
    result,blob=rlglb.read(str(out));assert blob[:len(b)]==b
    for a,m in zip(g['meshes'],result['meshes']):
        assert a.get('weights')==m.get('weights') and a.get('extras')==m.get('extras')
        for old,new in zip(a['primitives'],m['primitives']):
            assert old['indices']==new['indices'] and old.get('extras')==new.get('extras')
            if spec and 'shell' in old.get('extras',{}).get('partVertexRanges',{}):
                s,e=old['extras']['partVertexRanges']['shell']
                for old_target,new_target in zip(old['targets'],new['targets']):
                    for key,index in old_target.items():
                        old_array=rlglb.accessor(g,b,index);new_array=rlglb.accessor(result,blob,new_target[key])
                        np.testing.assert_array_equal(old_array[:s],new_array[:s]);np.testing.assert_array_equal(old_array[e:],new_array[e:])
            else:assert old.get('targets')==new.get('targets')
            for key,index in old['attributes'].items():
                if key not in ['POSITION','NORMAL'] and not (spec and key=='COLOR_0'):assert new['attributes'][key]==index
    report={'source_sha256':sha(source),'output_sha256':sha(out),'tool_sha256':sha(__file__),'records':records,'old_blob_prefix_exact':True,'all_indices_uv_skin_accessors_exact':True,'all_original_target_accessors_exact':not bool(spec),'painted_exterior_positions_normals_and_targets_exact':True,'profile_sha256':sha(profile_path) if profile_path else None,'edge_inset_override':edge_inset_override,'extra_controls':extra_controls or {},'qualified':False}
    save_json(out.with_suffix('.rl-cap-support.json'),report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--out',required=True);p.add_argument('--extra-controls');p.add_argument('--margin-mm',type=float,default=2.8);p.add_argument('--max-shift-mm',type=float,default=14);p.add_argument('--rebuild-from-profile');p.add_argument('--pin-profile-nape',action='store_true');p.add_argument('--cap-edge-inset-json',type=json.loads)
    a=p.parse_args();controls=json.loads(Path(a.extra_controls).read_text()) if a.extra_controls else None
    assert not a.pin_profile_nape or a.rebuild_from_profile
    report=repair(a.source,a.out,controls,a.margin_mm,a.max_shift_mm,a.rebuild_from_profile,a.pin_profile_nape,a.cap_edge_inset_json);print('RL_CAP_SUPPORTED',report['output_sha256'],flush=True)
