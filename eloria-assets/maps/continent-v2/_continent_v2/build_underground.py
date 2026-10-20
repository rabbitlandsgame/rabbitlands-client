#!/usr/bin/env python3
"""Build Landfall's disjoint underground sections with the existing interior kit.

One authored plan drives the rock shell, tile collision, markers and minimap.
The four sections are separated by unfloored, blocked blackspace. Resources
and creatures are server-owned and use the reviewed runtime models.

Retired with the procedural generators on 2026-10-16; the owner re-enabled it
on 2026-10-20 for the Cenote Deeps, and it runs only with --owner-approved.
The owner asked for section spindle_cavern to become a jungle cenote: style
"cenote" draws only the rock shell, the pools and a light shaft. Its rocks, ruins, plants and lamps are
reviewed Meshy kit pieces placed by tools/prepare_underground_scenery.py from
dressing(), which also decides what they block here. The mine, workings and
barrow sections build exactly as before.
"""
from __future__ import annotations
import argparse
from array import array
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw
from shapely import affinity, constrained_delaunay_triangles
from shapely.geometry import Point, LineString, Polygon, box
from shapely.ops import unary_union, triangulate

HERE = Path(__file__).resolve().parent
CHECKOUT = HERE.parents[3]
TOOLKIT = CHECKOUT/'eloria-assets/maps/nymara-regions/_toolkit'
sys.path.insert(0,str(TOOLKIT))
from amberwood import gltf as G, mesh as M, materials as MAT, textures as T

SOURCE = HERE/'content/underground.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data,indent=2)+"\n",encoding='utf-8',newline='\n')


def outline(section):
    rooms=[]
    cenote=section['style']=='cenote'
    for index,(x,y,rx,ry) in enumerate(section['rooms']):
        if section['style']=='barrow':
            rooms.append(box(x-rx,y-ry,x+rx,y+ry).buffer(-1).buffer(1))
        elif cenote:
            # Water-worn limestone: lower, broader lobes than the mine's chisel marks.
            points=[]
            for i in range(96):
                angle=i*math.tau/96
                waviness=(1+.07*math.sin(angle*4+index*1.7)+.045*math.cos(angle*7+index*.6)
                          +.02*math.sin(angle*13+index*2.3))
                points.append((x+rx*waviness*math.cos(angle),y+ry*waviness*math.sin(angle)))
            rooms.append(Polygon(points))
        else:
            points=[]
            for i in range(64):
                angle=i*math.tau/64
                waviness=1+.045*math.sin(angle*5+index*.8)+.025*math.cos(angle*9+index)
                points.append((x+rx*waviness*math.cos(angle),y+ry*waviness*math.sin(angle)))
            rooms.append(Polygon(points))
    # A link may wind through waypoints: [a, b, width, [[x, y], ...]].
    passages = [LineString([section['rooms'][link[0]][:2],*(link[3] if len(link)>3 else []),
                            section['rooms'][link[1]][:2]]).buffer(link[2]/2)
                for link in section['links']]
    shape=unary_union(rooms+passages)
    if cenote:
        shape=shape.buffer(1.2).buffer(-1.2)  # round the joints where tunnels meet chambers
    return shape


def wavy_ellipse(x,y,rx,ry,phase=0.):
    return Polygon([(x+rx*(1+.06*math.sin(a*3+phase)+.03*math.cos(a*7+phase))*math.cos(a),
                     y+ry*(1+.06*math.sin(a*3+phase)+.03*math.cos(a*7+phase))*math.sin(a))
                    for a in (i*math.tau/72 for i in range(72))])


def pools(section):
    """The section's standing water: wavy ellipses [x, y, rx, ry], reaching under the walls they touch."""
    shapes=[wavy_ellipse(*pool[:4],phase=index*1.3) for index,pool in enumerate(section.get('pools',[]))]
    if not shapes: return None
    return unary_union(shapes).intersection(outline(section).buffer(2.0))


# Reused Meshy kit pieces (tools/prepare_underground_scenery.py packages them at these sizes):
# the wall rocks with the half depth that stands proud of the rock face.
WALL_ROCKS=(('mossy_crag_1',2.0),('mossy_boulder_2',1.3),('mossy_crag_2',2.2),('mossy_boulder_1',1.0),
            ('mossy_boulder_3',1.2),('mossy_boulder_2',1.3))
# Lamps among the kit pieces: colour, energy, range, height of the flame.
KIT_LIGHTS={'jade_lantern_pole':([1,.74,.42],1.6,13,2.3),'jade_lantern_shrine':([.55,1,.72],1.3,10,1.6),
            'incense_brazier':([1,.58,.28],2.0,11,1.4)}


