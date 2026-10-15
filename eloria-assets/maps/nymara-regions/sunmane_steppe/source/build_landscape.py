"""Build the 384 m working steppe through the shared landscape toolkit."""
from pathlib import Path
from types import SimpleNamespace
import argparse,copy,json,math,os,struct,sys,time
import numpy as np
HERE=Path(__file__).resolve().parent
TOOLKIT=HERE.parents[1]/'_toolkit'
sys.path[:0]=[str(HERE),str(TOOLKIT)]
from amberwood import terrain as T,mesh as M,materials as MAT,stonework as S
from amberwood import watercraft as WATER,woodlandcraft as WOOD,civiccraft as CIV,routecraft as RC
from regionbuild import RegionBuild,Placement
import streaming_borders as SB
import glb_reader as GLB
import landscape_plan as P
import native_adapter as A
import settlement as N
import layout as LEGACY
import collision as NATIVE_COLLISION
PACKAGE=HERE.parent
LEGACY_MANIFEST=json.loads((HERE/'legacy-manifest.json').read_text(encoding='utf-8'))
MATERIALS={T.MEADOW:'steppe_sward',T.PATH:'steppe_dust',T.PAVING:'packed_earth',
           T.FOREST:'packed_earth',T.SHORE:'steppe_dust',T.ROCK:'cliff_rock',T.BARRENS:'amethyst_barrens_dust'}

def prepare_layout():
    layout=N.compose_layout(None)
    moves=P.relocate_layout(layout)
    for p in layout.placements:
        if p.landmark=='secret':p.x,p.z=P.remap_world(p.x,p.z,moves)
        if p.landmark=='transition':
            spec=next(s for s in SB.region_specs('sunmane_steppe') if s['portal']==p.interactive['id'])
            anchor=np.asarray(spec['anchor']);out=np.asarray(spec['outward'])
            point=anchor[[0,2]]-out*48
            p.x,p.z=map(float,point);p.rotation=math.atan2(out[0],out[1])
    return layout,moves

def add(build,name,group,position=(0,0,0),rotation=0,scale=1,collides=False,kind='prop',walk=False):
    build.add_mesh(name,group)
    build.place(Placement(name,name,tuple(position),rotation,scale,collides,walk,kind))

def worldpoint(t,x,z,lift=0):return [float(x),float(t.height_at(x,z))+lift,float(z)]

def normalize_environment(environment):
    """Publish numeric lighting fields used by both local and streamed views."""
    def normalize(value):
        if isinstance(value,str) and len(value)==7 and value.startswith('#'):
            return [int(value[i:i+2],16)/255. for i in (1,3,5)]
        if isinstance(value,list):return [normalize(v) for v in value]
        if not isinstance(value,dict):return value
        result={k:normalize(v) for k,v in value.items()}
        sun=result.get('sun',{})
        if 'rotationDegrees' in sun:
            x,y,z=map(math.radians,sun.pop('rotationDegrees'))
            rx=np.array([[1,0,0],[0,math.cos(x),-math.sin(x)],[0,math.sin(x),math.cos(x)]])
            ry=np.array([[math.cos(y),0,math.sin(y)],[0,1,0],[-math.sin(y),0,math.cos(y)]])
            rz=np.array([[math.cos(z),-math.sin(z),0],[math.sin(z),math.cos(z),0],[0,0,1]])
            sun['direction']=(ry@rx@rz@np.array([0.,0.,-1.])).tolist()
        variants=result.pop('variants',{})
        if 'golden-hour' in variants:result['goldenHour']=variants.pop('golden-hour')
        if variants:result['variants']=variants
        return result
    return normalize(environment)

