"""Landfall A3 owner partition: 18 sections on the ground v2 lattice.

python partition_a3.py [--write] [--preview]

Unchanged maps keep their A2 rings byte for byte. Changed and new maps are written as explicit rings on odd metres,
reusing A2 vertices wherever a border survives; each new border is listed once (CHAINS) and used reversed by both
neighbours. Checks (all on the ground v2 lattice, cell centres as the bootstrap/authority uses them):
  * every ring simple and valid, every vertex on odd integer metres;
  * no cell centre strictly inside two sections; every land cell owned;
  * boat-only: no land cell of the south-east isle maps touches a land cell of another map;
  * reported borders (shapely boundary intersections) for check_report.json.
--write puts sections_spec.json and check_report.json into partition-inputs-a3/ of the a3-cli worktree.
"""
import json, sys, hashlib
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from shapely.geometry import Polygon, MultiPolygon, LineString
from shapely.ops import unary_union
from shapely import orient_polygons

REPO = Path(r'C:/rabbitlands/worktrees/a3-cli')
META = REPO / 'eloria-assets/maps/continent-v2/_continent_v2'
A2 = META / 'partition-inputs'
OUT = META / 'partition-inputs-a3'
GROUND = META / 'group-terrain-v2'
PREVIEW = Path(__file__).resolve().parents[1] / 'partition-a3-preview.png'

# ---- new borders (each used by both neighbours) -------------------------------------------------------------
# Saltsound | Ringholm: x=2259 from Hearthcroft's corridor up to Ringholm island's NW corner, then ~12-16 m off the
# island's north coast, then east across the filled stub and north at x=3061 (Saltsound's translation x 2059
# allows at most 1023 m east); the shelf's east tip and the sea beyond are Ringholm's.
C5 = [(2259, 6717), (2259, 6611), (2301, 6599), (2331, 6581), (2391, 6567), (2451, 6577), (2511, 6595), (2571, 6605),
      (2631, 6629), (2691, 6661), (2751, 6703), (2861, 6651), (3011, 6621), (3061, 6621), (3061, 6561)]
# Hearthcroft | Ravenhead: ~10-15 m off Ravenhead headland's north coast (B14 fill = Hearthcroft's crofts)
C3 = [(1959, 6921), (1999, 6931), (2041, 6955), (2101, 6993), (2161, 7037), (2221, 7075), (2259, 7093)]
# Hearthcroft | Ringholm: x=2259 down to the headland (the B14 bridge's landing notch returns to Ringholm)
C2 = [(2259, 6717), (2259, 7093)]
# Ringholm | Ravenhead: past the headland's north-east tip, then through the sea gap south of the sound fill
C4 = [(2259, 7093), (2283, 7139), (2301, 7173), (2331, 7181), (2401, 7189), (2471, 7211), (2541, 7229), (2621, 7191),
      (2729, 7171), (2761, 7171)]
# Greenlight | Ravenhead: west of the B22 bar's north-east coast (the bars = Greenlight)
C7 = [(1849, 7371), (1961, 7631), (2001, 7671), (2311, 7671)]
# Ravenhead | coilmere: z=7671 kept, the corner over the new ground's north coast ceded
C8 = [(2311, 7671), (2719, 7671), (2729, 7671), (2761, 7671), (2761, 7591)]
# (revision 3: Jadestair merged into Coilmere; their A2 spindle/tollholm border C6 is gone)
# coilmere | suncoil: 55 m west of the temple ring path, then ~50 m south of it (the south arm round the lagoon's
# inner bay is Coilmere's coves), then down to the sea
C9 = [(3201, 7591), (3201, 8651)]
# hornmere | whitepeak: Whitepeak takes the Whitehorn ridge and the west lobe; the Mirrorhold citadel terrace
# (1250, 5465) and both mirror lakes stay in Hornmere; both reach the mainland's sea at z 6131 so both preload from
# Stagheath (revision 4: the border moved north from z 6221, so Stagheath and Saltsound own water for their quays)
NORTH = 6131
C11 = [(1351, 5021), (1351, NORTH)]


def rev(chain):
    return list(reversed(chain))


