"""Amberwood pilot: a working woodland town between upland beck and hay meadow."""
from __future__ import annotations
import math
import numpy as np
from amberwood import landscape as LAND, region as REG, terrain as TER
from amberwood import noise as N, props as P, routecraft as RC, mesh as M
from regionbuild import Placement
import layout

GROUND_MATERIALS = {TER.FOREST: "woodland_loam", TER.PATH: "woodland_track",
                    TER.MEADOW: "woodland_sward"}
# Hayfields belong to the low south-west, while the Mother and remote uplands
# retain old growth. Each meadow is an irregular joined area, not a POI disc.
MEADOWS = [(22, 18, 43, 28), (59, 45, 41, 32), (67, 101, 49, 30),
           (-4, -28, 29, 21), (132, -170, 26, 19)]
STALLS = [(6,-186,.04),(14,-185,-.06),(24,-185,.02),(34,-183,-.12),
          (43,-180,-.40),(8,-157,3.10),(19,-157,3.20),(30,-155,3.05),
          (-82,41,2.8),(232,152,2.9)]
EXPLORATION_ROADS = {"grove_floor_walk": np.asarray([(-12,-216),(24,-235),
                                                     (20,-251),(42,-276)],float)}


def prepare(t, seed):
    # This supporting giant has no platform attached. Set its roots west of
    # the grove floor walk, leaving a window through the overlapping crowns.
    t.giant_site_overrides = {2: (-12.0, -263.0)}
    edges = (N.value_noise(t.gx/19, t.gz/19, seed+611)-.5)*.32
    meadow = np.zeros_like(t.height)
    for x,z,rx,rz in MEADOWS:
        radius = np.hypot((t.gx-x)/rx, (t.gz-z)/rz) + edges
        meadow = np.maximum(meadow, 1-LAND.smoothstep(.68,1.18,radius))
    t.woodland_open = meadow
    # Broad grass pockets and sheltered woodland soil. Remove tiny anonymous
    # meadow islands; retain deliberately cultivated and formal plots.
    natural = np.isin(t.surface,[TER.FOREST,TER.MEADOW])
    t.surface[natural & (meadow>.35)] = TER.MEADOW
    t.tree_block |= meadow>.68
    # Busy paved court is continuous; its graded core was already established
    # by layout.prepare. The southeast corner rounds into the mill road.
    court = ((t.gx>1)&(t.gx<48)&(t.gz>-187)&(t.gz<-156))
    t.surface[court]=TER.PAVING
    t.surface_strength[court]=1
    t.tree_block |= court
    # Repaint routes at a human scale without changing their surveyed beds.
    for name,points in REG.ROUTES.items():
        w = 5.2 if name in ("settlement_road","harbour_road","timber_road") else 3.0
        LAND.worn_path(t,points,w,seed+N.stable_hash(name)%997,
                       TER.SCORCHED if name in ("burnt_track","charcoal_track") else TER.PATH)
    for points in EXPLORATION_ROADS.values():
        LAND.worn_path(t,points,3.2,seed+807)
    # The garden remains formally planted; household yards are small and useful.
    for site,toward in layout.LODGE_POSTS:
        x,z=site
        t.rect_terrace((x,z),6,6,float(t.height_at(x,z)),surface=TER.PATH,shoulder=5)
        LAND.worn_path(t,[site,toward],2.4,seed+int(x-z))


def density(t, seed):
    streams=[stations[:,[0,2]] for _,stations in t.amberwood_water]
    roads=list(REG.ROUTES.values())+[v[0] for v in layout.EXTRA_ROADS.values()]+list(EXPLORATION_ROADS.values())
    d,road,moisture=LAND.grove_density(t,roads,streams,seed,open_ground=t.woodland_open)
    d*=1-LAND.smoothstep(292,372,t.gx)*.90
    t.woodland_moisture=moisture
    return d,road


