"""Pack two equipment body fits and individual head fits as ordinary GLBs.

Uses a reviewed, hash-verified source delivery in scratch. No fitted attribute,
triangle index value or image byte changes. Only unused body variants are omitted
and eligible index buffers use unsigned 16-bit storage. Installation is separate.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import numpy as np
import equipment_authoring as ea
import import_generated_equipment as batch
import pack_canonical_equipment as pack

def smaller_indices(document: dict, binary: bytes) -> tuple[dict, bytes, int]:
    result = copy.deepcopy(document)
    index_ids = {primitive['indices'] for mesh in result.get('meshes', [])
                 for primitive in mesh['primitives']}
    users = {}
    for index, accessor in enumerate(result['accessors']):
        if 'sparse' in accessor:
            raise ValueError('Sparse accessors require a separate storage proof')
        users.setdefault(accessor['bufferView'], []).append(index)
    replacements = {}
    saved = 0
    for index in index_ids:
        spec = result['accessors'][index]
        view = result['bufferViews'][spec['bufferView']]
        values = ea.accessor_array(document, binary, index)
        maximum = int(values.max(initial=0))
        # glTF reserves the largest index value for primitive restart.
        dtype, component = ('<u2', 5123) if maximum < 65535 else ('<u4', 5125)
        if np.dtype(dtype).itemsize >= values.dtype.itemsize:
            continue
        if users[spec['bufferView']] != [index] or spec.get('byteOffset', 0) or view.get('byteStride'):
            raise ValueError('Unexpected shared or interleaved index buffer')
        converted = values.astype(dtype)
        assert np.array_equal(values, converted)
        replacements[spec['bufferView']] = converted.tobytes()
        spec['componentType'] = component
        saved += values.nbytes - converted.nbytes
    output = bytearray()
    for index, view in enumerate(result['bufferViews']):
        start = view.get('byteOffset', 0)
        data = replacements.get(index, binary[start:start + view['byteLength']])
        output.extend(b'\0' * (-len(output) % 4))
        view['byteOffset'], view['byteLength'] = len(output), len(data)
        output.extend(data)
    return result, bytes(output), saved


def asset_path(asset):
    folder=pack.PREFIX if asset['race']=='luminous_male' else pack.PREFIX/'variants'/asset['race']
    return folder/(asset['slug']+'.glb')


def run(manifest_path,stage):
    if stage.exists():raise FileExistsError(stage)
    if not stage.resolve().is_relative_to((pack.ROOT/'equipment-fit-build').resolve()):
        raise ValueError('Use a new scratch output directory')
    raw=manifest_path.read_bytes();parent=json.loads(raw)
    roster={p.slug:p for p in batch.roster()}
    selected=[a for a in parent['assets'] if roster[a['slug']].part==3 or a['race'] in ('luminous_male','luminous_female')]
    if len(selected)!=1424:raise ValueError(f'Expected 1024 head and 400 body fits, got {len(selected)}')
    files,assets={},[]
    for asset in selected:
        relative=asset_path(asset);source=manifest_path.parent/relative
        original=source.read_bytes();expected=parent['files'][relative.as_posix()]['sha256']
        if pack.sha(original)!=expected:raise ValueError(f'Source hash changed: {source}')
        d,b=ea.read_glb(source);nd,nb,saved=smaller_indices(d,b)
        writer=ea.EquipmentGLB();writer.doc,writer.binary=nd,nb
        target=stage/relative
        if target.exists():raise FileExistsError(target)
        writer.write(target);encoded=target.read_bytes()
        check,cb=ea.read_glb(target)
        for i in range(len(d['accessors'])):
            if not np.array_equal(ea.accessor_array(d,b,i),ea.accessor_array(check,cb,i)):
                raise ValueError(f'Accessor changed: {relative} {i}')
        for im in d.get('images',[]):
            if 'uri' not in im:raise ValueError('Expected reviewed external image storage')
            image_source=(source.parent/im['uri']).resolve()
            image_relative=image_source.relative_to(manifest_path.parent.resolve())
            image_key=image_relative.as_posix()
            if image_key not in files:
                data=image_source.read_bytes()
                if pack.sha(data)!=parent['files'][image_key]['sha256']:
                    raise ValueError(f'Image changed: {image_relative}')
                pack.new_file(stage/image_relative,data)
                files[image_key]={'sha256':pack.sha(data),'bytes':len(data)}
        if source.read_bytes()!=original:raise ValueError(f'Source changed during packing: {source}')
        files[relative.as_posix()]={'sha256':pack.sha(encoded),'bytes':len(encoded)}
        assets.append(dict(asset,packed_source_sha256=expected,packed_sha256=pack.sha(encoded),
                           index_bytes_saved=saved,accessors_verified=len(d['accessors'])))
        if len(assets)%100==0:print(f'PACK {len(assets)}/{len(selected)}',flush=True)
    if manifest_path.read_bytes()!=raw:raise ValueError('Parent manifest changed')
    report={'parent_manifest':str(manifest_path),'parent_manifest_sha256':pack.sha(raw),
            'tool_sha256':pack.sha(Path(__file__).read_bytes()),'body_templates':['luminous_male','luminous_female'],
            'files':files,'assets':assets,'protected':parent['protected'],
            'omitted_body_variants':len(parent['assets'])-len(assets),
            'bytes':sum(f['bytes'] for f in files.values()),
            'index_bytes_saved':sum(a['index_bytes_saved'] for a in assets)}
    pack.new_file(stage/'manifest.json',(json.dumps(report,indent=2)+'\n').encode())
    print(json.dumps({k:v for k,v in report.items() if k not in ('files','assets','protected')},indent=2),flush=True)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('manifest',type=Path);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();run(args.manifest,args.out)