def build_region(lod=False):
    layout,moves=prepare_layout()
    t=P.terrain(T,layout,cell=2. if lod else 1.)
    layout.landform=SimpleNamespace(height_at=t.height_at,sample=t.height_at)
    b=RegionBuild(t);b.empty_nodes=[];b.authored_roads=[];b.migration_field=moves;b.layout=layout
    builders=N._asset_builders()
    wanted={p.asset for p in layout.placements}
    for key in sorted(wanted):b.add_mesh('Kit_'+key,A.group(builders[key]()))
    oldentries={v['id']:v for v in LEGACY_MANIFEST['interactives']}
    for p in layout.placements:
        y=float(t.height_at(p.x,p.z))-p.sink
        b.place(Placement(p.name,'Kit_'+p.asset,(p.x,y,p.z),p.rotation,p.scale,p.collide,
                          kind='landmark' if p.landmark else 'prop'))
        position=worldpoint(t,p.x,p.z)
        if p.landmark:
            b.landmarks.append({'id':p.name,'node':p.name,'kind':p.landmark,'position':position,
                'serverTile':P.tile(p.x,p.z),'reachable':True,'rotationDegrees':math.degrees(p.rotation)})
        if p.interactive:
            entry=copy.deepcopy(oldentries.get(p.interactive['id'],p.interactive))
            entry.update(node=p.name,position=position.copy(),serverTile=P.tile(p.x,p.z))
            if entry['id'] in ('cave-wind_caves','cave-crystal_hollow'):
                wind=entry['id']=='cave-wind_caves'
                entry.update(destinationMap='sunmane_wind_caves',
                    destinationSpawn='wind-caves-mouth' if wind else 'crystal-hollow-adit',
                    destinationTile=[43,27] if wind else [169,28])
            # All use posts sit on a real approach, never at the opaque body's
            # centre. Native tents open along +X; the other door kits use +Z.
            reach={'great-hall':11.4,'round-tent':5.1,'caravanserai':7.,
              'seasonal-market':3.1,'well':2.7,'banner-shrine':3.2,'water-station':3.4,
              'burial-mound':6.5,'outpost':3.6,'secret':3.2,'cave-entrance':5.6,
              'production':4.4,'windmill':4.4,'filled-well':3.4}.get(p.landmark,0)
            if p.interactive['id'].startswith('windmill-'):reach=4.4
            if p.interactive['id']=='fourth-well':reach=3.4
            if reach:
                forward=np.array([math.sin(p.rotation),math.cos(p.rotation)])
                if p.landmark=='round-tent':forward=np.array([math.cos(p.rotation),-math.sin(p.rotation)])
                q=np.array([p.x,p.z])+forward*reach
                entry.update(position=worldpoint(t,*q),serverTile=P.tile(*q),propPosition=position.copy())
            if p.interactive['id']=='cove-landing':
                entry.update(position=worldpoint(t,p.x+5,p.z+1),serverTile=P.tile(p.x+5,p.z+1),propPosition=position.copy())
            if p.landmark=='animal-pen':
                variant=int(p.asset.rsplit('_',1)[1]);angle=math.tau*(3+4*variant+.5)/(11+variant)
                forward=np.array([math.cos(angle-p.rotation),math.sin(angle-p.rotation)])
                q=np.array([p.x,p.z])+forward*8.
                entry.update(position=worldpoint(t,*q),serverTile=P.tile(*q),propPosition=position.copy())
            b.interactives.append(entry)
            if entry.get('kind')=='portal':b.portals.append(copy.deepcopy(entry))
    timber,stone=N._palisade(layout)
    add(b,'Structure_Palisade',A.group({N.kit.TIMBER_DARK:timber,N.kit.STONE_PALE:stone}),collides=True,kind='wall')
    # Packed earth with three worn aisles replaces the huge pale tiled disc.
    core=np.hypot(t.gx,t.gz)<22
    t.surface[core]=T.PAVING
    for bridge_index,(name,a,bp,width) in enumerate(P.BRIDGES):
        a,bp=np.asarray(a,float),np.asarray(bp,float)
        group=CIV.sloped_boardwalk(float(np.linalg.norm((bp-a)[[0,2]])),a[1],bp[1],width,
                    foot=min(a[1],bp[1])-4,timber='timber_warm',rope='sun_leather')
        yaw=math.atan2(bp[0]-a[0],bp[2]-a[2]);node=f'Structure_Bridge_{bridge_index:02d}'
        add(b,node,group,(a[0],0,a[2]),yaw,kind='bridge')
        b.landmarks.append({'id':node,'node':node,'kind':'bridge','name':name,
                            'position':((a+bp)/2).tolist(),'serverTile':P.tile(*((a+bp)/2)[[0,2]])})
    b.water_meshes['Water_Sea']=T.water_plane(t,0,-460,-430,310,280,material='water_lake',cell=8,only_below=False)
    b.water_meshes['Water_SteppeBeck']=WOOD.water_ribbon(P.STREAM,1.9)
    b.water_meshes['Water_Waterholes']=WATER.pools(t.height_at,P.POOLS,material='water_pool')
    b.spawns=[{'id':'server-arrival','position':worldpoint(t,21,21,.1),'serverTile':list(P.ARRIVAL),
               'facing':[-1,0,0],'default':True},
              {'id':'arrival-datum','position':worldpoint(t,0,0,.1),'serverTile':[116,116],'facing':[0,0,-1]}]
    for s in b.spawns:
        s['node']='Spawn_'+s['id'].replace('-','_');b.empty_nodes.append({'node':s['node'],'position':s['position']})
    # A few overlapping, half-set rocks join each mouth to its rounded bank.
    # Their real volumes stay beside the entrance aisle.
    rock=A.group(builders['shore_rock_0']())
    for p in layout.placements:
        if p.landmark!='cave-entrance':continue
        for j,(side,back,scale) in enumerate(((-5.6,-3.4,2.0),(5.5,-4.0,2.3),(-6.8,-6.5,1.6))):
            c,s=math.cos(p.rotation),math.sin(p.rotation)
            x,z=p.x+c*side+s*back,p.z-s*side+c*back
            add(b,p.name+'_EarthRock_'+str(j),rock,(x,float(t.height_at(x,z))-.45,z),
                p.rotation+j*.4,scale,collides=True,kind='rock')
    for key,points in {**P.ROADS,**P.TRAILS}.items():
        b.authored_roads.append({'id':key,'waypoints':[list(q) for q in points],'widthMetres':5.5 if key in P.ROADS else 3.5})
    if not lod:details(b)
    t.despeckle_surfaces(5)
    b.terrain_meshes=t.build_feathered_meshes(T.MEADOW,uv_scale=.28,
                        materials=MATERIALS,feather_metres=1.5)
    for part in b.terrain_meshes.values():
        if part.material.startswith('steppe_sward'):part.uvs*=2.1
    # A continuous distant land surface keeps the unconnected frontier a
    # landscape horizon. It is neither collision nor a fabricated new road.
    b.terrain_meshes['Backdrop_Steppe']=T.backdrop(t,reach=160,cell=10,seed=P.SEED,
                                material='steppe_sward',sea_level=0,open_side='west',clip_interior=True)
    sys.path.insert(0, str(HERE.parents[1] / '_outer'))
    import outer_aprons
    outer_snapshot = outer_aprons.capture(b, 'sunmane_steppe')
    SB.apply(b,'sunmane_steppe')
    outer_aprons.apply(b, 'sunmane_steppe', outer_snapshot)
    sys.path.insert(0, str(HERE.parents[1] / '_finishing'))
    import connector_finish
    import march_approach
    march_approach.apply(b)
    connector_finish.apply(b, 'sunmane_steppe')
    import south_landform
    south_landform.apply(b)
    import north_paint
    north_paint.apply(b)
    # Both converters consume these legacy aliases; they must share the exact
    # surveyed trigger rather than leaving a second portal at the signpost.
    portals={p['id']:p for p in b.portals}
    for entry in b.interactives:
        if entry['id'] in portals:
            entry.update(copy.deepcopy(portals[entry['id']]))
    return b

