"""Replace an old MPFB shoulder-derived neck with a structured anatomical loft.

The input already contains the accepted canonical body as body primitive 1.
Retained upper-head P/N/J/W/UV data, body1, eyes, images and the 77-joint rig are
preserved. Apply before lower-face sculpting. The new neck uses an empty patch
inside the existing skin atlas; no materials, images or runtime work are added.
"""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
import fit_canonical as f


def mesh_data(glb,primitive):
    a=primitive['attributes'];tri=glb.read(primitive['indices']).reshape(-1,3)
    j,w=glb.read(a['JOINTS_0']),glb.read(a['WEIGHTS_0'])
    uv=glb.read(a['TEXCOORD_0'])
    return {'vertices':glb.read(a['POSITION']).astype(float),'normals':glb.read(a['NORMAL']),
            'triangles':tri,'uv':uv[tri],'vertex_uv':uv,'weights':f.dense_weights(j,w),
            'joints':j,'skinweights':w}


def image_bytes(glb,index):
    image=glb.doc['images'][index];view=glb.doc['bufferViews'][image['bufferView']]
    return bytes(glb.binary[view.get('byteOffset',0):view.get('byteOffset',0)+view['byteLength']])


def repair(input_path,output_path,fit_path=None,top_cut=1.55):
    if input_path.resolve()==output_path.resolve():raise ValueError('Keep the input stage immutable')
    glb=f.Glb(input_path);original=f.Glb(input_path)
    body=next(node for node in glb.doc['nodes'] if node.get('name')=='body')
    primitives=glb.doc['meshes'][body['mesh']]['primitives']
    old=mesh_data(glb,primitives[0]);native=mesh_data(glb,primitives[1])
    a=primitives[0]['attributes'];indices=primitives[0]['indices']
    material=glb.doc['materials'][primitives[0]['material']]
    image_index=glb.doc['textures'][material['pbrMetallicRoughness']['baseColorTexture']['index']]['source']
    size=Image.open(io.BytesIO(image_bytes(glb,image_index))).size
    head,topology=f.structured_neck_loft(old,native,top_cut=top_cut,atlas_size=size)
    flat=head['triangles'].ravel();flat_uv=head['uv'].reshape(-1,2)
    keys=np.column_stack((flat,np.round(flat_uv*1e7).astype(np.int64)))
    _,first,inverse=np.unique(keys,axis=0,return_index=True,return_inverse=True)
    ids=flat[first]
    arrays={a['POSITION']:head['vertices'][ids],a['NORMAL']:head['normals'][ids],
            a['TEXCOORD_0']:flat_uv[first],a['JOINTS_0']:head['joints'][ids],
            a['WEIGHTS_0']:head['skinweights'][ids],indices:inverse}
    # Reuse the six original accessor IDs. Compaction can discard their old
    # streams, leaving all non-head accessor IDs and payloads unchanged.
    for index,array in arrays.items():
        accessor=glb.doc['accessors'][index]
        array=np.asarray(array,dtype=f.DTYPES[accessor['componentType']])
        accessor['bufferView']=glb.blob(array.tobytes(),34963 if index==indices else 34962)
        accessor['count']=len(array);accessor.pop('byteOffset',None)
        if index==a['POSITION'] or 'min' in accessor:
            accessor.update(min=array.min(0).tolist(),max=array.max(0).tolist())
    glb.write(output_path)
    check=f.Glb(output_path)
    allowed=set(arrays)
    other_exact=all(np.array_equal(check.read(i),original.read(i)) for i in range(len(original.doc['accessors'])) if i not in allowed)
    assert other_exact
    assert len(check.doc['accessors'])==len(original.doc['accessors'])
    assert check.doc['nodes']==original.doc['nodes'] and check.doc['skins']==original.doc['skins']
    assert [image_bytes(check,i) for i in range(len(check.doc['images']))]==[image_bytes(original,i) for i in range(len(original.doc['images']))]
    origins=head['origins'][ids];retained=origins>=0
    uv=check.read(a['TEXCOORD_0'])
    retained_uv=retained.copy();retained_uv[retained]=np.all(uv[retained]==old['vertex_uv'][origins[retained]],axis=1)
    for attribute,key in [('POSITION','vertices'),('NORMAL','normals'),('JOINTS_0','joints'),('WEIGHTS_0','skinweights')]:
        assert np.array_equal(check.read(a[attribute])[retained_uv],old[key][origins[retained_uv]])
    report={'input_sha256':f.sha(input_path),'output_sha256':f.sha(output_path),
        'fitter_sha256':f.sha(Path(f.__file__)),'repair_tool_sha256':f.sha(Path(__file__)),
        'output_bytes':output_path.stat().st_size,'all_non_head_accessors_exact':other_exact,
        'nodes_skins_images_exact':True,'retained_original_export_vertices':int(retained_uv.sum()),
        'head_vertices_before':len(old['vertices']),'head_vertices_after':len(ids),
        'head_triangles_before':len(old['triangles']),'head_triangles_after':len(head['triangles']),
        'export_to_original_vertex':origins.tolist(),'export_retained_uv_mask':retained_uv.tolist(),
        'export_vertex_roles':[topology['vertex_roles'][i] for i in ids],
        'backend_vertex_indices':ids.tolist(),'topology':topology}
    if fit_path is None:fit_path=input_path.with_name('fit.json')
    if fit_path.exists():
        fit=json.loads(fit_path.read_text());fit['output_sha256']=f.sha(output_path)
        fit['head_bounds']=[check.read(a['POSITION']).min(0).tolist(),check.read(a['POSITION']).max(0).tolist()]
        fit['body_fit']={key:value for key,value in topology.items() if key not in ['source_vertex_origins','vertex_roles','face_roles']}
        output_path.with_name('fit.json').write_text(json.dumps(fit,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['input','output','report']:parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--fit',type=Path);parser.add_argument('--top-cut',type=float,default=1.55)
    args=parser.parse_args();report=repair(args.input,args.output,args.fit,args.top_cut)
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:report[key] for key in ['output_sha256','output_bytes','all_non_head_accessors_exact','nodes_skins_images_exact','retained_original_export_vertices','head_vertices_before','head_vertices_after','head_triangles_before','head_triangles_after']},indent=2))


if __name__=='__main__':main()
