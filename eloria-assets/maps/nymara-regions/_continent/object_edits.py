"""Authored object edits: continent-edits.json beside diagonal-plan.json.

The continent plan editor writes this file; composition applies it while the
objects are loaded, before footings, routing and scatter read them, so every
later stage sees the edited continent:

- ``remove`` drops a retained placement before assembly grouping, the
  RETIRED_GREY_SPANS pattern. Linked records re-anchor to the nearest other
  object, as they do for any retired root.
- ``transform`` rotates (``yawDegrees``) and scales (``scale``) the placement's
  source root about its own base centre in the region's library document, then
  adds ``translate`` to its shift after the territory pull. A moved object is
  grounded again at its new position; ``translate[1]`` stays as a raise above
  that ground. Linked records follow the translation only, never the rotation.
- ``add`` places a copy of any placeable asset in a territory library (a
  building, prop, landmark, tree, rock or undergrowth prototype; ``source`` is
  ``<library region>_<node>_WorldPlacement``) at ``pivot + translate``. The
  copy belongs to the territory it stands in: its subtree, with a tree's
  foliage companions, is cloned into that territory's document, and when the
  asset comes from another territory's library its meshes, accessors, buffer
  data, materials, textures and images are transplanted with it, because
  support stages read geometry from ``documents[obj['region']]``. Yaw and
  scale sit on the clone's roots. The copy is grounded at its target, gets a
  footing and collision identity (natural kinds get neither, like scatter),
  and carries no linked records.
- ``vegetationAreas`` clear or thin ecological scatter inside a polygon. The
  decision is made per candidate after every random draw and counter, so no
  tree, outcrop or undergrowth outside the areas moves or is renumbered.

Objects are named by their continent.glb root, ``<region>_<node>_WorldPlacement``.
A move, yaw and scale about the object's base centre is the matrix
``edit_matrix``; the editor draws pending edits with the same matrix.

Run ``python object_edits.py --library <library>`` to check the file against
the certified libraries without composing.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
EDITS_PATH = HERE / 'continent-edits.json'
EMPTY = {'version': 1, 'objects': [], 'vegetationAreas': []}
SCATTER_KINDS = ('tree', 'rock', 'undergrowth')
HULL_WORDS = ('boat', 'skiff', 'dugout', 'canoe', 'punt', 'lateen', 'packet', 'tender', 'barge', 'raft', 'wherry')
UNCOPYABLE_KINDS = ('foliage', 'road', 'path', 'terrain', 'ground')
UNCOPYABLE_PREFIXES = ('Road_', 'Path_', 'Track_', 'Soil_', 'Survey_', 'Walk_Road_', 'Walk_Path_', 'Walk_Track_', 'Walk_Survey_')
# Modules whose node-name literals are group membership, not lookups.
NOT_LOOKUPS = {'assemblies.py', 'object_edits.py'}
GENERIC_PREFIX_MATCHES = 25


def load_edits(path=EDITS_PATH):
    if not Path(path).exists():
        return copy.deepcopy(EMPTY)
    doc = json.loads(Path(path).read_text(encoding='utf-8'))
    if doc.get('version') != 1:
        raise ValueError(f'{path}: object edits must be version 1')
    return doc


def parse_root(name, regions):
    """(region, node) of a continent.glb root name."""
    base = name[:-len('_WorldPlacement')] if name.endswith('_WorldPlacement') else name
    if base.endswith('_WorldPlacement'):
        raise ValueError(f'{name}: bridge, ferry and access geometry is generated, not a placement')
    for region in sorted(regions, key=len, reverse=True):
        if base.startswith(region + '_'):
            return region, base[len(region) + 1:]
    raise ValueError(f'{name}: root name has no territory prefix')


def edit_matrix(pivot, yaw_degrees=0., scale=1., translate=(0., 0., 0.)):
    """p' = pivot + translate + Ry(yaw) * scale * (p - pivot), Ry right-handed about +Y."""
    import numpy as np
    angle = math.radians(yaw_degrees)
    c, s = math.cos(angle) * scale, math.sin(angle) * scale
    m = np.eye(4)
    m[0, 0], m[0, 2], m[2, 0], m[2, 2], m[1, 1] = c, s, -s, c, scale
    pivot = np.asarray(pivot, float)
    m[:3, 3] = pivot + np.asarray(translate, float) - m[:3, :3] @ pivot
    return m