def details(b):
    t=b.terrain;rng=np.random.default_rng(P.SEED)
    # Lee shrubs grow by damp swales and bank toes; no evenly spaced trees
    # or isolated decorative boulders across the open grazing ground.
    assets=N._asset_builders()
    for key in ('steppe_tree_0','steppe_tree_1','shrub_0','shrub_1','wheat_stand_0'):
        b.add_mesh('Kit_'+key,A.group(assets[key]()))
    for cluster,(cx,cz,r,count) in enumerate([(-59,30,9,11),(-29,-83,10,9),
         (108,-44,9,8),(-80,61,6,8),(156,-167,7,6)]):
        for index in range(count):
            x,z=rng.normal([cx,cz],[r*.45,r*.35]);y=float(t.height_at(x,z))
            if y<.7 or float(t.slope_at(x,z))>.45 or t.surface_at(x,z) in (T.PATH,T.PAVING):continue
            tree=index<2;key='steppe_tree_'+str(index%2) if tree else 'shrub_'+str(index%2)
            name=f'Lee_{cluster}_{index}'
            b.place(Placement(name,'Kit_'+key,(float(x),y-.08,float(z)),float(rng.uniform(0,math.tau)),
                              float(rng.uniform(.7,1)),tree,kind='tree' if tree else 'undergrowth'))
    # The cropped plots are small working parcels beside mills, with a clear
    # headland for carts. Grazing beyond them stays mostly empty.
    for idx,(x,z,w,d) in enumerate(P.FIELDS):
        for row in range(3):
            for col in range(3):
                px=x+(col-1)*w*.32;pz=z+(row-1)*d*.35;y=float(t.height_at(px,pz))
                b.place(Placement(f'Grain_{idx}_{row}_{col}','Kit_wheat_stand_0',(px,y,pz),.17, .65,kind='undergrowth'))

