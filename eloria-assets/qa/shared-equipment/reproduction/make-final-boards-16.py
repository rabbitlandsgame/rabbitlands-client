from pathlib import Path
from PIL import Image,ImageDraw,ImageOps

BASE=Path(__file__).resolve().parent/'preview'
OUT=BASE/'final-16-boards';OUT.mkdir(exist_ok=True)
def board(name,rows,cols=3,size=(480,430)):
    w,h=size;canvas=Image.new('RGB',(w*cols,h*len(rows)),(24,30,37));draw=ImageDraw.Draw(canvas)
    for r,row in enumerate(rows):
        for c,(label,path) in enumerate(row):
            im=Image.open(path).convert('RGB');im.thumbnail((w,h-28))
            canvas.paste(im,(c*w+(w-im.width)//2,r*h+28))
            draw.text((c*w+8,r*h+7),label,fill='white')
    canvas.save(OUT/(name+'.jpg'),quality=92)
    print(OUT/(name+'.jpg'))

for sex in ('male','female'):
    races=['luminous','votary','glasswarden','greyhaven','orun','stoneborn','ssarathi','mycelari']
    for start in (0,4):
        rows=[]
        for race in races[start:start+4]:
            slug=f'{race}_{sex}';folder='shared13-open-exceptions' if race in ('ssarathi','mycelari') else 'shared13-open-remaining'
            rows.append([(f'{slug} / {a}',BASE/folder/f'{slug}-after-Idle_Subtle-{a}-gear.png') for a in ('front','side','back')])
        board(f'neck-{sex}-{start//4+1}',rows)

for sex in ('male','female'):
    rows=[]
    for outfit in ('militia','phoenix','amberwood04'):
        slug=f'luminous_{sex}-{outfit}-complete'
        rows.append([(f'{sex} / {outfit} / {v}',BASE/'shared-16-blender'/f'{slug}{suffix}.png') for v,suffix in [('armour',''),('worn','_worn')]])
    board(f'blender-sets-{sex}',rows,2,(1000,590))
rows=[]
for race in ('ssarathi','mycelari'):
    for sex in ('male','female'):
        slug=f'{race}_{sex}-militia-complete'
        rows.append([(f'{race} {sex} / {v}',BASE/'shared-16-blender'/f'{slug}{suffix}.png') for v,suffix in [('armour',''),('worn','_worn')]])
board('blender-exceptions',rows,2,(1000,590))

gameplay=BASE/'installed-15-gameplay'
for race in ('luminous','ssarathi','mycelari'):
    for sex in ('male','female'):
        slug=f'{race}_{sex}'
        rows=[[(f'{slug} / {clip} / {angle}',gameplay/f'{slug}-{clip}-{angle}.png') for angle in ('front','side','gameplay')]
              for clip in ('Idle_Subtle','Walk','Jog','Run_Female','Fighting_Idle')]
        if all(p.exists() for row in rows for _,p in row):board(f'godot-{slug}',rows)