def thin_hash(x, z):
    """Uniform [0, 1) from metre-rounded (x, z); bit-identical to the editor's thinHash."""
    h = ((math.floor(x + .5) * 73856093) ^ (math.floor(z + .5) * 19349663)) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x5BD1E995) & 0xFFFFFFFF
    h ^= h >> 15
    return h / 4294967296.


def inside_polygon(x, z, polygon):
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, zi = polygon[i]
        xj, zj = polygon[j]
        if (zi > z) != (zj > z) and x < (xj - xi) * (z - zi) / (zj - zi) + xi:
            inside = not inside
        j = i
    return inside


def base_pivot(low, high):
    return [(low[0] + high[0]) * .5, low[1], (low[2] + high[2]) * .5]


def has_companions(placement):
    return placement.get('kind') == 'tree' or placement['node'].endswith('_Wood')


def copy_refusal(placement):
    """Why a library placement cannot be placed as a new asset, or None."""
    node, kind = placement['node'], placement.get('kind', 'prop')
    if kind in UNCOPYABLE_KINDS or node.startswith(UNCOPYABLE_PREFIXES):
        return 'roads, paths, ground and attached foliage are not placeable assets'
    if any(word in node.lower() for word in HULL_WORDS):
        return 'boats are settled on water by hull_settle and cannot be copied'
    return None


