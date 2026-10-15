"""Adapt prepared coastal claims to the shared bridge export contracts."""
from __future__ import annotations

import re
from types import SimpleNamespace

import numpy as np
import shapely as SH
from shapely.geometry import Polygon,box

from amberwood import mesh as M


def _encoded_faces(value,label):
    faces=np.asarray(value,float)
    if faces.ndim!=3 or faces.shape[1:]!=(3,3) or not len(faces):
        raise ValueError(f'{label} has no encoded triangles')
    if not np.isfinite(faces).all() or not np.array_equal(faces,faces.astype(np.float32).astype(float)):
        raise ValueError(f'{label} is not finite float32 geometry')
    normal=np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0])
    if np.any(normal[:,1]<=0):raise ValueError(f'{label} has a non-upward floor triangle')
    return faces


def _mesh(faces,material='bridge_timber'):
    faces=np.asarray(faces,float);positions=faces.reshape(-1,3).copy()
    mesh=M.Mesh(positions=positions,normals=np.tile([0.,1.,0.],(len(positions),1)),
                uvs=positions[:,[0,2]]*.25,indices=np.arange(len(positions)),material=material)
    mesh.recompute_normals(180)
    return mesh


def _footprint_cells(field,faces):
    mask=np.zeros_like(field['mask'],bool);x0=float(field['x0']);z0=float(field['z0'])
    cell=float(field['cell'])
    if not np.isfinite(cell) or cell<=0.:raise ValueError('bridge field cell size is invalid')
    rows,cols=mask.shape
    for face in faces:
        polygon=Polygon(face[:,[0,2]])
        low=np.floor((np.asarray(polygon.bounds[:2])-[x0,z0])/cell).astype(int)
        high=np.ceil((np.asarray(polygon.bounds[2:])-[x0,z0])/cell).astype(int)
        for col in range(max(0,low[0]),min(cols,high[0])):
            for row in range(max(0,low[1]),min(rows,high[1])):
                if polygon.intersection(box(x0+col*cell,z0+row*cell,
                                            x0+(col+1)*cell,z0+(row+1)*cell)).area>0.:
                    mask[row,col]=True
    return mask


def _component(world,field,claim):
    faces=_encoded_faces(claim.encoded_floor_triangles,f'coastal claim {claim.claim_id}')
    gap,_=_join_metrics(claim)
    full=_footprint_cells(field,faces);rows,cols=np.nonzero(full)
    if not len(rows):raise ValueError(f'coastal claim {claim.claim_id} has no bridge cells')
    sl=(slice(int(rows.min()),int(rows.max())+1),slice(int(cols.min()),int(cols.max())+1))
    local=full[sl];owners=np.asarray(world.owner_at(faces[:,:,0].mean(1),faces[:,:,2].mean(1)),int)
    mesh=_mesh(faces)
    return {'id':claim.claim_id,'coastalRecordId':claim.claim_id,'sites':[],'slice':sl,'cells':local,
            'water':np.zeros_like(local),
            'bankError':gap,'arch':{'prepared':True},'outline':field['outline'],
            '_preparedMeshCache':(mesh,owners),'claim':claim},full


def _join_metrics(claim):
    joins=claim.evidence.get('fullWidthJoins')
    if not isinstance(joins,dict) or joins.get('acceptanceAuthority') is not True or joins.get('clear') is not True:
        raise ValueError(f'coastal claim {claim.claim_id} lacks accepted full-width join evidence')
    gap=float(joins.get('maximumGapMetres',np.nan))
    if not np.isfinite(gap) or gap<0.:raise ValueError(f'coastal claim {claim.claim_id} has no valid join gap')
    worst=joins.get('worstBankXZ')
    if worst is not None:
        worst=tuple(map(float,worst))
        if len(worst)!=2 or not np.isfinite(worst).all():
            raise ValueError(f'coastal claim {claim.claim_id} has an invalid worst bank point')
    return gap,worst


