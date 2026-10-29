import sys, json
from PIL import Image, ImageDraw
d=sys.argv[1]; names=json.load(open(d+'/names.json')); cols=int(sys.argv[2]) if len(sys.argv)>2 else 4
import os
op=lambda p: Image.open(p) if os.path.exists(p) else None
tiles=[('base',op(d+'/base_f.png'),op(d+'/base_s.png'))]+[(n,op(d+f'/{i:02d}_f.png'),op(d+f'/{i:02d}_s.png')) for i,n in enumerate(names)]
W0,H0=tiles[0][1].size
tw,th=(2*W0 if tiles[0][2] else W0),H0+24
rows=(len(tiles)+cols-1)//cols
s=Image.new('RGB',(cols*tw,rows*th),'white'); dr=ImageDraw.Draw(s)
for k,(n,f,sd) in enumerate(tiles):
    x,y=(k%cols)*tw,(k//cols)*th; s.paste(f.convert('RGB'),(x,y+20))
    if sd: s.paste(sd.convert('RGB'),(x+W0,y+20)); dr.text((x+4,y+4),n,fill=(0,0,0))
s.save(d+'/gallery.png')