def ring(*parts):
    """Concatenate chains; consecutive duplicates (shared end points) dropped."""
    out = []
    for part in parts:
        for p in part:
            if not out or tuple(out[-1]) != tuple(p):
                out.append(tuple(p))
    if out[0] == out[-1]:
        out.pop()
    return out


def sections_a3(a2):
    R = {s['id']: [[tuple(int(v) for v in p) for p in r] for r in s['ownershipPolygons']] for s in a2['sections']}
    new = {}
    for keep in ('landfall', 'warrenmead', 'stagheath', 'twinbrook', 'reedfall', 'brambleshaw', 'pinebrow', 'boarsend'):
        new[keep] = R[keep]
    # Stagheath's north edge follows the north isle border north (it was A2's z 6221)
    new['stagheath'] = [[(x, NORTH if z == 6221 else z) for x, z in r] for r in R['stagheath']]
    new['saltsound'] = [ring([(1919, 6781), (1939, 6849), (2259, 6717)], C5[1:],
                             [(3061, 6371), (2201, 6371), (2201, NORTH), (1459, NORTH), (1459, 6761), (1459, 6811),
                              (1479, 6821), (1639, 6821)])]
    new['hearthcroft'] = [ring([(1939, 6849), (1919, 6781), (1639, 6821), (1479, 6821), (1489, 6911), (1519, 6961),
                                (1599, 7041), (1609, 7151), (1689, 7151), (1729, 7201), (1949, 7221)], C3, rev(C2))]
    new['ringholm'] = [ring(C2, C4, [(3231, 7171), (3231, 6561)], rev(C5))]
    new['ravenhead'] = [ring([(2761, 7171)], rev(C8), rev(C7), [(1949, 7221)], C3, C4)]
    new['greenlight'] = [ring([(1675, 7941), (1685, 8259), (2311, 8259)], rev(C7), [(1699, 7581), (1575, 7601),
                                                                                    (1575, 7655), (1629, 7701)])]
    # the south edge steps up west of x 2723: the sea south of the knob belongs to no map
    new['coilmere'] = [ring(C8, [(3201, 7591)], C9, [(2723, 8651), (2723, 8461), (2311, 8461), (2311, 8259)])]
    new['suncoil'] = [ring([(3201, 7471), (4101, 7471), (4101, 8701), (3201, 8701)], rev(C9))]
    new['hornmere'] = [ring([(621, NORTH), (621, 5021)], C11)]
    new['whitepeak'] = [ring(rev(C11), [(2031, 5021), (2031, NORTH)])]
    return new


ORDER = ['hearthcroft', 'ringholm', 'greenlight', 'coilmere', 'suncoil', 'landfall', 'warrenmead',
         'stagheath', 'twinbrook', 'reedfall', 'brambleshaw', 'saltsound', 'ravenhead', 'pinebrow', 'boarsend',
         'hornmere', 'whitepeak']
LABELS = {'coilmere': 'Coilmere', 'suncoil': 'Suncoil', 'hornmere': 'Hornmere',
          'whitepeak': 'Whitepeak'}
SUCCESSORS = {'coilmere': 'tollholm'}  # Coilmere also absorbs Spindle Hill (via Jadestair, plan-amendments mergedMaps)
COLOURS = {'coilmere': '#3fb8a8', 'suncoil': '#d9b13b', 'hornmere': '#9fc4e8', 'whitepeak': '#f2f4f8'}
SE_ISLE = {'coilmere', 'suncoil'}
NORTH_ISLE = {'hornmere', 'whitepeak'}


