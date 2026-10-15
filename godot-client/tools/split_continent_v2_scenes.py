#!/usr/bin/env python3
"""Rehome pinned isle content into the recorded fifteen-map partition.

Inputs come from pinned Git objects, including the P2 scene skeleton checkpoint.
No retired live scene is read. Complete node transforms are composed before
reframing; asset identities and payload are preserved. Roads are split by exact
cubic/line boundary intersections and de Casteljau subdivision, never flattened.
Ground keeps its analytic shape plus an exact source/destination ownership mask.
Every source node must have an explicit accounting reason. --check writes nothing
and refuses stale output; --output-root supports a reviewable scratch pilot.
"""
from __future__ import annotations
import argparse
import copy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import tempfile
from collections import Counter, defaultdict
import numpy as np
from shapely import affinity
from shapely.geometry import Point, Polygon, LineString, box
from shapely.ops import unary_union
import freeze_continent_v2_terrain as F
import continent_v2_territories as T

CHECKOUT=F.CHECKOUT
SOURCE_REF=F.SOURCE_REF
SKELETON_REF='fd12432dac6321b9dee16025843c578f7a4e8943'
META='eloria-assets/maps/continent-v2/_continent_v2'
PARTITION=META+'/partition-inputs/sections_spec.json'
RENAMES=META+'/marker-renames.json'
REGION_ROOT='godot-client/world_authoring/regions'
SCHEMA='eloria-continent-v2-marker-renames-v1'
REF=re.compile(r'(ExtResource|SubResource)\("([^"\n]+)"\)')
TRANSFORM_KEYS={'transform','position','rotation','rotation_degrees','rotation_order','quaternion','scale'}
SCRIPT_ROOT='res://src/dev/map_authoring_region/'
CONTAINERS={'.','Terrain','Terrain/Patches','Ground','Ground/Regions','Roads','Rivers','WaterRegions','Bridges','AuthoredAssets','Gameplay','Gameplay/Spawns','Gameplay/Portals','Gameplay/Interactives','Gameplay/Landmarks','Gameplay/Harvestables','Gameplay/NpcMarkers','Gameplay/AmbientPopulation','Gameplay/RuntimePoints','Gameplay/RuntimePoints/TerritoryPoints','Gameplay/RuntimePoints/TutorialTargets','GeneratedPreview'}

class SplitError(ValueError): pass

def jbytes(value): return F.json_bytes(value)
def scalar(text,default=''): return json.loads(text) if text is not None else default
def packed(kind,values): return kind+'('+', '.join(format(float(v),'.12g') for v in np.asarray(values).ravel())+')'
def matrix_text(matrix): return packed('Transform3D',np.r_[matrix[:3,:3].T.ravel(),matrix[:3,3]])
def properties_text(section): return '\n'.join(f'{k} = {v}' for k,v in section.properties.items())
def polygons(geometry):
    if geometry.is_empty: return []
    if geometry.geom_type=='Polygon': return [geometry]
    return [p for item in getattr(geometry,'geoms',[]) for p in polygons(item)]
def normalized_id(old):
    value=old
    for token in ('sw_isle','sw-isle','tollholms','gull_skerries','gull-skerries','sw','th','gs'):
        value=re.sub(r'(?<![A-Za-z0-9])'+re.escape(token)+r'(?![A-Za-z0-9])','',value)
    return re.sub(r'[-_]{2,}','-',value).strip('-_') or 'marker'
def sections(blob):
    with tempfile.TemporaryDirectory(prefix='eloria-split-parser-') as scratch:
        path=Path(scratch)/'scene.tscn';path.write_bytes(blob)
        return T.read_tscn(path)
def serialize(section):
    attributes=[]
    for key,value in section.attributes.items():
        if key in ('unique_id','uid'): continue
        encoded=json.dumps(value,ensure_ascii=False) if key in ('name','type','parent','id','path') else str(value)
        attributes.append(f'{key}={encoded}')
    return '['+section.kind+(' '+' '.join(attributes) if attributes else '')+']\n'+properties_text(section)+'\n'

