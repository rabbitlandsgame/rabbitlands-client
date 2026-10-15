"""Forehead and hairstyle measurements for open source-art headwear."""
from functools import lru_cache
import json
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull, cKDTree

import equipment_authoring as ea

CLIENT = Path(__file__).resolve().parents[2] / 'godot-client'


@lru_cache(maxsize=16)
def hair_triangles(slug):
    """Replay the client's Head-local hairFit and every offered hairstyle.

    Read-only measurements: neither the hairstyle nor the body is rescaled.
    Node transforms are included, just as in the client's socket attachment.
    """
    model = json.loads((CLIENT / 'data/actors/models.json').read_text())['models'][slug]
    rig = ea.load_rig(CLIENT / model['scene'].removeprefix('res://'))
    fit = np.eye(4)
    fit[:3, :3] = np.diag(model.get('hairFit', {}).get('scale', [1., 1., 1.]))
    fit[:3, 3] = model.get('hairFit', {}).get('offset', [0., 0., 0.])
    triangles = []
    for scene in model.get('hairStyles', [])[1:]:
        doc, binary = ea.read_glb(CLIENT / scene.removeprefix('res://'))
        world = ea.global_matrices(doc)
        for index, node in enumerate(doc['nodes']):
            if 'mesh' not in node:
                continue
            transform = world[index] if model.get('hairSkinned') else rig.rest['Head'] @ fit @ world[index]
            for primitive in doc['meshes'][node['mesh']]['primitives']:
                points = ea.accessor_array(doc, binary, primitive['attributes']['POSITION'])
                faces = ea.accessor_array(doc, binary, primitive['indices']).reshape(-1, 3)
                posed = points @ transform[:3, :3].T + transform[:3, 3]
                triangles.append(posed[faces])
    return np.concatenate(triangles) if triangles else np.empty((0, 3, 3))


def band_envelope(rig, rays):
    """A horizontal forehead section, including retained runtime hair.

    The outside contour of the section measures one envelope. Counting ray
    crossings from inside several closed scalp/hair shells would saturate or
    select an inner surface and make a Ssarathi circlet disappear into its hair.
    """
    path = CLIENT / f'assets/actors/native/races/{rig.source_slug}.glb'
    eyes = ea.load_rig(path, ('eyes',))
    height = float(np.quantile(eyes.positions[:, 1], .95)) + .032 * rig.fit_scale
    cut = []
    head_tree = cKDTree(rig._region(['Head']))
    for layer, triangles in enumerate([rig.positions[rig.faces], hair_triangles(rig.source_slug)]):
        for a, b in ((0, 1), (1, 2), (2, 0)):
            start, end = triangles[:, a], triangles[:, b]
            own = (start[:, 1] - height) * (end[:, 1] - height) < 0
            fraction = (height - start[own, 1]) / (end[own, 1] - start[own, 1])
            section_points = start[own] + fraction[:, None] * (end[own] - start[own])
            if layer:
                # Fit around the hair cap. Buns and hanging locks remain
                # visible beyond an open band; wrapping their entire silhouette
                # turns a crown into an oversized hoop.
                distance = head_tree.query(section_points)[0]
                section_points = section_points[distance < .020 * rig.fit_scale]
            cut.append(section_points[:, [0, 2]])
    section = np.concatenate(cut)
    if len(section) < 6:
        raise ValueError(f'No forehead/hair section for {rig.source_slug}')
    hull = ConvexHull(section)
    center = (section.min(axis=0) + section.max(axis=0)) / 2
    target = np.array([center[0], height, center[1]])
    normal, offset = hull.equations[:, :2], hull.equations[:, 2]
    radii = []
    for ray in rays:
        direction = normal @ ray[[0, 2]]
        outward = direction > 1e-8
        distance = -(normal[outward] @ center + offset[outward]) / direction[outward]
        radii.append(float(distance.min()) + .009 * rig.fit_scale)
    return target, np.asarray(radii)
