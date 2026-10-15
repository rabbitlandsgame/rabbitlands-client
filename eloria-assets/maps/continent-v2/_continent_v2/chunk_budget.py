"""Choose a whole-metre phase for the unchanged 96 m chunk lattice.

Scene transforms and served frames never move. Integral sums count every
placement and instanced triangle, including surface triangles, at each possible
integer phase. The best legal phase is deterministic; an impossible budget is
refused rather than increasing the shipping limits.
"""
from __future__ import annotations

import math
import numpy as np

SIZE = 96
PLACEMENTS = 240
TRIANGLES = 450_000


def subtree_triangles(document, root):
    total = 0
    node = document['nodes'][root]
    if 'mesh' in node:
        for primitive in document['meshes'][node['mesh']]['primitives']:
            if primitive.get('mode', 4) != 4:
                raise ValueError('chunk budgeting requires triangle primitives')
            accessor = primitive.get('indices', primitive['attributes']['POSITION'])
            total += document['accessors'][accessor]['count'] // 3
    return total + sum(subtree_triangles(document, child) for child in node.get('children', []))


def choose_origin(points, placements, triangles, frame_corner, *, lattice=-1023):
    points = np.asarray(points, float).reshape(-1, 2)
    placements, triangles = np.asarray(placements, float), np.asarray(triangles, float)
    if (len(points) != len(placements) or len(points) != len(triangles)
            or not np.isfinite(points).all() or not np.isfinite(placements).all()
            or not np.isfinite(triangles).all() or (placements < 0).any() or (triangles < 0).any()):
        raise ValueError('invalid chunk budget samples')
    if not len(points):
        return [lattice - SIZE * max(0, math.ceil((lattice-c)/SIZE)) for c in frame_corner], {}
    cells = np.floor(points).astype(int)
    minimum, maximum = cells.min(axis=0), cells.max(axis=0)
    low, high = minimum-SIZE, maximum+SIZE+1
    shape = tuple(high-low)
    sums=[]
    for weights in (placements, triangles):
        raster=np.zeros(shape, float)
        np.add.at(raster, tuple((cells-low).T), weights)
        sums.append(np.pad(raster.cumsum(0).cumsum(1), ((1,0),(1,0))))
    best=None
    nearest=None
    for x in range(SIZE):
        for z in range(SIZE):
            phase=np.array([int(lattice)+x, int(lattice)+z], dtype=int)
            first=phase + np.floor((minimum-phase)/SIZE).astype(int)*SIZE
            last=phase + np.floor((maximum-phase)/SIZE).astype(int)*SIZE
            xx,zz=np.meshgrid(np.arange(first[0],last[0]+1,SIZE),np.arange(first[1],last[1]+1,SIZE))
            ax,az=(xx-low[0]).ravel(),(zz-low[1]).ravel()
            bx,bz=ax+SIZE,az+SIZE
            values=[s[bx,bz]-s[ax,bz]-s[bx,az]+s[ax,az] for s in sums]
            maxima=[int(round(v.max())) for v in values]
            pressure=max(maxima[0]/PLACEMENTS,maxima[1]/TRIANGLES)
            score=(pressure, float(np.sum((values[0]/PLACEMENTS)**2+(values[1]/TRIANGLES)**2)),x,z)
            if nearest is None or score<nearest[0]: nearest=(score,maxima)
            if maxima[0]>PLACEMENTS or maxima[1]>TRIANGLES: continue
            if best is None or score<best[0]: best=(score,maxima,phase)
    if best is None:
        raise ValueError(f'no legal 96 m chunk phase: best maxima {nearest[1]} exceed {PLACEMENTS}/{TRIANGLES}')
    score,maxima,phase=best
    origin=[int(p-SIZE*max(0,math.ceil((p-c)/SIZE))) for p,c in zip(phase,frame_corner)]
    return origin, {'algorithm':'whole-metre-budget-phase-v1','phaseMetres':[score[2],score[3]],
                    'originMetres':origin,'maximumPlacements':maxima[0],'maximumTriangles':maxima[1],
                    'placementLimit':PLACEMENTS,'triangleLimit':TRIANGLES,'cellMetres':SIZE}
