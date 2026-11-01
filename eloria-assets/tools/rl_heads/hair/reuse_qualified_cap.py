"""Reuse a qualified fixed cap without changing any visible recipient arrays.

Authoring only. Output belongs in an ignored stage. The returned High GLB keeps
the recipient target order; a sidecar NPZ holds the cap-only Native corrective
with zero exterior. Independent combined High/coverage/Native gates still apply.
"""
from pathlib import Path
import argparse,copy,hashlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np
from PIL import Image
import rlglb,glbwriter
from bake_reference_paint import pack_chart_islands,bake_chart_paint

GROOMS=('hl_length_p','hl_length_n','hl_volume_p','hl_volume_n')
ATTRIBUTES={'POSITION','NORMAL','TEXCOORD_0','COLOR_0','JOINTS_0','WEIGHTS_0'}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def _field(g,b,p,names,name,semantic,count):
    if name not in names:return np.zeros((count,3))
    target=p['targets'][names.index(name)]
    return rlglb.accessor(g,b,target[semantic]) if semantic in target else np.zeros((count,3))

def _rest(g):
    assert len(g['skins'])==1 and len(g['skins'][0]['joints'])==1,'Only rigid Head-bound caps are supported'
    return rlglb.globals_of(g)[g['skins'][0]['joints'][0]]

def _occupancy(g,b,width,height,range_name):
    occupied=np.zeros((height,width),bool)
    for mesh in g['meshes']:
        for p in mesh['primitives']:
            U=rlglb.accessor(g,b,p['attributes']['TEXCOORD_0']);T=rlglb.accessor(g,b,p['indices'],normalize=False).astype(int).reshape(-1,3)
            assert np.isfinite(U).all() and U.min()>=0 and U.max()<=1,'Unique atlas charts must be normalized'
            ranges=p.get('extras',{}).get('partVertexRanges',{})
            if range_name in ranges:
                a,z=ranges[range_name];T=T[~((T>=a).all(1)&(T<z).all(1))]
            for uv in U[T]:
                lo=np.floor(uv.min(0)*[width,height]-2).astype(int);hi=np.ceil(uv.max(0)*[width,height]+2).astype(int)
                x0,y0=np.maximum(lo,0);x1,y1=np.minimum(hi,[width-1,height-1]);occupied[y0:y1+1,x0:x1+1]=True
    return occupied

def _tile(occupied,size):
    height,width=occupied.shape;tw,th=size;assert tw>0 and th>0
    preferred=int(height*.75)
    rows=list(range(preferred,max(preferred,height-th)+1,16))+list(range(0,height-th+1,16))
    seen=set()
    for y in rows:
        if y in seen or y+th>height:continue
        seen.add(y)
        for x in range(0,width-tw+1,16):
            if not occupied[y:y+th,x:x+tw].any():
                occupied[y:y+th,x:x+tw]=True
                return x,y,tw,th
    raise AssertionError('No unused cap tile; preserve existing charts and provide a deliberately repacked atlas')

