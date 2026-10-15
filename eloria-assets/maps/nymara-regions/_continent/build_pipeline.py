"""Reproducible continent build, using at most eight logical CPU cores.

The authored master is assembled before named territory/chunk export. Separate
stages support review and repair without silently accepting stale composition.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from build_progress import Progress
import authoring_catalog

HERE=Path(__file__).resolve().parent
CLIENT=HERE.parents[3]
SUNMANE_SCENE='res://world_authoring/regions/sunmane_steppe/sunmane_steppe.tscn'
SUNMANE_SNAPSHOT=CLIENT/'eloria-assets/maps/nymara-regions/sunmane_steppe/authoring/continent-authoring.json'


def find_godot(explicit=None):
    """Resolve the authoring runtime without accepting a stale manual bake."""
    candidates=[]
    if explicit is not None:candidates.append(Path(explicit))
    if os.environ.get('ELORIA_GODOT'):candidates.append(Path(os.environ['ELORIA_GODOT']))
    candidates.extend((CLIENT/'godot-client/Godot_v4.7.2-stable_win64_console.exe',
                       CLIENT/'godot-client/Godot_v4.7.2-stable_win64_console'))
    for candidate in candidates:
        if candidate.is_file():return str(candidate.resolve())
    for name in ('godot','godot4'):
        found=shutil.which(name)
        if found:return found
    searched=', '.join(map(str,candidates))+', godot/godot4 on PATH'
    raise RuntimeError('Godot is required to bake saved continent-authoring scenes; searched '+searched)


def bake_authored_regions(godot=None, catalog_path=None):
    """Bake every catalogued authored territory from its saved scene."""
    executable=find_godot(godot)
    project=CLIENT/'godot-client'
    try:
        imported=subprocess.run([executable,'--headless','--editor','--path',str(project),'--quit'],
                                cwd=CLIENT,check=False,timeout=180)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('Godot asset import did not finish within 180 seconds') from error
    if imported.returncode:
        raise RuntimeError(
            f'Godot asset import failed with exit code {imported.returncode}; fix the reported import errors before baking')
    contracts=authoring_catalog.authored_contracts(
        Path(catalog_path).resolve() if catalog_path is not None else authoring_catalog.CATALOG_PATH)
    if not contracts:
        raise RuntimeError('The territory catalog contains no complete authored scene/spec pairs')
    for contract in contracts:
        try:relative=contract.scene_path.resolve().relative_to(project.resolve()).as_posix()
        except ValueError as error:
            raise RuntimeError(f'{contract.id}: authored scene is outside the Godot project') from error
        command=[executable,'--headless','--path',str(project),
                 '--script','res://src/dev/map_authoring_region/region_bake_cli.gd','--',
                 '--scene','res://'+relative,'--output',str(contract.snapshot_path),
                 '--python',sys.executable]
        try:completed=subprocess.run(command,cwd=CLIENT,check=False,timeout=180)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f'{contract.id}: authoring bake did not finish within 180 seconds') from error
        if completed.returncode:
            raise RuntimeError(f'{contract.id}: authoring bake failed with exit code {completed.returncode}')
        if not contract.snapshot_path.is_file():
            raise RuntimeError(f'{contract.id}: authoring bake reported success without writing its snapshot')


def bake_sunmane(godot=None):
    executable=find_godot(godot)
    project=CLIENT/'godot-client'
    try:
        imported=subprocess.run([executable,'--headless','--editor','--path',str(project),'--quit'],
                                cwd=CLIENT,check=False,timeout=180)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('Godot asset import did not finish within 180 seconds') from error
    if imported.returncode:
        raise RuntimeError(
            f'Godot asset import failed with exit code {imported.returncode}; fix the reported import errors before baking')
    command=[executable,'--headless','--path',str(CLIENT/'godot-client'),
             '--script','res://src/dev/map_authoring_region/region_bake_cli.gd','--',
             '--scene',SUNMANE_SCENE,'--output',str(SUNMANE_SNAPSHOT),'--python',sys.executable]
    try:completed=subprocess.run(command,cwd=CLIENT,check=False,timeout=180)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('Sunmane authoring bake did not finish within 180 seconds') from error
    if completed.returncode:
        raise RuntimeError(f'Sunmane authoring bake failed with exit code {completed.returncode}')
    if not SUNMANE_SNAPSHOT.is_file():
        raise RuntimeError('Sunmane authoring bake reported success without writing its snapshot')


def limit_cores(count):
    for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS','VECLIB_MAXIMUM_THREADS'):
        os.environ[name]='1'
    if os.name=='nt':
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetCurrentProcess.restype=ctypes.c_void_p
        kernel.GetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.POINTER(ctypes.c_size_t)]
        kernel.SetProcessAffinityMask.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
        handle=kernel.GetCurrentProcess();current=ctypes.c_size_t();system=ctypes.c_size_t()
        if not kernel.GetProcessAffinityMask(handle,ctypes.byref(current),ctypes.byref(system)):raise ctypes.WinError(ctypes.get_last_error())
        cores=[i for i in range(ctypes.sizeof(current)*8) if current.value&(1<<i)][:count]
        if not kernel.SetProcessAffinityMask(handle,sum(1<<i for i in cores)):raise ctypes.WinError(ctypes.get_last_error())
    elif hasattr(os,'sched_setaffinity'):
        cores=sorted(os.sched_getaffinity(0))[:count];os.sched_setaffinity(0,cores)
    else:raise RuntimeError('No enforceable processor affinity API on this platform')
    os.environ['ELORIA_BUILD_CORES']=str(len(cores))
    print(f'Continent build CPU affinity: {cores}; numerical workers: 1',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server',type=Path,required=True)
    parser.add_argument('--data',type=Path,required=True,help='Directory for generated server ELM maps')
    parser.add_argument('--artifacts',type=Path,required=True)
    parser.add_argument('--library',type=Path,help='Verified retained-content cache (default artifacts/library)')
    parser.add_argument('--stage',choices=('all','libraries','compose','geometry','contracts','publish','atlas','verify'),default='all')
    parser.add_argument('--cores',type=int,choices=range(1,9),default=8)
    parser.add_argument('--godot',type=Path,help='Godot console executable used to bake registered saved region scenes')
    args=parser.parse_args();limit_cores(args.cores)
    server=args.server.resolve();artifacts=args.artifacts.resolve();artifacts.mkdir(parents=True,exist_ok=True)
    library=(args.library or artifacts/'library').resolve();output=HERE/'generated';output.mkdir(exist_ok=True)
    progress=Progress(output/'progress.json').watch()
    def run(script,*arguments,cwd=CLIENT):
        subprocess.run([sys.executable,'-u',str(script),*map(str,arguments)],cwd=cwd,check=True)
    stages=('libraries','compose','geometry','contracts','publish','atlas','verify') if args.stage=='all' else (args.stage,)
    if any(stage in ('libraries','compose','geometry','contracts') for stage in stages):
        print('Baking saved catalogued authoring scenes',flush=True)
        bake_authored_regions(args.godot)
    for stage in stages:
        print(f'Continent stage: {stage}',flush=True)
        progress.start(stage)
        if stage=='libraries':
            import build_library
            def one(region):run(HERE/'build_library.py','--region',region,'--output',library)
            with ThreadPoolExecutor(max_workers=min(2,args.cores)) as executor:list(executor.map(one,build_library.BUILDERS))
        elif stage in ('compose','geometry'):
            run(HERE/'build_continent.py','--library',library,'--output',output,'--stage','prepare' if stage=='compose' else 'geometry')
        elif stage=='contracts':
            import build_continent as B
            from crossings import prepare_contracts
            from export_contracts import export_contracts
            world,content=B.load_composed(output,library);B.verify_geometry_export(output);prepare_contracts(world)
            manifests={r:json.loads((B.package(r)/'world.json').read_text(encoding='utf-8')) for r in world.ids}
            export_contracts(world,content,manifests,output,server)
            B.publish_geography(world,manifests,output)
        elif stage=='publish':
            run(CLIENT/'eloria-assets/tools/publish_diagonal_continent.py','--server',server,'--publication',output/'publication.json',
                '--report',artifacts/'publication-report.json','--apply','--build','--data',args.data.resolve())
        elif stage=='atlas':
            run(HERE/'atlas_export.py','--output-dir',artifacts/'atlas','--apply')
            # Legacy LOD sidecars must carry the final served metadata before digests.
            run(CLIENT/'eloria-assets/tools/sync_geographic_family.py','--server',server,'--lod-only','--apply')
            run(CLIENT/'eloria-assets/tools/sync_package_content.py','--manifest',server/'config/eloria/client_content_manifest.json','--digests','--apply')
        elif stage=='verify':
            run(HERE/'audit_continent.py','--server',server,'--output',artifacts/'continent-audit.json')
            run(CLIENT/'eloria-assets/tools/build_continent_map.py','--check')
        progress.finish(0)
    print('Requested continent build stages completed.',flush=True)


if __name__=='__main__':main()