def metadata(b,stats,solids):
    t=b.terrain;m=copy.deepcopy(LEGACY_MANIFEST)
    m['landscapeRevision']=P.REVISION
    m['asset'].update(glb='world.glb',serverCells=384,regionSpanMeters=384,
        bounds={'min':[-122,-3,-274],'max':[274,55,122]},worldCentre=[76,0,-76])
    m['coordinateTransform'].update(serverOrigin=[116,116],origin=[0,0,0],walkingHeight=9.6,serverCells=[384,384],
        addressableWorldBounds={'min':[-116,-267],'max':[267,116]})
    m['bounds']={'playable':{'min':[-116,-3,-267],'max':[267,55,116]},'serverCells':384,'metresPerServerTile':1}
    m['spawnPoints']=b.spawns;m['spawns']=b.spawns
    m['collision']={'binary':'collision.bin','file':'collision.bin','format':'EWCG','version':2,
        'cellMetres':.5,'cellSize':.5,'width':768,'height':768,'originMetres':[-116,116],
        'nodeNames':solids,'heightEncoding':{'origin':-.2,'step':.2,'range':[1,255],'zeroMeansBlocked':True}}
    m['navigation'].update(surfaceNodePrefixes=['Terrain_','Walk_'],defaultSpawn='server-arrival',
        collisionFile='collision.bin',authority='server')
    m['landmarks']=b.landmarks;m['interactives']=b.interactives;m['portals']=b.portals
    m['roads']=b.authored_roads;m['streamingBorders']=b.streaming_borders
    m['terrain'].update(cellMeters=t.cell,lowestElevation=float(t.height.min()),highestElevation=float(t.height.max()),
        worldEdgeBarrier='Open grass and dry mineral benches; unlinked eastern frontier, western lake.')
    m['minimap']={'image':'minimap.webp','file':'minimap.webp','imageSize':[384,384],
        'pixelsPerMetre':1.,'metresPerPixel':1.,'worldMin':[-116,-268],'worldMax':[268,116],
        'northUp':True,'size':[384,384]}
    m['performance']=stats
    m['environment']['sun']['energy']=1.05
    m['environment']['ambient']['energy']=.48
    m['environment']['tonemap'].update(exposure=.88,white=3.0)
    m['environment']['water']['node']='Water_Sea'
    m['environment']=normalize_environment(m['environment'])
    m['rendering']={**m.get('rendering',{}),'occluderFadeAlpha':.18}
    m['npcMarkers']=copy.deepcopy(LEGACY_MANIFEST['runtimePopulation']['npcs'])
    m['harvestables']=copy.deepcopy(LEGACY_MANIFEST['runtimePopulation']['resources'])
    for bucket in ('npcMarkers','harvestables'):
        for e in m[bucket]:
            field='position' if 'position' in e else 'center';x,_,z=e[field]
            x,z=P.remap_world(x,z,b.migration_field)
            e[field]=worldpoint(t,x,z,.1);e['serverTile']=P.tile(x,z)
            if field=='center':e['position']=e[field].copy()
    m['runtimePopulation']={}
    m['contentLayout']=content_layout(b)
    apply_authored_posts(m,t)
    # Preserve all ambient livestock group identities while moving their seats
    # with the working ground. They remain non-colliding scenery actors.
    def follow(obj):
        if isinstance(obj,list):return [follow(e) for e in obj]
        if not isinstance(obj,dict):return obj
        result={k:follow(v) for k,v in obj.items()}
        for key in ('position','center'):
            pos=result.get(key)
            if isinstance(pos,list) and len(pos)==3 and all(isinstance(q,(float,int)) for q in pos):
                x,z=P.remap_world(pos[0],pos[2],b.migration_field);result[key]=worldpoint(t,x,z)
        return result
    if 'ambientPopulation' in m:
        m['ambientPopulation']=follow(m['ambientPopulation'])
        ambient_posts={'herd-open-steppe-west':(-80,-71),'herd-open-steppe-east':(130,22),
          'herd-open-steppe-north':(-3,-157),'herd-open-steppe-south':(116,70),
          'mounts-west-caravanserai':(-45,10),'mounts-east-caravanserai':(45,9),
          'mounts-north-caravanserai':(23,-72),'mounts-south-caravanserai':(-6,51)}
        for group in m['ambientPopulation']['groups']:
            if group['id'] in ambient_posts:
                group['center']=worldpoint(t,*ambient_posts[group['id']])
            group['serverTile']=P.tile(group['center'][0],group['center'][2])
    m['lighting']={'lights':[]}
    m['provenance']={'generator':'source/build_landscape.py','revision':P.REVISION,'seed':P.SEED,
        'nativeArt':'source/kit.py','sharedToolkit':'../_toolkit','externalMeshes':False}
    return m

