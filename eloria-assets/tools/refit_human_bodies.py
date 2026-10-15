"""Fit the generated equipment to the regenerated Human bodies, as a Human-only variant set.

    python eloria-assets/tools/refit_human_bodies.py --bodies <dir> --out <scratch> [--pieces a,b|all] [--jobs 4]

The Human bodies regenerated on 2026-10-05 replaced `luminous_male` and
`luminous_female`; every piece is fitted to the new bodies here and recorded
under `canonical_human_male` / `canonical_human_female`. Since the race rebase
every race shares these bodies below the neck and falls back to the Human
fits, and since the race programme's P7 cleanup (2026-10) each generated
piece's base scene is its `canonical_human_male` file: the older
`canonical_luminous_*` fits and the old-male base scenes they were built on
are deleted.

`--bodies` holds the new `luminous_male.glb` / `luminous_female.glb` (the
packed client files). They are both the fitting body and the torso anatomy
reference (refit_canonical_equipment's `--anatomy-reference`), since there is
no older retained source for these bodies. Headwear is fitted to the new heads
the same way. Nothing is written into the client; the output is scratch GLBs,
per-piece fit reports, and `human-variants.json` mapping each visual key to
its two variants.
"""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')

RACES = ('luminous_male', 'luminous_female')
GROUP = {'luminous_male': 'canonical_human_male', 'luminous_female': 'canonical_human_female'}


def _configure(bodies: Path, generated: Path, out: Path):
    import conform_equipment as ce
    import import_generated_equipment as batch
    import refit_canonical_equipment as refit
    ce.RACES = bodies
    batch.GENERATED = generated
    refit.SCRATCH = out
    return ce, batch, refit


def _work(args):
    bodies, generated, out, slug, race, tag, body_hash, codes, resume = args
    ce, batch, refit = _configure(Path(bodies), Path(generated), Path(out))
    piece = next(p for p in batch.roster() if p.slug == slug)
    anatomy = str(bodies) if piece.part == 5 else None
    return refit.build_one(piece, race, tag, body_hash, codes, resume, None, anatomy)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--bodies', type=Path, required=True)
    ap.add_argument('--generated', type=Path,
                    default=Path(__file__).resolve().parents[4] / 'generate_models' / 'meshy-armor-individual-glb')
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--pieces', default='all')
    ap.add_argument('--tag', default='human')
    ap.add_argument('--jobs', type=int, default=4)
    ap.add_argument('--resume', action='store_true')
    args = ap.parse_args()
    ce, batch, refit = _configure(args.bodies, args.generated, args.out)
    roster = batch.roster()
    if not roster:
        raise SystemExit(f'no generated sources under {args.generated}')
    wanted = None if args.pieces == 'all' else set(args.pieces.split(','))
    pieces = [p for p in roster if wanted is None or p.slug in wanted]
    missing = (wanted or set()) - {p.slug for p in pieces}
    if missing:
        raise SystemExit(f'unknown pieces: {sorted(missing)}')
    codes = refit.tool_hashes()
    hashes = {race: refit.digest(args.bodies / f'{race}.glb') for race in RACES}
    work = [(str(args.bodies), str(args.generated), str(args.out), p.slug, race, args.tag,
             hashes[race], codes, args.resume) for p in pieces for race in RACES]
    variants: dict = {}
    failures = []
    done = 0
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(_work, w): w for w in work}
        for future in as_completed(futures):
            w = futures[future]
            done += 1
            try:
                report = future.result()
            except Exception as exc:  # keep going; report every failure at the end
                failures.append({'slug': w[3], 'race': w[4], 'error': repr(exc)[:400]})
                print(f'{done}/{len(work)} FAILED {w[4]} {w[3]}: {exc!r}'[:300], flush=True)
                continue
            variants.setdefault(report['key'], {})[GROUP[report['race']]] = report['variant']
            print(f"{done}/{len(work)} {report['race']} {report['slug']}", flush=True)
    summary = {'bodies': {r: hashes[r] for r in RACES}, 'variants': variants, 'failures': failures}
    (args.out / f'{args.tag}-variants.json').write_text(json.dumps(summary, indent=1) + '\n')
    print(f'{len(variants)} keys, {len(failures)} failures -> {args.out / (args.tag + "-variants.json")}')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