class ObjectEdits:
    def __init__(self, doc, regions):
        self.doc = doc
        self.regions = list(regions)
        self.removed = {}
        self.transforms = {}
        self.copies = []
        for edit in doc.get('objects', []):
            action = edit.get('action')
            if action == 'add':
                region, node = parse_root(edit['source'], self.regions)
                self.copies.append((region, node, edit))
            elif action == 'remove':
                region, node = parse_root(edit['root'], self.regions)
                self.removed.setdefault(region, {})[node] = edit['root']
            elif action == 'transform':
                region, node = parse_root(edit['root'], self.regions)
                self.transforms[(region, node)] = edit
            else:
                raise ValueError(f'Unknown object edit action {action!r}')
        self.areas = doc.get('vegetationAreas', [])
        for area in self.areas:
            if area.get('mode') not in ('clear', 'thin') or len(area.get('polygon', [])) < 3:
                raise ValueError(f"{area.get('id')}: a vegetation area needs a mode and at least three corners")
            if not set(area.get('kinds', [])) <= set(SCATTER_KINDS):
                raise ValueError(f"{area.get('id')}: vegetation kinds must be among {SCATTER_KINDS}")
        self.report = {'removed': [], 'transformed': [], 'added': [],
                       'scatterSkipped': {kind: 0 for kind in SCATTER_KINDS}, 'areas': len(self.areas)}
        self.pending_removals = {(region, node) for region, nodes in self.removed.items() for node in nodes}
        # Source-frame rotation/scale applied to each transformed root; a copy starts from the original.
        self.turned = {}
        # (library region, territory) -> {(kind, index): index in the territory document} for transplanted resources.
        self.transplants = {}
        self.removed_placements = {}

    def __bool__(self):
        return bool(self.removed or self.transforms or self.copies or self.areas)

    def exclude_authored_region(self, region):
        """Drop legacy corrections after a scene assumes full object authority."""
        self.removed.pop(region, None)
        self.transforms = {key:value for key,value in self.transforms.items() if key[0] != region}
        self.pending_removals = {(r, node) for r, nodes in self.removed.items() for node in nodes}

    # -- during Content.load, per region ------------------------------------
    def filter_placements(self, region, placements):
        names = self.removed.get(region, {})
        kept = []
        for placement in placements:
            if placement['node'] in names:
                self.pending_removals.discard((region, placement['node']))
                self.report['removed'].append(names[placement['node']])
                # A removed placement is still an asset: removing it and placing a copy elsewhere is allowed.
                self.removed_placements[(region, placement['node'])] = placement
            else:
                kept.append(placement)
        return kept

    def prepare_document(self, region, document, body, placements):
        """Rotate/scale transformed roots in a private copy of the document."""
        edits = [(node, edit) for (r, node), edit in self.transforms.items()
                 if r == region and (edit.get('yawDegrees', 0) or edit.get('scale', 1) != 1)]
        if not edits:
            return document
        import numpy as np
        import scene_io as S
        document = dict(document)
        document['nodes'] = [dict(node) for node in document['nodes']]
        matrices, parents = S.GR.hierarchy(document)
        by_name = {n.get('name'): i for i, n in enumerate(document['nodes'])}
        by_placement = {p['node']: p for p in placements}
        for node, edit in edits:
            placement = by_placement.get(node)
            if placement is None or node not in by_name:
                raise ValueError(f"{edit['root']}: no retained placement {node} in {region}")
            if has_companions(placement):
                raise ValueError(f"{edit['root']}: trees and _Wood placements carry separate foliage roots; they can move but not rotate or scale")
            index = by_name[node]
            low, high = S.subtree_bounds(document, body, index, matrices)
            k = edit_matrix(base_pivot(low, high), edit.get('yawDegrees', 0), edit.get('scale', 1))
            parent = matrices[parents[index]] if index in parents else np.eye(4)
            local = np.linalg.inv(parent) @ k @ parent @ S.GR.local_matrix(document['nodes'][index])
            set_matrix(document['nodes'][index], local)
            self.turned[(region, node)] = k
            if 'position' in placement:
                placement['position'] = (k @ np.r_[np.asarray(placement['position'], float), 1.])[:3].tolist()
        return document

    def translation(self, region, node):
        edit = self.transforms.get((region, node))
        if edit is None:
            return None
        if edit.get('yawDegrees', 0) or edit.get('scale', 1) != 1 or any(edit.get('translate', (0, 0, 0))):
            self.report['transformed'].append(edit['root'])
        return edit if any(edit.get('translate', (0, 0, 0))) else None

    def apply_translation(self, world, region, edit, assembly_id, old_xz, new_xz, source_ground):
        """New (new_xz, shift, target_ground) for a moved, non-assembly placement."""
        import numpy as np
        tx, ty, tz = (float(v) for v in edit['translate'])
        if assembly_id:
            raise ValueError(f"{edit['root']} belongs to the connected assembly {assembly_id}; move the whole "
                             f"assembly with diagonal-plan.json assembly_sites.{assembly_id}.translation")
        new_xz = np.asarray(new_xz, float) + [tx, tz]
        if int(world.owner_at(*new_xz)) != world.ids.index(region):
            raise ValueError(f"{edit['root']}: the move takes it outside {region}")
        target_ground = ground_rule(region, source_ground, float(world.height_at(*new_xz)))
        shift = np.array([new_xz[0] - old_xz[0], target_ground - source_ground + ty, new_xz[1] - old_xz[1]])
        return new_xz, shift, target_ground

    def check_loaded(self, content):
        missing = sorted(self.removed[r][n] for r, n in self.pending_removals)
        if missing:
            raise ValueError(f'Object edits remove placements that do not exist: {missing}')
        unknown = [edit['root'] for (region, node), edit in self.transforms.items()
                   if (region, node) not in content.placement_by_name]
        if unknown:
            raise ValueError(f'Object edits transform placements that are not retained: {unknown}')

    # -- after every region is loaded -----------------------------------------
    def add_copies(self, world, content):
        import numpy as np
        import assemblies as A
        import scene_io as S
        documents = {}   # territory -> (private document copy, growing body)

        def private(region):
            if region not in documents:
                doc, body = content.documents[region]
                doc = dict(doc)
                for kind in ('nodes', 'meshes', 'accessors', 'bufferViews', 'materials', 'textures', 'images', 'samplers'):
                    doc[kind] = list(doc.get(kind, []))
                documents[region] = (doc, bytearray(body))
            return documents[region]

        for region, node, edit in self.copies:
            target = np.asarray(edit['pivot'], float) + np.asarray(edit['translate'], float)
            owner = world.ids[int(world.owner_at(target[0], target[2]))]
            if owner in getattr(content, 'authored_regions', ()):
                # Full scene object authority includes deletion.  A legacy add
                # whose target lies in that territory stays suppressed even
                # when its source library belongs to a neighbour.
                continue
            src_doc, src_body = content.documents[region]
            by_name = {n.get('name'): i for i, n in enumerate(src_doc['nodes'])}
            placement = next((p for p in content.metadata[region]['placements'] if p['node'] == node),
                             self.removed_placements.get((region, node)))
            if placement is None or node not in by_name:
                raise ValueError(f"{edit['id']}: {edit['source']} is not an asset in the {region} library")
            why = copy_refusal(placement)
            if why:
                raise ValueError(f"{edit['id']}: {why}")
            index = by_name[node]
            roots = [index, *companion_roots(content, region, placement, index, by_name)]
            matrices = S.GR.hierarchy(src_doc)[0]
            doc, body = private(owner)
            if owner == region:
                new_roots = [clone_subtree(doc, r) for r in roots]
            else:
                cache = self.transplants.setdefault((region, owner), {})
                new_roots = [transplant_subtree(doc, body, src_doc, src_body, r, cache) for r in roots]
            # Each clone is a root carrying its source's world matrix as authored (a transform edit on the
            # source is undone), then the copy's own yaw and scale about the base centre of all its roots.
            undo = np.linalg.inv(self.turned[(region, node)]) if (region, node) in self.turned else np.eye(4)
            for r, n in zip(roots, new_roots):
                set_matrix(doc['nodes'][n], undo @ matrices[r])
            low, high = subtree_bounds_all(S, doc, body, new_roots)
            k = edit_matrix(base_pivot(low, high), edit.get('yawDegrees', 0), edit.get('scale', 1))
            for n in new_roots:
                set_matrix(doc['nodes'][n], k @ S.GR.local_matrix(doc['nodes'][n]))
            low, high = subtree_bounds_all(S, doc, body, new_roots)
            ground = ground_rule(owner, float(low[1]), float(world.height_at(target[0], target[2])))
            centre = (np.asarray(low) + np.asarray(high)) * .5
            shift = np.array([target[0] - centre[0], ground - low[1] + float(edit['translate'][1]), target[2] - centre[2]])
            prefix = 'EditCopy_' + re.sub(r'[^A-Za-z0-9]+', '', edit['id']) + '_'
            kind = placement.get('kind', 'prop')
            natural = kind in A.NATURE
            obj = {'region': owner, 'index': new_roots[0], 'indices': new_roots, 'shift': shift,
                   'low': np.asarray(low) + shift, 'high': np.asarray(high) + shift, 'kind': kind,
                   'node': prefix + node, 'nodePrefix': prefix, 'names': set(),
                   'collides': bool(placement.get('collides', False)) and not natural,
                   'walk': bool(placement.get('walk_surface', False)),
                   'targetGround': ground, 'objectEdit': edit['id'], 'librarySource': [region, node]}
            content.objects.append(obj)
            if not natural:
                radius = float(np.linalg.norm((high - low)[[0, 2]]) * .5)
                footprint = min(38, max(2, radius * .72))
                world.foundation(target[[0, 2]], footprint, ground, feather=max(12, footprint * .7),
                                 obstacle=obj['collides'] and not obj['walk'])
            self.report['added'].append({'id': edit['id'], 'source': edit['source'], 'territory': owner,
                                         'at': [round(float(v), 2) for v in target]})
        for region, (doc, body) in documents.items():
            if doc.get('buffers'):
                doc['buffers'] = [dict(doc['buffers'][0], byteLength=len(body))]
            content.documents[region] = (doc, bytes(body))

    # -- during ecological_scatter --------------------------------------------
    def skips_scatter(self, kind, x, z):
        for area in self.areas:
            if kind not in area['kinds'] or not inside_polygon(x, z, area['polygon']):
                continue
            if area['mode'] == 'clear' or thin_hash(x, z) >= area.get('keep', 0):
                self.report['scatterSkipped'][kind] += 1
                return True
        return False


