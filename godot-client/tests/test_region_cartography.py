"""Actual raster regressions for geometry-derived atlas images (CPU only)."""
from pathlib import Path
import json
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'eloria-assets/tools'))
import render_region_cartography as C


def quad(y, material, low=0., high=10.):
    return C.M.Mesh(np.array([[low,y,low],[low,y,high],[high,y,high],[high,y,low]],np.float32),
                    np.tile([0.,1.,0.],(4,1)), np.zeros((4,2)),
                    indices=np.array([0,1,2,0,2,3]),material=material)


def scene(order, alpha=1.):
    s=C.R.Scene()
    s.add_material(C.R.RenderMaterial('ground',(0.,1.,0.,1.),roughness=1.))
    s.add_material(C.R.RenderMaterial('roof',(1.,0.,0.,1.),roughness=1.,alpha_mode='MASK'))
    colors=[]
    for name in order:
        s.add_mesh(quad(2. if name=='roof' else 0.,name))
        c=np.ones((4,4),np.float32)
        if name=='roof':c[:,3]=alpha
        colors.append(c)
    return s,np.vstack(colors)


def render(s, colors):
    return C.raster(s,np.ascontiguousarray(colors),np.array([0.,0.]),np.array([10.,10.]),(32,32),1)


def test_orthographic_roof_wins_independent_of_draw_order():
    one=np.asarray(render(*scene(['ground','roof']))[0])
    two=np.asarray(render(*scene(['roof','ground']))[0])
    assert np.array_equal(one,two)
    assert one[16,16,0] > one[16,16,1]*3


def test_vertex_alpha_reveals_lower_geometry_instead_of_writing_depth():
    image,_,coverage,_=render(*scene(['roof','ground'],alpha=0.))
    center=np.asarray(image)[16,16]
    assert center[1]>center[0]*3
    assert np.asarray(coverage)[16,16]==255


def test_opaque_vertex_rgb_matches_equivalent_material_tint():
    tint=np.array([.34,.41,.20,1.],np.float32)
    def tinted(base,vertex):
        s=C.R.Scene();s.add_material(C.R.RenderMaterial('ground',tuple(base),roughness=.95))
        s.add_mesh(quad(0.,'ground'))
        return np.asarray(render(s,np.tile(vertex,(4,1)).astype(np.float32))[0])
    assert np.array_equal(tinted(tint,np.ones(4)),tinted(np.ones(4),tint))


def test_coverage_is_geometry_derived_and_transparent_alpha_does_not_fill_it():
    s=C.R.Scene();s.add_material(C.R.RenderMaterial('ground',(.4,.4,.4,1.)))
    s.add_mesh(quad(0.,'ground',2.,8.))
    _,rgba,coverage,_=render(s,np.ones((4,4),np.float32))
    assert np.asarray(coverage)[16,16]==255
    assert np.asarray(coverage)[0,0]==0
    assert np.array_equal(np.asarray(rgba)[:,:,3],np.asarray(coverage))
    _,_,empty,_=render(*scene(['roof'],alpha=0.))
    assert not np.asarray(empty).any()


def test_perspective_original_native_entry_point_still_resolves_depth():
    s,_=scene(['ground','roof'])
    image=s.render([5,20,5],[5,0,5],width=32,height=32,lighting=C.LIGHT,shadows=False)
    center=np.asarray(image)[16,16]
    assert center[0]>center[1]*3


def test_scene_instances_keep_nested_transform_and_skip_only_invisible_helpers():
    d={'scene':0,'scenes':[{'nodes':[0]}],'nodes':[
        {'translation':[3,0,-5],'children':[1,2,3]},
        {'name':'Terrain_Actual_StreamCell_a+b','translation':[2,4,1],'mesh':0},
        {'name':'Walk_StreamThreshold_a','mesh':0},
        {'name':'SecondInstance','mesh':0,'matrix':np.eye(4).flatten().tolist()}]}
    nodes=list(C.visible_nodes(d))
    assert len(nodes)==2
    assert nodes[0][0]=='Terrain_Actual_StreamCell_a+b'
    assert np.allclose(nodes[0][2][:3,3],[5,4,-4])
    assert np.allclose(nodes[1][2][:3,3],[3,0,-5])


def test_framing_preserves_exact_declared_pixels_and_north_orientation():
    m={'minimap':{'worldMin':[-120.,-275.],'worldMax':[275.,120.],
                 'imageSize':[395,395],'pixelsPerMetre':1.}}
    low,high,size=C.frame(m)
    assert tuple(low)==(-120.,-275.) and tuple(high)==(275.,120.) and size==(395,395)
    s=C.R.Scene();s.add_material(C.R.RenderMaterial('ground',(.4,.4,.4,1.)))
    s.add_mesh(quad(0.,'ground',1.,3.))
    _,_,coverage,_=render(s,np.ones((4,4),np.float32))
    y,x=np.nonzero(np.asarray(coverage))
    assert x.mean()<16 and y.mean()<16, 'world -Z is image north, +X is east'


def test_common_sea_rgb_matches_actual_water_and_empty_background():
    s=C.R.Scene();s.add_material(C.R.RenderMaterial('water',C.WATER,roughness=1.))
    s.add_mesh(quad(0.,'water',2.,8.))
    image,_,_,_=render(s,np.ones((4,4),np.float32))
    pixels=np.asarray(image)
    assert tuple(pixels[16,16])==tuple(pixels[0,0])==C.water_rgb()


