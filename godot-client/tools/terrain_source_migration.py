"""Lossless, fixed-lattice terrain-source migration primitives.

These functions never resolve modifiers or choose an ownership plan. Callers must
provide an explicitly reviewed required mask and a hash-bound shared seed. Grid
identity is global integer (x, z), never a row number in a regional rectangle.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re

import numpy as np


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Window:
    x: int
    z: int
    width: int
    height: int

    def __post_init__(self):
        if self.width < 1 or self.height < 1:
            raise ValueError("empty terrain window")

    @property
    def shape(self):
        return self.height, self.width

    def contains(self, other: Window) -> bool:
        return (self.x <= other.x and self.z <= other.z and
                self.x + self.width >= other.x + other.width and
                self.z + self.height >= other.z + other.height)

    def union(self, other: Window) -> Window:
        x, z = min(self.x, other.x), min(self.z, other.z)
        return Window(x, z, max(self.x+self.width, other.x+other.width)-x,
                      max(self.z+self.height, other.z+other.height)-z)


def global_window(origin, translation, vertices, cell=2.0, lattice=(0, 0)):
    start = (np.asarray(origin) + np.asarray(translation) - lattice) / cell
    if not np.all(np.isfinite(start)) or not np.array_equal(start, np.rint(start)):
        raise ValueError("source origin is not on the fixed continent lattice")
    if not np.array_equal(vertices, np.asarray(vertices, dtype=int)):
        raise ValueError("noninteger vertex count")
    return Window(int(start[0]), int(start[1]), int(vertices[0]), int(vertices[1]))


def required_vertices(owners, region_index):
    """Owned-cell incident vertices plus the production one-vertex 3x3 ring."""
    cells = np.asarray(owners) == region_index
    incident = np.zeros((cells.shape[0]+1, cells.shape[1]+1), dtype=bool)
    for dz, dx in ((0, 0), (1, 0), (0, 1), (1, 1)):
        incident[dz:dz+cells.shape[0], dx:dx+cells.shape[1]] |= cells
    padded = np.pad(incident, 1)
    required = np.zeros_like(incident)
    for dz in range(3):
        for dx in range(3):
            required |= padded[dz:dz+incident.shape[0], dx:dx+incident.shape[1]]
    return required


def required_window(mask, field_window):
    if mask.shape != field_window.shape or not mask.any():
        raise ValueError("empty or incorrectly shaped ownership mask")
    z, x = np.where(mask)
    return Window(field_window.x+int(x.min()), field_window.z+int(z.min()),
                  int(x.max()-x.min()+1), int(z.max()-z.min()+1))


def validate_required_coverage(mask, field_window, saved_window):
    if not saved_window.contains(required_window(mask, field_window)):
        raise ValueError("saved terrain does not cover owned-cell incident vertices and shared ring")


def merge_claims(shape, claims, dtype):
    """Merge only authority-masked claims; duplicate values must be bit-identical."""
    result = np.zeros(shape, dtype=dtype)
    claimed = np.zeros(shape, dtype=bool)
    for values, mask in claims:
        values = np.asarray(values, dtype=dtype)
        if values.shape != shape or mask.shape != shape:
            raise ValueError("field claim shape mismatch")
        overlap = claimed & mask
        if result[overlap].tobytes() != values[overlap].tobytes():
            raise ValueError("conflicting shared-field claims")
        fresh = mask & ~claimed
        result[fresh] = values[fresh]
        claimed |= mask
    if not claimed.all():
        raise ValueError("shared-field coverage gap")
    return result


def remap_grid_by_global_id(old_bytes, old, new, field_bytes, field, stride=4,
                            active_modifiers=False):
    if not new.contains(old):
        raise ValueError("migration must preserve the entire old storage envelope")
    if len(old_bytes) != old.width*old.height*stride:
        raise ValueError("old grid byte length mismatch")
    if old == new:
        return old_bytes
    if active_modifiers:
        raise ValueError("growing terrain with active modifiers needs an explicit resolution policy")
    if len(field_bytes) != field.width*field.height*stride:
        raise ValueError("shared field byte length mismatch")
    result = np.empty((*new.shape, stride), dtype=np.uint8)
    fresh = np.ones(new.shape, dtype=bool)
    dx, dz = old.x-new.x, old.z-new.z
    result[dz:dz+old.height, dx:dx+old.width] = np.frombuffer(
        old_bytes, dtype=np.uint8).reshape(*old.shape, stride)
    fresh[dz:dz+old.height, dx:dx+old.width] = False
    z, x = np.where(fresh)
    fx, fz = x+new.x-field.x, z+new.z-field.z
    if np.any(fx < 0) or np.any(fz < 0) or np.any(fx >= field.width) or np.any(fz >= field.height):
        raise ValueError("newly allocated vertex is outside the shared field")
    result[z, x] = np.frombuffer(field_bytes, dtype=np.uint8).reshape(*field.shape, stride)[fz, fx]
    return result.tobytes()


def remap_sculpt(indices, delta_bytes, old, new):
    indices = np.asarray(indices, dtype=np.int64)
    if (not new.contains(old) or len(delta_bytes) != len(indices)*4 or
            np.any(indices < 0) or np.any(indices >= old.width*old.height) or
            np.any(np.diff(indices) <= 0)):
        raise ValueError("invalid sparse sculpt binding")
    mapped = (indices//old.width + old.z-new.z)*new.width + indices%old.width + old.x-new.x
    return mapped.astype('<i4'), delta_bytes


def preserved_old_bytes(result, old, new, stride=4):
    array = np.frombuffer(result, dtype=np.uint8).reshape(*new.shape, stride)
    dx, dz = old.x-new.x, old.z-new.z
    return array[dz:dz+old.height, dx:dx+old.width].tobytes()


def replace_terrain_grid(scene: bytes, old_origin, old_size, new_origin, new_size):
    """Replace two exact properties in the unique direct Terrain node only."""
    text = scene.decode('utf-8')
    blocks = list(re.finditer(r'^\[node name="Terrain"[^\r\n]* parent="\."[^\r\n]*\]\r?\n.*?(?=^\[|\Z)', text, re.M|re.S))
    if len(blocks) != 1:
        raise ValueError("expected exactly one direct Terrain node")
    block = blocks[0]; section = block[0]
    for key, kind, before, after in (
            ('origin', 'Vector2', old_origin, new_origin),
            ('grid_size', 'Vector2i', old_size, new_size)):
        pattern = rf'^{key} = {kind}\(([^\r\n)]*)\)'
        matches = list(re.finditer(pattern, section, re.M))
        if len(matches) != 1 or list(map(float, matches[0][1].split(','))) != list(before):
            raise ValueError(f"Terrain.{key} precondition does not match exactly once")
        value = f'{key} = {kind}({after[0]:g}, {after[1]:g})'
        section = section[:matches[0].start()] + value + section[matches[0].end():]
    return (text[:block.start()] + section + text[block.end():]).encode('utf-8')


def checked_path(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError("expected a checkout-relative path")
    path = (root/relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("path escaped checkout")
    return path


def load_shared_field(root, manifest_path, expected_hash=None):
    path = checked_path(root, manifest_path)
    data = path.read_bytes()
    if expected_hash and sha256(data) != expected_hash:
        raise ValueError("shared-field manifest hash mismatch")
    manifest = json.loads(data)
    lattice = manifest['lattice']
    if manifest['schema'] != 'eloria-terrain-shared-field-v1' or lattice['spacing'] != 2:
        raise ValueError("unsupported shared field")
    window = Window(*lattice['globalVertexMin'], *lattice['vertices'])
    arrays = {}
    for name, encoding in [('heights', 'float32-little-endian'), ('colors', 'rgba8')]:
        entry = manifest[name]
        payload = checked_path(root, entry['path']).read_bytes()
        if entry['encoding'] != encoding or sha256(payload) != entry['sha256'] or len(payload) != window.width*window.height*4:
            raise ValueError(f"invalid shared {name}")
        arrays[name] = payload
    return manifest, window, arrays


def _write_json(path, value):
    _atomic_write(path, (json.dumps(value, indent=2)+'\n').encode())


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.terrain-migration-tmp')
    with temp.open('wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def stage_transaction(root, directory, replacements, preconditions):
    """Save complete allowlist, originals and staged bytes before any product write."""
    root, directory = Path(root).resolve(), Path(directory).resolve()
    if (directory/'journal.json').exists():
        raise ValueError("transaction already exists; verify or roll it back")
    for name, digest in preconditions.items():
        path = checked_path(root, name)
        if not path.exists() or sha256(path.read_bytes()) != digest:
            raise ValueError(f"stale migration precondition: {name}")
    entries = []
    for name, payload in sorted(replacements.items()):
        path = checked_path(root, name)
        original = path.read_bytes() if path.exists() else None
        if original == payload:
            continue
        index = str(len(entries)).zfill(3)
        _atomic_write(directory/'staged'/index, payload)
        if original is not None:
            _atomic_write(directory/'original'/index, original)
        entries.append({'path': name, 'slot': index, 'before': sha256(original) if original is not None else None,
                        'after': sha256(payload), 'status': 'prepared'})
    journal = {'schema': 'eloria-terrain-migration-journal-v1', 'status': 'prepared',
               'preconditions': preconditions, 'entries': entries}
    _write_json(directory/'journal.json', journal)
    return journal


def apply_transaction(root, directory, *, stop_after=None):
    """Resume safely after interruption; repeat after commit verifies a no-op."""
    root, directory = Path(root).resolve(), Path(directory).resolve()
    journal = json.loads((directory/'journal.json').read_bytes())
    if journal['status'] == 'rolled-back':
        raise ValueError("rolled-back transaction cannot be reapplied")
    entries = {entry['path']: entry for entry in journal['entries']}
    for name, digest in journal['preconditions'].items():
        path = checked_path(root, name)
        actual = sha256(path.read_bytes()) if path.exists() else None
        allowed = (digest, entries[name]['after']) if name in entries else (digest,)
        if actual not in allowed:
            raise ValueError(f"stale migration precondition: {name}")
    # Validate the ENTIRE allowlist and backups before writing a single file.
    for entry in entries.values():
        path = checked_path(root, entry['path'])
        actual = sha256(path.read_bytes()) if path.exists() else None
        if actual not in (entry['before'], entry['after']):
            raise ValueError(f"unexpected concurrent edit: {entry['path']}")
        if sha256((directory/'staged'/entry['slot']).read_bytes()) != entry['after']:
            raise ValueError("corrupt staged payload")
        if entry['before'] is not None and sha256((directory/'original'/entry['slot']).read_bytes()) != entry['before']:
            raise ValueError("corrupt recovery backup")
    if journal['status'] == 'committed':
        for entry in entries.values():
            path = checked_path(root, entry['path'])
            if not path.exists() or sha256(path.read_bytes()) != entry['after']:
                raise ValueError(f"committed source was reverted: {entry['path']}")
        return 0
    writes = 0
    for entry in entries.values():
        path = checked_path(root, entry['path'])
        actual = sha256(path.read_bytes()) if path.exists() else None
        if actual not in (entry['before'], entry['after']):
            raise ValueError(f"concurrent edit during application: {entry['path']}")
        if actual != entry['after']:
            _atomic_write(path, (directory/'staged'/entry['slot']).read_bytes())
            writes += 1
        entry['status'] = 'applied'
        _write_json(directory/'journal.json', journal)
        if stop_after is not None and writes >= stop_after:
            raise InterruptedError("requested transaction interruption")
    journal['status'] = 'committed'
    _write_json(directory/'journal.json', journal)
    return writes


def rollback_transaction(root, directory):
    root, directory = Path(root).resolve(), Path(directory).resolve()
    journal = json.loads((directory/'journal.json').read_bytes())
    for entry in journal['entries']:
        path = checked_path(root, entry['path'])
        actual = sha256(path.read_bytes()) if path.exists() else None
        if actual not in (entry['before'], entry['after']):
            raise ValueError(f"rollback refuses concurrent edit: {entry['path']}")
        if entry['before'] is not None and sha256((directory/'original'/entry['slot']).read_bytes()) != entry['before']:
            raise ValueError("corrupt recovery backup")
    for entry in reversed(journal['entries']):
        path = checked_path(root, entry['path'])
        actual = sha256(path.read_bytes()) if path.exists() else None
        if actual not in (entry['before'], entry['after']):
            raise ValueError(f"concurrent edit during rollback: {entry['path']}")
        if entry['before'] is None:
            path.unlink(missing_ok=True)
        else:
            _atomic_write(path, (directory/'original'/entry['slot']).read_bytes())
        entry['status'] = 'restored'
        _write_json(directory/'journal.json', journal)
    journal['status'] = 'rolled-back'
    _write_json(directory/'journal.json', journal)