def dress(build, seed):
    t=build.terrain
    # Shift surplus stalls to freight destinations. Keep the through aisle and
    # stable service posts clear; preserve ten stalls as useful trade activity.
    for i,(x,z,angle) in enumerate(STALLS):
        layout._move(build,f"Prop_MarketStall_{i}",x,z,y=float(t.height_at(x,z))-.07,angle=angle)
    # Stock is stacked beside its stall, leaving the market aisle unobstructed.
    stock={'Sack_139':(8,-182),'Sack_150':(15,-181),'Sack_154':(24,-181),
           'Firewood_162':(34,-180),'Firewood_163':(37,-180),
           'Barrel_024':(43,-174),'BasketAmber_128':(7,-159),
           'Crate_070':(26,-181),'LogPile_218':(44,-176)}
    for p in build.placements:
        match=next((v for key,v in stock.items() if key in p.node),None)
        if match:p.position=(match[0],float(t.height_at(*match)),match[1])
    build.placements[:]=[p for p in build.placements if 'FenceSplit_256' not in p.node]
    # Working gardens behind two lodges, with open-ended fences and short paths.
    for i,(x,z) in enumerate([(-10,-216),(71,-228),(74,-146)]):
        for j,offset in enumerate([-2.0,0.0,2.0]):
            key=f"Prop_KitchenBed_{i}_{j}"
            plot=RC.crop_rows(5,1.1,seed+900+i*7+j,material="undergrowth",height_range=(.22,.48))
            layout._place(build,key,plot,x,float(t.height_at(x,z+offset)),z+offset)
        for j,dz in enumerate([-4.0,4.0]):
            key=f"Prop_YardFence_{i}_{j}"
            layout._place(build,key,P.fence(7,.8,seed+1100+i*9+j),x,float(t.height_at(x,z+dz))-.08,z+dz)
    # Gather unrelated loose rock scatter into the same outcrop families.
    # Legacy rocks inside the civic court and domestic approaches are removed.
    def keep(p):
        x,_,z=p.position
        if 0<x<49 and -191<z<-153:
            if p.kind in ("rock","undergrowth","leafdrift","fallenlog","stump","mushrooms"):
                return False
        return True
    build.placements[:]=[p for p in build.placements if keep(p)]
    for i,(x,z,angle) in enumerate([(164,-214,.4),(187,-256,.5),(-43,-70,1.2)]):
        for j,(dx,dz,scale) in enumerate([(0,0,1.6),(3,1,.85),(5,-1,.42),(-2,2,.6)]):
            key=f"Prop_Outcrop_{i}_{j}"
            item=P.boulder(radius=scale,seed=seed+1300+i*7+j)
            layout._place(build,key,item,x+dx,float(t.height_at(x+dx,z+dz))-.22,z+dz,angle,kind="rock")
    # Ground drift meshes share the calmer forest palette as well.
    for item in build.meshes.values():
        parts=getattr(item,"all_parts",None)
        for mesh in (parts if parts is not None else [item]):
            if mesh.material=="forest_floor":mesh.material="woodland_loam"
    build.notes.append("Landscape pilot: connected upland shoulder; quiet loam, irregular hay meadows, habitat groves, small household yards and one legible market court.")

def finish_doors(build):
    # Re-surveyed small clearings beside their landmarks after the compact
    # village left less space round full-size trunks and cellar props.
    posts={'amber-boar-run':(176,-362),'amber-undercut':(282.14,-266.62)}
    t=build.terrain
    for entry in build.interactives:
        identity=entry.get('secret')
        if identity not in posts:continue
        x,z=posts[identity];y=float(t.height_at(x,z))
        entry['position']=[x,y,z];entry['serverTile']=[round(x+174),round(174-z)]
        node='Secret_'+identity.replace('-','_')
        for p in build.placements:
            if p.node==node:
                p.position=(x,y-.05,z)
                if identity=='amber-undercut':
                    # The interaction belongs in front of the closed root door,
                    # not inside the circular trunk blocker around its frame.
                    ax=x+np.sin(p.rotation_y)*3.5;az=z+np.cos(p.rotation_y)*3.5
                    entry['position']=[float(ax),y,float(az)]
                    entry['serverTile']=[round(ax+174),round(174-az)]
        t.rect_terrace((x,z),3.5,3.5,y,surface=TER.PATH,shoulder=4)
        build.placements[:]=[p for p in build.placements if p.node==node or
            p.kind not in ('tree','foliage','rock','fallenlog') or
            np.hypot(p.position[0]-x,p.position[2]-z)>8]


def finish_water(build):
    """Keep water below the final graded ground, including the lowered pass.

    Earlier water surveys predated road/landmark grading. Dense downhill
    samples avoid a suspended ribbon across a newly lowered bank or saddle.
    """
    from amberwood.woodlandcraft import water_ribbon
    ribbons=[]
    for name,stations in build.terrain.amberwood_water:
        distances=np.r_[0,np.cumsum(np.linalg.norm(np.diff(stations[:,[0,2]],axis=0),axis=1))]
        samples=np.linspace(0,distances[-1],int(np.ceil(distances[-1]/1.5))+1)
        points=np.column_stack([np.interp(samples,distances,stations[:,i]) for i in range(3)])
        final_ground=build.terrain.height_at(points[:,0],points[:,2])
        points[:,1]=np.minimum.accumulate(np.minimum(points[:,1],final_ground+.14))
        ribbons.append(water_ribbon(points,2.6 if name=='garden_rill' else 3.6))
    build.water_meshes['Water_Streams']=M.merge(ribbons,'water_stream')


def finish_compact_doors(build):
    """Keep small secret props and their standing posts on the inhabited ground.

    These are final compact coordinates: the cairn previously intersected the
    sea-arch outcrop and the waystone sat inside the full-size mill lodge. Their
    existing clearings need no terrain grading or changes to either landmark.
    The smuggler's mouth keeps its cave, with use/return on the connected quay.
    """
    posts = {
        'amber-stone-ring-well': ((-35.5, -11.5), (78, 127)),
        'amber-waystone': ((-25.5, -55.5), (91, 173)),
        'amber-smuggle-mouth': (None, (41, 86)),
    }
    t = build.terrain
    for entry in build.interactives:
        identity = entry.get('secret')
        if identity not in posts:
            continue
        prop, tile = posts[identity]
        if prop is not None:
            x, z = prop
            node = 'Secret_' + identity.replace('-', '_')
            placement = next(p for p in build.placements if p.node == node)
            placement.position = (x, float(t.height_at(x, z)) + .05, z)
        x, z = tile[0] + .5 - 116, 116 - tile[1] - .5
        entry['position'] = [x, float(t.height_at(x, z)), z]
        entry['serverTile'] = list(tile)
        entry['approachNote'] = 'Surveyed standing post connected to the main village arrival.'
