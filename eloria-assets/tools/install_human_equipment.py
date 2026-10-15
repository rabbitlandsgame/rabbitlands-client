"""Pack and install the Human-only equipment variants built by refit_human_bodies.py.

    python eloria-assets/tools/install_human_equipment.py <fit scratch dir> [--tag human] [--stage <dir>]
    python eloria-assets/tools/install_human_equipment.py --catalog-only

Each fitted GLB is packed with pack_canonical_equipment.pack_glb (images moved
to the shared content-addressed `equipment/textures/canonical_<sha>` files,
accessors checked byte-equal after packing) into a scratch stage, then copied
to `equipment/variants/human_male|human_female/<slug>.glb`.  A texture that
already ships is reused; one that exists with different bytes stops the run.

The registry gains, for every fitted visual key, two variants:

    canonical_human_male   -> variants/human_male/<slug>.glb
    canonical_human_female -> variants/human_female/<slug>.glb

with `authoredFor` set to `human_male` / `human_female`.  Those keys have no
girth or foot-anchor entries, so the client wears each variant exactly as it
was fitted (no runtime widening or sole drop); headwear keeps the socket the
fitter measured on the new head.  `fitGroups` for luminous_male/female list
only their Human group (`[canonical_human_male]` / `[canonical_human_female]`).
The retired canonical_luminous_* fits and the old-male base scenes they fell
back to were deleted in the race programme's P7 cleanup (2026-10); a model
whose base scene is its canonical_human_male file keeps its base fields
(authoredFor, fitProfile, socket) equal to that variant's, so the install
refreshes them with the variant.  No other race's groups change; race variants
are installed by refit_race_headwear.py `install`, which writes variants only.

The registry and the catalogue are written as json.dumps(indent=2) with the
platform's line endings, which is what git's autocrlf checks out (CRLF here).

Every install then refreshes native_asset_catalog.json's structural inventory
(refresh_catalog_validation): a validate_glb result for each installed
variant, entries for removed files dropped, and `validation.files` set to the
GLBs actually on disk, which test_catalog_is_complete compares.
`--catalog-only` re-runs just that step over what is installed.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pack_canonical_equipment as pack

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / 'godot-client'
GROUP = {'canonical_human_male': 'human_male', 'canonical_human_female': 'human_female'}
RIG = {'canonical_human_male': 'luminous_male', 'canonical_human_female': 'luminous_female'}
NATIVE = CLIENT / 'assets/actors/native'
CATALOG = CLIENT / 'data/actors/native_asset_catalog.json'


def refresh_catalog_validation(catalog_path: Path = CATALOG) -> dict:
    """Record validate_glb for every installed Human variant and recount the inventory.

    The results are build_native_nymara_glbs.validate_glb, keyed by the
    repo-relative POSIX path, exactly as the builder and expand_hairstyles
    record theirs.  Results for Human variant files no longer on disk are
    dropped; every other entry is left as it is.  `validation.files` is the
    number of GLBs under assets/actors/native.
    """
    from build_native_nymara_glbs import validate_glb

    catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
    results = catalog.setdefault('validation', {}).setdefault('results', {})
    folders = [NATIVE / 'equipment' / 'variants' / folder for folder in sorted(set(GROUP.values()))]
    prefixes = tuple(folder.relative_to(ROOT).as_posix() + '/' for folder in folders)
    installed = {path.relative_to(ROOT).as_posix(): path
                 for folder in folders for path in sorted(folder.glob('*.glb'))}
    removed = [key for key in results if key.startswith(prefixes) and key not in installed]
    for key in removed:
        del results[key]
    added = [key for key in installed if key not in results]
    for key, path in installed.items():
        results[key] = validate_glb(path)
    on_disk = {path.relative_to(ROOT).as_posix() for path in NATIVE.rglob('*.glb')}
    catalog['validation']['files'] = len(on_disk)
    catalog_path.write_text(json.dumps(catalog, indent=2) + '\n', encoding='utf-8')
    return {'validated': len(installed), 'added': len(added), 'removed': len(removed),
            'files': len(on_disk),
            'unrecorded': sorted(on_disk - set(results)), 'stale': sorted(set(results) - on_disk)}


def apply_variant(model: dict, group: str, entry: dict) -> None:
    """Record one installed variant; a base that IS the human_male file follows it.

    Fields are assigned in place, so a reinstall of the same fit leaves the
    registry byte-identical (key order included); `socket` is dropped from the
    base only when the new fit has none.
    """
    model.setdefault('variants', {})[group] = entry
    if group == 'canonical_human_male' and model.get('scene') == entry['scene']:
        # The base IS this variant's file (P7): keep its fields equal.
        for field, value in entry.items():
            model[field] = value
        if 'socket' not in entry:
            model.pop('socket', None)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('fit', type=Path, nargs='?')
    ap.add_argument('--tag', default='human')
    ap.add_argument('--stage', type=Path)
    ap.add_argument('--catalog-only', action='store_true',
                    help='only refresh the catalogue inventory for the variants already installed')
    args = ap.parse_args()
    if args.catalog_only:
        print(json.dumps(refresh_catalog_validation()))
        return 0
    if args.fit is None:
        ap.error('the fit scratch dir is required unless --catalog-only')
    summary = json.loads((args.fit / f'{args.tag}-variants.json').read_text())
    if summary['failures']:
        raise SystemExit('the fit reported failures; fix them before installing')
    stage = args.stage or args.fit / 'packed' / args.tag
    if stage.exists():
        shutil.rmtree(stage)
    registry_path = CLIENT / 'data/actors/equipment.json'
    registry = json.loads(registry_path.read_bytes())
    new_textures, reused, installed = set(), set(), 0
    for key, variants in sorted(summary['variants'].items()):
        model = registry['models'][key]
        for group, variant in sorted(variants.items()):
            folder = GROUP[group]
            source = Path(variant['scene'])
            target = pack.PREFIX / 'variants' / folder / source.name
            for texture in pack.pack_glb(source, target, stage):
                dest = ROOT / texture
                data = (stage / texture).read_bytes()
                if dest.exists():
                    if dest.read_bytes() != data:
                        raise SystemExit(f'{dest} exists with different bytes')
                    reused.add(texture)
                else:
                    new_textures.add(texture)
            (ROOT / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage / target, ROOT / target)
            entry = {'scene': 'res://' + target.relative_to('godot-client').as_posix(),
                     'authoredFor': folder, 'fitProfile': 'canonical'}
            if 'socket' in variant:
                entry['socket'] = variant['socket']
            apply_variant(model, group, entry)
            installed += 1
    for texture in sorted(new_textures):
        (ROOT / texture).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(stage / texture, ROOT / texture)
    for group, rig in RIG.items():
        registry['fitGroups'][rig] = [group]
    registry_path.write_text(json.dumps(registry, indent=2) + '\n', encoding='utf-8')
    catalog = refresh_catalog_validation()
    print(json.dumps({'variants': installed, 'new_textures': len(new_textures), 'reused_textures': len(reused),
                      'catalog': catalog}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
