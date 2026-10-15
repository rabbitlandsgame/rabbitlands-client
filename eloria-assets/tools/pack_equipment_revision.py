"""Package an audited original-source revision over a reviewed compact set.

The parent manifest is immutable evidence. Unchanged assets keep their original
provenance; new candidates keep their actual source/body/tool hashes. This tool
only changes storage and proves every accessor and image byte survives packing.
It writes scratch outputs and an explicit installation plan, never client files.
"""
from __future__ import annotations
import argparse,copy,json,os
from pathlib import Path
import numpy as np
import equipment_authoring as ea
import pack_canonical_equipment as pack
import pack_shared_equipment as compact
import install_shared_equipment as install


def identical_mesh(a_path,b_path,art_only=False):
    a,ab=ea.read_glb(a_path);b,bb=ea.read_glb(b_path)
    am=a['meshes'][:1] if art_only else a['meshes'];bm=b['meshes'][:1] if art_only else b['meshes']
    ap=[p for m in am for p in m['primitives']];bp=[p for m in bm for p in m['primitives']]
    if len(ap)!=len(bp):return False
    for x,y in zip(ap,bp):
        if x['attributes'].keys()!=y['attributes'].keys():return False
        for k in x['attributes']:
            if not np.array_equal(ea.accessor_array(a,ab,x['attributes'][k]),ea.accessor_array(b,bb,y['attributes'][k])):return False
        if not np.array_equal(ea.accessor_array(a,ab,x['indices']),ea.accessor_array(b,bb,y['indices'])):return False
    images_a=list(pack.image_bytes(a,ab,a_path));images_b=list(pack.image_bytes(b,bb,b_path))
    return images_a[:1]==images_b[:1] if art_only else images_a==images_b


