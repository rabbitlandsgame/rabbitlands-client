"""Discovery stones beside the public basin and Orrery keepers' courts.

The old Orrery flagstone retained a separate high soil pillar when the
northern pass was lowered. Move its protection before that shared pass;
the principal Orrery and basin structures keep their own original footings.
"""
from copy import deepcopy
import numpy as np

REVISION = 'public-basin-and-orrery-discovery-1'
NATIVE_ORIGIN = (120., 96.)
OLD_POSTS = {'mirror-basin-spring': (80.,84.,-88.),
             'mirror-orrery-vault': (115.,124.,-230.)}
POSTS = {'mirror-basin-spring': (88.,84.,-109.),
         'mirror-orrery-vault': (62.,91.3536,-193.)}
# Place the physical clues after the final court is shaped. Their protected
# discovery approaches and authoritative markers stay unchanged; the clues
# sit beyond the actual actor corridor rather than across the public road.
FINAL_PROP_XZ = {'mirror-basin-spring': (88.,-111.7),
                 'mirror-orrery-vault': (62.5,-191.)}
# The old Basin stone overlapped the real basin's western masonry lip. Its
# original four-metre earth pad belongs to that structure and must survive
# the discovery move; the abandoned Orrery slab has no structural footing.
RETAINED_FOUNDATION_POSTS = ((80.,84.,-88.),)
IDENTITY_FIELDS = ('id','kind','secret','name','label','prop','key',
                   'destinationMap','destinationSpawn','authority')


def prepare(build):
    """Move only the two discovery props before northern footing protection."""
    if hasattr(build, 'secret_approaches'):
        return
    records = []
    for secret, point in POSTS.items():
        entry = next(e for e in build.interactives if e.get('secret') == secret)
        node = 'Secret_' + secret.replace('-', '_')
        prop = next(p for p in build.placements if p.node == node)
        identity = {k:deepcopy(entry[k]) for k in IDENTITY_FIELDS if k in entry}
        entry['position'] = list(point)
        entry['serverTile'] = [round(point[0]+NATIVE_ORIGIN[0]), round(NATIVE_ORIGIN[1]-point[2])]
        prop.position = (point[0], point[1]-.05, point[2]-1.8)
        prop.collides = False
        records.append({'secret':secret,'node':node,'identity':identity,
                        'originalSurveyPosition':list(OLD_POSTS[secret]),
                        'position':list(point),'propPosition':list(prop.position)})
    build.secret_approaches = {'revision':REVISION,'entries':records,
        'reason':'The Basin Spring is discovered on its dry southern court; the Orrery Vault flagstone lies beside the keepers\' working-court approach. The abandoned secret-only high footing is released.'}


def _tilt(gradient):
    """Rigid rotation from horizontal to a measured plane; never stretch a prop."""
    normal = np.array([-gradient[0],1.,-gradient[1]],float)
    normal /= np.linalg.norm(normal)
    axis = np.cross([0.,1.,0.],normal)
    skew = np.array([[0.,-axis[2],axis[1]],[axis[2],0.,-axis[0]],[-axis[1],axis[0],0.]])
    return np.eye(3) + skew + skew@skew/(1.+normal[1])


def finish(build):
    """Seat the retained props on actual final ground after the local court."""
    if not hasattr(build,'secret_approaches'):
        raise ValueError('Secret approaches were not authored before northern shaping')
    if build.secret_approaches.get('finished'):
        return
    from amberwood import mesh as M
    from verify_runtime import VerticalRayIndex
    meshes = [m for n,m in build.terrain_meshes.items() if n.startswith('Terrain_')
              and not any(s in n for s in ('_StreamCollar_','_ContinentBlend_','OuterEscarpment')) and m.triangle_count]
    terrain = VerticalRayIndex(np.concatenate([m.positions[m.indices.reshape(-1,3)] for m in meshes]))
    def height(x,z):
        value = terrain.top_hit(float(x),float(z))
        if value is None:
            raise ValueError(f'Secret discovery point has no actual ground at {x}, {z}')
        return float(value)
    for record in build.secret_approaches['entries']:
        secret = record['secret']
        entry = next(e for e in build.interactives if e.get('secret') == secret)
        prop = next(p for p in build.placements if p.node == record['node'])
        x,_,z = POSTS[secret]
        entry['position'] = [x,height(x,z),z]
        px,pz = FINAL_PROP_XZ[secret]
        if secret == 'mirror-orrery-vault':
            # Align the original slab with the verge axes. This rigid pose
            # clears the full public road and the discovery's final step.
            prop.rotation_y = 0.
            offsets = np.array([(a,b) for a in (-.8,0.,.8) for b in (-.8,0.,.8)])
            samples = np.array([height(px+a,pz+b) for a,b in offsets])
            plane = np.linalg.lstsq(np.c_[offsets,np.ones(len(offsets))],samples,rcond=None)[0]
            yaw = M.rotation_y(prop.rotation_y)[:3,:3]
            matrix = np.eye(4);matrix[:3,:3] = yaw.T@_tilt(plane[:2])@yaw
            build.meshes[prop.mesh] = build.meshes[prop.mesh].copy().transform(matrix)
            prop.position = (px,float(plane[2])-.05,pz)
            record['rigidGroundTilt'] = matrix[:3,:3].tolist()
            record['groundPlane'] = plane.tolist()
            record['propRotationY'] = prop.rotation_y
        else:
            prop.position = (px,height(px,pz)-.05,pz)
        if record['identity'] != {k:entry[k] for k in record['identity']}:
            raise ValueError('A discovery relocation changed a secret identity or destination')
        record.update(position=list(entry['position']),propPosition=list(prop.position),
                      nativeServerTile=list(entry['serverTile']))
    build.secret_approaches['finished'] = True


def manifest(build, payload):
    if not build.secret_approaches.get('finished'):
        raise ValueError('Unfinished secret approaches cannot be published')
    payload['secretApproaches'] = deepcopy(build.secret_approaches)
