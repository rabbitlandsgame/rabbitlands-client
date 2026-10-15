"""The real Underdeck must contain a clear floor between its two doorways."""
from pathlib import Path
import json
import sys
import unittest
import numpy as np

REGIONS=Path(__file__).resolve().parents[1]/'maps/nymara-regions'
sys.path.insert(0,str(REGIONS/'_toolkit'))
import glb_reader as G
PACKAGE=REGIONS/'interiors/manymouth_delta_insides'


def clips_body(triangle, low, high):
    """Clip an actual triangle against a conservative standing actor box."""
    polygon=list(triangle)
    for axis in range(3):
        for limit,sign in ((low[axis],1),(high[axis],-1)):
            result=[]
            for a,b in zip(polygon,polygon[1:]+polygon[:1]):
                da=(a[axis]-limit)*sign;db=(b[axis]-limit)*sign
                if da>=0:result.append(a)
                if (da>=0)!=(db>=0):result.append(a+(b-a)*(da/(da-db)))
            polygon=result
            if not polygon:return False
    return True


class UnderdeckAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((PACKAGE/'world.json').read_text())
        document,body=G.load(PACKAGE/'world.glb')
        cls.walk=G.triangles(document,body,G.named(document,'Walk_'))
        # The maze deliberately wades through the native shallow water at
        # y=-.9. Its transparent water-box side is not a solid body obstacle.
        cls.all=G.triangles(document,body,[i for i,n in enumerate(document['nodes'])
            if 'mesh' in n and not n.get('name','').endswith(('_manymouth_delta_shallow','_manymouth_delta_deep','_water_deep'))])

    def test_missing_native_link_has_floor_at_actual_actor_centres(self):
        # Three one-metre lanes through both literal doorway overlaps.
        # Deliberately sample each lane separately, rather than a dense corner
        # grid accidentally covering only one side of the 3.4m passage.
        for x in (169.,170.,171.):
            covered,top=G.rasterise(self.walk,1,57,x-.125,107.125,.25)
            self.assertTrue(covered.all(),f'Absent floor along x={x}')
            np.testing.assert_allclose(top,-1.6,atol=1e-5)
        space=self.manifest['spaces']['smugglers_warren.mazeway']
        self.assertEqual(space['floor'],-1.6)
        self.assertLessEqual(space['z0'],94.)
        self.assertGreaterEqual(space['z1'],106.)

    def test_new_passage_and_doorways_clear_the_literal_actor_body(self):
        lo,hi=self.all.min(axis=1),self.all.max(axis=1)
        checked=0
        for x in (169.,170.,171.):
            for z in np.arange(93.,107.01,.25):
                low=np.array([x-.45,-1.5,z-.45]);high=np.array([x+.45,.3,z+.45])
                near=(hi>=low).all(axis=1)&(lo<=high).all(axis=1)
                self.assertFalse(any(clips_body(t,low,high) for t in self.all[near]),(x,z))
                checked+=1
        self.assertEqual(checked,171)

    def test_existing_named_arrival_and_cache_identity_remain(self):
        arrival=next(x for x in self.manifest['spawnPoints'] if x['id']=='underdeck-hatch')
        self.assertEqual(arrival['position'],[170.,-1.55,39.5])
        hatch=next(x for x in self.manifest['interactives'] if x['id']=='secret-delta-market-cache')
        self.assertEqual(hatch['space'],'smugglers_warren.cache')
        self.assertEqual(hatch['position'],[211.5,-.6,128.5])
        self.assertEqual(hatch['destinationMap'],'manymouth_delta_secrets')


if __name__=='__main__':unittest.main()
