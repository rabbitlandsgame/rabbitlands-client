"""Extract approved paintings into unframed item cells (offline authoring).

The private source plan and original images stay in .local/asset-authoring.
The resulting compact painted sheet is sufficient for public atlas rebuilds.
This processes existing artwork; it does not generate or render any models.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / '.local/asset-authoring/working/item-icon-audit'
BACKGROUND = (5, 15, 18, 255)
CELL = 50
SOURCE_COLUMNS = 20
# The original painted tools/weapon bundle pointed up-right, opposite the
# concept-derived equipment. Reflect their art as well as the new equipment.
ORIGINAL_EQUIPMENT_MIRRORS = {5, 6, 7, 38, 39, 52, 53}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(source: Path) -> Image.Image:
    """Remove the neutral paper backing, preserving the original painting."""
    image = Image.open(source).convert('RGBA')
    image.thumbnail((512, 512), Image.Resampling.LANCZOS)
    if image.getchannel('A').getextrema()[0] < 200:
        return image.crop(image.getbbox())
    rgb = np.asarray(image.convert('RGB'))
    height, width = rgb.shape[:2]
    mask = np.zeros((height, width), np.uint8)
    # Include the paper inside the source's white outside margin in the
    # background sample. Sampling only that white margin retained beige paper.
    border_x = max(4, round(width * .065))
    border_y = max(4, round(height * .045))
    cv2.setRNGSeed(31)
    cv2.grabCut(rgb, mask,
                (border_x, border_y, width - border_x * 2, height - border_y * 2),
                np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64),
                5, cv2.GC_INIT_WITH_RECT)
    alpha = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(alpha)
    if count < 2:
        raise ValueError(f'No foreground extracted from {source.name}')
    threshold = max(25, stats[1:, cv2.CC_STAT_AREA].max() * .012)
    keep = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] > threshold]
    alpha = np.where(np.isin(labels, keep), 255, 0).astype(np.uint8)
    cutout = Image.fromarray(np.dstack((rgb, alpha)))
    bounds = cutout.getbbox()
    if bounds is None:
        raise ValueError(f'Empty extracted artwork: {source.name}')
    return cutout.crop(bounds)


def framed_cell(path: Path, index: int) -> Image.Image:
    """Recover the same interior the classic UI previously displayed."""
    image = Image.open(path).convert('RGBA')
    x, y = index % 5 * CELL, index // 5 * CELL
    return image.crop((x + 8, y + 8, x + 42, y + 42))


def compose(image: Image.Image, extent: int = 42) -> Image.Image:
    cell = Image.new('RGBA', (CELL, CELL), BACKGROUND)
    artwork = ImageOps.contain(image, (extent, extent), Image.Resampling.LANCZOS)
    cell.alpha_composite(artwork, ((CELL - artwork.width) // 2,
                                 (CELL - artwork.height) // 2))
    return cell


def facing_left(image: Image.Image) -> bool:
    """Boot toes project beyond the ankle; frontal pairs need no reflection."""
    alpha = np.asarray(image.getchannel('A')) > 100
    h = alpha.shape[0]
    ankle = np.where(alpha[int(h * .35):int(h * .65)])[1]
    toes = np.where(alpha[int(h * .8):])[1]
    return not (ankle.size and toes.size and toes.mean() - ankle.mean() > image.width * .035)


# Existing, independently painted bottle concepts, selected for effect/color.
# The last source concept is an alchemist case and is intentionally excluded.
POTION_ART = {
    474: ('concept', 0, 34), 475: ('original', 3, 38),
    476: ('concept', 1, 42), 477: ('original', 4, 34),
    478: ('concept', 2, 40), 479: ('original', 60, 42),
    480: ('original', 68, 42), 481: ('concept', 3, 40),
    482: ('concept', 12, 40), 483: ('concept', 14, 40),
    484: ('concept', 13, 40), 485: ('original', 62, 40),
    486: ('concept', 21, 40), 487: ('concept', 11, 40),
    488: ('original', 91, 40), 489: ('concept', 6, 40),
    490: ('concept', 19, 40), 491: ('concept', 23, 40),
    492: ('concept', 7, 40), 493: ('concept', 5, 40),
    494: ('concept', 8, 40), 495: ('original', 84, 40),
    496: ('concept', 22, 40), 497: ('concept', 10, 40),
    498: ('concept', 20, 40), 499: ('concept', 17, 40),
    500: ('concept', 6, 42), 501: ('concept', 5, 42),
    502: ('concept', 16, 40), 503: ('concept', 10, 42),
    504: ('concept', 4, 40), 505: ('original', 78, 34),
    570: ('original', 74, 40), 571: ('original', 68, 38),
    572: ('concept', 21, 38), 573: ('concept', 14, 38),
    574: ('concept', 23, 42), 575: ('original', 84, 38),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=WORK)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--draft', action='store_true')
    args = parser.parse_args()
    work = args.work
    records = {r['imageId']: r for r in json.loads((work / 'source-map.json').read_text())}
    generated = {r['id']: r for r in json.loads((work / 'generated.json').read_text(encoding='utf-8-sig'))}
    flips_path = work / 'orientation.json'
    overrides = json.loads(flips_path.read_text()) if flips_path.exists() else {}
    originals = work / 'before-atlases'
    cache = work / 'extracted'
    cache.mkdir(exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    source_root = ROOT / '.local/asset-authoring/workspace/concept_art'
    index = {p.stem: p for p in source_root.rglob('*.png')}
    cv2.setNumThreads(1)
    source_sheet = Image.new('RGBA', (SOURCE_COLUMNS * CELL, 30 * CELL))
    items = []
    for image_id in range(599):
        rec = dict(records.get(image_id, {}))
        metadata = {'imageId': image_id, 'name': rec.get('name', f'Original item {image_id}'),
                    'mirrorX': False, 'rotationDegrees': 0}
        if image_id < 118:
            source = originals / f'items{image_id // 25 + 1}.png'
            art = framed_cell(source, image_id % 25)
            metadata.update(sourceKind='original-painted-interior', source=source.name,
                            sourceSha256=digest(source))
            if image_id in ORIGINAL_EQUIPMENT_MIRRORS:
                art = ImageOps.mirror(art)
                metadata['mirrorX'] = True
            # Match the existing crop while replacing its decorative perimeter.
            cell = compose(art, 44)
        elif image_id in POTION_ART:
            family, local, extent = POTION_ART[image_id]
            if family == 'concept':
                source = ROOT / 'eloria-assets/concepts/item-icons/12_potions_elixirs.png'
                art = framed_cell(source, local)
            else:
                source = originals / f'items{local // 25 + 1}.png'
                art = framed_cell(source, local % 25)
            metadata.update(sourceKind='painted-potion-concept', source=source.name,
                            sourceCell=local, extent=extent, sourceSha256=digest(source))
            cell = compose(art, extent)
        elif image_id in generated:
            supplied = generated[image_id]
            source = Path(supplied['path'])
            art = Image.open(source).convert('RGBA')
            if art.getchannel('A').getextrema()[0] != 0:
                raise ValueError(f'Generated item {image_id} lacks transparent background')
            art = art.crop(art.getbbox())
            metadata.update(sourceKind='individual-generated-painting', source=source.name,
                            sourceSha256=digest(source), prompt=supplied['prompt'],
                            generatedWith='built-in image_gen', attempt=1,
                            dimensions=list(Image.open(source).size), generationDate='2026-10-18',
                            productionMode='single inventory illustration',
                            camera='isolated front three-quarter', verdict='pass',
                            references=[{'path': 'godot-client/assets/ui/items/items1.png',
                                         'sha256': digest(originals / 'items1.png')}])
            cell = compose(art, 42)
        elif rec.get('concept') or 576 <= image_id <= 583:
            source = ROOT / rec['concept'] if rec.get('concept') else index[
                f'Eight_legendary_fantasy_leg_armor_designs__r{(image_id-576)//4+1:02d}_c{(image_id-576)%4+1:02d}']
            cached = cache / f'{image_id}.png'
            cache_key = digest(source) + ':neutral-paper-cutout-v1'
            cache_receipt = cached.with_suffix('.json')
            current_cache = (cache_receipt.exists()
                             and json.loads(cache_receipt.read_text()).get('key') == cache_key)
            if cached.exists() and current_cache:
                art = Image.open(cached).convert('RGBA')
            else:
                art = extract(source)
                if 576 <= image_id <= 583:
                    art = art.crop((0, round(art.height * .64), art.width, art.height))
                    art = art.crop(art.getbbox())
                art.save(cached)
                cache_receipt.write_text(json.dumps({'key': cache_key}) + '\n')
            metadata.update(sourceKind='equipment-concept-cutout', source=source.name,
                            sourceSha256=digest(source))
            kind = rec.get('kind', '')
            if rec.get('part') == 6 and not facing_left(art):
                art = ImageOps.mirror(art)
                metadata['mirrorX'] = True
            if rec.get('family') == 'weapon' and kind in {
                    'axe', 'crossbow', 'dagger', 'greatsword', 'mace', 'maul',
                    'polearm', 'spear', 'staff', 'sword', 'wand', 'whip'}:
                angle = 225 if kind in {'sword', 'greatsword', 'dagger'} else 45
                art = art.rotate(angle, Image.Resampling.BICUBIC, expand=True)
                art = art.crop(art.getbbox())
                metadata['rotationDegrees'] = angle
            if str(image_id) in overrides:
                instruction = overrides[str(image_id)]
                if instruction.get('mirrorX'):
                    art = ImageOps.mirror(art)
                    metadata['mirrorX'] = not metadata['mirrorX']
                if instruction.get('rotate'):
                    angle = instruction['rotate']
                    art = art.rotate(angle, Image.Resampling.BICUBIC, expand=True)
                    art = art.crop(art.getbbox())
                    metadata['rotationDegrees'] = (metadata['rotationDegrees'] + angle) % 360
            cell = compose(art)
        elif args.draft:
            source = originals / f'items{image_id // 25 + 1}.png'
            cell = compose(framed_cell(source, image_id % 25))
            metadata.update(sourceKind='DRAFT-unreplaced', source=source.name)
        else:
            raise ValueError(f'No painted source selected for image {image_id}')
        source_sheet.paste(cell, (image_id % SOURCE_COLUMNS * CELL,
                                  image_id // SOURCE_COLUMNS * CELL))
        metadata['cellSha256'] = hashlib.sha256(cell.tobytes()).hexdigest()
        items.append(metadata)
        if image_id % 100 == 0:
            print(f'Prepared {image_id + 1}/599 cells', flush=True)
    output = args.output / 'painted-items.png'
    source_sheet.save(output)
    manifest = {'schema': 1, 'product': 'Rabbit Lands', 'date': '2026-10-18',
                'imageCount': 599, 'cellSize': 50, 'columns': SOURCE_COLUMNS,
                'source': output.name, 'sourceSha256': digest(output),
                'background': list(BACKGROUND), 'decorativeFrame': False,
                'equipmentFacing': 'left; neutral frontal wearables unchanged',
                'longWeaponDirection': 'action end upper-left, grip lower-right',
                'runtimeIdsUnchanged': True, 'draft': args.draft,
                'items': items}
    (args.output / 'manifest.json').write_bytes((json.dumps(manifest, indent=2) + '\n').encode('utf-8'))
    print(f'Prepared {len(items)} painted cells in {args.output}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
