"""Rows added to the frozen server content profile, and how they stay certified.

``legacy-server-profile`` freezes the authored content (spawns, NPCs, harvest
nodes, interactives) as it stood before the diagonal continent, and every
contract run checks the served files against it rewritten into the published
frame. A row that did not exist then has no place in that proof, so adding one
would otherwise mean re-certifying the frozen files, and with them the profile
digest every saved runtime binding in every territory carries.

An amendment instead lists whole blocks to append to the end of one frozen
content file, in order. Each row is written in the frozen frame (its x/y is a
source tile, like every baseline row); the amended text is the baseline text
with the block after its last line, so baseline rows keep their lines and
identities and the new rows follow with the next lines and ordinals. Contract
export places and binds them exactly like baseline rows (a saved runtime
marker must bind each one), the profile check rebuilds them the way it
rebuilds the baseline, and publication rewrites them in the served files by
the same identity. ``--sync`` writes a block into the served server files at
the tiles the last certified publication gives it, so the served files agree
with what the next contract run reconstructs.

The document is ``runtime-content-amendments.json`` beside this file:

    {"schema": "eloria-runtime-content-amendment-v1",
     "blocks": [{"id", "file", "region", "begin", "end", "comments": [...],
                 "rows": [{"fields": [...], "marker": "<runtime point id>"}]}]}

``begin``/``end`` are the block's own comment lines; a row's fields are the
file's pipe fields with the source tile in the coordinate fields;
``baseSha256`` is the certified digest of the frozen file the block follows,
so an amendment never lands on a profile it was not written against.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATH = HERE / 'runtime-content-amendments.json'
SCHEMA = 'eloria-runtime-content-amendment-v1'


class AmendmentError(ValueError):
    pass


def load(path: Path | str | None = PATH) -> dict | None:
    """The committed amendment document, or None when there is none."""
    path = Path(path) if path is not None else None
    if path is None or not path.exists():
        return None
    document = json.loads(path.read_text(encoding='utf-8'))
    if document.get('schema') != SCHEMA or not isinstance(document.get('blocks'), list):
        raise AmendmentError(f'{path.name}: unsupported runtime content amendment schema')
    document['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    return document


def for_certificate(document: dict | None, certificate: dict) -> dict | None:
    """``document`` if every block follows the frozen file this certificate names.

    A block written against another version of its file would put its rows
    after the wrong last line; re-certifying a frozen content file means
    re-pointing (and re-checking) the blocks that follow it.
    """
    if document is None:
        return None
    for block in document['blocks']:
        certified = certificate.get('files', {}).get('config/eloria/' + str(block.get('file')))
        if certified is None or certified != block.get('baseSha256'):
            raise AmendmentError(
                f'{block.get("id")}: written against {block.get("file")} '
                f'{str(block.get("baseSha256"))[:12]}, but the frozen profile certifies '
                f'{str(certified)[:12]}')
    return document


def _text(lines: list[str]) -> str:
    return ''.join(line + '\n' for line in lines)


def row_text(fields: list[str]) -> str:
    return ' | '.join(str(field) for field in fields)


def block_lines(block: dict, rows: list[list[str]] | None = None) -> list[str]:
    rows = [row['fields'] for row in block['rows']] if rows is None else rows
    return [block['begin'], *block.get('comments', []), *(row_text(fields) for fields in rows),
            block['end']]


def validate(document: dict | None, texts: dict[str, str], content: dict) -> None:
    """Refuse a block that could collide with a frozen row or with another block.

    ``texts`` are the frozen files by name, ``content`` the publisher's CONTENT
    table (keyword, map/x/y field indices, group, identity field).
    """
    if document is None:
        return
    seen_ids, seen_markers = set(), set()
    for block in document['blocks']:
        name = block.get('file')
        if name not in content:
            raise AmendmentError(f'{block.get("id")}: {name} is not an amendable content file')
        if name not in texts:
            raise AmendmentError(f'{block.get("id")}: frozen {name} is missing')
        if block.get('id') in seen_ids:
            raise AmendmentError(f'{block["id"]}: duplicate amendment block')
        seen_ids.add(block['id'])
        for field in ('begin', 'end'):
            if not str(block.get(field, '')).startswith('#'):
                raise AmendmentError(f'{block["id"]}: {field} must be a comment line')
        if any(not str(line).startswith('#') for line in block.get('comments', [])):
            raise AmendmentError(f'{block["id"]}: comments must be comment lines')
        keyword, mi, xi, yi, _, identity_index = content[name]
        old_tiles = set()
        identities = set()
        for number, line in enumerate(texts[name].splitlines(), 1):
            fields = [field.strip() for field in line.split('|')]
            if line.lstrip().startswith('#') or len(fields) <= max(mi, xi, yi):
                continue
            if fields[mi] == block['region']:
                old_tiles.add((int(fields[xi]), int(fields[yi])))
                if identity_index is not None:
                    identities.add(fields[identity_index])
        if not block['rows']:
            raise AmendmentError(f'{block["id"]}: a block must add rows')
        for row in block['rows']:
            fields = [str(field) for field in row['fields']]
            if keyword is not None and fields[0] != keyword or fields[mi] != block['region']:
                raise AmendmentError(f'{block["id"]}: {row_text(fields)} is not a {block["region"]} row')
            tile = (int(fields[xi]), int(fields[yi]))
            if tile in old_tiles:
                raise AmendmentError(f'{block["id"]}: source tile {tile} is already a {block["region"]} row')
            old_tiles.add(tile)
            if identity_index is not None:
                if fields[identity_index] in identities:
                    raise AmendmentError(f'{block["id"]}: identity {fields[identity_index]} is not unique')
                identities.add(fields[identity_index])
            marker = row.get('marker')
            if not isinstance(marker, str) or not marker or marker in seen_markers:
                raise AmendmentError(f'{block["id"]}: each row needs its own saved marker')
            seen_markers.add(marker)


def amend(texts: dict[str, str], document: dict | None) -> dict[str, str]:
    """``texts`` with every block appended to its file (a copy; files not named stay)."""
    result = dict(texts)
    if document is None:
        return result
    for block in document['blocks']:
        name = block['file']
        if name not in result:
            continue
        text = result[name]
        if block['begin'] in text:
            raise AmendmentError(f'{block["id"]}: the frozen {name} already carries this block')
        if text and not text.endswith('\n'):
            text += '\n'
        result[name] = text + _text(block_lines(block))
    return result


def row_lines(texts: dict[str, str], document: dict | None) -> dict[str, list[int]]:
    """Each block's row line numbers in the amended text, by block id."""
    result = {}
    if document is None:
        return result
    counts = {name: len(text.splitlines()) for name, text in texts.items()}
    for block in document['blocks']:
        name = block['file']
        start = counts[name] + 1 + 1 + len(block.get('comments', []))
        result[block['id']] = [start + index for index in range(len(block['rows']))]
        counts[name] += len(block_lines(block))
    return result


