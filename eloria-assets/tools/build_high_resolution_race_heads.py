"""Build scratch race-head grafts from original Meshy T-pose artwork, on eight CPUs."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import psutil

from prepare_race_head import extract, bind
from shared_player_bodies import run as graft


def run(root, sources, out, blender):
    psutil.Process().cpu_affinity(list(range(8)))
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
        os.environ[name]='8'
    models=json.loads((root/'godot-client/data/actors/models.json').read_text())['models']
    native=root/'godot-client/assets/actors/native'
    reports={}
    for slug,config in models.items():
        if 'bodyTemplate' not in config or slug.startswith('luminous_'):continue
        folder=out/slug;folder.mkdir(parents=True,exist_ok=True)
        if (folder/'body.glb').exists():
            reports[slug]=json.loads((folder/'body.json').read_text());continue
        source_slug=slug.replace('votary_','whitehorn_votary_')
        original=sources/(source_slug+'_tpose.glb')
        donor=sources/(source_slug+'_tpose_rigged.glb')
        template=native/'races'/f'luminous_{config["gender"]}.glb'
        extracted=folder/'source-head.glb';reduced=folder/'reduced.glb';canonical=folder/'head.glb'
        extract(original,donor,template,extracted)
        with (folder/'reduction.log').open('w') as log:
            subprocess.run([str(blender),'--background','--factory-startup','--threads','8',
                '--python-exit-code','1','--python',str(Path(__file__).with_name('reduce_race_head_blender.py')),
                '--',str(extracted),str(reduced)],stdout=log,stderr=subprocess.STDOUT,check=True)
        bind(extracted,reduced,template,native/'races'/f'{slug}.glb',canonical)
        reports[slug]=graft(canonical,template,folder/'body.glb',texture_source=extracted)
        print('GRAFTED',slug,flush=True)
    (out/'grafts.json').write_text(json.dumps(reports,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('root','sources','out','blender'):parser.add_argument('--'+name,type=Path,required=True)
    run(**vars(parser.parse_args()))
