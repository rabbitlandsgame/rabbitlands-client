"""Install validated high-resolution head grafts, refit hair, and measure equipment.

RETIRED (2026-10, race programme P7): `run` refuses. The race bodies are now
built and installed by rebase_race_body.py (build/verify/install/post-import)
and their hair by fit_character_appearance.py --race; this installer would
overwrite the rebased bodies, their face masks and the P5 hair fits with the
retired protrusion proxy. The code stays readable because race_head_prepare.py
documents the asset.extras stamping and compact_materials pass it reproduces
by reference to this file.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil
from PIL import Image
import equipment_authoring as ea
from shared_player_bodies import g, digest, copy_materials, write_group
from verify_shared_player_bodies import primitives, verify
from race_hair_skull import hair_skull, allows_protrusions
from fit_character_appearance import fit_hair
from build_face_masks import bake
from compact_character_materials import compact_materials


RETIRED = ('install_high_resolution_race_heads.py is retired (2026-10, race programme P7): install race bodies '
           'with rebase_race_body.py and race hair with fit_character_appearance.py --race <slug>.')


def run(root, candidates, body_name="body.glb"):
    raise SystemExit(RETIRED)
    client=root/'godot-client';native=client/'assets/actors/native'
    files={'models':client/'data/actors/models.json','catalog':client/'data/actors/native_asset_catalog.json',
           'equipment':client/'data/actors/equipment.json','masks':native/'face_masks/manifest.json',
           'necks':native/'neck_textures/manifest.json'}
    data={key:json.loads(path.read_text()) for key,path in files.items()}
    backup=candidates/'pre-install';backup.mkdir(parents=True,exist_ok=True)
    for key,path in files.items():
        target=backup/(key+'.json')
        if not target.exists():shutil.copy2(path,target)
    regions=json.loads(Path(__file__).with_name('face_regions.json').read_text())
    report={}
    for slug,config in data['models']['models'].items():
        if 'bodyTemplate' not in config or slug.startswith('luminous_'):continue
        folder=candidates/slug;source=folder/'head.glb';candidate=folder/body_name
        template=native/'races'/f'luminous_{config["gender"]}.glb'
        checks=verify(candidate,source,template)
        if checks['errors']:raise ValueError((slug,checks['errors']))
        path=native/'races'/f'{slug}.glb';prior=backup/(slug+'.glb')
        if not prior.exists():shutil.copy2(path,prior)
        d,b=g.read(candidate);binary=bytearray(b)
        if slug.startswith('ssarathi_'):
            old,old_binary=g.read(prior);mapping=copy_materials(d,binary,old,old_binary)
            mesh=next(m for m in d['meshes'] if m['name']=='body')
            for name,role,a,f in primitives(old,old_binary):
                if role!='race_tail':continue
                material=next(p['material'] for m in old['meshes'] for p in m['primitives']
                              if p.get('extras',{}).get('sourceRole')=='race_tail')
                pieces={};write_group(d,binary,{'a':a,'f':{('body',mapping[material]):f},'role':'race_tail'},pieces)
                mesh['primitives'].extend(pieces.get('body', []))
        provenance=d['asset']['extras']['highResolutionHead']
        d['asset']['extras']['sourceSHA256']=provenance['originalSHA256']
        d['asset']['extras']['eloriaSurfacesSplit']=14
        d=compact_materials(d,bytes(binary))
        d,binary=g.compact(d,bytes(binary));g.write(path,d,binary)
        b=bytes(binary)
        head_mesh=next(m for m in d['meshes'] if m['name']=='body')
        surface=next(i for i,p in enumerate(head_mesh['primitives']) if p.get('extras',{}).get('sourceRole')=='race_head')
        # Re-bake against the new source UVs; never reuse another atlas's mask.
        region=copy.deepcopy(regions['models'][slug]);region.pop('browStrokes',None)
        mask,mask_report=bake(path,region,regions['projection'])
        mask_path=native/'face_masks'/f'{slug}.png';Image.fromarray(mask).save(mask_path,optimize=True)
        mask_report['maskSHA256']=digest(mask_path);data['masks'][slug]=mask_report
        config['faceAppearance']={'sourceSurface':surface,'mask':f'res://assets/actors/native/face_masks/{slug}.png'}
        config['wardrobeBakedGrow']=['wardrobe_shirt','wardrobe_pants','wardrobe_boots']
        data['necks'].pop(slug,None)
        skull=hair_skull(d,b,slug);hair_report={}
        config['hairAllowsProtrusions']=allows_protrusions(slug)
        horizontal=.95 if allows_protrusions(slug) else 1.
        for index,style in enumerate(('parted','long','buns','buzzed'),1):
            target=native/'hair/fitted'/f'{slug}_{style}_{config["gender"]}.glb'
            hair_report[style]=fit_hair(native/'hair'/f'{style}_{config["gender"]}.glb',target,skull,
                                      {'scale':[horizontal,1,horizontal],'offset':[0,0,-.015]},d,b)
            config['hairStyles'][index]='res://'+target.relative_to(client).as_posix()
            data['catalog']['fittedHair'][f'{slug}:{index}']['sha256']=digest(target)
        rig=ea.load_rig(path)
        for key,measure in [('bodyGirth',ea.body_girth),('footAnchor',ea.foot_anchor),('soleDrop',ea.sole_drop)]:
            data['equipment'][key][slug]=measure(rig)
        catalog=data['catalog']['races'][slug]
        if slug.startswith('ssarathi_'):
            catalog['retainedTailTriangles'] = sum(d['accessors'][p['indices']]['count']//3
                for mesh in d['meshes'] for p in mesh['primitives']
                if p.get('extras', {}).get('sourceRole') == 'race_tail')
        catalog.update(sha256=digest(path),source=provenance['original'],sourceSHA256=provenance['originalSHA256'],
            baseBody=template.name,highResolutionHead=provenance,sharedBodyShape=d['asset']['extras']['sharedBodyShape'],
            surfaces=[mesh['name'] for mesh in d['meshes']],
            neckAdaptorTriangles=sum(d['accessors'][p['indices']]['count']//3 for mesh in d['meshes'] for p in mesh['primitives'] if p.get('extras',{}).get('sourceRole')=='neck_join'),
            triangles=sum(d['accessors'][p['indices']]['count']//3 for m in d['meshes'] for p in m['primitives']),
            vertices=sum(d['accessors'][p['attributes']['POSITION']]['count'] for m in d['meshes'] for p in m['primitives']),
            pipeline='eloria-assets/tools/build_high_resolution_race_heads.py')
        catalog.pop('appearanceFit',None)
        report[slug]={'source':provenance,'preservation':checks,'hair':hair_report,'modelSHA256':digest(path)}
        print('INSTALLED',slug,catalog['triangles'],'triangles; mask',mask_report['pixelsPerChannel'],flush=True)
    data['equipment']['refittedBodies']=[s for s,c in data['models']['models'].items() if 'bodyTemplate' in c]
    for key,path in files.items():path.write_text(json.dumps(data[key],indent=2)+'\n')
    (candidates/'installation.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--candidates',type=Path,required=True)
    parser.add_argument('--body-name',default='body.glb',help='Reviewed body filename within each race folder')
    run(**vars(parser.parse_args()))