def served_blocks(texts: dict[str, str], document: dict, specs: dict, publisher) -> dict[str, list[str]]:
    """Each block's lines as the served files carry them after ``specs`` (a
    certified publication's regions, arranged as verify_current_profile does)."""
    amended = amend(texts, document)
    result = {}
    for block in document['blocks']:
        name = block['file']
        counts = publisher.content_source_tile_counts({name: amended[name]})
        served, _ = publisher.rewrite_content(amended[name], name, copy.deepcopy(specs), False, counts)
        lines = served.splitlines()
        begin = lines.index(block['begin'])
        result[block['id']] = lines[begin:begin + len(block_lines(block))]
    return result


def replace_block(text: str, lines: list[str], begin: str, end: str) -> str:
    """``text`` with the block between ``begin`` and ``end`` replaced (or appended)."""
    current = text.splitlines()
    if begin in current:
        start = current.index(begin)
        stop = current.index(end, start)
        current[start:stop + 1] = lines
    else:
        current.extend(lines)
    return _text(current)


def previous_specs(previous: dict) -> dict:
    """A publication's regions arranged the way verify_current_profile reads them."""
    specs = copy.deepcopy(previous['regions'])
    for spec in specs.values():
        spec['tilePositions'] = copy.deepcopy(spec['baselineTilePositions'])
        spec['previousServerOrigin'] = spec['baselineServerOrigin']
        spec['contentTransform'] = spec['baselineContentTransform']
        spec['removedInteractiveIds'] = spec['baselineRemovedInteractiveIds']
    return specs


def _publisher():
    tools = HERE.parents[2] / 'tools'
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    return importlib.import_module('publish_diagonal_continent')


def main() -> int:
    parser = argparse.ArgumentParser(description='Write or check the amended blocks in a served server profile.')
    parser.add_argument('--server', required=True, help='the paired server checkout')
    parser.add_argument('--check', action='store_true', help='report differences, write nothing')
    args = parser.parse_args()
    document = load()
    if document is None:
        print('no runtime content amendment')
        return 0
    publisher = _publisher()
    server = Path(args.server).resolve()
    baseline = HERE / 'legacy-server-profile/config/eloria'
    texts = {name: (baseline / name).read_text(encoding='utf-8') for name in publisher.CONTENT}
    validate(document, texts, publisher.CONTENT)
    manifest = json.loads((server / 'config/eloria/client_content_manifest.json').read_text(encoding='utf-8'))
    published = manifest.get('diagonalContinent', {}).get('publicationSha256')
    if not published:
        raise AmendmentError('the served profile has no certified publication to seat the rows by')
    history = HERE / 'publication-history' / f'{published}.json'
    previous = json.loads(history.read_text(encoding='utf-8'))
    served = served_blocks(texts, document, previous_specs(previous), publisher)
    stale = []
    for block in document['blocks']:
        path = server / 'config/eloria' / block['file']
        current = path.read_text(encoding='utf-8')
        wanted = replace_block(current, served[block['id']], block['begin'], block['end'])
        if wanted != current:
            stale.append(block['id'])
            if not args.check:
                # Profile files are hash-bound raw bytes: keep the file's own line ends.
                newline = '\r\n' if b'\r\n' in path.read_bytes() else '\n'
                path.write_text(wanted, encoding='utf-8', newline=newline)
                print(f'{block["id"]}: wrote {len(block["rows"])} rows to {block["file"]}')
    if args.check and stale:
        print('stale: ' + ', '.join(stale))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
