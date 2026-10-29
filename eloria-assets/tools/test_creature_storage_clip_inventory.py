import json,struct
from pathlib import Path
import pytest
from run_creature_storage_qa import validate_source_clip_inventory


def job(tmp_path, names=('Idle_A','Unused_Attack')):
    doc={'asset':{'version':'2.0'},'buffers':[{'byteLength':0}],
         'animations':[{'name':name} if name is not None else {} for name in names]}
    raw=json.dumps(doc).encode();raw+=b' '*((-len(raw))%4)
    source=tmp_path/'source.glb';source.write_bytes(struct.pack('<III',0x46546c67,2,20+len(raw))+struct.pack('<II',len(raw),0x4e4f534a)+raw)
    witness=tmp_path/'witness.json';witness.write_text(json.dumps({'clips':{'Idle_A':[],'Unused_Attack':[]}}))
    return {'source':str(source),'witness':str(witness)}


def test_complete_original_witness_inventory(tmp_path):
    assert validate_source_clip_inventory(job(tmp_path))==['Idle_A','Unused_Attack']


def test_missing_unused_slot_in_witness_rejected(tmp_path):
    j=job(tmp_path);Path(j['witness']).write_text(json.dumps({'clips':{'Idle_A':[]}}))
    with pytest.raises(ValueError,match='original GLB native slots'):validate_source_clip_inventory(j)


def test_explicit_inventory_cannot_omit_unmapped_native_slot(tmp_path):
    j=job(tmp_path);j['all_native_clips']=['Idle_A']
    with pytest.raises(ValueError,match='original GLB native slots'):validate_source_clip_inventory(j)


def test_complete_explicit_inventory(tmp_path):
    j=job(tmp_path);j['all_native_clips']=['Unused_Attack','Idle_A']
    assert validate_source_clip_inventory(j)==['Idle_A','Unused_Attack']


@pytest.mark.parametrize('names',[('Idle_A',None),('Idle_A','Idle_A'),()])
def test_ambiguous_source_inventory_rejected(tmp_path,names):
    with pytest.raises(ValueError):validate_source_clip_inventory(job(tmp_path,names))
