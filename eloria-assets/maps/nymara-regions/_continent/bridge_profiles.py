"""Pure longitudinal profiles for broad, level continental bridge decks."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import linprog


DRY_CLEARANCE_METRES = .025


class ProfileError(ValueError):
    """The requested bridge cannot meet its banks and clearance limits."""


def smootherstep(value):
    value=np.clip(np.asarray(value,float),0.,1.)
    return value**3*(value*(value*6.-15.)+10.)


def arch_rise(wet_length,clearance,maximum_grade):
    """A deliberately shallow crown bounded by clearance and grade policy."""
    return min(float(clearance)/4.,float(wet_length)*float(maximum_grade)/20.)


def bank_bounds(terrain,maximum_lift):
    terrain=np.asarray(terrain,float)
    if not terrain.size or not np.isfinite(terrain).all():
        raise ProfileError('bridge bank has no finite full-width terrain section')
    return float(terrain.max()+DRY_CLEARANCE_METRES),float(terrain.min()+maximum_lift)


def canonical_stations(start,wet_start,wet_end,end,spacing=.5):
    """One deterministic breakline table shared by solve, query, and emission."""
    start,end,spacing=map(float,(start,end,spacing))
    if not start<end or not spacing>0.:
        raise ProfileError('canonical bridge stations need a positive span and spacing')
    middle=(float(wet_start)+float(wet_end))*.5
    count=max(1,int(np.ceil((end-start)/spacing)))
    candidates=[(start+i*spacing,False) for i in range(count)]
    candidates.extend((value,True) for value in (start,float(wet_start),middle,float(wet_end),end))
    candidates.sort(key=lambda item:item[0])
    groups=[]
    for value,authored in candidates:
        if groups:
            previous=groups[-1]
            scale=max(1.,abs(value),abs(previous[0]))
            if abs(value-previous[0])<=32*np.finfo(float).eps*scale:
                if authored:groups[-1]=(value,True)
                continue
        groups.append((value,authored))
    return np.asarray([value for value,_ in groups],float)


def station_basis(stations,start,middle,end):
    stations=np.asarray(stations,float);left=stations<=middle
    weight=np.where(left,smootherstep((stations-start)/(middle-start)),
                    smootherstep((end-stations)/(end-middle)))
    return np.stack((np.where(left,1.-weight,0.),np.where(left,0.,1.-weight),weight),axis=-1)


def interpolated_basis(distance,stations,basis):
    distance=np.asarray(distance,float);basis=np.asarray(basis,float)
    if basis.ndim!=2 or len(basis)!=len(stations) or not basis.shape[1]:
        raise ProfileError('profile basis must have one non-empty row per station')
    flat=distance.reshape(-1)
    result=np.stack([np.interp(flat,stations,basis[:,column]) for column in range(basis.shape[1])],axis=-1)
    return result.reshape(distance.shape+(basis.shape[1],))


def per_station_single_crest_constraints(stations,middle,rise,maximum_grade):
    stations=np.asarray(stations,float);count=len(stations);identity=np.eye(count);ds=np.diff(stations)
    if count<3 or np.any(ds<=0.):raise ProfileError('per-station profile needs unique increasing stations')
    matches=np.flatnonzero(stations==float(middle))
    if len(matches)!=1:raise ProfileError('per-station profile has no unique middle station')
    middle_index=int(matches[0]);rows=[];limits=[];delta=np.diff(identity,axis=0)
    for values,bounds in ((delta,float(maximum_grade)*ds),(-delta,float(maximum_grade)*ds)):
        rows.extend(values);limits.extend(bounds)
    for endpoint in (0,count-1):
        row=np.zeros(count);row[endpoint]=1.;row[middle_index]=-1.;rows.append(row);limits.append(-float(rise))
    for index in range(middle_index):
        row=np.zeros(count);row[index]=1.;row[index+1]=-1.;rows.append(row);limits.append(0.)
    for index in range(middle_index,count-1):
        row=np.zeros(count);row[index+1]=1.;row[index]=-1.;rows.append(row);limits.append(0.)
    curvature=[]
    for index in range(1,count-1):
        row=np.zeros(count);row[index-1]=1./ds[index-1];row[index]=-1./ds[index-1]-1./ds[index]
        row[index+1]=1./ds[index];curvature.append(row)
    return np.asarray(rows),np.asarray(limits),np.asarray(curvature),middle_index


@dataclass(frozen=True)
class ArchProfile:
    stations: np.ndarray
    heights: np.ndarray
    wet_start: float
    middle: float
    wet_end: float

    @property
    def start(self):return float(self.stations[0])
    @property
    def end(self):return float(self.stations[-1])
    @property
    def left(self):return float(self.heights[0])
    @property
    def crown(self):return float(np.interp(self.middle,self.stations,self.heights))
    @property
    def right(self):return float(self.heights[-1])
    def at(self,distance):return np.interp(distance,self.stations,self.heights,left=self.left,right=self.right)


def solve_arch(distances,lower,upper,*,start,wet_start,wet_end,end,left_bounds,right_bounds,
               maximum_grade,crown_metres):
    """Return the lowest feasible broad, single-crest longitudinal profile."""
    distances,lower,upper=np.broadcast_arrays(np.asarray(distances,float),np.asarray(lower,float),np.asarray(upper,float))
    if not start<wet_start<wet_end<end:raise ProfileError('bridge needs dry landings around a non-empty wet span')
    if not np.isfinite(lower).all() or not np.isfinite(distances).all():
        raise ProfileError('bridge profile constraints must be finite')
    left_low,left_high=map(float,left_bounds);right_low,right_high=map(float,right_bounds)
    if left_low>left_high+1e-9 or right_low>right_high+1e-9:
        raise ProfileError('a full-width bank cannot carry one level join within the terrain limits')
    middle=(float(wet_start)+float(wet_end))*.5
    stations=canonical_stations(start,wet_start,wet_end,end)
    basis=station_basis(stations,float(start),middle,float(end))
    coefficients=interpolated_basis(distances,stations,basis).reshape(-1,3)
    lower=lower.reshape(-1);upper=upper.reshape(-1);rows=[-coefficients];limits=[-lower]
    finite=np.isfinite(upper)
    if finite.any():rows.append(coefficients[finite]);limits.append(upper[finite])
    delta=np.diff(basis,axis=0);ds=np.diff(stations)
    rows.extend((delta,-delta,np.array([[1.,0.,-1.],[0.,1.,-1.]])))
    limits.extend((float(maximum_grade)*ds,float(maximum_grade)*ds,
                   np.array([-float(crown_metres),-float(crown_metres)])))
    # Height first, then a tiny endpoint penalty: the resulting crown is the
    # least elevation compatible with clearance and the authored visible rise.
    result=linprog(np.array([1e-7,1e-7,1.]),A_ub=np.concatenate(rows),b_ub=np.concatenate(limits),
                   bounds=[(left_low,left_high),(right_low,right_high),(None,None)],method='highs')
    if not result.success:raise ProfileError('bridge has no profile satisfying bank, clearance, lift, and grade constraints')
    profile=ArchProfile(stations,basis@result.x,float(wet_start),middle,float(wet_end))
    height=profile.at(distances).reshape(-1)
    if np.any(height<lower-1e-8) or np.any(finite&(height>upper+1e-8)):
        raise ProfileError('solved bridge profile escaped its source constraints')
    return profile