def apply_authored_posts(manifest,t):
    """Reviewable fixed standing posts, surveyed against the actual final grid."""
    path=HERE/'authored-posts.json'
    if not path.is_file():return
    posts=json.loads(path.read_text(encoding='utf-8'))
    assert posts['revision']==P.REVISION
    for name,tile in posts['npcs'].items():
        manifest['contentLayout']['npcs'][name]=worldpoint(t,tile[0]-116,116-tile[1])
    for bucket in ('interactives','portals'):
        for e in manifest[bucket]:
            tile=posts['interactives'].get(e['id'])
            if tile is None:continue
            e.setdefault('propPosition',e['position'].copy())
            e['serverTile']=tile;e['position']=worldpoint(t,tile[0]-116,116-tile[1])

def content_layout(b):
    out=copy.deepcopy(LEGACY.CONTENT);t=b.terrain
    out.update(primaryArrivalOnly=True,requireFullWildlife=True,roadClearance=3.4)
    out['gauntlets']={'sunmane_gauntlet':{'keeperTile':[147,112],'returnTile':[149,113]}}
    for role in out['services']:
        x,_,z=role['position'];role['position']=worldpoint(t,x,z,.1)
    for name,pos in out['npcs'].items():
        x,z=P.remap_world(pos[0],pos[2],b.migration_field);out['npcs'][name]=worldpoint(t,x,z)
        if name in P.NPC_POSTS:
            tx,ty=P.NPC_POSTS[name];out['npcs'][name]=worldpoint(t,tx-116,116-ty)
    for service in out['services']:
        if service['role']=='training':service['position']=worldpoint(t,7,16)
    out['harvest']['Wheat']=[[x,z,max(w,d)] for x,z,w,d in P.FIELDS]
    out['harvest']['Seed']=[[53,49,8],[79,54,8],[46,-96,7]]
    for resource,sites in out['harvest'].items():
        if resource in ('Wheat','Seed'):continue
        out['harvest'][resource]=[[*P.remap_world(x,z,b.migration_field),max(r,7)] for x,z,r in sites]
    for i,(species,_) in enumerate(out['wildlife'].items()):
        if i<6:sites=[[-48,-103,20],[72,64,19],[143,19,23],[93,-91,23]]
        elif i<12:sites=[[116,-123,24],[-53,-160,20],[170,-102,26],[210,6,23]]
        else:sites=[[191,-204,25],[232,-136,23],[-39,-216,23],[129,-233,24]]
        out['wildlife'][species]=sites
    return out

def collision(b,package):
    n=768;gx,gz=np.meshgrid(-116+(np.arange(n)+.5)*.5,116-(np.arange(n)+.5)*.5)
    ground=b.terrain.height_at(gx,gz);walk=(ground>.25)&(b.terrain.slope_at(gx,gz)<1.05)
    doc,body=GLB.load(package/'world.glb')
    nodes=[i for i,node in enumerate(doc['nodes']) if node.get('name','').startswith('Walk_') and not 'StreamView_' in node.get('name','')]
    deck,dy=GLB.rasterise(GLB.triangles(doc,body,nodes),n,n,-116,116,.5)
    surface=np.where(deck,np.maximum(ground,dy),ground);visible=deck&(dy>=ground-.03)
    # Water geometry owns its actual inundated footprint, including the beck.
    water_nodes=[i for i,node in enumerate(doc['nodes']) if node.get('name','').startswith('Water_') and not 'StreamView_' in node.get('name','')]
    covered,wy=GLB.rasterise(GLB.triangles(doc,body,water_nodes),n,n,-116,116,.5)
    walk &= ~(covered&(wy>surface-.1));walk|=visible
    dz,dx=np.gradient(surface,.5);walk &= visible|(np.hypot(dx,dz)<1.05)
    blocked,solids=NATIVE_COLLISION.blocked_by_scenery(package,gx,gz,.5,
        SimpleNamespace(sample=b.terrain.height_at))
    walk &= ~blocked
    origin=float(surface[walk].min())-.2;step=max(.2,(float(surface[walk].max())-origin)/254)
    grid=np.where(walk,np.clip(np.rint((surface-origin)/step),1,255),0).astype('uint8')
    (package/'collision.bin').write_bytes(struct.pack('<4sHHII',b'EWCG',2,0,n,n)+grid.tobytes())
    return {'heightEncoding':{'origin':origin,'step':step,'range':[1,255],'zeroMeansBlocked':True},
            'walkableCells':int(walk.sum()),'walkableFraction':float(walk.mean()),'authoredSurfaceExport':{'solidMeshNodes':solids}}

