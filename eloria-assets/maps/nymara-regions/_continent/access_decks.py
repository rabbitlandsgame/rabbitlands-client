"""Access decks: short walking decks the plan names where two walk surfaces stop short of each other.

A generated deck only knows the ground and the water (bridge_export), and a retained walk stops where its content
stopped. Where the two end metres apart over water or a hole, and neither may grow under the owner's road rules, the
plan's "access_decks" lays a named deck between them: a polyline with a surface height at every point and a width,
built in the geometry stage like the Mirrorhold bank ramps (mirror_access_geometry) and refused unless
"designed_decks" names it under this module. The Lamp Rock causeway, for one, ends 12-13 m of harbour short of the
yard bridge since the roads pass retired the floating deck that crossed it.

Each entry: {"name": "Walk_...", "region", "points": [[x, z], ...], "heights": [metres per point], "width": metres,
"note"}. Every segment climbs at most MAXIMUM_GRADE; the deck's top is the heights interpolated along the polyline.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

import landscape as L
from ferry_export import G, M

PLAN_KEY = 'access_decks'
MODULE = 'access_decks'
MAXIMUM_GRADE = .45
WIDTH_RANGE = (1., 8.)


def entries(plan):
    return list((plan or {}).get(PLAN_KEY) or [])


def validate_access_decks(plan):
    """Every problem with the plan's access decks; empty means valid."""
    value = (plan or {}).get(PLAN_KEY)
    if value is None:
        return []
    if not isinstance(value, list):
        return [f"'{PLAN_KEY}' must be a list of decks"]
    problems, names = [], set()
    regions = {region['id'] for region in (plan or {}).get('regions') or []}
    for index, deck in enumerate(value):
        name = deck.get('name') if isinstance(deck, dict) else None
        where = f'access deck {name!r}' if isinstance(name, str) else f'access deck {index}'
        if not isinstance(deck, dict):
            problems.append(f'{where}: each deck must be an object'); continue
        if not isinstance(name, str) or not name.startswith('Walk_'):
            problems.append(f'{where}: its name must be a Walk_ node name')
        elif name in names:
            problems.append(f'{where}: named twice')
        names.add(name)
        if regions and deck.get('region') not in regions:
            problems.append(f"{where}: unknown region {deck.get('region')!r}")
        points, heights = deck.get('points'), deck.get('heights')
        finite = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
        if not (isinstance(points, list) and len(points) >= 2 and all(isinstance(p, list) and len(p) == 2 and all(finite(v) for v in p) for p in points)):
            problems.append(f'{where}: points must be two or more finite [x, z] pairs'); continue
        if not (isinstance(heights, list) and len(heights) == len(points) and all(finite(v) for v in heights)):
            problems.append(f'{where}: one finite height per point'); continue
        width = deck.get('width')
        if not (finite(width) and WIDTH_RANGE[0] <= width <= WIDTH_RANGE[1]):
            problems.append(f'{where}: width must lie in {list(WIDTH_RANGE)} metres, not {width!r}')
        p, h = np.asarray(points, float), np.asarray(heights, float)
        run = np.linalg.norm(np.diff(p, axis=0), axis=1)
        if (run < .5).any():
            problems.append(f'{where}: consecutive points closer than half a metre')
        elif (np.abs(np.diff(h)) > run * MAXIMUM_GRADE + 1e-9).any():
            problems.append(f'{where}: a segment climbs steeper than {MAXIMUM_GRADE}')
        try:
            L.require_designed_deck(plan, name, MODULE)
        except ValueError as error:
            problems.append(f'{where}: {error}')
    return problems


