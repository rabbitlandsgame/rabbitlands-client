"""A restored natural river bank must retain drainage and actual low floors."""
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import ssarathi_bank_support as H

RIVER={'id':'southern_river','width':6.5,'points':[[0.,-100.,2.],[0.,100.,2.]]}
PLAN={'sea_level':0.,'rivers':[RIVER],'lakes':[]}


def field():
    x,z=np.meshgrid(np.arange(-60.,61.,2.),np.arange(-16.,17.,2.))
    natural=np.where(np.abs(x)<6.5,1.,2.5)
    old=np.where(np.abs(x)<6.5,1.,-4.)
    return x,z,old,natural


def test_restore_imported_seabed_to_bank_without_filling_the_river():
    x,z,old,natural=field()
    result=H.bank_field(x,z,old,natural,RIVER,PLAN,[])
    np.testing.assert_array_equal(result[np.abs(x)<6.5],old[np.abs(x)<6.5])
    np.testing.assert_allclose(result[(np.abs(x)>7)&(np.abs(x)<25)],2.5)
    np.testing.assert_array_equal(result[np.abs(x)>48],old[np.abs(x)>48])
    assert np.all(result>=old) and np.all(result<=natural)


def test_actual_bridge_floor_limits_the_bank_across_its_whole_footprint():
    x,z,old,natural=field()
    floor=np.array([[[8,2,-4],[8,2,4],[16,2,-4]],[[16,2,-4],[8,2,4],[16,2,4]]],float)
    result=H.bank_field(x,z,old,natural,RIVER,PLAN,[floor])
    on_floor=(x>=8)&(x<=16)&(np.abs(z)<=4)
    assert np.all(result[on_floor]<=1.94+1e-9)
    assert np.all(result[on_floor]>old[on_floor])


def test_submerged_descent_keeps_existing_support_without_hiding_old_burial():
    x,z,old,natural=field()
    floor=np.array([[[10,.5,-4],[10,-1.5,4],[14,.5,-4]],[[14,.5,-4],[10,-1.5,4],[14,-1.5,4]]],float)
    old[(x>=10)&(x<=14)&(np.abs(z)<=4)]=.75
    result=H.bank_field(x,z,old,natural,RIVER,PLAN,[floor])
    protected=(x>=8)&(x<=16)&(np.abs(z)<=4)
    np.testing.assert_array_equal(result[protected],old[protected])
    assert np.all(result[(x==24)]>old[(x==24)])


def test_occupied_bank_stays_a_low_flood_terrace_below_the_old_hill():
    x,z,old,natural=field()
    natural=np.where(np.abs(x)>12,12.,natural)
    result=H.bank_field(x,z,old,natural,RIVER,PLAN,[])
    assert np.all(result[(x==20)]<3.5)
    assert np.all(result[(x==20)]>2.)
