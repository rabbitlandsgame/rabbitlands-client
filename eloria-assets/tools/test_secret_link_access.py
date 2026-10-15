import os,unittest
from pathlib import Path
import numpy as np
import secret_link_access as S
from generate_continent_walk_proof import runtime

@unittest.skipUnless(os.environ.get('ELORIA_PROOF_SERVER'),'paired collision implementation required')
class LinkAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.R=runtime(Path(os.environ['ELORIA_PROOF_SERVER']))

    def collision(self):
        raw=bytearray([13]*144)
        raw[6*12+6]=3  # A literal walkable but unreachable decorative-stone top.
        return self.R['collision'].with_step_mask(self.R['collision'].CollisionMap(12,12,bytes(raw)),2)

    def test_isolated_walkable_stone_cannot_be_the_portal_and_repair_is_bounded(self):
        c=self.collision();self.assertTrue(c.walkable(6,6))
        chosen,proof=S.select_link(c,(2,2),(6,6),lambda p:{'floor':0})
        self.assertNotEqual(chosen,(6,6));self.assertLessEqual(max(abs(chosen[i]-6) for i in (0,1)),2)
        self.assertGreater(proof['walkingSteps'],0)
        with self.assertRaisesRegex(ValueError,'No connected body-clear'):
            S.select_link(c,(2,2),(6,6),lambda p:None)

    def test_body_clearance_and_reserved_portals_are_not_bypassed_by_walkability(self):
        c=self.collision()
        clear=lambda p:{'floor':0} if p==(7,7) else None
        self.assertEqual(S.select_link(c,(2,2),(6,6),clear)[0],(7,7))
        with self.assertRaises(ValueError):S.select_link(c,(2,2),(6,6),clear,forbidden={(7,7)})
        chosen,proof=S.select_link(c,(2,2),(4,4),lambda p:{'floor':0})
        self.assertEqual(chosen,(4,4));self.assertFalse(proof['changed'])

class PhysicalTests(unittest.TestCase):
    def test_literal_stone_side_intersects_body_but_roof_and_soffit_do_not(self):
        side=np.array([[.2,0,-1],[.2,2,1],[.2,2,-1]])
        self.assertLess(S.body_distance((0,0),side,.05,1.9),.45)
        self.assertEqual(S.body_distance((0,0),side+np.array([0,4,0]),.05,1.9),float('inf'))
        self.assertEqual(S.body_distance((0,0),side-np.array([0,3,0]),.05,1.9),float('inf'))

if __name__=='__main__':unittest.main()