@dataclass
class Source:
    id:str
    namespace:str
    scene:T.Scene
    sections:list
    translation:np.ndarray
    ownership:object
    resources:dict
    account:dict
    @classmethod
    def load(cls,reader,entry,index,plan):
        raw=reader.read(F.git_path(entry['scenePath']))
        scene=F.parse_scene(raw);ss=sections(raw)
        trans=F.numbers(scene.node('.').properties['continent_translation'],'Vector3')
        row=next(x for x in plan['territories'] if x['id']==entry['id'])
        shape=unary_union([Polygon(p) for p in row.get('ownershipPolygons',[row['ownershipPolygon']])])
        resources={(s.kind,s.attributes['id']):s for s in ss if s.kind in ('ext_resource','sub_resource')}
        return cls(entry['id'],f's{index}',scene,ss,trans,shape,resources,{})
    def continent_matrix(self,path):
        try:m=self.scene.world(path)
        except ValueError as error:raise SplitError(f"invalid/nonfinite source transform {self.id}:{path}") from error
        m[:3,3]+=self.translation
        if not np.isfinite(m).all():raise SplitError(f"nonfinite source transform {self.id}:{path}")
        return m
    def reason(self,path,reason):
        if path in self.account: raise SplitError(f'{self.id}:{path} assigned twice')
        self.account[path]=reason

class Registry:
    def __init__(self,base):
        self.sections=copy.deepcopy([s for s in base if s.kind in ('ext_resource','sub_resource')]);self.seen={}
    def import_section(self,source,section):
        result=copy.deepcopy(section)
        result.attributes={k:self.rewrite(source,str(v)) if k=='instance' else v for k,v in result.attributes.items()}
        result.properties={k:self.rewrite(source,v) for k,v in result.properties.items()}
        return result
    def rewrite(self,source,text):
        def replace(match):
            kind,old=match.groups();node_kind='ext_resource' if kind=='ExtResource' else 'sub_resource'
            key=(source.namespace,node_kind,old);new=source.namespace+'_'+old
            if key not in self.seen:
                self.seen[key]=new
                if (node_kind,old) not in source.resources: raise SplitError(f'{source.id}: missing resource {old}')
                item=self.import_section(source,source.resources[(node_kind,old)])
                item.attributes['id']=new;self.sections.append(item)
            return kind+'('+json.dumps(new)+')'
        return REF.sub(replace,text)

class Destination:
    def __init__(self,section,reader):
        self.id=section['mapId'];self.section=section
        path=f'{REGION_ROOT}/{self.id}/{self.id}.tscn'
        self.base=sections(reader.read(path));self.scene=F.parse_scene(reader.read(path))
        self.translation=F.numbers(self.scene.node('.').properties['continent_translation'],'Vector3')
        self.shape=unary_union([Polygon(r) for r in section['ownershipPolygons']])
        self.registry=Registry(self.base)
        self.nodes=copy.deepcopy([s for s in self.base if s.kind=='node'])
        self.paths={'.' if n.attributes.get('parent') is None else n.attributes['name'] if n.attributes['parent']=='.' else n.attributes['parent']+'/'+n.attributes['name'] for n in self.nodes}
        self.count=Counter();self.asset_ids=set();self.markers=[]
    def append(self,source,path,parent,name=None,properties=None,reframe=True):
        section=self.registry.import_section(source,source.scene.node(path))
        section.attributes['parent']=parent
        section.attributes['name']=name or source.scene.node(path).attributes['name']
        newpath=section.attributes['name'] if parent=='.' else parent+'/'+section.attributes['name']
        if newpath in self.paths: raise SplitError(f'{self.id}: duplicate node {newpath}')
        self.paths.add(newpath)
        if reframe:
            m=source.continent_matrix(path);m[:3,3]-=self.translation
            section.properties={k:v for k,v in section.properties.items() if k not in TRANSFORM_KEYS}
            section.properties['transform']=matrix_text(m)
        if properties: section.properties.update(properties)
        self.nodes.append(section)
        return newpath,section
    def bytes(self):
        # External resources precede subresources; dependency recursion adds children first.
        resources=sorted(self.registry.sections,key=lambda s:s.kind!='ext_resource')
        return ('[gd_scene format=3]\n\n'+'\n'.join(serialize(s) for s in resources+self.nodes)).encode('utf-8')

def owner(point,destinations):
    p=Point(float(point[0]),float(point[1]))
    for d in destinations:
        if d.shape.covers(p):return d
    raise SplitError(f'unassigned continent point {tuple(point)}')

