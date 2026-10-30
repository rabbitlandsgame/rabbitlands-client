"""Keep pilot fine-card UVs inside their atlas strip, away from repeat edges.

python guard_atlas_uvs.py source.glb output.glb
No positions, skin data, topology, normals or morph accessors are changed.
The input must use the original pilot 0.9..1.0 card strip; keep the input.
"""
import argparse,copy,hashlib,json,struct
from pathlib import Path
import numpy as np
import rlglb

def main():
    ap=argparse.ArgumentParser();ap.add_argument('source');ap.add_argument('out');a=ap.parse_args()
    source=Path(a.source);out=Path(a.out);assert source.resolve()!=out.resolve()
    g,b=rlglb.read(str(source));original=copy.deepcopy(g);blob=bytearray(b);changed=0
    assert g['asset']['extras']['rlHair']['style'] in ('rounded_afro','cornrows_low_knot','curly_twin_buns','shoulder_waves','receding_sweep')
    for mesh in g['meshes']:
        for primitive in mesh['primitives']:
            if g['materials'][primitive['material']]['name']!='rl_hair_card':continue
            index=primitive['attributes']['TEXCOORD_0'];uv=rlglb.accessor(g,b,index).copy()
            assert uv[:,1].min()>=.8999 and uv[:,1].max()<=1.0001
            uv[:,1]=.901+(uv[:,1]-.9)*.98
            accessor=g['accessors'][index];view=g['bufferViews'][accessor['bufferView']];assert not view.get('byteStride')
            start=view.get('byteOffset',0)+accessor.get('byteOffset',0);values=uv.astype('<f4');blob[start:start+values.nbytes]=values.tobytes()
            if 'min' in accessor:accessor['min']=uv.min(0).tolist();accessor['max']=uv.max(0).tolist()
            changed+=len(uv)
    for mesh in original['meshes']:
        for primitive in mesh['primitives']:
            for name,index in primitive['attributes'].items():
                if name!='TEXCOORD_0':assert np.array_equal(rlglb.accessor(original,b,index),rlglb.accessor(g,blob,index))
            for target in primitive.get('targets',[]):
                for index in target.values():assert np.array_equal(rlglb.accessor(original,b,index),rlglb.accessor(g,blob,index))
    text=json.dumps(g,separators=(',',':')).encode();text+=b' '*((-len(text))%4);blob+=b'\0'*((-len(blob))%4)
    out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(struct.pack('<III',0x46546c67,2,28+len(text)+len(blob))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(blob),0x004e4942)+blob)
    receipt={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'card_vertices':changed,'old_v':[.9,1.0],'new_v':[.901,.999],'geometry_skin_morphs_preserved':True}
    out.with_suffix('.uv-guard.json').write_text(json.dumps(receipt,indent=2));print(json.dumps(receipt),flush=True)

if __name__=='__main__':main()
