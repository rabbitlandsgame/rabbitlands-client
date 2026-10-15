"""Exact authored reseats preserve duplicate species counts and resource IDs."""
import reseat_guarded_content as R

def test_only_the_stranded_treant_moves_and_the_reseat_is_idempotent():
    old='spawn | verdant_stair | heartwood_treant | 35 | 346\nspawn | verdant_stair | heartwood_treant | 258 | 294\nspawn | verdant_stair | heartwood_treant | 157 | 180\n'
    first,changes=R.rewrite(old,'spawns.txt')
    assert len(changes)==1
    assert first.count('heartwood_treant')==3
    assert '| 66 | 304\n' in first
    assert '| 258 | 294\n' in first and '| 157 | 180\n' in first
    second,changes=R.rewrite(first,'spawns.txt')
    assert second==first and changes==[]

def test_resource_identity_and_kind_survive_the_reseat():
    first,changes=R.rewrite('node | verdant_stair | 62 | 169 | 37 | Quartz\n','harvesting.txt')
    assert [p.strip() for p in first.split('|')]==['node','verdant_stair','62','191','56','Quartz']
    assert len(changes)==1
    assert R.rewrite(first,'harvesting.txt')==(first,[])
