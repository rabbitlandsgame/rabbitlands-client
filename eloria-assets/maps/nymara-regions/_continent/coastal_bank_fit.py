"""Bounded terrain fitting for prepared coastal bridge bank joins."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Mapping

import numpy as np
import shapely
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, csr_matrix, vstack

from bridge_export import _terrain_interpolation, _terrain_triangles, _world_y_guard


@dataclass(frozen=True)
class BankFitResult:
    claim_id: str
    left_deck_height_metres: float
    right_deck_height_metres: float
    changed_vertices: tuple[Mapping, ...]
    affected_bounds_xz: tuple[tuple[float, float], tuple[float, float]]
    maximum_cut_metres: float
    maximum_fill_metres: float
    minimum_join_gap_metres: float
    maximum_join_gap_metres: float
    worst_bank_xz: tuple[float, float] | None
    maximum_approach_grade: float
    source_local_terrain_sha256: str
    final_local_terrain_sha256: str
    fit_mode: str
    acceptance_authority: bool = True
    clear: bool = True

    def report(self):
        return {
            'claimId': self.claim_id,
            'leftDeckHeightMetres': self.left_deck_height_metres,
            'rightDeckHeightMetres': self.right_deck_height_metres,
            'changedVertices': list(self.changed_vertices),
            'affectedBoundsXZ': [list(v) for v in self.affected_bounds_xz],
            'maximumCutMetres': self.maximum_cut_metres,
            'maximumFillMetres': self.maximum_fill_metres,
            'minimumJoinGapMetres': self.minimum_join_gap_metres,
            'maximumJoinGapMetres': self.maximum_join_gap_metres,
            'worstBankXZ': None if self.worst_bank_xz is None else list(self.worst_bank_xz),
            'maximumApproachGrade': self.maximum_approach_grade,
            'sourceLocalTerrainSha256': self.source_local_terrain_sha256,
            'finalLocalTerrainSha256': self.final_local_terrain_sha256,
            'fitMode': self.fit_mode,
            'acceptanceAuthority': self.acceptance_authority,
            'clear': self.clear,
        }


def height_sha256(height):
    return hashlib.sha256(np.ascontiguousarray(height, dtype='<f8').tobytes()).hexdigest()


def _road_xz(request):
    points = np.asarray(request['roadPoints'], float)
    if points.ndim != 2 or points.shape[0] < 2 or points.shape[1] not in (2, 3):
        raise ValueError('roadPoints must contain at least two XZ or XYZ points')
    return points if points.shape[1] == 2 else points[:, [0, 2]]


def _road_part(points, station_range):
    lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    stations = np.r_[0., np.cumsum(lengths)]
    low, high = sorted(map(float, station_range))
    if low < -1e-8 or high > stations[-1] + 1e-8 or high-low <= 0:
        raise ValueError('approachStationRangeMetres is outside roadPoints')
    cuts = sorted([low, high]+[float(value) for value in stations[1:-1] if low < value < high])
    result = []
    for value in cuts:
        index = min(int(np.searchsorted(stations, value, side='right')-1), len(lengths)-1)
        ratio = (value-stations[index])/max(lengths[index], 1e-12)
        result.append(points[index]+ratio*(points[index+1]-points[index]))
    return np.asarray(result)


def _terrain_cell(world):
    x = np.asarray(world.x, float); z = np.asarray(world.z, float)
    if len(x) < 2 or len(z) < 2:
        raise ValueError('coastal bank fitter requires a square terrain grid')
    dx, dz = np.diff(x), np.diff(z)
    cell = float(dx[0])
    if (cell <= 0 or not np.all(dx == cell) or not np.all(dz == cell)
            or float(dz[0]) != cell or cell != 2.):
        raise ValueError('coastal bank fitter requires the two-metre square continent terrain grid')
    return cell


def _join_samples(world, section, cell):
    section = np.asarray(section, float)
    if section.shape != (2, 3) or not np.isfinite(section).all():
        raise ValueError('joinSection must be a finite encoded 2x3 section')
    a, b = section[:, [0, 2]]
    delta = b-a
    values = [0., 1.]
    for coordinate, origin, step in ((0, world.x0, cell), (1, world.z0, cell)):
        if abs(delta[coordinate]) < 1e-12:
            continue
        low, high = sorted((a[coordinate], b[coordinate]))
        first = math.floor((low-origin)/step)+1
        last = math.ceil((high-origin)/step)
        for index in range(first, last):
            values.append((origin+index*step-a[coordinate])/delta[coordinate])
    # The terrain's two triangles divide each cell on u+v=1.  These are the
    # complete section/grid-diagonal breakpoints, including cell boundaries.
    diagonal_delta = delta.sum()
    if abs(diagonal_delta) >= 1e-12:
        start = a.sum()-world.x0-world.z0
        end = (a+delta).sum()-world.x0-world.z0
        low, high = sorted((start, end))
        first = math.floor(low/cell)+1
        last = math.ceil(high/cell)
        for index in range(first, last):
            values.append((index*cell-start)/diagonal_delta)
    values = sorted({min(1., max(0., float(value))) for value in values if -1e-9 <= value <= 1+1e-9})
    return np.asarray([a+value*delta for value in values])


def _terrain_row(world, xz, node_vars, baseline):
    base, nodes = _terrain_interpolation(world, float(xz[0]), float(xz[1]), baseline)
    row = {}
    for iz, ix, weight in nodes:
        index = node_vars.get((iz, ix))
        if index is not None:
            row[index] = row.get(index, 0.)+weight
    return base, row, tuple((int(iz), int(ix)) for iz, ix, _ in nodes)


def _local_digest(height, nodes):
    digest = hashlib.sha256()
    for iz, ix in sorted(nodes):
        digest.update(np.asarray([iz, ix], dtype='<i4').tobytes())
        digest.update(np.asarray([height[iz, ix]], dtype='<f4').tobytes())
    return digest.hexdigest()


def _request_geometry(world, request, cell):
    points = _road_xz(request)
    half = float(request['halfWidthMetres'])-.5
    if half <= 0:
        raise ValueError('halfWidthMetres must leave a positive 1m-actor centre corridor')
    joins = {}
    corridors = []
    for side in ('left', 'right'):
        bank = request[side]
        joins[side] = _join_samples(world, bank['joinSection'], cell)
        part = _road_part(points, bank['approachStationRangeMetres'])
        corridors.append(shapely.LineString(part).buffer(half, cap_style='flat', join_style='round'))
    corridor = shapely.union_all(corridors)
    low = np.floor((np.asarray(corridor.bounds)[[0, 1]]-[world.x0, world.z0])/cell).astype(int)-1
    high = np.ceil((np.asarray(corridor.bounds)[[2, 3]]-[world.x0, world.z0])/cell).astype(int)+1
    bounds = (max(0, low[0]), min(world.height.shape[1]-1, high[0]),
              max(0, low[1]), min(world.height.shape[0]-1, high[1]))
    triangles = []
    nodes = set()
    for triangle_nodes, triangle in _terrain_triangles(world, bounds):
        polygon = shapely.Polygon(np.asarray(triangle)[:, [0, 2]])
        if polygon.intersection(corridor).area > 0.:
            triangles.append((triangle_nodes, triangle))
            nodes.update(triangle_nodes)
    for samples in joins.values():
        for xz in samples:
            _, interpolation = _terrain_interpolation(world, *xz)
            nodes.update((iz, ix) for iz, ix, _ in interpolation)
    if not triangles:
        raise ValueError('coastal bank request has no exposed actor-centre approach terrain')
    return joins, triangles, nodes


def fit_coastal_banks(world, requests, *, content=None):
    """Fit every request in one LP and apply its terrain mutations atomically."""
    del content  # Retained/wet authority is explicit in pinnedVertexIndices.
    requests = tuple(requests)
    if not requests:
        return ()
    cell = _terrain_cell(world)
    baseline = np.asarray(world.height, float).copy()
    source_sha = height_sha256(baseline)
    geometries = []
    all_nodes = set()
    pinned = set()
    claim_ids = set()
    for request in requests:
        claim = str(request['claimId'])
        if claim in claim_ids:
            raise ValueError(f'duplicate coastal bank claimId: {claim}')
        claim_ids.add(claim)
        if request['sourceHeightSha256'] != source_sha:
            raise ValueError(f'{claim}: sourceHeightSha256 does not match current terrain')
        if 'pinnedVertexIndices' not in request:
            raise ValueError(f'{claim}: pinnedVertexIndices is mandatory water/support authority')
        geometry = _request_geometry(world, request, cell)
        geometries.append(geometry)
        all_nodes.update(geometry[2])
        pinned.update(tuple(map(int, node)) for node in request.get('pinnedVertexIndices', ()))
    # Existing registered solids are immutable even if a caller omitted them.
    pinned.update(node for node in all_nodes if bool(world.solids[node]))
    node_vars = {node: index for index, node in enumerate(sorted(all_nodes))}
    endpoint_offset = len(node_vars)
    endpoints = {(number, side): endpoint_offset+number*2+(side == 'right')
                 for number in range(len(requests)) for side in ('left', 'right')}
    absolute_offset = endpoint_offset+len(requests)*2
    size = absolute_offset+len(node_vars)
    rows, limits, equal, equal_values = [], [], [], []
    guard = _world_y_guard(world)
    contact = .025+guard
    for number, (request, geometry) in enumerate(zip(requests, geometries)):
        joins, triangles, _ = geometry
        grade = min(.64, float(request['maximumApproachGrade']))
        directions = np.linspace(0., 2*math.pi, 32, endpoint=False)
        cap = grade*math.cos(math.pi/32.)
        for triangle_nodes, triangle in triangles:
            xz = np.asarray(triangle)[:, [0, 2]]
            inverse = np.linalg.inv(xz[1:]-xz[0])
            base_heights = np.asarray([baseline[node] for node in triangle_nodes])
            base_gradient = inverse@np.array([base_heights[1]-base_heights[0],
                                              base_heights[2]-base_heights[0]])
            gradient_rows = {}
            for vertex, node in enumerate(triangle_nodes):
                unit = np.zeros(3); unit[vertex] = 1.
                coefficient = inverse@np.array([unit[1]-unit[0], unit[2]-unit[0]])
                gradient_rows[node_vars[node]] = coefficient
            for angle in directions:
                direction = np.array([math.cos(angle), math.sin(angle)])
                rows.append({index: float(direction@coefficient)
                             for index, coefficient in gradient_rows.items()})
                limits.append(cap-float(direction@base_gradient))
        for side in ('left', 'right'):
            endpoint = endpoints[(number, side)]
            for xz in joins[side]:
                base, row, _ = _terrain_row(world, xz, node_vars, baseline)
                row[endpoint] = -1.
                equal.append(row); equal_values.append(-base-contact)
    for node, variable in node_vars.items():
        absolute = absolute_offset+variable
        row = {variable: 1., absolute: -1.}
        rows.append(row); limits.append(0.)
        row = {variable: -1., absolute: -1.}
        rows.append(row); limits.append(0.)
    bounds = []
    for node in sorted(all_nodes):
        owning = [r for r, g in zip(requests, geometries) if node in g[2]]
        cut = min(float(r.get('cutLimitMetres', 4.)) for r in owning)
        fill = min(float(r.get('fillLimitMetres', 3.)) for r in owning)
        bounds.append((0., 0.) if node in pinned else (-cut+guard, fill-guard))
    bounds.extend([(None, None)]*(len(requests)*2)); bounds.extend([(0., None)]*len(node_vars))
    primary = np.zeros(size); primary[absolute_offset:] = 1.
    options = {'primal_feasibility_tolerance': 1e-9, 'dual_feasibility_tolerance': 1e-9}
    def sparse(records):
        row_indices, columns, data = [], [], []
        for row_number, record in enumerate(records):
            for column, value in record.items():
                if value:
                    row_indices.append(row_number); columns.append(column); data.append(value)
        return coo_matrix((data, (row_indices, columns)), shape=(len(records), size)).tocsr()
    matrix = sparse(rows); eq_matrix = sparse(equal)
    solved = linprog(primary, A_ub=matrix, b_ub=np.asarray(limits), A_eq=eq_matrix,
                     b_eq=np.asarray(equal_values), bounds=bounds, method='highs', options=options)
    fit_mode = 'exact-contact'
    if not solved.success and solved.status == 2:
        # A full-width bank can contain preserved terrain at different heights.
        # Keep exact uniform contact as the preferred solution, then fall back
        # to the owner's physical signed-gap band without relaxing any terrain,
        # grade, pin, or atomicity constraint.
        band_rows = list(rows)
        band_limits = list(limits)
        upper = .3-guard
        for row, base in zip(equal, equal_values):
            # equal_values is -terrainBase-contact. Recover the source terrain
            # so the same sparse row enforces lower <= deck-terrain <= upper.
            terrain_base = -float(base)-contact
            band_rows.append(row)
            band_limits.append(-terrain_base-contact)
            band_rows.append({index: -value for index, value in row.items()})
            band_limits.append(terrain_base+upper)
        matrix = sparse(band_rows)
        limits = band_limits
        eq_matrix = coo_matrix((0, size)).tocsr()
        equal_values = np.empty(0)
        solved = linprog(primary, A_ub=matrix, b_ub=np.asarray(limits), bounds=bounds,
                         method='highs', options=options)
        fit_mode = 'signed-gap-band-fallback'
    if not solved.success:
        raise ValueError(f'coastal bank terrain fit is infeasible: {solved.message}')
    # Lexicographic tie-break: retain minimum earthwork, then choose the lowest
    # feasible pair of deck endpoint heights.
    objective = np.zeros(size)
    for endpoint in endpoints.values(): objective[endpoint] = 1.
    if fit_mode == 'exact-contact' and solved.fun <= 1e-12:
        solved2 = solved
    else:
        eq2 = vstack((eq_matrix, csr_matrix(primary[None, :])), format='csr')
        solved2 = linprog(objective, A_ub=matrix, b_ub=np.asarray(limits), A_eq=eq2,
                          b_eq=np.r_[equal_values, float(solved.fun)], bounds=bounds,
                          method='highs', options=options)
    if not solved2.success:
        raise ValueError(f'coastal bank endpoint tie-break is infeasible: {solved2.message}')
    proposed = baseline.copy()
    for node, variable in node_vars.items():
        if node not in pinned:
            proposed[node] += solved2.x[variable]
    source_encoded = baseline.astype(np.float32).astype(float)
    encoded = source_encoded.copy()
    applied = baseline.copy()
    for node, variable in node_vars.items():
        if node in pinned:
            continue
        value = float(np.float32(proposed[node]))
        if value != source_encoded[node]:
            encoded[node] = value
            applied[node] = value
    if any(applied[node] != baseline[node] or encoded[node] != source_encoded[node]
           for node in pinned & all_nodes):
        raise AssertionError('coastal bank fitter changed a pinned terrain vertex')
    results = []
    for number, (request, geometry) in enumerate(zip(requests, geometries)):
        joins, triangles, nodes = geometry
        claim = str(request['claimId'])
        gaps = []
        worst = None
        endpoint_values = {}
        for side in ('left', 'right'):
            deck = float(np.float32(solved2.x[endpoints[(number, side)]]))
            endpoint_values[side] = deck
            for xz in joins[side]:
                terrain, _ = _terrain_interpolation(world, *xz, encoded)
                gap = deck-terrain
                gaps.append(gap)
                if worst is None or abs(gap-.025) > abs(worst[0]-.025):
                    worst = (gap, tuple(map(float, xz)))
        minimum_gap = min(gaps, default=0.)
        maximum_gap = max(gaps, default=0.)
        grades = []
        for triangle_nodes, triangle in triangles:
            xz = np.asarray(triangle)[:, [0, 2]]
            heights = np.asarray([encoded[node] for node in triangle_nodes])
            gradient = np.linalg.inv(xz[1:]-xz[0])@np.array([heights[1]-heights[0], heights[2]-heights[0]])
            grades.append(float(np.linalg.norm(gradient)))
        maximum_grade = max(grades, default=0.)
        deltas = np.asarray([encoded[node]-source_encoded[node] for node in nodes])
        if (minimum_gap < .025 or maximum_gap > .3
                or maximum_grade > float(request['maximumApproachGrade'])
                or -deltas.min(initial=0.) > float(request.get('cutLimitMetres', 4.))
                or deltas.max(initial=0.) > float(request.get('fillLimitMetres', 3.))):
            raise ValueError(f'{claim}: float32 coastal bank fit postcheck failed')
        changes = []
        for iz, ix in sorted(nodes):
            delta = float(encoded[iz, ix]-source_encoded[iz, ix])
            if delta:
                changes.append({'zIndex': iz, 'xIndex': ix, 'before': float(source_encoded[iz, ix]),
                                'after': float(encoded[iz, ix]), 'delta': delta})
        xz = np.asarray([[world.x0+ix*cell, world.z0+iz*cell] for iz, ix in nodes])
        results.append(BankFitResult(
            claim, endpoint_values['left'], endpoint_values['right'], tuple(changes),
            (tuple(map(float, xz.min(axis=0))), tuple(map(float, xz.max(axis=0)))),
            float(max(0., -deltas.min(initial=0.))), float(max(0., deltas.max(initial=0.))),
            minimum_gap, maximum_gap, None if worst is None else worst[1], maximum_grade,
            _local_digest(baseline, nodes), _local_digest(encoded, nodes), fit_mode))
    # No caller-visible mutation happens until every request and float32
    # acceptance check has passed.
    for node in all_nodes:
        world.height[node] = applied[node]
    return tuple(results)
