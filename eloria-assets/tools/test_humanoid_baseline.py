"""Check the installed iterative humanoid baseline against frozen native witnesses."""
from pathlib import Path
import argparse
import json
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from video_motion.asset import digest
from video_motion.native_shapes import NativeShapeAsset
from video_motion.runtime_validation import surface_sampler
ROOT=Path(__file__).resolve().parents[2]


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--actor');ap.add_argument('--report',type=Path);args=ap.parse_args()
    manifest=json.loads((ROOT/'docs/qa/humanoid-motion-baseline/manifest.json').read_text());registry=json.loads((ROOT/'godot-client/data/actors/models.json').read_text())['models']
    assert len(manifest['actors'])==40 and len({p['family'] for p in manifest['actors'].values()})==8
    assert manifest['status']=='approved_iterative_baseline' and manifest['further_visual_edits_planned']
    selected={a:p for a,p in manifest['actors'].items() if args.actor is None or a==args.actor};assert selected
    report={'passed':True,'actors':{},'scope':'Installed bytes, native bone/morph/surface witnesses, action maps, cadence, scale, preserved native actions and loop surfaces. Iterative baseline, not final artistic acceptance.'}
    for actor,p in selected.items():
        a=NativeShapeAsset(ROOT/p['runtime_path']);e=registry[actor];mapping=json.loads((ROOT/p['animation_map']).read_text());witness=json.loads((ROOT/f'godot-client/tests/fixtures/humanoid-baseline/{actor}.json').read_text());h=p['height_native']
        assert digest(a.path)==p['sha256']==witness['sha256']==p['native_conformance']['runtime_sha256']==p['packing']['runtime_sha256']
        assert e['animationLibrary']==e['scene'] and 'godot-client/'+e['scene'].removeprefix('res://')==p['runtime_path']
        assert 'godot-client/'+e['animationMap'].removeprefix('res://')==p['animation_map']
        assert a.path.stat().st_size==p['bytes']<100_000_000
        assert set(a.animations)==set(witness['clips'])==set(p['durations'])
        assert mapping['actions']['attack_primary']==p['primary_attack'] and set(mapping['actions'].values())<=set(a.animations)
        assert mapping['serverCommands']['46']=='attack_primary' and mapping['serverCommands']['3']=='death'
        assert a.d['asset']['extras']['rabbitlands_animation_bake_fps']==p['bake_fps']==witness['bake_fps']
        policy=Path(str(a.path)+'.import').read_text();assert f"animation/fps={p['bake_fps']}" in policy and '"optimizer/enabled": false' in policy and '"compression/enabled": false' in policy
        assert all(part['weights'].shape[1]<=8 for part in a.parts if 'weights' in part)
        for action,clip in [('walk','Walk'),('run','Jog')]:
            assert mapping['playbackSpeeds'][action]==1
            g=p['gaits'][clip];assert abs(g['duration']-a.duration(clip))<1e-5
            if g['stride']>0: assert mapping['strideScalesWithActor'] and abs(mapping['strideMetresPerSecond'][action]-g['stride']/g['duration']*e['import']['scale'])<1e-8
            else: assert action not in mapping['strideMetresPerSecond']
        sample_surface=surface_sampler(a,witness['surface_vertex_ids']);row={'sha256':p['sha256'],'clips':{}}
        for clip,entries in witness['clips'].items():
            times=[entry['time'] for entry in entries];tt,qq,ss,mm=a.sample(clip,times);bone_error=morph_error=surface_error=0.
            for k,entry in enumerate(entries):
                world=a.world(tt[k],qq[k],ss[k]);morph={n:v[k] for n,v in mm.items()}
                for name,value in entry['bones'].items(): bone_error=max(bone_error,float(abs(world[a.ids[name]]-np.array(value).reshape(4,4)).max()))
                for node,value in entry['morph_weights'].items(): morph_error=max(morph_error,float(abs(morph[int(node)]-value).max(initial=0)))
                surface_error=max(surface_error,float(np.linalg.norm(sample_surface(world,morph)-entry['surface'],axis=1).max()/h))
            assert bone_error<1e-10 and morph_error<1e-10 and surface_error<.00015,(actor,clip,bone_error,morph_error,surface_error)
            if clip in mapping['loopingClips']:
                t,q,s,m=a.sample(clip,[0,a.duration(clip)]);first=sample_surface(a.world(t[0],q[0],s[0]),{n:x[0] for n,x in m.items()});last=sample_surface(a.world(t[1],q[1],s[1]),{n:x[1] for n,x in m.items()});loop=float(np.linalg.norm(first-last,axis=1).max()/h)
                assert loop<.00015,(actor,clip,'surface loop',loop)
            row['clips'][clip]={'bone_error':bone_error,'morph_error':morph_error,'surface_error_over_height':surface_error}
        report['actors'][actor]=row;print(actor,'PASS',len(row['clips']),'native slots',flush=True)
    if args.report: args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('HUMANOID_BASELINE_NATIVE PASS',len(report['actors']),'actors',sum(len(p['clips']) for p in report['actors'].values()),'slots',flush=True)

if __name__=='__main__':main()
