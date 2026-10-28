import sys, numpy as np
from PIL import Image
d=sys.argv[1]; tag=sys.argv[2]
out=[]
for v in ('front','side'):
    g=np.asarray(Image.open(d+f'/game_{v}.png').convert('RGB')).astype(int); m=np.asarray(Image.open(d+f'/mpfb_{v}.png').convert('RGB')).astype(int)
    gm=(g.sum(2)<700); mm=(m.sum(2)<700)
    img=np.full(g.shape,255,np.uint8)
    img[gm&~mm]=(230,80,80); img[mm&~gm]=(80,80,230); img[gm&mm]=(170,150,200)
    # grid every 1 cm (ortho 0.36 m over 800 px => 22.2 px/cm)
    for y in range(0,800,22): img[y,:]=np.minimum(img[y,:],235)
    out.append(Image.fromarray(img))
s=Image.new('RGB',(1400,800),'white'); s.paste(out[0],(0,0)); s.paste(out[1],(700,0)); s.save(d+f'/overlay_{tag}.png')
