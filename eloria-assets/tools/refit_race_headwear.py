"""Refit the generated headwear to the rebuilt race bodies (P5), with the race clearance passes.

    python eloria-assets/tools/refit_race_headwear.py fit --out <scratch> [--tag t] [--pieces 3:134,...|all]
                                                     [--races all|<slug>,...] [--jobs 4] [--resume]
                                                     [--no-transfer] [--no-passes] [--stages] [--raw-from tag]
                                                     [--raw-only]
    python eloria-assets/tools/refit_race_headwear.py measure --out <scratch> [--tag t]
    python eloria-assets/tools/refit_race_headwear.py human-check --out <scratch> [--tag t]
    python eloria-assets/tools/refit_race_headwear.py install --out <scratch> [--tag t] --rigs <slug>,...
                                                     [--target-root <dir>] [--registry <json>] [--catalog <json>]

fit
    1. raw: every selected headwear piece (part 3) is fitted to every selected
       race body and to the Human body of each sex with the unchanged
       canonical fitter, refit_canonical_equipment.build_one -- the
       refit_human_bodies.py pattern (ce.RACES, batch.GENERATED and
       refit.SCRATCH overridden; never ``build()`` or ``--head-reference``,
       both broken for the races).  Output: ``<out>/raw/out/<tag>/<body>/``.
    2. race: on a race body the piece is the Human fit carried onto the race
       head (race_headwear_clearance.head_transfer: head size k about the eye
       anchor; the socket is carried the same way), then the passes
       headwear_race_policy.json names (helm or band growth, ear bulge,
       snout opening, feature or horn bulge, collar clearance, head bulge,
       horn pass-through).  All of it runs after the fitter, outside
       limb_head_remap.head_frame.  ``--raw-only`` stops after step 1.  On the Human bodies
       nothing runs: the final file is the raw fitter output byte for byte.
    The final piece and its record are ``<out>/<tag>/<body>/<slug>.glb`` /
    ``.fit.json``; ``<out>/<tag>-variants.json`` maps each visual key to its
    variants.  ``--stages`` also writes the piece after each pass under
    ``<out>/<tag>-stages/<stage>/<body>/``.  At most MAX_JOBS workers.

measure
    The gates for every fitted piece and for the installed variant on the same
    body: ear poke (cm2, mm), feature poke and feature-edge crossings, body
    edges crossing the piece (rebase_race_body.headwear_crossings' method) and
    the socket against the eye line -> ``<out>/<tag>-measure.json``.

human-check
    Compares every Human piece of the run with the installed
    ``canonical_human_<sex>`` variant accessor by accessor.

install
    First every fit record is checked against this checkout (asset, body,
    fitter and race-pass hashes, policy row) and audit_canonical_batch.py
    runs over the tag; then
    pack (pack_canonical_equipment.pack_glb into a stage) -> share textures
    (each image matched against the piece's base scene, ``models[key].scene``,
    and its Human variants; a match names the shipped file, anything else is
    re-encoded at <= 1024 px, JPEG 85, content-addressed) -> copy into
    ``equipment/variants/<race>/<slug>.glb`` and write
    ``models[key].variants["canonical_<race>"]`` only.  ``fitGroups`` is never
    touched.  ``--target-root``, ``--registry`` and ``--catalog`` redirect the
    writes (a dry run into scratch); by default they are this checkout's.

Nothing is written into the client except by ``install``.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CLIENT = ROOT / 'godot-client'
RACES_DIR = CLIENT / 'assets/actors/native/races'
EQUIPMENT_DIR = CLIENT / 'assets/actors/native/equipment'
REGISTRY = CLIENT / 'data/actors/equipment.json'
CATALOG = CLIENT / 'data/actors/native_asset_catalog.json'
GENERATED = ROOT.parents[1] / 'generate_models' / 'meshy-armor-individual-glb'
if not GENERATED.exists():
    GENERATED = ROOT.parent / 'generate_models' / 'meshy-armor-individual-glb'
RACE_BODIES = tuple(f'{race}_{sex}' for race in ('glasswarden', 'greyhaven', 'mycelari', 'orun',
                                                 'ssarathi', 'stoneborn', 'votary')
                    for sex in ('male', 'female'))
HUMAN_GROUP = {'luminous_male': 'canonical_human_male', 'luminous_female': 'canonical_human_female'}
STARTERS = ('3:134', '3:159', '3:115', '3:122')
OPEN_BANDS = ('3:111', '3:112', '3:119', '3:170')
#: Worker processes at most (machine safety: a fit worker holds a body, trimesh and scipy).
MAX_JOBS = 4


def digest(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def write_like(path: Path, value) -> None:
    """json.dumps(indent=2) + newline, in the line endings the file already has
    (the checkout is CRLF; git stores LF), so an install rewrites only what it
    changes."""
    path = Path(path)
    text = (json.dumps(value, indent=2) + '\n').encode('utf-8')
    if path.exists() and b'\r\n' in path.read_bytes()[:4096]:
        text = text.replace(b'\n', b'\r\n')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text)


def provenance() -> dict:
    """Hashes of what decides a race pass, beside the fitter's own tool_hashes."""
    names = ['race_headwear_clearance.py', 'refit_race_headwear.py', 'headwear_race_policy.json']
    return {n: digest(HERE / n) for n in names}


