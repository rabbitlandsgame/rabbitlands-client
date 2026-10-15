"""Waterfront structures keep sea level, coherent contacts and quiet basins."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import assemblies as A
import westhaven_support as W


class WesthavenSupportTests(unittest.TestCase):
    def test_water_architecture_and_its_work_yards_share_one_rigid_group(self):
        names = ('Landmark_Pier_A', 'Landmark_Pier_B', 'Jetty_05', 'Ship_At_Cargo_Pier',
            'Landmark_Harbour_Crane', 'Prop_Quay_Bollard_04', 'Landmark_Warehouse_04',
            'Landmark_Route_yard_bridge', 'Landmark_Guild_Hall', 'Entry_bonded_vaults_door',
            'Secret_haven_shipyard_butts', 'Mole_Run_07', 'Landmark_Gullstone_Watch')
        for name in names:
            self.assertEqual(A.placement_group('westhaven', {'node': name}), W.HARBOUR)
        for name in W.LIGHTHOUSE_NODES:
            self.assertEqual(A.placement_group('westhaven', {'node': name}), W.LIGHTHOUSE)
        for name in ('House_upper_0', 'Rock_lamp_rock_0078', 'Landmark_Cathedral', 'March_crownwater_berth_Stone'):
            self.assertIsNone(A.placement_group('westhaven', {'node': name}))

    def test_pier_boat_and_crane_keep_their_relative_heights_above_deep_bed(self):
        placements = [{'node': name, 'position': p} for name, p in (
            ('Landmark_Pier_A', [68, 3.4, 13]), ('Ship_At_Cargo_Pier', [57.5, 0, 31]),
            ('Landmark_Gantry', [63.4, 3.4, 24]))]
        bounds = {p['node']: (np.asarray(p['position'])-1, np.asarray(p['position'])+1) for p in placements}
        group = A.build_assemblies('westhaven', placements, bounds, lambda x, z: -8.)[W.HARBOUR]
        shift = group.shift_to(lambda p: p+W.TRANSLATIONS[W.HARBOUR][::2], lambda x, z: 21.)
        np.testing.assert_allclose(shift, W.TRANSLATIONS[W.HARBOUR])
        translated = np.array([p['position'] for p in placements])+shift
        np.testing.assert_allclose(translated[:, 1], [3.4, 0, 3.4])
        np.testing.assert_allclose(translated[0]-translated[1], [10.5, 3.4, -18])

    def test_four_half_cells_keep_quay_contact_and_water_beneath_the_deck(self):
        equations = W.envelope([[-20, -20], [40, -20], [40, 50], [-20, 50]])
        # The quay ends at source Z=10; the pier's floor is architectural and
        # must not cause an island to be raised underneath its wet span.
        survey = lambda x, z: np.where(z < 10, 3.4, -7.5)
        points = np.array([[x, z] for x in (4.25, 4.75) for z in (4.25, 4.75)] +
                          [[x, z] for x in (4.25, 4.75) for z in (24.25, 24.75)])
        p = points+[120, 1120]
        target, weight = W.support_fields(p[:, 0], p[:, 1], [120, 0, 1120], equations, survey)
        np.testing.assert_allclose(weight, 1)
        np.testing.assert_allclose(target, [3.4]*4+[-7.5]*4)

    def test_irregular_support_has_soft_shoulders_and_leaves_distant_ground_untouched(self):
        equations = W.envelope([[0, 0], [20, 0], [10, 20]])
        target, weight = W.support_fields([130, 130, 130, 250], [1125, 1155, 1190, 1300],
                                          [120, 0, 1120], equations, lambda x, z: np.zeros_like(x))
        self.assertEqual(weight[0], 1)
        self.assertGreater(weight[1], 0)
        self.assertLess(weight[1], 1)
        np.testing.assert_allclose(weight[2:], 0)
        continental = np.array([12., 12., 12., 12.])
        merged = continental*(1-weight)+target*weight
        np.testing.assert_allclose(merged[2:], continental[2:])

    def test_lighthouse_has_its_own_sea_datum_and_clear_separation_from_mole(self):
        lighthouse = np.array([208.065, 17, 82.665])+W.TRANSLATIONS[W.LIGHTHOUSE]
        mole = np.array([125, 5.2, 64])+W.TRANSLATIONS[W.HARBOUR]
        self.assertGreater(np.linalg.norm((lighthouse-mole)[[0, 2]]), 29)
        self.assertEqual(lighthouse[1], 17)
        self.assertEqual(mole[1], 5.2)

    def test_bridge_bank_collars_come_from_real_terminal_edges_and_leave_water_open(self):
        vertices = np.array([[0, 3.5, -3], [30, 2.8, -3], [0, 3.5, 3], [30, 2.8, 3]])
        triangles = vertices[[[0, 2, 1], [1, 2, 3]]]
        contacts = W.bridge_terminals(triangles)
        x = np.array([.25, .75, 15., 29.25, 29.75])
        z = np.zeros_like(x)
        terrain = np.full_like(x, -7.)
        for edge in contacts:
            target, weight = W.contact_fields(x, z, edge)
            terrain = terrain*(1-weight)+target*weight
        np.testing.assert_allclose(terrain, [3.5, 3.5, -7., 2.8, 2.8])


if __name__ == '__main__':
    unittest.main()
