"""Compress travel space while retaining a protected settlement at human scale.

Axis knots are authored geographic decisions, not a runtime coordinate transform.
Exported geometry, surveys and server coordinates all use ordinary metres.
"""
from copy import deepcopy
import numpy as np
from amberwood import mesh as M, terrain as TER


class Axis:
    def __init__(self, old_min, old_max, new_min, new_max, protected):
        a,b=protected
        slope=((new_max-new_min)-(b-a))/((old_max-old_min)-(b-a))
        self.old=np.array([old_min,a,b,old_max],float)
        self.new=np.array([new_min,new_min+(a-old_min)*slope,
                           new_min+(a-old_min)*slope+b-a,new_max],float)

    @staticmethod
    def interpolate(values, source, target):
        values=np.asarray(values,dtype=float)
        i=np.clip(np.searchsorted(source,values,side='right')-1,0,len(source)-2)
        return target[i]+(values-source[i])*(target[i+1]-target[i])/(source[i+1]-source[i])

    def __call__(self,v):return self.interpolate(v,self.old,self.new)
    def inverse(self,v):return self.interpolate(v,self.new,self.old)


class CompactLandscape:
    def __init__(self,x,z,old_origin,new_origin):
        self.x,self.z=x,z
        self.old_origin,self.new_origin=old_origin,new_origin

    def point(self,p):
        return [round(float(self.x(p[0])),4),p[1],round(float(self.z(p[2])),4)]

    def tile(self,p):
        x,z=p[0]-self.old_origin[0],self.old_origin[1]-p[1]
        return [int(round(float(self.x(x))+self.new_origin[0])),
                int(round(self.new_origin[1]-float(self.z(z))))]

    def metadata(self,value):
        if isinstance(value,list):return [self.metadata(v) for v in value]
        if not isinstance(value,dict):return value
        out={k:self.metadata(v) for k,v in value.items()}
        for k in ('position','centre','center','start','end','bankA','bankB'):
            p=value.get(k)
            if isinstance(p,(tuple,list)) and len(p)==3 and isinstance(p[0],(int,float)):
                out[k]=self.point(p)
        for k in ('positions','waypoints','endpoints'):
            if k in value:out[k]=[self.point(p) for p in value[k]]
        if 'serverTile' in value:out['serverTile']=self.tile(value['serverTile'])
        return out

    def mesh(self,piece):
        for part in getattr(piece,'all_parts',[piece]):
            if not part.vertex_count:continue
            old=part.positions.copy()
            dx=(self.x(old[:,0]+.01)-self.x(old[:,0]-.01))/.02
            dz=(self.z(old[:,2]+.01)-self.z(old[:,2]-.01))/.02
            part.positions[:,0]=self.x(old[:,0]);part.positions[:,2]=self.z(old[:,2])
            part.normals[:,0]/=dx;part.normals[:,2]/=dz
            part.sanitise_normals()
        return piece

    def apply(self,build):
        old=build.terrain
        t=TER.Terrain(float(self.x(old.x0)),float(self.z(old.z0)),
                      float(self.x(old.xs[-1])-self.x(old.x0)),
                      float(self.z(old.zs[-1])-self.z(old.z0)),cell=1.0)
        ox,oz=self.x.inverse(t.gx),self.z.inverse(t.gz)
        t.height=old.height_at(ox,oz)
        t.surface=old.surface_at(ox,oz)
        build.terrain=t
        for bucket in (build.terrain_meshes,build.water_meshes):
            for piece in bucket.values():self.mesh(piece)
        for p in build.placements:
            # Decks, bridges and monumental stairs follow the bank survey.
            # Houses, trees, furniture and their door heights retain their scale.
            if p.walk_surface and p.kind!='building':
                item=deepcopy(build.meshes[p.mesh])
                matrix=M.translation(*p.position)@M.rotation_y(p.rotation_y)@M.scaling(p.scale)
                item.transform(matrix)
                self.mesh(item)
                position=self.point(p.position)
                item.translate(*[-v for v in position])
                key=p.mesh+'__compact__'+p.node
                build.meshes[key]=item
                p.mesh=key;p.position=tuple(position);p.scale=1;p.rotation_y=0
            else:p.position=tuple(self.point(p.position))
        for name in ('landmarks','interactives','npc_markers','harvestables','portals','spawns','crossings'):
            setattr(build,name,self.metadata(getattr(build,name)))
        used={p.mesh for p in build.placements}
        build.meshes={k:v for k,v in build.meshes.items() if k in used}