# ---------------------------------------------------------------------------
# fit
# ---------------------------------------------------------------------------

def _configure(bodies: Path, generated: Path, out: Path):
    import conform_equipment as ce
    import import_generated_equipment as batch
    import refit_canonical_equipment as refit
    ce.RACES = bodies
    batch.GENERATED = generated
    refit.SCRATCH = out / 'raw'
    return ce, batch, refit


def _read_piece(path: Path):
    import equipment_authoring as ea
    d, b = ea.read_glb(path)
    if len(d['meshes']) != 1 or len(d['meshes'][0]['primitives']) != 1:
        raise ValueError(f'{path}: expected one socket mesh with one primitive')
    p = d['meshes'][0]['primitives'][0]
    get = lambda i: ea.accessor_array(d, b, i)
    return (d, b, get(p['attributes']['POSITION']).astype(float), get(p['attributes']['TEXCOORD_0']).astype(float),
            get(p['indices']).astype(np.int64).reshape(-1, 3))


def _write_piece(raw_doc, raw_bin, out: Path, positions, uvs, faces):
    """Rewrite the raw fitter GLB with new geometry; images, material, node and
    mesh extras are carried over unchanged."""
    import copy
    import equipment_authoring as ea
    import limb_head_remap as lhr
    glb = ea.EquipmentGLB(generator=raw_doc['asset'].get('generator', 'Eloria anatomical equipment retarget'))
    doc = copy.deepcopy(raw_doc)
    views = {}
    for image in doc.get('images', []):
        if 'bufferView' in image:
            view = raw_doc['bufferViews'][image['bufferView']]
            start = view.get('byteOffset', 0)
            data = raw_bin[start:start + view['byteLength']]
            views[image['bufferView']] = glb.view(data)
            image['bufferView'] = views[image['bufferView']]
    normals = lhr.normals(positions, faces)
    primitive = glb.primitive(positions, normals, uvs, faces.ravel(),
                              doc['meshes'][0]['primitives'][0]['material'])
    for key in ('images', 'samplers', 'textures', 'materials', 'nodes', 'scenes', 'scene', 'asset'):
        if key in doc:
            glb.doc[key] = doc[key]
    mesh = dict(doc['meshes'][0])
    mesh['primitives'] = [primitive]
    glb.doc['meshes'] = [mesh]
    glb.write(out)


def _frame(record: dict) -> dict:
    return next(p for p in record['passes'] if p.get('name') == 'inner_cranium_frame')