def ground_rule(region, source_ground, ground):
    # Content.load's rule for where a retained placement stands.
    if region in ('manymouth_delta', 'crownwater') and source_ground < 1.5 and ground < 1.5:
        return max(-1., min(ground, 1.))
    return max(.8, ground)


def set_matrix(node, matrix):
    for key in ('translation', 'rotation', 'scale'):
        node.pop(key, None)
    node['matrix'] = [float(v) for v in matrix.T.reshape(-1)]


def subtree_bounds_all(S, document, body, roots):
    """Exact vertex bounds of several subtrees.

    scene_io.subtree_bounds transforms each accessor's min/max box, which for a tilted node
    reaches well below the real mesh (a Whitehorn serac copy floated 8 m). A placed copy stands
    on its actual lowest vertex, the base the editor draws."""
    import numpy as np
    matrices = S.GR.hierarchy(document)[0]
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for index in S.descendants(document, roots):
        node = document['nodes'][index]
        if 'mesh' not in node:
            continue
        m = matrices[index]
        for primitive in document['meshes'][node['mesh']]['primitives']:
            position = document['accessors'][primitive['attributes']['POSITION']]
            if 'bufferView' in position:
                points = S.GR.accessor(document, body, primitive['attributes']['POSITION']).astype(float)
            else:   # a data-less accessor (fixtures) only has its box
                a, b = position['min'], position['max']
                points = np.array([[x, y, z] for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])], float)
            if not len(points):
                continue
            world = points @ m[:3, :3].T + m[:3, 3]
            lo, hi = np.minimum(lo, world.min(0)), np.maximum(hi, world.max(0))
    if not np.isfinite(lo).all():
        return S.subtree_bounds(document, body, roots[0], matrices)
    return lo, hi


