"""A zero-card profile must preserve the imported exterior without new strips."""
import unittest
from types import SimpleNamespace
import numpy as np
from build_loose_reference import detail_cards


class EmptyDetailProfile(unittest.TestCase):
    def test_zero_cards_at_every_lod(self):
        # Eligible source rows used to bypass a count==0 stop condition and
        # generate all available strips, exceeding both detail and LOD budgets.
        surface=SimpleNamespace(vertices=np.array([[.06,1.7,0],[.04,1.74,.01],[.05,1.78,0]]))
        head=SimpleNamespace(C=np.array([0,1.65,0]))
        spec={'seed':31,'details':{'fine_count':[0,0,0],'messy_count':[0,0,0],'segments':[5,3,2]}}
        for lod in range(3):
            with self.subTest(lod=lod):
                part=detail_cards(head,surface,np.tile([1,0,0],(3,1)),spec,lod)
                for field,width in [('P',3),('N',3),('UV',2),('T',3),('COL',4)]:
                    self.assertEqual(part[field].shape,(0,width))
                self.assertEqual((part['fine'],part['messy']),(0,0))


if __name__=='__main__':unittest.main()
