from pathlib import Path
from types import SimpleNamespace
import json
import sys
import unittest

import numpy as np


HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import bridge_export as B
import coastal_bridge_export as C


class Outline:
    def contains(self,x,z,tolerance=0.):return np.ones(np.broadcast(x,z).shape,bool)


class CoastalBridgeExportTests(unittest.TestCase):
    def fixture(self):
        floor=np.array([[[.25,2.,.25],[.25,2.,1.75],[1.75,2.,.25]],
                        [[1.75,2.,.25],[.25,2.,1.75],[1.75,2.,1.75]]],np.float32).astype(float)
        support=SimpleNamespace(name='west-foot',encoded_triangles=np.array(
            [[[.3,2.,.3],[.3,0.,.3],[.7,0.,.3]]],np.float32).astype(float))
        stair=SimpleNamespace(riser_triangles=np.array(
            [[[.25,1.,.25],[.25,0.,.25],[.75,0.,.25]]],np.float32).astype(float),supports=(support,))
        claim=SimpleNamespace(claim_id='coast-west-01',encoded_floor_triangles=floor,
                              loose_wet_cells=(4,5),road_ids=('road-west',),wet_extent_metres=(2.,4.),
                              join_stations_metres=(1.,5.),surfaces=(SimpleNamespace(name='floor'),),
                              evidence={'fullWidthJoins':{'acceptanceAuthority':True,'clear':True,
                                  'maximumGapMetres':.1,'worstBankXZ':[.5,.5]}},stairs=(stair,),supports=())
        world=SimpleNamespace(ids=['westhaven'],claimed_coastal_records=(claim,),
                              owner_at=lambda x,z:np.zeros(np.broadcast(x,z).shape,int),
                              height_at=lambda x,z:np.zeros(np.broadcast(x,z).shape))
        legacy={'id':500,'sites':[],'slice':(slice(2,4),slice(0,2)),'cells':np.ones((2,2),bool),
                'water':np.zeros((2,2),bool),'height':np.zeros((3,3)),'arch':None,'outline':Outline()}
        far=np.array([[[3.,0.,3.],[3.,0.,4.],[4.,0.,3.]]],np.float32).astype(float)
        claimed={'id':3,'sites':[2],'slice':(slice(3,4),slice(3,4)),'cells':np.ones((1,1),bool),
                 'arch':{'prepared':True},'_preparedMeshCache':(C._mesh(far),np.zeros(1,int))}
        mask=np.zeros((4,4),bool);mask[2:4,0:2]=True;mask[3,3]=True
        field={'x0':0.,'z0':0.,'cell':1.,'mask':mask,'height':np.zeros((5,5)),
               'components':[legacy,claimed],'outline':Outline(),'looseWetCells':99,
               'looseWetCellIndices':(4,5,10,11),'preparedLooseWetCellIndices':(4,5),
               'legacyLooseWetCellIndices':(10,11),
               'decks':[{'component':500,'sites':[],'bankErrorMetres':8.},
                   {'component':3,'sites':[2],'bankErrorMetres':.2,'worstDryLift':[3.,3.]}],
               'maximumBankError':8.,'worstBank':[9.,9.],'trimmedLandingCells':7,
               'cutOffLandingCells':3,'cutOffLandingBanks':[[1.,1.]]}
        world.claimed_coastal_inventory=C.build_selected_inventory(
            {'looseWetCellIndices':field['looseWetCellIndices']},(claim,))
        return world,claim,field,claimed

    def test_replacement_uses_exact_floor_for_cells_mesh_and_query(self):
        world,claim,field,claimed=self.fixture();actual=C.replace_legacy_loose_components(world,field)
        self.assertEqual(actual['looseWetCells'],4);self.assertIs(actual['components'][0],field['components'][0])
        self.assertIs(actual['components'][1],claimed)
        component=actual['components'][2];self.assertEqual(component['id'],'coast-west-01')
        self.assertNotIn('height',component)
        self.assertEqual(int(actual['mask'].sum()),9)
        self.assertEqual([deck['component'] for deck in actual['decks']],[500,3,'coast-west-01'])
        self.assertEqual((actual['preparedLooseWetCells'],actual['legacyLooseWetCells']),(2,2))
        self.assertEqual(actual['maximumBankError'],8.);self.assertEqual(actual['worstBank'],[9.,9.])
        self.assertEqual((actual['trimmedLandingCells'],actual['cutOffLandingCells']), (7,3))
        self.assertEqual(actual['cutOffLandingBanks'],[[1.,1.]])
        mesh,_=component['_preparedMeshCache']
        self.assertEqual(mesh.material,'bridge_timber')
        np.testing.assert_array_equal(mesh.uvs,mesh.positions[:,[0,2]]*.25)
        np.testing.assert_array_equal(mesh.positions[mesh.indices].reshape(-1,3,3),claim.encoded_floor_triangles)
        world.bridge_field=actual
        self.assertEqual(float(B.surface_at(world,.5,.5)),2.)

    def test_auxiliary_geometry_is_separate_stably_named_collision(self):
        world,_,_,_=self.fixture();parts=C.coastal_auxiliary_parts(world)
        self.assertEqual(len(parts),2);self.assertTrue(all(part['collides'] for part in parts))
        self.assertTrue(all('coast-west-01' in part['name'] for part in parts))
        self.assertEqual({part['recordId'] for part in parts},{'coast-west-01'})
        materials={'Riser' if '_Riser_' in part['name'] else 'Support':part['mesh'].material for part in parts}
        self.assertEqual(materials,{'Riser':'bridge_edge_timber','Support':'bridge_edge_timber'})

    def test_missing_or_stale_registry_and_missing_wet_count_fail_closed(self):
        world,claim,field,_=self.fixture();world.claimed_coastal_records=()
        with self.assertRaisesRegex(ValueError,'empty or not unique'):C.replace_legacy_loose_components(world,field)
        world.claimed_coastal_records=(SimpleNamespace(**{**claim.__dict__,'loose_wet_cells':None}),)
        with self.assertRaisesRegex(ValueError,'sorted unique nonnegative tuple'):
            C.replace_legacy_loose_components(world,field)

    def test_duplicate_or_incomplete_wet_ownership_fails_closed(self):
        world,claim,field,_=self.fixture()
        duplicate=SimpleNamespace(**{**claim.__dict__,'claim_id':'coast-west-02','loose_wet_cells':(5,)})
        world.claimed_coastal_records=(claim,duplicate)
        with self.assertRaisesRegex(ValueError,'ownership overlaps.*5'):
            C.replace_legacy_loose_components(world,field)
        world.claimed_coastal_records=(SimpleNamespace(**{**claim.__dict__,'loose_wet_cells':(4,)}),)
        with self.assertRaisesRegex(ValueError,'registry is stale'):
            C.replace_legacy_loose_components(world,field)

    def test_registry_rejects_duplicate_ids_and_out_of_authority_cells(self):
        _,claim,field,_=self.fixture()
        duplicate=SimpleNamespace(**{**claim.__dict__,'loose_wet_cells':(10,11)})
        with self.assertRaisesRegex(ValueError,'ids are empty or not unique'):
            C.build_selected_inventory({'looseWetCellIndices':field['looseWetCellIndices']},
                                       (claim,duplicate))
        outside=SimpleNamespace(**{**claim.__dict__,'claim_id':'outside',
                                   'loose_wet_cells':(4,99)})
        with self.assertRaisesRegex(ValueError,'outside current loose mask.*99'):
            C.build_selected_inventory({'looseWetCellIndices':field['looseWetCellIndices']},
                                       (outside,))

    def test_disjoint_wet_owners_cannot_emit_overlapping_prepared_floors(self):
        world,claim,field,_=self.fixture()
        second=SimpleNamespace(**{**claim.__dict__,'claim_id':'coast-east-02',
                                  'loose_wet_cells':(10,11)})
        world.claimed_coastal_records=(claim,second)
        world.claimed_coastal_inventory=C.build_selected_inventory(
            {'looseWetCellIndices':field['looseWetCellIndices']},world.claimed_coastal_records)
        field['preparedLooseWetCellIndices']=(4,5,10,11);field['legacyLooseWetCellIndices']=()
        with self.assertRaisesRegex(ValueError,'prepared coastal floors have positive overlap'):
            C.replace_legacy_loose_components(world,field)

    def test_field_cell_size_controls_actual_footprint_mask(self):
        world,claim,field,_=self.fixture();field['cell']=2.;field['mask']=np.zeros((2,2),bool)
        field['components'][0]['slice']=(slice(0,1),slice(0,1));field['components'][0]['cells']=np.ones((1,1),bool)
        field['components'][1]['slice']=(slice(1,2),slice(1,2));field['components'][1]['cells']=np.ones((1,1),bool)
        actual=C.replace_legacy_loose_components(world,field)
        self.assertEqual(int(actual['components'][2]['cells'].sum()),1)

    def test_complete_wet_authority_needs_no_legacy_component(self):
        world,claim,field,claimed=self.fixture();field['components']=[claimed]
        field['mask']=np.zeros_like(field['mask']);field['mask'][3,3]=True
        field['looseWetCellIndices']=(4,5);field['preparedLooseWetCellIndices']=(4,5)
        field['legacyLooseWetCellIndices']=()
        world.claimed_coastal_inventory=C.build_selected_inventory(
            {'looseWetCellIndices':(4,5)},(claim,))
        actual=C.replace_legacy_loose_components(world,field)
        self.assertEqual([component['id'] for component in actual['components']],[3,'coast-west-01'])
        self.assertEqual(actual['components'][1]['bankError'],.1)

    def test_touching_cell_without_positive_floor_overlap_is_allowed(self):
        world,claim,field,claimed=self.fixture()
        coast=np.array([[[0.,2.,0.],[0.,2.,1.],[1.,2.,0.]]],np.float32).astype(float)
        river=np.array([[[1.,1.,1.],[1.,1.,0.],[0.,1.,1.]]],np.float32).astype(float)
        world.claimed_coastal_records=(SimpleNamespace(**{**claim.__dict__,'encoded_floor_triangles':coast}),)
        world.claimed_coastal_inventory=C.build_selected_inventory(
            {'looseWetCellIndices':field['looseWetCellIndices']},world.claimed_coastal_records)
        claimed['slice']=(slice(0,1),slice(0,1));claimed['cells']=np.ones((1,1),bool)
        claimed['_preparedMeshCache']=(C._mesh(river),np.zeros(1,int))
        actual=C.replace_legacy_loose_components(world,field)
        self.assertEqual(len(actual['components']),3)

    def test_prepared_evidence_is_plain_json(self):
        world,claim,field,_=self.fixture()
        claim.evidence['numeric']={'points':np.array([[1.,2.]],np.float32),
                                   'count':np.int64(3),'clear':np.bool_(True)}
        report=C.replace_legacy_loose_components(world,field)['decks'][-1]
        encoded=json.loads(json.dumps(report))
        self.assertEqual(encoded['preparedEvidence']['numeric'],
                         {'points':[[1.0,2.0]],'count':3,'clear':True})


if __name__=='__main__':unittest.main()