def race_pass(body: Path, human: Path, key: str, raw: dict, human_raw: dict, out: Path,
              transfer: bool = True, passes: bool = True, stages: Path | None = None):
    """Carry the Human fit onto the race head, then the passes the policy names.

    ``raw`` / ``human_raw`` are build_one's records of the same piece on the
    race body and on the Human body of the same sex.  Returns (socket offset
    from the race Head, pass reports, transfer record)."""
    import race_headwear_clearance as rc
    rule = rc.policy(key)
    g = rc.head_geometry(str(body))
    d, b, p, uv, f = _read_piece(Path(raw['variant']['scene']))
    head = g.head[:3, 3]
    socket = head + np.asarray(raw['variant']['socket']['offset'], dtype=float)
    world = p + socket
    info = None
    kind = rule.get('kind')
    if transfer:
        info = rc.head_transfer(str(body), str(human))
        to_human = rc.frame_map(_frame(raw), _frame(human_raw))
        reference = to_human(world)
        world = rc.transfer_points(reference, info, drape=kind != 'helm')
        # The drape fade bends the carry over a few centimetres under the
        # chin: a bead or a buckle there would be turned inside out, so each
        # small part moves as one.
        if kind != 'helm':
            world = reference + rc.rigid_small_parts(reference, f, world - reference)
        # Every vertex carries its position in the Human fit through the
        # passes (as extra UV columns, interpolated wherever a pass splits or
        # cuts), so the collar pass can hold each point to the Human's clearance.
        uv = np.hstack([uv, reference])
        human_head = rc.head_geometry(str(human)).head[:3, 3]
        socket = rc.transfer_points(human_head + np.asarray(human_raw['variant']['socket']['offset'], dtype=float),
                                    info)

    def stage(name):
        if stages is not None:
            path = stages / name / body.stem / out.name
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_piece(d, b, path, world - socket, uv[:, :2], f)
    stage('s0transfer')
    reports = []

    def done(report):
        # The running count of faces turned over against the Human fit
        # (uv[:, 2:5] is each vertex's Human position): which pass made a hole.
        if info is not None:
            report['turnedOverSoFar'] = int(rc._flipped(uv[:, 2:5], world, f).sum())
        reports.append(report)
    rigid = kind == 'helm'
    band = kind == 'band'
    # Evening a bulge over faces it turns over is for single-sided materials
    # only (rc._bulge): every headwear material is double sided.
    even = not all(m.get('doubleSided') for m in d.get('materials', []))
    show = rule.get('raceFeatures') == 'show'
    if passes:
        if rigid and info is not None:
            world, r = rc.helm_grow(g, world, f, info['anchor'])
            done(r)
        if band and info is not None:
            # An open band leaves the hair, the scalp and the features drawn:
            # it is grown over the race's hair cap (every offered style) and a
            # crown or crystals as far as the Human band clears the Human's
            # own hair cap.  (Not the skin: a circlet's ribbons and a veil
            # hang across the face and neck by design.)
            hg = rc.head_geometry(str(human))
            ring = [rc.hair_cap(body.stem)]
            if show and g.feature_kind in ('crown', 'crystals'):
                ring.append(g.features)
            human_poke = rc.radial_poke(hg, rc._intersector(uv[:, 2:5][f]), rc.hair_cap(human.stem))['pokeCm2']
            world, r = rc.band_grow(g, world, f, info['anchor'], np.concatenate(ring),
                                    max(rc.BAND_ALLOWED_CM2, 1.2 * human_poke * info['k'] ** 2))
            done(r)
        ears = rule.get('ears') == 'tuck'
        if band and not ears:
            # An open band leaves the ears free, but a veil or a cloth top
            # hanging past them (3:112) must keep a race ear inside it.
            ears = rc.radial_poke(g, rc._intersector(world[f]), g.ears)['pokeCm2'] > 0
        if ears:
            world, f, uv, r = rc.ear_bulge(g, world, f, uv, rigid, even)
            r['band'] = band
            done(r)
        stage('s1ear')
        if rigid:
            world, f, uv, r = rc.snout_opening(g, world, f, uv)
            done(r)
        if show and g.feature_kind in ('crown', 'crystals'):
            if band:
                world, f, uv, r = rc.band_feature_bulge(g, world, f, uv, even)
            else:
                world, f, uv, r = rc.feature_bulge(g, world, f, uv, even)
            done(r)
        # Votary horns rise through a show hood (passThrough); an open band
        # rings the horn roots, so where a horn still crosses it the band is
        # draped over the root and opened like a hood.
        horns = g.feature_kind == 'horns' and (rule.get('horns') == 'passThrough' or (band and show))
        if horns:
            world, f, uv, r = rc.horn_bulge(g, world, f, uv, even)
            done(r)
        stage('s2feature')
        world, f, uv, r = rc.collar_clearance(g, world, f, uv,
                                              rc.head_geometry(str(human)) if info is not None else None)
        done(r)
        stage('s3collar')
        # Last of the pushes: whatever of the head or neck still comes through
        # (after the collar pass, which can lift a wrap into the throat).  One
        # round only: a second collar/head round turns faces over at the
        # throat (1830 on votary_male 3:159) for a few collar crossings.
        # (an open band too: a Ssarathi snout through a circlet's nose
        # pendant, a broad forehead through a headband's top)
        world, f, uv, r = rc.head_bulge(g, world, f, uv, show, rigid, even)
        done(r)
        stage('s4head')
        if horns:
            world, f, uv, r = rc.horn_pass_through(g, world, f, uv)
            done(r)
    if passes and info is not None:
        # Every vertex still carries its Human position (uv[:, 2:5]): a face
        # whose normal is reversed against the Human fit's has been turned
        # over by some pass and would read as a hole.
        reports.append(dict({'name': 'turned_over', 'flippedVsHuman': int(rc._flipped(uv[:, 2:5], world, f).sum()),
                             'triangles': int(len(f))}, **rc.seam_gaps(uv[:, 2:5], world)))
    _write_piece(d, b, out, world - socket, uv[:, :2], f)
    return (socket - head).tolist(), reports, info


def _raw_work(args):
    bodies, generated, out, slug, race, tag, body_hash, codes, resume = args
    bodies, generated, out = Path(bodies), Path(generated), Path(out)
    ce, batch, refit = _configure(bodies, generated, out)
    piece = next(p for p in batch.roster() if p.slug == slug)
    return refit.build_one(piece, race, tag, body_hash, codes, resume, None, None)


