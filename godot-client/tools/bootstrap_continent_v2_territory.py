#!/usr/bin/env python3
"""Bootstrap active continent-v2 editors from the recorded owner partition and frozen group terrain.

The Meshy conditioning and source edits have already been frozen; this tool never repeats them and needs no
external model. All map IDs, polygons and tie priority come from partition-inputs/sections_spec.json. Every base
is an exact byte crop of group-terrain, whose files, provenance and source commit are bound in each crop.
Replay protects authored scenes and retains authority/gameplay fields; --check writes nothing. Original source
editors/packages remain historical inputs until content migration retires their physical directories.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon, Point, LineString
from shapely.ops import unary_union
import continent_v2_territories as T

CHECKOUT=Path(__file__).resolve().parents[2]
CLIENT=CHECKOUT/'godot-client'
META=CHECKOUT/'eloria-assets/maps/continent-v2/_continent_v2'
INPUT=META/'partition-inputs'
GROUP=META/'group-terrain'
PLAN=META/'continent-v2-plan.json'
CATALOG=CLIENT/'world_authoring/continent-v2/territories.json'
VIEW=CATALOG.parent/'viewer'

def sha(raw): return hashlib.sha256(raw).hexdigest()
def jbytes(obj): return (json.dumps(obj,indent=1,ensure_ascii=False)+'\n').encode()
def read(path): return json.loads(path.read_text(encoding='utf-8'))
def resource(path):
    rel=path.relative_to(CLIENT) if path.is_relative_to(CLIENT) else Path('..')/path.relative_to(CHECKOUT)
    return 'res://'+rel.as_posix()
def packed(ring): return 'PackedVector2Array('+', '.join(str(v) for point in ring for v in point)+')'
def clip(rings):
    if len(rings)==1: return 'preview_clip_inside = '+packed(rings[0])
    return 'preview_clip_polygons = Array[PackedVector2Array](['+', '.join(packed(r) for r in rings)+'])'
def frame(section):
    x0,z0,x1,z1=section['bounds']; tx=(x0+x1)//2; tz=(z0+z1)//2
    ox=tx-x0+4; oz=z1-tz+4
    cells=int(math.ceil(max(x1-x0+8,z1-z0+8)/6)*6)
    if cells>2048: raise ValueError(section['mapId']+': frame exceeds 2048 cells')
    return [float(tx),0.0,float(tz)], {'origin':[ox,oz],'cells':[cells,cells],'collisionOriginMetres':[-float(ox),float(oz)]}

def line_parts(geometry):
    if geometry.is_empty: return []
    if geometry.geom_type=='LineString': return [geometry]
    return [p for g in getattr(geometry,'geoms',[]) for p in line_parts(g)]

def split_route(points, shapes):
    """Retain the source polyline and record exact cuts with fractional source indices, including sea gaps."""
    runs=[]
    for i,(a,b) in enumerate(zip(points[:-1],points[1:])):
        line=LineString([a,b]); cuts={0.0,1.0}
        if not line.length: continue
        for _,shape in shapes:
            intersection=line.intersection(shape.boundary)
            geometries=list(intersection.geoms) if hasattr(intersection,'geoms') else [intersection]
            for g in geometries:
                if g.is_empty: continue
                if g.geom_type=='Point': cuts.add(line.project(g)/line.length)
                elif g.geom_type=='LineString':
                    for p in (g.coords[0],g.coords[-1]): cuts.add(line.project(Point(p))/line.length)
        ordered=sorted(cuts)
        for lo,hi in zip(ordered[:-1],ordered[1:]):
            if hi-lo<1e-10: continue
            mid=line.interpolate((lo+hi)*0.5,normalized=True)
            owner=next((name for name,shape in shapes if shape.covers(mid)),None)
            start=list(line.interpolate(lo,normalized=True).coords[0]); end=list(line.interpolate(hi,normalized=True).coords[0])
            if runs and runs[-1]['territory']==owner and abs(runs[-1]['sourcePointRange'][1]-(i+lo))<1e-9:
                runs[-1]['sourcePointRange'][1]=i+hi; runs[-1]['polyline'].append(end)
                runs[-1]['points'][1]=i+1
            else: runs.append({'territory':owner,'points':[i,i+1],'sourcePointRange':[i+lo,i+hi],'polyline':[start,end]})
    return runs

def reassign_active_owners(plan, shapes, retired):
    """Position-bearing plan owners use exact priority. Unknown ownership schemas fail closed.

    Historical source identity records, owner decision prose and retired IDs remain provenance; active owners do
    not. A record without an explicit position cannot be reassigned merely from its old territory name.
    """
    def visit(value, path):
        if isinstance(value, dict):
            if value.get('territory') in retired:
                if 'x' in value and 'z' in value:
                    point=Point(value['x'],value['z'])
                elif 'centroid' in value:
                    point=Point(value['centroid'])
                else:
                    raise ValueError('unresolved nonposition plan owner: '+path)
                owner=next((rid for rid,shape in shapes if shape.covers(point)),None)
                if owner is None:
                    raise ValueError('plan owner point lies outside section polygons: '+path)
                value['territory']=owner
            for key,child in value.items(): visit(child,path+'/'+key)
        elif isinstance(value,list):
            for index,child in enumerate(value): visit(child,path+'/'+str(index))
    for key,value in plan.items():
        if key not in ('sources','partition'): visit(value,key)
    def audit(value,path):
        if isinstance(value,dict):
            for key,child in value.items():
                if key not in ('note','ownershipNote','role','kind') and isinstance(child,str) and child in retired:
                    raise ValueError('retired ID in active structured plan field: '+path+'/'+key)
                audit(child,path+'/'+key)
        elif isinstance(value,list):
            for index,child in enumerate(value):
                if isinstance(child,str) and child in retired:
                    raise ValueError('retired ID in active plan list: '+path+'/'+str(index))
                audit(child,path+'/'+str(index))
    for key,value in plan.items():
        if key not in ('sources','partition','decisions','openDecisions'): audit(value,key)


def scene(section,translation,server,origin,size,hsha,patches):
    rid=section['mapId']; base='res://world_authoring/regions/'+rid+'/'
    lines=['[gd_scene format=3]','']
    scripts={'region':'src/dev/map_authoring_region/region_control.gd','terrain':'src/dev/map_authoring_region/terrain_control.gd','sculpt':'src/dev/map_authoring_region/terrain_sculpt_layer.gd','surface':'src/dev/map_authoring_pilot/style/map_authoring_surface.gd','patch':'src/dev/map_authoring_region/terrain_patch.gd'}
    for key,path in scripts.items(): lines.append(f'[ext_resource type="Script" path="res://{path}" id="{key}"]')
    for key,path in [('detail','terrain-detail-luma.png'),('normal','terrain-detail-normal.png')]: lines.append(f'[ext_resource type="Texture2D" path="res://src/dev/map_authoring_pilot/style/textures/{path}" id="{key}"]')
    lines+=['','[sub_resource type="StandardMaterial3D" id="material"]','cull_mode = 2','vertex_color_use_as_albedo = true','albedo_texture = ExtResource("detail")','normal_enabled = true','normal_scale = 0.8','normal_texture = ExtResource("normal")','texture_filter = 5','','[sub_resource type="Resource" id="surface"]','resource_local_to_scene = true','script = ExtResource("surface")','source_material = SubResource("material")','','[sub_resource type="Resource" id="sculpt"]','resource_local_to_scene = true','script = ExtResource("sculpt")',f'base_sha256 = "{hsha}"',f'origin = Vector2({origin[0]}, {origin[1]})',f'grid_size = Vector2i({size[0]}, {size[1]})','cell_metres = 2.0','indices = PackedInt32Array()','deltas = PackedFloat32Array()','','[node name="'+rid+'" type="Node3D" groups=["map_authoring_region"]]','script = ExtResource("region")',f'region_id = "{rid}"',f'continent_translation = Vector3({translation[0]}, 0, {translation[2]})',f'server_origin = Vector2i({server["origin"][0]}, {server["origin"][1]})',f'server_cells = Vector2i({server["cells"][0]}, {server["cells"][1]})',f'collision_origin_metres = Vector2({server["collisionOriginMetres"][0]}, {server["collisionOriginMetres"][1]})',f'ownership_polygon_sha256 = "{T.polygons_sha(section["ownershipPolygons"])}"',f'export_directory = "res://../eloria-assets/maps/continent-v2/{rid}/authoring"','','[node name="Terrain" type="Node3D" parent="."]','script = ExtResource("terrain")',f'origin = Vector2({origin[0]}, {origin[1]})',f'grid_size = Vector2i({size[0]}, {size[1]})','cell_metres = 2.0',f'base_heights_path = "{base}base-heights.f32le"',f'base_colors_path = "{base}base-colors.rgba8"','base_surface = SubResource("surface")','sculpt_layer = SubResource("sculpt")','preview_uv_metres_inverse = 0.17',clip(section['ownershipPolygons']),'','[node name="Patches" type="Node3D" parent="Terrain"]']
    for patch in patches:
        x,y,z=patch['continentOrigin']; name=patch['id'].replace('-','_')
        lines+=['',f'[node name="{name}" type="Marker3D" parent="Terrain/Patches"]','script = ExtResource("patch")',f'patch_id = "{patch["id"]}"',f'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {x-translation[0]}, {y}, {z-translation[2]})',f'shape = {patch["shape"]}',f'operation = {patch["operation"]}',f'size = Vector2({patch["size"][0]}, {patch["size"][1]})',f'feather = {patch["feather"]}','enabled = true']
    for name,parent in [('Ground','.'),('Regions','Ground'),('Roads','.'),('Rivers','.'),('WaterRegions','.'),('Bridges','.'),('AuthoredAssets','.'),('Gameplay','.'),('Spawns','Gameplay'),('Portals','Gameplay'),('Interactives','Gameplay'),('Landmarks','Gameplay'),('Harvestables','Gameplay'),('NpcMarkers','Gameplay'),('AmbientPopulation','Gameplay'),('RuntimePoints','.'),('TerritoryPoints','RuntimePoints'),('TutorialTargets','RuntimePoints'),('GeneratedPreview','.')]:
        lines+=['',f'[node name="{name}" type="Node3D" parent="{parent}"]']
    return ('\n'.join(lines)+'\n').encode()

def generate():
    provenance=read(INPUT/'input-provenance.json')
    for name,record in provenance['files'].items():
        raw=(INPUT/name).read_bytes()
        if sha(raw)!=record['sha256'] or len(raw)!=record['bytes']: raise ValueError('partition input changed: '+name)
    spec=read(INPUT/'sections_spec.json'); sections=spec['sections']; report=read(INPUT/'check_report.json')
    frozen=read(GROUP/'terrain-provenance.json')
    if sha((GROUP/'terrain-provenance.json').read_bytes())!=provenance['frozenTerrainProvenanceSha256']: raise ValueError('frozen provenance changed')
    grid=frozen['grid']; w,h=grid['gridSize']; first=np.array(grid['continentFirstVertex']); cell=grid['cellMetres']
    if cell!=2: raise ValueError('group lattice must be 2 metres')
    arrays={}
    for name,dtype,shape in [('base-heights.f32le','<f4',(h,w)),('base-colors.rgba8','u1',(h,w,4))]:
        raw=(GROUP/name).read_bytes(); record=frozen['outputs'][name]
        if sha(raw)!=record['sha256'] or len(raw)!=record['bytes']: raise ValueError('frozen base changed: '+name)
        arrays[name]=np.frombuffer(raw,dtype).reshape(shape)
    if not np.isfinite(arrays['base-heights.f32le']).all(): raise ValueError('nonfinite frozen heights')
    shapes=[(s['mapId'],unary_union([Polygon(r) for r in s['ownershipPolygons']])) for s in sections]
    ids=[s['mapId'] for s in sections]
    if len(ids)!=len(set(ids)): raise ValueError('duplicate section ID')
    aliases={s['id']:s['mapId'] for s in sections}; shape_by=dict(shapes)
    outputs={}; source_plan=read(INPUT/'source-plan.json'); plan=copy.deepcopy(source_plan)
    plan['partition']={'specPath':(INPUT/'sections_spec.json').relative_to(CHECKOUT).as_posix(),'specSha256':sha((INPUT/'sections_spec.json').read_bytes()),'reportPath':(INPUT/'check_report.json').relative_to(CHECKOUT).as_posix(),'reportSha256':sha((INPUT/'check_report.json').read_bytes()),'priority':ids,'retiredMapIds':spec['retiredMapIds'],'sourcePlanSha256':sha((INPUT/'source-plan.json').read_bytes()),'sourceCommit':frozen['sourceCommit']}
    plan['decisions'].append('Owner Landfall section brief, 2026-10-10: exact recorded polygons and priority; authored source content and frozen terrain retained; group terrain is outside the active catalog.')
    plan['name']='Continent v2 owner section partition'
    plan['status']='Fifteen active owner sections; frozen terrain crops and authored content migration'
    plan['territories']=[]; seams=[]
    for record in report['borders']:
        pair=[aliases[v] for v in record['between']]; intersection=shape_by[pair[0]].boundary.intersection(shape_by[pair[1]].boundary)
        segments=[]
        for line in line_parts(intersection):
            points=list(line.coords)
            for a,b in zip(points[:-1],points[1:]): segments.append(sorted([list(a),list(b)]))
        segments.sort()
        if not segments or abs(intersection.length-record['length_m'])>1.1: raise ValueError('reported border differs: '+str(pair))
        entry={'between':pair,'segments':segments,'lengthMetres':intersection.length,'reportedLengthMetres':record['length_m'],'note':'Exact owner section border; ordinary land crossings.'}
        flattened=[v for seg in segments for v in seg]
        if len({p[0] for p in flattened})==1: entry['edge']={'x':flattened[0][0],'z':[min(p[1] for p in flattened),max(p[1] for p in flattened)]}
        elif len({p[1] for p in flattened})==1: entry['edge']={'z':flattened[0][1],'x':[min(p[0] for p in flattened),max(p[0] for p in flattened)]}
        seams.append(entry)
    knob=copy.deepcopy(next(m for m in source_plan['seams']['moles'] if m['id']=='seam-mole-knob')); knob['between']=['greenlight','spindle_hill']
    plan['seams']={'rule':source_plan['seams']['rule'],'openSeams':seams,'moles':[knob]}
    for key in ('approvedRoutes','approvedDecks'):
        for record in plan[key]: record['byTerritory']=split_route(record['approvedPolyline'],shapes)
    for lake in plan['water'].get('lakes',[]):
        p=Point(lake['properties']['centroid']); lake['properties']['territory']=next((rid for rid,shape in shapes if shape.covers(p)),None)
    entries=[]; patches={}
    for source in frozen['sources']:
        for patch in source.get('sceneSidePatches',[]): patches[patch['id']]=patch
    parent_files={kind:{'path':(GROUP/name).relative_to(CHECKOUT).as_posix(),'sha256':sha((GROUP/name).read_bytes())} for kind,name in [('heights','base-heights.f32le'),('colors','base-colors.rgba8'),('provenance','terrain-provenance.json')]}
    environment=next(iter(read(INPUT/'source-stubs.json').values()))['environment']
    for section in sections:
        rid=section['mapId']; translation,server=frame(section); region=CLIENT/'world_authoring/regions'/rid; package=CHECKOUT/'eloria-assets/maps/continent-v2'/rid
        x0,z0,x1,z1=section['bounds']; lo=np.floor((np.array([x0,z0])-60-first)/cell).astype(int); hi=np.ceil((np.array([x1,z1])+60-first)/cell).astype(int)
        lo=np.maximum(lo,0); hi=np.minimum(hi,[w-1,h-1]); c,r=lo; cw,ch=hi-lo+1; origin=(first+lo*cell-np.array(translation)[[0,2]]).tolist()
        crop={name:array[r:r+ch,c:c+cw].tobytes() for name,array in arrays.items()}
        for name,raw in crop.items(): outputs[region/name]=raw
        prov={'schema':'eloria-continent-v2-terrain-crop-v1','sourceCommit':frozen['sourceCommit'],'crop':{'parent':'isles-group-terrain','parentFiles':parent_files,'parentGrid':grid,'sourceCommit':frozen['sourceCommit'],'row0':int(r),'col0':int(c),'rows':int(ch),'cols':int(cw)},'outputs':{name:{'sha256':sha(raw),'bytes':len(raw)} for name,raw in crop.items()}}
        outputs[region/'terrain-provenance.json']=jbytes(prov)
        geo={'revision':'continent-v2-draft-1','translation':translation,'ownershipPolygon':section['ownershipPolygons'][0],'ownershipPolygons':section['ownershipPolygons'],'geometryMode':'continent-v2-editor-source'}
        stub={'schemaVersion':1,'asset':{'id':rid,'name':section['label'],'glb':'world.glb','units':'meters','seaLevel':0.0},'productionStatus':'continent-v2-editor-source','continentGeography':geo,'server':server,'environment':copy.deepcopy(environment)}
        outputs[package/'world.json']=jbytes(stub)
        scene_path=region/(rid+'.tscn'); spec_path=region/'region-authoring-spec.json'
        terrain={'origin':origin,'cellMetres':cell,'vertices':[int(cw),int(ch)]}
        entry={'id':rid,'label':section['label'],'manifestPath':resource(package/'world.json'),'publishedManifestPath':resource(package/'client/world.json'),'scenePath':resource(scene_path),'authoringSpecPath':resource(spec_path)}; entries.append(entry)
        plan['territories'].append({'id':rid,'label':section['label'],'role':'Owner-authored section partition','translation':translation,'ownershipPolygon':geo['ownershipPolygon'],'ownershipPolygons':geo['ownershipPolygons'],'server':server,'terrain':{**terrain,'baseHeightsSha256':sha(crop['base-heights.f32le']),'baseColorsSha256':sha(crop['base-colors.rgba8'])},'scenePath':scene_path.relative_to(CHECKOUT).as_posix()})
        chosen=[p for pid,p in patches.items() if (pid=='seam-mole-knob' and rid in knob['between']) or (pid=='seam-mole-pier' and rid=='ravenhead')]
        outputs[scene_path]=scene(section,translation,server,origin,[int(cw),int(ch)],sha(crop['base-heights.f32le']),chosen)
        authoring={'schema':'eloria-region-authoring-spec-v1','regionId':rid,'label':section['label'],'adapter':'continent-v2-meshy-v1','paths':{'scene':scene_path.relative_to(CHECKOUT).as_posix(),'manifest':(package/'world.json').relative_to(CHECKOUT).as_posix(),'snapshot':(package/'authoring/continent-authoring.json').relative_to(CHECKOUT).as_posix()},'inputs':{'baseHeights':(region/'base-heights.f32le').relative_to(CHECKOUT).as_posix(),'baseColors':(region/'base-colors.rgba8').relative_to(CHECKOUT).as_posix()},'continentTranslation':translation,'server':server,'terrain':terrain,'authority':{'ownedRouteIds':[],'requiredRouteIds':[],'ownedPlanFeatureIds':[],'ownedFerryConnectionIds':[]},'gameplay':{'runtimeBindingCount':0,'runtimePointCount':0,'existingMarkerBindingCount':0},'continentV2':{'planPath':PLAN.relative_to(CHECKOUT).as_posix(),'vertical':{k:source_plan['vertical'][k] for k in ('A','u0','peakMetres','gainAtSea')}}}
        if spec_path.exists():
            existing=read(spec_path)
            for key in ('authority','gameplay'): authoring[key]=existing.get(key,authoring[key])
        outputs[spec_path]=authoring
    reassign_active_owners(plan,shapes,set(spec['retiredMapIds']))
    outputs[PLAN]=jbytes(plan); plan_sha=sha(outputs[PLAN])
    for path,value in list(outputs.items()):
        if isinstance(value,dict): value['continentV2']['planSha256']=plan_sha; outputs[path]=jbytes(value)
    original=read(INPUT/'source-catalog.json')
    libraries=[{'directory':'res://world_authoring/regions/'+e['id']+'/assets/prototypes','catalogPrefix':e['id']} for e in original['entries']]
    catalog={'schema':original['schema'],'partitionSpecPath':resource(INPUT/'sections_spec.json'),'ownershipPriority':ids,'retiredMapIds':spec['retiredMapIds'],'sharedAssetLibraries':libraries,'sharedAssetCatalogPath':'res://world_authoring/continent-v2/shared-kit-catalog.json','entries':sorted(entries,key=lambda e:e['label'])}
    if CATALOG.exists():
        omitted={e['id'] for e in read(CATALOG)['entries']}-set(ids)
        if not omitted.issubset(set(spec['retiredMapIds'])): raise ValueError('unapproved catalog retirement: '+str(omitted))
    frames={r['id']:{**r['server'],'translation':r['translation']} for r in plan['territories']}
    problems=T.served_frame_problems(frames,CATALOG,entries)
    if problems: raise ValueError('\n'.join(problems))
    outputs[CATALOG]=jbytes(catalog)
    # Shared sea is in the continent frame, independent of any territory origin. Existing sea tint stays pinned.
    def viewer(selected):
        original_view=(INPUT/'source-view.tscn').read_text()
        resource_part=original_view[:original_view.index('[node name="IslesView"')]
        resource_part='\n'.join(line for line in resource_part.splitlines() if 'type="PackedScene"' not in line)
        scene_resources='\n'.join(f'[ext_resource type="PackedScene" path="{e["scenePath"]}" id="{e["id"]}"]' for e in selected)
        resource_part=resource_part.replace('[gd_scene format=3]', '[gd_scene format=3]\n\n'+scene_resources)
        common_nodes=original_view[original_view.index('[node name="IslesView"'):original_view.index('[node name="SouthWestIsle"')]
        common_nodes=common_nodes.replace('325, 0, 150)', '1743, 0, 7420)').replace('325, -48, 150)', '1743, -48, 7420)')
        lines=[resource_part,common_nodes]
        for e in selected:
            t=next(t for t in plan['territories'] if t['id']==e['id']); tx,ty,tz=t['translation']
            lines+=['',f'[node name="{e["id"]}" parent="." instance=ExtResource("{e["id"]}")]',f'position = Vector3({tx}, {ty}, {tz})','',f'[node name="Terrain" parent="{e["id"]}"]',clip(t['ownershipPolygons']),'',f'[editable path="{e["id"]}"]']
        lines+=['','[node name="Overview" type="Camera3D" parent="."]','position = Vector3(1743, 2600, 9700)','rotation_degrees = Vector3(-50, 0, 0)','far = 12000.0']
        return ('\n'.join(lines)+'\n').encode()
    outputs[VIEW/'isles_view.tscn']=viewer(entries)
    for e in entries: outputs[VIEW/(e['id']+'_view.tscn')]=viewer([e])
    outputs[META/'README.md']=('''# Continent v2 section partition

Active map IDs, exact polygons and ownership priority come from `partition-inputs/sections_spec.json`; the recorded
check report has 33 ordinary shared borders. Ravenhead retains both disjoint ownership rings. All editor bases are
byte crops of the hash-pinned `group-terrain` frozen terrain. Its grid is a data parent outside the active catalog.
The original plan and catalog are pinned under `partition-inputs` with their source commit and file hashes.

Run `python godot-client/tools/bootstrap_continent_v2_territory.py --check` to replay immutable crop/frame/plan checks.
The bootstrap does not reset existing authored scenes and preserves gameplay/authority spec fields. Edit those
scenes normally, then run `python godot-client/tools/continent_v2_territories.py` to validate seams and ownership.
Do not re-run the original Meshy conditioning. Source kit libraries are shared by catalog metadata; placements
remain authored content. Original three source editors/packages are staged historical inputs until migration
removes their physical directories; they have no active catalog references.
''').encode()
    return outputs

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--check',action='store_true'); args=parser.parse_args()
    outputs=generate(); problems=[]
    for path,raw in outputs.items():
        protected=path.suffix=='.tscn' and '/regions/' in path.as_posix()
        if args.check:
            if not path.exists(): problems.append('missing '+str(path.relative_to(CHECKOUT)))
            elif not protected and path.read_bytes()!=raw: problems.append('differs '+str(path.relative_to(CHECKOUT)))
        elif not (protected and path.exists()):
            path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists() or path.read_bytes()!=raw: path.write_bytes(raw)
    if args.check and not problems:
        territories=T.load_territories(CATALOG)
        for check in (T.check_frames,T.check_crops):
            found,_=check(territories); problems.extend(found)
    print(json.dumps({'generatedFiles':len(outputs),'problems':problems},indent=1))
    return int(bool(problems))
if __name__=='__main__': raise SystemExit(main())
