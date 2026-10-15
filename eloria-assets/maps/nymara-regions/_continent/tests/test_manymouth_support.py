import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import manymouth_support as M
import assemblies as A


def flat_square(y,extent=4):
    return np.array([[[-extent,y,-extent],[extent,y,extent],[extent,y,-extent]],
                     [[-extent,y,-extent],[-extent,y,extent],[extent,y,extent]]],float)


def test_upper_floor_uses_deck_not_lower_sleepers_or_underside():
    lower=flat_square(1.0);upper=flat_square(3.0);underside=flat_square(5.)[:,::-1]
    points=np.array([[-.25,-.25],[-.25,.25],[.25,-.25],[.25,.25]])
    result=M.upper_floor(points,np.concatenate([lower,upper,underside]))
    assert result==pytest.approx([3.]*4)


def test_bank_has_real_floor_clearance_and_broad_transition():
    x,z=np.meshgrid(np.arange(-44,46,2.),np.arange(-44,46,2.))
    target,weight,core=M.bank_fields(x,z,flat_square(8),apron=6,feather=32)
    assert np.all(target[core]==pytest.approx(7.82))
    assert weight[(abs(x)<=10)&(abs(z)<=4)].min()==1
    assert np.all(weight[(abs(x)>42)|(abs(z)>42)]==0)
    # A 7m bank above a 1m floodplain stays within a comfortable grade.
    height=1*(1-weight)+target*weight
    dz,dx=np.gradient(height,2.)
    assert np.hypot(dx,dz).max()<.40


def test_missing_walk_geometry_is_not_an_implicit_flattening_permission():
    x,z=np.meshgrid(np.arange(-4,6,2.),np.arange(-4,6,2.))
    with pytest.raises(ValueError,match='No actual upper floor'):
        M.bank_fields(x,z,np.empty((0,3,3)))


def test_arch_and_reliquary_keep_linked_secret_access_with_compound():
    for node in M.ARCH_NODES:
        assert A.placement_group(M.REGION,{'node':node,'kind':'landmark'})==M.ARCH
    for node in M.COURT_NODES:
        assert A.placement_group(M.REGION,{'node':node,'kind':'structure'})==M.COURT
    assert A.placement_group(M.REGION,{'node':'temple_stele_00','kind':'prop'}) is None
    assert A.placement_group('amberwood',{'node':'Secret_delta_arch_focus','kind':'landmark'}) is None


def test_adding_secret_geometry_does_not_change_arch_reference():
    assert A.REFERENCE[M.ARCH][0]==(108.96047980956422,-97.68252372878746)
    assert A.REFERENCE[M.TEMPLE][0]==(260.08404918038485,-218.86008126097346)


def test_actual_bank_has_no_competing_legacy_rectangle_footings():
    placements=[{'node':'arch_platform','kind':'landmark'},
                {'node':'SecretAccess_delta_study_school','kind':'structure'}]
    bounds={'arch_platform':([-9,-2,-7],[9,1,7]),
            'SecretAccess_delta_study_school':([15,-3,-20],[25,2,3])}
    groups=A.build_assemblies(M.REGION,placements,bounds,lambda x,z:np.asarray(x)*0)
    assert groups[M.ARCH].footprints==()


def test_temple_quay_uses_actual_floors_even_though_generic_quays_do_not_fill_water():
    assert len(M.TEMPLE_QUAY_FLOORS)==7
    assert 'Landing_temple_quay' in M.TEMPLE_QUAY_FLOORS
    assert all(A.placement_group(M.REGION,{'node':name,'kind':'structure'})==M.TEMPLE_QUAY
               for name in M.TEMPLE_QUAY_FLOORS)
    x,z=np.meshgrid(np.arange(-42,44,2.),np.arange(-42,44,2.))
    target,weight,core=M.bank_fields(x,z,flat_square(10.75),apron=4,feather=32)
    height=13.614*(1-weight)+target*weight
    assert height[core]==pytest.approx(10.57)
    dz,dx=np.gradient(height,2)
    assert np.hypot(dx,dz).max()<.2


def test_south_shore_landing_keeps_its_hamlets_tidal_datum():
    group=A.placement_group(M.REGION,{'node':'Landing_shore_south_hamlet','kind':'structure'})
    assert group==M.REGION+'.south_hamlet'
    assert A.placement_group('amberwood',{'node':'Landing_shore_south_hamlet','kind':'structure'}) is None


def test_quay_bank_composes_continuously_where_neighbor_weights_cross():
    x,z=np.meshgrid(np.arange(-48,50,2.),np.arange(-48,50,2.))
    target,weight,core=M.bank_fields(x,z,flat_square(10.75),apron=4,feather=32)
    old_weight=np.clip(.75+x/160,0,1)
    old_target=np.full(x.shape,13.614)
    composed,combined=M.overlay_bank(old_target,old_weight,target,weight)
    base=np.full(x.shape,12.)
    height=base*(1-combined)+composed*combined
    before=base*(1-old_weight)+old_target*old_weight
    assert height[core]==pytest.approx(10.57)
    assert height[weight==0]==pytest.approx(before[weight==0])
    assert np.all(height<=before+1e-10)  # Existing East floor caps stay clear.
    dz,dx=np.gradient(height,2.)
    assert np.hypot(dx,dz).max()<.20


def test_zero_bank_influence_keeps_absent_and_existing_foundations_exact():
    target=np.array([[4.,13.614],[9.,12.]])
    weight=np.array([[0.,1.],[.5,.7]])
    result,combined=M.overlay_bank(target,weight,np.ones((2,2))*10.57,np.zeros((2,2)))
    assert result==pytest.approx(target)
    assert combined==pytest.approx(weight)


def test_different_porch_levels_share_smooth_ground_between_fixed_aprons():
    x,z=np.meshgrid(np.arange(-48,50,2.),np.arange(-48,50,2.))
    left=flat_square(10.75,2)+[-10,0,0]
    right=flat_square(12.423,2)+[10,0,0]
    target,weight,core=M.bank_fields(x,z,np.concatenate((left,right)),smooth_levels=True)
    assert target[core&(x<0)]==pytest.approx(10.57)
    assert target[core&(x>0)]==pytest.approx(12.243)
    assert target.min()>=10.57-1e-6 and target.max()<=12.243+1e-6
    first=np.hypot(target[:-1,1:]-target[:-1,:-1],target[1:,:-1]-target[:-1,:-1])/2
    second=np.hypot(target[1:,1:]-target[1:,:-1],target[1:,1:]-target[:-1,1:])/2
    assert max(first.max(),second.max())<.35


def test_nearby_stilt_hamlet_has_separate_site_from_arch():
    import json
    plan=json.loads((Path(__file__).resolve().parents[1]/'diagonal-plan.json').read_text())
    arch=np.array(plan['assembly_sites'][M.ARCH]['center'])
    grove=np.array(plan['assembly_sites'][M.REGION+'.deep_grove']['center'])
    assert np.linalg.norm(grove-arch)>50
    assert plan['assembly_sites'][M.REGION+'.deep_grove']['water_level']==0
