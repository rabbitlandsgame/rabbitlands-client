from pathlib import Path
import subprocess,json,sys
ROOT=Path(__file__).resolve().parents[2];CLIENT=ROOT/'godot-client'
OUT=ROOT/'equipment-fit-build/shared-bodies/preview/installed-15-gameplay';OUT.mkdir(exist_ok=False)
GODOT='godot'
races=[f'{r}_{s}' for r in ('luminous','ssarathi','mycelari') for s in ('male','female')]
for race in races:
    for clip in ('Idle_Subtle','Walk','Jog','Run_Female','Fighting_Idle'):
        for angle in ('front','side','gameplay'):
            name=f'{race}-{clip}-{angle}'
            command=[GODOT,'--path',str(CLIENT),'--script','res://tests/canonical_equipment_preview.gd','--',
                     '--slug',race,'--out',str(OUT/(name+'.png')),'--clip',clip,'--angle',angle,
                     '--gear','yes','--hair','yes','--tints','yes','--outfit','3:133,4:219,5:208,6:248,0:114']
            with (OUT/(name+'.log')).open('x') as log:
                subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,creationflags=0x08000000,timeout=180)
            assert (OUT/(name+'.png.json')).exists(),name
            print(name,'OK',flush=True)
print('FINAL_GAMEPLAY_90_COMPLETE',flush=True)