def children(source,path):
    if not hasattr(source,'child_map'):
        source.child_map=defaultdict(list)
        for p,n in source.scene.nodes.items():
            source.child_map[n.attributes.get('parent')].append(p)
    result=[];pending=list(source.child_map[path])
    while pending:
        p=pending.pop(0);result.append(p);pending.extend(source.child_map[p])
    return result
def curve_data(source,node):
    ref=node.properties.get('curve','');match=REF.fullmatch(ref)
    if match is None or match[1]!='SubResource': raise SplitError('path has no saved Curve3D')
    curve=source.scene.sub[match[2]]
    points=re.search(r'"points":\s*PackedVector3Array\(([^)]*)\)',curve.properties['_data'])
    tilts=re.search(r'"tilts":\s*PackedFloat32Array\(([^)]*)\)',curve.properties['_data'])
    if not points or not tilts: raise SplitError('curve has no points/tilts')
    data=np.asarray(T.nums(points[1]),dtype=float).reshape(-1,3,3)
    tilt=np.asarray(T.nums(tilts[1]),dtype=float)
    if len(data)<2 or len(tilt)!=len(data) or not np.isfinite(data).all(): raise SplitError('invalid saved curve')
    return curve,data,tilt

def bezier(control,t):
    a=(1-t)*control[:-1]+t*control[1:];b=(1-t)*a[:-1]+t*a[1:]
    return (1-t)*b[0]+t*b[1]
def subdivide(control,t):
    a=(1-t)*control[:-1]+t*control[1:];b=(1-t)*a[:-1]+t*a[1:];c=(1-t)*b[0]+t*b[1]
    return np.array([control[0],a[0],b[0],c]),np.array([c,b[1],a[2],control[3]])
def interval(control,lo,hi):
    left,_=subdivide(control,hi)
    return subdivide(left,lo/hi)[1] if lo else left

def cuts(control,destinations):
    xz=control[:,[0,2]]
    lower=xz.min(axis=0);upper=xz.max(axis=0)
    coefficients=np.array([xz[0],3*(xz[1]-xz[0]),3*(xz[0]-2*xz[1]+xz[2]),-xz[0]+3*xz[1]-3*xz[2]+xz[3]])
    result=[0.,1.]
    for d in destinations:
        for poly in polygons(d.shape):
            bounds=poly.bounds
            if upper[0]<bounds[0] or lower[0]>bounds[2] or upper[1]<bounds[1] or lower[1]>bounds[3]:continue
            ring=list(poly.exterior.coords)
            for a,b in zip(ring[:-1],ring[1:]):
                a=np.array(a);b=np.array(b)
                if np.any(np.maximum(a,b)<lower-1e-8) or np.any(np.minimum(a,b)>upper+1e-8):continue
                edge=b-a
                coeff=coefficients.copy();coeff[0]-=a
                cross=coeff[:,0]*edge[1]-coeff[:,1]*edge[0]
                if np.max(abs(cross))<1e-9: raise SplitError('road runs along an ownership border')
                for root in np.polynomial.polynomial.polyroots(cross):
                    if abs(root.imag)>1e-8 or not 1e-10<root.real<1-1e-10:continue
                    t=float(root.real);p=bezier(control,t)[[0,2]]
                    u=np.dot(p-a,edge)/np.dot(edge,edge)
                    if -1e-8<=u<=1+1e-8:result.append(t)
    result.sort();return [v for i,v in enumerate(result) if i==0 or v-result[i-1]>1e-8]

def split_curve(data,tilts,widths,matrix,destinations):
    runs=[]
    for index in range(len(data)-1):
        a,b=data[index],data[index+1]
        control=np.array([a[2],a[2]+a[1],b[2]+b[0],b[2]])
        world=control@matrix[:3,:3].T+matrix[:3,3]
        values=cuts(world,destinations)
        for lo,hi in zip(values[:-1],values[1:]):
            name=owner(bezier(world,(lo+hi)*.5)[[0,2]],destinations).id
            if not runs or runs[-1]['owner']!=name:runs.append({'owner':name,'segments':[]})
            seg=interval(control,lo,hi)
            runs[-1]['segments'].append((seg, index+lo,index+hi, (1-lo)*tilts[index]+lo*tilts[index+1],(1-hi)*tilts[index]+hi*tilts[index+1],(1-lo)*widths[index]+lo*widths[index+1],(1-hi)*widths[index]+hi*widths[index+1]))
    return runs

