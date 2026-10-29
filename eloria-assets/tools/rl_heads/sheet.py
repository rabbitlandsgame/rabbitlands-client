import sys
from PIL import Image
d=sys.argv[1]; names=sys.argv[2].split(','); out=sys.argv[3]
ims=[Image.open(f'{d}/{n}.png').convert('RGB') for n in names]
W=sum(i.width for i in ims); H=max(i.height for i in ims)
s=Image.new('RGB',(W,H),'white'); x=0
for i in ims: s.paste(i,(x,0)); x+=i.width
s.save(out)
