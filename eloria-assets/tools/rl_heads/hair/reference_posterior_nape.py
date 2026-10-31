"""Optional coherent rear seating before a reference's nearest-head guard.

This is a measured source-fitting operation, never a Native corrective or a
change to its displacement bound. It leaves X/Y, topology and UVs untouched.
"""
import numpy as np
import assemble,headref,hairgen


def fit_posterior_nape(head,P,N,T,spec):
    config=spec.get('posterior_nape_fit')
    if not config:return P,N,{'enabled':False}
    P=np.asarray(P);N=np.asarray(N);T=np.asarray(T,int)
    assert P.shape==N.shape and P.ndim==2 and P.shape[1]==3
    assert np.isfinite(P).all() and np.isfinite(N).all()
    lower,upper=map(float,config['below_eye_mm'])
    width=float(config['half_width_mm']);front=float(config['max_z_from_center_mm'])
    margin=float(config.get('rear_margin_mm',5.5));limit=float(config['max_shift_mm'])
    feather=float(config.get('feather_mm',5))
    sample_up=float(config.get('rear_sample_up_mm',0))
    assert 0<=upper<lower<=250 and 0<width<=150 and -150<=front<=80
    assert 2<=margin<=12 and 0<limit<=80 and 0<feather<min(width,(lower-upper)/2)
    assert 0<=sample_up<=30
    low=float(head.eye_mid[1])-lower*.001;high=float(head.eye_mid[1])-upper*.001
    zmax=float(head.C[2])+front*.001;half=width*.001;fade=feather*.001
    blend=hairgen.smoothstep((P[:,1]-low)/fade)*hairgen.smoothstep((high-P[:,1])/fade)
    blend*=hairgen.smoothstep((half-abs(P[:,0]))/fade)*hairgen.smoothstep((zmax-P[:,2])/fade)
    selected=np.flatnonzero(blend>0)
    if not len(selected):return P,N,{'enabled':True,'selected_rows':0,'changed_rows':0,'maximum_shift_mm':0.}
    origins=P[selected].astype(float).copy();origins[:,2]=float(head.P[:,2].max())+.04
    direction=np.tile([0.,0.,-1.],(len(selected),1))
    rear_z=np.full(len(selected),np.inf);hit=np.zeros(len(selected),bool)
    # A curved open neck rim can leave only the front wall on an exact-height
    # ray. A bounded upward band finds the real posterior wall, rather than
    # interpreting that front-only hit as a rear envelope.
    offsets=np.linspace(0,sample_up*.001,max(1,int(np.ceil(sample_up/2))+1))
    for up in offsets:
        raised=origins.copy();raised[:,1]+=up
        rear,normal,valid=head.raycast(raised,direction,surface='skin',outermost=True)
        valid &= normal[:,2]<-.15
        rear_z[valid]=np.minimum(rear_z[valid],rear[valid,2]);hit|=valid
    depth=np.where(hit,np.maximum(P[selected,2]-rear_z+margin*.001,0),0)
    Q=P.copy();Q[selected,2]-=depth*blend[selected]
    changed=np.linalg.norm(Q-P,axis=1)>1e-12;distance=np.linalg.norm(Q-P,axis=1)*1000
    assert float(distance.max(initial=0))<=limit+1e-8,'Posterior source fit exceeds its declared displacement bound'
    assert np.array_equal(Q[:,:2],P[:,:2]) and np.array_equal(Q[~changed],P[~changed])
    _,weld=np.unique(np.round(P/1e-6),axis=0,return_inverse=True)
    M=headref.unit(N+assemble.morph_normals(P,T,N,Q-P,weld))
    M[~changed]=N[~changed]
    assert np.isfinite(M).all()
    receipt={'enabled':True,'method':'Profile-bounded posterior full-skin ray envelope before the generic head guard',
        'selected_rows':len(selected),'changed_rows':int(changed.sum()),'missing_rear_rays':int((~hit).sum()),
        'rear_sample_up_mm':sample_up,'rear_ray_bands':len(offsets),
        'maximum_shift_mm':float(distance.max(initial=0)),'declared_max_shift_mm':limit,
        'x_y_exact':True,'outside_positions_normals_exact':True,'topology_uv_unchanged':True,
        'normal_transport':'Authored normal plus the actual welded geometric normal change',
        'bounds':{'minimum_y':low,'maximum_y':high,'half_width':half,'maximum_z':zmax}}
    return Q,M,receipt
