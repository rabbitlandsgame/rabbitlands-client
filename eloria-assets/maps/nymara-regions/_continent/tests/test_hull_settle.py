"""Every decorative hull rests on the actual water or ground; companions follow; assemblies keep XZ."""
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hull_settle as H
from world_layout import World


def world(height=0.):
    obj = World.__new__(World); obj.x0 = obj.z0 = -20.; obj.cell = 2.
    obj.x = obj.z = np.arange(-20., 22., 2.); obj.gx, obj.gz = np.meshgrid(obj.x, obj.z)
    obj.height = np.full(obj.gx.shape, float(height))
    return obj


def rectangle(x0, x1, z0, z1, y):
    a, b, c, d = np.array([[x0, y, z0], [x1, y, z0], [x0, y, z1], [x1, y, z1]], float)
    return np.array([[a, c, b], [b, c, d]])


def prop(region, node, low, high, shift_y, **extra):
    """A placed prop: ``low``/``high`` are its world bounds, ``shift_y`` the Y part of its source-to-world shift."""
    low, high = np.array(low, float), np.array(high, float)
    return {'region': region, 'node': node, 'kind': 'prop', 'shift': np.array([0., shift_y, 0.]), 'low': low, 'high': high,
            'names': {node}, 'source': {}, **extra}


def content(objects):
    return SimpleNamespace(objects=objects, templates={}, mapping={}, bounds_by_name={})


def test_hulls_are_selected_by_name_and_kind_but_not_the_delta_dugouts():
    objects = [prop('crownwater', 'Prop_Boat_Harbour_0', [0, 0, 0], [4, 1, 2], 0.),
               prop('manymouth_delta', 'moored_boat_3', [0, 0, 0], [4, 1, 2], 0.),
               prop('mirrorhold', 'Prop_PierSkiff_1', [0, 0, 0], [4, 1, 2], 0., assembly='mirrorhold.city'),
               dict(prop('manymouth_delta', 'boat_yard_house_05', [0, 0, 0], [4, 1, 2], 0.), kind='building'),
               prop('amberwood', 'Prop_Sack', [0, 0, 0], [1, 1, 1], 0.)]
    assert [o['node'] for o in H.hulls(content(objects))] == ['Prop_Boat_Harbour_0', 'Prop_PierSkiff_1']


def test_a_floating_hull_is_lowered_to_the_water_with_its_rig_and_an_assembly_hull_keeps_its_xz():
    w = world(-3.)
    water = rectangle(-15, 15, -15, 15, 0.)
    # Source hulls carry their authored .6 m draft below the source water level (0).
    boat = prop('amberwood', 'Prop_HarbourPacket', [-3, 7.4, -1], [3, 9, 1], 8.)               # eight metres in the air
    rig = prop('amberwood', 'Prop_PacketRig', [-.5, 8.6, -.2], [.5, 14, .2], 8.)                # standing on the hull
    crate = prop('amberwood', 'Prop_Crate', [-1, 30, 0], [0, 31, 1], 30.)                       # far above: not a companion
    skiff = prop('mirrorhold', 'Prop_PierSkiff_0', [4, -2.6, 4], [8, -1.8, 6], -2., assembly='mirrorhold.city')  # two metres under
    c = content([boat, rig, crate, skiff])
    geometry = {'Prop_HarbourPacket': rectangle(-3, 3, -1, 1, -.6), 'Prop_PierSkiff_0': rectangle(4, 8, 4, 6, -.6)}
    report = H.apply_hull_settle(w, c, triangles=geometry, faces=water)
    assert {r['node']: r['mode'] for r in report['hulls']} == {'Prop_HarbourPacket': 'afloat', 'Prop_PierSkiff_0': 'afloat'}
    assert boat['low'][1] == pytest.approx(-.6) and boat['shift'][1] == pytest.approx(0.)
    assert rig['low'][1] == pytest.approx(.6), 'the rig follows its hull by the same distance'
    assert crate['low'][1] == 30., 'a prop far above the hull is not a companion'
    assert skiff['low'][1] == pytest.approx(-.6) and skiff['shift'][0] == 0. and skiff['shift'][2] == 0.
    assert report['assemblyDeviations'] == 1 and report['afloat'] == 2 and report['maximumMoveMetres'] == pytest.approx(8.)
    assert c.mapping[('amberwood', 'Prop_HarbourPacket')] is boat['shift']
    assert [r['companions'] for r in report['hulls']] == [['Prop_PacketRig'], []]


def test_a_hull_under_dry_ground_is_hauled_up_and_gameplay_links_are_left_alone():
    w = world(4.)
    buried = prop('crownwater', 'Prop_Boat_Harbour_2', [-3, -.2, -1], [3, .8, 1], .4, assembly='crownwater.causeway-city')
    linked = prop('crownwater', 'Prop_PacketBoat_west-quay', [5, 0, 5], [9, 1, 7], 0., source={'landmark': 'west-quay'})
    c = content([buried, linked])
    geometry = {'Prop_Boat_Harbour_2': rectangle(-3, 3, -1, 1, -.6), 'Prop_PacketBoat_west-quay': rectangle(5, 9, 5, 7, -.6)}
    report = H.apply_hull_settle(w, c, triangles=geometry, faces=np.empty((0, 3, 3)))
    assert report['hauledUp'] == 1
    assert report['skipped'] == [{'region': 'crownwater', 'node': 'Prop_PacketBoat_west-quay', 'reason': 'gameplay-linked'}]
    assert buried['low'][1] == pytest.approx(4.015), 'hull bottom rests 15 mm above the raised ground'
    assert linked['low'][1] == 0.


