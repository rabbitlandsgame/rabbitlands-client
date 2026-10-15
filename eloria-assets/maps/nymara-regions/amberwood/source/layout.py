"""Amberwood's inhabited river terraces and surveyed forest connections."""
from __future__ import annotations
import math
import numpy as np
from amberwood import region as REG, terrain as TER, routecraft as RC
from amberwood import civiccraft as CIV, woodlandcraft as WOOD, props as P
from amberwood import stonework as SW, mesh as M, waterfront as WATER
from regionbuild import Placement

ARRIVAL=(24.0,-171.0)
# Exact shore surveys, frozen before terraces are cut. All endpoints are world XYZ.
BRIDGES=[
 ("old-bridge","Millrace Bridge",(43,40.0,-135),(39,40.8,-159),5.0,"stone"),
 ("high-bridge","The Long Span",(96,44.4,-208),(143,44.0,-185),5.0,"stone"),
 ("ridge-bridge","The Ridge Span",(131,52.2,-330),(173,53.0,-284),4.5,"stone"),
 ("mill-footbridge","Mill Keeper's Walk",(-8,28.2,-126),(-44,27.4,-130),4.8,"wood"),
 ("moot-bridge","The Grove Footbridge",(-28,40.8,-187),(-41,38.0,-210),3.4,"wood"),
 ("harbour","Resinlanding",(-90,3.2,24),(-135,1.6,24),5.0,"wood"),
 ("kelp-landing","Kelp Landing",(-62,3.2,72),(-99,1.4,72),4.8,"wood"),
]
LEVELS={
 "coast_road":[3.2,3.2,5.4,10,16,20,26,29,30.1],
 "harbour_road":[1.8,2.6,3.2,5.4,10,15,23,27,28.31],
 "settlement_road":[28.31,30,34,38,40,40.8,40.8,44,46,46.77,51.24],
 "ridge_road":[46.77,46,44.4,44,46,47,49.62],
 "north_ridge_road":[51.03,52,52.2,53,56,57.88,55,49.62],
 "cove_road":[30.1,30.1,29,24,14,8,11,18,24.5,27,26.33],
 "lake_road":[26.33,30,35,36,36.5,36.5,36.48],
 "far_grove_road":[35,31,26,24,37,45,50],
 "west_lodge_road":[26.33,24.5,18,8],
 "stone_ring_road":[5.4,10,16,17,16],
 "meadow_road":[15,10.74,7,3.2,3.2,1.8],
 "south_coast_road":[3.2,2.8,3,3.5,4,8,12.19],
 "hollow_road":[40.8,41,42,42,40.8,38,36,29,27,26.33],
 "diggings_road":[56.42,58,59.45,56,52,51.03],
 "canopy_road":[44,48,48.8,50,54,55,56.5,58],
 "timber_road":[12.19,16,20,23.57,25,26,27,29.15],
 "orchard_road":[19.5,19,17.76,18.5,20,19.5,17,16.82],
}
EXTRA_ROADS={
 "moot_court":([(-12,-177),(9,-180),(24,-171)],[42,41,40.8],7),
 "guild_walk":([(24,-171),(47,-171),(64,-160)],[40.8,41,41.4],6),
 "mill_lane":([(12,-119),(-8,-126),(-44,-126),(-43,-106)],[30.1,28.2,27.4,27.2],4),
 "orchard_cart_link":([(48,125),(63,111),(90,102),(114,97),(138,88)],[4,8,12.03,15,17.76],5.5),
 "quarry_haul":([(216,102),(221,119),(225,136),(237,155)],[23.57,22,19,16.82],6),
 "north_pass":([(72,-312),(67,-337),(63,-355),(72,-373),(72,-384)],[51.24,51,51,55,55],5),
 "boundary_approach":([(288,-288),(283,-279),(280,-272)],[58.84,58,57],3),
 "grove_school":([(-43,-323),(-48,-316),(-48,-302),(-48,-294)],[26,30,34,36],3),
 "coppice_work_lane":([(173,-284),(183,-312),(177,-339),(176,-362)],[53,55,58,61.6],5),
 "whitehorn_continuation":([(72,-373),(72,-384),(72,-402),(72,-430)],[55,55,57,63],12),
 "moor_continuation":([(150,140),(156,162),(156,180),(158,200)],[12,11,10,9],8),
 "gorge_continuation":([(360,-54),(393,-66),(414,-66),(438,-68)],[38.25,41.8,42,43],8),
}
LODGE_POSTS=[
 ((7,-205),(24,-193)),((58,-178),(35,-177)),((-6,-208),(20,-202)),
 ((61,-224),(51,-220)),((-2,-165),(20,-172)),((58,-139),(46,-144)),
 ((37,-231),(53,-232)),((66,-245),(55,-239))]
