"""Whitehorn's provisioned gate, haul road and pilgrim ascent."""
from __future__ import annotations
import math
import numpy as np
from amberwood import terrain as TER, routecraft as RC, civiccraft as CIV
from amberwood import mountaincraft as MC, props as P, mesh as M
from regionbuild import Placement
import region as REG

ARRIVAL=(-12.0,69.0)
# Points are world metres. Surveyed levels keep carts on the shoulder and
# pilgrims beside the cascades, then climb the temple terrace in switchbacks.
ROADS={
 "gate_court":([(-35,70),(11,70)],[19.66,19.66],17),
 "gate_approach":([(-12,89),(-12,75),(-6,54),(18,39)],[19.66,19.66,20.0,18.66],5.5),
 "supply_link":([(18,39),(45,54),(72,66)],[18.66,22.0,25.8],4.2),
 "mine_haul":([(0,0),(78,-12),(126,18),(176,30),(222,27),(264,-12),
              (330,-18),(350,-59),(356,-88),(346,-109),(318,-123),
              (282,-119),(267,-120),(288,-138)],
             [17.59,19.9,25.0,30.0,35.54,35.3,37.35,39.0,42.0,46.0,50.1,
              50.26,50.26,50.33],5.5),
 "bridge_watch_link":([(126,18),(112,-8),(100,-30),(90,-46)],[25,28,31,31.99],3.4),
 "pilgrim_ascent":([(60,-103),(68,-131),(57,-153),(55,-179),(72,-198),
                    (90,-213),(102,-240),(82,-254),(116,-269),(88,-284),(102,-299)],
                   [22.3,30.2,32.5,34.0,38,42,48.49,53,58.8,64.1,67.85],5.0),
 "temple_vault_walk":([(102,-299),(119,-292),(127,-302),(121,-319)],
                       [67.85,67.85,67.85,67.85],6.0),
 "temple_eyrie_walk":([(102,-299),(85,-291),(77,-306),(79,-320)],
                       [67.85,67.85,67.85,67.85],6.0),
 "north_shrine_path":([(88,-284),(63,-299),(46,-327),(27,-348),(27,-357)],
                       [64.1,66,70,76.76,76.76],3.0),
 "east_shrine_path":([(318,-123),(336,-145),(342,-169),(354,-192)],
                       [50.1,52,55,58.1],3.4),
 "watch_cave_approach":([(-123,-119),(-122,-128),(-122,-137)],[47.3,47.64,47.64],4.0),
 "snowline_path":([(216,-120),(208,-133),(194,-146),(184,-154)],[55.8,55,55,55],4.5),
 "temple_keeper_approach":([(88,-284),(101,-281),(109,-284)],[64.1,64.1,64.1],4.0),
 "upper_bridge_south":([(90,-46),(132,-61),(163,-62),(186,-75)],
                         [31.99,35,39,42.2],3.5),
 "upper_bridge_north":([(186,-126),(208,-133),(230,-127),(267,-120)],
                         [49.4,55,53,50.26],3.5),
 "lower_bridge_south":([(30,-39),(36,-44),(41,-54)],[20,20,18],4.0),
 "cairn_reader_path":([(-82,-198),(-79,-191)],[71.63,71.63],6.0),
 "upper_cascade_path":([(90,-213),(107,-223),(120,-215)],[42,49,51],5.5),
 "lower_cascade_path":([(55,-179),(65,-186),(87,-181)],[34,34,34],5.5),
}
# Each roof is a weather refuge with its open side facing a working court.
# Court levels belong to the terrain; there is no duplicate paving mesh.
SHELTERS=[
 ("GateStore",(-28,61),12,6,0,19.66),
 ("GateWorkshop",(6,61),12,6,0,19.66),
 ("LowerCamp",(72,60),9,5,0,25.8),
 ("BridgeWatch",(90,-46),8,5,math.pi,31.99),
 ("HighOverlook",(224,39),9,5,math.pi,35.54),
 ("EastCamp",(333,-5),10,5,math.pi,37.35),
 ("MineYard",(266,-107),13,6,math.pi,50.26),
 ("TempleRest",(78,-250),8,5,math.pi/2,52),
]
CONTENT_LAYOUT={
 "services":[{"role":"information","position":[-13,19.66,74]},
             {"role":"storage","position":[-30,19.66,66]},
             {"role":"crafting_station","position":[4,19.66,65]},
             {"role":"training","position":[5,19.66,76]}],
 "npcs":{"Sister Arel":[-22,19.66,68],"Korrin":[-29,19.66,64.5],
         "Brother Kell Ivorwind":[-17,19.66,79],"Ration Sister Petch":[-33,19.66,64.5],
         "Ordinal Thrun":[109,64.1,-284],"Mine Captain Sarra Dolt":[270,50.26,-111],
         "Hesk Varne":[277,50.26,-118],"Ice-Cave Sounder Vesk":[-108,30.39,-37],
         "Cascade Watcher Ilun":[63,34,-183],"Rope-Bridge Keeper Adhe":[87,31.99,-51],
         "Shrine Sister Onwe":[27,76.76,-349],"Cairn-Reader Marrow Doun":[-82,71.63,-198],
         "Snowline Ranger Kestrel Vane":[194,55,-146],"Silverleaf Picker Doun Ashe":[341,57,-185]},
 "roadClearance":5.0,
 "harvest":{"Salt":[[119,-168,25],[151,-246,22]],"Peat":[[-71,55,22],[91,87,20]],
            "Crystal":[[277,-147,23],[-106,-49,20]],
            "Stormglass":[[321,-175,22],[142,-291,22]],
            "Silverleaf":[[69,-181,18],[340,-189,22],[-96,-215,24]],
            "Coal":[[284,-152,23],[311,-142,23]],"Quartz":[[302,-182,28],[-94,-150,25]],
            "Flint":[[250,-141,25],[-121,-180,24]],
            "Verdigris":[[344,-185,21],[202,-148,21]],
            "Bramble":[[-79,43,24],[78,83,23]],"Toadstool":[[-86,15,24],[234,55,22]]},
 "wildlife":{}
}
for species in ("whitehorn_yak","frosthorn_elk","thunder_ram"):
 CONTENT_LAYOUT["wildlife"][species]=[[93,78,26],[-82,25,25],[230,54,25]]
