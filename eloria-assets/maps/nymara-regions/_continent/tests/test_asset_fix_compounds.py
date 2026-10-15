"""Compounds from the retained asset audit, through Content.load: natural companions kept, pulled sites moved whole, the
footprint datum and member offsets.

A structure's named natural companions (assemblies.COMPANION_WORDS / COMPANION_PAIRS) are retained with it under one
shift and stay prototypes for the ecological scatter. A pulled site (assemblies.PULLED_SITES) is pulled into its
territory as one body in fine steps and, where asked, onto dry ground, keeping its legacy spacing where singles would
converge. A compound with the 'footprints' datum stands at the median of the continent ground less the legacy ground
under all its members. The plan's assembly_member_offsets move one member in the source frame before any bounds.
"""
from pathlib import Path
import json
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import assemblies as A
import content as C
import object_edits as OE
import scene_io as S
import test_retained_attachments as RA

REGION = RA.REGION
SMALL = ([-1., 0., -1.], [1., 2., 1.])


def fixture_document(nodes):
    """nodes: [(name, [x, y, z], (low, high))]: a document whose meshes are bare boxes, one root per placement."""
    document = {'nodes': [{'name': 'Group', 'children': list(range(1, len(nodes) + 1))}], 'meshes': [], 'accessors': []}
    for number, (name, position, (low, high)) in enumerate(nodes):
        document['accessors'].append({'min': list(low), 'max': list(high)})
        document['meshes'].append({'primitives': [{'attributes': {'POSITION': number}}]})
        document['nodes'].append({'name': name, 'translation': list(position), 'mesh': number})
    return document


def load(tmp_path, monkeypatch, nodes, placements, world_class=RA.World, **sections):
    monkeypatch.setattr(OE, 'load_edits', lambda *a, **k: {'version': 1, 'objects': [], 'vegetationAreas': []})
    folder = tmp_path / REGION
    folder.mkdir(parents=True, exist_ok=True)
    S.dump_glb(folder / 'library.glb', fixture_document(nodes), b'')
    (folder / 'library.json').write_text(json.dumps({'placements': placements}))
    x = np.arange(-300., 300.1, 5.)
    gx, gz = np.meshgrid(x, x)
    np.savez(folder / 'foundation-samples.npz', x=x, z=x, height=RA.legacy_height(gx, gz))
    world = world_class(None, **sections)
    template = {'spawnPoints': [{'id': 'arrival', 'default': True, 'position': [0., 0., 0.]}]}
    content = C.Content(world, tmp_path, {REGION: template}, {})
    content.load()
    return world, content


def placed(content, node):
    return content.placement_by_name[(REGION, node)]


def pivot(obj):
    return (np.asarray(obj['low'], float) + np.asarray(obj['high'], float)) * .5


def test_a_structures_named_rocks_are_retained_with_it_and_stay_scatter_prototypes(tmp_path, monkeypatch):
    nodes = [('Landmark_ridge_cave', [40., 0., -20.], ([-4., 0., -2.], [4., 7., 2.])),
             ('Landmark_ridge_cave_EarthRock_0', [45., 0., -18.], SMALL),
             ('Landmark_ridge_cave_EarthRock_1', [35., 0., -18.], SMALL),
             ('Rock_lonely', [-60., 0., 30.], SMALL)]
    placements = [{'node': nodes[0][0], 'kind': 'landmark', 'collides': True, 'position': nodes[0][1]}] + [
        {'node': name, 'kind': 'rock', 'collides': True, 'position': position} for name, position, _ in nodes[1:]]
    world, content = load(tmp_path, monkeypatch, nodes, placements)
    identity = REGION + '.Landmark_ridge_cave'
    cave, rocks = placed(content, 'Landmark_ridge_cave'), [placed(content, n) for n in ('Landmark_ridge_cave_EarthRock_0', 'Landmark_ridge_cave_EarthRock_1')]
    assert {cave.get('assembly'), *(r.get('assembly') for r in rocks)} == {identity}
    # One shift: the rocks keep their legacy offsets from the mouth, not the 0.78 compaction of singles.
    for rock in rocks:
        np.testing.assert_allclose(rock['shift'], cave['shift'])
    np.testing.assert_allclose(pivot(rocks[0])[[0, 2]] - pivot(cave)[[0, 2]], [5., 2.])
    assert (REGION, 'Rock_lonely') not in content.placement_by_name, 'an unrelated rock stays a scatter prototype only'
    prototypes = sorted(p[0]['node'] for p in content.prototypes[REGION])
    assert prototypes == ['Landmark_ridge_cave_EarthRock_0', 'Landmark_ridge_cave_EarthRock_1', 'Rock_lonely']
    # The mouth and its rocks carry their legacy ground as compound footprints instead of a flat round footing.
    assert world.footings == [] and len(world.assembly_footings) == 1
    assert content.assembly_records[identity]['foundationFootprints'] == 3, 'the mouth and both rocks'


