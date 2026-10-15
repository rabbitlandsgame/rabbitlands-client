"""Install the reviewed source-based Luminous bodies and appearance metadata."""
from __future__ import annotations
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import numpy as np
import trimesh
from PIL import Image
from scipy.ndimage import maximum_filter
from shared_player_bodies import g, append_array, append_view, dense_weights
from fit_character_appearance import combined, fit_hair
from verify_shared_player_bodies import primitives
from prepare_luminous_source import sample_pixels
import equipment_authoring as ea
import split_race_surfaces as split


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def smoothstep(x,lo,hi):
    t=np.clip((x-lo)/(hi-lo),0,1);return t*t*(3-2*t)


def image_pixels(d,b,p):
    ti=d['materials'][p['material']]['pbrMetallicRoughness']['baseColorTexture']['index']
    im=d['images'][d['textures'][ti]['source']];bv=d['bufferViews'][im['bufferView']];start=bv.get('byteOffset',0)
    return Image.open(io.BytesIO(b[start:start+bv['byteLength']])).convert('RGBA')


def bake_mask(original,sex):
    d,b=g.read(original);p=d['meshes'][0]['primitives'][0];a=p['attributes']
    v=g.accessor(d,b,a['POSITION']);uv=g.accessor(d,b,a['TEXCOORD_0']);faces=g.accessor(d,b,p['indices']).astype(int).reshape(-1,3)
    offset=[0,.9521999955,.0030060038] if sex=='female' else [0,.952162981,.010976493]
    v=(v+offset)*(1.7/(1.9029639959 if sex=='female' else 1.902911961))
    pixels=np.asarray(image_pixels(d,b,p).convert('RGB'));h,w=pixels.shape[:2]
    mask=np.zeros((h,w,3),dtype='f4');occupied=np.zeros((h,w),bool)
    centres=v[faces].mean(1)
    faces=faces[(centres[:,1]>1.555)&(centres[:,1]<1.62)&(centres[:,2]>.015)&(abs(centres[:,0])<.073)]
    skin_level=.793 if sex=='female' else .644
    for face in faces:
        pos=v[face];points=uv[face]*[w,h]-.5
        lo=np.maximum(np.floor(points.min(0)).astype(int),[0,0]);hi=np.minimum(np.ceil(points.max(0)).astype(int),[w-1,h-1])
        if np.any(lo>hi):continue
        edge1,edge2=points[1:]-points[0];det=edge1[0]*edge2[1]-edge1[1]*edge2[0]
        if abs(det)<1e-8:continue
        yy,xx=np.mgrid[lo[1]:hi[1]+1,lo[0]:hi[0]+1];dx,dy=xx-points[0,0],yy-points[0,1]
        u=(dx*edge2[1]-dy*edge2[0])/det;t=(edge1[0]*dy-edge1[1]*dx)/det
        weights=np.stack((1-u-t,u,t),-1);xyz=weights@pos;inside=weights.min(-1)>=-1e-5
        x,y,z=xyz[...,0],xyz[...,1],xyz[...,2];rgb=pixels[yy,xx]/255.
        eye=((abs(x)-(.033 if sex=='female' else .032))/.021)**2+((y-1.5827)/.010)**2
        pigment=(rgb.max(-1)-rgb.min(-1)<.19)|(rgb.mean(-1)<skin_level*.73)
        protect=(1-smoothstep(eye,.78,1.2))*pigment*(z>(.029 if sex=='female' else .045))
        iris=((abs(x)-(.033 if sex=='female' else .0315))/.006)**2+((y-1.583)/.006)**2
        iris=(1-smoothstep(iris,.65,1.3))*protect*(1-smoothstep(rgb.min(-1),.60,.87))
        brow_y=1.603 if sex=='female' else 1.601
        brow=((abs(x)-.033)/.025)**2+((y-brow_y)/(.008 if sex=='female' else .0045))**2
        brow=(1-smoothstep(brow,.55,1.15))*np.clip((skin_level-rgb.mean(-1))/(skin_level*.38),0,1)*(z>.04)
        value=np.stack([protect,iris,brow],-1)
        mask[yy[inside],xx[inside]]=np.maximum(mask[yy[inside],xx[inside]],value[inside])
        occupied[yy[inside],xx[inside]]=True
    for channel in range(3):
        padded=maximum_filter(mask[...,channel],size=5)
        mask[...,channel][~occupied]=padded[~occupied]
    return Image.fromarray(np.rint(np.clip(mask,0,1)*255).astype('u1'))


