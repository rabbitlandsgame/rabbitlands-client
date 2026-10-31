import unittest
from unittest.mock import patch
import tempfile
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from PIL import Image
from build_loose_reference import fit_mapped_head,prepare


class HeadFitHook(unittest.TestCase):
    def setUp(self):
        self.P=np.array([[0.,1.6,.1],[.01,1.6,.1],[0.,1.61,.1]])
        self.N=np.tile([0.,0.,1.],(3,1))
        self.T=np.array([[0,1,2]])
        self.spec={'hairline':{'nape':True}}

    def test_default_forwards_exact_existing_push_inputs(self):
        sentinel=self.P+np.array([0,0,.0032])
        with patch('build_loose_reference.assemble.push_out_var',return_value=sentinel) as push:
            result,normal,receipt=fit_mapped_head('head',self.P,self.N,self.T,self.spec)
        self.assertIs(result,sentinel)
        self.assertIs(normal,self.N)
        self.assertIsNone(receipt)
        self.assertIs(push.call_args.args[1],self.P)
        np.testing.assert_array_equal(push.call_args.args[2],np.full(3,.0032))
        self.assertEqual(push.call_args.kwargs,{'iters':5})

    def test_callback_replaces_push_and_cannot_mutate_source(self):
        original=self.P.copy()
        def fit(head,P,N,T,spec):
            self.assertEqual(head,'mapped-head')
            np.testing.assert_array_equal(P,original)
            P[:,2]+=.008
            spec['hairline']['nape']=False
            return P,N,{'method':'source-specific coherent nape','maximum_mm':8.}
        with patch('build_loose_reference.assemble.push_out_var') as push:
            result,normal,receipt=fit_mapped_head('mapped-head',self.P,self.N,self.T,self.spec,fit)
        push.assert_not_called()
        np.testing.assert_array_equal(self.P,original)
        np.testing.assert_array_equal(self.T,[[0,1,2]])
        self.assertTrue(self.spec['hairline']['nape'])
        np.testing.assert_allclose(result-original,np.tile([0,0,.008],(3,1)))
        np.testing.assert_array_equal(normal,self.N)
        self.assertEqual(receipt['maximum_mm'],8.)

    def test_invalid_arrays_normals_topology_and_receipt_fail(self):
        callbacks=[lambda h,P,N,T,s:(P[:2],N,{}),
                   lambda h,P,N,T,s:(P*np.nan,N,{}),
                   lambda h,P,N,T,s:(P,N*2,{}),
                   lambda h,P,N,T,s:(P,N,{'bad':np.zeros(1)})]
        def change_topology(h,P,N,T,s):
            T[0]=[0,2,1]
            return P,N,{}
        callbacks.append(change_topology)
        for callback in callbacks:
            with self.assertRaises((AssertionError,TypeError)):
                fit_mapped_head(None,self.P,self.N,self.T,self.spec,callback)
        np.testing.assert_array_equal(self.T,[[0,1,2]])

    def test_prepare_keeps_callback_normals_through_later_body_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir()
            np.savez(source/'extracted.npz',P=self.P,N=self.N,T=self.T,UV=np.zeros((3,2)))
            for name in ['hair-mask.png','hair-only.png']:
                Image.new('RGBA',(2,2),(255,255,255,255)).save(source/name)
            (source/'source.json').write_text('{}')
            profile=root/'profile.json';profile.write_text(json.dumps({'name':'fixture','transport_normals':True,'outer_triangles':[1,1,1]}))
            fit=root/'fit.json';fit.write_text(json.dumps({'sex':'female'}))
            fake_glb=root/'head.glb';fake_glb.write_bytes(b'fixture-head-source')
            head=SimpleNamespace(glb_path=fake_glb)
            args=SimpleNamespace(source=str(source),stage=str(root/'out'),profile=str(profile),fit=str(fit),sex=None)
            custom=np.tile([1.,0.,0.],(3,1))
            def callback(h,P,N,T,spec):return P,custom.copy(),{'method':'custom-source-normals'}
            with patch('build_loose_reference.BoundedHead',return_value=head), \
                 patch('build_loose_reference.hairgen.Scalp',return_value=object()), \
                 patch('build_loose_reference.ref.neutralize',side_effect=lambda h,P,f,s:P.copy()), \
                 patch('build_loose_reference.body_hull',return_value=np.zeros((6,4))), \
                 patch('build_loose_reference.body_safe',side_effect=lambda h,P,*a,**k:P+np.array([.01,.02,.03])), \
                 patch('build_loose_reference.repair_collar',side_effect=lambda h,P,N,UV,T,*a:(P,N,T,{})), \
                 patch('build_loose_reference.conform_temples',side_effect=lambda h,s,P,N,T,*a:(P,N,{})), \
                 patch('build_loose_reference.paths.body_glb',return_value=str(fake_glb)), \
                 patch('build_loose_reference.assemble.push_out_var') as generic:
                prepare(args,head_fit=callback)
            generic.assert_not_called()
            with np.load(root/'out/extracted.npz') as result:
                np.testing.assert_allclose(result['N'],custom,atol=1e-12)
                np.testing.assert_allclose(result['P'],self.P+[.01,.02,.03],atol=1e-12)
            receipt=json.loads((root/'out/source.json').read_text())
            self.assertEqual(receipt['fitting']['head_fit'],{'method':'custom-source-normals'})


if __name__=='__main__':unittest.main()
