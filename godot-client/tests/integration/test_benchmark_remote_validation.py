import copy
import unittest
from benchmark_remote_validation import validate_remote,validate_remote_cell

def fixture():
    d={k:1 for k in ('event_calls','physics_calls','physics_outputs','motion_total_us','action_total_us',
        'surface_total_us','sink_total_us','event_boundary_us_nested','physics_total_us',
        'physics_apply_us_nested','transfer_total_us','full_server_apply_us','full_action_sink_us')}
    d.update(requested='rust',backend='rust',reason='experimental_remote_rust',fallbacks=0,
        ownedActors=159,native={'ready':True,'remote_api':1,'active_bindings':159},ordinaryGate={'backend':'rust','failures':0})
    c={'actorNodes':160,'localLegacy':1,'eligibleRemote':159,'nativeOwned':159,
       'legacySupported':0,'unsupportedRemote':{},'mountedOwned':80,'deferredOwned':20}
    return d,c

class RemoteEvidence(unittest.TestCase):
    def test_verified_complete_census(self):
        d,c=fixture();validate_remote(d,c,'rust','fixture',160)
    def test_absent_legacy_is_backward_compatible(self):
        validate_remote(None,None,'legacy','fixture')
    def test_backend_fallback_and_unowned_fail(self):
        for key,value in [('backend','legacy'),('fallbacks',1),('ownedActors',158)]:
            d,c=fixture();d[key]=value
            with self.assertRaises(ValueError):validate_remote(d,c,'rust','fixture',160)
        d,c=fixture();c.update(nativeOwned=158,legacySupported=1)
        with self.assertRaises(ValueError):validate_remote(d,c,'rust','fixture',160)
    def test_unsupported_crowd_cannot_be_promoted(self):
        d,c=fixture();c.update(eligibleRemote=158,nativeOwned=158,unsupportedRemote={'cinematic':1})
        with self.assertRaises(ValueError):validate_remote(d,c,'rust','fixture',160)
    def test_bad_costs_and_gate_fail(self):
        for value in (None,float('nan'),-1,True):
            d,c=fixture();d['physics_total_us']=value
            with self.assertRaises(ValueError):validate_remote(d,c,'rust','fixture',160)
        d,c=fixture();d['ordinaryGate']['backend']='legacy'
        with self.assertRaises(ValueError):validate_remote(d,c,'rust','fixture',160)
    def test_cell_requires_actual_activity_and_both_boundaries(self):
        d,c=fixture();cell={'id':'s3-market-160','count':160,'census':{}}
        cell['census']['afterSpawn']={'nodes':160,'remotePresentation':{'presentation':d,'coverage':c}}
        cell['census']['afterSample']=copy.deepcopy(cell['census']['afterSpawn'])
        with self.assertRaises(ValueError):validate_remote_cell(cell,'rust')
        for key in ('physics_outputs','physics_calls','event_calls'):
            cell['census']['afterSample']['remotePresentation']['presentation'][key]+=10
        validate_remote_cell(cell,'rust')

if __name__=='__main__':unittest.main()