def main():
    a2 = json.load(open(A2 / 'sections_spec.json', encoding='utf-8'))
    secs = sections_a3(a2)
    assert set(secs) == set(ORDER), set(secs) ^ set(ORDER)
    prov = json.load(open(GROUND / 'terrain-provenance.json'))
    W, H = prov['grid']['gridSize']; x0, z0 = (int(v) for v in prov['grid']['continentFirstVertex'])
    hts = np.fromfile(GROUND / 'base-heights.f32le', '<f4').reshape(H, W)
    problems = []
    shapes = {}
    for rid in ORDER:
        polys = []
        for r in secs[rid]:
            for x, z in r:
                if x % 2 != 1 or z % 2 != 1:
                    problems.append(f'{rid}: vertex off the odd lattice {x},{z}')
            p = Polygon(r)
            if not p.is_valid or not p.exterior.is_simple:
                problems.append(f'{rid}: invalid ring')
            polys.append(p)
        shapes[rid] = unary_union(polys)
    # cell-centre ownership (cells between vertices; centre = vertex + 1 m), priority order as the spec states
    xs = x0 + 2 * np.arange(W - 1) + 1.0; zs = z0 + 2 * np.arange(H - 1) + 1.0
    owner = np.zeros((H - 1, W - 1), np.int16)
    count = np.zeros((H - 1, W - 1), np.int16)
    for i, rid in enumerate(ORDER):
        im = Image.new('L', (W - 1, H - 1), 0); d = ImageDraw.Draw(im)
        for r in secs[rid]:
            d.polygon([((x - x0) / 2 - 1.0, (z - z0) / 2 - 1.0) for x, z in r], fill=255)
        m = np.array(im) > 0
        count += m
        owner[(owner == 0) & m] = i + 1
    # strict double ownership: PIL fills boundary pixels of both neighbours, so judge strict interiors by shapely
    over = []
    for i, a in enumerate(ORDER):
        for b in ORDER[i + 1:]:
            inter = shapes[a].intersection(shapes[b])
            if inter.area > 1e-6:
                over.append((a, b, round(inter.area, 3)))
    if over:
        problems.append(f'overlapping sections: {over}')
    cell_land = (hts[:-1, :-1].astype(float) + hts[1:, :-1] + hts[:-1, 1:] + hts[1:, 1:]) / 4 > 0
    unowned = cell_land & (owner == 0)
    if unowned.any():
        lab, n = ndimage.label(unowned)
        for k in range(1, min(n, 8) + 1):
            rr, cc = np.nonzero(lab == k)
            problems.append(f'unowned land: {len(rr) * 4} m2 near ({int(xs[cc].mean())}, {int(zs[rr].mean())})')
    # boat-only: the south-east isle's land never shares an edge with another map's land
    idx = {rid: i + 1 for i, rid in enumerate(ORDER)}
    se = np.isin(owner, [idx[r] for r in SE_ISLE]) & cell_land
    other = ~np.isin(owner, [idx[r] for r in SE_ISLE]) & (owner > 0) & cell_land
    if (ndimage.binary_dilation(se) & other).any():
        problems.append('boat-only broken: south-east isle land touches another map')
    # borders
    borders = []
    for i, a in enumerate(ORDER):
        for b in ORDER[i + 1:]:
            line = shapes[a].boundary.intersection(shapes[b].boundary)
            if line.length > 0.5:
                borders.append({'between': [a, b], 'length_m': int(round(line.length))})
    # land stats
    stats = {}
    for i, rid in enumerate(ORDER):
        m = owner == i + 1
        stats[rid] = {'landM2': int((m & cell_land).sum() * 4), 'bounds': [int(v) for v in shapes[rid].bounds]}
    for rid in ORDER:
        print(f"{rid:12s} land {stats[rid]['landM2'] / 1e6:6.3f} km2  bounds {stats[rid]['bounds']}")
    print('borders', len(borders))
    print('problems', problems or 'none')
    if '--preview' in sys.argv:
        rgb = np.zeros((H - 1, W - 1, 3)); rgb[:] = (30, 60, 100)
        rng = np.random.default_rng(3); pal = rng.integers(60, 255, (len(ORDER) + 1, 3)); pal[0] = (30, 60, 100)
        img = pal[owner].astype(float)
        img = np.where(cell_land[..., None], img, img * 0.35 + np.array([30, 60, 100]) * 0.65)
        im = Image.fromarray(img.astype(np.uint8)).resize(((W - 1) // 2, (H - 1) // 2), Image.NEAREST)
        d = ImageDraw.Draw(im)
        for rid in ORDER:
            for r in secs[rid]:
                d.line([((x - x0) / 4, (z - z0) / 4) for x, z in r + [r[0]]], fill=(255, 255, 255), width=1)
            c = shapes[rid].representative_point()
            d.text(((c.x - x0) / 4 - 20, (c.y - z0) / 4), rid, fill=(0, 0, 0))
        im.save(PREVIEW)
    if '--write' in sys.argv:
        if problems:
            raise SystemExit('refusing to write with problems')
        write(a2, secs, shapes, stats, borders)


def write(a2, secs, shapes, stats, borders):
    by = {s['id']: s for s in a2['sections']}
    by_map = {s['mapId']: s for s in a2['sections']}
    sections = []
    for rid in ORDER:
        src = by.get(rid) or by_map.get(rid) or by_map.get(SUCCESSORS.get(rid, ''))
        sec = {}
        if src and rid not in SUCCESSORS and src['mapId'] == rid:
            sec = json.loads(json.dumps(src))
        sec.update({'id': rid, 'mapId': rid, 'label': LABELS.get(rid, sec.get('label', rid.title())),
                    'colour': COLOURS.get(rid, sec.get('colour', '#888888')),
                    'ownershipPolygons': [[[int(x), int(z)] for x, z in r] for r in secs[rid]],
                    'bounds': stats[rid]['bounds'], 'landM2': stats[rid]['landM2']})
        if rid in SUCCESSORS:
            sec['successorOf'] = SUCCESSORS[rid]
        elif rid == 'suncoil':
            sec['environmentFrom'] = 'coilmere'; sec['lookBase'] = 'coilmere'
        elif rid in NORTH_ISLE:
            sec['environmentFrom'] = 'stagheath'; sec['lookBase'] = 'stagheath'
        if json.dumps(sec['ownershipPolygons']) != json.dumps(src['ownershipPolygons'] if src and src['mapId'] == rid else None):
            for key in ('serverCellsEstimate', 'islandLandVertices2m', 'placements', 'placementsBySourceScene',
                        'markers', 'spawnRows', 'spawnLevels'):
                sec.pop(key, None)
        sections.append(sec)
    spec = {'schema': 'eloria-landfall-split-sections-v2',
            'frame': a2['frame'],
            'source': {'predecessor': {'path': 'eloria-assets/maps/continent-v2/_continent_v2/partition-inputs/sections_spec.json',
                                       'sha256': hashlib.sha256((A2 / 'sections_spec.json').read_bytes()).hexdigest()},
                       'ground': 'eloria-assets/maps/continent-v2/_continent_v2/group-terrain-v2/terrain-provenance.json',
                       'brief': 'Landfall A3, approved by the owner 2026-10-19: strait fills, a boat-only Verdant + Ssarathi '
                                'isle replacing Spindle Hill and Tollholm (fresh ids), a north Whitehorn + Mirrorhold isle; '
                                'revised the same day: near-rectangular borders, open sea unassigned, Jadestair merged '
                                'into Coilmere, the north isle border at z 6131 for the boat quays'},
            # jadestair: Spindle Hill's A3 successor, merged into Coilmere before release (owner 2026-10-19)
            'retiredMapIds': a2['retiredMapIds'] + ['spindle_hill', 'tollholm', 'jadestair'],
            'priorityNote': 'Sections are in priority order: a point exactly on a border belongs to the section listed first. '
                            'Unchanged A2 borders keep their exact vertex chains; new borders are shared vertex chains on '
                            'the odd-metre lattice. The south-east isle (coilmere, suncoil) shares no land '
                            'with any other map (boat-only); every isle shares sea borders with its neighbours so it preloads.',
            'sections': sections}
    OUT.mkdir(exist_ok=True)
    (OUT / 'sections_spec.json').write_text(json.dumps(spec, indent=1, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')
    report = {'uncoveredIslandVertices': 0, 'doubleOwnedCells': 0, 'mainlandVerticesOwned': 0,
              'servedDomainSymmetricDifferenceM2': None, 'borders': borders}
    (OUT / 'check_report.json').write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('written', OUT)


if __name__ == '__main__':
    main()
