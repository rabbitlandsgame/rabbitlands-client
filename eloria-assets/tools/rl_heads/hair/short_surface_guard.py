"""Optional contact-only short-hair surface guard, before detail attachment.

Checks triangle centres and edge midpoints, not only their corners. Native fitting belongs in a separate corrective; this helper never mixes the
two skulls.
"""
import numpy as np
import trimesh
import headref


def guard(head,P,T,delta,ids,combos,native=False,margin=.0030,max_shift_mm=14,max_iterations=6,
          fixed=None,native_controls=None,all_faces=False,geometric_projection=False):
    original=np.asarray(P);Q=original.astype(float,copy=True)
    assert not native and not native_controls,'Use a separate Native-only corrective; this guard owns the RL surface'
    # Crests far from the head cannot touch it. Keep all near-head faces and
    # their boundary neighbours; no topology or UV change occurs.
    sd,_,_=head.signed(Q)
    near=sd<.018
    faces=T if all_faces else T[near[T].any(1)]
    if not len(faces):
        return Q,{'face_samples':0,'states':1+len(delta)+len(combos),'changed_vertices':0,'maximum_shift_mm':0.,'margin_mm':margin*1000,'iterations':[],'native_bind_baseline_only':False,'native_source':None,'noncontact_positions_exact':True}
    bary=np.array([[1/3,1/3,1/3],[.5,.5,0],[.5,0,.5],[0,.5,.5]])
    used=np.unique(faces);vertices=np.vstack([np.repeat(used[:,None],3,axis=1),np.repeat(faces,len(bary),axis=0)])
    contribution=np.vstack([np.full((len(used),3),1/3),np.tile(bary,(len(faces),1))])
    contribution/=np.square(contribution).sum(1)[:,None]
    margins=np.full(len(Q),margin)
    if fixed is not None:margins[fixed]=.0024
    probe_margin=np.r_[margins[used],np.repeat(margins[faces].max(1),len(bary))]
    states={'rest':{}}|{name:{name:1} for name in delta}|combos
    # UV/normal splits are attribute seams, not geometric boundaries. Keep
    # their contact displacement identical so seating cannot reopen them.
    _,weld=np.unique(np.round(original/1e-6),axis=0,return_inverse=True)
    cache={};records=[];ever=np.zeros(len(Q),bool)
    for iteration in range(max_iterations):
        steps=np.zeros(len(Q));vectors=np.zeros_like(Q);contacts={'rl':0,'native':0};worst={'rl':float('inf'),'native':float('inf')}
        for label,weights in states.items():
            move=sum((delta[name]*value for name,value in weights.items() if name in delta),np.zeros_like(Q))
            posed=Q+move;probes=np.vstack([posed[used],np.einsum('qk,tki->tqi',bary,posed[faces]).reshape(-1,3)])
            key=tuple((name,value) for name,value in sorted(weights.items()) if name in ids)
            if key not in cache:
                D=sum((head.delta(name)*value for name,value in key),np.zeros_like(head.P))
                cache[key]=(D,trimesh.Trimesh(head.P+D,head.T,process=False))
            D,mesh=cache[key]
            distance,cp,normal,rim=head.signed(probes,D=D,mesh=mesh,with_rim=True)
            queries=[('rl',distance,normal,~rim,probe_margin)]
            for kind,distance,normal,eligible,target in queries:
                worst[kind]=min(worst[kind],float(distance.min()))
                bad=(distance<target-1e-8)&eligible
                contacts[kind]+=int(bad.sum())
                if not bad.any():continue
                amount=target[bad]+.0002-distance[bad]
                direction=normal[bad]
                if geometric_projection:
                    separation=probes[bad]-cp[bad]
                    length=np.linalg.norm(separation,axis=1)
                    direction=headref.unit(separation)*np.where(distance[bad]<0,-1.,1.)[:,None]
                    direction[length<1e-10]=normal[bad][length<1e-10]
                proposals=direction*amount[:,None]
                order=np.argsort(amount,kind='stable')
                for corner in range(3):
                    indices=vertices[bad,corner]
                    corner_amount=amount*contribution[bad,corner] if geometric_projection else amount
                    corner_vectors=proposals*contribution[bad,corner,None] if geometric_projection else proposals
                    if geometric_projection:order=np.argsort(corner_amount,kind='stable')
                    unique,reverse=np.unique(indices[order][::-1],return_index=True)
                    chosen=order[len(order)-1-reverse];wins=corner_amount[chosen]>steps[unique]
                    steps[unique[wins]]=corner_amount[chosen[wins]];vectors[unique[wins]]=corner_vectors[chosen[wins]]
        records.append({'iteration':iteration,'contacts':contacts,'minimum_mm':{key:value*1000 for key,value in worst.items() if np.isfinite(value)}})
        print('SHORT_SURFACE_GUARD',records[-1],flush=True)
        active=steps>0
        if not active.any():
            displacement=np.linalg.norm(Q-original,axis=1)*1000
            return Q,{'face_samples':len(vertices),'states':len(states),'changed_vertices':int(ever.sum()),
                      'maximum_shift_mm':float(displacement.max()),'margin_mm':margin*1000,'iterations':records,
                      'native_bind_baseline_only':False,'native_source':None,
                      'noncontact_positions_exact':bool(np.array_equal(Q[~ever],original[~ever]))}
        order=np.argsort(steps,kind='stable');_,reverse=np.unique(weld[order][::-1],return_index=True)
        chosen=order[len(order)-1-reverse];group_vector=np.zeros((weld.max()+1,3))
        group_vector[weld[chosen]]=vectors[chosen];vectors=group_vector[weld]
        active=np.linalg.norm(vectors,axis=1)>0
        Q[active]+=vectors[active];ever|=active
        shift=np.linalg.norm(Q-original,axis=1)*1000
        assert shift.max()<=max_shift_mm,'Sampled surface guard exceeded local displacement limit: '+str({'maximum_mm':float(shift.max()),'vertex':int(shift.argmax())})
    raise AssertionError('Sampled short-hair contact remains after bounded surface guard: '+str(records[-1]))
