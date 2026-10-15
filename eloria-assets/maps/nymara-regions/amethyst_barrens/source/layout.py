"""Glasswarden road surveys, service yard and content geography."""
from __future__ import annotations
import math
import numpy as np
import region as REG
from region import Placement
from amberwood import terrain as TER, routecraft as RC, civiccraft as CIV
from amberwood import mesh as M, props as PROP

STONE="amethyst_pale_stone"
ROAD="alpine_gravel"
DOORS={
 "resonant-vault-stair":(-78,-196.2),
 "geode-hollow-mouth":(333,-99),
 "shardworks-headframe":(122,-42),
 "storm-barrow-stair":(216,-147),
 "sour-cut-mouth":(192,-261),
 "measure-house-door":(143,-58),
 "counting-house-door":(275,-80),
}
CONTENT_LAYOUT={
 "services":[{"role":"information","position":[-4,5,-8]},
             {"role":"storage","position":[7,5,-22]},
             {"role":"crafting_station","position":[15,5,-22]},
             {"role":"training","position":[16,5,-9]}],
 "roadClearance":4.5,
 "npcs":{"Ione Brass":[-8,5,-12],"Varric Lens":[12,5,-18],
 "Observatory Warden Sela Prism":[-87,10,-179],
 "Tuning Adept Ollum Ghast":[300,5,85],
 "Field Station Cook Naia Flint":[-24,5,-17],
 "Shard Counter Bel Ammon":[276,5,-84],
 "Geode Digger Torvin Slate":[-114,8,-294],
 "Storm-Ruin Surveyor Ash Kell":[210,5,-144],
 "Freight Factor Nils Corrow":[338,5,80],
 "Watchtower Sentinel Ivar Quill":[354,7,-33],
 "Shard-Hauler Damu Orun":[-20,5,4],
 "Cluster Warden Peri Vance":[120,5,-47],
 "Deaf Digger Ollo Marrow":[191,15,-258],
 "Grinder Vell":[-122,8,-292]},
 "harvest":{"Clay":[[148,-109,21],[209,0,22]],
 "Crystal":[[131,-44,20],[93,-232,20]],"Stormglass":[[204,-169,23],[64,-280,23]],
 "Geode":[[311,-104,22],[200,-251,21]],"Silverleaf":[[9,-138,20]],
 "Toadstool":[[-111,-290,21]],"Verdigris":[[264,-177,23],[81,67,20]],
 "Coal":[[-87,-71,21],[275,-89,22]],"Quartz":[[16,21,20],[335,21,20]],
 "Thistle":[[53,48,21],[-46,29,23]]},"wildlife":{}
}
for names,spots in [
 (("stormglass_grazer","amethyst_moth","dusk_camel"),[[30,62,24],[-61,-115,24]]),
 (("crystal_mite","crystal_carapace_beetle","amethyst_stag_beetle"),[[107,-65,23],[246,-29,23]]),
 (("crystal_shore_crab",),[[318,111,24],[277,-331,25]]),
 (("cobalt_ibex",),[[55,-310,25],[276,-267,24]]),
 (("resonant_hound","amethyst_scorpion","coal_kobold"),[[198,-122,26],[279,-206,26]]),
 (("crystal_cave_spider","crystal_dire_wolf","barrens_wisp"),[[-90,-297,24],[223,-242,24]]),
 (("prism_wyrm","crystal_wing_griffin","amethyst_stone_golem","arcane_core_colossus","arcane_crystal_automaton"),[[176,-302,29],[259,-278,27]])]:
 for name in names:CONTENT_LAYOUT["wildlife"][name]=spots

def prepare(t):
 # River levels are fixed from the natural channel before roads and rebates.
 level=float(t.height_at(0,0))
 RC.grade_road(t,[(-30,-20),(23,-20)],[level]*2,width=24,shoulder=7,
               surface=TER.RESONANT_ROAD,clearance=3)
 # Grade the long approach up the observatory's sheltered terrace.
 obs=float(t.height_at(*REG.ANCHORS["observatory"]))-0.4
 RC.grade_road(t,[(-72,-144),(-78,-162),(-78,-185.5)],
               [max(level,float(t.height_at(-72,-144))),obs,obs],
               width=8,shoulder=8,surface=TER.RESONANT_ROAD,clearance=3)
 # Freeze exact bank levels before any route crosses them.
 t._survey={}
 for name,pts in REG.BRIDGE_ROUTES.items():
  t._survey[name]=(pts,[max(1.8,float(t.height_at(*p))+0.2) for p in pts])
 # The shore is a raised headland. Start inland at its surveyed height so the
 # pier meets the cargo road instead of creating a cut-off low deck in a rebate.
 t._survey["ferry_jetty"]=(np.array([[333.,72.],[350.,118.]]),
                            [max(1.8,float(t.height_at(333.,72.))+0.2),1.8])
 for name,pts in REG.ROUTES.items():
  if name=="observatory_approach":continue
  hs=[max(1.6,float(t.height_at(*p))) for p in pts]
  RC.grade_road(t,pts,hs,width=5.6 if "road" in name else 4.0,shoulder=4.0,
                surface=TER.RESONANT_ROAD,clearance=3)
 for name,(pts,hs) in t._survey.items():
  a,b=pts;run=b-a;length=float(np.linalg.norm(run));direction=run/length
  width=5.4 if name!="ferry_jetty" else 3.6
  for point,h,sign in ((a,hs[0],-1),(b,hs[1],1)):
   if name=="ferry_jetty" and sign==1:continue
   back=point+direction*sign*7
   RC.grade_road(t,[back,point],[max(1.6,float(t.height_at(*back))),h-0.18],
                 width=width+2,shoulder=4,surface=TER.RESONANT_ROAD,clearance=3)
  along=((t.gx-a[0])*run[0]+(t.gz-a[1])*run[1])/length**2
  across=np.abs((t.gx-a[0])*run[1]-(t.gz-a[1])*run[0])/length
  mask=(along>=-2.5/length)&(along<=1+2.5/length)&(across<width/2+3)
  t.height=np.where(mask,np.minimum(t.height,hs[0]+(hs[1]-hs[0])*along-0.2),t.height)
  t.tree_block|=mask
 for x,z in DOORS.values():
  h=float(t.height_at(x,z))
  RC.grade_road(t,[(x,z+5),(x,z-5)],[h,h],width=6,shoulder=5,
                surface=TER.RESONANT_ROAD,clearance=2)

