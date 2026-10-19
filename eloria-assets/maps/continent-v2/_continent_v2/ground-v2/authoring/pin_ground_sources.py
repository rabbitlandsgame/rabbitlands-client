"""Pin the generated edit rasters into ground-v2/sources and the recipe (crop to their weighted extent).

python pin_ground_sources.py
Reads island-ground/{fills-*,north-*,southeast-*} and fills-meta.json / <isle>-meta.json; writes
ground-v2/sources/<edit>.{heights.f32le,colors.rgba8,height-weights.u8,color-weights.u8}, the recipe's "edits"
and sources.json (generator hashes), and copies the generators into ground-v2/authoring/.
"""
import hashlib, json, shutil
from pathlib import Path
import numpy as np

STAGE = Path(__file__).resolve().parents[1]
IG = STAGE / 'island-ground'
G = Path(r'C:/rabbitlands/worktrees/a3-cli/eloria-assets/maps/continent-v2/_continent_v2/ground-v2')
NOTES = {
    'north-isle': 'Meshy continent GLB (sha256 42c88739...) surface at offset (3560,-1650): z-buffered at 2 m, the vertical '
                  'curve applied, objects opened away, heights x0.5 (walkable share like the main isle\'s hill maps), the '
                  'approved A3 draft coast (fine warp), coastal taper, citadel terrace pad, pits filled',
    'south-east-isle': 'Meshy continent GLB (sha256 42c88739...) surface at offset (3000,-1620), heights x0.5, lagoon '
                       'lowland within 260 m of Tollholm and Spindle Hill, the approved A3 draft coast (fine warp) kept 8 m '
                       'clear of the berths and sea lanes, temple summit pad, pits filled',
}
FILLS_NOTE = ('the approved A3 draft new-land mask (drafts.py compose(A3)) resampled to 2 m; harmonic join to the old coast '
              '(at most 6 m), plain bands by area, 40 m shelf, colours inpainted from inland land, old beach band repainted')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    items = []
    for w in json.load(open(IG / 'fills-meta.json'))['windows']:
        items.append(('strait-fills-' + w['window'], 'fills-' + w['window'], w['firstVertex'], w['gridSize'], 'strait_fills.py'))
    for name, eid in (('north', 'north-isle'), ('southeast', 'south-east-isle')):
        m = json.load(open(IG / f'{name}-meta.json'))
        items.append((eid, name, m['firstVertex'], m['gridSize'], 'island_ground.py'))
    recipe = json.load(open(G / 'recipe.json', encoding='utf-8'))
    (G / 'sources').mkdir(exist_ok=True)
    edits, notes = [], {}
    for eid, stem, first, size, gen in items:
        w, h = size
        eh = np.fromfile(IG / f'{stem}-heights.f32le', '<f4').reshape(h, w)
        ec = np.fromfile(IG / f'{stem}-colors.rgba8', np.uint8).reshape(h, w, 4)
        wh = np.fromfile(IG / f'{stem}-wh.u8', np.uint8).reshape(h, w)
        wc = np.fromfile(IG / f'{stem}-wc.u8', np.uint8).reshape(h, w)
        rr, cc = np.nonzero((wh > 0) | (wc > 0))
        r0, r1, c0, c1 = rr.min(), rr.max() + 1, cc.min(), cc.max() + 1
        files = {}
        for key, arr, ext in (('heights', eh, 'heights.f32le'), ('colors', ec, 'colors.rgba8'),
                              ('heightWeights', wh, 'height-weights.u8'), ('colorWeights', wc, 'color-weights.u8')):
            b = np.ascontiguousarray(arr[r0:r1, c0:c1]).tobytes()
            rel = f'sources/{eid}.{ext}'
            (G / rel).write_bytes(b)
            files[key] = {'path': rel, 'sha256': sha(b), 'bytes': len(b)}
        edits.append({'id': eid, 'kind': 'raster', 'firstVertex': [float(first[0] + 2 * c0), float(first[1] + 2 * r0)],
                      'gridSize': [int(c1 - c0), int(r1 - r0)], 'files': files})
        notes[eid] = {'generator': {'path': 'authoring/' + gen, 'sha256': sha((STAGE / 'tools' / gen).read_bytes())},
                      'note': NOTES.get(eid, FILLS_NOTE)}
    recipe['edits'] = edits
    (G / 'recipe.json').write_text(json.dumps(recipe, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    (G / 'authoring').mkdir(exist_ok=True)
    for gen in ('strait_fills.py', 'island_ground.py'):
        shutil.copyfile(STAGE / 'tools' / gen, G / 'authoring' / gen)
    draft = IG / 'a3-draft-newland.npz'
    doc = {'about': 'How each pinned raster was made. The generators are copied here for the record; they read private '
                    'inputs that stay outside Git: the Meshy continent GLB (sha256 42c887398a86d6f3675cf1e5396234d972b3544fb'
                    '795e877d6cfa4771f155d30) and the A3 draft mask (work-output drafts.py compose(A3)), and the staged base '
                    'from build_continent_v2_ground.py --base.',
           'draftMask': {'file': 'a3-draft-newland.npz', 'sha256': sha(draft.read_bytes())}, 'edits': notes}
    (G / 'sources.json').write_text(json.dumps(doc, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    for e in edits:
        print(e['id'], e['firstVertex'], e['gridSize'])


if __name__ == '__main__':
    main()
