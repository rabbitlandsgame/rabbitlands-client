from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
REG=ROOT/'eloria-assets/maps/nymara-regions'
sys.path[:0]=[str(REG.parent/'four-gates/source'),str(REG/'_toolkit'),str(REG/'_finishing')]
import connector_finish as F
import tidal_approaches as T
import glb_reader as GLB


def test_exact_curve_and_bank_plane_retained_with_only_collinear_station_removal():
    source=np.array([[.5,23.032258,-153.5],[2.,23.,-154.],[3.,20.,-154.],
        [4.,19.,-154.],[6.,17.,-156.],[24.,16.,-158.],[50.,22.,-158.],
        [52.5,23.,-158.5],[52.5,23.,-200.5]])
    road={'stations':source.tolist()};spec={'anchor':[52.5,23.,-200.5],'outward':[0,-1]}
    result=T.centres_for(road,spec)
    np.testing.assert_array_equal(result[0],source[0]);np.testing.assert_array_equal(result[-1],source[-2])
    assert all(any(np.array_equal(p,q) for q in source) for p in result)
    np.testing.assert_array_equal(np.array(road['stations']),source)
    levels=T.deck_levels(result)
    assert levels[0]==source[0,1] and levels[-1]==23. and np.all(levels>=23.)
    for side in (-4.25,4.25):assert T.edges(result,side,spec)[-1,1]==-158.5


def test_short_turning_court_closes_inland_elbow_without_extending_shared_slab():
    spec={'anchor':[52.5,23.,-200.5],'outward':[0,-1]}
    top,body=T.bank_landing(spec)
    ray=F.VerticalRayIndex(F._triangles([top]));under=F.VerticalRayIndex(F._triangles([body]))
    for x,z in ((52.836348405,-155.507857973),(53.085848405,-155.557757973),(49.5,-158.49),(55.5,-158.49)):
        assert ray.top_hit(x,z)==23.
        assert abs(under.top_hit(x,z)-22.2)<1e-8
    assert top.positions[:,2].min()==-158.5
    assert np.max(F._triangles([body])[:,:,1])==23.


def test_span_slab_has_real_thickness_and_outward_sides():
    spec={'anchor':[20.,23.,0.],'outward':[1,0]}
    centres=np.array([[-40.,23.,0.],[-22.,23.,0.]])
    body=T.sides(centres,spec,-4.25,4.25,-.8,0.,'pale_ashlar')
    triangles=F._triangles([body]);norm=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    assert np.all(triangles[:,:,1]>=22.2) and np.all(triangles[:,:,1]<=23.)
    bottom=np.all(np.abs(triangles[:,:,1]-22.2)<1e-8,axis=1)
    assert bottom.any() and np.all(norm[bottom,1]<0)
    for sign in (-1,1):
        side=np.all(np.abs(triangles[:,:,2]-sign*4.25)<1e-8,axis=1)
        assert side.any() and np.all(norm[side,2]*sign>0)


def test_clipped_top_normalization_restores_production_raster_without_moving_geometry():
    mesh=F.M.quad([[0,23,0],[2,23,0],[2,23,2],[0,23,2]],material='cobble_paving')
    # Exact clipping can yield either winding while leaving interpolated
    # vertex normals upward. The production raster reads the actual indices.
    faces=mesh.indices.reshape(-1,3)
    tri=F._triangles([mesh]);down=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])[:,1]<0
    faces[down]=faces[down][:,[0,2,1]]
    faces[0]=faces[0,[0,2,1]]
    positions=mesh.positions.copy();uvs=mesh.uvs.copy()
    before,_=GLB.rasterise(F._triangles([mesh]),8,8,0,2,.25)
    T.upward_top(mesh)
    after,height=GLB.rasterise(F._triangles([mesh]),8,8,0,2,.25)
    assert before.sum()<64 and after.all() and np.all(height==23.)
    np.testing.assert_array_equal(mesh.positions,positions)
    np.testing.assert_array_equal(mesh.uvs,uvs)