def headwear(d,binary):
    a,f=combined([part for part in primitives(d,bytes(binary)) if part[0] in ('body','eyes','eyebrows','scalp')])
    v=a['POSITION'];world=g.globals_of(d);skin=d['skins'][0];names=[d['nodes'][j]['name'] for j in skin['joints']];hi=names.index('Head');head=world[skin['joints'][hi]][:3,3]
    upper=v[(v[:,1]>1.66)&(v[:,1]<1.71)]
    rx=np.percentile(abs(upper[:,0]-head[0]),96)+.008;rz=np.percentile(abs(upper[:,2]-head[2]),96)+.008
    top=v[(abs(v[:,0])<.045)&(abs(v[:,2])<.065),1].max();base=top-.090
    d['materials'].append({'name':'Headwear','doubleSided':True,'pbrMetallicRoughness':{'baseColorFactor':[.9,.9,.9,1],'metallicFactor':0,'roughnessFactor':.85}})
    parent=next(n for n in d['nodes'] if n.get('name','').endswith('Source'))
    for name,data in [('wardrobe_head_band',split.ring(1,base-.008,base+.016)),('wardrobe_head_cap',split.dome(1,0))]:
        vv,nn,uu,ff=data;scale=np.array([rx,1.,rz])
        if name.endswith('cap'):scale[1]=top-base+.008;vv[:,1]*=scale[1];vv[:,1]+=base
        vv[:,0]=vv[:,0]*rx+head[0];vv[:,2]=vv[:,2]*rz+head[2];nn/=scale;nn/=np.linalg.norm(nn,axis=1,keepdims=True)
        jj=np.zeros((len(vv),4),dtype='u2');jj[:,0]=hi;ww=np.zeros((len(vv),4));ww[:,0]=1
        aa={k:append_array(d,binary,value,'VEC'+str(value.shape[1]),5123 if k=='JOINTS_0' else 5126) for k,value in {'POSITION':vv,'NORMAL':nn,'TEXCOORD_0':uu,'JOINTS_0':jj,'WEIGHTS_0':ww}.items()}
        d['meshes'].append({'name':name,'primitives':[{'attributes':aa,'indices':append_array(d,binary,ff.ravel(),'SCALAR',5125),'material':len(d['materials'])-1}]})
        d['nodes'].append({'name':name,'mesh':len(d['meshes'])-1,'skin':0});parent['children'].append(len(d['nodes'])-1)


def source_head(d, binary):
    # The source body group also contains hands. Keep distant skin out of
    # radial hair fitting: a long lock's ray can otherwise hit a hand.
    a, faces = combined([p for p in primitives(d, binary) if p[1] == 'race_head'])
    faces = faces[((a['POSITION'][faces, 1] > 1.45) & (abs(a['POSITION'][faces, 0]) < .20)).all(1)]
    ids = np.unique(faces)
    remap = np.full(len(a['POSITION']), -1); remap[ids] = np.arange(len(ids))
    faces = remap[faces]
    a = {key: value[ids] for key, value in a.items()}
    hi = next(i for i, n in enumerate(d['nodes']) if n.get('name') == 'Head')
    matrix = ea.global_matrices(d)[hi]
    v = (a['POSITION'] - matrix[:3, 3]) @ matrix[:3, :3]
    return trimesh.Trimesh(v, faces, process=False), dense_weights(a), matrix


