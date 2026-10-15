"""Sunmane's surveyed caravan roads, watered pastures and service court."""
from __future__ import annotations
import math
from types import SimpleNamespace
import numpy as np
from amberwood import routecraft as RC, civiccraft as CIV, woodlandcraft as WOOD, mesh as M

ROADS = {
 "west_caravan": [(0,0),(-25,0),(-30,0),(-42,0),(-52,0),(-72,2),(-84,6)],
 "east_caravan": [(0,0),(25,0),(42,0),(62,0),(78,-2),(90,-6)],
 "north_barrow": [(0,0),(11,-2),(12,-12),(10,-21),(0,-25),(0,-30),(18,-34),(22,-46),(20,-62),(12,-74)],
 "south_shore": [(0,0),(0,25),(4,32),(4,40),(4,58),(-4,66),(-14,80)],
 "northwest_pasture": [(-30,0),(-27,-16),(-31,-28),(-43,-28),(-46,-38),(-50,-46)],
 "southeast_mill": [(4,32),(20,30),(36,32),(44,38),(52,48)],
 "northeast_watch": [(32,0),(34,-10),(35,-28),(47,-40),(58,-44)],
 "southwest_cove": [(0,30),(-18,28),(-30,25),(-42,25),(-55,25),(-55,46)],
}
TRAILS = {
 "mill_ridge": [(44,38),(58,36),(64,28),(72,18)],
 "well_loop": [(-30,0),(-29,13),(-28,24),(-18,35),(-9,40)],
 "pen_loop": [(34,0),(35,-12),(46,-18),(54,-26)],
 "stone_circle": [(-43,-28),(-46,-23),(-44,-18)],
 "dock_spur": [(-55,46),(-59,49),(-64,52)],
 "east_camp": [(62,0),(70,10),(71,21)],
 "north_camp": [(-31,-28),(-26,-35),(-30,-40)],
 "desert_road": [(12,-74),(8,-90),(8,-108),(8,-126),(8,-138)],
 "drovers_camp": [(8,-108),(-5,-113),(-19,-113)],
 "salt_pan_spur": [(8,-108),(-10,-112),(-25,-119),(-32,-124)],
 "badland_track": [(8,-126),(32,-126),(52,-120),(70,-112),(87,-108),(99,-100)],
 "dune_crossing": [(20,-62),(34,-78),(46,-88),(60,-100),(70,-112)],
 "mountain_approach": [(8,-126),(10,-142),(2,-152)],
 "east_pass": [(71,21),(94,12),(110,-6),(118,-22),(128,-30)],
 "spire_walk": [(99,-100),(105,-88),(115,-86),(119,-91),(124,-96)],
 "north_inn": [(12,-74),(20,-73),(26,-72)],
 "barrow_approach": [(18,-34),(9,-34),(2,-35)],
 "arrival_lane": [(21,21),(21,28),(8,30),(0,25)],
 "west_inn": [(-45,0),(-45,8)],
 "east_inn": [(45,0),(45,7)],
 "south_inn": [(4,51),(-3,51)],
 "cave_watch": [(60,-100),(67,-107),(70,-112),(70,-117)],
 "frontier_watch": [(115,-86),(110,-80),(100,-80),(98,-85)],
 "well_garden": [(-28,24),(-31,22),(-33,24)],
}
LEVELS = {
 "west_caravan":[9.6,9.6,9.5,9.1,8.8,8,7],
 "east_caravan":[9.6,9.6,11.2,12.4,13.2,12.6],
 "north_barrow":[9.6,9.6,9.6,9.6,9.6,9.4,9.4,10,10.8,12],
 "south_shore":[9.6,9.6,9.3,9,8.4,8,8],
 "northwest_pasture":[9.5,9.5,9.5,9,9,9],
 "southeast_mill":[9.3,9.2,9,8.8,8.4],
 "northeast_watch":[10.3,10.6,11.1,11.8,12],
 "southwest_cove":[9.4,8.9,8.2,7.8,7.4,6.7],
 "desert_road":[12,14,14.8,15.2,20],
 "drovers_camp":[14.8,13.2,12.6],
 "badland_track":[15.2,15,15.5,16.5,16,17],
 "dune_crossing":[10.8,12,13.2,14.5,16.5],
 "spire_walk":[17,18,20,22,24],
 "cave_watch":[14.5,16,16.5,17.2],
 "east_pass":[12.6,13,14,15.5,16],
 "arrival_lane":[9.6,9.6,9.4,9.6],
 "north_inn":[12,12,12], "west_inn":[9.1,9.1], "east_inn":[11.3,11.3],
 "south_inn":[8.6,8.6], "barrow_approach":[9.4,9.4,9.4], "well_garden":[8.2,8.2,8.2],
}
BRIDGES = [
 ("West Ford",(-42,9.1,0),(-30,9.5,0),5.0),
 ("Pasture Walk",(-43,9,-28),(-31,9.5,-28),3.4),
 ("Cove Drovers Bridge",(-42,7.8,25),(-55,7.4,25),3.6),
]
STREAM = [(-14,8.6,-65),(-26,8.2,-55),(-38,7.6,-45),(-38,7.2,-28),
          (-34,6.8,-14),(-36,6.4,0),(-31,6.15,9),(-33,5.95,19),(-49,5.6,27),
          (-57,4.4,40),(-65,2.8,53),(-82,0.15,70)]
