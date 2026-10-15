#!/usr/bin/env python3
"""Fail fast on truncated or internally inconsistent Four Gates GLB deliveries."""

import json
import math
import struct
from pathlib import Path

from PIL import Image


PACKAGE = Path(__file__).resolve().parents[1] / "maps" / "four-gates-city"


def read_glb(path):
    raw = path.read_bytes()
    if len(raw) < 20 or raw[:4] != b"glTF":
        raise ValueError(f"{path.name}: missing glTF header")
    version, declared = struct.unpack_from("<II", raw, 4)
    if version != 2 or declared != len(raw):
        raise ValueError(f"{path.name}: declared {declared} bytes, actual {len(raw)}")
    json_len, json_type = struct.unpack_from("<I4s", raw, 12)
    if json_type != b"JSON" or 20 + json_len + 8 > len(raw):
        raise ValueError(f"{path.name}: invalid JSON chunk")
    document = json.loads(raw[20:20 + json_len])
    binary_offset = 20 + json_len
    binary_len, binary_type = struct.unpack_from("<I4s", raw, binary_offset)
    binary = raw[binary_offset + 8:]
    if binary_type != b"BIN\0" or binary_len != len(binary):
        raise ValueError(f"{path.name}: binary chunk length mismatch")
    if document["buffers"][0]["byteLength"] != binary_len:
        raise ValueError(f"{path.name}: buffer declaration mismatch")
    for index, view in enumerate(document.get("bufferViews", [])):
        end = view.get("byteOffset", 0) + view["byteLength"]
        if end > binary_len:
            raise ValueError(f"{path.name}: bufferView {index} exceeds binary chunk")
    names = [node.get("name") for node in document.get("nodes", []) if node.get("name")]
    if len(names) != len(set(names)):
        raise ValueError(f"{path.name}: duplicate node names")
    for index, image in enumerate(document.get("images", [])):
        view = document["bufferViews"][image["bufferView"]]
        start = view.get("byteOffset", 0)
        from io import BytesIO
        decoded = Image.open(BytesIO(binary[start:start + view["byteLength"]]))
        decoded.load()
    return document


def collect_node_references(value, key=None):
    if isinstance(value, dict):
        for child_key, child in value.items():
            yield from collect_node_references(child, child_key)
    elif isinstance(value, list):
        for child in value:
            yield from collect_node_references(child, key)
    elif isinstance(value, str) and key in {"node", "targetNode", "cityTerraceNode", "shorelineNode"}:
        yield value


def validate_pair(glb_name, json_name):
    document = read_glb(PACKAGE / glb_name)
    metadata = json.loads((PACKAGE / json_name).read_text())
    if metadata["asset"]["glb"] != glb_name:
        raise ValueError(f"{json_name}: asset.glb does not name {glb_name}")
    nodes = {node.get("name") for node in document.get("nodes", [])}
    missing = sorted(set(collect_node_references(metadata)) - nodes)
    if missing:
        raise ValueError(f"{json_name}: missing GLB nodes: {', '.join(missing[:12])}")
    return len(document["nodes"]), len(document["meshes"])


def main():
    lod1_document = read_glb(PACKAGE / "four-gates-city.glb")
    lod2_document = read_glb(PACKAGE / "four-gates-city-lod2.glb")
    lod1 = validate_pair("four-gates-city.glb", "four-gates-city.json")
    lod2 = validate_pair("four-gates-city-lod2.glb", "four-gates-city-lod2.json")
    metadata = json.loads((PACKAGE / "four-gates-city.json").read_text())
    if metadata.get("assetVersion") != "0.9.0":
        raise ValueError("four-gates-city.json: expected close-detail asset version 0.9.0")
    detail_names = {node.get("name") for node in lod1_document["nodes"] if node.get("name", "").startswith("Detail_")}
    if len(detail_names) < 250 or len(detail_names) != metadata.get("detailPass", {}).get("nodeCount"):
        raise ValueError("four-gates-city.glb: incomplete deterministic close-detail pass")
    if any(node.get("name", "").startswith("Detail_") for node in lod2_document["nodes"]):
        raise ValueError("four-gates-city-lod2.glb: close-detail nodes were not pruned")
    required = {
        "Detail_Gate_South_Inner_Crown_+1",
        "Detail_Civic_Planter_00_Border",
        "Detail_Market_Crate_00_A",
        "Detail_Residence_0_Balcony",
        "Detail_Waterfall_00_Foam_Ribbon_0",
        "Detail_Broadleaf_00_Crown",
    }
    missing_detail = required - detail_names
    if missing_detail:
        raise ValueError(f"four-gates-city.glb: missing detail contracts: {', '.join(sorted(missing_detail))}")
    route_intrusions = []
    for node in lod1_document["nodes"]:
        if not node.get("name", "").startswith("Detail_") or "translation" not in node:
            continue
        x, _, z = node["translation"]
        if math.hypot(x, z) > 70.0 and min(abs(x), abs(z)) < 30.0:
            route_intrusions.append(node["name"])
    if route_intrusions:
        raise ValueError(f"four-gates-city.glb: detail intrudes on principal-route clearance: {', '.join(route_intrusions[:8])}")
    print(f"Four Gates package valid: LOD1 {lod1[0]} nodes/{lod1[1]} meshes; LOD2 {lod2[0]} nodes/{lod2[1]} meshes")


if __name__ == "__main__":
    main()
