"""One reader for published straight and authored curved border approaches.

Coordinates are region-local XYZ. ``inward`` is metres along the centerline
from the unchanged seam; negative values continue outward to the trigger.
The optional contract contains final source-authored bed stations. It never
changes portal lane positions, arrival transforms or map travel semantics.
"""
from __future__ import annotations
import math


def _curve(frame):
    contract = frame.get('approachCenterline')
    if contract is None:
        return None
    if (contract.get('schemaVersion') != 1 or contract.get('direction') != 'inland-to-seam'
            or contract.get('stationHeight') != 'bed'
            or contract.get('laneHalfWidth') != 3 or contract.get('physicalHalfWidth', 0) < 3.75
            or contract.get('commonBoundaryLength') != 3):
        raise ValueError('Invalid authored border approach contract')
    points = contract.get('stations', [])
    if len(points) < 2 or any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in points):
        raise ValueError('Authored approach needs finite XYZ stations')
    index = contract.get('collarStartIndex')
    if not isinstance(index, int) or not 0 <= index < len(points)-1:
        raise ValueError('Authored approach collar start is invalid')
    anchor = frame['anchor'];out = frame['outward']
    if math.hypot(points[-1][0]-anchor[0], points[-1][2]-anchor[2]) > 1e-6:
        raise ValueError('Authored approach does not meet the exact seam')
    result = []; distance = 0.
    for p in reversed(points[index:]):
        if result:
            step = math.hypot(p[0]-result[-1][1][0], p[2]-result[-1][1][2])
            if step < 1e-9:
                if abs(p[1]-result[-1][1][1]) > 1e-6:
                    raise ValueError('Authored approach contains a vertical station jump')
                continue
            distance += step
        if distance <= 3.+1e-6 and math.hypot(p[0]-anchor[0]+out[0]*distance,
                                             p[2]-anchor[2]+out[1]*distance) > 1e-5:
            raise ValueError('Authored approach changes the common boundary strip')
        result.append((distance, p))
    if distance < 42.-1e-5:
        raise ValueError('Authored approach omits part of the required 42 m collar')
    for (a,p),(b,q) in zip(result,result[1:]):
        if a < 3. <= b:
            t=(3.-a)/(b-a)
            x=p[0]*(1-t)+q[0]*t;z=p[2]*(1-t)+q[2]*t
            if math.hypot(x-anchor[0]+out[0]*3.,z-anchor[2]+out[1]*3.)>1e-5:
                raise ValueError('Authored approach changes the common boundary strip')
            break
    return result


def collar_length(frame):
    curve = _curve(frame)
    return curve[-1][0] if curve else 42.


def point(frame, inward, lane=0):
    """Walking-top XYZ at a lane offset; positive lane uses (-outZ,outX)."""
    if abs(lane) > 3:
        raise ValueError('Border lane is outside the seven required actor lanes')
    anchor = frame['anchor'];out = frame['outward'];curve = _curve(frame)
    if curve is None or inward <= 0:
        return [anchor[0]-inward*out[0]-lane*out[1], anchor[1]+.03,
                anchor[2]-inward*out[1]+lane*out[0]]
    if inward > curve[-1][0]+1e-6:
        raise ValueError('Requested point exceeds the authored approach collar')
    for (a,p),(b,q) in zip(curve,curve[1:]):
        if inward <= b+1e-8:
            t=max(0.,min(1.,(inward-a)/(b-a)))
            # Direction points outward, matching legacy lane orientation.
            dx=(p[0]-q[0])/(b-a);dz=(p[2]-q[2])/(b-a)
            return [p[0]*(1-t)+q[0]*t-lane*dz,
                    p[1]*(1-t)+q[1]*t+frame['approachCenterline']['walkingBias'],
                    p[2]*(1-t)+q[2]*t+lane*dx]
    raise ValueError('Authored approach interpolation failed')


def lane_points(frame, lane, spacing=.2, outward=1.):
    """Dense native-to-seam lane including curved offset joins and threshold.

    Sampling every segment also prevents a sharp lane-normal turn skipping
    addressable cells. Returned depth is signed arc distance from the seam.
    """
    if spacing <= 0 or outward < 0:
        raise ValueError('Approach spacing/outward distance must be positive')
    length=collar_length(frame);count=max(1,math.ceil(length/spacing))
    distances=[length*(1-i/count) for i in range(count+1)]
    if outward:
        count=max(1,math.ceil(outward/spacing))
        distances.extend(-outward*i/count for i in range(1,count+1))
    result=[]
    for inward in distances:
        p=point(frame,inward,lane)
        if result:
            old_depth,old=result[-1];n=max(1,math.ceil(math.hypot(p[0]-old[0],p[2]-old[2])/spacing))
            result.extend((old_depth+(-inward-old_depth)*i/n,
                           [old[j]+(p[j]-old[j])*i/n for j in range(3)]) for i in range(1,n+1))
        else:
            result.append((-inward,p))
    return result


def tile(point, transform):
    origin=transform.get('origin',[0,0,0]);server=transform['serverOrigin']
    scale=transform.get('metresPerTile',1)
    return (math.floor((point[0]-origin[0])/scale+server[0]),
            math.floor((origin[2]-point[2])/scale+server[1]))


def lane_tiles(frame, transform, lane, spacing=.2, outward=0.):
    result=[]
    for _,p in lane_points(frame,lane,spacing,outward):
        target=tile(p,transform)
        if not result or result[-1]!=target:
            result.append(target)
    return result
