"""Exact map storage rewrites must preserve every drawn corner and bounds."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'eloria-assets/tools'))
import consolidate_map_vertices as CV


def fixture(*, indexed=False, padded=False, unused_extreme=False):
    corners=np.array([[0,0,0],[1,0,0],[0,0,1],[1,0,0],[1,0,1],[0,0,1]],np.float32)
    p=np.tile(corners,(40,1))
    if unused_extreme:
        p=np.concatenate([p,np.array([[90,50,-30],[80,40,-20]],np.float32)])
        indexed=True
    n=len(p);normal=np.tile([0,1,0],(n,1)).astype(np.float32)
    uv=p[:,[0,2]].copy();color=np.ones((n,4),np.float32)
    body=bytearray();views=[];accessors=[];attrs={}
    def add(values,kind,ctype,semantic=None):
        width=values.dtype.itemsize*values.shape[1];stride=(width+3)//4*4
        raw=np.zeros((len(values),stride),np.uint8);raw[:,:width]=values.view(np.uint8).reshape(len(values),width)
        body.extend(b'\0'*(-len(body)%4));views.append(dict(buffer=0,byteOffset=len(body),byteLength=raw.nbytes,byteStride=stride))
        body.extend(raw.tobytes());a=dict(bufferView=len(views)-1,componentType=ctype,count=len(values),type=kind)
        if semantic=='POSITION':a.update(min=values.min(0).tolist(),max=values.max(0).tolist())
        if semantic and ctype==5120:a['normalized']=True
        accessors.append(a)
        if semantic:attrs[semantic]=len(accessors)-1
        return len(accessors)-1
    add(p,'VEC3',5126,'POSITION')
    add((normal*127).astype(np.int8) if padded else normal,'VEC3',5120 if padded else 5126,'NORMAL')
    add(uv,'VEC2',5126,'TEXCOORD_0');add(color,'VEC4',5126,'COLOR_0')
    prim=dict(attributes=attrs,material=0,mode=4,extras={'keep':'primitive'})
    if indexed:prim['indices']=add(np.arange(240,dtype=np.uint32).reshape(-1,1),'SCALAR',5125)
    doc=dict(asset={'version':'2.0'},scene=0,scenes=[{'nodes':[0]}],nodes=[{'name':'Walk_A','mesh':0,'translation':[3,2,1],'extras':{'keep':True}}],
             meshes=[{'name':'road','primitives':[prim]}],materials=[{'name':'earth'}],
             accessors=accessors,bufferViews=views,buffers=[{'byteLength':len(body)}])
    if padded:doc['extensionsUsed']=doc['extensionsRequired']=['KHR_mesh_quantization']
    return doc,bytes(body)


class ConsolidateMapVerticesTest(unittest.TestCase):
    def rewrite(self,doc,body):
        before=CV.encode(doc,body);result=CV.consolidate(before)
        self.assertEqual(result['status'],'changed',result)
        self.assertLess(len(result['data']),len(before));CV.verify_equivalent(before,result['data'])
        return result,CV.decode(result['data'])

    def test_full_tuple_weld_is_stable_and_idempotent(self):
        d,b=fixture();r,(out,body)=self.rewrite(d,b)
        self.assertEqual(r['verticesAfter'],4);self.assertEqual(r['triangles'],80)
        p=out['meshes'][0]['primitives'][0]
        np.testing.assert_array_equal(CV.accessor(out,body,p['attributes']['POSITION']),
                                      [[0,0,0],[1,0,0],[0,0,1],[1,0,1]])
        self.assertEqual(CV.consolidate(r['data'])['status'],'unchanged')

    def test_uv_normal_and_colour_seams_are_not_welded(self):
        for semantic in ('TEXCOORD_0','NORMAL','COLOR_0'):
            d,b=fixture();a=d['accessors'][d['meshes'][0]['primitives'][0]['attributes'][semantic]]
            start=d['bufferViews'][a['bufferView']]['byteOffset'];body=bytearray(b)
            body[start:start+4]=np.array([.25],np.float32).tobytes()
            r,_=self.rewrite(d,bytes(body));self.assertEqual(r['verticesAfter'],5,semantic)

    def test_quantized_padded_normals_remain_exact(self):
        d,b=fixture(padded=True);r,(out,body)=self.rewrite(d,b)
        a=out['accessors'][out['meshes'][0]['primitives'][0]['attributes']['NORMAL']]
        self.assertEqual(a['componentType'],5120);self.assertTrue(a['normalized'])
        self.assertEqual(out['bufferViews'][a['bufferView']]['byteStride'],4)

    def test_interleaved_shared_views_and_embedded_images_are_preserved(self):
        d,b=fixture();p=d['meshes'][0]['primitives'][0]
        position=CV.accessor(d,b,p['attributes']['POSITION']);normal=CV.accessor(d,b,p['attributes']['NORMAL'])
        interleaved=np.ascontiguousarray(np.concatenate((position,normal),axis=1)).tobytes()
        rest=d['bufferViews'][2]['byteOffset'];body=interleaved+b[rest:]
        for i in (0,1):d['bufferViews'][i].update(byteOffset=0,byteLength=len(interleaved),byteStride=24)
        d['accessors'][1]['byteOffset']=12
        image=b'unchanged-image-payload!!';image+=b'\0'*(-len(image)%4)
        d['bufferViews'].append({'buffer':0,'byteOffset':len(body),'byteLength':len(image)})
        d['images']=[{'bufferView':len(d['bufferViews'])-1,'mimeType':'image/png','name':'preserved'}]
        body+=image;d['buffers'][0]['byteLength']=len(body)
        r,(out,packed)=self.rewrite(d,body);self.assertEqual(r['verticesAfter'],4)
        view=out['bufferViews'][out['images'][0]['bufferView']]
        self.assertEqual(packed[view['byteOffset']:view['byteOffset']+view['byteLength']],image)

    def test_publisher_consolidates_after_quantization_and_updates_size(self):
        import shared_meshes as SM
        with tempfile.TemporaryDirectory(prefix='exact-finish-') as folder:
            root=Path(folder);package=root/'nymara-regions/example';package.mkdir(parents=True)
            d,b=fixture();body=bytearray(b)
            # Two float normals differ in bytes but become the same byte normal.
            start=d['bufferViews'][1]['byteOffset'];body[start:start+4]=np.array([.000001],np.float32).tobytes()
            path=package/'world.glb';path.write_bytes(SM.write_glb(d,bytes(body)))
            manifest=package/'world.json';manifest.write_text(json.dumps({'asset':{'glb':'world.glb'},'performance':{'glbBytes':1}}))
            import os
            env=dict(os.environ,ELORIA_MAPS_ROOT=str(root))
            tool=Path(__file__).resolve().parents[2]/'eloria-assets/tools/publish_finish.py'
            done=subprocess.run([sys.executable,str(tool),str(path)],capture_output=True,text=True,env=env)
            self.assertEqual(done.returncode,0,done.stdout+done.stderr)
            result,binary=CV.decode(path.read_bytes());attrs=result['meshes'][0]['primitives'][0]['attributes']
            self.assertEqual(result['accessors'][attrs['NORMAL']]['componentType'],5120)
            self.assertEqual(result['accessors'][attrs['POSITION']]['count'],4)
            self.assertEqual(json.loads(manifest.read_text())['performance']['glbBytes'],path.stat().st_size)

    def test_publication_totals_follow_the_restated_cells(self):
        import publish_finish as PF
        with tempfile.TemporaryDirectory(prefix='exact-publication-') as folder:
            record=Path(folder)/'publication.json'
            record.write_text(json.dumps({'estimatedResidentMiB':{'a':1},
                                          'chunkGlbBytes':{'total':1,'max':1,'over100MiB':[]}}))
            cells=[{'id':'a','glbBytes':200,'estimatedResidentBytes':4*1048576}]
            before=record.read_bytes();self.assertTrue(PF._restate_publication(record,cells,True))
            self.assertEqual(record.read_bytes(),before)
            self.assertTrue(PF._restate_publication(record,cells,False))
            written=json.loads(record.read_text());self.assertEqual(written['chunkGlbBytes']['total'],200)
            self.assertEqual(written['chunkGlbBytes']['max'],200);self.assertEqual(written['estimatedResidentMiB']['a'],4)

    def test_unused_bound_extrema_are_retained(self):
        d,b=fixture(unused_extreme=True);r,(out,body)=self.rewrite(d,b)
        self.assertEqual(r['verticesAfter'],5)
        a=out['accessors'][out['meshes'][0]['primitives'][0]['attributes']['POSITION']]
        self.assertEqual(a['max'],[90,50,1]);self.assertEqual(a['min'],[0,0,-30])

    def test_shared_accessors_materials_and_nodes_keep_their_contract(self):
        d,b=fixture(indexed=True);d['meshes'][0]['primitives'].append(copy.deepcopy(d['meshes'][0]['primitives'][0]))
        d['materials'].append({'name':'other'});d['meshes'][0]['primitives'][1]['material']=1
        r,(out,body)=self.rewrite(d,b);self.assertEqual(out['nodes'],d['nodes'])
        self.assertEqual(out['materials'],d['materials']);self.assertEqual(r['triangles'],160)

    def test_generated_shading_is_not_changed(self):
        for kind in ('missing_normal','missing_tangent'):
            d,b=fixture()
            if kind=='missing_normal':d['meshes'][0]['primitives'][0]['attributes'].pop('NORMAL')
            else:d['materials'][0]['normalTexture']={'index':0}
            self.assertEqual(CV.consolidate(CV.encode(d,b))['status'],'unchanged')

    def test_unsupported_contracts_are_skipped(self):
        for kind in ('skin','animation','sparse','morph','lines','extension','joints','external'):
            d,b=fixture();p=d['meshes'][0]['primitives'][0]
            if kind=='skin':d['nodes'][0]['skin']=0
            elif kind=='animation':d['animations']=[{}]
            elif kind=='sparse':d['accessors'][0]['sparse']={}
            elif kind=='morph':p['targets']=[{'POSITION':0}]
            elif kind=='lines':p['mode']=1
            elif kind=='extension':d['extensionsUsed']=['EXT_meshopt_compression']
            elif kind=='joints':p['attributes']['JOINTS_0']=0
            else:d['buffers'][0]['uri']='other.bin'
            self.assertEqual(CV.consolidate(CV.encode(d,b))['status'],'skipped',kind)

    def test_corrupt_index_is_rejected(self):
        d,b=fixture(indexed=True);a=d['accessors'][-1];start=d['bufferViews'][a['bufferView']]['byteOffset'];bad=bytearray(b)
        bad[start:start+4]=np.array([99999],np.uint32).tobytes()
        with self.assertRaises(CV.ConsolidationError):CV.consolidate(CV.encode(d,bytes(bad)))

    def test_placement_only_glb_without_bin_is_unchanged(self):
        import shared_meshes as SM
        raw=SM.write_glb({'asset':{'version':'2.0'},'meshes':[], 'nodes':[],
                          'buffers':[{'byteLength':0}], 'accessors':[], 'bufferViews':[]},b'')
        self.assertEqual(CV.consolidate(raw)['status'],'unchanged')

    def test_verifier_detects_changed_corner_or_placement(self):
        d,b=fixture();before=CV.encode(d,b);r=CV.consolidate(before);after,body=CV.decode(r['data'])
        after['nodes'][0]['translation'][0]=12
        with self.assertRaises(CV.ConsolidationError):CV.verify_equivalent(before,CV.encode(after,body))


if __name__=='__main__':unittest.main()