def dressing(section):
    """The cenote's reused scenery, as placements in tile units: the source's props, then rocks along every wall.

    Each is {asset, x, y, height, yaw, scale, block, wall}: `block` is the radius (tiles) it takes from the walk
    grid; `wall` marks a rock set into the rock face, whose `outward` (world X/Y/Z) the client's cutaway judges it by:
    near the player on a wall facing the camera it drops out (the manifest's cutaway `props`).
    """
    if section['style']!='cenote': return []
    items=[]
    for prop in section.get('props',[]):
        x,y=prop['at']
        items.append({'asset':prop['asset'],'x':x,'y':y,'height':prop.get('height',0),'yaw':prop.get('yaw',0),
                      'scale':prop.get('scale',1),'block':prop.get('block',0),'wall':False,
                      **({'palette':prop['palette']} if 'palette' in prop else {}),
                      **({'light':True} if prop.get('light') else {})})
    keep_out=[(p['at'][0],p['at'][1],p['clearWall']) for p in section.get('props',[]) if p.get('clearWall')]
    ring=outline(section).exterior
    ccw=ring.is_ccw
    step=section.get('wallRockSpacing',4.0)
    for k in range(int(ring.length//step)):
        d=k*step+(k*7919%10)*.08
        p=ring.interpolate(d); q=ring.interpolate(d+.5)
        dx,dy=q.x-p.x,q.y-p.y; length=max(.01,math.hypot(dx,dy))
        nx,ny=(dy/length,-dx/length) if ccw else (-dy/length,dx/length)
        asset,proud=WALL_ROCKS[(k*5+k//3)%len(WALL_ROCKS)]
        scale=.85+(k*37%30)/100
        # Set the rock into the face so about a third of it stands proud of the wall.
        x,y=p.x+nx*proud*scale*.45,p.y+ny*proud*scale*.45
        if any(math.hypot(x-cx,y-cy)<r for cx,cy,r in keep_out): continue
        items.append({'asset':asset,'x':round(x,2),'y':round(y,2),'height':-.3,'yaw':k*137%360,
                      'scale':round(scale,2),'block':0,'wall':True,'outward':[round(nx,3),0,round(-ny,3)]})
    return items


def section_bounds(section):
    """A section's id, name and world-space X/Z bounds (metres, 2 m clear of its walls) for the client."""
    x0,y0,x1,y1=outline(section).buffer(2).bounds
    return {'id':section['id'],'name':section['name'],
            'bounds':{'min':[round(x0,2),round(240-y1,2)],'max':[round(x1,2),round(240-y0,2)]}}


def flat_triangles(polygon,height):
    """Upward-facing triangles covering `polygon` (holes respected) at `height`, as world-space vertex triples."""
    result=[]
    for tri in constrained_delaunay_triangles(polygon).geoms:
        p=list(tri.exterior.coords)[:3]
        a,b,c=[world(x,y,height) for x,y in p]
        if np.cross(np.subtract(b,a),np.subtract(c,a))[1]<0:
            a,b,c=c,b,a
        result.append((a,b,c))
    return result


FACE_OUT=dict(east=[1,0,0],west=[-1,0,0],south=[0,0,-1],north=[0,0,1])
CENOTE_WATER=-.45  # the pools' surface, below the walk floor at 0
CENOTE_BED=-1.9


def facing_quad(corners,toward,material):
    """A quad wound so its normal points along the world-space vector `toward`."""
    normal=np.cross(np.subtract(corners[1],corners[0]),np.subtract(corners[2],corners[0]))
    return M.quad(corners if np.dot(normal,toward)>=0 else corners[::-1],material=material)


def cenote_geometry(section,add,lights,chambers,wall_faces):
    """The cenote's shell: limestone floor and walls, sunk pools with banks, and the shaft of daylight."""
    ident=section['id']; poly=outline(section); water=pools(section)
    floor=poly.difference(water) if water is not None else poly
    for a,b,c in flat_triangles(floor,0):
        add(M.quad([a,b,c,c],material='verdant_wet_limestone').drop_degenerate(),f'Walk_{ident}')
    for a,b,c in flat_triangles(poly,8.5):
        add(M.quad([c,b,a,a],material='verdant_limestone_cliff').drop_degenerate(),f'Roof_{ident}')
    # A low, ragged rock face: the limestone crags set into it (dressing()) are the walls' skyline.
    boundary=list(poly.exterior.coords); count=len(boundary)-1
    ccw=poly.exterior.is_ccw; perimeter=0.
    def top(i): return 4.2+.5*math.sin(i%count*.11)+.25*math.sin(i%count*.37)
    for i,(a,b) in enumerate(zip(boundary,boundary[1:])):
        dx,dy=b[0]-a[0],b[1]-a[1]; length=max(.01,math.hypot(dx,dy))
        nx,ny=(dy/length,-dx/length) if ccw else (-dy/length,dx/length)
        ring=[world(*a,-.15),world(*b,-.15),world(*b,top(i+1)),world(*a,top(i))]
        facing=('east' if nx>0 else 'west') if abs(nx)>abs(ny) else ('south' if ny>0 else 'north')
        bucket=f'Build_{ident}_{facing}'
        wall_faces[bucket]=FACE_OUT[facing]
        face=M.quad(ring,material='verdant_limestone_cliff')
        face.uvs=np.array([[perimeter*.3,0],[(perimeter+length)*.3,0],
                           [(perimeter+length)*.3,top(i+1)*.3],[perimeter*.3,top(i)*.3]])
        add(face,bucket)
        perimeter+=length
    if water is not None:
        for part in getattr(water,'geoms',[water]):
            for a,b,c in flat_triangles(part,CENOTE_WATER):
                add(M.quad([a,b,c,c],material='water_cenote').drop_degenerate(),f'Water_{ident}')
            for a,b,c in flat_triangles(part,CENOTE_BED):
                add(M.quad([a,b,c,c],material='verdant_mossy_stone').drop_degenerate(),f'Pool_{ident}')
            # The bank drops from the floor's edge to the bed, facing the water.
            edge=list(part.exterior.coords); inner_ccw=part.exterior.is_ccw; run=0.
            for a,b in zip(edge,edge[1:]):
                dx,dy=b[0]-a[0],b[1]-a[1]; length=max(.01,math.hypot(dx,dy))
                ix,iy=(-dy/length,dx/length) if inner_ccw else (dy/length,-dx/length)
                bank=facing_quad([world(*a,.02),world(*b,.02),world(*b,CENOTE_BED),world(*a,CENOTE_BED)],
                                 (ix,0,-iy),'verdant_wet_limestone')
                bank.uvs=np.array([[run*.3,0],[(run+length)*.3,0],[(run+length)*.3,.6],[run*.3,.6]])
                add(bank,f'Bank_{ident}')
                run+=length
    if 'shaft' in section:
        # Daylight through the sinkhole's mouth: an open, faintly lit column over the pool.
        sx,sy,radius=section['shaft']
        def rim(angle,r,h): return world(sx+r*math.cos(angle),sy+r*math.sin(angle),h)
        for i in range(28):
            a0,a1=i*math.tau/28,(i+1)*math.tau/28
            add(M.quad([rim(a0,radius,.1),rim(a1,radius,.1),rim(a1,radius*.72,15),rim(a0,radius*.72,15)],
                       material='light_shaft'),f'Shaft_{ident}')
        lights.append({'id':f'{ident}-daylight','position':list(world(sx,sy,9)),'color':[.92,.96,.84],
                       'energyHint':4.0,'rangeHint':26})
    for index,(x,y,rx,ry) in enumerate(section['rooms']):
        chambers.append({'id':f'{ident}-{index}','section':ident,'position':list(world(x,y)),
                         'radius':min(rx,ry),'name':section['name']})
    lamp=0
    for item in dressing(section):
        light=KIT_LIGHTS.get(item['asset'])
        if light is None and item.get('light'):
            light=([.42,1,.72],1.0,8,1.0)  # a glowing jade growth
        if light is None: continue
        colour,energy,reach,height=light
        lights.append({'id':f'{ident}-lamp-{lamp}','position':list(world(item['x'],item['y'],height*item['scale'])),
                       'color':colour,'energyHint':energy,'rangeHint':reach})
        lamp+=1
    # The way out: a dark passage mouth; the serpent arch over it is kit scenery.
    x,y=section['exit']
    add(M.quad([world(x-1.7,y-1.2,.01),world(x+1.7,y-1.2,.01),world(x+1.7,y-1.2,3.3),world(x-1.7,y-1.2,3.3)],
               material='exit_dark'),f'Props_{ident}')


def world(x,y,height=0):
    return (x,height,240-y)


def build_geometry(design, textures):
    builder=G.GltfBuilder(generator='Eloria Landfall underground builder; shared original interior kit')
    root=G.Node('Landfall_Underground')
    parts=defaultdict(list)
    lights=[]; chambers=[]; hidden=[]; wall_faces={}
    def add(piece,bucket): parts[(bucket,piece.material)].append(piece)
    for section in design['sections']:
        if section['style']=='cenote':
            cenote_geometry(section,add,lights,chambers,wall_faces)
            continue
        ident=section['id']; poly=outline(section)
        floor={'barrow':'ashlar','crystal':'cliff_rock'}.get(section['style'],'packed_earth')
        rock='rubble_stone' if section['style']=='barrow' else 'cliff_rock'
        for tri in triangulate(poly):
            if not poly.covers(tri): continue
            p=list(tri.exterior.coords)[:3]
            # Server Y runs opposite Godot Z: CCW source is upward-facing.
            a,b,c=[world(x,y) for x,y in p]
            if np.cross(np.subtract(b,a),np.subtract(c,a))[1]<0:
                p.reverse();a,b,c=[world(x,y) for x,y in p]
            add(M.quad([a,b,c,c],uv_scale=.35,material=floor).drop_degenerate(),f'Walk_{ident}')
            add(M.quad([world(*p[2],7),world(*p[1],7),world(*p[0],7),world(*p[0],7)],
                       uv_scale=.2,material=rock).drop_degenerate(),f'Roof_{ident}')
        # Faceted walls share their rim vertices so no cracks expose blackspace.
        boundary=list(poly.exterior.coords)
        ccw=poly.exterior.is_ccw
        perimeter=0.
        for i,(a,b) in enumerate(zip(boundary,boundary[1:])):
            dx,dy=b[0]-a[0],b[1]-a[1]; length=max(.01,math.hypot(dx,dy))
            nx,ny=(dy/length,-dx/length) if ccw else (-dy/length,dx/length)
            top_a=6.5+.3*math.sin(i*.18)
            top_b=6.5+.3*math.sin(((i+1)%(len(boundary)-1))*.18)
            ring=[world(*a,-.15),world(*b,-.15),world(*b,top_b),world(*a,top_a)]
            facing=('east' if nx>0 else 'west') if abs(nx)>abs(ny) else ('south' if ny>0 else 'north')
            bucket=f'Build_{ident}_{facing}'
            wall_faces[bucket]=dict(east=[1,0,0],west=[-1,0,0],south=[0,0,-1],north=[0,0,1])[facing]
            face=M.quad(ring,material=rock)
            face.uvs=np.array([[perimeter*.3,0],[(perimeter+length)*.3,0],
                               [(perimeter+length)*.3,top_b*.3],[perimeter*.3,top_a*.3]])
            add(face,bucket)
            perimeter+=length
        for index,(x,y,rx,ry) in enumerate(section['rooms']):
            chambers.append({'id':f'{ident}-{index}','section':ident,'position':list(world(x,y)),
                             'radius':min(rx,ry),'name':section['name']})
            lights.append({'id':f'{ident}-lamp-{index}','position':list(world(x-rx+1.2,y,2.6)),
                           'color':[.65,.76,1] if section['style']=='crystal' else [1,.65,.32],
                           'energyHint':1.8,'rangeHint':18})
            # Lamps on the rock wall; the middle of every passage stays clear.
            lx,ly=x-rx+1.2,y
            add(M.box((.35,.6,.35),world(lx,ly,2.5),material='dark_iron'),f'Props_{ident}')
            add(M.icosphere(.18,1,material='lamp_glow').translate(*world(lx,ly,2.6)),f'Props_{ident}')
        if section['style']=='mine':
            for a,b,width in section['links']:
                p,q=np.array(section['rooms'][a][:2]),np.array(section['rooms'][b][:2])
                angle=math.atan2(q[1]-p[1],q[0]-p[0]); across=np.array([-math.sin(angle),math.cos(angle)])
                for amount in (.35,.7):
                    mid=p+(q-p)*amount
                    for sign in (-1,1):
                        x,y=mid+across*(width*.5-.3)*sign
                        add(M.box((.35,3.8,.35),world(x,y,1.9),material='timber_dark'),f'Props_{ident}')
                    beam=M.box((width,.4,.4),material='timber_warm').rotate_y(angle-math.pi/2).translate(*world(*mid,3.8))
                    add(beam,f'Props_{ident}')
            # Ore sleds and abandoned tools at the chamber edges.
            x,y=section['rooms'][1][:2]
            add(M.box((2.2,.16,1.2),world(x-9,y-3,.4),material='timber_warm'),f'Props_{ident}')
            for offset in (-.4,.4):
                add(M.cylinder(.32,.32,.15,10,material='dark_iron').rotate_z(math.pi/2).translate(*world(x-9,y-3+offset,.35)),f'Props_{ident}')
        elif section['style']=='crystal':
            for x,y,rx,ry in section['rooms'][1:]:
                for i in range(5):
                    px=x+rx*.82*math.cos(i*1.3); py=y+ry*.82*math.sin(i*1.3)
                    add(M.cylinder(.45,0,2+i*.25,6,material='cave_crystal').translate(*world(px,py,1+i*.125)),f'Props_{ident}')
        else:
            for x,y,rx,ry in section['rooms'][1:]:
                for sign in (-1,1):
                    sx=x+sign*(rx-2.2)
                    sy=y+ry-3.2
                    add(M.box((1.6,.9,3),world(sx,sy,.45),material='ashlar'),f'Props_{ident}')
                    add(M.box((1.85,.22,3.25),world(sx,sy,1),material='rubble_stone'),f'Props_{ident}')
        # A bright exit arch at the south lip of each entry chamber. The server
        # click target uses this already-authored doorway, not a second model.
        x,y=section['exit']
        for sign in (-1,1):
            add(M.box((.6,3.5,.6),world(x+sign*2,y,1.75),material='timber_warm' if section['style']=='mine' else 'ashlar'),f'Props_{ident}')
        add(M.box((4.6,.55,.8),world(x,y,3.55),material='timber_warm' if section['style']=='mine' else 'ashlar'),f'Props_{ident}')
        add(M.quad([world(x-1.7,y-1.2,.01),world(x+1.7,y-1.2,.01),world(x+1.7,y-1.2,3.3),world(x-1.7,y-1.2,3.3)],material='exit_dark'),f'Props_{ident}')
    used={m for _,m in parts}
    MAT.register_gltf_materials(builder,textures,only=used-{'lamp_glow','cave_crystal','exit_dark','light_shaft'})
    builder.add_material(G.Material('lamp_glow',base_color=(1,.5,.1,1),emissive=(1,.4,.05)))
    builder.add_material(G.Material('cave_crystal',base_color=(.3,.54,.62,1),roughness=.32,emissive=(.03,.10,.13)))
    builder.add_material(G.Material('exit_dark',base_color=(.008,.009,.011,1),double_sided=True))
    if 'light_shaft' in used:
        builder.add_material(G.Material('light_shaft',base_color=(.95,.97,.82,.10),emissive=(.45,.48,.38),
                                        alpha_mode='BLEND',double_sided=True))
    all_meshes=[]; collision_nodes=[];walls=[]
    for (bucket,material),pieces in sorted(parts.items()):
        piece=M.merge(pieces,material=material).drop_degenerate().sanitise_normals()
        if bucket.startswith(('Walk_','Roof_','Water_','Pool_')):
            piece.uvs=piece.positions[:,[0,2]]*.22
        name=f'{bucket}_{material}'
        builder.add_mesh(name,piece,with_tangents=True); root.add(G.Node(name,mesh=name))
        all_meshes.append(piece)
        if bucket.startswith('Roof'): hidden.append(name)
        if bucket.startswith('Build'):
            # Each wall names its cave, so the client keeps another cave's walls hidden (`sectioned`).
            section=next(s['id'] for s in design['sections'] if bucket.startswith(f"Build_{s['id']}_"))
            collision_nodes.append(name);walls.append({'node':name,'outward':wall_faces[bucket],'section':section})
    builder.add_node(root)
    bounds=M.merge(all_meshes).bounds()
    return builder,lights,chambers,hidden,collision_nodes,bounds,walls


def masks(design):
    from shapely import contains_xy
    cells=design['map']['cells']; size=cells*2
    x,y=np.meshgrid((np.arange(size)+.5)*.5,(np.arange(size)+.5)*.5)
    half=np.zeros((size,size),dtype=bool)
    for section in design['sections']:
        # Cell corners must fit on the authored floor; retain a conservative
        # actor-width margin at rock walls. Blackspace has no geometry at all.
        half |= contains_xy(outline(section).buffer(-.4),x,y)
        if section['style']=='mine':
            for a,b,width in section['links']:
                p,q=np.array(section['rooms'][a][:2]),np.array(section['rooms'][b][:2]); delta=q-p
                across=np.array([-delta[1],delta[0]])/np.linalg.norm(delta)
                for amount in (.35,.7):
                    for sign in (-1,1):
                        px,py=p+delta*amount+across*(width*.5-.3)*sign
                        half &= ~((abs(x-px)<.4)&(abs(y-py)<.4))
            px,py=section['rooms'][1][:2]
            half &= ~((abs(x-(px-9))<1.3)&(abs(y-(py-3))<.85))
        elif section['style']=='crystal':
            for px,py,rx,ry in section['rooms'][1:]:
                for i in range(5):
                    sx=px+rx*.82*math.cos(i*1.3);sy=py+ry*.82*math.sin(i*1.3)
                    half &= ~((x-sx)**2+(y-sy)**2<.7**2)
        elif section['style']=='barrow':
            for px,py,rx,ry in section['rooms'][1:]:
                for sign in (-1,1):
                    half &= ~((abs(x-(px+sign*(rx-2.2)))<1.1)&(abs(y-(py+ry-3.2))<1.9))
        elif section['style']=='cenote':
            # The wall rocks stand proud of the face: keep a wider margin than the mine's.
            half &= ~(contains_xy(outline(section),x,y) & ~contains_xy(outline(section).buffer(-1.0),x,y))
            water=pools(section)
            if water is not None:
                half &= ~contains_xy(water.buffer(.4),x,y)
            for item in dressing(section):
                if item['block']>0:
                    half &= ~((x-item['x'])**2+(y-item['y'])**2<item['block']**2)
        for _,_,nx,ny in section['nodes']:
            half[ny*2:ny*2+2,nx*2:nx*2+2]=False
    coarse=half.reshape(cells,2,cells,2).all(axis=(1,3))
    # A cenote's props and pools can pinch off a scrap of floor, and publication refuses a stranded pocket:
    # close whatever the arrival cannot reach (the server's four-way steps on the coarse grid).
    from scipy import ndimage
    for section in design['sections']:
        if section['style']!='cenote': continue
        x0,y0,x1,y1=(int(v) for v in outline(section).buffer(1).bounds)
        window=coarse[y0:y1+1,x0:x1+1]
        labels,_=ndimage.label(window)
        ax,ay=section['arrival']
        stranded=window&(labels!=labels[ay-y0,ax-x0])
        if stranded.sum()>12:
            ys,xs=np.nonzero(stranded)
            raise SystemExit(f'{section["id"]}: {int(stranded.sum())} floor tiles are cut off from the arrival, '
                             f'e.g. ({xs[0]+x0},{ys[0]+y0}): a prop or pool closes a passage')
        half[y0*2:(y1+1)*2,x0*2:(x1+1)*2]&=~np.repeat(np.repeat(stranded,2,0),2,1)
    coarse=half.reshape(cells,2,cells,2).all(axis=(1,3))
    return half,coarse


def entrance_asset(style, textures, path):
    builder=G.GltfBuilder(generator='Eloria Landfall cave entrance; original shared kit materials')
    parts=defaultdict(list)
    def add(p): parts[p.material].append(p)
    rock='rubble_stone' if style=='barrow' else 'cliff_rock'
    # An open arch embedded in its own rocky mound: front is +Z, the adit
    # recedes north. No surface or body closes the player-sized central mouth.
    for sign in (-1,1):
        for i in range(3):
            add(M.icosphere(1,1,material=rock).scale(1.6+i*.12,1.8-i*.15,2.7)
                .rotate_y(sign*(.4+i*.8)).rotate_z(sign*(.13-i*.19))
                .translate(sign*(3.2+i*.9),1.1,-1.8-i*.5))
    # Separate faces give the tunnel's soffit proper depth UVs. The toolkit's
    # flat arch UVs collapse on the extrusion and turn rock into vertical stripes.
    ring=[]
    for i in range(17):
        angle=i*math.pi/16
        ring.append(((2.9*math.cos(angle),3.5*math.sin(angle)),
                     (3.8*math.cos(angle),4.6*math.sin(angle))))
    def vertex(p,z):return (p[0],p[1],z)
    for (ia,oa),(ib,ob) in zip(ring,ring[1:]):
        add(M.quad([vertex(ia,.1),vertex(oa,.1),vertex(ob,.1),vertex(ib,.1)],uv_scale=.3,material=rock))
        add(M.quad([vertex(ib,-3.7),vertex(ob,-3.7),vertex(oa,-3.7),vertex(ia,-3.7)],uv_scale=.3,material=rock))
        add(M.quad([vertex(oa,.1),vertex(oa,-3.7),vertex(ob,-3.7),vertex(ob,.1)],uv_scale=.3,material=rock))
        add(M.quad([vertex(ia,.1),vertex(ib,.1),vertex(ib,-3.7),vertex(ia,-3.7)],uv_scale=.3,material=rock))
    add(M.box((5.6,4.6,.12),(0,2.2,-2.2),material='exit_dark'))
    if style=='mine':
        for sign in (-1,1): add(M.box((.45,3.5,.5),(sign*1.95,1.7,0),material='timber_warm'))
        add(M.box((4.4,.5,.6),(0,3.5,0),material='timber_warm'))
    elif style=='barrow':
        for sign in (-1,1): add(M.box((.7,3.5,.8),(sign*2,1.7,0),material='ashlar'))
        add(M.box((4.7,.6,.9),(0,3.6,0),material='ashlar'))
    else:
        for sign in (-1,1): add(M.cylinder(.35,0,2.2,6,material='cave_crystal').translate(sign*3,.9,1))
    add(M.cylinder(.18,.14,1.8,8,material='dark_iron').translate(-3.1,.9,2))
    add(M.icosphere(.22,1,material='lamp_glow').translate(-3.1,2,2))
    MAT.register_gltf_materials(builder,textures,only=set(parts)-{'exit_dark','lamp_glow','cave_crystal'})
    for spec in [G.Material('exit_dark',base_color=(.006,.007,.008,1),double_sided=True),
                 G.Material('lamp_glow',base_color=(1,.5,.1,1),emissive=(1,.4,.05)),
                 G.Material('cave_crystal',base_color=(.3,.54,.62,1),emissive=(.03,.1,.13))]: builder.add_material(spec)
    root=G.Node(f'{style}_entrance')
    for material, pieces in parts.items():
        name=f'Entrance_{material}'; builder.add_mesh(name,M.merge(pieces).sanitise_normals(),with_tangents=True);root.add(G.Node(name,mesh=name))
    builder.add_node(root);path.parent.mkdir(parents=True,exist_ok=True);builder.write_glb(str(path))


def build(server):
    sys.path.insert(0,str(server)); from eloria import served_grid as SG
    design=json.loads(SOURCE.read_text()); ident=design['map']['id']; cells=design['map']['cells']
    out=HERE.parent/ident/'client';out.mkdir(parents=True,exist_ok=True)
    textures={'ashlar':T.ashlar(512,seed=53),'packed_earth':T.packed_earth(512,seed=223),
              'rubble_stone':T.rubble_stone(512,seed=61),'cliff_rock':T.cliff_rock(512,seed=67),
              'timber_warm':T.timber(512,seed=23,tone='warm'),'timber_dark':T.timber(512,seed=173,tone='dark'),
              'dark_iron':T.dark_iron(256,seed=101)}
    if any(s['style']=='cenote' for s in design['sections']):
        # The Verdant Stair's own limestone and cenote water (materials.py seeds).
        textures.update({'verdant_mossy_stone':T.verdant_mossy_stone(512,seed=617),
                         'verdant_wet_limestone':T.verdant_wet_limestone(512,seed=619),
                         'verdant_limestone_cliff':T.verdant_limestone_cliff(512,seed=631),
                         'water_cenote':T.water_surface(512,seed=683,tone='cenote')})
    builder,lights,chambers,hidden,collision_nodes,bounds,walls=build_geometry(design,textures)
    builder.write_glb(str(out/'world.glb'))
    half,coarse=masks(design)
    ew=struct.pack('<4sHHII',b'EWCG',2,0,cells*2,cells*2)+half.astype(np.uint8).tobytes()
    (out/'collision.bin').write_bytes(ew)
    grid=SG.ServedGrid(cells,cells,array('H',np.where(coarse,2000,0).astype(np.uint16).ravel()))
    (out/'served-grid.escg.gz').write_bytes(SG.encode_file(grid))
    coordinate={'metresPerTile':1.,'serverOrigin':[0,cells],'serverCells':[cells,cells],
                'origin':[0,0,0],'walkingHeight':0.,'invertServerY':True,'serverStorageVersion':1,'serverTileMin':[0,0]}
    nodes=[];exits=[];spawns=[]
    for i,section in enumerate(design['sections']):
        spawns.append({'id':section['id'],'name':section['name'],'section':section['id'],'default':i==0,
                       'position':list(world(*section['arrival'],.05)),'serverTile':section['arrival'],'rotationDegrees':180})
        for oid,res,x,y in section['nodes']:
            nodes.append({'id':f'{section["id"]}-{oid}','objectId':oid,'resource':res,'serverTile':[x,y],
                          'position':list(world(x+.5,y+.5)),'section':section['id'],'authority':'server'})
        exits.append({'id':f'{section["id"]}-exit','objectId':section['entrance']['object'],
                      'role':'portal','position':list(world(*section['exit'])),'serverTile':section['exit'],
                      'destinationMap':section['entrance']['map'],'destinationTile':section['entrance']['returnTile'],
                      'label':f'Leave {section["name"]}'})
    manifest={'schemaVersion':'1.1.0','assetVersion':'1.0.0',
              'asset':{'id':ident,'name':design['map']['name'],'glb':'world.glb','units':'meters',
                       'coordinateSystem':{'handedness':'right','upAxis':'Y','northAxis':'-Z'},'origin':[0,0,0],
                       'bounds':{'min':bounds[0].tolist(),'max':bounds[1].tolist()},'interiorClass':'insides','parentRegion':'landfall','serverCells':cells},
              'coordinateTransform':coordinate,'serverCells':[cells,cells],'spawnPoints':spawns,
              'chambers':chambers,'harvestables':nodes,'portals':exits,'interactives':exits,
              'navigation':{'surfaceNodePrefixes':['Walk_'],'authority':'server','defaultSpawn':spawns[0]['id']},
              'collision':{'binary':'collision.bin','format':'EWCG-v2','width':cells*2,'height':cells*2,
                           'cellMetres':.5,'originMetres':[0,cells],'heightEncoding':{'origin':-.1,'step':.1},'gridAlignment':'tile-centres-v1',
                           'sha256':sha(out/'collision.bin'),'nodeNames':collision_nodes,
                           'servedGrid':{'binary':'served-grid.escg.gz','format':'ESCG-v2','sha256':sha(out/'served-grid.escg.gz'),
                                         'unitMetres':.05,'climbMetres':1.,'originMetres':-100.,'width':cells,'height':cells}},
              'environment':{'profile':'cave-interior','backgroundColor':'#000000',
                             'ambient':{'color':'#acb3bf','energy':.55,'skyContribution':0},
                             'sun':{'energy':.25,'color':'#ffe4c0','shadows':False},
                             'fog':{'enabled':False},'tonemap':{'mode':'filmic','exposure':1.1}},
              'lighting':{'markers':lights},
              # A wall cuts away only while the camera looks nearly straight through it (owner 2026-10-20: the
              # convention's 0.2 took too much of a cave away); wall rocks fade instead of hiding.
              'cutaway':{'hideNodes':hidden,'walls':walls,'facingThreshold':.6,
                         # Rocks set into a wall drop out within 12 m of the player while their wall faces the
                         # camera within 60 degrees (owner 2026-10-20: between hiding whole sides and fading only
                         # the one in front).
                         'props':{'facingThreshold':.5,'radiusMetres':12},
                         'reason':'The shared interior roof and camera-facing wall cutaway convention'},
              # One cave at a time: the client draws only the section the player stands in (SecretSections).
              'sectioned':True,'sections':[section_bounds(s) for s in design['sections']],
              'minimap':{'file':'minimap.webp','image':'minimap.webp','northUp':True,'worldMin':[0,0],'worldMax':[cells,cells],'imageSize':[720,720]},
              'provenance':{'source':'_continent_v2/content/underground.json','sourceSha256':sha(SOURCE),
                            'builder':'_continent_v2/build_underground.py','builderSha256':sha(__file__)}}
    write_json(out/'world.json',manifest)
    # Images go to the content-addressed pool, as every published map's do (eloria-assets/tools/shared_images.py).
    sys.path.insert(0,str(CHECKOUT/'eloria-assets/tools'))
    import shared_images
    moved=shared_images.externalise(out/'world.glb',dry_run=False)
    shared_images.record_manifest(out/'world.glb',moved['uris'],dry_run=False)
    image=Image.new('RGB',(720,720),'black');draw=ImageDraw.Draw(image)
    for section in design['sections']:
        poly=outline(section); points=[(x*3,y*3) for x,y in poly.exterior.coords]
        if section['style']=='cenote':
            draw.polygon(points,fill=(66,80,62),outline=(118,128,98),width=2)
            water=pools(section)
            for part in getattr(water,'geoms',[water]) if water is not None else []:
                draw.polygon([(x*3,y*3) for x,y in part.intersection(poly).exterior.coords],fill=(44,122,112))
        else:
            draw.polygon(points,fill=(73,70,63) if section['style']!='crystal' else (56,71,78),outline=(116,107,91),width=2)
        for _,res,x,y in section['nodes']: draw.ellipse((x*3-2,y*3-2,x*3+2,y*3+2),fill=(158,179,162))
        x,y=section['exit'];draw.rectangle((x*3-4,y*3-4,x*3+4,y*3+4),fill=(232,185,94))
    image.save(out/'minimap.webp',lossless=True)
    # The procedural entrance models stay retired: each door's art is reused Meshy scenery (objects.json),
    # which this builder no longer writes; retarget_underground.py keeps those records' tiles and labels.
    registry=json.loads((CHECKOUT/'godot-client/data/maps/registry.json').read_text(encoding='utf-8'))
    if registry['maps'].get(ident,{}).get('coordinateTransform')!=coordinate:
        raise SystemExit(f'registry.json has no {ident} row with this frame; publish it first')
    print(json.dumps({'map':ident,'sections':len(design['sections']),'nodes':len(nodes),'monsters':sum(len(s['spawns']) for s in design['sections']),
                      'walkableTiles':int(coarse.sum()),'glbBytes':(out/'world.glb').stat().st_size,'imagesShared':moved['moved']}))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--server',type=Path,required=True)
    ap.add_argument('--owner-approved',metavar='NOTE',
                    help="the owner's approval for this rebuild (the generator was retired on 2026-10-16)")
    args=ap.parse_args()
    if not args.owner_approved:
        raise RuntimeError('build_underground.py is retired: procedural models and generators were archived on 2026-10-16. '
                           'See docs/procedural-model-archive.md. It rebuilds only with --owner-approved "<who, when, what>" '
                           '(the owner re-enabled it on 2026-10-20 for the Cenote Deeps). No outputs were written.')
    build(args.server.resolve())
