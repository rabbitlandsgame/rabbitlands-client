"""Reduce woodland detail while retaining the exact finished landscape."""
from copy import deepcopy
import re
from amberwood import populate

TREE=re.compile(r'^Tree_(.+)_v(\d+)_(?:high|mid|low)_(wood|canopy)$')
DETAIL=re.compile(r'^(?:Undergrowth|FallenLog|Stump|LeafDrift|Mushrooms|Rock)_\d+(?:_|$)')


def derive(build):
    """Keep shared edges, water, foundations and every retained object's pose.

    An independently regenerated low-detail forest consumes different random
    choices and changes the terrain's protected footprints. That can move a
    road contact or make its constrained solve infeasible. The far package is
    a visual reduction of the completed region instead.
    """
    distant=deepcopy(build)
    referenced={str(item['node']) for group in ('landmarks','interactives','harvestables','portals')
                for item in getattr(build,group,[]) if item.get('node')}
    retained=[]
    omitted=[]
    for placement in distant.placements:
        if DETAIL.match(placement.node) and not placement.landmark and placement.node not in referenced:
            omitted.append(placement.node)
            continue
        match=TREE.fullmatch(placement.mesh)
        if match:
            species,variant,part=match.groups()
            wood,canopy=populate.ensure_tree_meshes(distant,species,int(variant),'low')
            replacement=wood if part=='wood' else canopy
            if replacement is None:
                omitted.append(placement.node)
                continue
            placement.mesh=replacement
        retained.append(placement)
    distant.placements=retained
    used={placement.mesh for placement in retained}
    distant.meshes={name:mesh for name,mesh in distant.meshes.items() if name in used}
    distant.distant_omissions=sorted(omitted)
    distant.notes.append('Far landscape retains the exact finished terrain, water, roads and retained poses; tree meshes reduce to their low tier and unlinked ground detail is omitted.')
    return distant
