"""Publish the toolkit's unchanged lake texture for all streamed sea planes."""
from pathlib import Path
import argparse
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'eloria-assets/maps/four-gates/world.glb'
TARGET = ROOT / 'godot-client/assets/world/continent-water.png'


def texture_bytes(path=SOURCE):
    raw = path.read_bytes()
    magic, version, length = struct.unpack_from('<4sII', raw)
    if magic != b'glTF' or version != 2 or length != len(raw):
        raise ValueError('Expected a complete GLB 2.0 package')
    size, kind = struct.unpack_from('<II', raw, 12)
    if kind != 0x4e4f534a:
        raise ValueError('GLB JSON chunk missing')
    doc = json.loads(raw[20:20+size])
    start = 28 + size
    binary_size, kind = struct.unpack_from('<II', raw, 20+size)
    if kind != 0x004e4942 or start+binary_size > len(raw):
        raise ValueError('GLB binary chunk missing or truncated')
    materials = [m for m in doc['materials'] if m.get('name') == 'water_lake']
    if len(materials) != 1:
        raise ValueError('Expected exactly one toolkit water_lake material')
    texture = doc['textures'][materials[0]['pbrMetallicRoughness']['baseColorTexture']['index']]
    image = doc['images'][texture['source']]
    view = doc['bufferViews'][image['bufferView']]
    at = start + view.get('byteOffset', 0)
    data = raw[at:at+view['byteLength']]
    if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data) != view['byteLength']:
        raise ValueError('Expected the original embedded PNG texture')
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    data = texture_bytes()
    if args.apply:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_bytes(data)
    elif not TARGET.is_file() or TARGET.read_bytes() != data:
        raise SystemExit('Continent water texture is stale; run with --apply')
    print(json.dumps({'source': str(SOURCE), 'texture': str(TARGET),
                      'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}))
