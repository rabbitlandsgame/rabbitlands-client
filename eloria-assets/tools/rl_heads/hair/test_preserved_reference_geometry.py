import unittest
from unittest.mock import patch
import numpy as np
from types import SimpleNamespace
import build_loose_reference as loose
import build_tied_reference as tied


class Head:
    C=np.array([0.,1.7,0.]);eye_mid=np.array([0.,1.7,.08]);R=.1
    P=np.array([[-.1,1.6,0],[.1,1.6,0],[0,1.8,0]])
    T=np.array([[0,1,2]])
    def delta(self,name):return np.tile([.001,0,0],(3,1))
    def bind(self,P,**kwargs):return len(P)
    def bound_delta(self,count,D):return np.tile(D[0],(count,1))


class Binding:
    calls=[]
    def __init__(self,head,P,*args,**kwargs):self.P=P;self.dist=np.full(len(P),.01)
    def delta(self,D,**kwargs):
        Binding.calls.append(kwargs)
        return np.tile(D[0],(len(self.P),1))


class PreservedGeometryTests(unittest.TestCase):
    def setUp(self):
        self.P=np.array([[0,1.7,-.12],[.01,1.71,-.11],[.02,1.7,-.12],[0,1.72,-.10]],float)
        self.ranges={'exterior':[0,3],'backing':[3,3],'shell':[3,4],'detail':[4,4]}
        self.hull=np.array([[1,0,0,-1],[-1,0,0,-1],[0,1,0,-1.5],[0,-1,0,0],[0,0,1,-1],[0,0,-1,-1]],float)
        self.spec={'preserve_prepared_exterior':True,'preserve_curtain_depth':True,
                   'groom':{'root_fade_mm':[8,28],'length_positive':.4,'length_negative':.3,'volume_positive':.3,'volume_negative':.2},
                   'details':{'segments':[2,2,2]}}
        Binding.calls=[];tied.PROOFS.clear()

    def roots(self,head,scalp,P):return P-np.array([0,0,.01]),np.tile([0,0,1.],(len(P),1))

    def run_builder(self,builder):
        original=self.P.copy()
        with patch.object(loose.assemble,'Binding',Binding), \
             patch.object(loose.assemble,'push_out_var',side_effect=AssertionError('Legacy head push must not run')), \
             patch.object(loose.ref,'joint_groom_clearance',side_effect=AssertionError('Envelope must not alter a preserved source')), \
             patch.object(loose.ref,'roots',side_effect=self.roots), \
             patch.object(tied,'knot_field',side_effect=lambda P,Q,h,s,c,k,p:np.tile([0,-.03 if p else .02,0],(len(P),1))):
            scalp=SimpleNamespace(hairline=lambda longitude:np.full_like(longitude,-30))
            _,_,fields=builder(Head(),scalp,self.P,['id_fixture_p'],self.spec,self.hull,self.ranges)
        np.testing.assert_array_equal(self.P,original)
        np.testing.assert_allclose(fields['id_fixture_p'],np.tile([.001,0,0],(len(self.P),1)))
        self.assertEqual(Binding.calls,[{'keep_clear':False,'exact':False}])
        for name in loose.GROOMS:np.testing.assert_array_equal(fields[name][3],0)
        self.assertGreater(np.linalg.norm(fields['hl_length_p'][:3]),0)

    def test_loose_controls_retain_rest_and_skip_legacy_projection(self):self.run_builder(loose.groom_fields)
    def test_tied_controls_retain_rest_and_skip_legacy_projection(self):self.run_builder(tied.groom_builder)

    def test_optin_is_strict_and_default_stays_off(self):
        self.assertFalse(loose.preserve_prepared_exterior({}))
        self.assertFalse(loose.preserve_prepared_exterior({'preserve_prepared_exterior':False}))
        for value in [0,1,None,'true',[]]:
            with self.assertRaises(ValueError):loose.preserve_prepared_exterior({'preserve_prepared_exterior':value})

    def test_native_authoring_remains_a_separate_stage(self):
        self.spec['native_head_clearance_mm']=2.8
        with patch.object(tied,'native_surface') as native:
            with self.assertRaisesRegex(AssertionError,'separate Native corrective'):
                tied.groom_builder(Head(),None,self.P,[],self.spec,self.hull,self.ranges)
            native.assert_not_called()


if __name__=='__main__':unittest.main()