def run_arrays(run):
    points=[];tilts=[];widths=[]
    for seg,start,end,ta,tb,wa,wb in run['segments']:
        if not points:points.append(np.array([np.zeros(3),seg[1]-seg[0],seg[0]]));tilts.append(ta);widths.append(wa)
        else:points[-1][1]=seg[1]-seg[0]
        points.append(np.array([seg[2]-seg[3],np.zeros(3),seg[3]]));tilts.append(tb);widths.append(wb)
    return np.array(points),np.array(tilts),np.array(widths)

def ground_masks(source,path,destinations):
    n=source.scene.node(path);m=source.continent_matrix(path)
    if np.any(abs(m[[0,2],1])>1e-8) or np.any(abs(m[1,[0,2]])>1e-8):raise SplitError('tilted ground region unsupported')
    basis=m[np.ix_([0,2],[0,2])];inverse=np.linalg.inv(basis);offset=-inverse@m[[0,2],3]
    half=F.numbers(n.properties.get('size','Vector2(10, 7)'),'Vector2')*.5
    shape=int(n.properties.get('shape','0'))
    existing=n.properties.get('clip_polygon')
    old=source.ownership
    if existing:
        ring=F.numbers(existing,'PackedVector2Array').reshape(-1,2)
        if len(ring):old=old.intersection(Polygon(ring@basis.T+m[[0,2],3]))
    for d in destinations:
        chosen=[]
        for mask in polygons(old.intersection(d.shape)):
            local=affinity.affine_transform(mask,[inverse[0,0],inverse[0,1],inverse[1,0],inverse[1,1],*offset])
            unit=affinity.scale(local,xfact=1/half[0],yfact=1/half[1],origin=(0,0))
            hit=unit.intersection(box(-1,-1,1,1)).area>1e-12 if shape==1 else unit.distance(Point(0,0))<1-1e-12
            if hit:
                if local.interiors:raise SplitError('ground mask has holes')
                ring=np.array(local.exterior.coords[:-1])
                if not 3<=len(ring)<=64:raise SplitError('ground mask vertex limit')
                chosen.append(ring)
        if len(chosen)>1:raise SplitError(f'{source.id}:{path}: multiple ground mask components')
        if chosen:yield d,chosen[0]