def _post_work(args):
    bodies, out, slug, race, tag, raw_tag, body_hash, codes, transfer, passes, stages = args
    import race_headwear_clearance as rc
    bodies, out = Path(bodies), Path(out)
    raw_dir = out / 'raw' / 'out' / raw_tag
    raw = json.loads((raw_dir / race / f'{slug}.fit.json').read_text())
    key = raw['key']
    final = out / tag / race / f'{slug}.glb'
    final.parent.mkdir(parents=True, exist_ok=True)
    record = {'key': key, 'slug': slug, 'race': race, 'raw': raw['variant']['scene'],
              'rawSHA256': raw['asset_sha256'], 'bodySHA256': body_hash, 'toolSHA256': codes,
              'raceToolSHA256': provenance(), 'fit': raw['passes']}
    if rc.is_race_body(race):
        human = bodies / f'{rc.human_slug(race)}.glb'
        human_raw = json.loads((raw_dir / human.stem / f'{slug}.fit.json').read_text())
        offset, reports, info = race_pass(bodies / f'{race}.glb', human, key, raw, human_raw, final,
                                          transfer, passes, out / f'{tag}-stages' if stages else None)
        variant = dict(raw['variant'], scene=final.as_posix())
        variant['socket'] = dict(raw['variant']['socket'], offset=offset)
        record.update(policy=rc.policy(key), transfer=info, humanRawSHA256=human_raw['asset_sha256'],
                      racePasses=reports)
    else:
        shutil.copyfile(raw['variant']['scene'], final)
        variant = dict(raw['variant'], scene=final.as_posix())
        record.update(policy=None, transfer=None, racePasses=[])
    # audit_canonical_batch.py reads race, slug and asset_sha256 from every record
    record['asset_sha256'] = digest(final)
    record['variant'] = variant
    write_json(final.with_suffix('.fit.json'), record)
    return record


def _keys_to_slugs(batch, wanted: str):
    roster = [p for p in batch.roster() if p.part == 3]
    if wanted == 'all':
        return roster
    keys = set(wanted.split(','))
    chosen = [p for p in roster if f'{p.part}:{p.visual}' in keys or p.slug in keys]
    found = {f'{p.part}:{p.visual}' for p in chosen} | {p.slug for p in chosen}
    missing = keys - found
    if missing:
        raise SystemExit(f'unknown headwear: {sorted(missing)}')
    return chosen


def _pool(jobs):
    return ProcessPoolExecutor(max_workers=max(1, min(jobs, MAX_JOBS)))


def cmd_fit(args) -> int:
    import race_headwear_clearance as rc
    ce, batch, refit = _configure(args.bodies, args.generated, args.out)
    pieces = _keys_to_slugs(batch, args.pieces)
    if not pieces:
        raise SystemExit(f'no generated sources under {args.generated}')
    bands = [f'{p.part}:{p.visual}' for p in pieces if f'{p.part}:{p.visual}' in OPEN_BANDS]
    if bands:
        print(f'note: {bands} read the INSTALLED hair (headwear_envelope.py); fit them after the hair install')
    races = list(RACE_BODIES) if args.races == 'all' else args.races.split(',')
    # The Human of each sex is always fitted: every race fit is carried from it.
    fitted = list(dict.fromkeys(races + [rc.human_slug(r) for r in races]))
    codes = refit.tool_hashes()
    hashes = {race: digest(args.bodies / f'{race}.glb') for race in fitted}
    summary = {'tag': args.tag, 'bodies': hashes, 'toolSHA256': codes, 'raceToolSHA256': provenance(),
               'transfer': not args.no_transfer, 'passes': not args.no_passes, 'variants': {}, 'failures': []}
    raw_tag = args.raw_from or args.tag
    raw_work = [(str(args.bodies), str(args.generated), str(args.out), p.slug, race, raw_tag, hashes[race], codes,
                 args.resume or bool(args.raw_from)) for p in pieces for race in fitted]
    failed = set()
    summary['rawTag'] = raw_tag
    with _pool(args.jobs) as pool:
        futures = {pool.submit(_raw_work, w): w for w in raw_work}
        for done, future in enumerate(as_completed(futures), 1):
            w = futures[future]
            try:
                future.result()
            except Exception as exc:  # keep going; every failure is reported at the end
                failed.add((w[3], w[4]))
                summary['failures'].append({'stage': 'raw', 'slug': w[3], 'race': w[4], 'error': repr(exc)[:400]})
                print(f'raw {done}/{len(raw_work)} FAILED {w[4]} {w[3]}: {exc!r}'[:300], flush=True)
    print(f'raw: {len(raw_work) - len(failed)}/{len(raw_work)} built', flush=True)
    if args.raw_only:
        write_json(args.out / f'{raw_tag}-raw.json', summary)
        return 1 if summary['failures'] else 0
    post_work =[(str(args.bodies), str(args.out), p.slug, race, args.tag, raw_tag, hashes[race], codes,
                  not args.no_transfer, not args.no_passes, args.stages)
                 for p in pieces for race in fitted
                 if (p.slug, race) not in failed and (p.slug, rc.human_slug(race)) not in failed]
    with _pool(args.jobs) as pool:
        futures = {pool.submit(_post_work, w): w for w in post_work}
        for done, future in enumerate(as_completed(futures), 1):
            w = futures[future]
            try:
                record = future.result()
            except Exception as exc:
                summary['failures'].append({'stage': 'race', 'slug': w[2], 'race': w[3], 'error': repr(exc)[:400]})
                print(f'{done}/{len(post_work)} FAILED {w[3]} {w[2]}: {exc!r}'[:300], flush=True)
                continue
            group = HUMAN_GROUP.get(record['race'], 'canonical_' + record['race'])
            summary['variants'].setdefault(record['key'], {})[group] = record['variant']
            k = record['transfer']['k'] if record.get('transfer') else None
            print(f"{done}/{len(post_work)} {record['race']} {record['key']} {record['slug']} k={k} "
                  + ' '.join(f"{r['name']}:{r.get('maxMm', r.get('openings'))}" for r in record['racePasses']),
                  flush=True)
    write_json(args.out / f'{args.tag}-variants.json', summary)
    print(f"{len(summary['variants'])} keys, {len(summary['failures'])} failures -> "
          f"{args.out / (args.tag + '-variants.json')}")
    return 1 if summary['failures'] else 0