class SeamWorld(RA.World):
    """A continent the territory owns west of x = 990; beyond the seam another territory owns the ground."""
    SEAM = 990.

    def owner_at(self, x, z):
        return (np.asarray(x, float) > self.SEAM).astype(int)


class CoastWorld(RA.World):
    """A continent the territory owns everywhere, whose ground drops into the sea east of x = 985."""
    COAST = 985.

    def height_at(self, x, z):
        x = np.asarray(x, float)
        return np.where(x > self.COAST, -3., 5. + .05 * x + .02 * np.asarray(z, float))


SITE = [('Landmark_site_hall', [100., 0., 0.], ([-3., 0., -3.], [3., 6., 3.])),
        ('Landmark_site_tower', [130., 0., 0.], ([-3., 0., -3.], [3., 12., 3.]))]
SITE_PLACEMENTS = [{'node': name, 'kind': 'landmark', 'collides': True, 'position': position} for name, position, _ in SITE]


def use_site(monkeypatch, dry=False):
    identity = REGION + '.test-site'
    monkeypatch.setattr(A, 'PULLED_SITES', {REGION: {identity: (('Landmark_site_hall', 'Landmark_site_tower'), ())}})
    monkeypatch.setattr(A, 'SITE_PULL', {identity: (.02, 160, dry)})
    monkeypatch.setattr(A, 'REFERENCE', dict(A.REFERENCE, **{identity: (None, 'footprints')}))
    return identity


def test_singles_beyond_a_seam_converge_but_a_pulled_site_moves_whole_and_stops_at_the_seam(tmp_path, monkeypatch):
    world, singles = load(tmp_path, monkeypatch, SITE, SITE_PLACEMENTS, world_class=SeamWorld)
    hall, tower = placed(singles, 'Landmark_site_hall'), placed(singles, 'Landmark_site_tower')
    # Legacy 30 m apart, compacted to 23.4 m, the tower pulled back over the seam: the two converge.
    assert np.linalg.norm(pivot(tower)[[0, 2]] - pivot(hall)[[0, 2]]) < 10.
    identity = use_site(monkeypatch)
    world, site = load(tmp_path, monkeypatch, SITE, SITE_PLACEMENTS, world_class=SeamWorld)
    hall, tower = placed(site, 'Landmark_site_hall'), placed(site, 'Landmark_site_tower')
    assert hall['assembly'] == tower['assembly'] == identity
    np.testing.assert_allclose(hall['shift'], tower['shift'])
    np.testing.assert_allclose(pivot(tower)[[0, 2]] - pivot(hall)[[0, 2]], [30., 0.])
    # The pull stops at the first 2 % step that brings every corner inside: within one step of the seam.
    east = float(tower['high'][0])
    assert SeamWorld.SEAM - 2. < east <= SeamWorld.SEAM
    assert site.assembly_records[identity]['datum'] == 'footprints'


def test_a_pulled_site_that_needs_dry_ground_is_pulled_off_the_sea_as_one_body(tmp_path, monkeypatch):
    identity = use_site(monkeypatch, dry=False)
    world, wet = load(tmp_path, monkeypatch, SITE, SITE_PLACEMENTS, world_class=CoastWorld)
    assert pivot(placed(wet, 'Landmark_site_tower'))[0] > CoastWorld.COAST, 'owned ground: no pull without the dry rule'
    use_site(monkeypatch, dry=True)
    world, dry = load(tmp_path, monkeypatch, SITE, SITE_PLACEMENTS, world_class=CoastWorld)
    hall, tower = placed(dry, 'Landmark_site_hall'), placed(dry, 'Landmark_site_tower')
    assert pivot(tower)[0] <= CoastWorld.COAST and pivot(tower)[0] > CoastWorld.COAST - 3.
    np.testing.assert_allclose(pivot(tower)[[0, 2]] - pivot(hall)[[0, 2]], [30., 0.])
    assert hall['assembly'] == identity


class DomeWorld(RA.World):
    """The fixture continent with a 20 m dome over x 915-1065, where three of a compound's five members stand."""

    def height_at(self, x, z):
        x = np.asarray(x, float)
        base = 5. + .05 * x + .02 * np.asarray(z, float)
        return np.where((x >= 915.) & (x <= 1065.), base + 20., base)


