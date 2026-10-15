#!/usr/bin/env python3
"""Render the shared continent once and derive every territory's exact Tab map.

Run after geometry export and coordinate publication, before package digests:
  python atlas_export.py --output-dir <review-folder> --apply

The existing native orthographic renderer supplies actual topmost geometry,
vertex colours, texture cutouts and shared daylight. All territory crops share
one world pixel lattice; ownership boundaries cannot change a shoreline or
cut a canopy. Region worldMin/worldMax and client hit polygons remain exact.
No editor scene, concept image, terrain inference or parallel renderer is used.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'eloria-assets/tools'))
import build_continent_map as B
import render_region_cartography as C
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
MASTER = HERE/'generated/continent.glb'
GENERATOR = 'eloria-assets/maps/nymara-regions/_continent/atlas_export.py'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def global_frame(manifest, placed):
    low, high, size = C.frame(manifest)
    translation = manifest.get('continentGeography', {}).get('translation', placed['translation'])
    if not np.allclose(translation, placed['translation'], atol=1e-6):
        raise ValueError('Territory and continent geography translations differ')
    offset = np.asarray(translation, dtype=float)[[0, 2]]
    return low+offset, high+offset, size


def crop_world(image, origin, pixels_per_metre, low, high, size):
    """Exact common-lattice copy where possible; declared frame otherwise."""
    box = [*((np.asarray(low)-origin)*pixels_per_metre),
           *((np.asarray(high)-origin)*pixels_per_metre)]
    if box[0] < -1e-5 or box[1] < -1e-5 or box[2] > image.width+1e-5 or box[3] > image.height+1e-5:
        raise ValueError('Territory minimap lies outside the shared continent raster')
    if np.allclose(box, np.rint(box), atol=1e-5):
        result = image.crop(tuple(int(round(value)) for value in box))
        return result if result.size == tuple(size) else result.resize(size, Image.Resampling.LANCZOS)
    # Non-square and fractional bounds retain the same coordinate mapping. This
    # only resamples the common raster; it does not independently render edges.
    return image.transform(size, Image.Transform.EXTENT, box, Image.Resampling.BICUBIC)


def render(master, output, supersample=2, pixels_per_metre=None):
    began = time.perf_counter()
    master = master.resolve()
    output.mkdir(parents=True, exist_ok=True)
    layout, registry, geography = (B.load_json(path) for path in (B.LAYOUT, B.REGISTRY, B.GEOGRAPHY))
    origins = np.asarray(layout['originMetres'], dtype=float)
    extent = np.asarray(layout['canvasMetres'], dtype=float)
    territories = []
    inputs = {B.path_to_resource(master): C.sha(master),
              B.path_to_resource(B.GEOGRAPHY): C.sha(B.GEOGRAPHY)}
    for tool in (Path(__file__), Path(C.__file__), Path(B.__file__),
                 C.TOOLKIT/'native/raster.c', Path(C.atlas_soft_ground.__file__),
                 ROOT/'godot-client/src/world/soft_ground.gdshader'):
        inputs[B.path_to_resource(tool)] = C.sha(tool)
    # The review master is reproducible and ignored; these tracked authored
    # sources plus every named GLB remain verifiable in a clean checkout.
    for source in sorted(HERE.glob('*.py')) + sorted(HERE.glob('*.json')):
        inputs[B.path_to_resource(source)] = C.sha(source)
    for identity, entry in B.registry_entries(registry, layout):
        path = B.resource_to_path(entry['manifest']).resolve()
        manifest = B.load_json(path)
        local_low, local_high, size = C.frame(manifest)
        low, high, _ = global_frame(manifest, geography['regions'][identity])
        source = C.source_inputs(path, manifest)
        glb = path.parent/manifest['asset']['glb']
        inputs[B.path_to_resource(glb)] = source['glb']
        for uri, expected in source.get('externalResources', {}).items():
            inputs[B.path_to_resource(C.external_resource(glb, uri, expected))] = expected
        territories.append({'region':identity, 'sourceManifest':str(path),
            'manifestSha256':source['manifest'], 'contractSha256':B.contract_digest(manifest),
            'worldMin':local_low.tolist(), 'worldMax':local_high.tolist(),
            'globalMin':low.tolist(), 'globalMax':high.tolist(), 'imageSize':list(size),
            'pixelsPerMetre':float(manifest['minimap']['pixelsPerMetre'])})
    required_ppm = max(value['pixelsPerMetre'] for value in territories)
    ppm = float(pixels_per_metre or required_ppm)
    if ppm < required_ppm:
        raise ValueError(f'Shared raster requires at least {required_ppm} pixels per metre')
    dimensions = tuple(int(round(value*ppm)) for value in extent)
    if not np.allclose(np.asarray(dimensions), extent*ppm, atol=1e-5):
        raise ValueError('Shared raster must use an exact integer pixel lattice')
    # The complete review GLB is embedded and self-contained. Named territory
    # GLBs can instead use the declared external PNGs validated above.
    scene, colours, geometry = C.scene_from_glb(master)
    rgb, rgba, coverage, counts = C.raster(scene, colours, origins, origins+extent,
        dimensions, supersample, native_cache=output/'_atlas_native')
    rgb.save(output/'continent-global.png')
    coverage.save(output/'continent-coverage.png')
    atlas_size = tuple(int(round(value/float(layout['metresPerPixel']))) for value in extent)
    atlas = rgb if rgb.size == atlas_size else rgb.resize(atlas_size, Image.Resampling.LANCZOS)
    atlas.save(output/'continent-atlas.png')
    for territory in territories:
        folder = output/territory['region']
        folder.mkdir(parents=True, exist_ok=True)
        arguments = (origins, ppm, territory['globalMin'], territory['globalMax'], tuple(territory['imageSize']))
        crop_world(rgb, *arguments).save(folder/'minimap.webp', 'WEBP', quality=92, method=6)
        crop_world(rgba, *arguments).save(folder/'cartography.webp', 'WEBP', lossless=True, method=6, exact=True)
        territory['outputs'] = {name:C.sha(folder/name) for name in ('minimap.webp', 'cartography.webp')}
        print(f"{territory['region']}: common-world crop {territory['globalMin']} to {territory['globalMax']}", flush=True)
    report = {'schemaVersion':1, 'generator':GENERATOR,
        'masterResource':B.path_to_resource(master),
        'masterSha256':inputs[B.path_to_resource(master)], 'inputs':inputs,
        'territoryContracts':{B.path_to_resource(Path(t['sourceManifest'])):t['contractSha256'] for t in territories},
        'layout':{key:layout[key] for key in ('originMetres', 'canvasMetres', 'metresPerPixel')},
        'imageSha256':C.sha(output/'continent-atlas.png'),
        'pixelsPerMetre':ppm, 'supersample':supersample,
        'projection':'orthographic, -Z north, +X east; one shared world pixel lattice',
        'waterRGB':list(C.water_rgb()), 'geometry':geometry, 'coverage':counts,
        'territories':territories,
        'limits':['Shared daylight omits atmosphere and cast shadows.',
                  'Minimaps retain rectangular local framing; territory ownership is a separate polygon.',
                  'Normal and roughness textures are omitted at atlas scale.'],
        'seconds':round(time.perf_counter()-began, 3)}
    validate_inputs(report)
    write_json(output/'atlas-render-report.json', report)
    return report


def validate_inputs(report):
    for resource, expected in report['inputs'].items():
        if C.sha(B.resource_to_path(resource)) != expected:
            raise RuntimeError(f'Continent render input changed: {resource}')
    for territory in report['territories']:
        if C.sha(territory['sourceManifest']) != territory['manifestSha256']:
            raise RuntimeError(f"Territory changed during atlas rendering: {territory['region']}")


def apply(report, output):
    """Publish derived maps only after all master and package inputs validate."""
    validate_inputs(report)
    layout = B.load_json(B.LAYOUT)
    if report['layout'] != {key:layout[key] for key in report['layout']}:
        raise RuntimeError('Atlas layout changed during rendering')
    if C.sha(output/'continent-atlas.png') != report['imageSha256']:
        raise RuntimeError('Rendered continent image changed before publication')
    for territory in report['territories']:
        for name, expected in territory['outputs'].items():
            if C.sha(output/territory['region']/name) != expected:
                raise RuntimeError(f"Rendered territory image changed: {territory['region']}/{name}")
    for territory in report['territories']:
        path = Path(territory['sourceManifest'])
        manifest = B.load_json(path)
        for name in territory['outputs']:
            (path.parent/name).write_bytes((output/territory['region']/name).read_bytes())
        minimap = manifest['minimap']
        minimap['image'] = 'minimap.webp'
        minimap['geometryImage'] = 'cartography.webp'
        minimap['renderedFrom'] = 'shared continent.glb (common world pixel lattice)'
        minimap['cartographyRender'] = {'generator':GENERATOR, 'masterSha256':report['masterSha256'],
            'globalMin':territory['globalMin'], 'globalMax':territory['globalMax'],
            'pixelsPerMetre':report['pixelsPerMetre'], 'supersample':report['supersample'],
            'waterRGB':report['waterRGB']}
        assert B.contract_digest(manifest) == territory['contractSha256']
        write_json(path, manifest)
    generated = HERE/'cartography'
    generated.mkdir(parents=True, exist_ok=True)
    image = generated/'continent-atlas.png'
    image.write_bytes((output/'continent-atlas.png').read_bytes())
    # Keep the published freshness proof deterministic; timings and full input
    # manifests belong in the review report, not client production provenance.
    proof = {key:report[key] for key in ('schemaVersion', 'generator', 'masterSha256', 'inputs',
        'territoryContracts', 'layout', 'imageSha256', 'pixelsPerMetre', 'supersample', 'projection')}
    proof['inputs'] = dict(proof['inputs'])
    master_resource = report['masterResource']
    proof['optionalReviewInputs'] = {master_resource:proof['inputs'].pop(master_resource)}
    proof['reviewMaster'] = 'Verified while rendering; when absent, freshness checks verify tracked named GLBs, shared textures and authored generation inputs.'
    proof_path = generated/'continent-atlas.json'
    write_json(proof_path, proof)
    layout['geometryAtlas'] = {'image':B.path_to_resource(image), 'report':B.path_to_resource(proof_path)}
    layout['sea'] = report['waterRGB']
    write_json(B.LAYOUT, layout)
    B.build()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--master', type=Path, default=MASTER)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--supersample', type=int, choices=(1, 2, 3, 4), default=2)
    parser.add_argument('--pixels-per-metre', type=float)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.is_relative_to(ROOT/'eloria-assets/maps'):
        parser.error('Review output must be outside authored maps; --apply publishes derived maps')
    report = render(args.master, output, args.supersample, args.pixels_per_metre)
    if args.apply:
        apply(report, output)
    print(f"Shared atlas: {report['geometry']['triangles']:,} triangles, {report['seconds']:.1f}s", flush=True)


if __name__ == '__main__':
    main()