# ---------------------------------------------------------------------------
# measure / human-check
# ---------------------------------------------------------------------------

def measure_code_digest() -> str:
    """The source of everything a measurement reads (not the passes): the
    cached rows of the installed variants stay valid while only a pass changes."""
    import inspect
    import race_headwear_clearance as rc
    names = ('measure', 'radial_poke', 'edge_crossings', '_ray_extents', '_intersector', '_chunks',
             'piece_triangles', 'head_geometry', '_fit_cranium', '_protrusion', '_edges_of', '_triangles',
             'hair_cap', '_samples', 'policy', 'collar_clip', '_exposed_collar', '_first_hit')
    source = ''.join(inspect.getsource(getattr(rc, n)) for n in names)
    constants = repr([getattr(rc, n) for n in ('FEATURE_MM', 'COLLAR_NECK_BELOW_EYE', 'BAND_HAIR_REACH', 'RAY_CHUNK',
                                               'COLLAR_UNDER_SHIRT', 'COLLAR_CLIP_DEPTH')])
    return hashlib.sha256((source + constants).encode()).hexdigest()


def _measure_work(args):
    bodies, slug, rows = args
    import race_headwear_clearance as rc
    g = rc.head_geometry(str(Path(bodies) / f'{slug}.glb'))
    eye = g.eye_y
    out = []
    for key, which, scene, socket in rows:
        socket_world = g.head[:3, 3] + np.asarray(socket, dtype=float)
        tris = rc.piece_triangles(scene, socket_world)
        m = rc.measure(g, tris, key)
        m.update(key=key, body=slug, which=which, scene=str(scene),
                 socketToEyeMm=round(float(socket_world[1] - eye) * 1000, 2),
                 lowestY=round(float(tris[..., 1].min()), 4))
        out.append(m)
    return out


