"""Small geometric paint fixtures; no private input or runtime assets required."""
import unittest
import numpy as np
from bake_reference_paint import bake_chart_paint,pack_chart_islands,_barycentric


class PaintBakeTests(unittest.TestCase):
    def test_retained_thin_donor_has_stable_barycentric_coordinates(self):
        triangles=np.array([[[0,0,0],[.05,0,0],[.05,2e-12,0]]],float)
        expected=np.array([[.2,.3,.5]])
        point=np.einsum('fc,fcv->fv',expected,triangles)
        # This face passes the donor-area gate but its Gram determinant cancels.
        self.assertGreater(np.linalg.norm(np.cross(triangles[0,1],triangles[0,2])),1e-14)
        np.testing.assert_allclose(_barycentric(point,triangles),expected,atol=1e-14)

    def test_truly_degenerate_donor_still_fails(self):
        with self.assertRaisesRegex(AssertionError,'Degenerate'):
            _barycentric(np.zeros((1,3)),np.array([[[0,0,0],[1,0,0],[2,0,0]]],float))

    def fixture(self):
        positions=np.array([[-1,0,0],[0,0,0],[0,1,0],[-1,1,0],[0,0,0],[1,0,0],[1,1,0],[0,1,0]],float)
        triangles=np.array([[0,1,2],[0,2,3],[4,5,6],[4,6,7]])
        # Disconnected atlas islands, with unrelated green background between.
        uv=np.array([[.1,.1],[.2,.1],[.2,.2],[.1,.2],[.8,.8],[.9,.8],[.9,.9],[.8,.9]])
        recipient=np.array([[-1,0,.001],[1,0,.001],[1,1,.001],[-1,1,.001]])
        chart=np.array([[0,0],[1,0],[1,1],[0,1]],float);faces=np.array([[0,1,2],[0,2,3]])
        image=np.zeros((32,32,4),dtype='u1');image[:]=[0,255,0,255];image[:10,:10]=[255,0,0,255];image[23:,23:]=[0,0,255,255]
        return positions,uv,triangles,recipient,chart,faces,image

    def test_two_donor_islands_do_not_interpolate_through_background(self):
        args=self.fixture();before=[a.copy() for a in args]
        image,receipt=bake_chart_paint(*args,size=(32,16))
        np.testing.assert_array_equal(image[:,:16,:3],np.broadcast_to([255,0,0],(16,16,3)))
        np.testing.assert_array_equal(image[:,16:,:3],np.broadcast_to([0,0,255],(16,16,3)))
        self.assertEqual(receipt['unfilled_covered_texels'],0);self.assertEqual(receipt['covered_texels'],512)
        self.assertAlmostEqual(receipt['projection_max_mm'],1,places=6)
        for actual,expected in zip(args,before):np.testing.assert_array_equal(actual,expected)

    def test_top_left_orientation_and_explicit_opaque_coverage(self):
        P=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0]],float);UV=P[:,:2].copy();T=np.array([[0,1,2],[0,2,3]])
        source=np.zeros((16,16,4),dtype='u1');source[:8]=[255,0,0,0];source[8:]=[0,0,255,128]
        image,receipt=bake_chart_paint(P,UV,T,P,UV,T,source,size=(16,16))
        self.assertGreater(image[1,8,0],250);self.assertGreater(image[-2,8,2],250)
        self.assertTrue((image[:,:,3]==255).all());self.assertEqual(receipt['source_alpha_min'],0)
        self.assertEqual(receipt['source_nonopaque_samples'],256)

    def test_normalized_texel_centres_match_gpu_sampling(self):
        P=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0]],float);UV=P[:,:2].copy();T=np.array([[0,1,2],[0,2,3]])
        source=np.array([[[255,0,0,255],[0,255,0,255]],[[0,0,255,255],[255,255,255,255]]],dtype='u1')
        image,_=bake_chart_paint(P,UV,T,P,UV,T,source,size=(2,2))
        np.testing.assert_array_equal(image,source)

    def test_overlapping_recipient_charts_fail_closed(self):
        args=list(self.fixture());args[4]=np.tile(np.array([[0,0],[1,0],[1,1],[0,1]],float),(2,1));args[3]=np.vstack([args[3],args[3]+[0,0,.01]])
        args[5]=np.vstack([args[5],args[5]+4])
        with self.assertRaisesRegex(AssertionError,'overlapping'):bake_chart_paint(*args,size=(8,8))

    def test_repeating_shell_charts_pack_without_changing_local_mapping(self):
        uv=np.tile(np.array([[.1,.7],[.9,.7],[.9,.9],[.1,.9]]),(2,1));faces=np.array([[0,1,2],[0,2,3],[4,5,6],[4,6,7]])
        chart,receipt=pack_chart_islands(uv,faces)
        self.assertEqual(receipt['islands'],2);self.assertLess(chart[:4,0].max(),chart[4:,0].min())
        for group in [slice(0,4),slice(4,8)]:
            np.testing.assert_allclose((chart[group]-chart[group].min(0))/np.ptp(chart[group],axis=0),
                                       (uv[group]-uv[group].min(0))/np.ptp(uv[group],axis=0))


if __name__=='__main__':unittest.main()
