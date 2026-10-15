"""Atlas-only glTF opaque clamp, with actual frozen/native raster regression."""
from pathlib import Path
import copy,sys
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'eloria-assets/tools'))
import render_region_cartography as C
import atlas_soft_ground as A
from test_region_cartography import quad,textured_scene


def edge_texture(axis):
    pixels=np.zeros((512,512,4),np.uint8);pixels[:,:,3]=255
    if axis==0:
        pixels[:,:256,0]=220;pixels[:,256:,2]=220
    else:
        pixels[:256,:,0]=220;pixels[256:,:,2]=220
    return pixels


def test_gltf_wrap_defaults_mixed_axes_and_unsupported_modes():
    assert C.texture_wrap({'textures':[{}]},0)==(C.REPEAT,C.REPEAT)
    doc={'textures':[{'sampler':0}], 'samplers':[{'wrapS':33071}]}
    assert C.texture_wrap(doc,0)==(C.CLAMP_TO_EDGE,C.REPEAT)
    doc['samplers'][0]['wrapT']=33648
    with pytest.raises(ValueError,match='wrap mode'):C.texture_wrap(doc,0)


@pytest.mark.parametrize('axis',[0,1])
def test_mips_clamp_opposite_edges_and_preserve_repeat_and_alpha(axis):
    texture=edge_texture(axis);texture[:,:,3]=np.arange(512,dtype=np.uint16)[None,:]%256
    wrap=tuple(C.CLAMP_TO_EDGE if i==axis else C.REPEAT for i in range(2))
    clamped=C.mip_albedo(texture,3,wrap)
    repeated=C.mip_albedo(texture,3)
    assert np.array_equal(repeated,C.mip_albedo(texture,3,(C.REPEAT,C.REPEAT)))
    assert np.array_equal(clamped[:,:,3],texture[:,:,3])
    first=clamped[256,0] if axis==0 else clamped[0,256]
    last=clamped[256,-1] if axis==0 else clamped[-1,256]
    opposite=repeated[256,0] if axis==0 else repeated[0,256]
    assert tuple(first[:3])==(220,0,0) and tuple(last[:3])==(0,0,220)
    assert opposite[0]>80 and opposite[2]>80


@pytest.mark.parametrize('axis',[0,1])
@pytest.mark.parametrize('coordinate',[-2.,0.,1.,3.])
def test_actual_specialized_sampler_clamps_at_and_beyond_texture_edges(tmp_path,axis,coordinate):
    scene=C.R.Scene();scene.add_texture('edges',edge_texture(axis))
    material=C.R.RenderMaterial('paint',(1.,1.,1.,1.),albedo='edges',roughness=1.)
    material.atlas_wrap=tuple(C.CLAMP_TO_EDGE if i==axis else C.REPEAT for i in range(2))
    scene.add_material(material);mesh=quad(0.,'paint')
    mesh.uvs[:]=.5;mesh.uvs[:,axis]=coordinate;scene.add_mesh(mesh)
    result=C.raster(scene,np.ones((4,4),np.float32),np.array([0.,0.]),np.array([10.,10.]),
                    (12,12),1,native_cache=tmp_path/'native')
    center=np.asarray(result[0])[6,6]
    if coordinate<=0:assert center[0]>center[2]*5
    else:assert center[2]>center[0]*5
    assert np.asarray(result[2]).min()==255
    assert result[3]['opaqueClampSampler']['baseRasterSha256']==A.sha(C.TOOLKIT/'native/raster.c')


def test_repeat_native_pixels_and_mask_coverage_identical_when_adapter_is_active(tmp_path):
    scene,colors=textured_scene(alpha=True)
    args=(colors,np.array([0.,0.]),np.array([10.,10.]),(32,32),2)
    original=C.raster(scene,*args,native_cache=tmp_path/'native')
    material=C.R.RenderMaterial('unused-clamp',albedo='fine')
    material.atlas_wrap=(C.CLAMP_TO_EDGE,C.CLAMP_TO_EDGE)
    scene.add_material(material)  # Select the adapter, but leave all visible repeats untouched.
    specialized=C.raster(scene,*args,native_cache=tmp_path/'native')
    assert all(np.array_equal(np.asarray(original[i]),np.asarray(specialized[i])) for i in range(3))


def test_minified_material_retains_wrap_without_mutating_geometry_or_textures():
    scene,colors=textured_scene();scene.materials[0].atlas_wrap=(C.CLAMP_TO_EDGE,C.REPEAT)
    before=[x.copy() for arrays in (scene.positions,scene.normals,scene.uvs,scene.indices,scene._texture_images) for x in arrays]
    result=C.minified_scene(scene,np.array([0.,0.]),np.array([10.,10.]),(32,32))
    variants=[m for m in result.materials if '-atlas-mip-' in m.name]
    assert variants and all(m.atlas_wrap==(C.CLAMP_TO_EDGE,C.REPEAT) for m in variants)
    after=[x for arrays in (scene.positions,scene.normals,scene.uvs,scene.indices,scene._texture_images) for x in arrays]
    assert all(np.array_equal(a,b) for a,b in zip(before,after))


@pytest.mark.parametrize('mode,soft',[('MASK',False),('BLEND',False),('OPAQUE',True)])
def test_unsupported_alpha_clamp_combinations_fail_clearly(mode,soft):
    material=C.R.RenderMaterial('unsupported',alpha_mode=mode)
    material.atlas_wrap=(C.CLAMP_TO_EDGE,C.CLAMP_TO_EDGE);material.atlas_soft_ground=soft
    with pytest.raises(ValueError,match='opaque albedo only'):C.clamp_flags(material)


def test_sampler_specialization_rejects_absent_or_duplicate_hooks():
    source=(C.TOOLKIT/'native/raster.c').read_text();shader=(C.ROOT/'godot-client/src/world/soft_ground.gdshader').read_text()
    for hook in (A.SAMPLER_HOOK,A.ALBEDO_HOOK):
        for value in (source.replace(hook,''),source+hook):
            with pytest.raises(ValueError,match='sampler hook'):A.specialize(value,shader)