def dress_crossings(build,seed):
 for i,(name,(pts,hs)) in enumerate(build.terrain._survey.items()):
  a,b=pts;length=float(np.linalg.norm(b-a));width=5.4
  if name=="ferry_jetty":
   width=3.6
   mesh=CIV.sloped_boardwalk(length,*hs,width=width,foot=-18,
          timber="timber_grey",rope="amethyst_brass")
   mesh.translate(0,0,-length/2);rotation=math.atan2(b[0]-a[0],b[1]-a[1])
  else:
   mesh=CIV.arcaded_causeway(length,*hs,width=width,arches=max(2,round(length/12)),
          foot=min(hs)-9,stone=STONE,paving=ROAD,trim=STONE)
   # End lanterns mark each crossing without reducing the cart width.
   for u in (0.03,0.97):
    x=(u-0.5)*length;y=hs[0]+(hs[1]-hs[0])*u
    for sign in (-1,1):
     mesh.add(M.cylinder(0.22,0.16,3.2,8,material=STONE).translate(x,y,sign*3.25))
     mesh.add(M.icosphere(0.26,1,material="amethyst_crystal").translate(x,y+3.5,sign*3.25))
   rotation=math.atan2(-(b[1]-a[1]),b[0]-a[0])
  node=f"Landmark_SurveyedBridge_{i}"
  build.add_mesh(name,mesh)
  build.place(Placement(node,name,((a[0]+b[0])/2,0,(a[1]+b[1])/2),rotation,kind="landmark"))
  identity=f"amethyst-crystal-bridge-{i}" if i<7 else "amethyst-ferry-jetty"
  build.landmarks.append({"id":identity,"name":"Amethyst Crystal Bridge" if i<7 else "Crownwater Packet Jetty",
   "node":node,"type":"bridge","position":[float((a[0]+b[0])/2),sum(hs)/2,float((a[1]+b[1])/2)]})
  ends=[[float(a[0]),hs[0],float(a[1])],[float(b[0]),hs[1],float(b[1])]]
  build.crossings.append({"id":name,"endpoints":RC.crossing_endpoints(ends)})

def dress(build,seed):
 t=build.terrain
 shelter=CIV.market_shelter(width=14,depth=6,stone=STONE,timber="amethyst_brass",roof="amethyst_banner")
 build.add_mesh("AssayExchange",shelter)
 build.place(Placement("Landmark_AssayExchange","AssayExchange",(11,float(t.height_at(11,-23)),-23),kind="landmark"))
 build.landmarks.append({"id":"glasswarden-assay-exchange","name":"Glasswarden Assay Exchange",
  "node":"Landmark_AssayExchange","type":"market","position":[11,float(t.height_at(11,-23)),-23]})
 # A cellar door outside the observatory and two small roadside premises.
 for key in ("measure-house-door","counting-house-door"):
  x,z=DOORS[key];y=float(t.height_at(x,z))
  mesh=RC.vault_entry(stone=STONE,roof="amethyst_verdigris",wood="amethyst_brass")
  node="Door_"+key
  build.add_mesh(node,mesh);build.place(Placement(node,node,(x,y,z-5),collides=True,kind="building"))
  build.landmarks.append({"id":key+"-entry","node":node,"name":key.replace("-"," ").title(),
   "type":"building","position":[x,y,z-5]})
 # Cargo and drinking water mark the pause before the open basin.
 for i,(x,z) in enumerate([(-19,0),(-18,2),(334,78),(336,78)]):
  mesh=PROP.crate(size=1.1,seed=seed+3200+i)
  import populate as POP
  POP._remap(mesh,POP.KIT_TO_REGION)
  key=f"Freight_{i}";build.add_mesh(key,mesh)
  build.place(Placement(key,key,(x,float(t.height_at(x,z)),z),collides=True,kind="prop"))
 boat=PROP.rowing_boat(length=5.4,beam_width=1.8,seed=seed+3300)
 build.add_mesh("PacketTender",boat)
 build.place(Placement("PacketTender","PacketTender",(353,0.05,110),-0.84,kind="prop"))
 build.notes.append("Glasswarden service yard, seven surveyed crystal bridges, cove packet jetty and working habitat rings.")