def textured_scene(alpha=False):
    # Deliberately far above atlas Nyquist, over a retained broad color change.
    y,x=np.indices((512,512))
    fine=((x//2+y//2)%2)*96
    broad=48+36*np.sin(x/512*2*np.pi)
    rgb=np.clip(broad+fine,0,255).astype(np.uint8)
    texture=np.repeat(rgb[:,:,None],4,axis=2)
    texture[:,:,3]=np.where((x//37)%2,255,0) if alpha else 255
    s=C.R.Scene();s.add_texture('fine',texture)
    s.add_material(C.R.RenderMaterial('ground',(.8,.6,.3,1.),albedo='fine',
                                      roughness=1.,alpha_mode='MASK' if alpha else 'OPAQUE'))
    mesh=quad(0.,'ground')
    mesh.uvs=mesh.positions[:,[0,2]]*.1875+np.array([.113,.071])
    s.add_mesh(mesh)
    return s,np.ones((4,4),np.float32)


def test_projected_mip_rejects_checker_alias_but_retains_broad_texture(monkeypatch):
    # Compare integrated linear radiance: averaging already tone-mapped bright
    # and dark samples would be a different, nonlinear reference operation.
    monkeypatch.setattr(C.R,'_tonemap',lambda color,*args:
        C.Image.fromarray(np.clip(np.rint(color*255),0,255).astype(np.uint8)))
    s,colors=textured_scene()
    arguments=(s,colors,np.array([0.,0.]),np.array([10.,10.]),(24,24))
    filtered=np.asarray(C.raster(*arguments,2)[0]).astype(float)
    reference=np.asarray(C.raster(*arguments,64,minify=False)[0]).astype(float)
    aliased=np.asarray(C.raster(*arguments,2,minify=False)[0]).astype(float)
    error=np.abs(filtered-reference).mean()
    assert error<2.5
    assert np.abs(aliased-reference).mean()>5
    assert error<np.abs(aliased-reference).mean()*.3
    assert np.ptp(filtered[:,:,0].mean(axis=0))>12


def test_minification_keeps_exact_cutout_coverage_framing_and_input_arrays():
    s,colors=textured_scene(alpha=True)
    original=[array.copy() for bucket in (s.positions,s.normals,s.uvs,s.indices,s.tri_material,s._texture_images) for array in bucket]
    arguments=(s,colors,np.array([-2.,-2.]),np.array([12.,12.]),(36,36))
    before=C.raster(*arguments,2,minify=False)
    after=C.raster(*arguments,2)
    assert np.array_equal(np.asarray(before[2]),np.asarray(after[2]))
    assert before[3]==after[3] and before[0].size==after[0].size
    current=[array for bucket in (s.positions,s.normals,s.uvs,s.indices,s.tri_material,s._texture_images) for array in bucket]
    assert all(np.array_equal(a,b) for a,b in zip(original,current))
    assert len(s.materials)==1 and len(s._texture_images)==1


def test_uv_footprint_handles_rotated_and_mirrored_instances():
    mesh=quad(0.,'unused')
    uv=mesh.positions[:,[0,2]].copy()
    levels=C.projected_mip_levels(mesh.positions,uv,mesh.indices,(.1,.1))
    assert levels.tolist()==[6,6]
    rotated=uv[:,::-1]*np.array([-1.,1.])
    assert np.array_equal(levels,C.projected_mip_levels(mesh.positions,rotated,mesh.indices,(.1,.1)))
    assert not C.projected_mip_levels(mesh.positions,uv*.001,mesh.indices,(.1,.1)).any()


def test_periodic_mip_keeps_alpha_bytes_and_repeat_edge_continuity():
    y,x=np.indices((512,512))
    texture=np.empty((512,512,4),np.uint8)
    texture[:,:,:3]=((x//8)%2*200+20)[:,:,None]
    texture[:,:,3]=(x+y)%256
    filtered=C.mip_albedo(texture,5)
    assert np.array_equal(filtered[:,:,3],texture[:,:,3])
    assert np.max(np.abs(filtered[:,0,:3].astype(int)-filtered[:,-1,:3].astype(int)))<=1
    assert np.array_equal(C.mip_albedo(texture,0),texture)


def test_publication_preserves_framing_and_repeated_output_bytes(tmp_path):
    package=tmp_path/'package';package.mkdir()
    output=tmp_path/'renders';(output/'test').mkdir(parents=True)
    original={'asset':{'glb':'world.glb'},'coordinateTransform':{'serverOrigin':[3,5]},
        'minimap':{'worldMin':[-3,-5],'worldMax':[7,5],'imageSize':[10,10],
                   'pixelsPerMetre':1.,'image':'minimap.webp'},'portals':[{'id':'untouched'}]}
    manifest=package/'world.json';manifest.write_text(json.dumps(original),encoding='utf-8')
    (package/'world.glb').write_bytes(b'geometry fixture')
    for f in ('minimap.webp','cartography.webp'):(output/'test'/f).write_bytes(b'output fixture')
    report={'region':'test','sourceManifest':str(manifest),
        'inputs':{'manifest':C.sha(manifest),'glb':C.sha(package/'world.glb')},
        'outputs':{f:C.sha(output/'test'/f) for f in ('minimap.webp','cartography.webp')},
        'toolSha256':'tool','rendererSourceSha256':'raster','supersample':2,'waterRGB':list(C.water_rgb())}
    C.apply_outputs(report,output)
    published=json.loads(manifest.read_text(encoding='utf-8'))
    assert all(published['minimap'][k]==v for k,v in original['minimap'].items())
    assert published['coordinateTransform']==original['coordinateTransform']
    assert published['portals']==original['portals']
    assert published['minimap']['geometryImage']=='cartography.webp'
    once=manifest.read_bytes()
    report['inputs']['manifest']=C.sha(manifest)
    C.apply_outputs(report,output)
    assert manifest.read_bytes()==once
