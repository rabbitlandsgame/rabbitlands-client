"""Keep archived procedural model builders from recreating retired assets.

Shared readers, rig fitting and imported-model exporters remain available.
The original procedural implementations are preserved in the local authoring
archive described by docs/procedural-model-archive.md.
"""
from pathlib import Path

PROCEDURAL_GENERATORS = frozenset({
    'Eloria native Nymara builder', 'Eloria equipment authoring',
    'Eloria ranger asset authoring', 'Eloria Sunmane livestock builder 1.0',
    'Eloria world object builder', 'Eloria Amethyst editor kit',
    'Eloria Sunmane editor kit',
    'Eloria Landfall cave entrance; original shared kit materials',
    'Eloria sw_isle plaza_rosette', 'Eloria sw_isle garden_paving',
})


def retired_entrypoint(name: str) -> None:
    raise RuntimeError(
        f'{name} is retired: procedural model generation was archived on '
        '2026-10-16. Use the updated imported models. See '
        'docs/procedural-model-archive.md. No outputs were written.')


def require_supported_generator(generator: str) -> None:
    if generator in PROCEDURAL_GENERATORS:
        retired_entrypoint(generator)


def require_animation_source(asset) -> None:
    """Inspect/archive readers may open old assets; fitting may not select them."""
    generator = asset.document.get('asset', {}).get('generator', '')
    if generator in PROCEDURAL_GENERATORS:
        raise ValueError(
            f'{Path(asset.path).name} is an archived procedural model, not an '
            'updated animation target. Choose a current model from '
            'eloria-assets/source/model-development-roster.json.')
