"""Preserve two legacy identities on surveyed habitat after the actor guard.

Run before the shared relocation audit. This is an exact authored migration,
not a larger nearest-ground search. It never changes geometry or counts.
"""
from pathlib import Path
import argparse

POSTS=(
    ('spawns.txt','heartwood_treant',(35,346),(66,304),
     'Northern forest pocket, clear5x5 court outside the public ascent.'),
    ('harvesting.txt','62',(169,37),(191,56),
     'Quartz on the damp limestone shoulder, clear3x3 standing area.'),
)

def rewrite(text,filename):
    rows=text.splitlines();changes=[]
    for name,identity,old,new,reason in POSTS:
        if name!=filename:continue
        old_rows=[];new_rows=[]
        for index,line in enumerate(rows):
            f=[s.strip() for s in line.split('|')]
            if len(f)<5 or f[1]!='verdant_stair' or f[2]!=identity:continue
            point=(int(f[3]),int(f[4]))
            if point==old:old_rows.append(index)
            if point==new:new_rows.append(index)
        if not old_rows:
            if len(new_rows)!=1:raise ValueError((filename,identity,'Missing original and authored post'))
            continue
        if len(old_rows)!=1 or new_rows:raise ValueError((filename,identity,'Ambiguous authored identity'))
        index=old_rows[0];fields=rows[index].split('|')
        fields[3]=' '+str(new[0])+' ';fields[4]=' '+str(new[1])+(' ' if len(fields)>5 else '')
        rows[index]='|'.join(fields);changes.append((identity,old,new,reason))
    return '\n'.join(rows)+'\n',changes

def apply(server,write=False):
    report=[]
    for filename in sorted({p[0] for p in POSTS}):
        path=Path(server)/'config/eloria'/filename
        old=path.read_text(encoding='utf-8');new,changes=rewrite(old,filename)
        if write and changes:path.write_text(new,encoding='utf-8')
        report.extend((filename,*row) for row in changes)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    for row in apply(args.server,args.apply):print(row)
