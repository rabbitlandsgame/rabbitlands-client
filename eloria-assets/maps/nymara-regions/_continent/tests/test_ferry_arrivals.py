"""Ferry returns follow the fitted quay, independently of territory seed layout."""
from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from crossings import ferry_arrival,global_tile,tile_for


def world_for(landing,forward):
    link={'id':'coast--island'}
    fit={'region':'coast','connections':[link['id']],'landing':list(landing),'forward':list(forward)}
    # The geographic seed lies north while a quay may face any direction.
    world=SimpleNamespace(regions={'coast':{'center':[170,1060]}},
        address=lambda region:([174,244],[588,588]),
        ferry_shore_report={'finalFits':[fit]})
    return world,link


@pytest.mark.parametrize('landing,forward',[
    ([394,1206],[-.9569403357322088,.2902846772544624]),
    ([334,1558],[.9951847266721969,.0980171403295606]),
    ([1058,1576],[-.6343932841636454,.7730104533627371]),
    ([284,1600],[-.6343932841636454,.7730104533627371]),
    ([148,1192],[1.,0.]),
    ([304,1592],[.6343932841636455,.7730104533627369]),
])
def test_six_quay_orientations_keep_all_actor_subcells_on_the_real_bank(landing,forward):
    world,link=world_for(landing,forward)
    tile=ferry_arrival(world,link,'coast',landing)
    assert tile!=tile_for(world,'coast',landing)
    centre=global_tile(world,'coast',tile)
    actor=centre+np.array([[-.25,-.25],[-.25,.25],[.25,-.25],[.25,.25]])
    delta=actor-np.asarray(landing)
    along=delta@np.asarray(forward)
    across=delta@np.array([-forward[1],forward[0]])
    assert np.all((-4<=along)&(along<0))
    assert np.max(abs(across))<1.25


def test_westhaven_east_facing_quay_returns_west_not_toward_northern_seed():
    world,link=world_for([148,1192],[1.,0.])
    tile=ferry_arrival(world,link,'coast',[148,1192])
    assert tile==[149,112]
    np.testing.assert_array_equal(global_tile(world,'coast',tile),[145.5,1191.5])
    assert tile!=[152,115]  # Previously published northwards, outside the quay.


@pytest.mark.parametrize('mutate',[
    lambda fits:fits.clear(),
    lambda fits:fits.append(fits[0].copy()),
    lambda fits:fits[0].update(landing=[148,1192.001]),
    lambda fits:fits[0].update(region='island'),
    lambda fits:fits[0].update(connections=['obsolete-link']),
    lambda fits:fits[0].update(forward=[0,0]),
    lambda fits:fits[0].update(forward=[2,0]),
    lambda fits:fits[0].update(forward=[float('nan'),0]),
])
def test_missing_ambiguous_or_stale_physical_fit_fails_closed(mutate):
    world,link=world_for([148,1192],[1.,0.])
    mutate(world.ferry_shore_report['finalFits'])
    with pytest.raises(ValueError,match='final bank'):
        ferry_arrival(world,link,'coast',[148,1192])
