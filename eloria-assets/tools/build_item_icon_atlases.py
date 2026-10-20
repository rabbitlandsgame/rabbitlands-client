#!/usr/bin/env python3
"""Pack the approved Rabbit Lands paintings into runtime item atlases.

The compact public painting sheet is authoritative. Rebuilding never reads old
mesh screenshots, procedural bottle painters, private models or a server tree.

  python eloria-assets/tools/build_item_icon_atlases.py
  python eloria-assets/tools/build_item_icon_atlases.py --check
  python eloria-assets/tools/build_item_icon_atlases.py --dry-run
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'godot-client'
SOURCE = ROOT / 'eloria-assets/source/item-icons/painted-2026-10-18'
SUPPLEMENTS = [ROOT / 'eloria-assets/source/item-icons/quivers-2026-10-20']


def planned_atlases() -> list[tuple[Path, Image.Image]]:
    manifest = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('draft') or manifest.get('decorativeFrame'):
        raise ValueError('Only approved unframed paintings can be packed')
    config = json.loads((CLIENT / 'data/items/atlases.json').read_text())
    count = int(config['imageCount'])
    if config['cellSize'] != [50, 50]:
        raise ValueError('Painting cell size disagrees with the runtime registry')
    records = manifest['items']
    base_count = int(manifest['imageCount'])
    if [r['imageId'] for r in records] != list(range(base_count)):
        raise ValueError('Every image ID must have exactly one painting')
    source_path = SOURCE / manifest['source']
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != manifest['sourceSha256']:
        raise ValueError('Painting sheet hash does not match the approved manifest')
    sheet = Image.open(source_path).convert('RGBA')
    source_columns = int(manifest['columns'])
    expected = (source_columns * 50, ((base_count + source_columns - 1) // source_columns) * 50)
    if sheet.size != expected:
        raise ValueError('Painting sheet dimensions disagree with its sampling grid')
    per_atlas, columns = int(config['imagesPerAtlas']), int(config['columns'])
    if len(config['atlases']) != (count + per_atlas - 1) // per_atlas:
        raise ValueError('Runtime atlas capacity disagrees with imageCount')
    output = [Image.new('RGBA', (256, 256)) for _ in config['atlases']]
    cells = []
    for image_id, record in enumerate(records):
        x, y = image_id % source_columns * 50, image_id // source_columns * 50
        cell = sheet.crop((x, y, x + 50, y + 50))
        if hashlib.sha256(cell.tobytes()).hexdigest() != record['cellSha256']:
            raise ValueError(f'Painting {image_id} does not match its approved cell hash')
        cells.append((image_id, cell))
    for folder in SUPPLEMENTS:
        supplement = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        if supplement.get('draft') or supplement.get('decorativeFrame'):
            raise ValueError('Only selected unframed supplements can be packed')
        for record in supplement['items']:
            path = folder / record['source']
            if hashlib.sha256(path.read_bytes()).hexdigest() != record['sourceSha256']:
                raise ValueError(f'Supplement source hash differs: {path.name}')
            cell = Image.open(path).convert('RGBA')
            if cell.size != (50, 50):
                raise ValueError(f'Supplement must contain a 50px cell: {path.name}')
            cells.append((int(record['imageId']), cell))
    if [image_id for image_id, _ in cells] != list(range(count)):
        raise ValueError('Base paintings and supplements must cover every image ID exactly once')
    for image_id, cell in cells:
        local = image_id % per_atlas
        output[image_id // per_atlas].paste(cell, (local % columns * 50, local // columns * 50))
    return [(CLIENT / name.removeprefix('res://'), image)
            for name, image in zip(config['atlases'], output)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='verify runtime pixels without writing')
    parser.add_argument('--dry-run', action='store_true', help='validate sources and list changed atlases')
    args = parser.parse_args()
    planned = planned_atlases()
    changed = []
    for target, image in planned:
        same = target.is_file() and Image.open(target).convert('RGBA').tobytes() == image.tobytes()
        if not same:
            changed.append(target.name)
            if not args.check and not args.dry_run:
                image.save(target)
    print(f'{len(planned)} atlases validated; {len(changed)} require updates')
    if changed:
        print(', '.join(changed))
    return int(args.check and bool(changed))


if __name__ == '__main__':
    raise SystemExit(main())