def cmd_measure(args) -> int:
    import race_headwear_clearance as rc
    summary = json.loads((args.out / f'{args.tag}-variants.json').read_text())
    registry = json.loads(REGISTRY.read_text(encoding='utf-8'))
    jobs = {}
    for key, variants in summary['variants'].items():
        for group, variant in variants.items():
            slug = next((r for r, g in HUMAN_GROUP.items() if g == group), group.removeprefix('canonical_'))
            if not rc.is_race_body(slug):
                # The Human fit on its own body: the baseline a race fit's
                # collar crossings are read against.
                jobs.setdefault(slug, []).append((key, 'human', variant['scene'], variant['socket']['offset']))
                continue
            rows = jobs.setdefault(slug, [])
            rows.append((key, 'trial', variant['scene'], variant['socket']['offset']))
            installed = registry['models'][key].get('variants', {}).get(group)
            if installed:
                rows.append((key, 'installed', str(CLIENT / installed['scene'].removeprefix('res://')),
                             installed['socket']['offset']))
    # The installed variants do not change between trial tags: their rows are
    # cached by body and file digest.
    cache_path = args.out / f'installed-measure-cache-{measure_code_digest()[:12]}.json'
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    body_sha = {slug: digest(args.bodies / f'{slug}.glb') for slug in jobs}
    results, todo = [], {}
    for slug, rows in jobs.items():
        for row in rows:
            ckey = f"{body_sha[slug]}:{digest(row[2])}:{row[3]}" if row[1] == 'installed' else None
            if ckey and ckey in cache:
                results.append(dict(cache[ckey], key=row[0], body=slug, which='installed', scene=row[2]))
            else:
                todo.setdefault(slug, []).append(row)
    # A few rows per task, so the workers stay busy to the end (a body with
    # horns or a crown takes several times as long as one without).
    tasks = [(str(args.bodies), s, rows[i:i + 8]) for s, rows in sorted(todo.items()) for i in range(0, len(rows), 8)]
    with _pool(args.jobs) as pool:
        for rows in pool.map(_measure_work, tasks):
            for row in rows:
                results.append(row)
                if row['which'] == 'installed':
                    offset = next(r[3] for r in jobs[row['body']] if r[0] == row['key'] and r[1] == 'installed')
                    cache[f"{body_sha[row['body']]}:{digest(row['scene'])}:{offset}"] = row
    write_json(cache_path, cache)
    human_rows = {(r['key'], r['body']): r for r in results if r['which'] == 'human'}
    results = [r for r in results if r['which'] != 'human']
    for row in results:
        base = human_rows.get((row['key'], rc.human_slug(row['body'])))
        row['humanCollarCrossings'] = base['collarCrossings'] if base else None
        # the Human fit's own gate values: what a race fit is read against
        row['humanRow'] = {k: base[k] for k in ('ears', 'skin', 'neck', 'hairCap', 'collarCrossings', 'collarClipCm2')
                           if base and k in base}
        # The gate: socket to eye line against the Human's of the same piece,
        # scaled by the head size the transfer measured.
        slug, human = row['body'], rc.human_slug(row['body'])
        info = rc.head_transfer(str(args.bodies / f'{slug}.glb'), str(args.bodies / f'{human}.glb'))
        hv = summary['variants'][row['key']].get(HUMAN_GROUP[human]) \
            or registry['models'][row['key']]['variants'][HUMAN_GROUP[human]]
        h = rc.head_geometry(str(args.bodies / f'{human}.glb'))
        human_mm = float(h.head[1, 3] + hv['socket']['offset'][1] - h.eye_y) * 1000
        row['humanSocketToEyeMm'] = round(human_mm, 2)
        row['headSize'] = info['k']
        row['socketTargetMm'] = round(human_mm * info['k'], 2)
    write_json(args.out / f'{args.tag}-measure.json', results)
    print(f"{len(results)} rows -> {args.out / (args.tag + '-measure.json')}")
    return 0


def cmd_human_check(args) -> int:
    import equipment_authoring as ea
    summary = json.loads((args.out / f'{args.tag}-variants.json').read_text())
    registry = json.loads(REGISTRY.read_text(encoding='utf-8'))
    rows, bad = [], 0
    for key, variants in sorted(summary['variants'].items()):
        for group in HUMAN_GROUP.values():
            if group not in variants:
                continue
            final = Path(variants[group]['scene'])
            raw = json.loads(final.with_suffix('.fit.json').read_text())['raw']
            installed = CLIENT / registry['models'][key]['variants'][group]['scene'].removeprefix('res://')
            d1, b1 = ea.read_glb(final)
            d2, b2 = ea.read_glb(installed)
            same = len(d1['accessors']) == len(d2['accessors']) and all(
                np.array_equal(ea.accessor_array(d1, b1, i), ea.accessor_array(d2, b2, i))
                for i in range(len(d1['accessors'])))
            socket = variants[group]['socket'] == registry['models'][key]['variants'][group]['socket']
            row = {'key': key, 'group': group, 'finalEqualsRaw': digest(final) == digest(raw),
                   'accessorsEqualInstalled': bool(same), 'socketEqualInstalled': socket}
            bad += not all(v for k, v in row.items() if k not in ('key', 'group'))
            rows.append(row)
            print(json.dumps(row))
    write_json(args.out / f'{args.tag}-human-check.json', rows)
    return 1 if bad else 0


# ---------------------------------------------------------------------------
# install: pack -> share -> copy, variants only
# ---------------------------------------------------------------------------

def _thumb(data: bytes):
    from PIL import Image
    return np.asarray(Image.open(io.BytesIO(data)).convert('RGB').resize((64, 64), Image.BILINEAR)).astype(np.float32)


def _scene_images(path: Path) -> list[Path]:
    import equipment_authoring as ea
    if not path.exists():
        return []
    d, _ = ea.read_glb(path)
    return [(path.parent / i['uri']).resolve() for i in d.get('images', []) if 'uri' in i]


