"""Bake a reference hair cap's continuous paint without changing mesh geometry.

Input and output are separate local files. Original exterior UVs, every position,
normal, index, colour, skin and morph accessor remain unchanged. Only the cap UV
accessor and embedded/external atlas are replaced. No external service is used.
"""
import argparse,copy
from pathlib import Path
import numpy as np
from PIL import Image
import glbwriter,rlglb
from bake_reference_paint import pack_chart_islands,bake_chart_paint
from build_loose_reference import sha,save_json


def bake(source,out):
    source=Path(source);out=Path(out)
    assert source.name==out.name and source.resolve()!=out.resolve()
    assert not out.exists() and not out.with_suffix('.png').exists()
    out.parent.mkdir(parents=True,exist_ok=True)
    original_g,blob=rlglb.read(str(source));writer=glbwriter.GLB()
    assert len(original_g.get('images',[]))==1,'Expected a single shared hair atlas'
    writer.g=copy.deepcopy(original_g);writer.blob=bytearray(blob)
    old_image=np.asarray(Image.open(source.with_suffix('.png')).convert('RGBA'))
    assert old_image.shape==(1024,1024,4),'Expected the shared reference atlas'
    image=Image.new('RGBA',(2048,2048),(160,160,160,255))
    image.paste(Image.fromarray(old_image[:768]).resize((2048,1536),Image.Resampling.LANCZOS),(0,0))
    image.paste(Image.fromarray(old_image[922:]).resize((2048,204),Image.Resampling.LANCZOS),(0,1844))
    records=[];tile_x=0
    for lod,(old_mesh,mesh) in enumerate(zip(original_g['meshes'],writer.g['meshes'])):
        for old,primitive in zip(old_mesh['primitives'],mesh['primitives']):
            if original_g['materials'][old['material']]['name']!='rl_hair_clump':continue
            ranges=old['extras']['partVertexRanges'];e0,e1=ranges['exterior'];s0,s1=ranges['shell']
            assert s1>s0 and e1>e0
            P=rlglb.accessor(original_g,blob,old['attributes']['POSITION'])
            UV=rlglb.accessor(original_g,blob,old['attributes']['TEXCOORD_0'])
            T=rlglb.accessor(original_g,blob,old['indices'],normalize=False).astype(int).reshape(-1,3)
            donor=T[(T>=e0).all(1)&(T<e1).all(1)]-e0
            cap=T[(T>=s0).all(1)&(T<s1).all(1)]-s0
            chart,chart_proof=pack_chart_islands(UV[s0:s1],cap)
            width=512 if lod==0 else 256
            paint,proof=bake_chart_paint(P[e0:e1],UV[e0:e1],donor,P[s0:s1],chart,cap,old_image,size=(width,256),force_opaque=True)
            image.paste(Image.fromarray(paint),(tile_x,1536))
            updated=UV.copy();updated[s0:s1,0]=(tile_x+chart[:,0]*width)/2048
            updated[s0:s1,1]=(1536+chart[:,1]*256)/2048
            np.testing.assert_array_equal(updated[:s0],UV[:s0]);np.testing.assert_array_equal(updated[s1:],UV[s1:])
            primitive['attributes']['TEXCOORD_0']=writer.accessor(updated,'VEC2',target=34962)
            records.append({'lod':lod,'tile':[tile_x,1536,width,256],'recipient_chart':chart_proof,**proof});tile_x+=width
    assert tile_x==1024 and len(records)==3
    image.save(out.with_suffix('.png'));view=writer._view(out.with_suffix('.png').read_bytes())
    for entry in writer.g.get('images',[]):entry.update(bufferView=view,mimeType='image/png');entry.pop('uri',None)
    for material in writer.g['materials']:material.setdefault('extras',{})['texture']=out.with_suffix('.png').name
    writer.g['asset']['extras']['rlHair']['materials']={m['name']:out.with_suffix('.png').name for m in writer.g['materials']}
    writer.save(str(out))
    # Compare all original non-UV primitive accessors after the rewrite.
    result_g,result_b=rlglb.read(str(out))
    for before,after in zip(original_g['meshes'],result_g['meshes']):
        for a,b in zip(before['primitives'],after['primitives']):
            for key,index in a['attributes'].items():
                if key=='TEXCOORD_0':continue
                np.testing.assert_array_equal(rlglb.accessor(original_g,blob,index),rlglb.accessor(result_g,result_b,b['attributes'][key]))
            np.testing.assert_array_equal(rlglb.accessor(original_g,blob,a['indices']),rlglb.accessor(result_g,result_b,b['indices']))
            assert a.get('targets')==b.get('targets')
    report={'source_sha256':sha(source),'source_atlas_sha256':sha(source.with_suffix('.png')),'output_sha256':sha(out),'atlas_sha256':sha(out.with_suffix('.png')),'tool_sha256':sha(__file__),'cap_paint':records,'all_non_uv_geometry_skin_and_morph_accessors_exact':True,'exterior_and_detail_uvs_exact':True,'qualified':False}
    save_json(out.with_suffix('.cap-paint.json'),report)
    print('CONTINUOUS_LOOSE_CAP_PAINT',report['output_sha256'],flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True);parser.add_argument('--out',required=True)
    args=parser.parse_args();bake(args.source,args.out)