def run(parent_path,directory,audit_path,body_build,body_registry,out):
    if out.exists() or not out.resolve().is_relative_to(pack.SCRATCH.resolve()):raise ValueError('Use a new scratch directory')
    parent_raw=parent_path.read_bytes();parent=json.loads(parent_raw)
    registry_raw=body_registry.read_bytes();registry=json.loads(registry_raw)
    for name,h in registry['outputs'].items():
        if install.sha_file(pack.ROOT/name)!=h:raise ValueError('Body registry differs from installed review')
    body_raw=(body_build/'manifest.json').read_bytes();bodies=json.loads(body_raw)
    if len(bodies['candidates'])!=16:raise ValueError('Expected sixteen verified retained heads')
    for slug,h in bodies['candidates'].items():
        result=json.loads((body_build/'reports'/(slug+'.json')).read_bytes())
        if result['geometry']['errors'] or result['motion']['errors']:raise ValueError('Body verification failed')
        if result['geometry']['candidateSHA256']!=h or result['motion']['sha256']!=h:raise ValueError('Stale body audit')
        if pack.refit.digest(pack.refit.ce.RACES/(slug+'.glb'))!=h:raise ValueError('Body differs from reviewed candidate')
    for a in parent['assets']:
        if a['body_sha256']!=bodies['sourceSHA256'][a['race']]:raise ValueError('Parent equipment did not fit the retained canonical source')
    audit_raw=audit_path.read_bytes();audit=json.loads(audit_raw)
    if audit['failures']:raise ValueError('Candidate audit has failures')
    records={}
    for record in directory.glob('*/*.fit.json'):
        r=json.loads(record.read_bytes());p=record.with_suffix('').with_suffix('.glb')
        if pack.sha(p.read_bytes())!=r['asset_sha256']:raise ValueError(f'Changed candidate: {p}')
        if pack.refit.digest(pack.refit.ce.RACES/(r['race']+'.glb'))!=r['body_sha256']:raise ValueError('Body changed after fitting')
        records[(r['race'],r['slug'])]=(r,p)
    audited={(r['race'],r['slug']) for r in audit['assets']}
    if set(records)!=audited:raise ValueError('Audit does not cover exactly these candidates')
    originals={(r['race'],r['slug']) for r in parent['assets']}
    if not set(records)<=originals:raise ValueError('Revision introduces an undeclared asset')
    files,assets,updates={},[],{}
    references=set();controls=[]
    for asset in parent['assets']:
        key=(asset['race'],asset['slug']);relative=compact.asset_path(asset)
        name=relative.as_posix();source=parent_path.parent/relative;target=out/relative
        old=parent['files'][name]['sha256']
        if pack.sha(source.read_bytes())!=old or install.sha_file(pack.ROOT/relative)!=old:raise ValueError(f'Parent asset changed: {relative}')
        result=copy.deepcopy(asset)
        if key in records:
            report,candidate=records[key]
            if not report['key'].startswith('5:'):
                # Lower-body controls demonstrate that neck surgery did not
                # alter the reviewed leg/foot fits. They are verification only.
                if not identical_mesh(source,candidate):raise ValueError(f'Lower-body control changed: {key}')
                controls.append(dict(race=key[0],slug=key[1],candidate_sha256=report['asset_sha256']))
            else:
                if report.get('anatomy_reference_sha256')!=bodies['sourceSHA256'][asset['race']]:
                    raise ValueError('Use the verified original canonical anatomy reference for torso fitting')
                if not identical_mesh(source,candidate,art_only=True):raise ValueError('Revision changed the reviewed original artwork')
                pack.pack_glb(candidate,relative,out)
                raw=target.read_bytes();d,b=ea.read_glb(target);nd,nb,saved=compact.smaller_indices(d,b)
                temporary=target.with_suffix('.compact.glb')
                writer=ea.EquipmentGLB();writer.doc,writer.binary=nd,nb;writer.write(temporary)
                if target.read_bytes()!=raw:raise ValueError('Concurrent scratch write')
                os.replace(temporary,target)
                if not identical_mesh(candidate,target):raise ValueError('Packing changed geometry or images')
                result.update({k:report[k] for k in ('source_sha256','body_sha256','tool_sha256','asset_sha256','anatomy_reference_sha256')})
                result.update(candidate_build=directory.name,packed_sha256=pack.sha(target.read_bytes()),index_bytes_saved=saved)
                result.pop('compatibility',None)
                result.update(pack.validate(target,asset['race']))
                updates[name]={'source':str(target.resolve()),'sha256':result['packed_sha256'],'expected':old}
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True);os.link(source,target)
        d,b=ea.read_glb(target)
        for image in d.get('images',[]):
            if 'uri' not in image:raise ValueError('Expected external shared image')
            image_path=(target.parent/image['uri']).resolve()
            if not image_path.is_relative_to(out.resolve()):raise ValueError('Image leaves scratch set')
            ref=image_path.relative_to(out.resolve());references.add(ref)
            if not image_path.exists():
                src=parent_path.parent/ref
                if pack.sha(src.read_bytes())!=parent['files'][ref.as_posix()]['sha256']:raise ValueError('Parent image changed')
                image_path.parent.mkdir(parents=True,exist_ok=True);os.link(src,image_path)
        files[name]={'sha256':pack.sha(target.read_bytes()),'bytes':target.stat().st_size}
        assets.append(result)
    for ref in references:
        path=out/ref;name=ref.as_posix();h=pack.sha(path.read_bytes())
        files[name]={'sha256':h,'bytes':path.stat().st_size}
        current=install.sha_file(pack.ROOT/ref)
        if current!=h:updates[name]={'source':str(path.resolve()),'sha256':h,'expected':current}
    remove={}
    for name,spec in parent['files'].items():
        if name in files:continue
        if not name.startswith(pack.PREFIX.as_posix()+'/textures/canonical_'):raise ValueError('Unexpected removed parent file')
        if install.sha_file(pack.ROOT/name)!=spec['sha256']:raise ValueError('Obsolete texture changed')
        remove[name]=spec['sha256']
        importer=pack.ROOT/(name+'.import')
        if importer.is_file():remove[name+'.import']=install.sha_file(importer)
    protected={}
    for name,old in parent['protected'].items():
        current=install.sha_file(pack.ROOT/name)
        expected=bodies['candidates'].get(Path(name).stem) if '/races/' in name else registry['outputs'].get(name,old)
        if current!=expected:raise ValueError(f'Protected input changed: {name}')
        protected[name]=current
    if body_registry.read_bytes()!=registry_raw or (body_build/'manifest.json').read_bytes()!=body_raw or parent_path.read_bytes()!=parent_raw or audit_path.read_bytes()!=audit_raw:raise ValueError('Evidence changed while packing')
    manifest={'parent_manifest':str(parent_path.resolve()),'parent_manifest_sha256':pack.sha(parent_raw),
              'audit':str(audit_path.resolve()),'audit_sha256':pack.sha(audit_raw),'tool_sha256':pack.refit.digest(__file__),
              'body_registry_manifest_sha256':pack.sha(registry_raw),'body_build_manifest_sha256':pack.sha(body_raw),'validated_body_sha256':bodies['candidates'],
              'body_templates':parent['body_templates'],'assets':assets,'files':files,'protected':protected,
              'bytes':sum(q['bytes'] for q in files.values()),'lower_body_controls':controls,
              'omitted_body_variants':parent['omitted_body_variants']}
    pack.new_file(out/'manifest.json',(json.dumps(manifest,indent=2)+'\n').encode())
    pack.new_file(out/'install.json',(json.dumps({'replace':updates,'remove':remove,'protected':protected},indent=2)+'\n').encode())
    print('PACKED',len(assets),'assets;',len(updates),'updates;',len(remove),'obsolete files;',manifest['bytes'],'bytes')
    return manifest


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--parent',type=Path,required=True);ap.add_argument('--candidates',type=Path,required=True)
    ap.add_argument('--audit',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--body-build',type=Path,required=True);ap.add_argument('--body-registry',type=Path,required=True)
    a=ap.parse_args();run(a.parent,a.candidates,a.audit,a.body_build,a.body_registry,a.out)