def minimap(b,path):
    # Actual shared preview renderer draws this exact build, including native
    # roofs and exposed bridge decks, from a vertical orthographic camera.
    from amberwood import render as R
    scene=R.Scene()
    from dataclasses import replace
    import preview
    sets=preview.texture_sets();MAT.register_preview_materials(scene,sets)
    known={m.name:m for m in scene.materials}
    for item in list(b.meshes.values())+list(b.terrain_meshes.values())+list(b.water_meshes.values()):
        for part in getattr(item,'all_parts',[item]):
            name=part.material
            if name in known:continue
            if name.startswith('sun_'):
                family,color,metal,rough,double,*_=N.MATERIALS[name[4:]]
                material=R.RenderMaterial(name,base_color=color,roughness=rough,metallic=metal)
            else:material=replace(known[MAT.base_material(name)],name=name,
                    alpha_mode='BLEND' if name.endswith(MAT.SOFT_GROUND_SUFFIX) else 'MASK')
            scene.add_material(material);known[name]=material
    for bucket in (b.terrain_meshes,b.water_meshes):
        for name,part in bucket.items():
            if not name.startswith(('StreamView_','Backdrop_')) and part.triangle_count:scene.add_mesh(part)
    for p in b.placements:
        if p.node.startswith('StreamView_'):continue
        transform=M.translation(*p.position)@M.rotation_y(p.rotation_y)@M.scaling(p.scale)
        for part in b.meshes[p.mesh].all_parts:
            if part.triangle_count:scene.add_mesh(part,transform)
    altitude=2000.
    fov=2.*math.degrees(math.atan(192./altitude))
    image=scene.render(eye=(76,altitude,-75.99),target=(76,0,-76),width=384,height=384,
        fov=fov,lighting=R.Lighting(fog_density=0.,ambient_strength=.74,shadow_strength=.38),
        shadows=True,shadow_size=1024,shadow_center=(76,12,-76),shadow_radius=240,
        near=100.,far=2400.)
    image.save(path,quality=93)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,default=PACKAGE);ap.add_argument('--skip-lod',action='store_true')
    ap.add_argument('--skip-minimap',action='store_true');a=ap.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    b=build_region();print('COMPOSED',len(b.placements),'placements',flush=True)
    stats,solids=A.export(b,a.output/'world.glb')
    m=metadata(b,stats,solids)
    (a.output/'world.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
    m['collision'].update(collision(b,a.output))
    import contentposts
    posts=HERE/'server-content.json'
    # The first build migrates marker positions through the local field. Later
    # integration republishes server-content with the matching revision.
    if posts.exists():
        rows=json.loads(posts.read_text(encoding='utf-8'))
        if rows.get('landscapeRevision')==P.REVISION:contentposts.apply(m,a.output,rows)
    contentposts.apply_runtime(m,a.output)
    (a.output/'world.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
    if not a.skip_minimap:minimap(b,a.output/'minimap.webp')
    if not a.skip_lod:
        low=build_region(True);lowstats,_=A.export(low,a.output/'world-lod2.glb',True)
        lm=copy.deepcopy(m);lm['asset']['glb']='world-lod2.glb';lm['performance']=lowstats
        (a.output/'world-lod2.json').write_text(json.dumps(lm,indent=2)+'\n',encoding='utf-8')
    print('BUILD complete',stats,flush=True)

if __name__=='__main__':main()
