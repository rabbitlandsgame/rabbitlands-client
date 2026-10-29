"""Raw object storage must preserve vertices, variants and all live image bytes."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'eloria-assets/tools'))
import optimize_static_glb_storage as S
import consolidate_map_vertices as G


def fixture(*, vertices=5, indices=None):
    positions = np.zeros((vertices, 3), '<f4')
    positions[:4] = [[0,0,0], [1,0,0], [0,0,1], [1,0,1]]
    positions[-1] = [90,50,-30]  # Unreferenced records/bounds must remain.
    normals = np.tile(np.array([[0,1,0]], '<f4'), (vertices, 1))
    uvs = positions[:, [0,2]].copy()
    colors = np.ones((vertices, 4), '<f4')
    faces = np.array(indices if indices is not None else [0,1,2,1,3,2], '<u4').reshape(-1,1)
    body = bytearray(); views = []; accessors = []
    def add(values, kind, component, target):
        body.extend(b'\0' * (-len(body) % 4))
        views.append(dict(buffer=0, byteOffset=len(body), byteLength=values.nbytes, target=target))
        body.extend(values.tobytes())
        accessor = dict(bufferView=len(views)-1, componentType=component, count=len(values), type=kind)
        accessor.update(min=values.min(0).astype(float).tolist(), max=values.max(0).astype(float).tolist())
        accessors.append(accessor)
        return len(accessors)-1
    attrs = {'POSITION': add(positions, 'VEC3', 5126, 34962), 'NORMAL': add(normals, 'VEC3', 5126, 34962),
             'TEXCOORD_0': add(uvs, 'VEC2', 5126, 34962), 'COLOR_0': add(colors, 'VEC4', 5126, 34962)}
    index = add(faces, 'SCALAR', 5125, 34963)
    images = []
    for i, size in enumerate((68,84,4096)):
        body.extend(b'\0' * (-len(body) % 4))
        views.append(dict(buffer=0, byteOffset=len(body), byteLength=size))
        body.extend(bytes([65+i]) * size)
        images.append(dict(bufferView=len(views)-1, mimeType='image/png', name='image-'+str(i)))
    body.extend(b'\0' * (-len(body) % 4))
    d = dict(asset={'version':'2.0','extras':{'sourceModelSha256':'1'*64}}, scene=0,
             scenes=[{'nodes':[0]}], nodes=[{'mesh':0,'name':'Bookcase','translation':[2,3,4],'extras':{'keep':True}}],
             meshes=[{'name':'bookcase','primitives':[{'attributes':attrs,'indices':index,'material':0,'mode':4}]}],
             materials=[{'name':'wood','pbrMetallicRoughness':{'baseColorTexture':{'index':0}},
                         'normalTexture':{'index':1,'scale':0.72}}],
             textures=[{'source':i,'sampler':0} for i in range(3)], images=images,
             samplers=[{'wrapS':10497,'wrapT':10497,'minFilter':9987}],
             accessors=accessors, bufferViews=views, buffers=[{'byteLength':len(body)}])
    return d, bytes(body)


class StaticStorageTests(unittest.TestCase):
    def optimize(self, d=None, b=None, **kwargs):
        if d is None: d,b=fixture()
        before=G.encode(d,b)
        result=S.optimize(before,**kwargs)
        return before,result

    def test_width_only_keeps_every_vertex_record_generated_shading_input_and_image(self):
        before,r=self.optimize()
        self.assertEqual(r['status'],'changed');self.assertEqual(r['removedImages'],[])
        left,lb=G.decode(before);right,rb=G.decode(r['data'])
        self.assertEqual(left['nodes'],right['nodes']);self.assertEqual(left['materials'],right['materials'])
        self.assertEqual(right['accessors'][4]['componentType'],5123)
        for i in range(4):
            self.assertEqual(G.accessor(left,lb,i).tobytes(),G.accessor(right,rb,i).tobytes())
            self.assertEqual(left['accessors'][i]['min'],right['accessors'][i]['min'])
            self.assertEqual(left['accessors'][i]['max'],right['accessors'][i]['max'])
        self.assertEqual(r['proof']['triangles'],2)

    def test_prune_is_opt_in_and_removes_only_unreferenced_image_and_texture(self):
        before,r=self.optimize(prune_unused_images=True,narrow_indices=False)
        self.assertEqual(r['removedImages'],[2]);self.assertEqual(r['narrowedAccessors'],[])
        self.assertEqual(r['imageIndexMap'],{0:0,1:1});self.assertEqual(r['textureIndexMap'],{0:0,1:1})
        d,b=G.decode(r['data']);self.assertEqual(len(d['images']),2);self.assertEqual(len(d['textures']),2)
        self.assertTrue(r['proof']['retainedImagesByteIdentical'])
        self.assertEqual(S.optimize(before,narrow_indices=False)['status'],'unchanged')

    def test_variant_material_keeps_image_not_used_by_default_primitive(self):
        d,b=fixture();d['materials'].append({'emissiveTexture':{'index':2}})
        d['extensionsUsed']=['KHR_materials_variants'];d['extensions']={'KHR_materials_variants':{'variants':[{'name':'lit'}]}}
        d['meshes'][0]['primitives'][0]['extensions']={'KHR_materials_variants':{'mappings':[{'material':1,'variants':[0]}]}}
        self.assertEqual(S.dependencies(d)['images'],[0,1,2])
        self.assertEqual(self.optimize(d,b,prune_unused_images=True,narrow_indices=False)[1]['status'],'unchanged')

    def test_unbound_declared_material_is_conservatively_retained(self):
        d,b=fixture();d['materials'].append({'occlusionTexture':{'index':2}})
        self.assertEqual(self.optimize(d,b,prune_unused_images=True,narrow_indices=False)[1]['status'],'unchanged')

    def test_nested_material_extension_slot_is_live(self):
        d,b=fixture();d['extensionsUsed']=['KHR_materials_clearcoat']
        d['materials'][0]['extensions']={'KHR_materials_clearcoat':{'clearcoatTexture':{'index':2}}}
        self.assertEqual(self.optimize(d,b,prune_unused_images=True,narrow_indices=False)[1]['status'],'unchanged')

    def test_alternate_texture_source_keeps_fallback_and_variant_images(self):
        d,b=fixture();d['extensionsUsed']=['KHR_texture_basisu']
        d['textures'][0]['extensions']={'KHR_texture_basisu':{'source':2}}
        self.assertEqual(self.optimize(d,b,prune_unused_images=True,narrow_indices=False)[1]['status'],'unchanged')

    def test_qualified_materials_and_samplers_are_semantically_identical_after_reindex(self):
        d,b=fixture();d['materials'][0]['normalTexture']['index']=2
        before,r=self.optimize(d,b,prune_unused_images=True)
        self.assertEqual(r['removedImages'],[1]);self.assertEqual(r['imageIndexMap'],{0:0,2:1})
        self.assertEqual(r['textureIndexMap'],{0:0,2:1})
        a,ab=G.decode(before);c,cb=G.decode(r['data'])
        self.assertEqual(S._materials(a,ab),S._materials(c,cb));self.assertEqual(a['samplers'],c['samplers'])

    def test_unknown_extension_and_ambiguous_image_extras_are_left_unchanged(self):
        d,b=fixture();d['extensionsUsed']=['VENDOR_future_images']
        self.assertEqual(self.optimize(d,b,prune_unused_images=True)[1]['status'],'skipped')
        d,b=fixture();d['asset']['extras']['imageIndex']=2
        self.assertEqual(self.optimize(d,b,prune_unused_images=True)[1]['reason'],'unqualified_image_or_texture_extras')

    def test_shared_image_view_cannot_remove_active_image_bytes(self):
        d,b=fixture();d['images'][2]['bufferView']=d['images'][0]['bufferView']
        before,r=self.optimize(d,b,prune_unused_images=True,narrow_indices=False)
        self.assertEqual(r['removedImages'],[2]);self.assertTrue(r['proof']['retainedImagesByteIdentical'])
        self.assertNotIn(d['images'][0]['bufferView'],r['removedBufferViews'])

    def test_uint16_primitive_restart_value_is_never_written(self):
        d,b=fixture(vertices=65536,indices=[0,1,65535])
        self.assertEqual(self.optimize(d,b)[1]['status'],'unchanged')
        d,b=fixture(vertices=65536,indices=[0,1,65534])
        r=self.optimize(d,b)[1]
        self.assertEqual(r['status'],'changed');self.assertTrue(r['proof']['vertexRecordsUnchanged'])

    def test_shared_index_accessor_is_narrowed_once(self):
        d,b=fixture();d['meshes'][0]['primitives'].append(copy.deepcopy(d['meshes'][0]['primitives'][0]))
        r=self.optimize(d,b)[1];self.assertEqual(r['narrowedAccessors'],[4]);self.assertEqual(r['proof']['triangles'],4)

    def test_accessor_also_used_as_vertex_data_keeps_original_storage(self):
        d,b=fixture();d['meshes'][0]['primitives'][0]['attributes']['_CUSTOM_INDEX']=4
        self.assertEqual(self.optimize(d,b)[1]['status'],'unchanged')

    def test_verifier_rejects_changed_unreferenced_vertex_record(self):
        before,r=self.optimize();d,b=G.decode(r['data']);body=bytearray(b)
        a=d['accessors'][0];v=d['bufferViews'][a['bufferView']];offset=v['byteOffset']+(a['count']-1)*12
        body[offset:offset+4]=np.array([999],'<f4').tobytes()
        with self.assertRaises(S.StorageError):
            S.verify_equivalent(before,G.encode(d,bytes(body)),removed_images=[],narrowed_accessors=[4])

    def test_verifier_rejects_changed_active_image(self):
        before,r=self.optimize();d,b=G.decode(r['data']);body=bytearray(b)
        view=d['bufferViews'][d['images'][0]['bufferView']];body[view['byteOffset']]^=1
        with self.assertRaises(S.StorageError):
            S.verify_equivalent(before,G.encode(d,bytes(body)),removed_images=[],narrowed_accessors=[4])

    def test_verifier_rejects_changed_numeric_index_order(self):
        before,r=self.optimize();d,b=G.decode(r['data']);body=bytearray(b)
        view=d['bufferViews'][d['accessors'][4]['bufferView']];body[view['byteOffset']:view['byteOffset']+2]=b'\x02\x00'
        with self.assertRaises(S.StorageError):
            S.verify_equivalent(before,G.encode(d,bytes(body)),removed_images=[],narrowed_accessors=[4])

    def test_sparse_deformation_and_external_buffers_are_not_rewritten(self):
        for change in ('sparse','skin','external'):
            d,b=fixture()
            if change=='sparse':d['accessors'][0]['sparse']={}
            elif change=='skin':d['skins']=[{}]
            else:d['buffers'][0]['uri']='elsewhere.bin'
            self.assertEqual(self.optimize(d,b)[1]['status'],'skipped')

    def test_invalid_variant_material_and_texture_indices_fail_closed(self):
        d,b=fixture();d['meshes'][0]['primitives'][0]['extensions']={'KHR_materials_variants':{'mappings':[{'material':999}]}}
        with self.assertRaises(S.StorageError):self.optimize(d,b)
        d,b=fixture();d['materials'][0]['normalTexture']['index']=999
        with self.assertRaises(S.StorageError):self.optimize(d,b)


if __name__=='__main__':unittest.main()
