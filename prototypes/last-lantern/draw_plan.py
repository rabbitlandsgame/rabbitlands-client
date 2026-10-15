"""Render the authored layout as a review drawing; no captured images are edited."""
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
layout = json.loads((ROOT/"package/layout.json").read_text())
im = Image.new("RGB", (1500, 1080), "#102b37")
d = ImageDraw.Draw(im)
font_root = Path("C:/Windows/Fonts")
def font(size, bold=False):
    path = font_root/("segoeuib.ttf" if bold else "segoeui.ttf")
    return ImageFont.truetype(str(path),size)

ink, muted, gold = "#edf1e8", "#a8c0c0", "#edc486"
d.text((50,35),"ELORIA   /   OPENING ADVENTURE",font=font(18,True),fill=gold)
d.text((47,65),"Lantern Reach",font=font(48,True),fill=ink)
d.text((50,132),"The Last Lantern · Map and quest draft",font=font(21),fill=muted)
d.text((1080,67),"120 × 120 tiles",font=font(25,True),fill=ink)
d.text((1080,103),"1/36 of Four Gates' area",font=font(19),fill=muted)
d.line((50,179,1450,179),fill="#345461",width=2)
notes = [
    ("The unlit beacon", "Move toward Nesh's lantern.","17,19"),
    ("A hand in the dark", "Caldus, supplies and the chart.","32,32"),
    ("What the shore gives", "3 Reed (21,54) · 1 Quartz (28,59)","24,54"),
    ("Something you made", "Shared cache → craft a Torch.","46,70"),
    ("Hold the path", "Equip → fight → take the loot.","67,53"),
    ("Catch your breath", "Eat → choose Matter or Carry.","83,70"),
    ("The last lantern", "Repair the housing. Light it.","95,96"),
    ("The road is yours", "Trade → ferry → meet Ilyon.","102,24"),
]
for i,(title,body,at) in enumerate(notes):
    y=210+i*91
    d.ellipse((50,y+2,84,y+36),fill="#254752",outline=gold,width=1)
    d.text((61,y+4),str(i+1),font=font(20,True),fill=gold)
    d.text((101,y),title,font=font(22,True),fill=ink)
    d.text((101,y+34),body,font=font(17),fill=muted)

ox,oy,s=535,1000,7
def point(at):
    return (ox+at[0]*s,oy-at[1]*s)
d.rounded_rectangle((515,205,1445,1015),12,fill="#173743",outline="#335662",width=1)
for x in range(0,121,20):
    a=point((x,0)); b=point((x,110))
    d.line((*a,*b),fill="#21434c")
for y in range(0,111,20):
    a=point((0,y)); b=point((120,y))
    d.line((*a,*b),fill="#21434c")
for y in range(120):
    for x in range(120):
        h=layout["walkGrid"][y*120+x]
        if h:
            px,py=point((x,y))
            d.rectangle((px,py-s,px+s,py),fill="#527468" if h < 20 else "#688378")
for route,color,width in [(layout["route"],gold,4),(layout["shortcut"],"#9bc9c5",3)]:
    d.line([point(p) for p in route],fill=color,width=width,joint="curve")
for gate in layout["gates"]:
    x,y=point(gate["at"])
    d.line((x-15,y,x+15,y),fill="#e4a07b",width=6)
for i,area in enumerate(layout["areas"]):
    x,y=point(area["at"])
    d.ellipse((x-18,y-18,x+18,y+18),fill="#122f3c",outline=gold,width=2)
    d.text((x-7,y-14),str(i+1),font=font(21,True),fill=ink)
d.text((1370,226),"N",font=font(21,True),fill=gold)
d.line((1379,290,1379,260),fill=gold,width=2)
d.polygon([(1379,250),(1373,263),(1385,263)],fill=gold)
d.text((549,218),"ONE GUIDED ROUTE",font=font(17,True),fill=muted)
d.text((550,251),"West beach → beacon → east dock",font=font(17),fill=muted)
d.text((1088,809),"RETURN STAIR",font=font(16,True),fill="#b9dcd6")
d.text((1088,835),"Opens after lighting",font=font(15),fill=muted)
d.line((1032,823,1074,823),fill="#9bc9c5",width=2)
d.text((51,986),"Gate progression",font=font(17,True),fill=gold)
d.text((51,1014),"Torch → preparation → beacon lit",font=font(17),fill=muted)
d.text((548,1034),"Authored collision and target positions · Placeholder terrain and art · Private rescue, no failure timer",font=font(16),fill=muted)
im.save(ROOT/"map-plan.png")
print("Wrote map-plan.png")