def build(checkout=CHECKOUT,source_ref=SOURCE_REF,skeleton_ref=SKELETON_REF):
    reader=F.GitInputs(checkout,source_ref);base=F.GitInputs(checkout,skeleton_ref)
    spec=json.loads(base.read(PARTITION));destinations=[Destination(s,base) for s in spec['sections']]
    by_id={d.id:d for d in destinations}
    catalog=json.loads(reader.read(F.CATALOG_PATH));plan=json.loads(reader.read(META+'/continent-v2-plan.json'))
    sources=[Source.load(reader,e,i,plan) for i,e in enumerate(catalog['entries'])]
    rename_entries=[];road_report=[];transform_max=0.;all_asset_ids=Counter();marker_ids=set()
    for source in sources:
        grounds=[(p,n) for p,n in source.scene.nodes.items() if source.scene.script_of(n)==SCRIPT_ROOT+'ground_region_control.gd']
        ground_order={p:i for i,(p,n) in enumerate(sorted(grounds,key=lambda item:(int(item[1].properties.get('priority','0')),scalar(item[1].properties.get('region_id'),item[1].attributes['name']))))}
        for path,n in source.scene.nodes.items():
            script=source.scene.script_of(n)
            if path in source.account:continue
            if path in CONTAINERS:
                if path not in ('.','Terrain') and (n.properties or n.attributes.get('type')!='Node3D'):raise SplitError(f'nonempty structural node {source.id}:{path}')
                source.reason(path,'frozen terrain/P2 structure' if path in ('.','Terrain','Terrain/Patches') else 'preserved structural container')
                continue
            if script==SCRIPT_ROOT+'terrain_patch.gd':
                identity=scalar(n.properties.get('patch_id'))
                targets=['greenlight','spindle_hill'] if identity=='seam-mole-knob' else ['ravenhead'] if identity=='seam-mole-pier' else []
                if not targets:raise SplitError('unrecognized terrain patch '+identity)
                for target in targets:
                    matches=[p for p,node in by_id[target].scene.nodes.items() if scalar(node.properties.get('patch_id'))==identity]
                    if len(matches)!=1:raise SplitError('P2 mirrored patch missing '+identity)
                    expected=source.continent_matrix(path);actual=by_id[target].scene.world(matches[0]);actual[:3,3]+=by_id[target].translation
                    if np.max(abs(expected-actual))>.001:raise SplitError('P2 patch transform moved')
                source.reason(path,'P2 preserved mirrored patch '+identity);continue
            if script==SCRIPT_ROOT+'asset_control.gd':
                if n.attributes.get('parent')!='AuthoredAssets':raise SplitError('nested asset wrapper unsupported')
                m=source.continent_matrix(path);d=owner(m[[0,2],3],destinations)
                aid=scalar(n.properties.get('asset_id'),n.attributes['name'])
                if aid in d.asset_ids:raise SplitError(f'duplicate preserved asset_id {d.id}:{aid}')
                d.asset_ids.add(aid);all_asset_ids[(source.id,aid)]+=1
                newpath,new=d.append(source,path,'AuthoredAssets',source.namespace+'_'+n.attributes['name'])
                back=T.transform(new.properties['transform']);back[:3,3]+=d.translation
                transform_max=max(transform_max,float(np.max(abs(back-m))))
                if transform_max>=.001:raise SplitError('placement transform exceeds 1mm')
                d.count['placements']+=1;d.count['placements:'+source.id]+=1
                if 'causeway-support' in n.properties.get('scene_path','') or 'causeway-joint' in n.properties.get('scene_path',''):
                    if scalar(n.properties.get('collision_role'))!='none':raise SplitError('repair placement collision role changed')
                    d.count['authoredRepairs']+=1
                source.reason(path,'placement '+d.id)
                for child in children(source,path):
                    childnode=source.scene.node(child)
                    if childnode.attributes.get('instance') is None or set(childnode.properties)-TRANSFORM_KEYS-{'metadata/map_asset_id','metadata/map_asset_scene'}:raise SplitError('unknown authored asset child '+child)
                    relative=child[len(path)+1:];parent=newpath if '/' not in relative else newpath+'/'+relative.rsplit('/',1)[0]
                    d.append(source,child,parent,reframe=False);source.reason(child,'placement content '+d.id)
                continue
            if script==SCRIPT_ROOT+'gameplay_marker.gd':
                m=source.continent_matrix(path);d=owner(m[[0,2],3],destinations)
                old=scalar(n.properties.get('record_id'),n.attributes['name']);kind=scalar(n.properties.get('kind'),'landmark')
                new_id=d.id+'--'+normalized_id(old)
                if new_id in marker_ids:new_id+='--'+hashlib.sha256((source.id+':'+old).encode()).hexdigest()[:8]
                if new_id in marker_ids:raise SplitError('duplicate renamed marker')
                marker_ids.add(new_id)
                parent=n.attributes['parent'].replace('Gameplay/RuntimePoints','RuntimePoints',1)
                d.append(source,path,parent,new_id,{'record_id':json.dumps(new_id)})
                d.count['markers']+=1;d.count['markers:'+kind]+=1;d.markers.append(new_id)
                rename_entries.append({'oldRegion':source.id,'oldMarkerId':old,'oldNodePath':path,'kind':kind,'newRegion':d.id,'newMarkerId':new_id,'continentPosition':m[:3,3].tolist()})
                source.reason(path,'marker '+d.id);continue
            if script==SCRIPT_ROOT+'ground_region_control.gd':
                assigned=[]
                for d,ring in ground_masks(source,path,destinations):
                    props={'clip_polygon':packed('PackedVector2Array',ring),'uv_anchor_continent':packed('Vector2',source.translation[[0,2]]),'uv_anchor_continent_enabled':'true','source_layer_ordinal':str(ground_order[path])}
                    d.append(source,path,'Ground/Regions',source.namespace+'_'+n.attributes['name'],props)
                    d.count['grounds']+=1;assigned.append(d.id)
                if not assigned:raise SplitError('unassigned ground region '+path)
                source.reason(path,'ground mask '+','.join(assigned));continue
            if script==SCRIPT_ROOT+'path_control.gd':
                curve,data,tilt=curve_data(source,n);m=source.continent_matrix(path)
                if n.attributes.get('parent')=='Rivers':
                    world=data[:,2]@m[:3,:3].T+m[:3,3];d=owner(world[len(world)//2,[0,2]],destinations)
                    if not all(d.shape.covers(Point(p[[0,2]])) for p in world):raise SplitError('river crosses border '+path)
                    d.append(source,path,'Rivers',source.namespace+'_'+n.attributes['name']);d.count['rivers']+=1
                    source.reason(path,'whole river '+d.id);continue
                if n.attributes.get('parent')!='Roads':raise SplitError('unknown path group')
                widths=F.numbers(n.properties.get('point_widths','PackedFloat32Array()'),'PackedFloat32Array')
                if len(widths)==0:widths=np.zeros(len(data))
                if len(widths)!=len(data):raise SplitError('road width count differs')
                default=float(n.properties.get('default_width','8'))
                widths=np.where(widths>0,widths,default)
                runs=split_curve(data,tilt,widths,m,destinations)
                identity=scalar(n.properties.get('path_id'),n.attributes['name'])
                for ri,run in enumerate(runs):
                    d=by_id[run['owner']];points,tilts,piece_widths=run_arrays(run)
                    newpath,new=d.append(source,path,'Roads',d.id+'--'+normalized_id(identity)+'--'+str(ri),{'path_id':json.dumps(d.id+'--'+normalized_id(identity)+'--'+str(ri)),'point_widths':packed('PackedFloat32Array',piece_widths)})
                    custom=copy.deepcopy(curve);custom.attributes['id']=source.namespace+'_road_'+hashlib.sha256(identity.encode()).hexdigest()[:16]+'_cut_'+str(ri)
                    custom.properties['_data']='{\n"points": '+packed('PackedVector3Array',points)+',\n"tilts": '+packed('PackedFloat32Array',tilts)+'\n}'
                    custom.properties['point_count']=str(len(points));d.registry.sections.append(custom)
                    new.properties['curve']='SubResource('+json.dumps(custom.attributes['id'])+')'
                    d.count['roads']+=1
                    road_report.append({'source':source.id,'path':path,'newRegion':d.id,'newPathId':scalar(new.properties['path_id']),'sourceParameterRange':[run['segments'][0][1],run['segments'][-1][2]],'points':len(points)})
                source.reason(path,'cut road '+','.join(run['owner'] for run in runs));continue
            if script==SCRIPT_ROOT+'bridge_control.gd':
                childpaths=children(source,path)
                if {p.rsplit('/',1)[-1] for p in childpaths}!={'Start','End'}:raise SplitError('unexpected bridge children '+path)
                ends=[source.continent_matrix(p)[[0,2],3] for p in childpaths]
                d=owner(np.mean(ends,axis=0),destinations)
                if not d.shape.covers(LineString(ends)):raise SplitError('bridge crosses border '+path)
                newpath,_=d.append(source,path,'Bridges',source.namespace+'_'+n.attributes['name']);d.count['bridges']+=1;source.reason(path,'whole bridge '+d.id)
                for child in childpaths:
                    d.append(source,child,newpath,reframe=False);source.reason(child,'bridge endpoint '+d.id)
                continue
            if script==SCRIPT_ROOT+'water_region_control.gd':
                m=source.continent_matrix(path);d=owner(m[[0,2],3],destinations)
                d.append(source,path,'WaterRegions',source.namespace+'_'+n.attributes['name']);d.count['waters']+=1;source.reason(path,'whole water '+d.id);continue
            raise SplitError(f'unknown/unassigned source node {source.id}:{path} ({script or n.attributes.get("type")})')
        if set(source.account)!=set(source.scene.nodes):raise SplitError('incomplete source accounting '+source.id)
    outputs={};spawn_total=0;spawn_ids=set()
    per_spawns=defaultdict(list);spawn_sources=defaultdict(dict)
    for source in sources:
        content=json.loads(reader.read(f'eloria-assets/maps/continent-v2/{source.id}/content/spawns.json'))
        for old in content['spawns']:
            if old['id'] in spawn_ids:raise SplitError('duplicate spawn row id')
            spawn_ids.add(old['id']);point=np.asarray(old['local'])+source.translation[[0,2]];d=owner(point,destinations)
            row=copy.deepcopy(old);row['local']=(point-d.translation[[0,2]]).tolist();per_spawns[d.id].append(row);spawn_total+=1
            spawn_sources[d.id][source.id]=content['source'];d.count['spawns:'+source.id]+=1
    for d in destinations:
        expected=sum(d.section['placementsBySourceScene'].values())
        if d.count['placements']!=expected:raise SplitError(f'{d.id}: placement count differs {d.count["placements"]}!={expected}')
        expected_markers=sum(len(items) for items in d.section['markers'].values())
        if d.count['markers']!=expected_markers:raise SplitError(f'{d.id}: marker count differs')
        for source,count in d.section['spawnRows'].items():
            if d.count['spawns:'+source]!=count:raise SplitError(f'{d.id}: spawn row count differs for {source}')
        if d.count['grounds']>127:raise SplitError('ground cap exceeded')
        outputs[f'{REGION_ROOT}/{d.id}/{d.id}.tscn']=d.bytes()
        path=f'{REGION_ROOT}/{d.id}/region-authoring-spec.json'
        authoring=json.loads(base.read(path))
        live=Path(checkout)/path
        if live.exists():
            existing=json.loads(live.read_text(encoding='utf-8'))
            if existing.get('gameplay',{}).get('generatedArrival'):
                authoring['gameplay']['generatedArrival']=copy.deepcopy(existing['gameplay']['generatedArrival'])
        arrival_relative=f'eloria-assets/maps/continent-v2/{d.id}/content/arrival.json'
        arrival=Path(checkout)/arrival_relative
        if arrival.exists():
            authoring['gameplay']['generatedArrival']={'path':arrival_relative,'sha256':F.sha256(arrival.read_bytes())}
        authoring['gameplay'].update({'authoredMarkerCount':d.count['markers'],'runtimePointCount':d.count['markers:runtime_point'],'runtimeBindingCount':0,'existingMarkerBindingCount':0})
        outputs[path]=jbytes(authoring)
        content={'schema':'eloria-continent-v2-spawns-v1','map':d.id,'about':'Pinned original spawn rows, partitioned by exact continent position. local remains the source of truth.','source':{'sourceCommit':reader.commit,'originalSources':spawn_sources[d.id]},'spawns':per_spawns[d.id]}
        outputs[f'eloria-assets/maps/continent-v2/{d.id}/content/spawns.json']=jbytes(content)
    totals=Counter()
    for d in destinations:totals.update(d.count)
    if totals['placements']!=17401 or totals['markers']!=254 or spawn_total!=1027 or totals['grounds']!=253:raise SplitError('global source conservation count differs')
    proof={'schema':SCHEMA,'sourceCommit':reader.commit,'skeletonCommit':base.commit,'partitionSha256':F.sha256(base.read(PARTITION)),'entries':rename_entries,'roadPieces':road_report,'conservation':{'placements':17401,'markers':254,'spawnRows':1027,'groundRecords':253,'maxPlacementMatrixErrorMetres':transform_max,'perMap':{d.id:dict(d.count) for d in destinations},'accountedSourceNodes':{s.id:len(s.account) for s in sources}},'sourceFiles':{p:F.sha256(raw) for p,raw in sorted(reader.files.items())}}
    outputs[RENAMES]=jbytes(proof)
    return outputs,proof

def verify_outputs(outputs,root):
    for relative,raw in outputs.items():
        path=Path(root)/relative
        if not path.is_file() or path.read_bytes()!=raw:
            raise SplitError('stale or corrupt split output: '+relative)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-ref',default=SOURCE_REF);parser.add_argument('--skeleton-ref',default=SKELETON_REF)
    parser.add_argument('--output-root',type=Path,default=CHECKOUT);parser.add_argument('--regions',nargs='+');parser.add_argument('--omit-rename-map',action='store_true');parser.add_argument('--check',action='store_true');parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    try:
        outputs,proof=build(source_ref=args.source_ref,skeleton_ref=args.skeleton_ref)
        if args.regions:
            allowed=set(proof['conservation']['perMap'])
            if not set(args.regions)<=allowed:raise SplitError('unknown pilot region')
            outputs={p:raw for p,raw in outputs.items() if p==RENAMES or any('/'+r+'/' in p for r in args.regions)}
        if args.omit_rename_map:outputs.pop(RENAMES,None)
        if args.check:verify_outputs(outputs,args.output_root)
        else:
            for relative,raw in outputs.items():
                path=args.output_root/relative
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        if args.report:args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_bytes(jbytes(proof))
        print(json.dumps({'outputs':len(outputs),'checked':args.check,'conservation':proof['conservation']},indent=1))
    except (SplitError,F.FreezeError,ValueError) as error:parser.exit(1,str(error)+'\n')
if __name__=='__main__':main()