CONTENT_LAYOUT={
 "services":[{"role":"information","position":[24,40.8,-164]},
             {"role":"storage","position":[13,40.8,-177]},
             {"role":"crafting_station","position":[40,41,-177]},
             {"role":"training","position":[40,40.8,-162]}],
 "npcs":{"Eryn Amber":[18,40.8,-170],"Tomas Root":[11,40.8,-177],
         "Resin Trader":[31,40.8,-166],"Hall Steward":[-8,42,-176],
         "Amber Master":[54,41.4,-164],"Harbour Master":[-83,3.2,31],
         "Kelp Landing Factor Hesper":[-62,3.2,66],
         "Canopy Rigger":[58,48,-200],"Grove Reader Nesh Pallid":[-44,26,-323],
         "Nine Watchers Hermit Bode":[-50,17,-29]},
 "roadClearance":5.0,
 "primaryArrivalOnly":True,
 "harvest":{
 "Resin":[[89,-275,24],[114,-294,25],[4,-263,26]],
 "Hearthroot":[[104,109,21],[56,114,24],[10,10,25]],
 "Toadstool":[[-22,-240,23],[-47,-308,23],[3,-291,22]],
 "Kelp":[[-57,69,12]],"Coal":[[244,18,23],[224,144,20]],
 "Stormglass":[[337,-59,25],[362,-166,28]],
 "Orchid":[[-3,-266,25]],"Peat":[[-16,112,22]],
 "Bramble":[[105,76,24]],"Cotton":[[81,132,21]],
 "Wheat":[[64,114,18]],"Seed":[[107,98,17]],
 "Bog Iron":[[238,151,19]],"Sage":[[100,110,20]]},
 "wildlife":{}
}
for species in ("amberhart","amberwood_owl","lantern_stag","moss_badger","amber_lantern_moth",
                "berry_bramble_boar","autumn_antler_stag","russet_faun","sapling_sprite"):
 CONTENT_LAYOUT["wildlife"][species]=[[76,76,27],[39,30,27],[86,-14,22]]
for species in ("rootback_boar","moss_bear","mossback_boar","autumn_bramble_boar",
                "brambleback_boar","elderwood_stag","giant_amber_moth","amberwood_great_owl",
                "autumn_crown_stag","mossback_badger","giant_badger"):
 CONTENT_LAYOUT["wildlife"][species]=[[13,-254,26],[114,-253,26],[207,63,27]]
for species in ("briarhide_wolf","thornhide_wolf","moss_armored_hound","thornbark_wolf",
                "moonshadow_lynx","moss_bugbear","sporefolk","owlbear","mossbound_stone_golem"):
 CONTENT_LAYOUT["wildlife"][species]=[[161,-269,29],[277,-161,27],[-4,-320,29]]
for species in ("thornwood_dryad_queen","spectral_forest_knight","autumn_bark_treant",
                "elderwood_dryad_queen","spectral_forest_duelist","moss_bearded_giant","ember_leaf_spirit"):
 CONTENT_LAYOUT["wildlife"][species]=[[273,-259,28],[183,-350,29],[332,-192,29]]