def reuse(source,qualified_cap,out,source_atlas=None,source_range='shell',cap_range='fixed_shell',tile_sizes=None):
    source,qualified_cap,out=map(Path,(source,qualified_cap,out));source_atlas=Path(source_atlas) if source_atlas else source.with_suffix('.png')
    assert source.resolve()!=out.resolve() and source.name==out.name and not out.exists()
    assert not out.with_suffix('.png').exists() and not out.with_suffix('.cap-native.npz').exists()
    g,b=rlglb.read(str(source));cg,cb=rlglb.read(str(qualified_cap));info=g['asset']['extras']['rlHair'];ci=cg['asset']['extras']['rlHair']
    assert info['headSHA256']==ci['headSHA256'] and info['sex']==ci['sex'],'Cap and recipient must use the same frozen head/sex'
    assert np.array_equal(_rest(g),_rest(cg)),'Cap and recipient rigid Head rest differ'
    assert len(g['meshes'])==len(cg['meshes']) and 1<=len(g['meshes'])<=3
    image=Image.open(source_atlas).convert('RGBA');original_image=np.asarray(image).copy();width,height=image.size
    assert all(not m.get('extras',{}).get('texture') or m['extras']['texture']==source_atlas.name for m in g['materials']),'This helper preserves a single shared recipient atlas'
    occupied=_occupancy(g,b,width,height,source_range)
    sizes=tile_sizes or [(512,256),(256,256),(256,256)];assert len(sizes)>=len(g['meshes'])
    writer=glbwriter.GLB();writer.g=copy.deepcopy(g);writer.blob=bytearray(b);reports=[];native_arrays={};tiles=[]
    for lod,(mesh,cm,dst_mesh) in enumerate(zip(g['meshes'],cg['meshes'],writer.g['meshes'])):
        names=mesh['extras']['targetNames'];cnames=cm['extras']['targetNames'];assert 'hl_native_fit' not in names,'Supply the High source before adding a combined corrective'
        assert set(GROOMS)<=set(names) and 'hl_native_fit' in cnames
        candidates=[(pi,p) for pi,p in enumerate(mesh['primitives']) if source_range in p.get('extras',{}).get('partVertexRanges',{})];assert len(candidates)==1
        cap_candidates=[p for p in cm['primitives'] if cap_range in p.get('extras',{}).get('partVertexRanges',{})];assert len(cap_candidates)==1
        pi,p=candidates[0];cap=cap_candidates[0];dst=dst_mesh['primitives'][pi];a,z=p['extras']['partVertexRanges'][source_range];ca,cz=cap['extras']['partVertexRanges'][cap_range]
        assert set(p['attributes'])==ATTRIBUTES and set(cap['attributes'])==ATTRIBUTES
        old={k:rlglb.accessor(g,b,v,normalize=k!='JOINTS_0') for k,v in p['attributes'].items()};new={k:rlglb.accessor(cg,cb,v,normalize=k!='JOINTS_0')[ca:cz] for k,v in cap['attributes'].items()}
        assert np.count_nonzero(new['JOINTS_0'])==0 and np.array_equal(new['WEIGHTS_0'],np.tile([1.,0,0,0],(cz-ca,1)))
        T=rlglb.accessor(g,b,p['indices'],normalize=False).astype(int).reshape(-1,3);CT=rlglb.accessor(cg,cb,cap['indices'],normalize=False).astype(int).reshape(-1,3);mask=(T>=a).all(1)&(T<z).all(1);capT=CT[(CT>=ca).all(1)&(CT<cz).all(1)]-ca
        assert mask.any() and len(capT);assert not (((T>=a)&(T<z)).any(1)&~mask).any(),'A face crosses the named cap boundary'
        for name in GROOMS:assert np.count_nonzero(_field(cg,cb,cap,cnames,name,'POSITION',len(rlglb.accessor(cg,cb,cap['attributes']['POSITION'])))[ca:cz])==0,'Qualified fixed cap has a nonzero groom'
        chart,chart_report=pack_chart_islands(new['TEXCOORD_0'],capT,padding=.05);tile=_tile(occupied,sizes[lod]);x,y,tw,th=tile;tiles.append(tile)
        paint,bake_report=bake_chart_paint(old['POSITION'][a:z],old['TEXCOORD_0'][a:z],T[mask]-a,new['POSITION'],chart,capT,original_image,size=(tw,th),force_opaque=True)
        assert np.array_equal(paint[:,:,3],np.full((th,tw),255,dtype='u1'));image.paste(Image.fromarray(paint),(x,y));new['TEXCOORD_0']=(chart*[tw,th]+[x,y])/[width,height]
        addition=(cz-ca)-(z-a)
        def join(values,replacement):return np.concatenate([values[:a],replacement,values[z:]])
        for key,values in old.items():
            values_out=join(values,new[key]);acc=g['accessors'][p['attributes'][key]];component=acc['componentType'];normalized=acc.get('normalized',False);encoded=np.rint(values_out*{5121:255,5123:65535}[component]) if normalized else values_out
            dst['attributes'][key]=writer.accessor(encoded,acc['type'],component,target=34962,minmax=key=='POSITION',normalized=normalized)
        outside=T[~mask].copy();outside[outside>=z]+=addition;newT=np.vstack([outside,capT+a]);dst['indices']=writer.accessor(newT.astype('u4').reshape(-1),'SCALAR',5125,target=34963)
        dst['targets']=[]
        for name,target in zip(names,p['targets']):
            assert name in cnames or name.startswith('hl_'),'Qualified cap lacks an identity field'
            result={}
            for semantic in set(target)|{'POSITION'}|set(cap['targets'][cnames.index(name)] if name in cnames else {}):
                values=_field(g,b,p,names,name,semantic,len(old['POSITION']));replacement=_field(cg,cb,cap,cnames,name,semantic,len(rlglb.accessor(cg,cb,cap['attributes']['POSITION'])))[ca:cz];result[semantic]=writer.sparse_vec3(join(values,replacement),eps=0)
            dst['targets'].append(result)
        for part,(start,end) in list(dst['extras']['partVertexRanges'].items()):
            if part==source_range:dst['extras']['partVertexRanges'][part]=[start,end+addition]
            elif start>=z:dst['extras']['partVertexRanges'][part]=[start+addition,end+addition]
            else:assert end<=a,'A non-cap range overlaps the cap'
        for semantic in ['POSITION','NORMAL']:
            values=np.zeros((len(old['POSITION'])+addition,3));values[a:a+cz-ca]=_field(cg,cb,cap,cnames,'hl_native_fit',semantic,len(rlglb.accessor(cg,cb,cap['attributes']['POSITION'])))[ca:cz];native_arrays[f'lod{lod}_{semantic}']=values.astype('f4')
        total=sum(g['accessors'][q['indices']]['count']//3 for q in mesh['primitives'])-int(mask.sum())+len(capT);assert total<=[18000,7000,2500][lod]
        reports.append({'lod':lod,'mesh':mesh['name'],'primitive':pi,'old_range':[a,z],'new_range':[a,a+cz-ca],'cap_triangles':len(capT),'total_triangles':total,'tile':tile,'chart':chart_report,'paint':bake_report,'zero_all_cap_grooms':True,'native_maximum_mm':float(np.linalg.norm(native_arrays[f'lod{lod}_POSITION'],axis=1).max()*1000)})
        writer.g['asset']['extras']['rlHair']['tris'][f'lod{lod}']=total
    out.parent.mkdir(parents=True,exist_ok=True);png=out.with_suffix('.png');image.save(png);view=writer._view(png.read_bytes())
    for entry in writer.g.get('images',[]):entry.update(bufferView=view,mimeType='image/png');entry.pop('uri',None)
    writer.g['asset']['extras']['rlHair']['fixedCapReuse']={'sourceSHA256':sha(source),'qualifiedCapSHA256':sha(qualified_cap),'toolSHA256':sha(__file__),'headAndRigidRestExact':True,'zeroCapGrooms':True,'method':'Qualified hidden cap geometry/fields, continuous recipient flow bake; visible recipient arrays unchanged'};writer.save(str(out));native_path=out.with_suffix('.cap-native.npz');np.savez_compressed(native_path,**native_arrays)
    gg,bb=rlglb.read(str(out));assert bb[:len(b)]==b;mask_pixels=np.zeros((height,width),bool)
    for x,y,tw,th in tiles:mask_pixels[y:y+th,x:x+tw]=True
    assert np.array_equal(np.asarray(image)[~mask_pixels],original_image[~mask_pixels])
    for row in reports:
        lod=row['lod'];pi=row['primitive'];before=g['meshes'][lod]['primitives'][pi];after=gg['meshes'][lod]['primitives'][pi];a,z=row['old_range'];na,nz=row['new_range']
        for key,at in before['attributes'].items():
            v=rlglb.accessor(g,b,at,normalize=key!='JOINTS_0');nv=rlglb.accessor(gg,bb,after['attributes'][key],normalize=key!='JOINTS_0');assert np.array_equal(v[:a],nv[:na]) and np.array_equal(v[z:],nv[nz:]),key
        for name in g['meshes'][lod]['extras']['targetNames']:
            for semantic in ['POSITION','NORMAL']:
                v=_field(g,b,before,g['meshes'][lod]['extras']['targetNames'],name,semantic,len(rlglb.accessor(g,b,before['attributes']['POSITION'])));nv=_field(gg,bb,after,gg['meshes'][lod]['extras']['targetNames'],name,semantic,len(rlglb.accessor(gg,bb,after['attributes']['POSITION'])));assert np.array_equal(v[:a],nv[:na]) and np.array_equal(v[z:],nv[nz:]),(name,semantic)
        assert g['meshes'][lod]['primitives'][:pi]==gg['meshes'][lod]['primitives'][:pi] and g['meshes'][lod]['primitives'][pi+1:]==gg['meshes'][lod]['primitives'][pi+1:]
    receipt={'source_sha256':sha(source),'qualified_cap_sha256':sha(qualified_cap),'output_sha256':sha(out),'atlas_sha256':sha(png),'cap_native_npz_sha256':sha(native_path),'head_sha256':info['headSHA256'],'head_and_rigid_rest_exact':True,'all_visible_attribute_and_target_prefix_suffix_values_exact':True,'all_other_primitives_exact':True,'all_non_tile_atlas_pixels_exact':True,'native_exterior_zero':True,'target_order_unchanged':True,'reports':reports,'qualified':False};out.with_suffix('.cap-reuse.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',required=True);ap.add_argument('--cap',required=True);ap.add_argument('--out',required=True);ap.add_argument('--atlas');args=ap.parse_args();print(json.dumps(reuse(args.source,args.cap,args.out,args.atlas),indent=2))