def run(workspace,client_root,candidates=None):
    client=client_root/'godot-client';native=client/'assets/actors/native'
    models_path=client/'data/actors/models.json';models=json.loads(models_path.read_text())
    masks_path=native/'face_masks/manifest.json';masks=json.loads(masks_path.read_text())
    necks_path=native/'neck_textures/manifest.json';necks=json.loads(necks_path.read_text())
    report={}
    equipment_path = client/'data/actors/equipment.json'
    equipment = json.loads(equipment_path.read_text())
    # The shipped wardrobe was authored on the previous bodies. Retain those
    # measurements separately so replacing a body cannot redefine its author.
    equipment.setdefault('authoredBodyGirth', copy.deepcopy(equipment['bodyGirth']))
    equipment.setdefault('authoredFootAnchor', copy.deepcopy(equipment['footAnchor']))
    equipment['refittedBodies'] = ['luminous_male', 'luminous_female']
    catalog_path = client/'data/actors/native_asset_catalog.json'
    catalog = json.loads(catalog_path.read_text())
    for sex in ('male','female'):
        slug='luminous_'+sex
        root=workspace/'work-output'/('luminous-source-base' if sex=='male' else 'luminous-female-source-base')
        if candidates is not None:
            root=candidates/sex
        source=root/'rigged'/f'{slug}.glb';manifest=json.loads((root/'rigged/manifest.json').read_text())
        d,b=g.read(source);binary=bytearray(b)
        weight_report=d['asset'].get('extras',{}).get('bodyWeightRepair')
        if not weight_report or weight_report.get('version', 0) < 2:
            raise ValueError(f'{source}: rebuild with rig_luminous_source.py; post-fit weight smoothing cannot repair baked folds')
        config=models['models'][slug]
        groups={}
        textures=native/'race_textures'/slug;textures.mkdir(parents=True,exist_ok=True)
        for mesh in d['meshes']:
            name=mesh['name'];p=mesh['primitives'][0]
            im=image_pixels(d,binary,p);im.save(textures/(name+'_basecolor.png'))
            x0,y0,x1,y1=manifest['groups'][name]['atlasCrop']
            if name in ('body','eyes','eyebrows','scalp'):
                groups[name]={'uvScale':[(x1-x0)/2048,(y1-y0)/2048],'uvOffset':[x0/2048,y0/2048]}
                p['extras']['sourceRole']='race_head'
                p['extras']['sourceUVScale']=groups[name]['uvScale'];p['extras']['sourceUVOffset']=groups[name]['uvOffset']
            else:
                rgb=np.asarray(im.convert('RGB')).astype(float)/255
                uv=g.accessor(d,binary,p['attributes']['TEXCOORD_0']);ff=g.accessor(d,binary,p['indices']).astype(int).reshape(-1,3)
                samples=sample_pixels(np.rint(rgb*255).astype('u1'),uv[ff].mean(1))
                median=max(float(np.median(samples.max(1))),.05)
                grey=np.clip(rgb.max(-1)*.8/median,0,1)
                tint=Image.fromarray(np.rint(grey*255).astype('u1')).convert('RGBA');tint.putalpha(im.getchannel('A'))
                tint.save(textures/(name+'_tint.png'));stream=io.BytesIO();tint.save(stream,format='PNG')
                d['images'].append({'mimeType':'image/png','bufferView':append_view(d,binary,stream.getvalue())});d['textures'].append({'source':len(d['images'])-1})
                d['materials'][p['material']]['pbrMetallicRoughness']['baseColorTexture']={'index':len(d['textures'])-1}
        headwear(d,binary)
        original=workspace/'generate_models/eloria-races-meshy'/f'luminous_human_{sex}_tpose.glb'
        d['asset'].setdefault('extras', {})['sourceSHA256'] = sha(original)
        d['asset'].setdefault('extras',{})['sourceIntegration']={'version':1,'candidateSHA256':sha(source),'skinWeightRepair':weight_report}
        target=native/'races'/f'{slug}.glb';d,b=g.compact(d,bytes(binary));g.write(target,d,b)
        config['faceAppearance']={'sourceSurface':0,'mask':f'res://assets/actors/native/face_masks/{slug}.png','groups':groups}
        config['wardrobeBakedGrow']=['wardrobe_shirt','wardrobe_pants','wardrobe_boots']
        original=workspace/'generate_models/eloria-races-meshy'/f'luminous_human_{sex}_tpose.glb'
        mask=bake_mask(original,sex);mask_path=native/'face_masks'/f'{slug}.png';mask.save(mask_path)
        masks[slug]={'modelSHA256':sha(target),'maskSHA256':sha(mask_path),'sourceMaterial':0,'size':[2048,2048],'pixelsPerChannel':(np.asarray(mask)>.1).sum((0,1)).tolist(),'sourceUVGroups':groups}
        necks.pop(slug,None)
        # Fit the existing authored hairstyle designs to the new source skull.
        skull=source_head(d,b);hair_report={}
        for style in ('parted','long','buns','buzzed'):
            src=native/'hair'/f'{style}_{sex}.glb'
            dest=native/'hair/fitted'/f'{slug}_{style}_{sex}.glb'
            hair_report[style]=fit_hair(src,dest,skull,{'scale':[1,1,1],'offset':[0,0,-.015]},d,b)
        report[slug]={'source':str(source),'sourceSHA256':sha(source),'modelSHA256':sha(target),'skinWeights':weight_report,'hair':hair_report,'triangles':sum(d['accessors'][p['indices']]['count']//3 for m in d['meshes'] for p in m['primitives'])}
        rig = ea.load_rig(target)
        equipment['bodyGirth'][slug] = ea.body_girth(rig)
        equipment['footAnchor'][slug] = ea.foot_anchor(rig)
        equipment['soleDrop'][slug] = ea.sole_drop(rig)
        entry = catalog['races'][slug]
        entry.update(vertices=sum(d['accessors'][p['attributes']['POSITION']]['count'] for m in d['meshes'] for p in m['primitives']),
                     triangles=report[slug]['triangles'], sha256=sha(target),
                     source=original.name, sourceSHA256=sha(original), baseBody=original.name,
                     neckAdaptorTriangles=0, pipeline='eloria-assets/tools/integrate_luminous_sources.py',
                     sourceIntegration=d['asset']['extras']['sourceIntegration'])
        entry.pop('appearanceFit', None)
        config['hairStyles'] = config['hairStyles'][:4] + [f'res://assets/actors/native/hair/fitted/{slug}_buzzed_{sex}.glb']
        for index, style in enumerate(('parted', 'long', 'buns', 'buzzed'), 1):
            hair_path = native/'hair/fitted'/f'{slug}_{style}_{sex}.glb'
            hd, _ = g.read(hair_path)
            catalog['fittedHair'][f'{slug}:{index}'] = {
                'path': hair_path.relative_to(client_root).as_posix(),
                'sha256': hair_report[style]['sha256'], 'joints': 77,
                'triangles': sum(hd['accessors'][p['indices']]['count']//3 for m in hd['meshes'] for p in m['primitives'])}
        print(slug,report[slug]['triangles'],'integrated',flush=True)
    models_path.write_text(json.dumps(models,indent=2)+'\n');masks_path.write_text(json.dumps(masks,indent=2)+'\n');necks_path.write_text(json.dumps(necks,indent=2)+'\n')
    equipment_path.write_text(json.dumps(equipment, indent=2)+'\n')
    catalog_path.write_text(json.dumps(catalog, indent=2)+'\n')
    report_dir = workspace/'work-output/luminous-install'
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir/'integration.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--workspace',type=Path,required=True);ap.add_argument('--client-root',type=Path,required=True)
    ap.add_argument('--candidates',type=Path,help='Alternate reviewed candidate root with male/rigged and female/rigged groups')
    run(**vars(ap.parse_args()))
