"""Offline mount-only fit of an existing imported Meshy Dock Rat.

The neutral source is preserved; this explicitly replaces its rejected legacy
automatic skeleton. No creature definitions or existing animations are changed.
Run with Python + NumPy. All three loops are in place and use Y up / +Z forward.
"""
from pathlib import Path
import copy, hashlib, json, math, struct
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = HERE / 'giant_rat_neutral.glb'
OUTPUT = ROOT / 'godot-client/assets/actors/native/mounts/giant_rat.glb'

def read_glb(path):
    data = path.read_bytes()
    n = struct.unpack_from('<I', data, 12)[0]
    return json.loads(data[20:20+n]), bytearray(data[28+n:])

def accessor(doc, blob, index):
    a = doc['accessors'][index]; v = doc['bufferViews'][a['bufferView']]
    types = {5121:'u1', 5123:'<u2', 5125:'<u4', 5126:'<f4'}
    widths = {'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}
    return np.frombuffer(blob, dtype=types[a['componentType']],
        count=a['count']*widths[a['type']], offset=v.get('byteOffset',0)+a.get('byteOffset',0)).reshape(a['count'],-1).copy()

def append(doc, blob, values, kind, component=5126, target=None):
    dtype = {5126:'<f4',5123:'<u2',5125:'<u4'}[component]
    values = np.asarray(values,dtype=dtype)
    blob.extend(b'\0' * (-len(blob)%4)); start=len(blob); blob.extend(values.tobytes())
    view={'buffer':0,'byteOffset':start,'byteLength':values.nbytes}
    if target is not None: view['target']=target
    doc['bufferViews'].append(view)
    a={'bufferView':len(doc['bufferViews'])-1,'componentType':component,'count':len(values),'type':kind}
    if component==5126:
        a['min']=values.min(axis=0).reshape(-1).tolist(); a['max']=values.max(axis=0).reshape(-1).tolist()
    doc['accessors'].append(a); return len(doc['accessors'])-1

def qmul(a,b):
    av=np.asarray(a[:3]);bv=np.asarray(b[:3]);return np.r_[a[3]*bv+b[3]*av+np.cross(av,bv),a[3]*b[3]-np.dot(av,bv)]

def qinv(q): return np.r_[-np.asarray(q[:3]),q[3]]

def align(a,b):
    a=np.asarray(a,dtype=float);b=np.asarray(b,dtype=float)
    a/=np.linalg.norm(a);b/=np.linalg.norm(b)
    q=np.r_[np.cross(a,b),1+np.dot(a,b)]
    if np.linalg.norm(q)<1e-8: q=np.array([1.,0,0,0])
    return q/np.linalg.norm(q)

def axisq(axis, angle): return np.r_[np.asarray(axis)*math.sin(angle/2),math.cos(angle/2)]

def smooth(a,b,x):
    v=np.clip((x-a)/(b-a),0,1);return v*v*(3-2*v)

def segment_distance(points,a,b):
    t=np.clip(((points-a)@(b-a))/np.dot(b-a,b-a),0,1)
    return np.linalg.norm(points-(a+t[:,None]*(b-a)),axis=1),t

def main():
    doc,blob=read_glb(SOURCE)
    primitives=doc['meshes'][0]['primitives']
    source_points=np.concatenate([accessor(doc,blob,p['attributes']['POSITION']) for p in primitives])
    # Exported surfaces, rather than armature/orphan bounds, set the real floor.
    floor=float(source_points[:,1].min()); scale=1.45/(float(source_points[:,1].max())-floor)
    offset=np.array([.18,floor,0])
    names=[];parents=[];positions=[]
    def bone(name,parent,point):
        names.append(name);parents.append(parent);positions.append(np.array(point,dtype=float));return len(names)-1
    root=bone('root',-1,[0,0,0])
    hips=bone('hips',root,[0,.78,-.38])
    spine=bone('spine',hips,[0,.86,.27])
    head=bone('head',spine,[-.04,.91,.88])
    legs=[]
    for end in ['front','hind']:
        for side,sign in [('l',1),('r',-1)]:
            if end=='front': a=[sign*.36,.70,.50];b=[sign*.37,.38,.39];c=[sign*.37,.095,.83];parent=spine
            else: a=[sign*.50,.60,-.58];b=[sign*.51,.28,-.70];c=[sign*.49,.095,-.24];parent=hips
            u=bone(end+'_'+side+'_upper',parent,a);k=bone(end+'_'+side+'_lower',u,b);f=bone(end+'_'+side+'_paw',k,c)
            legs.append({'end':end,'side':side,'sign':sign,'ids':[u,k,f]})
    tail_points=np.array([[.10,.45,-1.19],[-.43,.17,-1.29],[-.95,.09,-1.06],[-1.20,.075,-.57],[-1.13,.07,-.03],[-1.11,.07,.43],[-1.17,.07,.72]])
    tail=[]; parent=hips
    for i,point in enumerate(tail_points): parent=bone('tail_%02d'%(i+1),parent,point);tail.append(parent)
    positions=np.array(positions)
    nodes=[]
    for i,name in enumerate(names):
        local=positions[i]-(positions[parents[i]] if parents[i]>=0 else 0)
        nodes.append({'name':name,'translation':local.tolist(),'children':[]})
        if parents[i]>=0: nodes[parents[i]]['children'].append(i)
    for n in nodes:
        if not n['children']: n.pop('children')
    mesh_node=len(nodes);nodes.append({'name':'GiantRat','mesh':0,'skin':0});nodes[0]['children'].append(mesh_node)
    doc['nodes']=nodes;doc['scenes']=[{'nodes':[0]}];doc['scene']=0
    binds=np.repeat(np.eye(4)[None],len(names),axis=0);binds[:,:3,3]=-positions
    bind_accessor=append(doc,blob,binds.transpose(0,2,1).reshape(-1,16),'MAT4')
    doc['skins']=[{'name':'GiantRatMountRig','joints':list(range(len(names))),'skeleton':0,'inverseBindMatrices':bind_accessor}]
    sole_witnesses={}
    for primitive in primitives:
        points=(accessor(doc,blob,primitive['attributes']['POSITION'])-offset)*scale
        primitive['attributes']['POSITION']=append(doc,blob,points,'VEC3',target=34962)
        fields=np.zeros((len(points),len(names)))
        head_mix=smooth(.38,.78,points[:,2])*smooth(.42,.65,points[:,1])
        spine_mix=smooth(-.40,.30,points[:,2])
        fields[:,hips]=(1-head_mix)*(1-spine_mix)
        fields[:,spine]=(1-head_mix)*spine_mix
        fields[:,head]=head_mix
        for leg in legs:
            u,k,f=leg['ids']; side=leg['sign']
            lateral=smooth(.07,.22,points[:,0]*side)
            if leg['end']=='front': region=smooth(.28,.43,points[:,2])*(1-smooth(.66,.86,points[:,1]))
            else: region=(1-smooth(.10,.35,points[:,2]))*smooth(-1.,-.78,points[:,2])*(1-smooth(.39,.64,points[:,1]))
            amount=region*lateral
            # The long thin tail is a separate anatomical field, never a leg.
            amount*=smooth(-.83,-.68,points[:,0])
            paw_zone=(points[:,1]<.15)&(points[:,0]*side>.07)&(points[:,0]>-.73)&(points[:,2]>-.85)
            paw_zone&=(points[:,2]>.33) if leg['end']=='front' else (points[:,2]<=.33)
            amount=np.maximum(amount,paw_zone.astype(float))
            fields*=1-amount[:,None]
            low=1-smooth(.14,.31,points[:,1]);high=smooth(.26,.52,points[:,1])
            joint_weights=np.stack([high,(1-low)*(1-high),low*(1-high)],axis=1)
            joint_weights/=joint_weights.sum(axis=1,keepdims=True)
            for i,joint in enumerate([u,k,f]): fields[:,joint]+=amount*joint_weights[:,i]
            footprint=(amount>.98)&(points[:,1]<.045)
            sole_witnesses[leg['end']+'_'+leg['side']]=points[footprint].round(7).tolist()
        distances=[];fractions=[]
        for a,b in zip(tail_points[:-1],tail_points[1:]):
            distance,fraction=segment_distance(points,a,b);distances.append(distance);fractions.append(fraction)
        distances=np.array(distances).T;segment=distances.argmin(axis=1)
        nearest=distances[np.arange(len(points)),segment]
        tail_amount=(1-smooth(.13,.24,nearest))*(1-smooth(.35,.52,points[:,1]))
        tail_amount*=np.maximum(1-smooth(-.83,-.66,points[:,0]),1-smooth(-1.12,-.97,points[:,2]))
        # Include the whole broad native curl, not only the centreline band.
        low_tail=np.maximum((1-smooth(-.84,-.73,points[:,0]))*(1-smooth(.28,.42,points[:,1])),
            (1-smooth(-1.01,-.88,points[:,2]))*(1-smooth(.26,.42,points[:,1])))
        tail_amount=np.maximum(tail_amount,low_tail)
        fields*=1-tail_amount[:,None]
        for i in range(len(points)):
            s=segment[i]; t=fractions[s][i]; fields[i,tail[s]]+=tail_amount[i]*(1-t);fields[i,tail[s+1]]+=tail_amount[i]*t
        order=np.argsort(fields,axis=1)[:,-4:][:,::-1];weights=np.take_along_axis(fields,order,axis=1)
        weights/=weights.sum(axis=1,keepdims=True)
        assert np.isfinite(weights).all() and np.max(abs(weights.sum(1)-1))<1e-5
        primitive['attributes']['JOINTS_0']=append(doc,blob,order,'VEC4',component=5123,target=34962)
        primitive['attributes']['WEIGHTS_0']=append(doc,blob,weights,'VEC4',target=34962)
    doc['animations']=[]; ik_error=0.
    for clip,duration,stride,height,duty in [('Idle_A',2.4,0.,0.,.65),('Walk',.85,.43,.10,.66),('Jog',.54,.60,.17,.56)]:
        times=np.linspace(0,duration,round(duration*60)+1); count=len(times)
        trans=np.repeat(np.array([n.get('translation',[0,0,0]) for n in nodes[:len(names)]])[None],count,axis=0)
        rotations=np.zeros((count,len(names),4));rotations[:,:,3]=1
        for frame,t in enumerate(times):
            cycle=t/duration;moving=stride>0
            bob=(.005+.004*math.sin(2*math.pi*cycle)) if not moving else ((-.03 if clip=='Walk' else -.06)+(.012 if clip=='Walk' else .018)*math.cos(4*math.pi*cycle))
            trans[frame,hips,1]+=bob
            rotations[frame,head]=axisq([1,0,0],(.01 if not moving else .018)*math.sin(2*math.pi*cycle))
            # Cancel bob at the tail base to keep its low native curl clear.
            trans[frame,tail[0],1]-=bob
            for i,joint in enumerate(tail): rotations[frame,joint]=axisq([0,1,0],(.005 if not moving else .018 if clip=='Walk' else .035)*math.sin(2*math.pi*cycle-i*.55))
            if not moving: continue
            for leg in legs:
                u,k,f=leg['ids'];a,b,c=positions[[u,k,f]]
                phase_offset={('front','l'):0,('hind','r'):.25,('front','r'):.5,('hind','l'):.75}[(leg['end'],leg['side'])]
                if clip=='Jog': phase_offset=0 if (leg['end'],leg['side']) in [('front','l'),('hind','r')] else .5
                phase=(cycle+phase_offset)%1
                if phase<duty: dz=stride*(.5-phase/duty);lift=0
                else:
                    s=(phase-duty)/(1-duty);m=-stride*(1-duty)/duty
                    dz=(2*s**3-3*s*s+1)*(-stride*.5)+(s**3-2*s*s+s)*m+(-2*s**3+3*s*s)*(stride*.5)+(s**3-s*s)*m
                    lift=height*math.sin(math.pi*s)**2
                anchor=a+np.array([0,bob,0]);target=c+np.array([0,lift+.012,dz])
                ray=target-anchor;distance=np.linalg.norm(ray);direction=ray/distance
                l1=np.linalg.norm(b-a);l2=np.linalg.norm(c-b)
                reach=np.clip(distance,abs(l1-l2)+1e-6,l1+l2-1e-6)
                ik_error=max(ik_error,abs(distance-reach))
                pole=b-a;pole-=direction*np.dot(pole,direction)
                if np.linalg.norm(pole)<1e-8: pole=np.array([0,0,-1.])
                pole/=np.linalg.norm(pole)
                x=(l1*l1-l2*l2+reach*reach)/(2*reach)
                elbow=anchor+direction*x+pole*math.sqrt(max(0,l1*l1-x*x))
                upper=align(b-a,elbow-anchor);lower=align(c-b,target-elbow)
                rotations[frame,u]=upper;rotations[frame,k]=qmul(qinv(upper),lower);rotations[frame,f]=qinv(lower)
        animation={'name':clip,'samplers':[],'channels':[]}
        time_accessor=append(doc,blob,times.reshape(-1,1),'SCALAR')
        for joint in range(len(names)):
            for path,values,kind in [('translation',trans[:,joint],'VEC3'),('rotation',rotations[:,joint],'VEC4')]:
                if path=='rotation':
                    for i in range(1,len(values)):
                        if np.dot(values[i-1],values[i])<0: values[i]*=-1
                animation['samplers'].append({'input':time_accessor,'output':append(doc,blob,values,kind),'interpolation':'LINEAR'})
                animation['channels'].append({'sampler':len(animation['samplers'])-1,'target':{'node':joint,'path':path}})
        doc['animations'].append(animation)
    doc['asset']['generator']='Rabbit Lands imported Giant Rat mount draft v1'
    doc['extras']={'mountOnly':True,'source':'existing Meshy Dock Rat','sourceSha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'rootMotion':'in_place'}
    doc['buffers']=[{'byteLength':len(blob)}]
    encoded=json.dumps(doc,separators=(',',':')).encode();encoded+=b' '* (-len(encoded)%4);blob.extend(b'\0'*(-len(blob)%4))
    output=struct.pack('<III',0x46546c67,2,28+len(encoded)+len(blob))+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+struct.pack('<II',len(blob),0x004e4942)+blob
    OUTPUT.parent.mkdir(parents=True,exist_ok=True);OUTPUT.write_bytes(output)
    report={'draft':True,'sourceSha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'outputSha256':hashlib.sha256(output).hexdigest(),'joints':len(names),'triangles':4000,'clips':[(a['name'],doc['accessors'][a['samplers'][0]['input']]['max'][0]) for a in doc['animations']],'maximumIKReachErrorMetres':ik_error,'mountOnly':True,'notes':'New anatomical rig/skin and three mount loops on preserved imported geometry/UVs/textures. Creature combat slots are deliberately absent.'}
    (HERE/'build-report.json').write_text(json.dumps(report,indent=2)+'\n')
    (HERE/'sole-witnesses.json').write_text(json.dumps(sole_witnesses,separators=(',',':'))+'\n')
    print(json.dumps(report))

if __name__=='__main__': main()
