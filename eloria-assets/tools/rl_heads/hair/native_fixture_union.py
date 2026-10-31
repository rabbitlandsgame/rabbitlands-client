"""Conservative union of complete, hash-verified evaluated Native Rest surfaces.

This is authoring support, not the independent control/pose qualification gate.
It intentionally has no mesh/radial API: nearest distances are evaluated on each
complete fixture so detached patches cannot invent inside/outside signs.
"""
from pathlib import Path
import json
import numpy as np
import trimesh
import headref
from native_hair_fixtures import load_fixture,EvaluatedNativeSurface


class NativeFixtureUnion:
    def __init__(self,manifest,sex,case_names=None,optimize=True,horizontal_slice_proof=False):
        assert not horizontal_slice_proof or not optimize,'Horizontal slice proof currently requires optimize=False'
        self.horizontal_slice_proof=bool(horizontal_slice_proof)
        data=json.loads(Path(manifest).read_text())
        assert data.get('hair_identity_policy')=='native_fixed_skull','Use evaluated fixturev2 or later with zero High hair IDs'
        seen=set();self.surfaces=[];self.records=[]
        for record in data['cases']:
            if record['sex']!=sex or record['clip']!='Rest_Pose' or record['fraction']!=0:continue
            if case_names is not None and record['case'] not in case_names:continue
            assert not record['rl_hair_identity_controls'],'Native skull fitting must use zero High identity targets'
            signature=tuple(sorted((part['mesh'],part['sha256']) for part in record['parts'] if part['mesh'] in ['body','scalp','wardrobe_shirt']))
            if signature in seen:continue
            seen.add(signature)
            surface=load_fixture(manifest,record,horizontal_slice_proof=True) if self.horizontal_slice_proof else load_fixture(manifest,record)
            self.surfaces.append(surface)
            self.records.append({'case':record['case'],'quality':record['quality']})
        assert self.surfaces,'No matching evaluated Native Rest surfaces'
        self.optimize=bool(optimize);self._plans=None;self.last_query_stats={}
    def _prepare(self):
        base=self.surfaces[0];self._plans=[]
        for surface in self.surfaces[1:]:
            compatible=(type(base) is EvaluatedNativeSurface and type(surface) is EvaluatedNativeSurface
                and base.P.shape==surface.P.shape and np.array_equal(base.T,surface.T))
            if not compatible:self._plans.append(False);continue
            changed=np.any(base.P!=surface.P,axis=1)
            faces=changed[base.T].any(1)
            if not faces.any():self._plans.append(None);continue
            used=np.unique(base.T[faces]);points=np.vstack([base.P[used],surface.P[used]])
            self._plans.append(np.stack([points.min(0),points.max(0)]))

    @staticmethod
    def _candidate(points,unsigned,bounds):
        if bounds is False:return np.ones(len(points),bool)
        if bounds is None:return np.zeros(len(points),bool)
        separation=np.maximum(np.maximum(bounds[0]-points,points-bounds[1]),0)
        # Include the uncertainty band rather than pruning equality/touching.
        return np.linalg.norm(separation,axis=1)<=unsigned+1e-9

    def _frame(self,points,base_result,need_tie_guard):
        base=self.surfaces[0]
        chunks=[trimesh.proximity.closest_point(base.mesh,points[start:start+512]) for start in range(0,len(points),512)]
        cp,distance,triangle=(np.concatenate([row[index] for row in chunks],axis=0) for index in range(3))
        tv=base.T[triangle]
        bc=headref.barycentric(base_result[1],base.P[tv[:,0]],base.P[tv[:,1]],base.P[tv[:,2]])
        normal=headref.unit((base.N[tv]*bc[:,:,None]).sum(1))
        consistent=((cp==base_result[1]).all(1)&(distance==np.abs(base_result[0]))&(normal==base_result[2]).all(1))
        ambiguous=~consistent
        # A changed remote triangle can reorder nearest-distance ties. Do not
        # reuse an ambiguous witness on a geometry-changing fixture.
        ambiguous|=need_tie_guard&(bc.min(1)<=1e-10)
        tree=base.mesh.triangles_tree;triangles=base.mesh.triangles
        ids_to_check=np.flatnonzero(need_tie_guard&~ambiguous)
        # Prove a unique nearest triangle, including equal-distance witnesses
        # with different closest points (not only shared-edge/UV-seam ties).
        # Batch the bounded triangle search in C where supported.
        for start in range(0,len(ids_to_check),512):
            rows=ids_to_check[start:start+512];query_rows=points[rows];epsilon=1e-9
            radius=np.abs(base_result[0][rows])+epsilon
            lower=query_rows-radius[:,None];upper=query_rows+radius[:,None]
            if hasattr(tree,'intersection_v'):
                try:
                    ids,counts=tree.intersection_v(np.ascontiguousarray(lower),np.ascontiguousarray(upper))
                    owners=np.repeat(np.arange(len(rows)),counts.astype(int))
                    if len(ids):
                        nearest=trimesh.triangles.closest_point(triangles[ids.astype(int)],query_rows[owners])
                        finite=np.isfinite(nearest).all(1)
                        matching=finite&(np.abs(np.linalg.norm(nearest-query_rows[owners],axis=1)-np.abs(base_result[0][rows])[owners])<=epsilon)
                        hits=np.bincount(owners,weights=matching,minlength=len(rows))
                        invalid=np.bincount(owners,weights=~finite,minlength=len(rows))>0
                        ambiguous[rows]|=(hits!=1)|invalid
                    else:ambiguous[rows]=True
                    continue
                except (TypeError,ValueError):
                    # Older rtree/numpy combinations lack a usable bulk API.
                    pass
            for at in rows:
                point=points[at];radius=abs(base_result[0][at])+epsilon
                candidates=list(tree.intersection(np.r_[point-radius,point+radius]))
                if not candidates:ambiguous[at]=True;continue
                nearest=trimesh.triangles.closest_point(triangles[candidates],np.repeat(point[None],len(candidates),0))
                if not np.isfinite(nearest).all() or (np.abs(np.linalg.norm(nearest-point,axis=1)-abs(base_result[0][at]))<=epsilon).sum()!=1:ambiguous[at]=True
        return {'base':base_result,'tv':tv,'bc':bc,'consistent':consistent,'ambiguous':ambiguous}

    def _query_fixture(self,surface,plan,points,frame):
        base=frame['base'];unsigned=np.abs(base[0])
        query=self._candidate(points,unsigned,plan)|~frame['consistent']
        if plan is not None and plan is not False:query|=frame['ambiguous']
        distance=np.empty(len(points));closest=np.array(base[1],copy=True);normal=np.empty_like(base[2]);reuse=~query
        if reuse.any():
            # Geometry is unchanged at this unique closest triangle. Normals
            # may change anywhere: reconstruct them from this fixture's own N,
            # then reconstruct its raw sign before its outside-bounds proof.
            tv=frame['tv'][reuse];bc=frame['bc'][reuse]
            normal[reuse]=headref.unit((surface.N[tv]*bc[:,:,None]).sum(1))
            raw=np.sign(((points[reuse]-closest[reuse])*normal[reuse]).sum(1));raw[raw==0]=1
            distance[reuse]=unsigned[reuse]*raw
            bounds=surface.mesh.bounds
            if ((bounds[1]-bounds[0])>1e-6).all():
                outside=((points[reuse]<bounds[0]-1e-9)|(points[reuse]>bounds[1]+1e-9)).any(1)
                indices=np.flatnonzero(reuse)[outside];distance[indices]=unsigned[indices]
        if query.any():
            d,q,n=surface.signed(points[query]);distance[query]=d;closest[query]=q;normal[query]=n
        return (distance,closest,normal),int(query.sum())

    def signed(self,P,optimize=None):
        points=np.asarray(P,float)
        if not len(points):return np.empty(0),np.empty((0,3)),np.empty((0,3))
        enabled=self.optimize if optimize is None else bool(optimize)
        assert not getattr(self,'horizontal_slice_proof',False) or not enabled,'Horizontal slice proof currently requires optimize=False'
        base=self.surfaces[0].signed(points)
        distance,point,normal=(np.array(array,copy=True) for array in base)
        total=len(points)*len(self.surfaces);actual=len(points);frame=None
        if enabled and len(self.surfaces)>1:
            if self._plans is None:self._prepare()
            possible=np.zeros(len(points),bool);potential=0
            for plan in self._plans:
                reuse=~self._candidate(points,np.abs(base[0]),plan);potential+=int(reuse.sum())
                if plan is not None and plan is not False:possible|=reuse
            # A second baseline witness query costs n points. Skip all extra
            # machinery when conservative boxes cannot save even that much.
            if potential>=len(points):
                frame=self._frame(points,base,possible);actual+=len(points)
        for index,surface in enumerate(self.surfaces[1:]):
            if frame is None:result=surface.signed(points);queried=len(points)
            else:result,queried=self._query_fixture(surface,self._plans[index],points,frame)
            d,q,n=result;actual+=queried;take=d<distance
            distance[take]=d[take];point[take]=q[take];normal[take]=n[take]
        self.last_query_stats={'full_query_points':total,'actual_closest_query_points':actual,
            'avoided_query_points':total-actual,'baseline_witness_requery':frame is not None,
            'ambiguous_baseline_points':int(frame['ambiguous'].sum()) if frame is not None else 0}
        return distance,point,normal