def companion_roots(content, region, placement, index, by_name):
    """A tree's (or _Wood placement's) foliage roots: Content.load's record when it kept one, otherwise the
    foliage placements at the same authored position, the rule load uses (it skips some nodes, such as
    March_ trees, before recording theirs)."""
    import numpy as np
    known = content.companions.get((region, index))
    if known is not None or not has_companions(placement) or 'position' not in placement:
        return list(known or [])
    key = tuple(np.round(placement['position'], 4))
    return [by_name[p['node']] for p in content.metadata[region]['placements']
            if p.get('kind') == 'foliage' and p['node'] in by_name and 'position' in p
            and tuple(np.round(p['position'], 4)) == key]


def transplant_subtree(document, body, source, source_body, root, cache):
    """Append root's subtree from another document with every resource it uses; returns the new root index.

    ``document``'s resource lists must be private copies and ``body`` a bytearray; appended buffer data is
    4-byte aligned. ``cache`` maps (kind, source index) to the transplanted index, so resources shared by
    several copies from one library travel once."""
    def transfer(kind, index):
        key = (kind, index)
        if key in cache:
            return cache[key]
        old = source[kind][index]
        out = copy.deepcopy(old)
        if kind == 'bufferViews':
            start = old.get('byteOffset', 0)
            body.extend(bytes((-len(body)) % 4))
            out.update(buffer=0, byteOffset=len(body))
            body.extend(source_body[start:start + old['byteLength']])
        elif kind == 'accessors':
            if 'sparse' in old:
                raise ValueError('sparse accessors cannot be transplanted')
            if 'bufferView' in old:
                out['bufferView'] = transfer('bufferViews', old['bufferView'])
        elif kind == 'meshes':
            for part in out['primitives']:
                part['attributes'] = {k: transfer('accessors', v) for k, v in part['attributes'].items()}
                if 'indices' in part:
                    part['indices'] = transfer('accessors', part['indices'])
                if 'material' in part:
                    part['material'] = transfer('materials', part['material'])
                if 'targets' in part:
                    part['targets'] = [{k: transfer('accessors', v) for k, v in t.items()} for t in part['targets']]
        elif kind == 'materials':
            def textures(item):
                if isinstance(item, dict):
                    for k, v in item.items():
                        if k.endswith('Texture') and isinstance(v, dict) and 'index' in v:
                            v['index'] = transfer('textures', v['index'])
                        else:
                            textures(v)
                elif isinstance(item, list):
                    for v in item:
                        textures(v)
            textures(out)
        elif kind == 'textures':
            if 'source' in out:
                out['source'] = transfer('images', out['source'])
            if 'sampler' in out:
                out['sampler'] = transfer('samplers', out['sampler'])
        elif kind == 'images':
            if 'bufferView' not in old:
                raise ValueError('library images must be embedded')
            out['bufferView'] = transfer('bufferViews', old['bufferView'])
        document[kind].append(out)
        cache[key] = len(document[kind]) - 1
        return cache[key]

    def visit(index):
        clone = copy.deepcopy(source['nodes'][index])
        for key in ('skin', 'camera'):
            clone.pop(key, None)
        new = len(document['nodes'])
        document['nodes'].append(clone)
        if 'mesh' in clone:
            clone['mesh'] = transfer('meshes', clone['mesh'])
        children = [visit(child) for child in source['nodes'][index].get('children', [])]
        if children:
            clone['children'] = children
        else:
            clone.pop('children', None)
        return new

    return visit(root)


