"""Saved road faces must follow the terrain between vertices as well as at them."""
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import math

import landscape as L
from terrain_export import authored_road_faces, conform_road_faces, encoded_road_faces
from world_layout import triangle_sample


def world(heights,x0=0.,z0=0.):
    grid=np.asarray(heights,float)
    return SimpleNamespace(x0=x0,z0=z0,height=grid,
        height_at=lambda x,z:triangle_sample(grid,x,z,x0,z0))


def attributes(faces):
    x,z=faces[:,:,0],faces[:,:,2]
    return np.stack((2*x-z,3*z+x),axis=2),np.stack((x+z,x-z,x*0+.7,.1*x+.2*z),axis=2)


def signed_area(faces):
    a,b=faces[:,1]-faces[:,0],faces[:,2]-faces[:,0]
    return (a[:,0]*b[:,2]-a[:,2]*b[:,0])*.5


def reference_road_faces(world,snapshot,path):
    """The ribbon exporter before bend repair (client e13cb478), kept verbatim as the straight-road oracle."""
    controls=path['points'];vertices=[];uv=[];colors=[];indices=[];along=0.;lateral_steps=6
    road_override=path['surface'].get('roadOverrides');feather=float(road_override['edgeFeather']) if road_override else 0.
    control_points=[snapshot.continent_point(value['position']) for value in controls]
    control_widths=[float(value['width']) for value in controls]
    points=[];widths=[]
    for index,(start,end) in enumerate(zip(control_points,control_points[1:])):
        count=max(1,int(math.ceil(np.linalg.norm(end[[0,2]]-start[[0,2]]))))
        amount=np.linspace(0.,1.,count+1)[:-1]
        points.extend(start*(1-value)+end*value for value in amount)
        widths.extend(control_widths[index]*(1-value)+control_widths[index+1]*value for value in amount)
    points.append(control_points[-1]);widths.append(control_widths[-1])
    for index,(point,width) in enumerate(zip(points,widths)):
        previous=point if index==0 else points[index-1];following=point if index==len(points)-1 else points[index+1]
        tangent=(following-previous)[[0,2]];tangent/=max(np.linalg.norm(tangent),1e-12);side=np.array([-tangent[1],tangent[0]])
        if index:along+=float(np.linalg.norm(point-points[index-1]))
        for lateral_index in range(lateral_steps+1):
            u=lateral_index/lateral_steps;lateral=width*(.5-u)
            vertex=point.copy();vertex[[0,2]]+=side*lateral
            vertex[1]=float(world.height_at(vertex[0],vertex[2]))+.055
            vertices.append(vertex);uv.append([u*width,along])
            distance_from_edge=1.-abs(u*2.-1.)
            alpha=1. if feather<=0 else float(L.smoothstep(0.,feather,distance_from_edge))
            colors.append([1.,1.,1.,alpha])
        if index<len(points)-1:
            base=index*(lateral_steps+1);following=base+lateral_steps+1
            for lateral_index in range(lateral_steps):
                a=base+lateral_index;b=a+1;c=following+lateral_index;d=c+1
                indices.extend((a,d,b,a,c,d))
    vertices=np.asarray(vertices,float);face_indices=np.asarray(indices).reshape(-1,3)
    return vertices[face_indices],np.asarray(uv)[face_indices],np.asarray(colors)[face_indices]


def road(points,width=5.5,feather=.45):
    """A saved road through rows of [x, z] (optionally with a width) on gently sloping ground."""
    world=SimpleNamespace(height_at=lambda x,z:.01*np.asarray(x)+.02*np.asarray(z)+3.)
    snapshot=SimpleNamespace(continent_point=lambda value:np.asarray(value,float)+np.array([100.,0.,200.]))
    rows=[{'position':[float(p[0]),.03*float(p[0])-.02*float(p[1]),float(p[1])],'width':float(p[2]) if len(p)>2 else width}
          for i,p in enumerate(points)]
    return world,snapshot,{'points':rows,'surface':{'roadOverrides':{'edgeFeather':feather}}}


def uv_mapping(faces,uv):
    """Per triangle (fold, anisotropy) of the ground-from-texture map in the xz plane."""
    e1,e2=faces[:,1,[0,2]]-faces[:,0,[0,2]],faces[:,2,[0,2]]-faces[:,0,[0,2]]
    f1,f2=uv[:,1]-uv[:,0],uv[:,2]-uv[:,0]
    ground=e1[:,0]*e2[:,1]-e1[:,1]*e2[:,0];texture=f1[:,0]*f2[:,1]-f1[:,1]*f2[:,0]
    fold=((ground*texture<0)|((texture==0)&(ground!=0)))&(abs(ground)>1e-9)
    valid=(abs(texture)>1e-12)&(abs(ground)>1e-9)
    jacobian=np.stack((e1,e2),-1)@np.linalg.inv(np.where(valid[:,None,None],np.stack((f1,f2),-1),np.eye(2)))
    sigma=np.linalg.svd(jacobian,compute_uv=False)
    return fold,np.where(valid,sigma[:,0]/sigma[:,1],1.)