def test_a_hull_against_a_bank_is_moored_at_the_water_line_and_a_hull_over_a_dry_ridge_is_not():
    w = world(-2.)
    w.height[:, w.x >= 2.] = -.4         # a shelf .4 m under the water line along the hull's east end, no water mesh over it
    water = rectangle(-15, 1.9, -15, 15, 0.)
    boat = prop('manymouth_delta', 'MooredMarketBoat_2', [-3, 3.4, -1], [3, 4.4, 1], 4.)
    report = H.apply_hull_settle(w, content([boat]), triangles={'MooredMarketBoat_2': rectangle(-3, 3, -1, 1, -.6)}, faces=water)
    record = report['hulls'][0]
    assert record['mode'] == 'moored' and report['moored'] == 1
    assert boat['low'][1] == pytest.approx(-.6), 'moored at the water line with its authored draft'
    assert record['bankIntrusionMetres'] == pytest.approx(.2, abs=1e-6)
    # The same hull over a ridge that stands 1.5 m proud of the water is hauled up instead.
    w2 = world(-2.); w2.height[:, w2.x >= 2.] = 1.5
    boat2 = prop('manymouth_delta', 'MooredMarketBoat_3', [-3, 3.4, -1], [3, 4.4, 1], 4.)
    report2 = H.apply_hull_settle(w2, content([boat2]), triangles={'MooredMarketBoat_3': rectangle(-3, 3, -1, 1, -.6)}, faces=water)
    assert report2['hulls'][0]['mode'] == 'hauled-up'


def test_a_hull_hauled_up_across_a_slope_moves_to_the_nearest_water_within_reach(monkeypatch):
    w = world(2.5)
    w.height[:, w.x >= -4.] = .5        # the legacy mooring became a step: 2.5 m west of x=-4, .5 m east of it
    w.height[:, w.x >= 1.] = -3.        # water from x=1 eastward
    w.water = {'mask': w.gx >= 1.}
    water = rectangle(1, 15, -15, 15, 0.)
    monkeypatch.setattr(H, 'sample_water_surface', lambda world_, x, z: (np.asarray(x) >= 1., np.zeros(np.shape(x))))
    boat = prop('westhaven', 'Prop_Boat_00', [-7, -.6, -1], [-1, .4, 1], 0., assembly='westhaven.lamp-island')
    lamp = prop('westhaven', 'Prop_Lamp', [-4.4, .3, -.2], [-3.6, 2, .2], 0.)
    c = content([boat, lamp])
    report = H.apply_hull_settle(w, c, triangles={'Prop_Boat_00': rectangle(-7, -1, -1, 1, -.6)}, faces=water)
    record = report['hulls'][0]
    assert record['mode'] == 'afloat' and record['movedXZ'] == pytest.approx([8., 0.]) and report['movedToWater'] == [{'region': 'westhaven', 'node': 'Prop_Boat_00', 'metres': 8.}]
    assert boat['low'][0] == pytest.approx(1.) and boat['low'][1] == pytest.approx(-.6) and boat['shift'][0] == pytest.approx(8.)
    assert lamp['low'][0] == pytest.approx(3.6) and lamp['low'][1] == pytest.approx(.3 - .6 + .6), 'the lamp on the boat moves with it'
    assert report['restingOnSlopes'] == []


def test_no_hulls_records_an_empty_report():
    w = world()
    report = H.apply_hull_settle(w, content([prop('amberwood', 'Prop_Sack', [0, 0, 0], [1, 1, 1], 0.)]))
    assert report['hulls'] == [] and report['afloat'] == 0 and w.hull_settle is report


def test_saved_hull_and_nearby_saved_companion_keep_scene_transforms():
    w = world(-3.)
    water = rectangle(-15, 15, -15, 15, 0.)
    old = prop('amberwood', 'Prop_HarbourPacket', [-3, 7.4, -1], [3, 9, 1], 8.)
    saved_hull = prop('crownwater', 'Prop_Boat_Harbour_0', [4, 7.4, -1], [8, 9, 1], 8.)
    saved_rig = prop('crownwater', 'Prop_PacketRig', [-.5, 8.6, -.2], [.5, 14, .2], 8.)
    c = content([old, saved_hull, saved_rig])
    c.authored_regions = {'crownwater'}
    report = H.apply_hull_settle(
        w, c, triangles={'Prop_HarbourPacket': rectangle(-3, 3, -1, 1, -.6)},
        faces=water)
    assert [entry['node'] for entry in report['hulls']] == ['Prop_HarbourPacket']
    assert report['hulls'][0]['companions'] == []
    assert saved_hull['shift'][1] == saved_rig['shift'][1] == 8.
    assert saved_hull['low'][1] == 7.4 and saved_rig['low'][1] == 8.6
