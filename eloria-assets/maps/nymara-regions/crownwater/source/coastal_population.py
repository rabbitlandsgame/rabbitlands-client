"""Crownwater's working shores, using the common architectural toolkit."""
import math
import numpy as np
from amberwood import mesh as M, stonework as SW, architecture as ARCH
from amberwood import civiccraft as CIVIC, routecraft as RC, terrain as TER
import coastal_plan as PLAN
import crownarch as CA

def prepare(t):
    """Ground every occupied yard and the landward end of each real pier."""
    import region as REG
    for name,x,z,yaw,w,d in PLAN.HOUSES:
        level=max(2.8,float(t.height_at(x,z)))
        t.rect_terrace((x,z),w/2+1.2,d/2+1.2,level,yaw,TER.PAVING)
        t.mark_blocked_disc((x,z),math.hypot(w,d)/2+1.3)
    for portal,(end,start,level) in PLAN.FERRIES.items():
        island='outer_'+('north' if portal.startswith('north') else 'west' if portal.startswith('west') else 'south')
        cx,cz=PLAN.ANCHORS[island]
        # Side aisles avoid the pavilion's solid centre.
        side=(start[0],cz) if portal.startswith(('north','south')) else (cx,start[1])
        RC.grade_road(t,[side,start],[level,level],width=4.4,shoulder=3.5,surface=TER.PAVING,clearance=2)
        dx,dz=end[0]-start[0],end[1]-start[1];length=math.hypot(dx,dz)
        u=((t.gx-start[0])*dx+(t.gz-start[1])*dz)/(length*length)
        across=np.abs((t.gx-start[0])*dz-(t.gz-start[1])*dx)/length
        mask=(u>=0)&(u<=1.12)&(across<=3.6)
        t.height=np.where(mask,np.minimum(t.height,level-.35),t.height)
    # A short native approach meets the shared level deck exactly at -42m.
    RC.grade_road(t,[(210,-10.5),(222,-10.5)],[4,4],width=7,shoulder=3,
                  surface=TER.PAVING,clearance=3)

def _house(seed,w,d):
    out=SW.MeshGroup()
    # Full-size plaster cottage, shaded windows, tiled low roof and a chimney.
    out.add(M.box((w,.35,d),center=(0,.175,0),material=CA.STONE))
    out.add(M.box((w,3.0,d),center=(0,1.85,0),material='lime_plaster'))
    out.add(CIVIC.pitched_canopy(w+1.0,d+1.2,3.55,5.0,CA.VERDIGRIS))
    out.add(ARCH.door(1.05,2.15,material='timber_dark').translate(0,.35,-d/2-.08))
    for x in (-w*.29,w*.29):
        out.add(ARCH.window(.95,1.1).translate(x,1.5,-d/2-.12))
    out.add(M.box((.8,2.2,.8),center=(w*.3,4.7,d*.22),material=CA.STONE))
    # Material choices are supplied by this regional composition.
    for part in out.parts:
        if part.material not in ('lime_plaster',CA.STONE,CA.VERDIGRIS,'timber_dark','amber_resin'):
            part.material='timber_dark'
    return out

def populate(build,seed):
    from populate import _add
    t=build.terrain
    for i,(name,x,z,yaw,w,d) in enumerate(PLAN.HOUSES):
        level=float(t.height_at(x,z))
        _add(build,'Building_Shore_'+name,'ShoreHouse_'+name,_house(seed+i,w,d),
             (x,level-.03,z),yaw,kind='building',collides=True)
        # Crates and barrels are stored beside the house, clear of its front.
        px=x+math.cos(yaw)*(w/2+1.0);pz=z-math.sin(yaw)*(w/2+1.0)
        _add(build,'Prop_ShoreCargo_'+name,'ShoreCrate',
             M.box((.9,.85,.85),center=(0,.425,0),material='timber_warm'),
             (px,float(t.height_at(px,pz)),pz),yaw,kind='prop',collides=True)
    for i,(portal,(end,start,level)) in enumerate(PLAN.FERRIES.items()):
        dx,dz=end[0]-start[0],end[1]-start[1];length=math.hypot(dx,dz)+2
        deck=CIVIC.sloped_boardwalk(length,level,level,width=4.2,foot=-7,
                                    timber='timber_warm',rope='timber_dark')
        _add(build,'Walk_PacketPier_'+portal,'PacketPier_'+portal,deck,
             (start[0],0,start[1]),math.atan2(dx,dz),kind='landmark')
        build.crossings.append({'id':'pier-'+portal,'endpoints':[
            [start[0],level,start[1]],[end[0],level,end[1]]]})
        side=(dz/math.hypot(dx,dz),-dx/math.hypot(dx,dz))
        _add(build,'Prop_PacketBoat_'+portal,'PacketBoat',CA.moored_boat(seed=seed+i),
             (end[0]+side[0]*5,-.18,end[1]+side[1]*5),math.atan2(dx,dz),kind='prop')
    deck=CIVIC.arcaded_causeway(8.5,4,4,width=7,arches=1,foot=-9,
                              stone=CA.STONE,paving='cobble_paving',trim=CA.MARBLE)
    _add(build,'Walk_FourGatesNativeLanding','FourGatesNativeLanding',deck,
         (224.25,0,-10.5),kind='landmark')
    build.crossings.append({'id':'four-gates-native','endpoints':[[220,4,-10.5],[228.5,4,-10.5]]})
    # Preserve both names/IDs at each old route while giving the station a real
    # sheltered waiting place, visibly separate from the departure plank.
    for route,(x,z) in {'east-quay':(202,-35),'north-quay':(161,-229),
                         'west-quay':(-78,-147),'south-quay':(30,88)}.items():
        y=float(t.height_at(x,z))
        for prefix in ('march','station'):
            node='March_'+route.replace('-','_')+('_Stone' if prefix=='march' else '_Station')
            if prefix=='march':
                mesh=M.box((.75,1.5,.3),center=(0,.75,0),material=CA.STONE)
                pos=(x-4,y,z)
            else:
                mesh=CIVIC.market_shelter(width=6,depth=3,stone=CA.STONE,roof=CA.VERDIGRIS)
                pos=(x,y,z)
            _add(build,node,node,mesh,pos,kind='landmark')
            build.landmarks.append({'id':prefix+'-'+route,'name':route.replace('-',' ').title()+(' Route Stone' if prefix=='march' else ' Waiting Shelter'),
                'node':node,'type':'waystation','position':list(pos),
                'serverTile':[math.floor(pos[0]+120),math.floor(120-pos[2])]})
