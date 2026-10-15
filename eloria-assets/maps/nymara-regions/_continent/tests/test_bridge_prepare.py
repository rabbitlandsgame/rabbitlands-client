from pathlib import Path
from types import ModuleType,SimpleNamespace
import sys
import unittest
from unittest.mock import patch
import numpy as np


HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import bridge_prepare as P
import bridge_export as E
import build_continent as B


class BridgePreparationTests(unittest.TestCase):
    def test_all_saved_zero_river_sites_continue_to_coastal_inventory_without_terrain_edits(self):
        world=SimpleNamespace(ids=['saved-west','saved-east'],crossing_sites=[],
                              water={'mask':np.zeros((2,2),bool)},height=np.array([[1.,2.],[3.,4.]]),
                              authored_terrain_authority=np.ones((2,2),bool))
        content=SimpleNamespace(authored_regions=set(world.ids))
        original=world.height.copy();water=world.water
        sea=ModuleType('sea_crossings');coast=ModuleType('coastal_bridge_export')
        sea.COMPONENT501_ROAD='coast-501';sea.COMPONENT502_ROAD='coast-502'
        sea.DEFAULT_SELECTED_COASTAL_ROADS=()
        sea._selected_coastal_roads=lambda values:tuple(values)
        sea.apply_coastal_road_edits=lambda actual:(_ for _ in ()).throw(AssertionError('unexpected road edit'))
        sea.prepare_coastal_claims=lambda actual,content=None,inventory=None,selected_road_ids=None:()
        inventory={'looseWetCellIndices':(),'components':()}
        registry={'mode':'selected-with-legacy-fallback','authorityLooseWetCellIndices':(),
                  'prepared':(),'fallbackLooseWetCellIndices':()}
        coast.build_selected_inventory=lambda actual,records:registry
        with patch.dict(sys.modules,{'sea_crossings':sea,'coastal_bridge_export':coast}), \
             patch.object(E,'loose_crossing_inventory',return_value=inventory):
            report=P.prepare_bridges(world,content)
        self.assertEqual(report['claimedRiverFit'],{'count':0,'siteIds':()})
        self.assertEqual(report['coastalClaims']['count'],0)
        np.testing.assert_array_equal(world.height,original)
        self.assertIs(world.water,water)

    def test_saved_manymouth_claim_skips_default_native_coastal_fit(self):
        from sea_crossings import COMPONENT502_ROAD

        world=SimpleNamespace(ids=['manymouth_delta'],crossing_sites=[],
                              water={'mask':np.zeros((2,2),bool)},height=np.ones((2,2)),
                              authored_terrain_authority=np.ones((2,2),bool))
        snapshot=SimpleNamespace(document={'replacements':{'routeIds':[COMPONENT502_ROAD]}})
        content=SimpleNamespace(authored_regions={'manymouth_delta'},
                                authoring_snapshots={'manymouth_delta':snapshot})
        inventory={'looseWetCellIndices':(4,8),'components':()}
        with patch.object(E,'loose_crossing_inventory',return_value=inventory), \
             patch('sea_crossings.prepare_coastal_claims',side_effect=AssertionError('native fit ran')):
            report=P.prepare_bridges(world,content)
        self.assertEqual(report['claimedRiverFit'],{'count':0,'siteIds':()})
        self.assertEqual(report['coastalClaims']['mode'],'saved-scene-authority')
        self.assertEqual(report['coastalClaims']['fallbackWetCells'],2)
        self.assertFalse(hasattr(world,'claimed_coastal_records'))
        self.assertFalse(hasattr(world,'claimed_coastal_inventory'))
        with self.assertRaisesRegex(ValueError,'owned by saved Manymouth'):
            P.prepare_bridges(world,content,selected_coastal_road_ids=[COMPONENT502_ROAD])
        snapshot.document['replacements']['routeIds']=[]
        with self.assertRaisesRegex(ValueError,'lack persistent route'):
            P.prepare_bridges(world,content)

    def test_default_component502_selection_does_not_apply_component501_edit(self):
        calls=[];world=SimpleNamespace();content=object()
        records=(SimpleNamespace(claim_id='coast-502'),)
        sea=ModuleType('sea_crossings');bridges=ModuleType('bridge_export');coast=ModuleType('coastal_bridge_export')
        sea.COMPONENT501_ROAD='coast-501';sea.COMPONENT502_ROAD='coast-502'
        sea.DEFAULT_SELECTED_COASTAL_ROADS=('coast-502',)
        sea._selected_coastal_roads=lambda values:tuple(values)
        sea.apply_coastal_road_edits=lambda actual:(_ for _ in ()).throw(
            AssertionError('component 501 edit ran during the component 502 release'))
        bridges.fit_claimed_sites=lambda actual,content=None:(calls.append(('river-fit',actual,content)) or {'selectedSiteIds':[3,7]})
        inventory={'looseWetCellIndices':(4,5,8),'components':()}
        bridges.loose_crossing_inventory=lambda actual:(calls.append(('inventory',actual)) or inventory)
        sea.prepare_coastal_claims=lambda actual,content=None,inventory=None,selected_road_ids=None:(
            calls.append(('coastal-fit',actual,content,inventory,selected_road_ids)) or records)
        registry={'mode':'selected-with-legacy-fallback','authorityLooseWetCellIndices':(4,5,8),
                  'prepared':({'looseWetCells':(4,5)},),'fallbackLooseWetCellIndices':(8,)}
        coast.build_selected_inventory=lambda actual,actual_records:(
            calls.append(('registry',actual,actual_records)) or registry)
        with patch.dict(sys.modules,{'sea_crossings':sea,'bridge_export':bridges,
                                     'coastal_bridge_export':coast}):
            report=P.prepare_bridges(world,content)
        self.assertEqual([call[0] for call in calls],
                         ['river-fit','inventory','coastal-fit','registry'])
        self.assertIs(calls[0][1],world);self.assertIs(calls[0][2],content);self.assertIs(calls[2][2],content)
        self.assertIs(calls[2][3],inventory);self.assertEqual(calls[2][4],('coast-502',))
        self.assertEqual(world.claimed_coastal_records,records)
        self.assertIs(world.claimed_coastal_inventory,registry)
        self.assertEqual(report,{'coastalRoadEdits':{'count':0,'roadIds':()},
                                 'claimedRiverFit':{'count':2,'siteIds':(3,7)},
                                 'coastalClaims':{'count':1,'claimIds':('coast-502',),
                                     'selectedRoadIds':('coast-502',),
                                     'mode':'selected-with-legacy-fallback','authorityWetCells':3,
                                     'preparedWetCells':2,'fallbackWetCells':1}})

    def test_component501_edit_is_gated_by_explicit_selection(self):
        world=SimpleNamespace();calls=[]
        sea=ModuleType('sea_crossings');bridges=ModuleType('bridge_export');coast=ModuleType('coastal_bridge_export')
        sea.COMPONENT501_ROAD='coast-501';sea.COMPONENT502_ROAD='coast-502'
        sea.DEFAULT_SELECTED_COASTAL_ROADS=('coast-502',)
        sea._selected_coastal_roads=lambda values:tuple(values)
        sea.apply_coastal_road_edits=lambda actual:(calls.append('edit') or (SimpleNamespace(road_id='coast-501'),))
        bridges.fit_claimed_sites=lambda actual,content=None:{'selectedSiteIds':[]}
        inventory={'looseWetCellIndices':(),'components':()}
        bridges.loose_crossing_inventory=lambda actual:inventory
        record=SimpleNamespace(claim_id='coastal-501')
        sea.prepare_coastal_claims=lambda *args,**kwargs:(record,)
        registry={'mode':'selected-with-legacy-fallback','authorityLooseWetCellIndices':(),
                  'prepared':(),'fallbackLooseWetCellIndices':()}
        coast.build_selected_inventory=lambda actual,records:registry
        with patch.dict(sys.modules,{'sea_crossings':sea,'bridge_export':bridges,
                                     'coastal_bridge_export':coast}):
            report=P.prepare_bridges(world,object(),selected_coastal_road_ids=('coast-501',))
        self.assertEqual(calls,['edit'])
        self.assertEqual(report['coastalRoadEdits']['roadIds'],('coast-501',))
        self.assertEqual(report['coastalClaims']['selectedRoadIds'],('coast-501',))

    def test_coordinator_is_a_composition_shaping_source(self):
        self.assertIn('bridge_prepare.py',B.SHAPING_SOURCES)


if __name__=='__main__':unittest.main()
