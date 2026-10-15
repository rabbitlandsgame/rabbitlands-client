"""Visual depth, mask, seam and physical-preservation regressions."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import copy,sys,unittest
import numpy as np

SOURCE=Path(__file__).resolve().parent
sys.path.insert(0,str(SOURCE))
import north_paint as N
from amberwood.mesh import Mesh


def quad(y,material):
    p=np.array([[-5,y,-20],[5,y,-20],[5,y,0],[-5,y,0]],float)
    return Mesh(positions=p,indices=np.array([0,3,2,0,2,1]),normals=np.tile([0,1,0],(4,1)),
        uvs=p[:,[0,2]]*.28,colors=np.column_stack((np.ones((4,3)),[.2,1,1,.2])),material=material)


def fixture():
    root='Terrain_Base'
    names=[root+'_StreamCollar_amethyst-sunmane_'+p for p in ('Turf','Frost')]
    meshes={root:quad(5,'steppe_sward'),names[0]:quad(5,'steppe_sward_ground'),
        names[1]:quad(5,'amethyst_barrens_dust_ground'),'Walk_Bridge':quad(9,'timber_warm')}
    return SimpleNamespace(terrain_meshes=meshes,water_meshes={'Water_Stream':quad(1,'water_lake')},
        streaming_borders=[dict(id=N.CONNECTION,anchor=[0,5,0],outward=[0,1],sceneNodes=list(meshes))],notes=[]),names


class NorthPaintTests(unittest.TestCase):
    def apply(self,build):
        plan={'connections':[dict(id=N.CONNECTION,ends=[dict(region=N.REGION),dict(region='amethyst_barrens')])]}
        with patch.object(N.C.G,'plan',return_value=plan),patch.object(N.C.G,'boundary_sample',side_effect=lambda region,q,**kw:(abs(q[:,1]),np.zeros(len(q)))):
            return N.apply(build)

    def test_ordered_depth_without_physical_or_uv_changes(self):
        b,names=fixture();old=copy.deepcopy(b);supported=N.C.REGIONS
        self.apply(b)
        self.assertEqual(N.C.REGIONS,supported)
        for name in ('Terrain_Base','Walk_Bridge'):
            for attr in ('positions','indices','normals','uvs','colors'):
                np.testing.assert_array_equal(getattr(b.terrain_meshes[name],attr),getattr(old.terrain_meshes[name],attr))
        for attr in ('positions','indices','normals','uvs','colors'):
            np.testing.assert_array_equal(getattr(b.water_meshes['Water_Stream'],attr),getattr(old.water_meshes['Water_Stream'],attr))
        turf=b.terrain_meshes[names[0]]
        np.testing.assert_allclose(turf.positions[:,1],5.002+N.receiving_edge_lift(turf.positions[:,2]))
        for name in (names[1],names[1]+N.SOFT_SUFFIX+'High',names[1]+N.SOFT_SUFFIX+'Low'):
            m=b.terrain_meshes[name]
            # Split vertices inherit their piecewise-linear parent surface.
            self.assertTrue(((m.positions[:,1]>=5.004-1e-8)&(m.positions[:,1]<=5.016+1e-8)).all())
            np.testing.assert_allclose(m.uvs,m.positions[:,[0,2]]*.28)

    def test_exact_shared_strip_palette_and_mask_disjoint_from_soft_part(self):
        b,names=fixture();self.apply(b)
        hard=b.terrain_meshes[names[1]];high=b.terrain_meshes[names[1]+N.SOFT_SUFFIX+'High'];low=b.terrain_meshes[names[1]+N.SOFT_SUFFIX+'Low']
        self.assertEqual(hard.material,'amethyst_barrens_dust_ground')
        for soft in (high,low):
            self.assertEqual(soft.material,'amethyst_barrens_dust_soft_ground')
            self.assertTrue((soft.positions[:,2]<=-3+1e-8).all())
        self.assertTrue((hard.positions[:,2]>=-3-1e-8).all())
        np.testing.assert_allclose(hard.colors[:,3],.2+.8*(hard.positions[:,0]+5)/10)
        def area(m):
            t=m.positions[m.indices].reshape(-1,3,3)
            return abs(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0])[:,1]).sum()/2
        self.assertAlmostEqual(area(hard)+area(high)+area(low),200.)
        self.assertIn(names[1]+N.SOFT_SUFFIX+'High',b.streaming_borders[0]['sceneNodes'])
        self.assertIn(names[1]+N.SOFT_SUFFIX+'Low',b.streaming_borders[0]['sceneNodes'])
        # The old alpha=.5 contour is x=-1.25. Both sets end exactly there;
        # their alpha at the -3m interface is binary, not raw .4/.6 coverage.
        self.assertTrue((high.positions[:,0]>=-1.25-1e-8).all())
        self.assertTrue((low.positions[:,0]<=-1.25+1e-8).all())
        np.testing.assert_array_equal(high.colors[np.isclose(high.positions[:,2],-3),3],1.)
        np.testing.assert_array_equal(low.colors[np.isclose(low.positions[:,2],-3),3],0.)

    def test_fade_has_fractional_coverage_and_remains_bounded(self):
        alpha=np.linspace(0,1,101)
        edge=N.inland_coverage(alpha,np.full(len(alpha),-3.))
        inside=N.inland_coverage(alpha,np.full(len(alpha),-15.))
        np.testing.assert_array_equal(edge,(alpha>=.5).astype(float))
        np.testing.assert_allclose(N.inland_coverage(np.array([.4,.6]),np.array([-3.000001,-3.000001])),[0,1],atol=1e-12)
        self.assertTrue((np.diff(inside)>=0).all())
        self.assertTrue(((inside>=0)&(inside<=.7)).all())
        self.assertGreater(np.count_nonzero((inside>0)&(inside<.7)),30)
        b,names=fixture();self.apply(b);snapshot=copy.deepcopy(b.terrain_meshes)
        self.apply(b)
        for name,m in snapshot.items():
            np.testing.assert_array_equal(m.positions,b.terrain_meshes[name].positions)
            np.testing.assert_array_equal(m.colors,b.terrain_meshes[name].colors)
            np.testing.assert_array_equal(m.indices,b.terrain_meshes[name].indices)

    def test_frozen_helper_registration_restored_after_failure(self):
        b,_=fixture();supported=N.C.REGIONS
        with patch.object(N.C,'apply',side_effect=ValueError('invalid substrate')):
            with self.assertRaisesRegex(ValueError,'invalid substrate'):N.apply(b)
        self.assertEqual(N.C.REGIONS,supported)

    def test_all_paint_layers_match_receiving_edge_and_keep_inland_separation(self):
        b,names=fixture();road='Terrain_Base_StreamCollar_amethyst-sunmane_Road'
        b.terrain_meshes[road]=quad(5,'cobble_paving_ground');b.streaming_borders[0]['sceneNodes'].append(road)
        self.apply(b)
        for name,bias in ((names[0],.002),(names[1],.004),(road,.006)):
            mesh=b.terrain_meshes[name];edge=mesh.positions[:,2]>=-3-1e-8
            np.testing.assert_allclose(mesh.positions[edge,1],5+bias+.012)
        np.testing.assert_array_equal(N.receiving_edge_lift(np.array([0.,-3.,-13.,-20.])),[.012,.012,0.,0.])
        # The same additive field for all layers retains their ordering.
        depth=np.linspace(-20,0,101);lift=N.receiving_edge_lift(depth)
        np.testing.assert_allclose((.016+lift)-(.014+lift),.002,atol=1e-12)


if __name__=='__main__':unittest.main()
