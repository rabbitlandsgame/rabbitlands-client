"""The retained customs arch has its own landing after its crossing moves."""
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import sys
import numpy as np
import pytest

CLIENT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(CLIENT/'eloria-assets/maps/nymara-regions/_toolkit'))
from amberwood.terrain import Terrain,PAVING

def source(name):
    spec=importlib.util.spec_from_file_location('customs_test_'+name,CLIENT/'eloria-assets/maps/four-gates/source'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

LANDING=source('customs_landing');PLAN=source('landscape_plan')


def test_customs_footing_and_seven_lane_join_do_not_depend_on_shared_bridge():
    t=Terrain(-50,120,100,90,cell=1)
    t.height[:]=14.
    LANDING.prepare(t,PLAN,PAVING)
    for x in (-22.,-11.,.5,11.,23.):
        for z in (164.5,172.,179.5):
            assert t.height_at(x,z)==pytest.approx(23)
    for z in np.arange(153.5,186.51):
        for lane in range(-3,4):assert t.height_at(.5+lane,z)==pytest.approx(23)
    assert t.height_at(49,205)==14.


def test_shaping_protection_never_publishes_a_solid_gate_passage():
    gate=SimpleNamespace(node='Gate_South_Outer',collides=False)
    other=SimpleNamespace(node='Other',collides=False)
    build=SimpleNamespace(placements=[gate,other])
    with pytest.raises(RuntimeError):
        with LANDING.retain_footing_during_geography(build):
            assert gate.collides and not other.collides
            raise RuntimeError('builder failure')
    assert not gate.collides and not other.collides
