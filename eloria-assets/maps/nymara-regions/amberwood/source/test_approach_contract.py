from pathlib import Path
from types import SimpleNamespace
import copy
import sys
import unittest
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parents[1]/'_toolkit')]
import approach_contract as A


class FinishedApproachContract(unittest.TestCase):
    def build(self):
        stations=[[0,10,0],[8,9,-4.5],[20,9,-4.5],[39,10,0],[42,10,0]]
        return SimpleNamespace(geography_roads=[dict(id=A.ROAD,stations=stations,contactNote='bypass')],
             streaming_borders=[dict(id=A.ROAD,anchor=[42,10,0],outward=[1,0])])

    def test_published_contract_uses_final_bed_and_does_not_mutate_road(self):
        b=self.build();before=copy.deepcopy(b.geography_roads);A.export(b)
        self.assertEqual(b.geography_roads,before)
        c=b.streaming_borders[0]['approachCenterline']
        self.assertEqual(c['stations'],before[0]['stations'])
        self.assertEqual((c['laneHalfWidth'],c['physicalHalfWidth'],c['walkingBias']),(3,4.25,.03))

    def test_rejects_changed_seam(self):
        b=self.build();b.geography_roads[0]['stations'][-1][0]+=1
        with self.assertRaisesRegex(ValueError,'published seam'):A.export(b)

    def test_explicit_moves_remain_bounded_unlinked_assemblies(self):
        self.assertEqual(set(A.MOVES),{'Undergrowth_0310','March_east_road_tree_000','March_east_road_tree_002','Tree_0857_dark_pine_Wood'})
        self.assertNotIn('Landmark_Watchtower_5',A.MOVES)


if __name__=='__main__':unittest.main()
