"""Audit every completed candidate; report all faults instead of stopping early."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

import equipment_authoring as ea
import refit_canonical_equipment as refit
import pack_canonical_equipment as pack

# Independent GLB topology reader used by the regression suite.
sys.path.insert(0, str(refit.ROOT / "godot-client/tests"))
from test_equipment_fit import _shells


def audit(directory, out):
    rows, failures = [], []
    for record in sorted(directory.glob('*/*.fit.json')):
        report = json.loads(record.read_text())
        path = record.with_suffix('').with_suffix('.glb')
        label = f"{report['race']}/{report['slug']}"
        try:
            if refit.digest(path) != report['asset_sha256']:
                raise ValueError('Candidate hash changed')
            row = dict(race=report['race'], slug=report['slug'], **pack.validate(path, report['race']))
            rig = refit.cached_rig(report['race'])
            document, binary = ea.read_glb(path)
            row['closed_shells'] = 0
            for mesh in document['meshes']:
                mesh_closed, mesh_volume = 0, 0.
                for part in mesh['primitives']:
                    v=ea.accessor_array(document,binary,part['attributes']['POSITION'])
                    f=ea.accessor_array(document,binary,part['indices']).reshape(-1,3)
                    for shell in _shells(v,f):
                        if not shell.closed:continue
                        mesh_closed += 1;mesh_volume += max(0.,shell.volume)
                        if shell.volume < -1e-10:
                            failures.append(f"{label}/{mesh['name']}: inward closed shell {shell.volume:.9g} m3")
                row['closed_shells'] += mesh_closed
                if mesh['name'].startswith(('GeneratedArmorBacking','GeneratedLegBacking','GeneratedBootBacking')) and (not mesh_closed or mesh_volume < 1e-9):
                    failures.append(f"{label}/{mesh['name']}: no closed lining volume")
            primitive = document['meshes'][0]['primitives'][0]
            attrs = primitive['attributes']
            positions = ea.accessor_array(document, binary, attrs['POSITION'])
            used = np.unique(ea.accessor_array(document, binary, primitive['indices']))
            row['art_min'] = positions[used].min(axis=0).tolist()
            row['art_max'] = positions[used].max(axis=0).tolist()
            if report.get('region') == 'boots':
                row['soles_mm'] = {}
                names = rig.joint_names
                for side in ('l', 'r'):
                    chain = [i for i, name in enumerate(names) if name.endswith('_' + side)]
                    all_floors, art_floors = [], []
                    for mesh_index, mesh in enumerate(document['meshes']):
                        for p in mesh['primitives']:
                            a = p['attributes']
                            v = ea.accessor_array(document, binary, a['POSITION'])
                            j = ea.accessor_array(document, binary, a['JOINTS_0'])
                            w = ea.accessor_array(document, binary, a['WEIGHTS_0']).astype(float)
                            u = np.unique(ea.accessor_array(document, binary, p['indices']))
                            own = (w[u] * np.isin(j[u], chain)).sum(axis=1) > w[u].sum(axis=1) * .5
                            if not own.any():
                                continue
                            floor = float(v[u[own], 1].min())
                            all_floors.append(floor)
                            if mesh_index == 0:
                                art_floors.append(floor)
                    sole = ea.weighted_sole(rig, side)
                    sink = 1000 * (sole - min(all_floors))
                    float_mm = 1000 * (min(art_floors) - sole)
                    row['soles_mm'][side] = {'sink': sink, 'floating': float_mm}
                    if sink > 8.0001 or float_mm > 8.0001:
                        failures.append(f'{label} {side}: sink {sink:.3f}, floating {float_mm:.3f} mm')
            if report.get('region') == 'legs':
                low, high = row['art_min'][1], row['art_max'][1]
                sole = max(ea.weighted_sole(rig, s) for s in ('l', 'r'))
                if low < sole + .020 or low > rig.origin('calf_l')[1] - .020 or high < rig.origin('spine_01')[1]:
                    failures.append(f'{label}: source hem/waist {low:.4f}/{high:.4f}')
            rows.append(row)
        except Exception as error:
            failures.append(f'{label}: {type(error).__name__}: {error}')
    result = {'completed_assets': len(rows), 'failures': failures, 'assets': rows}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(f'CANONICAL_AUDIT assets={len(rows)} failures={len(failures)}')
    for failure in failures:
        print(failure)
    return bool(failures)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    sys.exit(audit(args.directory, args.out))