def prepare(t,seed):
 # Smooth inhabited benches before their approaches. The mill is below town,
 # on the outlet; the western huts occupy dry shore rather than a seabed.
 for pts,ys,w in [
  ([(7,-177),(42,-172)],[40.8,40.8],26),
  ([(-17,-191),(-8,-181)],[43,42],18),
  ([(60,-154),(69,-150)],[41.4,41.4],20),
  ([(-73,-170),(-54,-172)],[8,8],23),
  ([(-68,-228),(-54,-228)],[24.5,24.5],19),
  ([(-87,30),(-61,36)],[3.2,5.4],18),
  ([(-43,-118),(-31,-118)],[27.2,27.2],13),
  ([(215,144),(240,155)],[17,16.82],19)]:
  RC.grade_road(t,pts,ys,width=w,shoulder=10,surface=TER.PAVING,clearance=3)
 # The channels keep their downhill survey when roads later grade their banks.
 t.amberwood_water=[]
 for name,points in REG.STREAMS.items():
  if name=="grove_burn":
   points=[(-24,-372),(-43,-351),(-50,-330),(-55,-297),(-60,-270),(-62,-242),(-58,-218),(-70,-194),(-82,-180)]
  line,bed=RC.incise_channel(t,points,width=3.8,shoulder=14,floor=-.8)
  t.amberwood_water.append((name,np.c_[line[:,0],bed+.32,line[:,1]]))
 for name,ys in LEVELS.items():
  RC.grade_road(t,REG.ROUTES[name],ys,width=5.5 if name in ("harbour_road","settlement_road","timber_road","orchard_road") else 4.2,
                shoulder=7,surface=TER.PATH,clearance=3)
 for name,(pts,ys,w) in EXTRA_ROADS.items():
  # Border roads occupy broad saddles and drainage valleys. Their shoulders
  # must shape the whole hill, rather than cut a slot through the old rim.
  shoulder=60 if name=="whitehorn_continuation" else 24 if name.endswith("_continuation") else 6
  RC.grade_road(t,pts,ys,width=w,shoulder=shoulder,surface=TER.PATH,clearance=3)
 for x,z in [(-79,-168),(-50,-181),(-43,-155)]:
  y=max(8,float(t.height_at(x,z)))
  RC.grade_road(t,[(x-3,z),(x+3,z)],[y,y],width=13,shoulder=6,surface=TER.PATH,clearance=3)
 # Court should be one clear ground surface, with two distinct market rows.
 RC.grade_road(t,[(6,-174),(44,-174)],[40.8,40.8],width=26,shoulder=8,surface=TER.PAVING,clearance=4)
 # The guild hall shares the village bench. Re-establish it after shaping
 # the river valley so bank blending cannot scoop out its entrance.
 RC.grade_road(t,[(64,-160),(66,-150)],[41.4,41.4],width=20,shoulder=8,surface=TER.PAVING,clearance=3)
 for i,(site,toward) in enumerate(LODGE_POSTS):
  y=float(t.height_at(*site))
  RC.grade_road(t,[site,toward],[y,float(t.height_at(*toward))],width=7,shoulder=4,surface=TER.PATH,clearance=2)
  t.rect_terrace(site,6,6,y,0,TER.PAVING)
 # Each bridge owns only the ground beneath its deck. The real bank road
 # reaches its exact end, with a 16 cm recess under the emitted walking skin.
 for key,name,a,b,w,kind in BRIDGES:
  a,b=np.asarray(a),np.asarray(b);delta=b[[0,2]]-a[[0,2]]
  length=float(np.linalg.norm(delta));direction=delta/length
  for point,sign in ((a,-1),(b,1)):
   if point[1]<2:continue
   back=point[[0,2]]+direction*sign*6
   RC.grade_road(t,[back,point[[0,2]]],[float(t.height_at(*back)),point[1]-.16],
                 width=w+1.6,shoulder=3,surface=TER.PATH,clearance=3)
  along=((t.gx-a[0])*delta[0]+(t.gz-a[2])*delta[1])/length**2
  across=abs((t.gx-a[0])*delta[1]-(t.gz-a[2])*delta[0])/length
  profile=a[1]+(b[1]-a[1])*along
  mask=(along>=-2/length)&(along<=1+2/length)&(across<w/2+1.5)
  t.height=np.where(mask,np.minimum(t.height,profile-.22),t.height);t.tree_block|=mask
 RC.grade_road(t,[(-29,-125),(-29,-112)],[25.5,25.3],width=3.5,shoulder=1.5,
               surface=TER.ROCK,clearance=1)
 # Stepped monument faces south, up from the actual forecourt. Its old
 # rotated stair climbed away from the approach.
 RC.grade_road(t,[(174,-54),(174,-82),(174,-89.3)],[32.92,36.8,37.0],
               width=11,shoulder=6,surface=TER.PAVING,clearance=4)
 top=37+4.4*np.clip((-89.3-t.gz)/9.2,0,1)
 mask=(abs(t.gx-174)<11.5)&(t.gz>-113)&(t.gz<-88)
 t.height=np.where(mask,np.minimum(t.height,top-.24),t.height)
 t.tree_block|=mask

