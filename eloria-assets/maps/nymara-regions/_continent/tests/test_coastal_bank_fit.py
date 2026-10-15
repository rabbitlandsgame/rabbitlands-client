from types import SimpleNamespace

import numpy as np
import pytest

import coastal_bank_fit as F
import audit_continent as A
import build_continent as B


def world():
    height = np.zeros((12, 12), float)
    return SimpleNamespace(height=height, solids=np.zeros_like(height, bool),
                           x0=0., z0=0., x=np.arange(12)*2., z=np.arange(12)*2.)


def request(w, claim='coast-a'):
    return {
        'claimId': claim,
        'roadId': 'road-a',
        'roadPoints': [[0., 10.], [20., 10.]],
        'halfWidthMetres': 2.,
        'left': {'joinSection': [[4., 0., 8.], [4., 0., 12.]],
                 'joinStationMetres': 4., 'approachStationRangeMetres': [0., 3.]},
        'right': {'joinSection': [[16., 0., 8.], [16., 0., 12.]],
                  'joinStationMetres': 16., 'approachStationRangeMetres': [17., 20.]},
        'cutLimitMetres': 4., 'fillLimitMetres': 3., 'maximumApproachGrade': .65,
        'pinnedVertexIndices': (), 'sourceHeightSha256': F.height_sha256(w.height),
    }


def test_flat_banks_need_no_earthwork_and_report_float32_authority():
    w = world()
    w.height[11, 11] = .123456789012345
    outside = w.height[11, 11]
    item = request(w); item['sourceHeightSha256'] = F.height_sha256(w.height)
    result, = F.fit_coastal_banks(w, [item])
    assert result.left_deck_height_metres > .025
    assert result.right_deck_height_metres > .025
    assert result.changed_vertices == ()
    assert .025 <= result.minimum_join_gap_metres <= result.maximum_join_gap_metres < .026
    assert result.maximum_approach_grade == 0.
    assert result.fit_mode == 'exact-contact'
    assert result.report()['fitMode'] == 'exact-contact'
    assert result.report()['acceptanceAuthority'] is True
    assert w.height[11, 11] == outside


def test_every_join_grid_breakpoint_meets_one_deck_height():
    w = world()
    w.height[5, 2] = 1.  # x=4,z=10: section middle, not either endpoint
    item = request(w)
    item['sourceHeightSha256'] = F.height_sha256(w.height)
    result, = F.fit_coastal_banks(w, [item])
    assert result.left_deck_height_metres-w.height[5, 2] >= .025
    assert .025 <= result.minimum_join_gap_metres <= result.maximum_join_gap_metres < .026
    assert any(row['zIndex'] == 5 and row['xIndex'] == 2 for row in result.changed_vertices)


def test_overlapping_requests_share_vertices_in_one_atomic_fit():
    w = world(); w.height[5, 2] = 1.
    first = request(w, 'first'); first['sourceHeightSha256'] = F.height_sha256(w.height)
    first['pinnedVertexIndices'] = ((5, 0),)
    second = request(w, 'second'); second['sourceHeightSha256'] = first['sourceHeightSha256']
    second['pinnedVertexIndices'] = ((5, 0),)
    results = F.fit_coastal_banks(w, [first, second])
    assert [result.claim_id for result in results] == ['first', 'second']
    assert results[0].left_deck_height_metres-w.height[5, 2] >= .025
    assert w.height[5, 0] == 0.


def test_failed_combined_acceptance_leaves_world_unchanged():
    w = world(); w.height[5, 2] = 1.; before = w.height.copy()
    item = request(w); item['sourceHeightSha256'] = F.height_sha256(w.height)
    item['pinnedVertexIndices'] = ((4, 2), (5, 2), (6, 2))
    with pytest.raises(ValueError, match='infeasible'):
        F.fit_coastal_banks(w, [item])
    np.testing.assert_array_equal(w.height, before)


def test_infeasible_uniform_contact_falls_back_to_signed_physical_gap_band():
    w = world()
    w.height[5, 2] = .2
    item = request(w)
    item['sourceHeightSha256'] = F.height_sha256(w.height)
    item['pinnedVertexIndices'] = tuple(np.ndindex(w.height.shape))
    result, = F.fit_coastal_banks(w, [item])
    assert result.fit_mode == 'signed-gap-band-fallback'
    assert .025 <= result.minimum_join_gap_metres
    assert result.maximum_join_gap_metres <= .3
    assert result.maximum_join_gap_metres-result.minimum_join_gap_metres > .15
    assert result.changed_vertices == ()


def test_non_infeasibility_solver_failure_does_not_enter_fallback(monkeypatch):
    w = world()
    item = request(w)
    calls = []

    def fail(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(success=False, status=4, message='solver numerical failure')

    monkeypatch.setattr(F, 'linprog', fail)
    with pytest.raises(ValueError, match='solver numerical failure'):
        F.fit_coastal_banks(w, [item])
    assert len(calls) == 1


def test_fitter_is_a_shaping_and_export_certificate_source():
    for sources in (A.SHAPING_SOURCES, A.EXPORT_SOURCES, B.SHAPING_SOURCES, B.EXPORT_SOURCES):
        assert 'coastal_bank_fit.py' in sources
        assert 'coastal_prepare.py' in sources
    assert set(A.SHAPING_SOURCES) == set(B.SHAPING_SOURCES)
    assert set(A.EXPORT_SOURCES) == set(B.EXPORT_SOURCES)


def test_road_part_keeps_interior_vertices_in_station_order():
    part = F._road_part(np.array([[0., 0.], [4., 0.], [4., 4.]]), [1., 7.])
    np.testing.assert_allclose(part, [[1., 0.], [4., 0.], [4., 3.]])