for species in ("glacier_ram","whitehorn_ice_ram","cobalt_ibex","glacier_crab"):
 CONTENT_LAYOUT["wildlife"][species]=[[-82,-161,28],[113,-167,25],[290,-178,30]]
for species in ("ice_snow_leopard","rimeclaw","thornhide_wolf","moonshadow_lynx",
                "ice_wolverine","crystal_cave_spider"):
 CONTENT_LAYOUT["wildlife"][species]=[[-98,-224,31],[301,-223,30],[158,-186,27]]
for species in ("iceback_ursid","crystal_polar_bear","obsidian_bear","glacier_troll","snow_yeti"):
 CONTENT_LAYOUT["wildlife"][species]=[[-79,-278,33],[287,-261,33],[161,-268,27]]
for species in ("glacier_harpy","whitehorn_ice_griffin","frost_stone_golem",
                "glacier_titan","frost_wraith_queen","glacier_paladin"):
 CONTENT_LAYOUT["wildlife"][species]=[[-67,-335,32],[170,-343,32],[284,-325,35]]

BRIDGES=[("rope_bridge",(41.0,18.0,-54.0),(61.0,22.3,-104.0)),
         ("rope_bridge_upper",(186.0,42.2,-75.0),(186.0,49.4,-126.0))]

def prepare(t):
 # The pilgrim stair and its side walks use one surveyed shelf datum.
 t.rect_terrace((102,-309),16,13,67.85,0,TER.MARBLE,shoulder=12)
 # A mine's apron is a broad bench with a soft cut face, never an isolated
 # rectangular pad punched into the slope beside a higher cart track.
 RC.grade_road(t,[(251,-115),(279,-127),(293,-138)],[50.26,50.3,50.33],
               width=26,shoulder=14,surface=TER.PATH,clearance=4)
 # The watch cave cuts into an ice-backed shoulder. Its throat stays clear
 # at the front; the rear hood enters rising ground instead of standing free.
 cave_width=np.clip((10.0-abs(t.gx+122.0))/5.0,0,1)
 cave_depth=np.clip((-142.0-t.gz)/5.0,0,1)*np.clip((t.gz+162.0)/7.0,0,1)
 cave_mask=(cave_width*cave_depth)>0
 t.height=np.where(cave_mask,np.maximum(t.height,47.64+6*cave_width*cave_depth),t.height)
 t.surface=np.where(cave_mask,TER.SNOW,t.surface)
 t.tree_block|=cave_mask
 for name,(pts,heights,width) in ROADS.items():
  RC.grade_road(t,pts,heights,width=width,shoulder=6,surface=TER.PAVING
                 if name=="gate_court" else TER.PATH,clearance=3)
 for name,(x,z),w,d,angle,y in SHELTERS:
  # Ground under the wind walls is cut with the same datum as the work floor.
  t.rect_terrace((x,z),w/2+2,d/2+3,y,0,TER.PAVING if "Gate" in name else TER.PATH,shoulder=8)
  t.mark_blocked_disc((x,z),max(w,d)/2+5)

 # Bridgeheads have fixed road stations. Searching the nearest brown pixel
 # after a yard cut could pick both banks on one side of the gorge.
 for name,a,b in BRIDGES:
  a,b=np.asarray(a),np.asarray(b)
  direction=(b[[0,2]]-a[[0,2]])
  length=float(np.linalg.norm(direction));direction/=length
  for point,sign in ((a,-1),(b,1)):
   x,z=point[[0,2]];back=np.array([x,z])+direction*sign*7
   RC.grade_road(t,[back,[x,z]],[float(t.height_at(*back)),point[1]-0.16],
                 width=5.6,shoulder=3,surface=TER.PATH,clearance=3)
  along=((t.gx-a[0])*(b[0]-a[0])+(t.gz-a[2])*(b[2]-a[2]))/length**2
  across=abs((t.gx-a[0])*(b[2]-a[2])-(t.gz-a[2])*(b[0]-a[0]))/length
  profile=a[1]+(b[1]-a[1])*along-1.4*(1-(2*along-1)**2)
  mask=(along>=-2/length)&(along<=1+2/length)&(across<3.0)
  t.height=np.where(mask,np.minimum(t.height,profile-0.22),t.height)
  t.tree_block|=mask