def share_textures(staged: Path, target: Path, model: dict, stage: Path) -> list[dict]:
    """Point a packed variant's images at the textures its piece already ships.

    Candidates are the images of the base scene (``model['scene']``) and of
    every Human variant of the piece; a 64 px thumbnail within 3/255 mean
    difference is the same picture.  Anything else is re-encoded the shipped
    way into the stage.  Returns one record per image.
    """
    import pack_canonical_equipment as pack
    from PIL import Image
    candidates = []
    for scene in [model.get('scene', '')] + [v.get('scene', '') for g, v in model.get('variants', {}).items()
                                              if g in HUMAN_GROUP.values()]:
        if scene.startswith('res://'):
            candidates += _scene_images(CLIENT / scene.removeprefix('res://'))
    thumbs = [(p, _thumb(p.read_bytes())) for p in dict.fromkeys(candidates) if p.exists()]
    d, b = pack.ea.read_glb(stage / target)
    records = []
    for image in d.get('images', []):
        current = (stage / target).parent / image['uri']
        data = current.read_bytes()
        t = _thumb(data)
        score, match = min(((float(np.abs(t - bt).mean()), p) for p, bt in thumbs), default=(1e9, None))
        if score < 3.0:
            texture = pack.PREFIX / 'textures' / match.name
            records.append({'image': current.name, 'shared': match.name, 'difference': round(score, 3)})
        else:
            im = Image.open(io.BytesIO(data)).convert('RGB')
            if max(im.size) > 1024:
                im = im.resize(tuple(round(s * 1024 / max(im.size)) for s in im.size), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, 'JPEG', quality=85, optimize=True)
            encoded = buf.getvalue()
            texture = pack.PREFIX / 'textures' / ('canonical_' + hashlib.sha256(encoded).hexdigest() + '.jpg')
            (stage / texture).parent.mkdir(parents=True, exist_ok=True)
            (stage / texture).write_bytes(encoded)
            records.append({'image': current.name, 'reencoded': texture.name, 'difference': round(score, 3)})
        image['uri'] = os.path.relpath(texture, target.parent).replace('\\', '/')
        image['mimeType'] = 'image/jpeg' if texture.suffix == '.jpg' else 'image/png'
        records[-1]['texture'] = texture.as_posix()
    from share_human_equipment_textures import write
    import struct
    raw = (stage / target).read_bytes()
    n = struct.unpack('<I', raw[12:16])[0]
    write(stage / target, d, raw[20 + n:])
    return records


def verify_records(args, summary, rigs) -> None:
    """Refuse an install whose fits no longer describe this checkout: every
    final piece must still hash as recorded, on the same body, with the same
    fitter, race passes and policy row; then audit_canonical_batch.py runs
    over the whole tag (asset hashes, images, binds, triangles, shells)."""
    import race_headwear_clearance as rc
    import refit_canonical_equipment as refit
    import audit_canonical_batch as audit
    codes, race_codes = refit.tool_hashes(), provenance()
    problems = []
    for key, variants in summary['variants'].items():
        for race in rigs:
            variant = variants.get('canonical_' + race)
            if variant is None:
                problems.append(f'{key} {race}: not fitted')
                continue
            final = Path(variant['scene'])
            record = json.loads(final.with_suffix('.fit.json').read_text())
            checks = {'asset': digest(final) == record['asset_sha256'],
                      'body': digest(args.bodies / f'{race}.glb') == record['bodySHA256'],
                      'fitter': record['toolSHA256'] == codes,
                      'race passes': record['raceToolSHA256'] == race_codes,
                      'policy': record['policy'] == rc.policy(key)}
            problems += [f'{key} {race}: {name} changed since the fit' for name, ok in checks.items() if not ok]
    if problems:
        raise SystemExit('refusing to install:\n  ' + '\n  '.join(problems[:40]))
    if audit.audit(args.out / args.tag, args.out / f'{args.tag}-audit.json'):
        raise SystemExit(f"audit_canonical_batch failed: {args.out / (args.tag + '-audit.json')}")