def deck_mesh(deck, material):
    """The walking surface: the polyline's heights across the whole width, a vertex row at least every metre."""
    points, heights = np.asarray(deck['points'], float), np.asarray(deck['heights'], float)
    run = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
    stations = np.unique(np.concatenate([np.linspace(run[i], run[i + 1], int(np.ceil(run[i + 1] - run[i])) + 1) for i in range(len(run) - 1)]))
    x = np.interp(stations, run, points[:, 0]); z = np.interp(stations, run, points[:, 1]); y = np.interp(stations, run, heights)
    direction = np.gradient(np.c_[x, z], axis=0); direction /= np.maximum(np.linalg.norm(direction, axis=1)[:, None], 1e-9)
    normal = np.c_[-direction[:, 1], direction[:, 0]]
    across = np.linspace(-deck['width'] / 2., deck['width'] / 2., 5)
    px = x[:, None] + normal[:, 0:1] * across[None, :]; pz = z[:, None] + normal[:, 1:2] * across[None, :]
    vertices = np.c_[px.ravel(), np.repeat(y, len(across)), pz.ravel()]
    row, col = np.indices((len(stations) - 1, len(across) - 1)); a = (row * len(across) + col).ravel(); b = a + 1; c = a + len(across); d = c + 1
    # Wind the faces up whichever way the polyline runs.
    for indices in (np.c_[a, c, b, b, c, d].ravel(), np.c_[a, b, c, b, d, c].ravel()):
        tri = vertices[indices.reshape(-1, 3)]; n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        if n[:, 1].min() > 0:
            break
    mesh = M.Mesh(positions=vertices, normals=np.tile([0., 1., 0.], (len(vertices), 1)),
                  uvs=np.c_[np.repeat(stations, len(across)), np.tile(across, len(stations))], indices=indices, material=material)
    mesh.recompute_normals(180)
    grade = np.hypot(n[:, 0], n[:, 2]) / n[:, 1]
    if n[:, 1].min() <= 0 or grade.max() > .65:
        raise ValueError(f"{deck['name']}: access deck triangles exceed the walking grade")
    return mesh, {'name': deck['name'], 'region': deck['region'], 'lengthMetres': round(float(run[-1]), 2),
                  'maximumGrade': round(float(grade.max()), 3), 'heights': [float(v) for v in heights]}


def edge_faces(world, mesh, material):
    """Plain faces down from the deck's outer edges to under the ground or the water bed, below the walking face."""
    faces = mesh.indices.reshape(-1, 3)
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    unique, counts = np.unique(edges, axis=0, return_counts=True)
    top = mesh.positions[unique[counts == 1]].copy(); top[:, :, 1] -= .04
    bottom = top.copy()
    bottom[:, :, 1] = np.minimum(top[:, :, 1] - .3, world.height_at(top[:, :, 0], top[:, :, 2]) - .12)
    vertices = np.stack([top[:, 0], top[:, 1], bottom[:, 0], bottom[:, 1]], axis=1).reshape(-1, 3)
    indices = (np.arange(len(top))[:, None] * 4 + np.array([0, 2, 1, 1, 2, 3])).ravel()
    result = M.Mesh(positions=vertices, normals=np.zeros_like(vertices), uvs=vertices[:, [0, 2]], indices=indices, material=material)
    result.recompute_normals(180)
    return result


def build_access_decks(world, content, path):
    """Write the plan's access decks to ``path``; returns their structure parts and records world.access_decks."""
    plan = getattr(world, 'plan', None) or {}
    problems = validate_access_decks(plan)
    if problems:
        raise ValueError('Access decks: ' + '; '.join(problems))
    from mirror_access_geometry import stone_texture
    builder = G.GltfBuilder('Eloria access decks')
    builder.add_image('access_deck_ashlar', stone_texture())
    builder.add_material(G.Material('access_deck_stone', base_color_texture='access_deck_ashlar', roughness=.95, double_sided=True))
    parts, reports = [], []
    saved=set(getattr(world,'authoring_snapshots',{}))
    for deck in entries(plan):
        if deck['region'] in saved:
            reports.append({'name':deck['name'],'region':deck['region'],
                            'skipped':'saved-authoring-authority'})
            continue
        mesh, report = deck_mesh(deck, 'access_deck_stone')
        builder.add_mesh(deck['name'], mesh, with_tangents=False); root = builder.add_node(G.Node(deck['name'], mesh=deck['name']))
        parts.append({'region': deck['region'], 'node': deck['name'], 'roots': [root], 'bounds': mesh.bounds(), 'segment': [], 'collides': False})
        edge = edge_faces(world, mesh, 'access_deck_stone'); edge_name = deck['name'].replace('Walk_', 'AccessDeck_Edge_', 1)
        builder.add_mesh(edge_name, edge, with_tangents=False); root = builder.add_node(G.Node(edge_name, mesh=edge_name))
        parts.append({'region': deck['region'], 'node': edge_name, 'roots': [root], 'bounds': edge.bounds(), 'segment': [], 'collides': False})
        reports.append(report)
    Path(path).parent.mkdir(parents=True, exist_ok=True); builder.write_glb(str(path))
    world.access_decks = reports
    return parts
