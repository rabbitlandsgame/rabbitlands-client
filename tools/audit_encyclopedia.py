#!/usr/bin/env python3
"""Audit encyclopedia catalogues against a current Rabbit Lands server checkout.

Written guides still require editorial review. This checks the reproducible
parts, duplicate page keys, leftover placeholders and shared source metadata.
Generated comparison files and the report stay under the ignored .local folder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / 'godot-client'


def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-root', type=Path, required=True)
    args = parser.parse_args()
    server = args.server_root.resolve()
    out = ROOT / '.local' / 'encyclopedia-audit'
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        sys.executable, str(ROOT / 'tools/generate_manufacturing_catalog.py'),
        '--server-root', str(server), '--output', str(out / 'recipes.json'),
        '--knowledge-output', str(out / 'knowledge.json'),
    ], check=True)
    checks = {}
    for generated, shipped in [('recipes.json', 'manufacturing/recipes.json'),
                               ('knowledge.json', 'knowledge/catalog.json')]:
        checks[shipped] = read(out / generated) == read(CLIENT / 'data' / shipped)
    sys.path.insert(0, str(server))
    from eloria.magic_book import BOOK
    magic = read(CLIENT / 'data/spells/catalog.json')
    for source, field in [('spells', 'spells'), ('aliases', 'spellAliases'),
                          ('families', 'spellFamilies')]:
        checks['magic:' + field] = BOOK[source] == magic[field]
    perks = subprocess.run([
        sys.executable, str(server / 'tools/generate_perk_reference.py'),
        '--client', str(CLIENT), '--check',
    ], check=False)
    checks['perks'] = perks.returncode == 0
    manifest = read(server / 'config/eloria/client_content_manifest.json')
    source_hashes = {
        key: hashlib.sha256((server / 'config/eloria' / name).read_bytes()
                            .replace(b'\r\n', b'\n')).hexdigest()
        for key, name in [('recipesSha256', 'recipes.txt'),
                          ('itemsSha256', 'items.txt'), ('booksSha256', 'books.txt')]
    }
    checks['server_catalogue_provenance'] = manifest['catalog_sources'] == source_hashes
    document = read(CLIENT / 'data/reference/encyclopedia.json')
    keys = []
    authored = []
    for category in document['categories']:
        for entry in category.get('entries', []):
            keys.append(category['id'] + '/' + entry['id'])
            # Legacy IDs retain "todo" so existing bookmarks remain valid.
            text = json.dumps({key: value for key, value in entry.items() if key != 'id'})
            authored.append(text)
    checks['unique_authored_keys'] = len(keys) == len(set(keys))
    checks['no_player_facing_placeholders'] = all(
        'TODO' not in text and 'not written yet' not in text.lower() for text in authored)
    summary = {
        'checks': checks,
        'recipes': len(read(out / 'recipes.json')['recipes']),
        'knowledge': len(read(out / 'knowledge.json')['entries']),
        'spells': len(magic['spells']),
        'authored_pages_including_generated_perks': len(keys),
        'source_hashes': source_hashes,
        'server_commit': subprocess.check_output(
            ['git', '-C', str(server), 'rev-parse', 'HEAD'], text=True).strip(),
    }
    (out / 'report.json').write_text(json.dumps(summary, indent=2) + '\n',
                                     encoding='utf-8', newline='\n')
    for name, passed in checks.items():
        print(('PASS ' if passed else 'FAIL ') + name)
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