def cmd_install(args) -> int:
    import pack_canonical_equipment as pack
    rigs = [r for r in args.rigs.split(',') if r]
    unknown = [r for r in rigs if r not in RACE_BODIES]
    if unknown:
        raise SystemExit(f'install writes race variants only; not a race body: {unknown}')
    summary = json.loads((args.out / f'{args.tag}-variants.json').read_text())
    if summary['failures']:
        raise SystemExit('the fit reported failures; fix them before installing')
    verify_records(args, summary, rigs)
    target_root = args.target_root or ROOT
    registry_path = args.registry or REGISTRY
    registry = json.loads(Path(registry_path).read_text(encoding='utf-8'))
    groups_before = json.dumps(registry['fitGroups'], sort_keys=True)
    stage = args.out / 'packed' / args.tag
    if stage.exists():
        shutil.rmtree(stage)
    installed, textures, shares = [], set(), []
    for key, variants in sorted(summary['variants'].items()):
        model = registry['models'][key]
        for race in rigs:
            group = 'canonical_' + race
            if group not in variants:
                continue
            variant = variants[group]
            source = Path(variant['scene'])
            target = pack.PREFIX / 'variants' / race / source.name
            pack.pack_glb(source, target, stage)
            for record in share_textures(stage, target, model, stage):
                shares.append(dict(record, key=key, race=race))
                if 'reencoded' in record:
                    textures.add(record['texture'])
            dest = Path(target_root) / target
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage / target, dest)
            entry = {'scene': 'res://' + target.relative_to('godot-client').as_posix(),
                     'authoredFor': race, 'fitProfile': 'canonical', 'socket': variant['socket']}
            model.setdefault('variants', {})[group] = entry
            installed.append(dest)
    for texture in sorted(textures):
        dest = Path(target_root) / texture
        data = (stage / texture).read_bytes()
        if dest.exists() and dest.read_bytes() != data:
            raise SystemExit(f'{dest} exists with different bytes')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    if json.dumps(registry['fitGroups'], sort_keys=True) != groups_before:
        raise SystemExit('fitGroups changed; refusing to write the registry')
    write_like(Path(registry_path), registry)
    catalog = refresh_catalog(installed, Path(target_root), args.catalog or CATALOG)
    report = {'variants': len(installed), 'sharedImages': sum('shared' in s for s in shares),
              'reencodedImages': sum('reencoded' in s for s in shares), 'newTextures': sorted(textures),
              'catalog': catalog, 'shares': shares}
    write_json(args.out / f'{args.tag}-install.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'shares'}))
    return 0


def refresh_catalog(installed: list[Path], target_root: Path, catalog_path) -> dict:
    """validate_glb for each installed race variant, keyed like the builders key theirs."""
    from build_native_nymara_glbs import validate_glb
    catalog_path = Path(catalog_path)
    source = catalog_path if catalog_path.exists() else CATALOG
    catalog = json.loads(source.read_text(encoding='utf-8'))
    results = catalog.setdefault('validation', {}).setdefault('results', {})
    for path in installed:
        results[path.relative_to(target_root).as_posix()] = validate_glb(path)
    if Path(target_root).resolve() == ROOT.resolve():
        catalog['validation']['files'] = len(list((CLIENT / 'assets/actors/native').rglob('*.glb')))
    if not catalog_path.exists() and source.exists():
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_bytes(source.read_bytes())
    write_like(catalog_path, catalog)
    return {'validated': len(installed), 'files': catalog['validation'].get('files')}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='command', required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--out', type=Path, required=True)
    common.add_argument('--tag', default='race')
    common.add_argument('--bodies', type=Path, default=RACES_DIR)
    common.add_argument('--jobs', type=int, default=4)
    fit = sub.add_parser('fit', parents=[common])
    fit.add_argument('--generated', type=Path, default=GENERATED)
    fit.add_argument('--pieces', default=','.join(STARTERS))
    fit.add_argument('--races', default='all')
    fit.add_argument('--resume', action='store_true')
    fit.add_argument('--no-transfer', action='store_true',
                     help="keep the fitter's own seat (diagnostic)")
    fit.add_argument('--raw-from', metavar='TAG',
                     help='reuse the raw fitter builds of an earlier tag (resumed: checked unchanged)')
    fit.add_argument('--stages', action='store_true',
                     help='also write the piece after each pass under <out>/<tag>-stages/<stage>/')
    fit.add_argument('--no-passes', action='store_true')
    fit.add_argument('--raw-only', action='store_true',
                     help='stop after the raw fitter builds (reuse them later with --raw-from)')
    sub.add_parser('measure', parents=[common])
    sub.add_parser('human-check', parents=[common])
    inst = sub.add_parser('install', parents=[common])
    inst.add_argument('--rigs', required=True)
    inst.add_argument('--target-root', type=Path)
    inst.add_argument('--registry', type=Path)
    inst.add_argument('--catalog', type=Path)
    args = ap.parse_args()
    if args.out.resolve().is_relative_to(ROOT.resolve()):
        raise SystemExit('--out must be outside the checkout (the default refit SCRATCH is not gitignored)')
    return {'fit': cmd_fit, 'measure': cmd_measure, 'human-check': cmd_human_check,
            'install': cmd_install}[args.command](args)


if __name__ == '__main__':
    raise SystemExit(main())
