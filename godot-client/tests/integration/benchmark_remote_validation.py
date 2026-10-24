"""Phase11 actual coverage attestation; no engine or asset reads."""
from __future__ import annotations
import math

def validate_remote(presentation, coverage, requested, label, expected_nodes=None):
    def fail(message): raise ValueError(f'{label}: {message}')
    def integer(value, name, minimum=0):
        if isinstance(value,bool) or not isinstance(value,int) or value<minimum:
            fail(f'invalid {name}')
        return value
    if requested not in ('legacy','rust'): fail('unsupported remote request')
    if presentation is None and requested=='legacy': return
    if not isinstance(presentation,dict) or presentation.get('requested')!=requested:
        fail('actual remote request differs')
    if presentation.get('backend')!=requested: fail('remote service fell back or was not requested')
    if requested=='legacy': return
    if presentation.get('reason')!='experimental_remote_rust' or presentation.get('fallbacks')!=0:
        fail('remote fallback or unavailable service')
    if not isinstance(coverage,dict): fail('missing actual remote coverage')
    counts={k:integer(coverage.get(k),k) for k in
            ('actorNodes','localLegacy','eligibleRemote','nativeOwned','legacySupported','mountedOwned','deferredOwned')}
    excluded=coverage.get('unsupportedRemote')
    if not isinstance(excluded,dict) or any(not isinstance(k,str) for k in excluded):
        fail('missing unsupported remote census')
    excluded_total=sum(integer(v,'unsupportedRemote') for v in excluded.values())
    if counts['localLegacy']+counts['eligibleRemote']+excluded_total!=counts['actorNodes'] \
            or counts['eligibleRemote']!=counts['nativeOwned']+counts['legacySupported']:
        fail('remote coverage partitions disagree')
    if expected_nodes is not None and counts['actorNodes']!=expected_nodes:
        fail('remote census disagrees with actor/body census')
    if counts['legacySupported'] or excluded_total:
        fail('supported crowd comparison has unowned or unsupported remote actors')
    if counts['mountedOwned']>counts['nativeOwned'] or counts['deferredOwned']>counts['nativeOwned']:
        fail('remote subcensus exceeds coverage')
    native=presentation.get('native')
    if not isinstance(native,dict) or native.get('ready') is not True or native.get('remote_api')!=1:
        fail('native remote API not instantiated')
    if native.get('active_bindings')!=counts['nativeOwned']:
        fail('Rust dense state disagrees with live weak bindings')
    for name in ('event_calls','physics_calls','physics_outputs','motion_total_us','action_total_us',
                 'surface_total_us','sink_total_us','event_boundary_us_nested','physics_total_us',
                 'physics_apply_us_nested','transfer_total_us','full_server_apply_us','full_action_sink_us'):
        value=presentation.get(name)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
            fail(f'missing/nonfinite complete-boundary cost counter {name}')
    gate=presentation.get('ordinaryGate')
    if not isinstance(gate,dict) or gate.get('backend')!='rust' or gate.get('failures')!=0:
        fail('ordinary shared gate clock fell back')
    if counts['nativeOwned'] and presentation.get('ownedActors')!=counts['nativeOwned']:
        fail('weak binding count disagrees with live native census')

def validate_remote_cell(cell,requested):
    if requested!='rust': return
    name=cell.get('id','unknown')
    census=cell.get('census',{})
    snapshots=[]
    for point in ('afterSpawn','afterSample'):
        boundary=census.get(point,{})
        remote=boundary.get('remotePresentation',{})
        validate_remote(remote.get('presentation'),remote.get('coverage'),requested,
                        f'{name}.{point}',boundary.get('nodes'))
        snapshots.append(remote['presentation'])
    before,after=snapshots
    for key in ('physics_calls','physics_outputs','event_calls'):
        if after[key]<before[key]: raise ValueError(f'{name}: remote lifetime counter regressed')
    if cell.get('count',1)>1 and (after['physics_outputs']<=before['physics_outputs']
                                or after['event_calls']<=before['event_calls']):
        raise ValueError(f'{name}: requested remote path did not execute between warmup/sample boundaries')
