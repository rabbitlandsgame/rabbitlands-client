"""Correct embedded image MIME labels without changing any GLB binary bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

def repair(source, output):
    original = source.read_bytes()
    magic, version, length = struct.unpack_from('<4sII', original)
    size, kind = struct.unpack_from('<I4s', original, 12)
    if (magic, version, length, kind) != (b'glTF', 2, len(original), b'JSON'):
        raise ValueError('Expected a GLB 2.0 with its JSON chunk first')
    document = json.loads(original[20:20+size])
    tail = original[20+size:]
    binary_size, binary_kind = struct.unpack_from('<I4s', tail)
    if binary_kind != b'BIN\0':
        raise ValueError('Expected the original BIN chunk after JSON')
    binary = tail[8:8+binary_size]
    changes = []
    for index, image in enumerate(document.get('images', [])):
        if 'bufferView' not in image:
            continue
        view = document['bufferViews'][image['bufferView']]
        offset = view.get('byteOffset', 0)
        header = binary[offset:offset+8]
        actual = ('image/jpeg' if header.startswith(b'\xff\xd8\xff') else
                  'image/png' if header == b'\x89PNG\r\n\x1a\n' else None)
        if actual is None:
            raise ValueError(f'Unknown embedded image encoding: {index}')
        if image.get('mimeType') != actual:
            changes.append({'image': index, 'before': image.get('mimeType'), 'after': actual})
            image['mimeType'] = actual
    if not changes:
        raise ValueError('No MIME mismatch to repair')
    encoded = json.dumps(document, separators=(',', ':'), ensure_ascii=False).encode()
    encoded += b' ' * ((-len(encoded)) % 4)
    result = struct.pack('<4sII', magic, version, 20+len(encoded)+len(tail))
    result += struct.pack('<I4s', len(encoded), b'JSON') + encoded + tail
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as handle:
        handle.write(result)
    if source.read_bytes() != original or output.read_bytes()[20+len(encoded):] != tail:
        raise ValueError('Input or binary chunk changed')
    digest = lambda value: hashlib.sha256(value).hexdigest()
    return {'source': str(source), 'source_sha256': digest(original),
            'candidate': str(output), 'candidate_sha256': digest(result),
            'binary_sha256': digest(binary), 'changes': changes}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('-o', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    report = repair(args.source, args.o)
    with args.report.open('x') as handle:
        json.dump(report, handle, indent=2)
