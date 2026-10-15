from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[2];CLIENT=ROOT/'godot-client'
OUT=ROOT/'equipment-fit-build/shared-bodies/preview/installed-16-neck';OUT.mkdir(exist_ok=False)
GODOT='godot'
for race in ('luminous_male','luminous_female','ssarathi_female','mycelari_female'):
    for clip in ('Idle_Subtle','Run_Female'):
        for angle in ('front','side'):
            name=f'{race}-{clip}-{angle}'
            cmd=[GODOT,'--path',str(CLIENT),'--script','res://tests/canonical_equipment_preview.gd','--',
                 '--slug',race,'--out',str(OUT/(name+'.png')),'--clip',clip,'--angle',angle,
                 '--gear','yes','--hair','no','--tints','no','--outfit','5:228','--region','neck','--cycle','yes']
            with (OUT/(name+'.log')).open('x') as log:
                subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,creationflags=0x08000000,timeout=180)
            print(name,'OK',flush=True)
