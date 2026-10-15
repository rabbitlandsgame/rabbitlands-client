"""Actual atlas raster coverage follows the runtime's UV-locked discard shader."""
from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'eloria-assets/tools'))
import render_region_cartography as C
import atlas_soft_ground as A


def quad(y,name,lo=0.,hi=10.):
    p=np.array([[lo,y,lo],[lo,y,hi],[hi,y,hi],[hi,y,lo]],np.float32)
    return C.M.Mesh(p,np.tile([0.,1.,0.],(4,1)),p[:,[0,2]]*.731+np.array([.173,.379]),
                    indices=np.array([0,1,2,0,2,3]),material=name)


def scene(alpha=.5,order=('ground','soft'),textured=False,vertex_rgb=1.):
    s=C.R.Scene()
    s.add_material(C.R.RenderMaterial('ground',(.04,.7,.04,1.),roughness=1.))
    material=C.R.RenderMaterial('soil_soft_ground',(.7,.04,.04,0. if textured else 1.),roughness=1.,alpha_mode='MASK')
    material.atlas_soft_ground=True
    if textured:
        pixels=np.full((512,512,4),255,np.uint8);pixels[:,:,3]=0
        s.add_texture('softTexture',pixels);material.albedo='softTexture'
    s.add_material(material)
    s.add_material(C.R.RenderMaterial('roof',(.04,.04,.7,1.),roughness=1.))
    colors=[]
    for name in order:
        s.add_mesh(quad({'ground':0.,'soft':1.,'roof':2.}[name],
                        'soil_soft_ground' if name=='soft' else name,
                        3. if name=='roof' else 0.,7. if name=='roof' else 10.))
        c=np.ones((4,4),np.float32)
        if name=='soft':c[:,:3]=vertex_rgb;c[:,3]=alpha
        colors.append(c)
    return s,np.vstack(colors)


def render(s,colors):
    return C.raster(s,colors,np.array([0.,0.]),np.array([10.,10.]),(192,192),1)


@pytest.mark.parametrize('alpha',[0.,.25,.5,.75,1.])
def test_fractional_ground_coverage_uses_vertex_alpha_not_fixed_half_cutoff(alpha):
    image,_,coverage,report=render(*scene(alpha=alpha))
    rgb=np.asarray(image)
    red=float((rgb[:,:,0]>rgb[:,:,1]*2).mean())
    assert abs(red-alpha)<.02
    assert np.asarray(coverage).min()==255
    assert report['softGroundDither']['runtimeShaderSha256']==A.sha(C.ROOT/'godot-client/src/world/soft_ground.gdshader')


def test_opaque_roof_occludes_soft_ground_independent_of_draw_order():
    first=render(*scene(order=('ground','soft','roof')))
    second=render(*scene(order=('roof','soft','ground')))
    assert np.array_equal(np.asarray(first[0]),np.asarray(second[0]))
    center=np.asarray(first[0])[96,96]
    assert center[2]>center[0]*2 and center[2]>center[1]*2


def test_minified_textured_soft_ground_ignores_texture_material_alpha_and_vertex_rgb():
    first=render(*scene(alpha=.37,textured=True,vertex_rgb=0.))
    second=render(*scene(alpha=.37,textured=True,vertex_rgb=1.))
    assert np.array_equal(np.asarray(first[0]),np.asarray(second[0]))
    rgb=np.asarray(first[0]);assert abs(float((rgb[:,:,0]>rgb[:,:,1]*2).mean())-.37)<.02
    s,_=scene(textured=True)
    filtered=C.minified_scene(s,np.array([0.,0.]),np.array([10.,10.]),(192,192))
    variants=[m for m in filtered.materials if '-atlas-mip-' in m.name]
    assert variants and all(m.atlas_soft_ground for m in variants)


def test_ordinary_mask_keeps_texture_alpha_and_fixed_cutoff():
    s,colors=scene(alpha=.75,textured=True)
    s.materials[1].atlas_soft_ground=False
    image,_,coverage,report=render(s,colors)
    rgb=np.asarray(image)
    assert (rgb[:,:,1]>rgb[:,:,0]*2).all()
    assert np.asarray(coverage).min()==255
    assert 'softGroundDither' not in report
    s,colors=scene(alpha=.25)
    s.materials[1].atlas_soft_ground=False
    rgb=np.asarray(render(s,colors)[0])
    assert (rgb[:,:,1]>rgb[:,:,0]*2).all()


def test_plain_atlas_uses_platform_cache_without_loading_shared_binary(monkeypatch,tmp_path):
    monkeypatch.setattr(C.R,'_library',lambda:pytest.fail('atlas loaded shared libraster.so'))
    s,colors=scene(alpha=.75);s.materials[1].atlas_soft_ground=False
    result=C.raster(s,colors,np.array([0.,0.]),np.array([10.,10.]),(32,32),1,
                    native_cache=tmp_path/'native')
    proof=result[3]['nativeRenderer']
    assert proof['baseRasterSha256']==A.sha(C.TOOLKIT/'native/raster.c')
    assert proof['librarySha256'] and 'cacheReceipt' not in proof


def test_ordinary_mask_stays_fixed_cutoff_alongside_dithered_ground():
    s,colors=scene(order=('ground','soft','roof'))
    s.materials[2].alpha_mode='MASK'
    colors[-4:,3]=.49
    hidden=render(s,colors)[0]
    reference=render(*scene())[0]
    assert np.array_equal(np.asarray(hidden),np.asarray(reference))
    colors[-4:,3]=.51
    center=np.asarray(render(s,colors)[0])[96,96]
    assert center[2]>center[0]*2 and center[2]>center[1]*2


def test_requested_compiler_resolves_command_names_and_explicit_paths(monkeypatch,tmp_path):
    compiler=tmp_path/'gcc.exe';compiler.write_bytes(b'fixture compiler')
    monkeypatch.setenv('ELORIA_ATLAS_CC','gcc')
    monkeypatch.setattr(A.shutil,'which',lambda name:str(compiler) if name=='gcc' else None)
    assert A.compiler()==compiler.resolve()
    monkeypatch.setenv('ELORIA_ATLAS_CC',str(compiler))
    assert A.compiler()==compiler.resolve()


def test_specialization_fails_if_hook_or_runtime_semantics_are_ambiguous():
    source=(C.TOOLKIT/'native/raster.c').read_text(encoding='utf-8')
    shader=(C.ROOT/'godot-client/src/world/soft_ground.gdshader').read_text(encoding='utf-8')
    assert A.specialize(source,shader).count('mat->alpha_mode == 3')==1
    for invalid in (source.replace(A.HOOK,''),source+A.HOOK):
        with pytest.raises(ValueError,match='exactly once'):A.specialize(invalid,shader)
    with pytest.raises(ValueError,match='shader'):
        A.specialize(source,shader.replace('COLOR.a < threshold','COLOR.a <= threshold'))


def test_specialized_build_is_reproducible_and_preserves_frozen_inputs(tmp_path):
    source=C.TOOLKIT/'native/raster.c';library=C.TOOLKIT/'native/libraster.so'
    shader=C.ROOT/'godot-client/src/world/soft_ground.gdshader'
    before={p:A.sha(p) for p in (source,library,shader)}
    _,one=A.load(source,shader,tmp_path/'one')
    _,two=A.load(source,shader,tmp_path/'two')
    assert one['specializedSourceSha256']==two['specializedSourceSha256']
    assert one['librarySha256']==two['librarySha256']
    assert all(A.sha(p)==sha for p,sha in before.items())