def dress_crossings(build,seed):
 for i,(name,a,b) in enumerate(BRIDGES):
  a,b=np.asarray(a),np.asarray(b)
  length=float(np.linalg.norm(b[[0,2]]-a[[0,2]]));center=(a+b)/2
  angle=math.atan2(-(b[2]-a[2]),b[0]-a[0])
  span=MC.suspension_bridge(length=length,width=2.4,sag=1.4,
                            rise=b[1]-a[1],seed=seed+i)
  node=f"Landmark_rope_bridge_{i:02d}"
  _place(build,node,span,float(center[0]),float(center[2]),float(center[1]),angle,kind="landmark")
  build.landmarks.append({"id":f"whitehorn-rope-bridge-{i:02d}",
    "name":"Whitehorn Rope Bridge","node":node,"type":"bridge",
    "position":[float(center[0]),float(center[1]-1.4),float(center[2])]})
  build.crossings.append({"id":name,"endpoints":[list(map(float,a)),list(map(float,b))]})
 build.notes.append("Two surveyed suspension decks meet their actual banks, with continuous profiled planks.")

def _place(build,key,item,x,z,y,angle=0,kind="prop",collides=False):
 build.add_mesh(key,item)
 build.place(Placement(key,key,(x,y,z),angle,kind=kind,collides=collides))