def _move(build,node,x,z,y=None,angle=None):
 p=next((p for p in build.placements if p.node==node),None)
 if p is None:return
 p.position=(x,float(build.terrain.height_at(x,z))-.15 if y is None else y,z)
 if angle is not None:p.rotation_y=angle
 for bucket in (build.landmarks,build.interactives):
  for item in bucket:
   if item.get("node")==node:item["position"]=list(p.position)

def _place(build,key,item,x,y,z,angle=0,kind="prop",collides=False):
 build.add_mesh(key,item)
 build.place(Placement(key,key,(x,y,z),angle,kind=kind,collides=collides))

def dress(build,seed):
 t=build.terrain
 replaced={"Landmark_HighBridge","Landmark_OldBridge","Landmark_RidgeBridge",
           "Landmark_Harbour_Dock","Prop_Dock_Small","Landmark_KelpLanding","Prop_RetainingWall_0"}
 build.placements[:]=[p for p in build.placements if p.node not in replaced]
 build.landmarks[:]=[l for l in build.landmarks if l.get("node") not in replaced]
 for i,(key,name,a,b,w,kind) in enumerate(BRIDGES):
  a,b=np.asarray(a),np.asarray(b);length=float(np.linalg.norm(b[[0,2]]-a[[0,2]]));center=(a+b)/2
  if kind=="stone":
   item=CIV.arcaded_causeway(length,a[1],b[1],width=w,arches=3,foot=min(a[1],b[1])-16,
                            stone="rubble_stone",trim="carved_wood")
   angle=math.atan2(-(b[2]-a[2]),b[0]-a[0])
  else:
   item=CIV.sloped_boardwalk(length,a[1],b[1],width=w,foot=-8 if key in ("harbour","kelp-landing") else min(a[1],b[1])-8,
                            timber="timber_grey",rope="timber_dark")
   # The timber recipe begins at local Z=0; masonry is centred.
   item.translate(0,0,-length/2)
   angle=math.atan2(b[0]-a[0],b[2]-a[2])
  node="Landmark_Survey_"+key
  _place(build,node,item,float(center[0]),0,float(center[2]),angle,kind="landmark")
  build.crossings.append({"id":key,"endpoints":RC.crossing_endpoints([a,b],inset=2)})
  build.landmarks.append({"id":key,"name":name,"node":node,"type":"bridge" if "bridge" in key else "harbour",
                          "position":list(map(float,center))})
 for i,(site,toward) in enumerate(LODGE_POSTS):
  _move(build,f"Building_Lodge_{i:02d}",*site,angle=math.atan2(toward[0]-site[0],toward[1]-site[1]))
 for i in range(10):
  x=7+(i//2)*8;z=-185 if i%2==0 else -160
  _move(build,f"Prop_MarketStall_{i}",x,z,y=40.72,angle=0 if i%2==0 else math.pi)
 _move(build,"Interact_Well_Market",1,-177,y=40.75)
 _move(build,"Interact_AmberBench_1",44,-178,y=40.8,angle=math.pi/2)
 # A real mill serves the pool's descending outlet.
 _move(build,"Building_Lodge_14",-34,-118,y=27.0,angle=0)
 build.meshes["Mill_Water"]=WOOD.watermill(seed+670,wheel_height=1.15)
 p=next(p for p in build.placements if p.node=="Building_Lodge_14");p.mesh="Mill_Water"
 build.landmarks.append({"id":"mill-house","name":"The Race Mill","node":p.node,"type":"building","position":list(p.position)})
 # Town silhouettes and sightline: the Mother rises above its neighbouring crowns.
 for node in ("Landmark_GreatTree_Wood","Landmark_GreatTree_Canopy"):
  p=next(p for p in build.placements if p.node==node);p.scale=1.28
 _move(build,"Landmark_GreatArch",174,-102,y=37.0,angle=0)
 next(l for l in build.landmarks if l["id"]=="great-arch")["position"][1]=41.4
 _place(build,"Landmark_GateCellar",RC.vault_entry(stone="rubble_stone",wood="timber_dark",roof="shingles"),
        190,float(t.height_at(190,-96)),-96)
 build.landmarks.append({"id":"gate-cellar","name":"The Gate Undercroft","node":"Landmark_GateCellar",
                         "type":"building","position":[190,float(t.height_at(190,-96)),-96]})
 # The northern cove watch belongs to the dry point, not the landing itself.
 _move(build,"Landmark_Watchtower_7",-46,-194)
 for i,site,toward in [(16,(-79,-168),(-63,-168)),(17,(-50,-181),(-63,-181)),(18,(-43,-155),(-60,-165))]:
  _move(build,f"Building_Lodge_{i:02d}",*site,angle=math.atan2(toward[0]-site[0],toward[1]-site[1]))
 for i in range(5):
  _move(build,f"Prop_RowingBoat_{i}",-141-i%2*5,19+i*4,y=-.18,angle=math.pi/2)
 _move(build,"Prop_KelpBoat",-105,76,y=-.18,angle=math.pi/2)
 packet=SW.group(P.rowing_boat(seed=seed+670))
 packet.scale(2.5)
 _place(build,"Prop_HarbourPacket",packet,-145,-.25,28,math.pi/2)
 _place(build,"Prop_PacketRig",WATER.lateen_rig(8),-145,.6,28,math.pi/2)
 # Roadside work roofs group storage, guild work and freight without closed facade rooms.
 for name,(x,z),w,angle in [
  ("TownStore",(9,-193),10,0),("GuildAwning",(43,-193),10,0),
  ("HarbourFreight",(-82,33),12,math.pi),("QuarryShelter",(232,143),10,0)]:
  y=float(t.height_at(x,z))
  _place(build,"Landmark_"+name,CIV.market_shelter(w,4,stone="rubble_stone",timber="timber_dark",roof="shingles"),
         x,y,z,angle)
 for i,(x,z) in enumerate(((61,107),(69,112),(78,118))):
  _place(build,f"Prop_CultivatedGrain_{i}",RC.crop_rows(8,5,seed+i,material="thatch_reed"),
         x,float(t.height_at(x,z)),z)
 for i,(x,z) in enumerate(((210,143),(214,149),(237,152))):
  _move(build,f"Prop_Cart_{i+1:03d}",x,z,angle=math.pi)
 build.notes.append("Amberwood circulation: a mill below a market town, seven surveyed crossings, dry coast settlements and graded cart approaches.")

def finish(build):
 t=build.terrain
 build.water_meshes["Water_Streams"]=M.merge([WOOD.water_ribbon(stations,2.6 if name=="garden_rill" else 3.6)
                                            for name,stations in t.amberwood_water],"water_stream")
 # Remove random blocking furniture from the through aisle. Trees and bushes
 # retain their seeded scatter, then the shared corridor pass clears approaches.
 corridors=[[[x,y,z] for (x,z),y in zip(REG.ROUTES[name],ys)] for name,ys in LEVELS.items()]
 corridors.extend([[[x,y,z] for (x,z),y in zip(pts,ys)] for pts,ys,w in EXTRA_ROADS.values()])
 corridors.extend([[list(a),list(b)] for _,_,a,b,_,_ in BRIDGES])
 RC.clear_walk_corridors(build,corridors,{"tree":4,"rock":3,"undergrowth":3,"ground-detail":2.5})
 trunks={p.node.removesuffix("_Wood") for p in build.placements if p.node.startswith("Tree_") and p.node.endswith("_Wood")}
 build.placements[:]=[p for p in build.placements if not
                       (p.node.startswith("Tree_") and p.node.endswith("_Canopy") and p.node.removesuffix("_Canopy") not in trunks)]
 # Closed buildings state their solid footprints for the mandatory stamp pass.
 for p in build.placements:
  if p.kind!="building":continue
  old=p.node
  if not old.startswith("Landmark_"):
   p.node="Landmark_"+old
  found=False
  for item in build.landmarks:
   if item.get("node")==old:
    item["node"]=p.node;found=True
    if item["type"]!="settlement":item["function"]=item["type"];item["type"]="building"
  if not found:
   build.landmarks.append({"id":old.lower().replace("_","-"),"name":"Timber Lodge",
                           "node":p.node,"type":"building","position":list(p.position)})
 build.placements[:]=[p for p in build.placements if not
  (p.node.startswith("Prop_") and p.collides and p.node not in ("Prop_MarketStall_0",)
   and 6<p.position[0]<43 and -180<p.position[2]<-165)]