def test_a_footprint_datum_stands_the_compound_on_all_its_members_ground(tmp_path, monkeypatch):
    names = ['Landmark_village_' + str(i) for i in range(5)]
    nodes = [(name, [x, 0., 0.], ([-2., 0., -2.], [2., 5., 2.])) for name, x in zip(names, (0., 30., 60., 150., 180.))]
    placements = [{'node': name, 'kind': 'landmark', 'assembly': 'village', 'position': position} for name, position, _ in nodes]
    identity = REGION + '.village'
    monkeypatch.setattr(A, 'REFERENCE', dict(A.REFERENCE, **{identity: ((0., 0.), 'terrain')}))
    world, by_point = load(tmp_path, monkeypatch, nodes, placements, world_class=DomeWorld)
    monkeypatch.setattr(A, 'REFERENCE', dict(A.REFERENCE, **{identity: ((0., 0.), 'footprints')}))
    world, by_footprints = load(tmp_path, monkeypatch, nodes, placements, world_class=DomeWorld)
    point, footprints = placed(by_point, names[0])['shift'], placed(by_footprints, names[0])['shift']
    np.testing.assert_allclose(point[[0, 2]], footprints[[0, 2]])
    # The reference point stands on the plain; three of the five members stand under the dome, so the median lifts it.
    shift = np.asarray(point, float)
    x = np.array([0., 30., 60., 150., 180.])
    plain = 5. + .05 * (x + shift[0]) + .02 * shift[2] - RA.legacy_height(x, 0.)
    assert point[1] == pytest.approx(plain[0], abs=1e-6)
    samples = []
    for centre in x:
        gx, gz = np.meshgrid(np.arange(centre - 2., centre + 2. + 1e-9, 2.), np.arange(-2., 2. + 1e-9, 2.))
        wx = gx + shift[0]
        samples.append((np.where((wx >= 915.) & (wx <= 1065.), 20., 0.) + 5. + .05 * wx + .02 * (gz + shift[2]) - RA.legacy_height(gx, gz)).ravel())
    assert footprints[1] == pytest.approx(float(np.median(np.concatenate(samples))), abs=1e-6)
    assert footprints[1] > point[1] + 10.


def test_a_member_offset_moves_one_member_in_the_source_frame_before_the_compound_is_grouped(tmp_path, monkeypatch):
    offset = [.5, -2.5, 1.]
    world, plain = RA.loaded(tmp_path, monkeypatch, None)
    world, moved = RA.loaded(tmp_path, monkeypatch, None, assembly_member_offsets={REGION + '.yard': {'Landmark_yard_north': offset}})
    identity = REGION + '.yard'
    for content in (plain, moved):
        np.testing.assert_allclose(placed(content, 'Landmark_yard_north')['shift'], placed(content, 'Landmark_yard_south')['shift'])
    relative = lambda content: pivot(placed(content, 'Landmark_yard_north')) - pivot(placed(content, 'Landmark_yard_south'))
    np.testing.assert_allclose(relative(moved) - relative(plain), offset, atol=1e-9)
    assert moved.member_offsets == {(REGION, 'Landmark_yard_north'): offset}
    assert moved.assembly_records[identity]['sourceBounds'] != plain.assembly_records[identity]['sourceBounds']
    # The document on disk keeps the member where the library put it.
    on_disk, _ = S.GR.load(tmp_path / REGION / 'library.glb')
    assert on_disk['nodes'][6]['translation'] == [RA.YARD[0][0], 0., RA.YARD[0][1]]


@pytest.mark.parametrize('section, message', [
    ({REGION + '.nowhere': {'Landmark_yard_north': [0., 1., 0.]}}, 'no compound of that id'),
    ({REGION + '.yard': {'Landmark_cairn': [0., 1., 0.]}}, "'Landmark_cairn' is not a member of grey_moors.yard"),
    ({'nowhere.yard': {'Landmark_yard_north': [0., 1., 0.]}}, "'nowhere.yard' is not an assembly id"),
    ({REGION + '.yard': {'Landmark_yard_north': [0., 'up', 0.]}}, 'must be three finite metres'),
    ({REGION + '.yard': {}}, 'must map member nodes'),
    ([], 'must map assembly ids')])
def test_member_offsets_that_name_nothing_or_no_vector_are_refused(tmp_path, monkeypatch, section, message):
    with pytest.raises(ValueError, match=message):
        RA.loaded(tmp_path, monkeypatch, None, assembly_member_offsets=section)