def dress(build,seed):
 t=build.terrain
 import kit
 _place(build,"Landmark_WatchCave",kit.ice_cave_mouth(seed+407,span=5.0,height=4.0),
         -122,-141,47.64,math.pi,kind="landmark",collides=True)
 build.landmarks.append({"id":"whitehorn-watch-cave","name":"The Cascade Cave",
     "node":"Landmark_WatchCave","type":"cave","position":[-122,47.64,-136]})
 for name,(x,z),w,d,angle,y in SHELTERS:
  roof=CIV.roadside_shelter(w,d,stone="pale_ashlar",roof="snow_pack")
  # Wall rectangles are reserved explicitly by the region collision pass.
  _place(build,"Landmark_"+name,roof,x,z,y,angle,kind="landmark")
  build.landmarks.append({"id":"whitehorn-"+name.lower(),"name":
    {"GateStore":"The Ration House","GateWorkshop":"Gate Repair Shelter",
     "MineYard":"The Hauliers' Yard","TempleRest":"Last Pilgrim Rest"}.get(name,name),
    "node":"Landmark_"+name,"type":"shelter","position":[x,y,z]})
 for i,(x,z,angle) in enumerate([(-2,70,0),(17,69,0),(272,-106,math.pi),(258,-113,0)]):
  _place(build,f"Prop_HaulSledge{i}",MC.ore_sledge(ore="snow_pack" if i<2 else "cliff_rock"),
         x,z,float(t.height_at(x,z)),angle)
 for i,(x,z) in enumerate([(-36,62),(11,61),(70,60),(327,-5),(261,-107)]):
  _place(build,f"Prop_RefugeFuel{i}",P.log_pile(length=2.2,rows=2,per_row=3),x,z,float(t.height_at(x,z)))
 for i,(x,z) in enumerate([(-20,75),(15,75),(69,67),(87,-51),(220,34),(329,-12),(273,-113),(82,-249)]):
  _place(build,f"Prop_RefugeFire{i}",P.brazier(seed=seed+i),x,z,float(t.height_at(x,z)))
 # The temple keeps its marble facade and gains the slender snowy crown in
 # the concept silhouette. Bases enter the existing crown; no exposed planes coincide.
 for i,(dx,height,radius) in enumerate([(-8,12,1.5),(0,20,2.2),(8,12,1.5)]):
  _place(build,f"Landmark_TemplePinnacle{i}",MC.temple_pinnacle(height,radius),
         102+dx,-317,67.85+17.4,kind="landmark")
 for i,(x,z) in enumerate([(-12,48),(38,6),(174,31),(330,-42),(72,-146),(92,-237)]):
  _place(build,f"Prop_RouteSign{i}",P.signpost(seed=seed+i),x,z,float(t.height_at(x,z)))
 build.notes.append("Gate ration house and repair shelter, eight weather refuges, eastern cart saddle and switchback temple ascent.")

def block_walls(blockers,gx,gz):
 for name,(x,z),w,d,angle,y in SHELTERS:
  dx,dz=gx-x,gz-z
  lx=dx*math.cos(angle)-dz*math.sin(angle)
  lz=dx*math.sin(angle)+dz*math.cos(angle)
  blockers |= (abs(lx)<w/2+0.3)&(abs(lz+d/2)<0.55)
  blockers |= (abs(abs(lx)-(w/2-0.24))<0.55)&(abs(lz-0.03)<(d-0.54)/2+0.3)

def roads(t):
 return [{"id":name,"width":width,"points":[[float(x),float(y),float(z)]
          for (x,z),y in zip(pts,heights)]} for name,(pts,heights,width) in ROADS.items()]
