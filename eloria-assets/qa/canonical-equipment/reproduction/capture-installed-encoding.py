from pathlib import Path
import json,subprocess,sys,shutil,time,hashlib
from PIL import Image
import numpy as np
ROOT=Path.cwd();BUILD=ROOT/'equipment-fit-build';PREVIEW=BUILD/'preview'
log=BUILD/'reports/canonical-delivery-validation.log'
while not log.exists() or 'installed-editor-import exit 0' not in log.read_text():time.sleep(15)
checks=[]
for race in ['luminous_male','luminous_female','ssarathi_female','mycelari_female']:
    for clip,view in [('Idle_Subtle','front'),('Run_Female','side')]:
        subprocess.run([shutil.which('pwsh'),'-NoProfile','-File','eloria-assets/tools/capture_canonical_equipment.ps1','-Slugs',race,'-Prefix','installed-encoding-militia','-Outfit','0:114,3:133,4:219,5:208,6:248','-Clips',clip,'-Angles',view],check=True)
        a=PREVIEW/f'final-militia_{race}_{clip}_{view}.png';b=PREVIEW/f'installed-encoding-militia_{race}_{clip}_{view}.png'
        x,y=[np.asarray(Image.open(p).convert('RGBA')) for p in [a,b]]
        changed=int(np.any(x!=y,axis=2).sum())
        checks.append(dict(race=race,clip=clip,view=view,scratch_sha256=hashlib.sha256(a.read_bytes()).hexdigest(),installed_sha256=hashlib.sha256(b.read_bytes()).hexdigest(),changed_pixels=changed,max_channel_difference=int(np.abs(x.astype(int)-y.astype(int)).max())))
        print('INSTALLED_RENDER',race,clip,'changed pixels',changed,flush=True)
(BUILD/'reports/installed-encoding-image-comparison.json').write_text(json.dumps(checks,indent=2)+'\n')
assert all(row['changed_pixels']==0 for row in checks)
print('INSTALLED_IMAGES_IDENTICAL',len(checks),flush=True)
