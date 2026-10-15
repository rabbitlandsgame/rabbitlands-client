"""Resolve one default arrival without adding generated markers to conserved authored gameplay.

Authored arrivals stay scene-owned. Spawnless sections use hash-bound content metadata
named by their authoring spec, copied into snapshot.generatedArrival by the baker.
Every publisher validates the same input and frame, refusing stale or mixed defaults.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import ownership

SCHEMA = "eloria-continent-v2-generated-arrival-v1"
ALGORITHM = "nearest-owned-safe-baseline-tile-v1"


class ArrivalError(ValueError):
    pass


def frame_record(frame):
    return {"origin": list(frame.origin), "cells": list(frame.cells), "translation": list(frame.translation)}


def frame_sha256(frame):
    return hashlib.sha256(json.dumps(frame_record(frame), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _bake_json_equal(source, baked):
    """Godot's JSON round trip may change the last binary64 bit; retain strict structure and hash authority."""
    if isinstance(source, bool) or isinstance(baked, bool):
        return source is baked
    if isinstance(source, (int, float)) and isinstance(baked, (int, float)):
        if isinstance(source, int):
            return source == baked
        return math.isfinite(source) and math.isfinite(baked) and math.isclose(
            source, baked, rel_tol=0, abs_tol=4*max(math.ulp(source), math.ulp(baked)))
    if isinstance(source, dict) and isinstance(baked, dict):
        return source.keys() == baked.keys() and all(_bake_json_equal(v, baked[k]) for k, v in source.items())
    if isinstance(source, list) and isinstance(baked, list):
        return len(source) == len(baked) and all(_bake_json_equal(a, b) for a, b in zip(source, baked))
    return type(source) is type(baked) and source == baked


def _vector(value, size, field):
    if not isinstance(value, list) or len(value) != size or any(isinstance(v, bool) or not isinstance(v, (int,float)) or not math.isfinite(v) for v in value):
        raise ArrivalError(f"{field}: expected {size} finite numeric coordinates")
    return value


def contained(checkout, relative):
    if not isinstance(relative, str) or not relative or ":" in relative or "\\" in relative:
        raise ArrivalError("arrival path must be a checkout-relative path")
    parts = relative.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ArrivalError("arrival path escapes its checkout")
    root = Path(checkout).resolve()
    path = root.joinpath(*parts)
    if not path.resolve().is_relative_to(root) or any(p.is_symlink() or (hasattr(p,"is_junction") and p.is_junction()) for p in [path,*path.parents] if p != root and p.is_relative_to(root)):
        raise ArrivalError("arrival path uses a link or escapes its checkout")
    return path


def resolve(document, frame, checkout):
    """Return the one normal spawn record, validating generated metadata against spec, bake and ownership."""
    region = frame.region
    if document.get("regionId") != region:
        raise ArrivalError(f"{region}: arrival requested from another map's snapshot")
    authored = [r for r in document.get("gameplay", {}).get("spawnPoints", []) if r.get("default")]
    generated = document.get("generatedArrival")
    spec_path = Path(checkout)/"godot-client/world_authoring/regions"/region/"region-authoring-spec.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    reference = spec.get("gameplay", {}).get("generatedArrival")
    if authored:
        if len(authored) != 1 or generated is not None or reference is not None:
            raise ArrivalError(f"{region}: exactly one authored or generated default is required")
        result = dict(authored[0])
    else:
        if not isinstance(reference, dict) or set(reference) != {"path","sha256"} or not isinstance(generated, dict):
            raise ArrivalError(f"{region}: missing hash-bound generated arrival")
        path = contained(checkout, reference["path"])
        expected_path = Path(checkout)/"eloria-assets/maps/continent-v2"/region/"content/arrival.json"
        if path != expected_path or not path.is_file():
            raise ArrivalError(f"{region}: generated arrival has an unexpected source path")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != reference["sha256"]:
            raise ArrivalError(f"{region}: generated arrival source hash changed; re-bake")
        result = json.loads(raw)
        if not _bake_json_equal(result, generated) or document.get("sources",{}).get("generatedArrival") != reference:
            raise ArrivalError(f"{region}: generated arrival differs from its source/bake binding; re-bake")
        if result.get("schema") != SCHEMA or result.get("map") != region or result.get("id") != f"generated-arrival-{region}" or result.get("default") is not True or result.get("generated") is not True:
            raise ArrivalError(f"{region}: invalid generated arrival identity/schema")
        if result.get("frame") != frame_record(frame):
            raise ArrivalError(f"{region}: generated arrival frame changed")
        provenance = result.get("provenance", {})
        partition = Path(checkout)/"eloria-assets/maps/continent-v2/_continent_v2/partition-inputs/sections_spec.json"
        if provenance.get("algorithm") != ALGORITHM or provenance.get("frameSha256") != frame_sha256(frame) or provenance.get("sectionsSpecSha256") != hashlib.sha256(partition.read_bytes()).hexdigest():
            raise ArrivalError(f"{region}: generated arrival selection/frame provenance changed")
        for field in ("clientBaseCommit","sourceWorldSha256","sourceCollisionSha256","sourceServedGridSha256"):
            value = provenance.get(field)
            length = 40 if field == "clientBaseCommit" else 64
            if not isinstance(value,str) or len(value) != length or any(c not in "0123456789abcdef" for c in value):
                raise ArrivalError(f"{region}: invalid {field} provenance")
    position = _vector(result.get("position"),3,f"{region} arrival position")
    _vector(result.get("facing",[0,0,-1]),3,f"{region} arrival facing")
    tile = _vector(result.get("serverTile"),2,f"{region} arrival tile")
    if any(v != int(v) for v in tile) or tuple(tile) != frame.tile(position[0],position[2]):
        raise ArrivalError(f"{region}: arrival tile differs from its authoritative local position")
    stub = json.loads((Path(checkout)/"eloria-assets/maps/continent-v2"/region/"world.json").read_text(encoding="utf-8"))
    if not ownership.contains(*frame.to_continent(position[0],position[2]),stub["continentGeography"],boundary=True):
        raise ArrivalError(f"{region}: arrival lies outside map ownership")
    return result