def footprint(faces):
    return unary_union([Polygon(f[:,[0,2]]) for f in faces if Polygon(f[:,[0,2]]).area>1e-12])


class RoadConformanceTests(unittest.TestCase):
    def test_observed_float32_slivers_keep_nonzero_footprint_and_all_attributes(self):
        # Captured from Amberwood's saved road to Grey Moors after terrain cuts.
        reversed_face=np.array([[491.7680177688604,41.32873489864652,552.2319822311397],
            [491.0674877166748,41.40855268344756,552.9325113296509],
            [491.30099805196124,41.381946791400885,552.6990019480387]])
        collapsed=np.array([[498.,43.021644287109375,546.],
            [497.93092155456543,42.99129198680537,546.0690779685974],
            [497.930921792984,42.99129200112218,546.069078207016]])
        faces=np.array([reversed_face,collapsed,reversed_face[::-1]])
        uv=np.arange(18,dtype=float).reshape(3,3,2)
        rgba=np.arange(36,dtype=float).reshape(3,3,4)/36.
        saved=[v.copy() for v in (faces,uv,rgba)]
        out,out_uv,out_rgba,report=encoded_road_faces(faces,uv,rgba)
        self.assertEqual(report,{'inputFaces':3,'collapsedFaces':1,'reorientedFaces':2,'outputFaces':2})
        for value,original in zip((out,out_uv,out_rgba),(faces,uv,rgba)):
            np.testing.assert_array_equal(value,original[[0,2]][:,[0,2,1]])
        encoded=out.astype('f4').astype(float)
        self.assertTrue((signed_area(encoded)*signed_area(faces[[0,2]])>0).all())
        # Reordering does not move any represented vertex or erase nonzero area.
        np.testing.assert_array_equal(abs(signed_area(encoded)),abs(signed_area(faces[[0,2]].astype('f4').astype(float))))
        for value,copy in zip((faces,uv,rgba),saved):np.testing.assert_array_equal(value,copy)

    def test_sharp_valley_bend_preserves_footprint_attributes_and_winding(self):
        w=world([[10,10,10],[10,0,10],[10,10,10]])
        original=np.array([[[.2,10,.2],[3.8,10,.3],[.3,10,3.8]],
                           [[3.8,10,.3],[3.7,10,3.7],[.3,10,3.8]]])
        uv,colors=attributes(original); saved=[v.copy() for v in (original,uv,colors,w.height)]
        faces,out_uv,out_colors=conform_road_faces(w,original,uv,colors)
        self.assertGreater(len(faces),len(original))
        self.assertTrue((signed_area(faces)>0).all())
        before=unary_union([Polygon(f[:,[0,2]]) for f in original])
        after=unary_union([Polygon(f[:,[0,2]]) for f in faces])
        self.assertLess(before.symmetric_difference(after).area,1e-12)
        self.assertAlmostEqual(sum(abs(signed_area(faces))),before.area,places=11)
        expected_uv,expected_colors=attributes(faces)
        np.testing.assert_allclose(out_uv,expected_uv,atol=1e-13)
        np.testing.assert_allclose(out_colors,expected_colors,atol=1e-13)
        # Any barycentric interior point of each new face lies on one affine
        # terrain plane. The old ribbon floats over the valley by many metres.
        for weights in ([1/3]*3,[.1,.2,.7],[.6,.3,.1]):
            points=np.einsum('i,tij->tj',weights,faces)
            np.testing.assert_allclose(points[:,1]-w.height_at(points[:,0],points[:,2]),.055,atol=1e-12)
        self.assertGreater(10-w.height_at(2.,2.),9.)
        for value,copy in zip((original,uv,colors,w.height),saved):np.testing.assert_array_equal(value,copy)

    def test_reversed_and_overlapping_faces_keep_separate_attribute_layers(self):
        w=world([[0,4,0],[3,0,3],[0,4,0]],-2.,-2.)
        face=np.array([[-1.8,5,-1.8],[1.7,5,-1.7],[-1.7,5,1.7]])
        original=np.array([face,face[::-1]])
        uv,colors=attributes(original);colors[1,:,3]=.9
        out,_,rgba=conform_road_faces(w,original,uv,colors)
        positive=signed_area(out)>0;negative=signed_area(out)<0
        self.assertTrue(positive.any() and negative.any())
        self.assertAlmostEqual(sum(abs(signed_area(out))),sum(abs(signed_area(original))),places=11)
        np.testing.assert_allclose(rgba[negative,:,3],.9)

    def test_grid_edges_zero_area_and_outside_domain(self):
        w=world([[0,1,2],[1,2,3],[2,3,4]])
        original=np.array([[[0,5,0],[4,5,0],[0,5,4]],[[0,5,0],[2,5,2],[4,5,4]]],float)
        uv,colors=attributes(original)
        out,_,_=conform_road_faces(w,original,uv,colors)
        self.assertAlmostEqual(sum(abs(signed_area(out))),8.,places=12)
        with self.assertRaisesRegex(ValueError,'outside'):
            wrong=original.copy();wrong[0,0,0]=-.001
            conform_road_faces(w,wrong,uv,colors)
        with self.assertRaisesRegex(ValueError,'finite'):
            wrong=original.copy();wrong[0,0,1]=float('nan')
            conform_road_faces(w,wrong,uv,colors)

    def test_single_terrain_triangle_preserves_original_xz_and_attributes(self):
        w=world([[0,2],[3,4]])
        original=np.array([[[.1,99,.1],[.8,99,.1],[.1,99,.8]]])
        uv,colors=attributes(original)
        out,actual_uv,actual_colors=conform_road_faces(w,original,uv,colors)
        np.testing.assert_array_equal(out[:,:,[0,2]],original[:,:,[0,2]])
        np.testing.assert_array_equal(actual_uv,uv);np.testing.assert_array_equal(actual_colors,colors)

    def test_straight_and_gently_curved_roads_keep_their_exact_ribbon(self):
        # Saved samples a centimetre apart and a 2 mm backwards blip, as editor bakes write them,
        # on a straight tapering road; and a gentle 1 m-sampled curve. Neither folds or streaks,
        # so the exporter must emit the old ribbon byte for byte.
        straight=[[0,0],[1,0],[2,0],[2.01,0],[3,0],[4.002,0],[4.,0],[5,0,6.5],[7,0,7.]]
        gentle=[[10*math.sin(a),10-10*math.cos(a)] for a in np.linspace(0.,1.2,13)]
        for points in (straight,gentle):
            args=road(points)
            expected=reference_road_faces(*args);actual=authored_road_faces(*args)
            for value,reference in zip(actual,expected):
                self.assertEqual(value.shape,reference.shape)
                self.assertEqual(value.tobytes(),reference.tobytes())

    def test_sharp_bends_are_continuous_unfolded_and_keep_their_coverage(self):
        # A 72 degree corner sampled 1 cm before its vertex (Suncoil trail-15) and a pair of
        # 45 degree grid corners 3 m apart (A3 trails). Before the fix both fanned the outer
        # side into one texture row (a streak) and folded the inner side back over itself.
        corner=[[float(x),0] for x in range(-10,0)]+[[-.01,0],[0,0]]+[[.309*k,.951*k] for k in range(1,11)]
        grid=([[float(x),0] for x in range(-7,4)]+[[3.71,.71],[4.41,1.41],[5.12,2.12]]+
              [[5.12,2.12+k] for k in range(1,11)])
        straight=reference_road_faces(*road([[0,0],[5,0]]))
        expected={round(float(a),9):float(c) for a,c in zip(straight[1][...,0].ravel()/5.5,straight[2][...,3].ravel())}
        for points in (corner,grid):
            args=road(points)
            old_faces,old_uv,_=reference_road_faces(*args)
            fold,anisotropy=uv_mapping(old_faces,old_uv)
            self.assertTrue(fold.any() and anisotropy.max()>10)
            faces,uv,colors=authored_road_faces(*args)
            fold,anisotropy=uv_mapping(faces,uv)
            self.assertFalse(fold.any())
            self.assertLess(anisotropy.max(),3.5)
            # One uv and alpha per ground vertex: the strips are continuous, with no seam or fan.
            seen={}
            for position,value,colour in zip(faces.reshape(-1,3),uv.reshape(-1,2),colors.reshape(-1,4)):
                row=np.concatenate((value,colour))
                np.testing.assert_array_equal(seen.setdefault(position[[0,2]].round(9).tobytes(),row),row)
            # No two triangles overlap, and the ribbon covers what the old one did (the
            # centreline's half-width buffer, mitred inside and rounded outside) to within 2%.
            cover=footprint(faces);old_cover=footprint(old_faces)
            self.assertAlmostEqual(sum(Polygon(f[:,[0,2]]).area for f in faces),cover.area,places=6)
            self.assertLess(cover.symmetric_difference(old_cover).area,.02*old_cover.area)
            # The lateral alpha profile is the straight road's: alpha is the same function of u.
            profile={round(float(a),9):float(c) for a,c in zip(uv[...,0].ravel()/5.5,colors[...,3].ravel())}
            self.assertEqual(profile,expected)

    def test_bends_near_a_road_end_whose_last_strip_turns_are_unfolded(self):
        # The last 19 m of Coilmere r42-overlook (x, z, width): two 14 degree kinks 16 and 12 m
        # from the end, small kinks after them, and a saved sample 5 cm before the end that
        # turns the last strip by 3.7 degrees. Its section is square to those 5 cm, so the last
        # strip is itself a defect; its bend used to merge with the kinks' and limit all their
        # chords to the 5 cm run-out, leaving 1.4 m2 folded. Checked from both road ends.
        end=[[0.,0.,7.32],[.767,-.039,7.31],[.989,-.05,7.3],[1.986,-.1,7.27],[2.753,-.139,7.25],[2.964,-.205,7.24],
             [3.91,-.502,7.2],[4.647,-.734,7.17],[4.85,-.8,7.26],[5.794,-1.109,7.68],[6.535,-1.351,8.01],
             [6.71,-1.462,8.04],[7.545,-1.993,8.17],[8.212,-2.418,8.28],[8.377,-2.522,8.31],[9.209,-3.049,8.43],
             [9.891,-3.481,8.54],[10.043,-3.568,8.56],[10.896,-4.056,8.7],[11.617,-4.468,8.81],[11.746,-4.541,8.83],
             [12.6,-5.027,8.96],[13.344,-5.452,9.07],[13.453,-5.502,9.09],[14.343,-5.911,9.21],[15.15,-6.282,9.33],
             [15.23,-6.319,9.34],[16.117,-6.726,9.47],[16.956,-7.112,9.6],[17.003,-7.13,9.59]]
        points=[[-float(k),0.,7.32] for k in range(12,0,-1)]+end
        for case in (points,[[-x,-z,w] for x,z,w in points[::-1]]):
            args=road(case)
            old_faces,old_uv,_=reference_road_faces(*args)
            self.assertTrue(uv_mapping(old_faces,old_uv)[0].any())
            faces,uv,colors=authored_road_faces(*args)
            fold,anisotropy=uv_mapping(faces,uv)
            self.assertFalse(fold.any())
            self.assertLess(anisotropy.max(),3.5)
            cover=footprint(faces);old_cover=footprint(old_faces)
            self.assertAlmostEqual(sum(Polygon(f[:,[0,2]]).area for f in faces),cover.area,places=6)
            self.assertLess(cover.symmetric_difference(old_cover).area,.02*old_cover.area)
            # The rebuilt end section stays on the road's end point, square to the road's
            # last metres rather than to its last 5 cm (3.7 degrees away).
            control=np.asarray([args[1].continent_point(row['position']) for row in args[2]['points']])[:,[0,2]]
            tip,towards=(control[-1],control[-1]-control[-4]) if case is points else (control[0],control[0]-control[3])
            rows=np.column_stack((uv.reshape(-1,2),faces.reshape(-1,3)[:,[0,2]]))
            section=rows[rows[:,1]==(rows[:,1].max() if case is points else rows[:,1].min())]
            middle=section[np.isclose(section[:,0],section[:,0].max()/2)][0,2:]
            across=section[section[:,0].argmax(),2:]-section[section[:,0].argmin(),2:]
            self.assertLess(np.linalg.norm(middle-tip),1e-9)
            self.assertLess(abs(float(across@towards))/np.linalg.norm(across)/np.linalg.norm(towards),math.sin(math.radians(1.)))

    def test_near_segment_search_matches_measuring_every_local_segment(self):
        # Bend sections are lengthened against the segments near each station only; with
        # every local segment offered to every probe the ribbon must be byte-identical.
        import terrain_export
        def every(points,start,edge,edge_length,bound,chunk=512):
            row,column=np.divmod(np.arange(len(points)*len(start)),len(start))
            return row,column,np.zeros(len(row)),np.zeros(len(row),bool)
        cases=[[[float(x),0] for x in range(-10,0)]+[[-.01,0],[0,0]]+[[.309*k,.951*k] for k in range(1,11)],
               [[float(x),0] for x in range(-7,4)]+[[3.71,.71],[4.41,1.41],[5.12,2.12]]+[[5.12,2.12+k] for k in range(1,11)],
               [[0,0],[6,0],[6.02,.4],[0,.8],[-3,4]]]
        for points in cases:
            args=road(points)
            fast=authored_road_faces(*args)
            original=terrain_export._segments_near;terrain_export._segments_near=every
            try:slow=authored_road_faces(*args)
            finally:terrain_export._segments_near=original
            for a,b in zip(fast,slow):self.assertEqual(a.tobytes(),b.tobytes())

if __name__=='__main__':unittest.main()