def clone_subtree(document, root):
    """Append a copy of root's subtree (nodes only; meshes are shared); returns the new root index."""
    mapping = {}

    def visit(index):
        clone = copy.deepcopy(document['nodes'][index])
        new = len(document['nodes'])
        document['nodes'].append(clone)
        mapping[index] = new
        clone['children'] = [visit(child) for child in document['nodes'][index].get('children', [])]
        if not clone['children']:
            clone.pop('children')
        return new

    return visit(root)


# -- catalogue for the editor and the pre-compose check ------------------------
def module_literals(continent):
    literals = {}
    for path in sorted(Path(continent).glob('*.py')):
        if path.name in NOT_LOOKUPS:
            continue
        for literal in re.findall(r"""['"]([A-Za-z][A-Za-z0-9_\-]{3,})['"]""", path.read_text(encoding='utf-8')):
            literals.setdefault(literal, set()).add(path.name)
    return literals


def catalogue(library, continent=HERE, regions=None):
    """Per region, per retained placement: what an edit may do with it and why not."""
    import sys
    if str(continent) not in sys.path:
        sys.path.insert(0, str(continent))
    import assemblies as A
    library = Path(library)
    regions = regions or sorted(p.name for p in library.iterdir() if (p / 'library.json').exists())
    literals = module_literals(continent)
    by_region = {region: json.loads((library / region / 'library.json').read_text(encoding='utf-8'))['placements']
                 for region in regions}
    all_names = [p['node'] for placements in by_region.values() for p in placements]
    # A prefix literal is a lookup only when it is specific: not a family shared by several
    # territories (Walk_, Prop_, Landmark_Gate...) and matching a handful of nodes continent-wide.
    families = {}
    for region, placements in by_region.items():
        for p in placements:
            parts = p['node'].split('_')
            for depth in range(1, len(parts)):
                families.setdefault('_'.join(parts[:depth]) + '_', set()).add(region)
    prefixes = {lit: mods for lit, mods in literals.items() if lit.endswith('_')
                and len(families.get(lit, ())) < 3
                and 0 < sum(n.startswith(lit) for n in all_names) <= GENERIC_PREFIX_MATCHES}
    out = {}
    for region in regions:
        placements = by_region[region]
        entries = {}
        for p in placements:
            node = p['node']
            refs = set(literals.get(node, set()))
            for lit, mods in prefixes.items():
                if node.startswith(lit):
                    refs |= mods
            kind = p.get('kind', 'prop')
            entries[node] = {
                'kind': kind, 'landmark': p.get('landmark'), 'collides': bool(p.get('collides')),
                'walk': bool(p.get('walk_surface')), 'assembly': A.placement_group(region, p, placements),
                'companions': has_companions(p), 'hull': any(w in node.lower() for w in HULL_WORDS),
                'natural': kind in A.NATURE, 'referencedBy': sorted(refs), 'copyRefusal': copy_refusal(p)}
        out[region] = entries
    return out


