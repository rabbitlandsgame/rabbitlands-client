"""Frozen terrain refuses corrupt/stale inputs and outputs; replays pinned history."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import freeze_continent_v2_terrain as F


class MemoryInputs:
    def __init__(self, files, commit=F.SOURCE_REF):
        self.commit = commit
        self.files = dict(files)

    def read(self, path):
        return self.files[path]


@pytest.fixture(scope="module")
def pinned():
    reader = F.GitInputs(F.CHECKOUT)
    expected = F.build_snapshot(reader)
    return reader.files, expected


def scene_path(files, region="sw_isle"):
    catalog = json.loads(files[F.CATALOG_PATH])
    return F.git_path(next(e["scenePath"] for e in catalog["entries"] if e["id"] == region))


def replace_array(blob, key, kind, values):
    text = blob.decode("utf-8")
    pattern = rf"(?m)^{key} = {kind}\([^\n]*\)"
    text, count = re.subn(pattern, f"{key} = {kind}({', '.join(map(str, values))})", text, count=1)
    assert count == 1
    return text.encode("utf-8")


def layer_arrays(blob):
    text = blob.decode("utf-8")
    idx = re.search(r"(?m)^indices = PackedInt32Array\(([^\n]*)\)", text).group(1)
    delta = re.search(r"(?m)^deltas = PackedFloat32Array\(([^\n]*)\)", text).group(1)
    return [int(i.strip()) for i in idx.split(",")], [float(d.strip()) for d in delta.split(",")]


def test_pinned_history_replays_without_live_source_paths(pinned, monkeypatch):
    def refuse_working_tree(*_args, **_kwargs):
        raise AssertionError("frozen replay must not read a retired working-tree source")
    monkeypatch.setattr(F.T, "res_to_path", refuse_working_tree)
    monkeypatch.setattr(F.T, "load_territories", refuse_working_tree)
    reader = F.GitInputs(F.CHECKOUT, F.SOURCE_REF)
    repeated = F.build_snapshot(reader)
    assert repeated == pinned[1]
    assert F.sha256(repeated["base-heights.f32le"]) == "176b536762632e57bc40a1298f9a6ccf304a2c27bd420ec9e0f7191314ed69ec"
    provenance = json.loads(repeated["terrain-provenance.json"])
    assert provenance["nonzeroSculptVertices"] == 47601
    assert sum(s["ownedVerticesVerifiedByteExact"] for s in provenance["sources"]) == 1477723


@pytest.mark.parametrize("filename", ["base-heights.f32le", "base-colors.rgba8", "terrain-provenance.json"])
def test_check_refuses_corruption_without_repairing_it(pinned, tmp_path, filename):
    F.write_or_check(tmp_path, pinned[1], check=False)
    F.write_or_check(tmp_path, pinned[1], check=True)
    path = tmp_path / filename
    corrupt = bytearray(path.read_bytes())
    corrupt[len(corrupt) // 2] ^= 1
    path.write_bytes(corrupt)
    with pytest.raises(F.FreezeError, match="stale or corrupt"):
        F.write_or_check(tmp_path, pinned[1], check=True)
    assert path.read_bytes() == bytes(corrupt)


def test_check_refuses_missing_output(pinned, tmp_path):
    F.write_or_check(tmp_path, pinned[1], check=False)
    (tmp_path / "base-heights.f32le").unlink()
    with pytest.raises(F.FreezeError, match="base-heights"):
        F.write_or_check(tmp_path, pinned[1], check=True)


def test_stale_sculpt_base_binding_is_refused(pinned):
    files = dict(pinned[0]); path = scene_path(files)
    files[path] = re.sub(rb'(?m)^base_sha256 = "[a-f0-9]+"', b'base_sha256 = "' + b'0' * 64 + b'"', files[path], count=1)
    with pytest.raises(F.FreezeError, match="stale sculpt base/grid binding"):
        F.build_snapshot(MemoryInputs(files))


@pytest.mark.parametrize("invalid", ["duplicate", "out-of-grid", "non-finite", "over-limit"])
def test_bad_sparse_sculpt_entries_are_refused(pinned, invalid):
    files = dict(pinned[0]); path = scene_path(files)
    indices, deltas = layer_arrays(files[path])
    if invalid == "duplicate": indices[1] = indices[0]
    if invalid == "out-of-grid": indices[-1] = 1446 * 1259
    if invalid == "non-finite": deltas[0] = float("nan")
    if invalid == "over-limit": deltas[0] = 4096.01
    files[path] = replace_array(files[path], "indices", "PackedInt32Array", indices)
    files[path] = replace_array(files[path], "deltas", "PackedFloat32Array", deltas)
    with pytest.raises(F.FreezeError, match="unique, sorted|non-finite|4096"):
        F.build_snapshot(MemoryInputs(files))


def test_sparse_cross_source_conflict_is_refused(pinned):
    files = dict(pinned[0]); catalog = json.loads(files[F.CATALOG_PATH])
    sources = [F.load_source(MemoryInputs(files), e) for e in catalog["entries"]]
    sw = next(s for s in sources if s.territory.id == "sw_isle")
    gull = next(s for s in sources if s.territory.id == "gull_skerries")
    rs, cs = np.nonzero(sw.sculpt)
    x = sw.territory.first_vertex[0] + cs * 2
    z = sw.territory.first_vertex[1] + rs * 2
    cols = ((x - gull.territory.first_vertex[0]) / 2).astype(int)
    rows = ((z - gull.territory.first_vertex[1]) / 2).astype(int)
    hit = np.flatnonzero((cols >= 0) & (cols < gull.territory.width) & (rows >= 0) & (rows < gull.territory.height))[0]
    conflicting = int(rows[hit] * gull.territory.width + cols[hit])
    path = scene_path(files, "gull_skerries")
    files[path] = replace_array(files[path], "indices", "PackedInt32Array", [conflicting])
    files[path] = replace_array(files[path], "deltas", "PackedFloat32Array", [1.0])
    with pytest.raises(F.FreezeError, match="overlapping sparse sculpt entries"):
        F.build_snapshot(MemoryInputs(files))


def test_crop_corruption_is_refused_even_when_sculpt_binding_is_updated(pinned):
    files = dict(pinned[0]); catalog = json.loads(files[F.CATALOG_PATH])
    gull = next(e for e in catalog["entries"] if e["id"] == "gull_skerries")
    source = F.load_source(MemoryInputs(files), gull)
    path = source.paths["baseHeights"]
    changed = np.frombuffer(files[path], "<f4").copy(); changed[0] += 1.0
    files[path] = changed.astype("<f4").tobytes()
    scene = source.paths["scene"]
    files[scene] = re.sub(rb'(?m)^base_sha256 = "[a-f0-9]+"',
                         b'base_sha256 = "' + F.sha256(files[path]).encode() + b'"', files[scene], count=1)
    with pytest.raises(F.FreezeError, match="byte-identical crop"):
        F.build_snapshot(MemoryInputs(files))


def test_source_spec_frame_mismatch_is_refused(pinned):
    files = dict(pinned[0]);catalog = json.loads(files[F.CATALOG_PATH])
    path = F.git_path(catalog["entries"][0]["authoringSpecPath"])
    spec = json.loads(files[path]);spec["terrain"]["origin"][0] += 2
    files[path] = F.json_bytes(spec)
    with pytest.raises(F.FreezeError, match="source frames disagree"):
        F.build_snapshot(MemoryInputs(files))