POOLS = [(-14,-65,5,8.6),(-4,-34,3.6,8.2),(-58,26,4.5,5.4),
         (-46,42,4.7,5.2),(54,-35,4.4,9.6),(37,50,5,6.5)]
FIELDS = ((30,38,7,5),(50,46,6,5),(-47,18,5,4),(-25,-56,6,4),(29,-57,5,5))
INNS = ((-45,14,math.pi),(45,13,math.pi),(26,-72,-math.pi/2),(-9,51,math.pi/2))
PADS = [((-45,14),9.1,9),((45,13),11.3,9),((26,-72),12,9),((-9,51),8.6,9),((-19,-113),12.6,9.5)]
NPCS = {
 "Orun khan":(4,-2),"Khanet Berel Suran":(6,-3),"Guest-Right Judge Oru Bakhan":(-5,-3),
 "Elder Sura":(-5,1),"Kesh":(6,5),"Seasonal market broker":(-6,5),
 "Caravan Doctor Nesrin":(-12,5),"Crossroads well keeper":(-4,11),"Well-Digger Harun Tel":(-2,14),
 "West caravan master":(-45,5),"East caravan master":(45,5),
 "Camp horse master":(-29,-34),"Herd-Mother Tamu Ashai":(-28,-31),
 "Banner shrine keeper":(-25,-35),"Banner Boy Suvi":(-23,-33),
 "Barrow warden":(6,-34),"Steppe miller":(43,34),"Grain Tallyman Sef Corrin":(39,35),
 "Dune well keeper":(5,-91),"Salt-pan factor":(60,-98),
 "Wind caves watch":(67,-110),"Wind-Cave Listener Esku":(65,-108),
 "Amethyst prospector":(121,-94),"Whitehorn range warden":(100,-82),
 "Salt Rider Onen Dur":(58,-97),"Cove landing factor":(-53,45),"Rider Anse":(30,5),
}
CONTENT = {
 "primaryArrivalOnly": True, "roadClearance": 3.1, "requireFullWildlife": True,
 "services":[{"role":role,"position":[x,9.71,z]} for role,x,z in [
     ("information",4,19),("storage",-4,8),("crafting_station",6,11),("training",7,17)]],
 "npcs":{name:[x,0,z] for name,(x,z) in NPCS.items()},
 "harvest":{
     "Wheat":[[x,z,max(w,d)] for x,z,w,d in FIELDS],
     "Seed":[[31,40,6],[-23,-54,6],[56,45,5]],
     "Sage":[[-49,18,5],[57,-38,6],[-25,49,7],[-17,-110,7],[43,-98,7]],
     "Clay":[[-55,35,5],[-45,-41,5]], "Flint":[[-35,-64,7],[56,-56,7]],
     "Crystal":[[114,-103,7],[116,-63,7]],"Salt":[[-16,-120,7],[58,-114,6]],
     "Iron Ore":[[124,-42,6],[-45,-122,6]],
     "Resin":[[-51,38,7],[74,48,6]],"Thistle":[[95,22,10],[-26,47,8]],
     "Geode":[[108,-102,8]],"Verdigris":[[123,-44,7]],"Coal":[[122,-43,7]],
 }, "wildlife":{},
}
for species in ("dunrunner","golden_plains_horse","suncrest_heron","red_fox","glowhorn_sheep","skystripe_antelope"):
 CONTENT["wildlife"][species]=[[-44,-48,17],[39,42,17],[76,-37,19],[97,26,17]]