def problems(edits, catalogue_by_region):
    """Human-readable reasons an edit would fail or break linked content."""
    regions = list(catalogue_by_region)
    found = []
    for edit in edits.get('objects', []):
        action = edit['action']
        name = edit['source'] if action == 'add' else edit['root']
        label = edit.get('id', name)
        try:
            region, node = parse_root(name, regions)
        except ValueError as error:
            found.append(str(error))
            continue
        entry = catalogue_by_region.get(region, {}).get(node)
        if action == 'add':
            if entry is None:
                found.append(f'{label}: {node} is not an asset in the {region} library')
            elif entry['copyRefusal']:
                found.append(f"{label}: {entry['copyRefusal']}")
            continue
        if entry is None:
            found.append(f'{label}: {node} is not a retained placement in {region} (scatter, terrain or generated geometry)')
            continue
        if entry['referencedBy']:
            found.append(f"{label}: {node} is looked up by name in {', '.join(entry['referencedBy'])}; editing it breaks that stage")
        if entry['natural'] and not entry['landmark'] and not entry['assembly']:
            found.append(f'{label}: {node} is a natural prototype, not a retained object')
        if action == 'transform':
            moved = any(edit.get('translate', (0, 0, 0)))
            turned = edit.get('yawDegrees', 0) or edit.get('scale', 1) != 1
            if moved and entry['assembly']:
                found.append(f"{label}: part of assembly {entry['assembly']}; move the whole assembly with assembly_sites.{entry['assembly']}.translation")
            if turned and entry['companions']:
                found.append(f'{label}: trees and _Wood placements can move but not rotate or scale')
    return found


def main():
    parser = argparse.ArgumentParser(description='Check continent-edits.json against the certified libraries.')
    parser.add_argument('--library', required=True)
    parser.add_argument('--edits', default=str(EDITS_PATH))
    args = parser.parse_args()
    edits = load_edits(args.edits)
    ObjectEdits(edits, [p.name for p in Path(args.library).iterdir() if (p / 'library.json').exists()])
    found = problems(edits, catalogue(args.library))
    for line in found:
        print('problem:', line)
    counts = {a: sum(e['action'] == a for e in edits['objects']) for a in ('remove', 'transform', 'add')}
    print(f"{counts['remove']} removals, {counts['transform']} transforms, {counts['add']} copies, "
          f"{len(edits.get('vegetationAreas', []))} vegetation areas; {len(found)} problems")
    raise SystemExit(1 if found else 0)


if __name__ == '__main__':
    main()
