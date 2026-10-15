"""Validate, share identical image bytes, and install a reviewed scratch build.

Packing never writes client assets. Installation checks every destination against
the start snapshot, then checks it again immediately before atomic replacement.
Item definitions, bodies, animation clips and appearance metadata are protected.

The batch `pack` and `install` commands are retired (2026-10, race programme
P7): they write the old layout (the old-male base scenes equipment/<slug>.glb
and `canonical_<race>` variants for every body, luminous_* included) that the
P7 cleanup deleted. `pack_glb`, `validate` and the provenance helpers stay;
install_human_equipment.py and refit_race_headwear.py `install` use them.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
import subprocess

import numpy as np

import equipment_authoring as ea
import refit_canonical_equipment as refit

ROOT = refit.ROOT
SCRATCH = refit.SCRATCH
PREFIX = Path('godot-client/assets/actors/native/equipment')
REGISTRY = Path('godot-client/data/actors/equipment.json')


def snapshot():
    """Record actual worktree bytes before a new scratch build or installation."""
    output = SCRATCH / 'in/start-hashes.json'
    if output.exists():
        raise FileExistsError('Keep the original snapshot; use a fresh worktree for a new refit')
    paths = subprocess.check_output(['git', 'ls-files', '--',
        'godot-client/data', 'godot-client/assets/actors/native',
        'eloria-assets/tools'], cwd=ROOT, text=True).splitlines()
    base = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    data = {'base': base, 'files': {p: refit.digest(ROOT/p) for p in paths if (ROOT/p).is_file()}}
    new_file(output, (json.dumps(data, indent=2)+'\n').encode())
    print(f'Snapshotted {len(data["files"])} files at {base}')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def image_bytes(document, binary, path):
    for image in document.get('images', []):
        if 'bufferView' in image:
            view = document['bufferViews'][image['bufferView']]
            start = view.get('byteOffset', 0)
            yield binary[start:start + view['byteLength']]
        else:
            yield (path.parent / image['uri']).read_bytes()


def validate(path, race=None):
    document, binary = ea.read_glb(path)
    stats = {'vertices': 0, 'triangles': 0, 'images': []}
    for encoded in image_bytes(document, binary, path):
        if not encoded.startswith((b'\xff\xd8', b'\x89PNG')):
            raise ValueError(f'Unsupported or corrupt image in {path}')
        stats['images'].append(sha(encoded))
    rigs = document.get('skins', [])
    expected = refit.cached_rig(race) if rigs and race else None
    for skin in rigs:
        names = [document['nodes'][i]['name'] for i in skin['joints']]
        if expected is not None and names != expected.joint_names:
            raise ValueError(f'Joint order differs from canonical body: {path}')
        binds = ea.accessor_array(document, binary, skin['inverseBindMatrices'])
        if not np.isfinite(binds).all():
            raise ValueError(f'Nonfinite binds: {path}')
        if expected is not None:
            matrices = binds.reshape(-1, 4, 4).transpose(0, 2, 1)
            rests = np.asarray([expected.rest[name] for name in names])
            if not np.allclose(rests @ matrices, np.eye(4), atol=2e-6):
                raise ValueError(f'Noncanonical rest binding: {path}')
    for mesh in document.get('meshes', []):
        for primitive in mesh['primitives']:
            attrs = {name: ea.accessor_array(document, binary, index)
                     for name, index in primitive['attributes'].items()}
            if any(not np.isfinite(value).all() for value in attrs.values()):
                raise ValueError(f'Nonfinite vertex attribute: {path}')
            indices = ea.accessor_array(document, binary, primitive['indices']).ravel()
            if len(indices) % 3 or indices.max() >= len(attrs['POSITION']):
                raise ValueError(f'Invalid triangles: {path}')
            if 'WEIGHTS_0' in attrs:
                weights = attrs['WEIGHTS_0'].astype(float)
                if np.issubdtype(attrs['WEIGHTS_0'].dtype, np.integer):
                    weights /= np.iinfo(attrs['WEIGHTS_0'].dtype).max
                if np.min(weights) < 0 or not np.allclose(weights.sum(axis=1), 1., atol=.012):
                    raise ValueError(f'Invalid skin weights: {path}')
                if attrs['JOINTS_0'].max() >= 77:
                    raise ValueError(f'Invalid joint index: {path}')
            stats['vertices'] += len(attrs['POSITION'])
            stats['triangles'] += len(indices) // 3
    return stats


def new_file(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Concurrent packing workers may share the same content-addressed image.
    try:
        with path.open('xb') as handle:
            handle.write(data)
    except FileExistsError:
        if path.read_bytes() != data:
            raise ValueError(f'Existing scratch output differs: {path}')


def pack_glb(source, target, stage):
    document, binary = ea.read_glb(source)
    images = list(image_bytes(document, binary, source))
    removed = {image['bufferView'] for image in document.get('images', []) if 'bufferView' in image}
    if document.get('extensionsUsed'):
        raise ValueError('Packing requires ordinary, uncompressed glTF buffer views')
    for accessor in document.get('accessors', []):
        if accessor.get('bufferView') in removed or 'sparse' in accessor:
            raise ValueError('Unexpected image/accessor buffer alias')
    mapping, views, packed = {}, [], bytearray()
    for index, view in enumerate(document['bufferViews']):
        if index in removed:
            continue
        packed.extend(b'\0' * ((-len(packed)) % 4))
        offset = view.get('byteOffset', 0)
        replacement = dict(view, byteOffset=len(packed))
        packed.extend(binary[offset:offset + view['byteLength']])
        mapping[index] = len(views)
        views.append(replacement)
    for accessor in document.get('accessors', []):
        if 'bufferView' in accessor:
            accessor['bufferView'] = mapping[accessor['bufferView']]
    texture_paths = []
    for image, encoded in zip(document.get('images', []), images):
        suffix = '.jpg' if encoded.startswith(b'\xff\xd8') else '.png'
        texture = PREFIX / 'textures' / ('canonical_' + sha(encoded) + suffix)
        new_file(stage / texture, encoded)
        image.pop('bufferView', None)
        image['mimeType'] = 'image/jpeg' if suffix == '.jpg' else 'image/png'
        image['uri'] = os.path.relpath(texture, target.parent).replace('\\', '/')
        texture_paths.append(texture)
    document['bufferViews'] = views
    glb = ea.EquipmentGLB(generator='Eloria shared-texture canonical equipment')
    from pack_shared_equipment import smaller_indices
    glb.doc, glb.binary, _ = smaller_indices(document, bytes(packed))
    destination = stage / target
    if destination.exists():
        raise FileExistsError(destination)
    glb.write(destination)
    packed_doc, packed_bin = ea.read_glb(destination)
    source_doc, source_bin = ea.read_glb(source)
    for index in range(len(source_doc.get('accessors', []))):
        if not np.array_equal(ea.accessor_array(source_doc, source_bin, index),
                              ea.accessor_array(packed_doc, packed_bin, index)):
            raise ValueError(f'Packing changed accessor {index}: {target}')
    return texture_paths


@lru_cache(maxsize=16)
def only_function_body_changed(previous, current, function):
    """Prove module execution and every other function unchanged by a torso edit.

    Only remap's lazy function body may differ. Its signature, defaults and
    decorators still participate in the comparison, since those can execute
    while importing the module used by the limb/head fitter.
    """
    trees = [ast.parse(source) for source in (previous, current)]
    for tree in trees:
        functions = [node for node in tree.body
                     if isinstance(node, ast.FunctionDef) and node.name == function]
        if len(functions) != 1:
            return False
        functions[0].body = [ast.Pass()]
    return ast.dump(trees[0], include_attributes=False) == ast.dump(trees[1], include_attributes=False)


def only_torso_mapping_changed(previous, current):
    return only_function_body_changed(previous, current, 'remap')


def module_references_only(source, module, permitted):
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    references = [node for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id == module]
    return bool(references) and all(isinstance(parents.get(node), ast.Attribute)
                                   and parents[node].attr in permitted for node in references)


@lru_cache(maxsize=16)
def head_frame_is_guarded(source):
    tree = ast.parse(source)
    builder = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'build')
    assignments = [node for node in builder.body if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'is_head' for t in node.targets)]
    expected = ast.parse('is_head = kind in io.SOCKET_KIND').body[0]
    if len(assignments) != 1 or ast.dump(assignments[0]) != ast.dump(expected):
        return False
    guards = [node for node in builder.body if isinstance(node, ast.If)
              and isinstance(node.test, ast.Name) and node.test.id == 'is_head']
    guarded = {id(node) for guard in guards for statement in guard.body for node in ast.walk(statement)}
    references = [node for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id == 'head_frame']
    return len(references) == 1 and id(references[0]) in guarded


@lru_cache(maxsize=16)
def only_low_ornament_guard_added(previous, current):
    """A source-specific reuse proof: exactly one early continue was added."""
    before, after = [ast.parse(source) for source in (previous, current)]
    function = next(node for node in after.body
                    if isinstance(node, ast.FunctionDef) and node.name == 'remap')
    guard = ast.parse('if block[:, 1].max() < wrist[1] - .16 * source_height:\n    continue').body[0]
    matches = [node for node in ast.walk(function)
               if isinstance(node, ast.If) and ast.dump(node) == ast.dump(guard)]
    if len(matches) != 1:
        return False
    for parent in ast.walk(function):
        for _, value in ast.iter_fields(parent):
            if isinstance(value, list) and matches[0] in value:
                value.remove(matches[0])
    return ast.dump(before) == ast.dump(after)


@lru_cache(maxsize=64)
def low_ornament_count(source, expected_sha):
    """Evaluate the new branch using the same source-only component inputs.

    No wearer geometry participates before this branch. Zero matches proves
    unchanged execution for every wearer of this exact original design.
    """
    import torso_remap
    if refit.digest(source) != expected_sha:
        raise ValueError('Source changed during compatibility proof')
    surface, _ = refit.ce.read_source(source)
    points, triangles = surface.positions, surface.indices.reshape(-1, 3)
    canon, edges, count = refit.ce._weld(points, triangles)
    labels = refit.ce._components(edges, count)[canon]
    frames = torso_remap.source_skeleton(points)
    height = np.ptp(points[:, 1])
    matches = 0
    for side, sign in [('l', 1.), ('r', -1.)]:
        _, wrist = frames[side]
        for label in np.unique(labels):
            block = points[labels == label]
            centroid = np.unique(np.round(block, 5), axis=0).mean(axis=0)
            if block[:, 0].min() < -.075 * height and block[:, 0].max() > .075 * height:
                continue
            if centroid[0] * sign < .17 * height:
                continue
            matches += int(block[:, 1].max() < wrist[1] - .16 * height)
    return matches


def fitting_provenance(report, codes, previous_torso_source=None, previous_head_source=None):
    """Keep complete recorded hashes; allow a proven unrelated torso-body edit.

    Limb/head fitting reads only torso_remap.backing_colour. This narrow proof
    lets a later torso-only rebuild share already audited boots/legs/headwear.
    It cannot bless an old torso or a change to any other function or tool.
    """
    changed = {name for name in set(codes) | set(report['tool_sha256'])
               if codes.get(name) != report['tool_sha256'].get(name)}
    if not changed:
        return {}
    if not changed <= {'torso_remap.py', 'limb_head_remap.py'}:
        raise ValueError('Fitter changed after candidate build')
    proofs = []
    slot = report['key'].split(':')[0]
    for filename, function, previous_path, forbidden in [
        ('torso_remap.py', 'remap', previous_torso_source, '5'),
        ('limb_head_remap.py', 'head_frame', previous_head_source, '3')]:
        if filename not in changed:
            continue
        if previous_path is None:
            raise ValueError(f'Candidate needs rebuilding: {filename}/{report["key"]}')
        previous_path = Path(previous_path)
        if previous_path.is_dir():
            previous_path = previous_path / (report['tool_sha256'][filename] + '.py')
        previous = previous_path.read_bytes()
        current = Path(__file__).with_name(filename).read_bytes()
        if sha(previous) != report['tool_sha256'][filename] or sha(current) != codes[filename]:
            raise ValueError('Compatibility source does not match the recorded fitter hashes')
        if slot == forbidden:
            if filename != 'torso_remap.py' or not only_low_ornament_guard_added(previous, current):
                raise ValueError(f'Candidate needs rebuilding: {filename}/{report["key"]}')
            piece = next(p for p in refit.batch.roster() if p.slug == report['slug'])
            source = piece.source.parent / report['source']
            if low_ornament_count(source, report['source_sha256']):
                raise ValueError(f'New ornament branch changes this source: {report["slug"]}')
            proofs.append({'changed_tool': filename, 'built_sha256': sha(previous),
                           'current_sha256': sha(current), 'previous_source': str(previous_path),
                           'proof': 'AST identical after removing the one new low-ornament guard; guard has zero matching original components',
                           'source_sha256': report['source_sha256'], 'matching_components': 0})
            continue
        if not only_function_body_changed(previous, current, function):
            raise ValueError(f'The edit changes more than the {function} function body')
        if filename == 'torso_remap.py':
            if not module_references_only(Path(__file__).with_name('limb_head_remap.py').read_bytes(),
                                          'torso_remap', {'backing_colour'}):
                raise ValueError('Limb/head fitter has a new torso dependency')
            entry = 'backing_colour'
        elif slot == '5':
            if not module_references_only(Path(__file__).with_name('torso_remap.py').read_bytes(),
                                          'limb_head_remap', {'clip'}):
                raise ValueError('Torso fitter has a new limb/head dependency')
            entry = 'clip'
        else:
            if slot not in {'4','6'} or report['kind'] in refit.ce.SOCKET_KIND or not head_frame_is_guarded(current):
                raise ValueError('Head fitting may execute for this candidate')
            entry = 'build with is_head false'
        proofs.append({'changed_tool': filename, 'built_sha256': sha(previous),
                       'current_sha256': sha(current), 'unchanged_entry_point': entry,
                       'proof': f'AST identical except the unused {function} function body',
                       'previous_source': str(previous_path)})
    return {'compatibility': proofs}


RETIRED = ('pack_canonical_equipment {} is retired (2026-10, race programme P7): it writes the deleted '
           'old-male base scenes and canonical_luminous_* variants. Install Human fits with '
           'install_human_equipment.py and race headwear with refit_race_headwear.py install')


def pack(tag, out_tag, overlays=(), previous_torso_source=None, previous_head_source=None):
    raise RuntimeError(RETIRED.format('pack'))
    if Path(out_tag).name != out_tag or out_tag in ('.', '..'):
        raise ValueError('Output tag must be a directory name')
    stage = SCRATCH / 'packed' / out_tag
    if stage.exists():
        raise FileExistsError('Use a new packed tag')
    selected = {}
    registry = None
    for candidate_tag in (tag, *overlays):
        if Path(candidate_tag).name != candidate_tag or candidate_tag in ('.', '..'):
            raise ValueError('Build tags must be directory names')
        candidate_registry = json.loads((SCRATCH / f'out/{candidate_tag}/equipment.json').read_text())
        if registry is None:
            registry = candidate_registry
        else:
            for key in ('canonicalHeadRestY', 'bodyGirth', 'footAnchor', 'soleDrop', 'fitProfiles', 'fitGroups', 'bodyTemplates'):
                if candidate_registry.get(key) != registry.get(key):
                    raise ValueError(f'Overlay changes body/runtime measurements: {candidate_tag}/{key}')
        for report in json.loads((SCRATCH / f'reports/{candidate_tag}-fit.json').read_text()):
            selected[report['race'], report['slug']] = dict(report, candidate_build=candidate_tag)
            model = registry['models'][report['key']]
            if not registry.get('bodyTemplates') or report['race'] != 'luminous_male' or report['key'].startswith('3:'):
                model.setdefault('variants', {})['canonical_'+report['race']] = report['variant']
    reports = [selected[key] for key in sorted(selected)]
    snapshot = json.loads((SCRATCH / 'in/start-hashes.json').read_text())
    current_hash = refit.digest(ROOT / REGISTRY)
    if current_hash != snapshot['files'][REGISTRY.as_posix()]:
        raise ValueError('Client equipment registry changed since task start')
    roster = {p.slug: p for p in refit.batch.roster()}
    races = sorted(registry['bodyGirth'])
    actual = {(report['race'], report['slug']) for report in reports}
    expected = {(race if piece.part == 3 else registry.get('bodyTemplates', {}).get(race, race), slug)
                for race in races for slug, piece in roster.items()}
    if actual != expected:
        raise ValueError(f'Incomplete batch: missing {len(expected-actual)}, extra {len(actual-expected)}')
    manifest = {'base': snapshot['base'], 'builds': [tag, *overlays], 'files': {}, 'assets': [], 'protected': {}}
    for path, digest in snapshot['files'].items():
        if (path.startswith('godot-client/data/') and path != REGISTRY.as_posix()) or any(
            path.startswith('godot-client/assets/actors/native/' + folder + '/')
            for folder in ('races', 'shared', 'hair')):
            if refit.digest(ROOT / path) != digest:
                raise ValueError(f'Protected input changed: {path}')
            manifest['protected'][path] = digest
    codes = refit.tool_hashes()
    for completed, report in enumerate(reports, 1):
        race, slug = report['race'], report['slug']
        compatibility = fitting_provenance(report, codes, previous_torso_source, previous_head_source)
        original = roster[slug].source.parent / report['source']
        if refit.digest(original) != report['source_sha256']:
            raise ValueError(f'Original design changed: {original}')
        source = SCRATCH / 'out' / report['candidate_build'] / race / f'{slug}.glb'
        if refit.digest(source) != report['asset_sha256']:
            raise ValueError(f'Candidate changed: {source}')
        if refit.digest(refit.ce.RACES / f'{race}.glb') != report['body_sha256']:
            raise ValueError(f'Body changed: {race}')
        before = validate(source, race)
        target = PREFIX / (f'{slug}.glb' if race == 'luminous_male' else f'variants/{race}/{slug}.glb')
        textures = pack_glb(source, target, stage)
        after = validate(stage / target, race)
        if before != after:
            raise ValueError(f'Packing changed asset contents: {target}')
        for path in [target, *textures]:
            manifest['files'][path.as_posix()] = {'sha256': refit.digest(stage / path),
                'expected': snapshot['files'].get(path.as_posix()),
                'bytes': (stage / path).stat().st_size}
        variant = copy.deepcopy(report['variant'])
        variant['scene'] = 'res://' + target.relative_to('godot-client').as_posix()
        model = registry['models'][report['key']]
        if race == 'luminous_male':
            model.update(variant)
        if not registry.get('bodyTemplates') or race != 'luminous_male' or roster[slug].part == 3:
            model.setdefault('variants', {})['canonical_' + race] = variant
        provenance = {key: report[key] for key in ('candidate_build', 'source',
            'source_sha256', 'body_sha256', 'tool_sha256', 'asset_sha256')}
        if 'orchestrator_sha256' in report:
            provenance['orchestrator_sha256'] = report['orchestrator_sha256']
        for reference in ('head_reference_sha256', 'anatomy_reference_sha256'):
            if reference in report:
                provenance[reference] = report[reference]
        provenance.update(compatibility)
        manifest['assets'].append({'race': race, 'slug': slug, **after, **provenance})
        if completed % 264 == 0:
            size = sum(entry['bytes'] for entry in manifest['files'].values())
            print(f'PACK {completed}/{len(reports)} {race}; {size/1e9:.3f} GB shared files', flush=True)
    encoded = (json.dumps(registry, indent=2, allow_nan=False) + '\n').encode()
    new_file(stage / REGISTRY, encoded)
    manifest['files'][REGISTRY.as_posix()] = {'sha256': sha(encoded), 'expected': current_hash}
    new_file(stage / 'manifest.json', (json.dumps(manifest, indent=2) + '\n').encode())
    print(f'Packed {len(reports)} assets into {len(manifest["files"])} files: {stage}')


def install(tag):
    raise RuntimeError(RETIRED.format('install'))
    stage = SCRATCH / 'packed' / tag
    manifest = json.loads((stage / 'manifest.json').read_text())
    for path, digest in manifest['protected'].items():
        if refit.digest(ROOT / path) != digest:
            raise ValueError(f'Protected input changed: {path}')

    def checked(path, spec):
        relative = Path(path)
        if relative.is_absolute() or '..' in relative.parts or not (
            relative == REGISTRY or relative.is_relative_to(PREFIX)):
            raise ValueError(f'Unexpected install destination: {path}')
        current = refit.digest(ROOT / path) if (ROOT / path).exists() else None
        if current != spec['expected']:
            raise ValueError(f'Destination changed; no overwrite: {path}')
        if refit.digest(stage / path) != spec['sha256']:
            raise ValueError(f'Packed candidate changed: {path}')

    for path, spec in manifest['files'].items():
        checked(path, spec)
    # Install the registry last, so it never points at a partially copied set.
    paths = sorted(manifest['files'], key=lambda path: path == REGISTRY.as_posix())
    for path in paths:
        spec = manifest['files'][path]
        destination = ROOT / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + '.canonical-install-tmp')
        new_file(temporary, (stage / path).read_bytes())
        checked(path, spec)
        os.replace(temporary, destination)
        if refit.digest(destination) != spec['sha256']:
            raise ValueError(f'Installed hash differs: {path}')
    print(f'Installed {len(paths)} hash-checked files')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['snapshot', 'pack', 'install'])
    parser.add_argument('tag', nargs='?')
    parser.add_argument('--out-tag')
    parser.add_argument('--overlay', action='append', default=[], help='Validated partial source rebuild to overlay on the complete base batch')
    parser.add_argument('--compatible-torso-source', type=Path, help='Exact prior source; only remap function-body edits may be reused for non-torso pieces')
    parser.add_argument('--compatible-head-source', type=Path, help='Exact prior source; only head_frame body edits may be reused outside headwear')
    args = parser.parse_args()
    if args.command == 'snapshot':
        snapshot()
    elif not args.tag:
        parser.error('pack/install requires a build tag')
    elif args.command == 'pack':
        pack(args.tag, args.out_tag or args.tag, args.overlay, args.compatible_torso_source, args.compatible_head_source)
    else:
        install(args.tag)
