"""Published crossings keep the palette the regional recipes read."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import build_continent as B


class CrossingPaletteTests(unittest.TestCase):
    def test_legacy_pair_palette_is_retained_and_new_pairs_use_the_first_biome(self):
        legacy=[{'id':'amberwood-whitehorn','palette':'alpine','ends':[{'region':'amberwood'},{'region':'whitehorn_range'}]},
                {'id':'grey-westhaven','palette':'pasture','ends':[{'region':'grey_moors'},{'region':'westhaven'}]}]
        self.assertEqual(B.crossing_palette(['whitehorn_range','amberwood'],legacy),'alpine')
        self.assertEqual(B.crossing_palette(['grey_moors','westhaven'],legacy),'pasture')
        self.assertEqual(B.crossing_palette(['grey_moors','whitehorn_range'],legacy),'moor')
        self.assertEqual(B.crossing_palette(['sunmane_steppe','verdant_stair'],legacy),'steppe')
        self.assertEqual(B.crossing_palette(['unknown','verdant_stair'],[]),'pasture')

    def test_every_territory_has_a_biome_palette_the_toolkit_knows(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'_toolkit'))
        import streaming_borders as S
        for region,palette in B.REGION_PALETTES.items():
            self.assertIn(palette,S.PALETTES,region)


if __name__=='__main__':
    unittest.main()
