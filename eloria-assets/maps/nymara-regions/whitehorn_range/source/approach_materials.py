"""Expose the actual steep White bank faces as bedrock, retaining their skin."""
import numpy as np
from scipy.interpolate import RegularGridInterpolator
import connector_finish as F
import approach_landform as W

def apply(build,before):
    bases={n:m for n,m in build.terrain_meshes.items() if F._base(n) and m.triangle_count}
    after=F.VerticalRayIndex(F._triangles(list(bases.values())))
    roads=[r for r in build.geography_roads if r['id'] in W.ROAD_IDS]
    xs=np.arange(-195.,81.,1.);zs=np.arange(10.,146.,1.)
    x,z=np.meshgrid(xs,zs);p=np.c_[x.ravel(),z.ravel()]
    a=np.array([after.top_hit(*q) for q in p],object);b=np.array([before.top_hit(*q) for q in p],object)
    present=np.array([v is not None and k is not None for v,k in zip(a,b)])
    heights=np.array([float(v) if v is not None else 0. for v in a]);old=np.array([float(v) if v is not None else 0. for v in b])
    dz,dx=np.gradient(heights.reshape(x.shape))
    grade=np.hypot(dx,dz).ravel()
    mask=np.minimum.reduce([grade-.75,abs(heights-old)-.3,W._distance(p,roads)-5.75,
                            F.R._edge_distance(build,W.REGION,p)-8.,p[:,1]-20.,70.-W._distance(p,roads)])
    mask[~present]=-1.
    sample=RegularGridInterpolator((zs,xs),mask.reshape(x.shape),bounds_error=False,fill_value=-1.)
    added={};area=0.;faces=0
    for name,mesh in bases.items():
        value=sample(mesh.positions[:,[2,0]])
        if np.max(value)<=0:continue
        # Reassign existing complete faces. Extra physical cuts here could
        # create submillimetre triangles below the collision ray's area
        # threshold, although the visible union remained mathematically
        # unchanged. Material-only partition retains the exact actual skin.
        original_faces=mesh.indices.reshape(-1,3)
        selected=value[original_faces].mean(axis=1)>0.
        rock=mesh.copy();rock.indices=original_faces[selected].ravel()
        keep=mesh.copy();keep.indices=original_faces[~selected].ravel()
        if not rock.triangle_count:continue
        rock.material='alpine_bedrock_ground'
        # Per-face projections avoid stretching a leaf/ground texture down
        # a cliff, and avoid seams caused by mixed per-vertex dominant axes.
        indices=rock.indices.reshape(-1,3);tri=rock.positions[indices]
        normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);axis=np.argmax(abs(normal),axis=1)
        positions=tri.reshape(-1,3);uv=np.empty((len(tri),3,2))
        for i,axes in enumerate(((2,1),(0,2),(0,1))):uv[axis==i]=tri[axis==i][:,:,axes]
        rock.positions=positions;rock.uvs=uv.reshape(-1,2)*.28
        rock.normals=rock.normals[indices].reshape(-1,3)
        if rock.colors is not None:rock.colors=rock.colors[indices].reshape(-1,4)
        rock.indices=np.arange(len(positions));rock.recompute_normals(180)
        build.terrain_meshes[name]=keep
        new_name=name+'_WhiteApproachBedrock';added[new_name]=rock
        for frame in build.streaming_borders:
            if name in frame.get('sceneNodes',[]) and new_name not in frame['sceneNodes']:frame['sceneNodes'].append(new_name)
        area+=float(np.linalg.norm(normal,axis=1).sum()*.5);faces+=len(tri)
    for name,mesh in list(build.terrain_meshes.items()):
        if mesh.triangle_count and name.startswith('Terrain_') and ('_StreamCollar_' in name or '_ContinentBlend_' in name):
            build.terrain_meshes[name]=F.R._clip_scalar(mesh,sample(mesh.positions[:,[2,0]]))
    build.terrain_meshes.update(added)
    return {'bedrockFacePieces':faces,'surfaceSquareMetres':area,'newNodes':list(added),'walkingAndWaterUnchanged':True}