for species in ("steppe_aurochs","golden_bison","sunmane_cat","dire_wolf","giant_mole","jadefeather_raptor"):
 CONTENT["wildlife"][species]=[[75,-63,19],[39,-73,16],[-37,-96,20],[107,-26,17]]
for species in ("plains_griffin","stormmane_lion","highland_orc","ironhorn_minotaur","storm_chimera","azure_hyena"):
 CONTENT["wildlife"][species]=[[109,-65,22],[100,-115,20],[-29,-116,19]]

def sculpt(gx,gz,height,classes,cell):
 """Use the shared road grader against this legacy heightfield."""
 t=SimpleNamespace(gx=gx,gz=gz,height=height,surface=classes,
                   tree_block=np.zeros(height.shape,bool),cell=cell,
                   _write_strength=lambda *args:None)
 def grade(points,ys,width,shoulder=4):
  RC.grade_road(t,points,ys,width=width,shoulder=shoulder,surface=2,clearance=0)
 grade([(-1,0),(1,0)],[9.6,9.6],49,4)
 grade([(21,20),(21,28)],[9.6,9.6],6,3)
 for (x,z),y,r in PADS:grade([(x-.1,z),(x+.1,z)],[y,y],r*2,4)
 for name,points in {**ROADS,**TRAILS}.items():
  if name in LEVELS:grade(points,LEVELS[name],5 if name in ROADS else 3.4)
 for name,a,b,width in BRIDGES:
  grade([(a[0],a[2]),(b[0],b[2])],[a[1]-.12,b[1]-.12],width+1,3)
 line=np.asarray(STREAM,float)
 original=t.height.copy()
 grade(line[:,[0,2]],line[:,1]-.7,3.8,3)
 t.height=np.minimum(t.height,original)
 for x,z,r,level in POOLS:
  distance=np.hypot(gx-x,gz-z);edge=np.clip((distance-r*.55)/(r*.75),0,1)
  blend=1-edge*edge*(3-2*edge)
  t.height=np.minimum(t.height,t.height*(1-blend)+(level-.8)*blend)
 for name,a,b,width in BRIDGES:
  a,b=np.asarray(a,float),np.asarray(b,float);direction=(b-a)/np.linalg.norm((b-a)[[0,2]])
  for end,sign in ((a,-1),(b,1)):
   outside=end+direction*3*sign
   grade([outside[[0,2]],end[[0,2]]],[outside[1]-.12,end[1]-.12],width+.6,1.6)
 return t.height

def geometry(mesh):
 from glb import Geometry
 faces=mesh.indices.reshape(-1,3).copy()
 points=mesh.positions[faces]
 face_normals=np.cross(points[:,1]-points[:,0],points[:,2]-points[:,0])
 reversed_faces=np.einsum("ij,ij->i",face_normals,mesh.normals[faces].mean(axis=1))<0
 faces[reversed_faces]=faces[reversed_faces][:,::-1]
 out=Geometry();out.add(mesh.positions,mesh.normals,mesh.uvs,faces.ravel())
 return out

def emit_bridges(builder,materials,landform):
 for index,(name,a,b,width) in enumerate(BRIDGES):
  a,b=np.asarray(a,float),np.asarray(b,float);length=float(np.linalg.norm((b-a)[[0,2]]))
  group=CIV.sloped_boardwalk(length,a[1],b[1],width,foot=min(a[1],b[1])-5,
                             timber="timber_warm",rope="leather")
  group=group.transformed(M.translation(a[0],0,a[2]) @ M.rotation_y(math.atan2(b[0]-a[0],b[2]-a[2])))
  node="Structure_Bridge_%02d"%index
  for prefix,parts in ((node,group.by_material().values()),("Walk_Bridge_%02d"%index,group.by_material(walk=True).values())):
   builder.emit(prefix,[(geometry(mesh),materials[mesh.material]) for mesh in parts])
  builder.landmarks.append({"id":node,"name":name,"kind":"bridge","node":node,
    "position":((a+b)/2).tolist(),"serverTile":[round((a[0]+b[0])/2+58),round(58-(a[2]+b[2])/2)],"reachable":True})

def emit_water(builder,landform,material):
 builder.emit("Water_SteppeBeck",[(geometry(WOOD.water_ribbon(STREAM,1.8)),material)])
