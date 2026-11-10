"""Distinct metal artwork, safe replacement history, and client item references."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
from unittest.mock import patch

from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'eloria-assets/tools'))
import build_item_icon_atlases as builder

METALS = ROOT / 'eloria-assets/source/item-icons/metals-2026-11-09'
STORM = ROOT / 'eloria-assets/source/item-icons/stormglass-ingot-2026-11-09'


def test_every_requested_material_has_a_distinct_painting_in_its_runtime_slot():
    records = [row for folder in (METALS, STORM)
               for row in json.loads((folder / 'manifest.json').read_text())['items']]
    expected = {'Steel Bar': 626, 'Stormglass Ingot': 33, 'Silver Bar': 627,
                'Gold Bar': 628, 'Titanium Bar': 629, 'Silver Ore': 630,
                'Gold Ore': 631, 'Titanium Ore': 632}
    assert {r['name']: r['imageId'] for r in records} == expected
    assert len({r['paintedSourceSha256'] for r in records}) == 8
    planned = [image for _, image in builder.planned_atlases()]
    pixels = set()
    for record in records:
        folder = STORM if record['imageId'] == 33 else METALS
        image = Image.open(folder / record['source']).convert('RGBA')
        assert image.size == (50, 50)
        atlas, local = divmod(record['imageId'], 25)
        x, y = local % 5 * 50, local // 5 * 50
        assert planned[atlas].crop((x, y, x + 50, y + 50)).tobytes() == image.tobytes()
        pixels.add(hashlib.sha256(image.tobytes()).hexdigest())
        assert image.getpixel((0, 0)) == image.getpixel((49, 49)) == (5, 15, 18, 255)
    assert len(pixels) == 8


def test_stormglass_replacement_preserves_every_other_existing_icon():
    with patch.object(builder, 'MATERIAL_REPLACEMENTS', []):
        before = [image for _, image in builder.planned_atlases()]
    after = [image for _, image in builder.planned_atlases()]
    changed = set()
    for image_id in range(633):
        atlas, local = divmod(image_id, 25)
        x, y = local % 5 * 50, local // 5 * 50
        bounds = (x, y, x + 50, y + 50)
        if before[atlas].crop(bounds).tobytes() != after[atlas].crop(bounds).tobytes():
            changed.add(image_id)
    assert changed == {33}


@pytest.mark.parametrize('damage', ['wrong_preceding_hash', 'duplicate_id'])
def test_material_replacement_refuses_stale_or_ambiguous_history(tmp_path, damage):
    folder = tmp_path / 'replacement'
    shutil.copytree(STORM, folder)
    path = folder / 'manifest.json'
    manifest = json.loads(path.read_text())
    if damage == 'wrong_preceding_hash':
        manifest['items'][0]['replacesCellSha256'] = '0' * 64
        message = 'Replacement target painting differs: 33'
    else:
        manifest['items'].append(dict(manifest['items'][0]))
        message = 'Invalid or duplicate replacement image ID: 33'
    path.write_text(json.dumps(manifest))
    with patch.object(builder, 'MATERIAL_REPLACEMENTS', [folder]), pytest.raises(ValueError, match=message):
        builder.planned_atlases()


def test_new_metals_are_in_the_client_item_and_smelting_catalogues():
    categories = json.loads((ROOT / 'godot-client/data/items/categories.json').read_text())['categories']
    recipes = json.loads((ROOT / 'godot-client/data/manufacturing/recipes.json').read_text())['recipes']
    for index, metal in enumerate(('Silver', 'Gold', 'Titanium')):
        assert categories[metal + ' Bar'] == 'Metals'
        assert categories[metal + ' Ore'] == 'Ores'
        recipe, = [r for r in recipes if r['output'] == metal + ' Bar']
        assert recipe['outputImageId'] == 627 + index
        ingredient, = [r for r in recipe['ingredients'] if r['name'] == metal + ' Ore']
        assert ingredient['imageId'] == 630 + index and ingredient['quantity'] == 3
    steel, = [r for r in recipes if r['output'] == 'Steel Bar']
    assert steel['outputImageId'] == 626