def _plain_json(value):
    if isinstance(value,np.ndarray):return _plain_json(value.tolist())
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,dict):return {str(key):_plain_json(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):return [_plain_json(item) for item in value]
    return value


def _coastal_deck_report(claim,component):
    gap,worst=_join_metrics(claim)
    return {'component':claim.claim_id,'recordId':claim.claim_id,'sites':[],
            'roadIds':tuple(claim.road_ids),'cells':int(component['cells'].sum()),
            'wetCells':len(claim.loose_wet_cells),'encodedFloorTriangles':len(claim.encoded_floor_triangles),
            'wetExtentMetres':tuple(claim.wet_extent_metres),
            'joinStationsMetres':tuple(claim.join_stations_metres),
            'surfaceNames':tuple(surface.name for surface in claim.surfaces),
            'stairs':len(claim.stairs),'supports':len(claim.supports),
            'bankErrorMetres':gap,'worstBank':worst,
            'preparedEvidence':_plain_json(claim.evidence)}


def _floor_union(mesh):
    faces=np.asarray(mesh.positions[mesh.indices.reshape(-1,3)],float)
    return SH.union_all([Polygon(face[:,[0,2]]) for face in faces])


def build_selected_inventory(inventory,records):
    """Freeze the exact selected/fallback partition of the current loose mask."""
    authority=tuple(map(int,inventory.get('looseWetCellIndices',())))
    if authority!=tuple(sorted(set(authority))):
        raise ValueError('current loose wet-cell authority is missing, duplicate, or unsorted')
    records=tuple(records);ids=[claim.claim_id for claim in records]
    if not records or len(ids)!=len(set(ids)):
        raise ValueError('selected coastal claim ids are empty or not unique')
    owned=set();prepared=[]
    for claim in records:
        cells=getattr(claim,'loose_wet_cells',None)
        if not isinstance(cells,tuple) or cells!=tuple(sorted(set(cells))) or any(
                not isinstance(cell,(int,np.integer)) or cell<0 for cell in cells):
            raise ValueError('prepared coastal loose_wet_cells is not a sorted unique nonnegative tuple')
        overlap=owned.intersection(cells)
        if overlap:raise ValueError(f'prepared coastal wet-cell ownership overlaps: {sorted(overlap)}')
        owned.update(map(int,cells))
        prepared.append({'claimId':str(claim.claim_id),'roadIds':tuple(map(str,claim.road_ids)),
                         'looseWetCells':tuple(map(int,cells))})
    extra=sorted(owned-set(authority))
    if extra:raise ValueError(f'prepared coastal wet-cell ownership is outside current loose mask: {extra}')
    fallback=tuple(sorted(set(authority)-owned))
    return {'schema':1,'mode':'selected-with-legacy-fallback',
            'authorityLooseWetCellIndices':authority,'prepared':tuple(prepared),
            'fallbackLooseWetCellIndices':fallback}


def _selected_inventory(world,authority):
    registry=getattr(world,'claimed_coastal_inventory',None)
    if not isinstance(registry,dict) or registry.get('schema')!=1 or \
            registry.get('mode')!='selected-with-legacy-fallback':
        raise ValueError('selected coastal inventory registry is missing or invalid')
    records=tuple(getattr(world,'claimed_coastal_records',()))
    expected=build_selected_inventory({'looseWetCellIndices':tuple(map(int,authority))},records)
    if registry!=expected:raise ValueError('selected coastal inventory registry is stale')
    owned=tuple(cell for row in expected['prepared'] for cell in row['looseWetCells'])
    return records,tuple(sorted(owned)),expected['fallbackLooseWetCellIndices']


def prepared_footprint_mask(world,authority,shape,x0,z0,cell):
    """Return the exact prepared-floor cell mask after registry validation."""
    records,owned,fallback=_selected_inventory(world,authority)
    field={'mask':np.zeros(tuple(shape),bool),'x0':float(x0),'z0':float(z0),'cell':float(cell)}
    result=np.zeros(tuple(shape),bool)
    for claim in records:result|=_footprint_cells(field,_encoded_faces(
        claim.encoded_floor_triangles,f'coastal claim {claim.claim_id}'))
    return result,owned,fallback


def replace_legacy_loose_components(world,field):
    """Append selected prepared claims while retaining every legacy fallback floor."""
    authority=tuple(int(cell) for cell in field.get('looseWetCellIndices',()))
    records,owned,fallback=_selected_inventory(world,authority)
    if tuple(field.get('preparedLooseWetCellIndices',()))!=owned or \
            tuple(field.get('legacyLooseWetCellIndices',()))!=fallback:
        raise ValueError('bridge field selected/fallback coastal partition is stale')
    prepared=[];prepared_masks=[];loose_mask=np.zeros_like(field['mask'],bool)
    for claim in records:
        component,mask=_component(world,field,claim);prepared.append(component);prepared_masks.append(mask);loose_mask|=mask
    for first in range(len(prepared)):
        for second in range(first+1,len(prepared)):
            if not np.any(prepared_masks[first]&prepared_masks[second]):continue
            first_mesh,_=prepared[first]['_preparedMeshCache'];second_mesh,_=prepared[second]['_preparedMeshCache']
            if _floor_union(first_mesh).intersection(_floor_union(second_mesh)).area>0.:
                raise ValueError('selected prepared coastal floors have positive overlap')
    retained=list(field['components'])
    claimed=[component for component in retained if component.get('sites')]
    if any(not component.get('arch',{}).get('prepared',False) for component in claimed):
        raise ValueError('coastal replacement requires every claimed bridge to be prepared')
    retained_mask=np.asarray(field['mask'],bool).copy()
    if np.any(retained_mask&loose_mask):
        from bridge_export import deck_mesh
        for legacy in retained:
            legacy_mask=np.zeros_like(field['mask'],bool);legacy_mask[legacy['slice']]|=legacy['cells']
            for coast,coast_mask in zip(prepared,prepared_masks):
                if not np.any(legacy_mask&coast_mask):continue
                legacy_mesh,_=deck_mesh(world,legacy);coast_mesh,_=coast['_preparedMeshCache']
                if _floor_union(legacy_mesh).intersection(_floor_union(coast_mesh)).area>0.:
                    raise ValueError('prepared coastal floor has positive overlap with a retained bridge floor')
    result=dict(field);result['components']=retained+prepared;result['mask']=retained_mask|loose_mask
    result['looseWetCells']=len(authority);result['preparedLooseWetCells']=len(owned)
    result['legacyLooseWetCells']=len(fallback)
    result['decks']=list(field.get('decks',()))+[_coastal_deck_report(claim,component)
                                                for claim,component in zip(records,prepared)]
    retained_error=float(field.get('maximumBankError',0.));retained_worst=field.get('worstBank')
    prepared_worst=max(prepared,key=lambda component:float(component['bankError']),default=None)
    prepared_error=float(prepared_worst['bankError']) if prepared_worst is not None else 0.
    if prepared_error>retained_error:
        result['maximumBankError']=prepared_error
        result['worstBank']=_join_metrics(prepared_worst['claim'])[1]
    else:
        result['maximumBankError']=retained_error;result['worstBank']=retained_worst
    return result


def component_token(component):
    """Stable node-name token; never derives identity from transient component numbers."""
    value=component.get('coastalRecordId',component['id'])
    if isinstance(value,(int,np.integer)):return f'{int(value):03d}'
    value=str(value)
    token=re.sub(r'[^A-Za-z0-9_-]+','-',value).strip('-')
    if not token:raise ValueError('bridge component has no stable node token')
    return token


def coastal_auxiliary_parts(world):
    """Return separately colliding riser/support meshes partitioned by territory."""
    parts=[]
    for claim in tuple(getattr(world,'claimed_coastal_records',())):
        groups=[]
        for index,stair in enumerate(claim.stairs):
            if len(stair.riser_triangles):
                groups.append((f'Riser_{index:02d}',stair.riser_triangles,'bridge_edge_timber'))
        supports={support.name:support for support in claim.supports}
        for stair in claim.stairs:
            supports.update((support.name,support) for support in stair.supports)
        groups.extend((f'Support_{name}',support.encoded_triangles,'bridge_edge_timber')
                      for name,support in sorted(supports.items()))
        for suffix,triangles,material in groups:
            faces=np.asarray(triangles,float).astype(np.float32).astype(float)
            if not len(faces):continue
            owners=np.asarray(world.owner_at(faces[:,:,0].mean(1),faces[:,:,2].mean(1)),int)
            for owner in np.unique(owners):
                selected=faces[owners==owner];region=world.ids[int(owner)]
                parts.append({'region':region,'name':f'BridgeCoastal_{component_token({"id":claim.claim_id})}_{suffix}_{region}',
                              'mesh':_mesh(selected,material),'collides':True,'recordId':claim.claim_id})
    return parts
