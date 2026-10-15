"""Place retained authored structures and ecological instances in one world."""
from __future__ import annotations
import copy
import json
import math
import re
import time
from pathlib import Path
import object_edits as OE
import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy.spatial import cKDTree
import landscape as L
import scene_io as S
import winding as W
import assemblies as A
import authoring as CA

NATURAL={'tree','foliage','rock','undergrowth','stone','scatter','small_dressing',
         'stump','fallenlog','leafdrift','mushrooms','fern','vine','scrub'}
METADATA=('landmarks','interactives','portals','spawnPoints','pointsOfInterest','harvestables','npcMarkers','creatureSpawns','spawns')
# Grey Moors survey fragments crossing the drainage that the continental
# bridge union now spans. Exactly these roots; see grey_crossings.py.
RETIRED_GREY_SPANS=('Landmark_boardwalk_gate','Landmark_boardwalk_centre','Landmark_boardwalk_south')
# A ground-standing prop whose base the regional survey left this far under
# its own terrain is stood on the ground when it is placed (see load()).
BURIED_PROP_METRES=.2
# A ground-standing prop the regional survey left this far in the air stands
# on the target ground too; hulls are settled on the actual water or ground by
# the boat modules, and props that float by design keep their authored offset.
FLOATING_PROP_METRES=.5
HULL_WORDS=('boat','skiff','dugout','canoe','punt','lateen','packet','tender','barge','raft','wherry')
FLOATING_BY_DESIGN=('wisp','light','flame','spark','orb','crystal','shard','lantern')
# Structures built to be passed keep the soft road clearance but are no solid
# for road alignment. Whole name words only: a shopfront on Four Gates street,
# a march track and an archive are solids, as are an arch's columns and a
# gate's walls and wings.
WALK_THROUGH_WORDS=('gate','arch','arcade','colonnade','causeway','portal','waygate')
WALK_THROUGH_EXCEPTIONS=('archcolumn','gatecolumn','gatewall','gatewing')
# Ecological scatter never grows inside a building (Content.scatter_structures): a retained face more than
# STRUCTURE_RISE_METRES above the ground marks the composed cells under its real footprint, grown by a
# trunk's reach. Many retained structures carry collides: false (their collision is authored separately),
# so the footing obstacles alone never showed them to the scatter.
STRUCTURE_RISE_METRES=1.
STRUCTURE_REACH_METRES=1.
# Exported root-name fragments that are no building: the scatter itself, props, walk surfaces and the
# generated bridge unions (the roots O/edits-after/scan_trees_in_structures.py leaves out as well).
SCATTER_OPEN_ROOT_TOKENS=('_Grove_','_WoodlandFloor_','_Outcrop_','_Prop_','_Walk_','BridgeUnion')
# Retained families that are landforms or float by design rather than buildings, so scatter keeps growing
# round and under them, matched as node-name prefixes: the Amethyst Barrens' crystal massif spires (rubble
# at their feet) and its levitating shards (ground cover under them).
SCATTER_THROUGH_PREFIXES=('Crystal_MassifSpire_','Landmark_LevitatingShards_')


def name_words(name):
    """The whole words of a node name: separators and camel case both split ('Landmark_GreatArch' -> landmark, great, arch)."""
    return [w.lower() for w in re.findall(r'[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+',str(name))]


def walk_through(name):
    """A gate, arch, arcade, colonnade, causeway or portal, by the whole words of its node name."""
    if any(word in str(name).lower() for word in WALK_THROUGH_EXCEPTIONS):return False
    return any(word in WALK_THROUGH_WORDS for word in name_words(name))


def retained_source_center(transform,center):
    """(source centre, xz scale) summarising a retained transform: the source point the territory's
    centre stands on, and the north-south squeeze (1 for a rigid translation).

    Content places through landscape.retained_map_xz (Content.mapped_xz); a source centre and a
    per-axis scale cannot express the layout's turn. This summary is kept for the published
    contentTransform alone, the continuous fallback for server tiles with no explicit mapping."""
    translation,scale,about=L.retained_affine(transform)
    return (np.asarray(center,float)-translation[[0,2]]-about*(1.-scale))/scale,scale


def retained_source_placements(region, placements):
    """Discard Manymouth's former inter-district route assemblies as roots.

    Its source layout.py/compact_plan.py emit Survey_<from>__<to> parents
    containing Walk_Survey_* ribbons. The continent authors those routes again;
    retaining the parent accidentally preserves aerial floors despite filtering
    standalone Walk nodes. Landing_* platforms and real architecture remain.
    Filter before assembly grouping so discarded route bounds cannot move a town.
    """
    obsolete={'manymouth_delta':('Survey_','Walk_Survey_'),
              'mirrorhold':('Landmark_MeltwaterBridge_',),
              # Whitehorn's boundary marches dressed the old map's exits; under the
              # retained transform they stand in the continent's seam zones at the
              # relief's edge, where the seam roads are the exits.
              'whitehorn_range':('Landmark_rope_bridge_','March_west_pass_','March_east_pass_','March_south_gate_'),
              'amberwood':('Landmark_Survey_ridge-bridge',)}
    # Wilderness spans were surveyed against the retired regional ravines.
    # Their new crossings are built from the continent's actual drainage.
    # Named discoveries at the old bridge abutments retain their own geometry.
    # Grey Moors keeps its other spans, causeway bridges and boardwalk cache;
    # only the three duplicate crossings are retired, by exact root name.
    # The Whitehorn north shrine stood on the old map's crest beyond the continent's
    # north edge; under the retained transform it lands on the shore two metres
    # from the sea with a 164 m legacy footing. Retired until the crest returns.
    retired={'grey_moors':set(RETIRED_GREY_SPANS),'whitehorn_range':{'Landmark_shrine_01'}}
    return [p for p in placements if not p['node'].startswith(obsolete.get(region,())) and p['node'] not in retired.get(region,())]


def placement_bounds(document,body,placements):
    """(low, high) of every retained placement's own subtree, by node name."""
    matrices=S.GR.hierarchy(document)[0]
    by_name={n.get('name'):i for i,n in enumerate(document['nodes'])}
    return {p['node']:S.subtree_bounds(document,body,by_name[p['node']],matrices)
            for p in placements if p['node'] in by_name}


def turn_layout(document,body,placements,yaw_degrees,pivots=None,turns=None):
    """Turn a whole retained layout by ``yaw_degrees`` in a private copy of its document.

    A retained root turns about its own base centre on object_edits' own matrix, the rotation it
    performs for an authored edit (which is then applied on top of this one, never twice): the mesh
    turns in place while mapped_xz carries its position round. A compound member turns about ``pivots[node]``,
    its compound's reference point, so the members' positions rotate about it as well and the compound
    stays one rigid body under a single shift. A tree's foliage companions turn with the tree, on its
    matrix, so a crown cannot part from its trunk. Nothing is scaled. ``turns``, when given, receives
    each turned root's matrix by node name (a retained attachment is carried on its host's).
    """
    document=dict(document);document['nodes']=[dict(node) for node in document['nodes']]
    matrices,parents=S.GR.hierarchy(document)
    by_name={n.get('name'):i for i,n in enumerate(document['nodes'])}
    foliage={}
    for p in placements:
        if p.get('kind')=='foliage' and p['node'] in by_name and 'position' in p:
            foliage.setdefault(tuple(np.round(p['position'],4)),[]).append(p['node'])
    turned=set()
    for p in placements:
        name=p['node']
        if name not in by_name or name in turned:continue
        roots=[name]
        if (p.get('kind')=='tree' or name.endswith('_Wood')) and 'position' in p:
            roots+=[c for c in foliage.get(tuple(np.round(p['position'],4)),()) if c!=name and c not in turned]
        low,high=np.full(3,np.inf),np.full(3,-np.inf)
        for root in roots:
            l,h=S.subtree_bounds(document,body,by_name[root],matrices)
            low=np.minimum(low,l);high=np.maximum(high,h)
        pivot=(pivots or {}).get(name)
        # object_edits' matrix is a right-handed turn about +Y, which swings the opposite way to the
        # map's yaw (positive from north towards east, landscape._rotate_xz). Turning the root by its
        # negative puts the mesh round exactly as retained_map_xz carries the positions.
        k=OE.edit_matrix([float(pivot[0]),0.,float(pivot[1])] if pivot is not None else OE.base_pivot(low,high),-yaw_degrees)
        for root in roots:
            index=by_name[root];parent=matrices[parents[index]] if index in parents else np.eye(4)
            OE.set_matrix(document['nodes'][index],np.linalg.inv(parent)@k@parent@S.GR.local_matrix(document['nodes'][index]))
            turned.add(root)
            if turns is not None:turns[root]=k
    return document


# Authored corrections to retained placements, per territory, in the plan (see Content.load):
#   "retained_part_edits": {"<region>": [{"node": str, "part": str, "translate": [dx, dy, dz]}
#                                        or {"node": str, "part": str, "remove": true}]}
#   "retained_attachments": {"<region>": [{"node": str, "host": str, "offset": [dx, dy, dz]}]}
#   "retained_footings": {"<region>": [{"node": str, "radius": metres, "feather": metres}]}
# Every vector is in metres of the legacy source frame (the library's own axes).
RETAINED_SECTIONS=('retained_part_edits','retained_attachments','retained_footings')
PART_EDIT_KEYS=('node','part','translate','remove')
ATTACHMENT_KEYS=('node','host','offset')
FOOTING_KEYS=('node','radius','feather')
#   "assembly_member_offsets": {"<assembly id>": {"<member node>": [dx, dy, dz]}}
# moves one member of a compound in the legacy source frame before any bounds or grouping (see apply_member_offsets):
# object edits refuse compound members, whose one shared shift keeps the compound rigid.
MEMBER_OFFSETS='assembly_member_offsets'
# Name words of placements that may stand in water: the pull of a single and of a pulled site ask the rest for dry ground.
AQUATIC_WORDS=('boat','skiff','pier','jetty','quay','bridge','causeway','sunken','waterfall')


def _finite_vector(value,length):
    """``value`` as a finite float vector of ``length``, or None."""
    if isinstance(value,(str,bytes,dict)) or value is None:return None
    try:vector=np.asarray(value,float)
    except (TypeError,ValueError):return None
    return vector if vector.shape==(length,) and np.isfinite(vector).all() else None


def check_retained_sections(plan,ids):
    """Refuse a retained plan section that is not a territory table or names a territory the continent lacks."""
    for section in RETAINED_SECTIONS:
        table=(plan or {}).get(section)
        if table is None:continue
        if not isinstance(table,dict):raise ValueError(f'{section}: must map territory ids to lists of entries')
        unknown=sorted(set(table)-set(ids))
        if unknown:raise ValueError(f'{section}: no territory {unknown}; the continent has {list(ids)}')
        for region,entries in table.items():
            if not isinstance(entries,list) or not all(isinstance(entry,dict) for entry in entries):
                raise ValueError(f'{section}[{region!r}]: must be a list of objects')


def retained_section(plan,section,region):
    """One territory's entries of a retained plan section (an empty list where it has none)."""
    return list(((plan or {}).get(section) or {}).get(region) or [])


def apply_part_edits(region,document,body,placements,entries):
    """Move or drop named parts of retained placements, in a private copy of the territory's document.

    Each entry names a retained placement ``node`` and one ``part`` inside its subtree (a descendant
    node, never the placement itself: object edits move and remove whole placements), and either
    ``translate`` [dx, dy, dz] or ``remove``: true. The translation is authored in the legacy source
    world frame and converted to the part's parent-local frame through the hierarchy matrices, so the
    part's world vertices move by exactly that vector whatever rotation its ancestors carry; a removal
    drops the meshes of the part's whole subtree. Content.load applies these before any bounds are
    taken, so a placement's bounds, turn pivot, grounding and footing all see the edited part.
    Refuses an unknown placement or part, a part outside the placement's subtree, an ambiguous part
    name, a part edited twice, and an entry that does not do exactly one of the two.
    """
    if not entries:return document
    document=dict(document);document['nodes']=[dict(node) for node in document['nodes']]
    matrices,parents=S.GR.hierarchy(document)
    # The index Content.load uses for a placement's node: the last node of that name.
    by_name={n.get('name'):i for i,n in enumerate(document['nodes'])}
    placed={p['node'] for p in placements}
    edited=set()
    for number,entry in enumerate(entries):
        where=f'retained_part_edits[{region!r}][{number}]'
        unknown=sorted(set(entry)-set(PART_EDIT_KEYS))
        if unknown:raise ValueError(f'{where}: unknown key(s) {unknown}; an entry carries {list(PART_EDIT_KEYS)}')
        node,part=entry.get('node'),entry.get('part')
        if not isinstance(node,str) or node not in placed or node not in by_name:
            raise ValueError(f'{where}: {node!r} is not a retained placement in {region}')
        if not isinstance(part,str) or part not in by_name:
            raise ValueError(f'{where}: {node} has no part {part!r}; no node of that name is in the {region} library')
        root=by_name[node]
        if part==node:
            raise ValueError(f'{where}: {part} is the placement itself; a part edit moves or drops one of its parts '
                             '(object edits move and remove whole placements)')
        subtree=S.descendants(document,[root])
        matches=[i for i,n in enumerate(document['nodes']) if n.get('name')==part and i in subtree and i!=root]
        if not matches:raise ValueError(f'{where}: {part} lies outside the subtree of {node}')
        if len(matches)>1:raise ValueError(f'{where}: {node} holds {len(matches)} parts named {part}; name one that is unique')
        index=matches[0]
        if index in edited:raise ValueError(f'{where}: {node} part {part} is edited twice')
        edited.add(index)
        remove,translate=entry.get('remove',False),entry.get('translate')
        if remove not in (True,False):raise ValueError(f'{where}: remove must be true or false, not {remove!r}')
        if remove==(translate is not None):
            raise ValueError(f'{where}: an entry either translates its part or removes it, not {"both" if remove else "neither"}')
        if remove:
            for i in S.descendants(document,[index]):document['nodes'][i].pop('mesh',None)
            continue
        vector=_finite_vector(translate,3)
        if vector is None:raise ValueError(f'{where}: translate must be three finite metres [dx, dy, dz], not {translate!r}')
        # Carried into the parent's frame a world translation is the parent's inverse linear part applied to
        # the vector; an ancestor moved by an earlier entry changes only the parent's translation, so the
        # matrices taken once above still convert it exactly.
        parent=matrices[parents[index]];move=np.eye(4);move[:3,3]=vector
        OE.set_matrix(document['nodes'][index],np.linalg.inv(parent)@move@parent@S.GR.local_matrix(document['nodes'][index]))
    return document


def check_member_offsets(plan,ids):
    """Refuse an "assembly_member_offsets" section that is not {assembly id: {node: vector}} or names a territory the continent lacks."""
    table=(plan or {}).get(MEMBER_OFFSETS)
    if table is None:return {}
    if not isinstance(table,dict):raise ValueError(f'{MEMBER_OFFSETS}: must map assembly ids to {{member node: [dx, dy, dz]}}')
    for identity,entries in table.items():
        region=str(identity).split('.',1)[0]
        if '.' not in str(identity) or region not in ids:
            raise ValueError(f'{MEMBER_OFFSETS}: {identity!r} is not an assembly id of a territory the continent has ({list(ids)})')
        if not isinstance(entries,dict) or not entries:
            raise ValueError(f'{MEMBER_OFFSETS}[{identity!r}]: must map member nodes to three metres [dx, dy, dz]')
        for node,vector in entries.items():
            if _finite_vector(vector,3) is None:
                raise ValueError(f'{MEMBER_OFFSETS}[{identity!r}][{node!r}]: must be three finite metres [dx, dy, dz], not {vector!r}')
    return table


def apply_member_offsets(region,document,body,placements,plan):
    """(document, {node: offset}): the plan's "assembly_member_offsets" for one territory's compounds applied.

    Each entry moves a member's placement root by [dx, dy, dz] metres of the legacy source frame, in a private copy of
    the document, converted to the root's parent-local frame so its world vertices move by exactly that vector; the
    placement's source position moves with it. Content.load applies this after the part edits and before any bounds,
    turn or grouping, so the compound's bounds, footprints, anchor and every later stage see the member where the
    offset puts it, and the compound still moves under one shift. Linked records keep their own source points.
    Refuses an assembly id none of this territory's placements form, a node that is not a member of that compound,
    and a tree or _Wood placement (its foliage roots are separate placements).
    """
    table=(plan or {}).get(MEMBER_OFFSETS) or {}
    mine={identity:offsets for identity,offsets in table.items() if str(identity).split('.',1)[0]==region}
    if not mine:return document,{}
    members={}
    for p in placements:
        group=A.placement_group(region,p,placements)
        if group:members.setdefault(group,{})[p['node']]=p
    document=dict(document);document['nodes']=[dict(node) for node in document['nodes']]
    matrices,parents=S.GR.hierarchy(document)
    by_name={n.get('name'):i for i,n in enumerate(document['nodes'])}
    applied={}
    for identity,offsets in mine.items():
        where=f'{MEMBER_OFFSETS}[{identity!r}]'
        if identity not in members:
            raise ValueError(f'{where}: no compound of that id among the {region} placements (it has {sorted(members)})')
        for node,vector in offsets.items():
            placement=members[identity].get(node)
            if placement is None or node not in by_name:
                raise ValueError(f'{where}: {node!r} is not a member of {identity}')
            if placement.get('kind')=='tree' or node.endswith('_Wood'):
                raise ValueError(f'{where}: {node} carries separate foliage roots and cannot be offset alone')
            vector=_finite_vector(vector,3)
            if vector is None:raise ValueError(f'{where}[{node!r}]: must be three finite metres [dx, dy, dz]')
            index=by_name[node]
            parent=matrices[parents[index]] if index in parents else np.eye(4)
            move=np.eye(4);move[:3,3]=vector
            OE.set_matrix(document['nodes'][index],np.linalg.inv(parent)@move@parent@S.GR.local_matrix(document['nodes'][index]))
            if 'position' in placement:placement['position']=(np.asarray(placement['position'],float)+vector).tolist()
            applied[node]=vector.tolist()
    return document,applied


def retained_attachments(plan,region,placements,edits=None):
    """The plan's "retained_attachments" for one territory: {node: (host, offset)}, hosts before what they carry.

    An attached placement moves rigidly with its host instead of being mapped, pulled and grounded on
    its own (Content.load with attachment_shift): for a legacy vertex v its composed vertex is the
    host's composed turn pivot plus the layout's turn R of (v - host's turn pivot + offset) in x/z, with
    no squeeze, and its vertical shift is the host's plus the offset's dy. ``offset`` [dx, dy, dz] is in
    metres of the legacy source frame (default none). It gets no footing, Content.reground moves it by
    its host's correction, and its linked records follow its shift. A host may itself be attached.
    Refuses an unknown node or host, self-attachment, an object attached twice, a cycle, an attached
    object that belongs to a compound (its compound moves it), a boat as either end (the boat modules
    settle hulls on their own), and object edits that would part the two: any transform edit on the
    attached object, or a yaw or scale edit on its host (a translation of the host is carried).
    """
    entries=retained_section(plan,'retained_attachments',region)
    if not entries:return {}
    by_node={p['node']:p for p in placements}
    attached={}
    for number,entry in enumerate(entries):
        where=f'retained_attachments[{region!r}][{number}]'
        unknown=sorted(set(entry)-set(ATTACHMENT_KEYS))
        if unknown:raise ValueError(f'{where}: unknown key(s) {unknown}; an entry carries {list(ATTACHMENT_KEYS)}')
        node,host=entry.get('node'),entry.get('host')
        for label,name in (('node',node),('host',host)):
            if not isinstance(name,str) or name not in by_node:
                raise ValueError(f'{where}: {label} {name!r} is not a retained placement in {region}')
        if node==host:raise ValueError(f'{where}: {node} cannot be attached to itself')
        if node in attached:raise ValueError(f'{where}: {node} is attached twice')
        offset=_finite_vector(entry.get('offset',[0.,0.,0.]),3)
        if offset is None:raise ValueError(f"{where}: offset must be three finite metres [dx, dy, dz], not {entry.get('offset')!r}")
        group=A.placement_group(region,by_node[node],placements)
        if group:raise ValueError(f'{where}: {node} belongs to the compound {group}, which moves it; only a separate placement can be attached')
        for name in (node,host):
            if any(word in name.lower() for word in HULL_WORDS):
                raise ValueError(f'{where}: {name} is a boat; hulls are settled on their own and can neither carry nor be carried')
        if edits is not None:
            own=edits.transforms.get((region,node))
            if own is not None:
                raise ValueError(f"{where}: {node} rides on {host}, so the object edit {own['root']} cannot move or turn it "
                                 'on its own; edit its host or the attachment offset')
            carried=edits.transforms.get((region,host))
            if carried is not None and (carried.get('yawDegrees',0) or carried.get('scale',1)!=1):
                raise ValueError(f"{where}: {host} carries the yaw or scale object edit {carried['root']}, which {node} cannot follow")
        attached[node]=(host,offset)
    ordered={}
    def place(node,trail):
        if node in ordered:return
        host=attached[node][0]
        if host in trail:raise ValueError(f"retained_attachments[{region!r}]: {' -> '.join(trail+[host])} is a cycle")
        if host in attached:place(host,trail+[host])
        ordered[node]=attached[node]
    for node in attached:place(node,[node])
    return ordered


def attachment_shift(host_shift,host_turn,turn,offset):
    """The shift that carries an attached placement rigidly with its host.

    ``host_turn`` and ``turn`` are the matrices turn_layout turned the host's and the object's roots by,
    each about its own pivot (None where the layout does not turn). The host stands at
    host_turn(u) + host_shift for a legacy point u; the object must stand at host_turn(v + offset) +
    host_shift, and its document already holds turn(v). Both turns carry the layout's one rotation, so v
    cancels and the difference is a constant: host_turn(offset) - turn(0) + host_shift. Under a layout
    that does not turn it is host_shift + offset.
    """
    host_turn=np.eye(4) if host_turn is None else np.asarray(host_turn,float)
    turn=np.eye(4) if turn is None else np.asarray(turn,float)
    if not np.allclose(host_turn[:3,:3],turn[:3,:3],atol=1e-9):
        raise ValueError('An attached placement and its host must turn with one rotation')
    return (host_turn@np.r_[np.asarray(offset,float),1.])[:3]-turn[:3,3]+np.asarray(host_shift,float)


def retained_footings(plan,region,placements,attached=()):
    """The plan's "retained_footings" for one territory: {node: (radius, feather)}.

    A separate retained placement gets a round footing at load: centred on its bounds centre at the
    ground there, full within 0.72 x half its xz bounds diagonal (2 to 38 m) and feathered over
    max(12, 0.7 x that radius), and it overrides the plan's ground (terrain edits included) wherever it
    is full. An entry replaces that circle: ``radius`` in metres, where 0 means no footing at all (the
    placement stands on the ground the plan gives it, typically a terrain edit shaped round it), and an
    optional ``feather`` (metres, above 0; by default the rule above for the given radius). A structure
    without a footing still reaches the router through register_obstacles. Refuses an unknown node, a
    node given twice, a compound member (its compound's footprints are its footing), an attached
    placement (it has none) and a negative or non-finite radius or feather.
    """
    entries=retained_section(plan,'retained_footings',region)
    if not entries:return {}
    by_node={p['node']:p for p in placements}
    footings={}
    for number,entry in enumerate(entries):
        where=f'retained_footings[{region!r}][{number}]'
        unknown=sorted(set(entry)-set(FOOTING_KEYS))
        if unknown:raise ValueError(f'{where}: unknown key(s) {unknown}; an entry carries {list(FOOTING_KEYS)}')
        node=entry.get('node')
        if not isinstance(node,str) or node not in by_node:raise ValueError(f'{where}: {node!r} is not a retained placement in {region}')
        if node in footings:raise ValueError(f'{where}: {node} is given twice')
        group=A.placement_group(region,by_node[node],placements)
        if group:raise ValueError(f'{where}: {node} belongs to the compound {group}, whose footprints are its footing')
        if node in attached:raise ValueError(f'{where}: {node} is attached to a host and has no footing of its own')
        radius=entry.get('radius')
        if isinstance(radius,bool) or not isinstance(radius,(int,float)) or not math.isfinite(radius) or radius<0:
            raise ValueError(f'{where}: radius must be a distance in metres of at least 0, not {radius!r}')
        feather=entry.get('feather',max(12.,float(radius)*.7))
        if isinstance(feather,bool) or not isinstance(feather,(int,float)) or not math.isfinite(feather) or feather<=0:
            raise ValueError(f'{where}: feather must be a distance in metres above 0, not {feather!r}')
        footings[node]=(float(radius),float(feather))
    return footings


def spawn_position(template):
    spawns=template.get('spawnPoints',template.get('spawns',[]))
    default=template.get('navigation',{}).get('defaultSpawn')
    chosen=next((s for s in spawns if s.get('id')==default or s.get('default')),spawns[0] if spawns else {'position':[0,0,0]})
    return np.array(chosen.get('position',[0,0,0]),float)


class Content:
    def __init__(self,world,library,templates,legacy):
        self.world=world;self.library=Path(library);self.templates=templates;self.legacy=legacy
        self.documents={};self.metadata={};self.prototypes={};self.objects=[];self.mapping={};self.source_centers={};self.scales={}
        # A territory's retained transform (None where it keeps the centre/scale rule) and, under a
        # turned layout, the constant part of what each placement carries beyond that transform's own
        # mapping of its source point (see load(); the placement's live shift is the other part).
        self.transforms={};self.residuals={}
        self.placement_by_name={};self.bounds_by_name={}
        self.companions={}
        self.assembly_records={}
        # winding.double_sided_sheets' report per territory whose table entry changed or missed anything.
        self.double_sided={}
        # The plan's assembly_member_offsets as applied: (region, node) -> [dx, dy, dz].
        self.member_offsets={}
        # Placements carried by a host (the plan's retained_attachments): (region, node) -> {'host', 'offset',
        # 'relative': its shift less its host's at load}, and the keys with every host before what it carries.
        self.attachments={};self.attachment_order=[]
        self.ids=world.ids
        self.edits=OE.ObjectEdits(OE.load_edits(),world.ids)
        self.authoring_snapshots=dict(getattr(world,'authoring_snapshots',{}))
        snapshot=getattr(world,'authoring_snapshot',None)
        if snapshot is not None:
            self.authoring_snapshots.setdefault(snapshot.document['regionId'],snapshot)
        self.authored_regions=set(self.authoring_snapshots)
        for region in self.authored_regions:self.edits.exclude_authored_region(region)

    def load_authored_region(self,region,document,body,metadata):
        """Load exact scene objects without legacy mapping, grounding or pads."""
        snapshot=self.authoring_snapshots[region]
        self.documents[region]=(document,body);self.metadata[region]=metadata
        self.transforms[region]=None;self.source_centers[region]=np.zeros(2);self.scales[region]=1.
        matrices,_=S.GR.hierarchy(document)
        # The retained authoring library deliberately reuses prototype
        # subtrees.  A prototype node can therefore have the same name as an
        # authored placement, but only the named roots in the default scene
        # carry that placement's saved matrix.  Looking through every node
        # can select a later nested prototype, inheriting the wrong parent's
        # transform for bounds and then losing that parent during partition.
        scene=document['scenes'][document.get('scene',0)]
        by_name={}
        for index in scene.get('nodes',[]):
            name=document['nodes'][index].get('name')
            if not name:
                raise ValueError(f'{region}: authored retained library has an unnamed scene root')
            if name in by_name:
                raise ValueError(f'{region}: authored retained library has duplicate scene root {name!r}')
            by_name[name]=index
        retained=[];natural=[]
        translation=snapshot.translation
        for placement in metadata['placements']:
            name=placement['node']
            grouped=placement.get('groupedNodes',[name])
            if (not isinstance(grouped,list) or not grouped or grouped[0]!=name or
                    any(not isinstance(value,str) or not value for value in grouped) or
                    len(set(grouped))!=len(grouped)):
                raise ValueError(f'{region}: authored placement {name!r} has invalid grouped scene roots')
            missing=[value for value in grouped if value not in by_name]
            if missing:
                raise ValueError(
                    f'{region}: authored placement {name!r} is missing certified roots {missing}')
            indices=[by_name[value] for value in grouped];index=indices[0]
            bounds=[S.subtree_bounds(document,body,value,matrices) for value in indices]
            low=np.min([value[0] for value in bounds],axis=0)
            high=np.max([value[1] for value in bounds],axis=0)
            shift=translation.copy()
            names={document['nodes'][child].get('name','')
                   for child in S.descendants(document,indices)}
            kind=placement.get('kind','prop')
            obj={'region':region,'index':index,'indices':indices,'shift':shift,
                 'low':low+shift,'high':high+shift,'kind':kind,'node':name,'names':names,
                 'collides':placement.get('collides',False),'walk':placement.get('walk_surface',False),
                 'source':placement,'sourcePivot':(low+high)*.5,
                 'targetGround':float(self.world.height_at(*(low[[0,2]]+high[[0,2]])*.5+translation[[0,2]]))}
            retained.append(obj)
            self.mapping[(region,name)]=shift
            self.placement_by_name[(region,name)]=obj
            self.bounds_by_name[(region,name)]=(low+shift,high+shift)
            if kind in NATURAL:natural.append((placement,index,low,high))
        self.objects.extend(retained);self.prototypes[region]=natural
        print(f'{region}: retained {len(retained)} scene-authored objects, {len(natural)} reusable natural prototypes',flush=True)

    def mapped_xz(self,region,points):
        """Source xz to continent xz. A retained transform carries the whole layout: squeezed and turned
        about its own point, then translated (landscape.retained_map_xz); any other territory keeps the
        centre-and-scale rule. Points may be one pair or an array of them."""
        authored=getattr(self,'authoring_snapshots',{})
        if region in authored:
            return np.asarray(points,float)+authored[region].translation[[0,2]]
        transform=self.transforms.get(region)
        if transform is not None:return L.retained_map_xz(transform,points)
        points=np.asarray(points,float)
        return (points-self.source_centers[region])*self.scales[region]+self.world.regions[region]['center']

    def solid_boxes(self):
        """Retained colliding solids no road alignment should cross: (region, node, low, high)."""
        return [(o['region'],o['node'],np.asarray(o['low'],float),np.asarray(o['high'],float))
                for o in self.objects if o.get('collides') and not o.get('walk') and o.get('kind') not in A.NATURE]

    def register_obstacles(self):
        """Register every retained colliding structure with the router where it finally stands.

        Runs after the prepare stages have moved what they move (the Amberwood
        stall row, the props cleared off the market stair and root ramp strips):
        a structure registered at load and moved afterwards leaves the router
        a phantom solid where nothing stands and none where the structure
        does, and the fifteenth's hub roads were aligned through two moved
        market stalls. With the structures registered where they stand the
        Amberwood hub roads leave the platform east, the cinder chapel door
        road takes a direct line up the hill (234 m, a 21 m cut, in place of a
        495 m loop with a 45 m cut) and the discovery branches south of the
        Great Tree move with them; the Motherroot Voice, whose root plateau
        one of those branches used to reach, stands at the Motherroot mouth
        (amberwood_access.MOTHERROOT_VOICE_POST), and the root ramp joins the
        plateau to the village yard. A gate, arch, arcade, colonnade, causeway
        or portal is built to be passed: it keeps the soft clearance but is no
        solid for alignment.
        """
        count=0
        for o in self.objects:
            if o.get('collides') and not o.get('walk'):
                self.world.structure_obstacle(o['low'],o['high'],solid=not walk_through(o['node']));count+=1
        return count

    def members_dry(self,assembly,source_bounds,shift):
        """Does every member of a compound carried by ``shift`` stand on dry ground? The rule a single is pulled by: the
        member's centre above 0.8 m and out of water deeper than 0.35 m; boats, piers, quays, bridges, causeways, sunken
        pieces and waterfalls (AQUATIC_WORDS) may stand in water."""
        centres=np.array([((np.asarray(source_bounds[node][0],float)+np.asarray(source_bounds[node][1],float))*.5)[[0,2]]
                          for node in assembly.nodes if not any(word in node.lower() for word in AQUATIC_WORDS)])
        if not len(centres):return True
        x,z=centres[:,0]+shift[0],centres[:,1]+shift[2]
        height=np.asarray(self.world.height_at(x,z),float)
        wet=L.water_fields(x,z,height=height,plan=self.world.plan)
        return bool(np.all((height>.8)&~(np.asarray(wet['mask'],bool)&(np.asarray(wet['depth'],float)>.35))))

    def load(self):
        check_retained_sections(self.world.plan,self.ids)
        check_member_offsets(self.world.plan,self.ids)
        for region in self.ids:
            folder=self.library/region
            document,body=S.GR.load(folder/'library.glb')
            # Triangles wound against their own normals are reversed in a private copy before anything reads
            # the geometry (winding.py; README "Inverted winding in retained library meshes").
            document,body,_=W.normalise_winding(document,body)
            # Authored open sheets meant to be seen from both sides (the Sunmane canvases, the Four Gates arcade
            # walls, boats and shrine roofs: winding.DOUBLE_SIDED_SHEETS) render doubleSided in the same private copy.
            document,sides=W.double_sided_sheets(document,W.DOUBLE_SIDED_SHEETS.get(region))
            if sides['materials'] or sides['primitives'] or sides['unmatched']:
                self.double_sided[region]=sides
                print(f"{region}: double-sided sheets: {len(sides['materials'])} materials, {len(sides['primitives'])} primitives"
                      +(f"; unmatched {sides['unmatched']}" if sides['unmatched'] else ''),flush=True)
            metadata=json.loads((folder/'library.json').read_text())
            if region in self.authoring_snapshots:
                marker=metadata.get('continentAuthoring',{})
                if marker.get('snapshotSha256')!=self.authoring_snapshots[region].digest:
                    raise ValueError(f'{region}: retained library was not built from the current authoring snapshot')
                self.load_authored_region(region,document,body,metadata)
                continue
            metadata['placements']=retained_source_placements(region,metadata['placements'])
            if region=='amberwood':
                from amberwood_access import prepare_camp_source
                document,metadata=prepare_camp_source(document,body,metadata,folder)
            # Authored object edits (continent-edits.json): removals before
            # grouping and bounds, rotation/scale on the source roots.
            metadata['placements']=self.edits.filter_placements(region,metadata['placements'])
            region_transform=self.world.plan.get('retained_transforms',{}).get(region)
            self.transforms[region]=region_transform
            # The plan's authored corrections to retained placements: part edits change the document before
            # any bounds are taken; attachments and footings are checked against the same placements.
            document=apply_part_edits(region,document,body,metadata['placements'],
                                      retained_section(self.world.plan,'retained_part_edits',region))
            # Compound members offset in the source frame (the plan's assembly_member_offsets), before any bounds.
            document,offsets=apply_member_offsets(region,document,body,metadata['placements'],self.world.plan)
            self.member_offsets.update({(region,node):vector for node,vector in offsets.items()})
            attachments=retained_attachments(self.world.plan,region,metadata['placements'],self.edits)
            footings=retained_footings(self.world.plan,region,metadata['placements'],attachments)
            turns={}
            ground=np.load(folder/'foundation-samples.npz')
            sample=RegularGridInterpolator((ground['z'],ground['x']),ground['height'],bounds_error=False,fill_value=None)
            def source_height(x,z):
                x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
                return sample(np.c_[z.ravel(),x.ravel()]).reshape(x.shape)
            # A transform that turns carries the whole legacy layout round as one rigid body: every
            # placement turns before its own authored edits, each compound about its reference so it
            # stays rigid, and the compounds keep the anchors they had before the turn.
            yaw=L.retained_yaw_degrees(region_transform) if region_transform is not None else 0.
            unmap=(lambda x,z:L.retained_unmap_xz(region_transform,x,z)) if yaw else None
            references=None;legacy_bounds={}
            if yaw:
                legacy_bounds=placement_bounds(document,body,metadata['placements'])
                anchored=A.build_assemblies(region,metadata['placements'],legacy_bounds,source_height)
                references={identity:assembly.reference_xz for identity,assembly in anchored.items()}
                document=turn_layout(document,body,metadata['placements'],yaw,
                    {node:assembly.reference_xz for assembly in anchored.values() for node in assembly.nodes},turns=turns)
            document=self.edits.prepare_document(region,document,body,metadata['placements'])
            self.documents[region]=(document,body)
            self.metadata[region]=metadata
            matrices,parents=S.GR.hierarchy(document)
            by_name={n.get('name'):i for i,n in enumerate(document['nodes'])}
            foliage={}
            for placement in metadata['placements']:
                if placement.get('kind')=='foliage' and placement['node'] in by_name:
                    foliage.setdefault(tuple(np.round(placement['position'],4)),[]).append(by_name[placement['node']])
            attached_foliage=set()
            for placement in metadata['placements']:
                if placement.get('kind')=='tree' or placement['node'].endswith('_Wood'):
                    attached_foliage.update(foliage.get(tuple(np.round(placement['position'],4)),[]))
            # Geographic centres are territory labels; the inhabited arrival is
            # the retained local composition's datum within that territory.
            center=spawn_position(self.templates[region])[[0,2]]
            self.source_centers[region]=center
            self.scales[region]=.78 if region!='four_gates' else .90
            if region_transform:
                # One transform for the whole layout: a rigid translation, or a translation with a
                # north-south squeeze and a turn about a source point. The published summary only.
                self.source_centers[region],self.scales[region]=retained_source_center(region_transform,self.world.regions[region]['center'])
            source_bounds={p['node']:S.subtree_bounds(document,body,by_name[p['node']],matrices)
                           for p in metadata['placements'] if p['node'] in by_name}
            groups=A.build_assemblies(region,metadata['placements'],source_bounds,source_height,references=references)
            group_shifts={}
            for identity,assembly in groups.items():
                site=self.world.plan.get('assembly_sites',{}).get(identity,{})
                authored_transform=site.get('translation')
                if authored_transform is None and region_transform:
                    # The territory's transform taken at the compound's reference
                    # point, so a squeezed layout moves each compound whole; with
                    # a ground datum the compound stands on the composed relief.
                    translation=L.retained_affine(region_transform)[0];reference=np.asarray(assembly.reference_xz,float)
                    mapped=self.mapped_xz(region,reference)
                    grounded=isinstance(region_transform,dict) and region_transform.get('datum')=='ground'
                    lift=float(self.world.height_at(*mapped))-float(assembly.reference_y) if grounded else float(translation[1])
                    authored_transform=[float(mapped[0]-reference[0]),lift,float(mapped[1]-reference[1])]
                shift=assembly.shift_to(lambda p:self.mapped_xz(region,p),self.world.height_at,
                    water_level=site.get('water_level',0.),target_xz=site.get('center'))
                if authored_transform is not None:
                    # An explicit authored relocation, such as a discovery
                    # moved into an accessible side gallery, keeps every
                    # linked point and all of its geometry on one transform.
                    shift=np.asarray(authored_transform,float).copy()
                    if shift.shape!=(3,) or not np.isfinite(shift).all():
                        raise ValueError(identity+': authored translation must contain three finite metres')
                # Move a whole compound when an edge would leave its territory.
                # No component acquires a private XZ or vertical correction.
                hub=np.asarray(self.world.regions[region]['center'],float)
                member_points=np.array([[x,z] for node in assembly.nodes
                    for x in (source_bounds[node][0][0],source_bounds[node][1][0])
                    for z in (source_bounds[node][0][2],source_bounds[node][1][2])])
                # A pulled site (assemblies.PULLED_SITES) steps finer and may need dry ground as well (assemblies.SITE_PULL).
                step,steps,needs_dry=A.SITE_PULL.get(identity,A.PULL)
                for _ in range(0 if authored_transform is not None else steps):
                    points=member_points+shift[[0,2]]
                    if np.all(self.world.owner_at(points[:,0],points[:,1])==self.ids.index(region)) and (not needs_dry or self.members_dry(assembly,source_bounds,shift)):break
                    target=assembly.reference_xz+shift[[0,2]];shift[[0,2]]+=(hub-target)*step
                if authored_transform is None and assembly.datum=='terrain':
                    anchor=assembly.reference_xz+shift[[0,2]]
                    shift[1]=float(self.world.height_at(*anchor))-assembly.reference_y
                elif authored_transform is None and assembly.datum=='footprints':
                    shift[1]=assembly.footprint_lift(self.world.height_at,source_height,shift,unmap=unmap)
                group_shifts[identity]=shift
                self.assembly_records[identity]=dict(A.report(assembly),translation=shift.tolist())
                feather=32. if identity=='mirrorhold.city' else 24.
                margin=feather+12.
                low=assembly.bounds[0,[0,2]]+shift[[0,2]]-margin;high=assembly.bounds[1,[0,2]]+shift[[0,2]]+margin
                ix0=max(0,int((low[0]-self.world.x0)/2));ix1=min(len(self.world.x),int((high[0]-self.world.x0)/2)+2)
                iz0=max(0,int((low[1]-self.world.z0)/2));iz1=min(len(self.world.z),int((high[1]-self.world.z0)/2)+2)
                sl=np.s_[iz0:iz1,ix0:ix1]
                target,weight=assembly.sample_foundation(self.world.gx[sl],self.world.gz[sl],shift,source_height,feather=feather,unmap=unmap)
                if region=='manymouth_delta' and assembly.datum=='water':
                    # Stilt floors sit above wet ground. Legacy survey terraces
                    # cannot become banks poking through their intact porches.
                    target=np.minimum(target,shift[1]+1.)
                if identity in ('manymouth_delta.north_fishing','manymouth_delta.paddy_hamlet',
                                'manymouth_delta.west_hamlet','manymouth_delta.east_hamlet'):
                    # These intact groups occupy real low coast or upper banks.
                    # Their former regional surveys contain deep trenches;
                    # retain the natural seabed and only lower occupied bank
                    # beneath the stilt floors, with the normal soft apron.
                    target=np.minimum(self.world.original_height[sl],shift[1]+1.)
                    if identity=='manymouth_delta.east_hamlet':
                        # The occupied upper-bank yards share one soil datum.
                        # Fill the slightly lower lore-court end as well as
                        # cutting the hillward side; keep the local footprint
                        # mask and feather instead of making a rectangular pad.
                        target=np.full(target.shape,shift[1]+1.)
                self.world.assembly_foundation(sl,target,weight)
            retained=[];natural=[]
            # Carried placements come after every other, hosts before what they carry, so each finds its host's
            # final shift; the retained list is put back in the library's order below.
            rank={node:number for number,node in enumerate(attachments)}
            carried=sorted((p for p in metadata['placements'] if p['node'] in rank),key=lambda p:rank[p['node']])
            for p in [p for p in metadata['placements'] if p['node'] not in rank]+carried:
                index=by_name.get(p['node'])
                if index is None: continue
                name=p['node'];kind=p.get('kind','prop')
                host=attachments.get(name)
                if kind=='foliage' and index in attached_foliage:continue
                assembly_id=A.placement_group(region,p,metadata['placements'])
                if name.startswith('Walk_Survey_'):continue
                if any(token in name for token in ('_Stream','StreamView_','Backdrop_')) or name.startswith(('March_','MarchGate_')): continue
                low,high=S.subtree_bounds(document,body,index,matrices)
                if kind=='tree' or name.endswith('_Wood'):
                    companions=foliage.get(tuple(np.round(p['position'],4)),[])
                    self.companions[(region,index)]=companions
                    for companion in companions:
                        c_low,c_high=S.subtree_bounds(document,body,companion,matrices)
                        low=np.minimum(low,c_low);high=np.maximum(high,c_high)
                if not np.isfinite(low).all():continue
                # A structure's natural companions (assemblies.companions) are retained with it and stay prototypes for
                # the ecological scatter as well: the Sunmane EarthRocks are the steppe's only rocks.
                natural_companion=bool(assembly_id) and name in A.companions(region,metadata['placements'])
                if kind in NATURAL and not p.get('landmark') and (not assembly_id or natural_companion):
                    if kind in ('tree','rock','fern','undergrowth','scrub','stump','fallenlog','mushrooms','leafdrift') and .05<high[1]-low[1]<30: natural.append((p,index,low,high))
                    if not assembly_id:continue
                # Former regional paths are replaced by continent roads. Keep
                # architectural floors, bridges, streets and named discoveries.
                if not p.get('landmark') and (kind in ('road','path','terrain','ground') or name.startswith(('Road_','Path_','Track_','Soil_','Walk_Road_','Walk_Path_','Walk_Track_'))):continue
                pivot=(low+high)*.5
                old_xz=pivot[[0,2]]
                new_xz=self.mapped_xz(region,old_xz)
                owner=int(self.world.owner_at(*new_xz));expected=self.ids.index(region)
                # Pull peripheral decorative structures inside their named
                # territory. The exact displacement follows linked metadata.
                hub=np.array(self.world.regions[region]['center'],float)
                radius=float(np.linalg.norm((high-low)[[0,2]])*.5)
                for _ in range(0 if assembly_id or host else 24):
                    samples=np.array([new_xz+[dx,dz] for dx,dz in ((0,0),(radius+3,0),(-radius-3,0),(0,radius+3),(0,-radius-3))])
                    owned=np.all(self.world.owner_at(samples[:,0],samples[:,1])==expected)
                    aquatic=any(word in name.lower() for word in AQUATIC_WORDS)
                    ground_height=float(self.world.height_at(*new_xz))
                    wet=L.water_fields(*new_xz,height=ground_height,plan=self.world.plan)
                    dry=aquatic or (ground_height>.8 and not (wet['mask'] and wet['depth']>.35))
                    if owned and dry:break
                    new_xz=hub+(new_xz-hub)*.90
                source_xz=old_xz
                if unmap is not None and assembly_id:
                    # The turn moved this member inside its compound; the legacy ground it was surveyed
                    # on lies under the continent point carried back through the layout's mapping.
                    source_xz=np.asarray(unmap(*(old_xz+group_shifts[assembly_id][[0,2]])),float)
                source_ground=float(sample([[source_xz[1],source_xz[0]]])[0])
                # Regional surveys left some ground-standing props buried in
                # their own terrain (Whitehorn cairns up to 30 m under it). A
                # compact prop whose base lies under the legacy ground stands
                # on the ground here. Props above the ground may rest on decks
                # or rocks and keep their authored offset, as do landmarks,
                # buildings and buried crystals; hulls are settled on water.
                hull=any(word in name.lower() for word in HULL_WORDS)
                if kind=='prop' and not assembly_id and not hull and source_ground-float(low[1])>BURIED_PROP_METRES:
                    source_ground=float(low[1])-.02
                elif (kind=='prop' and not assembly_id and not hull and float(low[1])-source_ground>FLOATING_PROP_METRES
                      and not any(word in name.lower() for word in FLOATING_BY_DESIGN)):
                    source_ground=float(low[1])-.02
                target_ground=float(self.world.height_at(*new_xz))
                # Large inhabited compounds retain their internal grade. The
                # continent supplies a broad landing around their footprint.
                if region in ('manymouth_delta','crownwater') and source_ground<1.5 and target_ground<1.5:
                    target_ground=max(-1.,min(target_ground,1.))
                else:target_ground=max(.8,target_ground)
                shift=np.array([new_xz[0]-old_xz[0],target_ground-source_ground,new_xz[1]-old_xz[1]])
                if assembly_id:
                    shift=group_shifts[assembly_id].copy();new_xz=old_xz+shift[[0,2]]
                    target_ground=source_ground+shift[1]
                    if region=='manymouth_delta' and groups[assembly_id].datum=='water':target_ground=min(source_ground,1.)+shift[1]
                if host is not None:
                    # Carried rigidly by its host: no mapping, pull or grounding of its own.
                    carrier=self.placement_by_name.get((region,host[0]))
                    if carrier is None:
                        raise ValueError(f'retained_attachments[{region!r}]: {name} rides on {host[0]}, which is not a retained '
                                         'structure (natural prototypes, roads, streams and marches are not placed)')
                    if yaw and (host[0] not in turns or name not in turns):
                        raise ValueError(f'retained_attachments[{region!r}]: {name} or its host {host[0]} did not turn with the layout')
                    shift=attachment_shift(carrier['shift'],turns.get(host[0]),turns.get(name),host[1])
                    new_xz=old_xz+shift[[0,2]];target_ground=source_ground+shift[1]
                edit=self.edits.translation(region,name)
                if edit is not None:
                    new_xz,shift,target_ground=self.edits.apply_translation(self.world,region,edit,assembly_id,old_xz,new_xz,source_ground)
                all_names={document['nodes'][i].get('name','') for i in S.descendants(document,[index])}
                obj={'region':region,'index':index,'indices':[index,*self.companions.get((region,index),[])],'shift':shift,'low':low+shift,'high':high+shift,
                     'kind':kind,'node':name,'names':all_names,'collides':p.get('collides',False),
                     'walk':p.get('walk_surface',False),'source':p,'sourcePivot':pivot,'targetGround':target_ground}
                if assembly_id:obj['assembly']=assembly_id
                if host is not None:
                    obj['attachment']={'host':host[0],'offset':host[1].tolist()}
                    self.attachments[(region,name)]={'host':host[0],'offset':host[1].tolist(),'relative':shift-carrier['shift']}
                    self.attachment_order.append((region,name))
                retained.append(obj)
                self.mapping[(region,name)]=shift
                if yaw:
                    # This and the placement's own shift are together what it carries beyond the layout's
                    # mapping of its source point: the pull inside the territory, its grounding and any
                    # authored move. A linked record is mapped with the layout and then carried by both,
                    # so it keeps its place on the object, and a later stage that moves the object (the
                    # shift, in place) moves its records with it.
                    legacy=legacy_bounds.get(name)
                    base=((legacy[0]+legacy[1])*.5)[[0,2]] if legacy is not None else old_xz
                    self.residuals[(region,name)]=old_xz-np.asarray(L.retained_map_xz(region_transform,base),float)
                self.placement_by_name[(region,name)]=obj
                self.bounds_by_name[(region,name)]=(low+shift,high+shift)
                # Obstacles reach the router through register_obstacles once the
                # prepare stages have moved what they move (build_continent,
                # before plan_connections).
                # Avoid raising seabed for docks; their piers are authored to
                # support the walk surface above the common estuary water.
                if not assembly_id and host is None and (source_ground>=1.5 or target_ground>=1.5 or region not in ('manymouth_delta','crownwater')):
                    footprint=min(38,max(2,radius*.72));feather=max(12,footprint*.7)
                    # An authored footing (the plan's retained_footings) replaces the circle; radius 0 is none.
                    if name in footings:footprint,feather=footings[name]
                    if footprint>0:
                        self.world.foundation(new_xz,footprint,target_ground,feather=feather,obstacle=p.get('collides',False) and not p.get('walk_surface',False))
            unplaced=sorted(node for node in [*attachments,*footings] if (region,node) not in self.placement_by_name)
            if unplaced:
                raise ValueError(f'{region}: the plan attaches or foots {unplaced}, which are not retained structures '
                                 '(natural prototypes, roads, streams and marches are not placed)')
            if rank:
                order={id(p):number for number,p in enumerate(metadata['placements'])}
                retained.sort(key=lambda obj:order[id(obj['source'])])
            self.objects.extend(retained)
            self.prototypes[region]=natural
            print(f'{region}: retained {len(retained)} structures/landmarks, {len(natural)} natural prototypes',flush=True)
        self.edits.check_loaded(self)
        self.edits.add_copies(self.world,self)
        if self.edits:print(f"Object edits: {len(self.edits.report['removed'])} removed, {len(self.edits.report['transformed'])} transformed, {len(self.edits.report['added'])} added",flush=True)

    def carried_point(self,region,point,anchor,shift):
        """A linked record carried by the retained object ``anchor``: the object's own displacement, or,
        under a turned layout, the record's source point mapped with the layout, so its offset from the
        object turns with it, plus what that object carries beyond the mapping (its residual and the
        shift it stands at now)."""
        residual=self.residuals.get(anchor) if anchor else None
        if residual is None:return point+shift
        x,z=np.asarray(L.retained_map_xz(self.transforms[region],point[[0,2]]),float)+residual+shift[[0,2]]
        return np.array([x,point[1]+shift[1],z])

    def mapped_point(self,region,point,node=None,landmark=None):
        point=np.array(point,float)
        if region in self.authoring_snapshots:
            return self.authoring_snapshots[region].continent_point(point)
        anchor=(region,node) if node else None
        shift=self.mapping.get(anchor) if anchor else None
        if shift is None and landmark:
            anchor=None
            entry=next((p for p in self.metadata[region]['placements'] if p.get('landmark')==landmark),None)
            if entry:
                shift=self.mapping.get((region,entry['node']))
                if shift is not None:anchor=(region,entry['node'])
        if shift is None:
            anchor=None;transform=self.transforms.get(region)
            # A turn moves a compound's members away from their source frame, so a record with no link
            # of its own is measured against the objects where they stand, in continent metres.
            probe=(np.asarray(L.retained_map_xz(transform,point[[0,2]]),float)
                   if transform is not None and L.retained_yaw_degrees(transform) else None)
            nearby=[]
            for obj in self.objects:
                if obj['region']!=region or obj.get('kind') in NATURAL or 'sourcePivot' not in obj:continue
                low=obj['low']-obj['shift'];high=obj['high']-obj['shift'];pivot=obj['sourcePivot'][[0,2]];here=point[[0,2]]
                if probe is not None:low=obj['low'];high=obj['high'];pivot=((low+high)*.5)[[0,2]];here=probe
                outside=np.maximum(np.maximum(low[[0,2]]-here,here-high[[0,2]]),0)
                distance=float(np.linalg.norm(outside))
                if distance<=24:nearby.append((distance+.005*np.linalg.norm(here-pivot),obj))
            if nearby:
                candidate=min(nearby,key=lambda p:p[0])[1]
                mapped=self.carried_point(region,point,(candidate['region'],candidate['node']),candidate['shift'])
                if int(self.world.owner_at(mapped[0],mapped[2]))==self.ids.index(region):
                    shift=candidate['shift'];anchor=(candidate['region'],candidate['node'])
        if shift is not None:return self.carried_point(region,point,anchor,shift)
        x,z=self.mapped_xz(region,point[[0,2]])
        hub=np.asarray(self.world.regions[region]['center'],float)
        for _ in range(40):
            h=float(self.world.height_at(x,z))
            water=L.water_fields(x,z,height=h,plan=self.world.plan)
            if int(self.world.owner_at(x,z))==self.ids.index(region) and not (water['mask'] and water['depth']>.35):break
            x,z=hub+(np.array([x,z])-hub)*.90
        return np.array([x,float(self.world.height_at(x,z)),z])

    def mapped_server_point(self,region,tile,roads=False):
        """Use the authoritative tile and its linked architectural transform.

        A pinned tile answers with its pin, except to a road builder (``roads``) when the plan's authored point keeps
        its roads on the entrance (authored_points "roads": "entrance")."""
        authored=getattr(self,'authored_server_points',{}).get((region,tuple(tile)))
        if authored is not None and not (roads and (region,tuple(tile)) in getattr(self,'entrance_road_tiles',())):
            return np.asarray(authored,float).copy()
        entries=[]
        def visit(value):
            if isinstance(value,list):
                for entry in value:visit(entry)
            elif isinstance(value,dict):
                old=value.get('serverTile',value.get('server_tile'))
                if old is not None and tuple(old)==tuple(tile):entries.append(value)
                for entry in value.values():
                    if isinstance(entry,(dict,list)):visit(entry)
        visit(self.templates[region])
        entry=next((e for e in entries if e.get('doorNode') or e.get('node')),entries[0] if entries else {})
        origin=self.templates[region]['coordinateTransform']['serverOrigin']
        point=[tile[0]+.5-origin[0],0.,origin[1]-tile[1]-.5]
        return self.mapped_point(region,point,entry.get('node',entry.get('doorNode')),entry.get('landmark'))

    def reground(self):
        """Settle footings after overlapping village terraces and roads agree.

        A placement carried by a host (retained_attachments) is not settled on the ground under it: it moves
        by its host's correction, so the two stay one rigid body. Attachments are carried at load and here
        only, so a stage that has moved either of the two on its own since load is refused."""
        corrections={}
        for obj in self.objects:
            if obj['region'] in self.authored_regions:continue
            if obj.get('assembly') or obj.get('attachment'):continue
            pivot=(obj['low']+obj['high'])*.5
            difference=float(self.world.height_at(pivot[0],pivot[2]))-obj['targetGround']
            obj['shift'][1]+=difference;obj['low'][1]+=difference;obj['high'][1]+=difference
            obj['targetGround']+=difference
            self.bounds_by_name[(obj['region'],obj['node'])]=(obj['low'],obj['high'])
            corrections[(obj['region'],obj['node'])]=difference
        for region,node in getattr(self,'attachment_order',()):
            obj=self.placement_by_name[(region,node)];record=self.attachments[(region,node)]
            host=self.placement_by_name[(region,record['host'])]
            difference=corrections.get((region,record['host']),0.)
            obj['shift'][1]+=difference;obj['low'][1]+=difference;obj['high'][1]+=difference
            obj['targetGround']+=difference
            self.bounds_by_name[(region,node)]=(obj['low'],obj['high'])
            corrections[(region,node)]=difference
            if not np.allclose(np.asarray(obj['shift'],float)-np.asarray(host['shift'],float),record['relative'],rtol=0,atol=1e-6):
                raise ValueError(f"{region}:{node} rides on {record['host']}, but a stage after load moved one of the two on its "
                                 'own; attachments are carried only at load and by reground')
        for identity in self.assembly_records:
            A.assert_rigid([obj for obj in self.objects if obj.get('assembly')==identity])

    def scatter_structures(self):
        """The composed ground cells ecological scatter keeps out of: the real footprints of retained buildings.

        Every retained placement where it finally stands, object-edit moves and copies included, rasterised by
        structure_cells from its own triangles (a footprint circle or box would close the ground round a long
        gatehouse or a diagonal arcade). Left out, by exported root name (scatter_blocking_root): the scatter
        itself, props, walk surfaces, and the landform and floating families in SCATTER_THROUGH_PREFIXES;
        terrain, water, bridges and access geometry are generated, not retained placements. Documents'
        hierarchies and mesh triangles are read once per territory. Records its size and cost in
        ``scatter_structure_report``.
        """
        started=time.monotonic()
        mask=np.zeros(np.shape(self.world.height),bool)
        cell=float(self.world.x[1]-self.world.x[0])
        cache={};batch=[];pending=0;roots=0;triangles=0
        for obj in self.objects:
            if 'libraryRegion' in obj:continue
            region=obj['region'];document,body=self.documents[region]
            if id(document) not in cache:cache[id(document)]=(S.GR.hierarchy(document)[0],{})
            matrices,meshes=cache[id(document)]
            shift=np.asarray(obj['shift'],float)
            for root in obj.get('indices',[obj['index']]):
                if not scatter_blocking_root(region,obj.get('nodePrefix','')+document['nodes'][root].get('name','')):continue
                roots+=1
                for index in S.descendants(document,[root]):
                    node=document['nodes'][index]
                    if 'mesh' not in node:continue
                    if node['mesh'] not in meshes:meshes[node['mesh']]=mesh_triangles(document,body,node['mesh'])
                    local=meshes[node['mesh']]
                    if not len(local):continue
                    matrix=matrices[index]
                    batch.append(local@matrix[:3,:3].T+matrix[:3,3]+shift);pending+=len(local);triangles+=len(local)
                    if pending>=200000:
                        structure_cells(np.concatenate(batch),self.world.height,self.world.x0,self.world.z0,cell,mask=mask);batch=[];pending=0
        if batch:structure_cells(np.concatenate(batch),self.world.height,self.world.x0,self.world.z0,cell,mask=mask)
        self.scatter_structure_report={'roots':roots,'triangles':triangles,'cells':int(mask.sum()),
                                       'seconds':round(time.monotonic()-started,2),'refused':{'tree':0,'rock':0,'undergrowth':0}}
        return mask

    def ecological_scatter(self):
        structures=self.scatter_structures();refused=self.scatter_structure_report['refused']
        def in_structure(kind,px,pz):
            # Asked after the candidate's counter has advanced, so every later name stays where it was.
            row=min(max(int(math.floor((pz-self.world.z0)/2)),0),len(self.world.z)-1)
            column=min(max(int(math.floor((px-self.world.x0)/2)),0),len(self.world.x)-1)
            if structures[row,column]:refused[kind]+=1;return True
            return False
        rng=np.random.default_rng(self.world.plan['seed']+481)
        xs=np.arange(self.world.x0+6,self.world.x1,9.)
        zs=np.arange(self.world.z0+6,self.world.z1,9.)
        gx,gz=np.meshgrid(xs,zs)
        x=gx.ravel()+rng.uniform(-3.8,3.8,gx.size);z=gz.ravel()+rng.uniform(-3.8,3.8,gz.size)
        h=self.world.height_at(x,z)
        ec=L.vegetation_fields(x,z,height=h,plan=self.world.plan)
        road=triangle_road(self.world,x,z)
        blocked=self.world.obstacles[np.clip(((z-self.world.z0)/2).astype(int),0,len(self.world.z)-1),np.clip(((x-self.world.x0)/2).astype(int),0,len(self.world.x)-1)]
        wet=L.water_fields(x,z,height=h,plan=self.world.plan)
        slope=np.hypot((self.world.height_at(x+2,z)-self.world.height_at(x-2,z))/4,(self.world.height_at(x,z+2)-self.world.height_at(x,z-2))/4)
        count=0
        for i in np.flatnonzero((rng.random(len(x))<np.clip(ec['tree_density'],0,1)) & (h>.8)&(~wet['mask'])&(road>1.9)&(~blocked)&(slope<.65)):
            region=self.ids[int(self.world.owner_at(x[i],z[i]))]
            if ec['conifer'][i]>.45: source='whitehorn_range'
            elif z[i]>980 and x[i]>800:source='verdant_stair' if rng.random()<.6 else 'ssarathi_ruins'
            elif ec['dryness'][i]>.55:source='sunmane_steppe'
            elif ec['deciduous'][i]>.4:source='amberwood' if rng.random()<.7 else 'grey_moors'
            else:source='grey_moors'
            pool=[p for p in self.prototypes.get(source,[]) if p[0]['kind']=='tree']
            if not pool:continue
            p,index,low,high=pool[int(rng.integers(len(pool)))]
            center=(low+high)*.5
            # Root contact uses the lower trunk, not the placement origin.
            shift=np.array([x[i]-center[0],h[i]-low[1]+.025,z[i]-center[2]])
            doc,_=self.documents[source]
            count+=1
            if region in self.authored_regions:continue
            if self.edits.skips_scatter('tree',x[i],z[i]):continue
            if in_structure('tree',x[i],z[i]):continue
            self.objects.append({'region':region,'libraryRegion':source,'index':index,'shift':shift,
                'indices':[index,*self.companions.get((source,index),[])],
                'low':low+shift,'high':high+shift,'kind':'tree','node':f'Grove_{count:05d}',
                'nodePrefix':f'Grove_{count:05d}_','names':set(),'collides':False,'walk':False})
        print(f'Continental ecology: {count} trees placed in moist, sheltered, clear ground',flush=True)
        formations=0
        # A few exposed outcrops and their related debris, with generous quiet
        # ground between them. Regional libraries keep their geology/materials.
        candidates=(h>1)&(~wet['mask'])&(road>3)&(~blocked)&(slope>.16)&(slope<.62)
        for i in np.flatnonzero(candidates & (rng.random(len(x))<.028)):
            region=self.ids[int(self.world.owner_at(x[i],z[i]))]
            pool=[p for p in self.prototypes.get(region,[]) if p[0]['kind']=='rock']
            if not pool:continue
            pool=sorted(pool,key=lambda p:np.prod(p[3]-p[2]))
            selected=[pool[int(rng.integers(max(1,len(pool)//2),len(pool)))]] if len(pool)>1 else pool
            selected+= [pool[int(rng.integers(max(1,len(pool)//2)))]] * int(rng.integers(1,4))
            formations+=1
            for j,(p,index,low,high) in enumerate(selected):
                xx=x[i]+(rng.uniform(-4,4) if j else 0);zz=z[i]+(rng.uniform(-4,4) if j else 0)
                if int(self.world.owner_at(xx,zz))!=self.ids.index(region):continue
                if region in self.authored_regions:continue
                if self.edits.skips_scatter('rock',xx,zz):continue
                if in_structure('rock',xx,zz):continue
                y=float(self.world.height_at(xx,zz));center=(low+high)*.5
                shift=np.array([xx-center[0],y-low[1]-.12,zz-center[2]])
                self.objects.append({'region':region,'libraryRegion':region,'index':index,'shift':shift,
                    'low':low+shift,'high':high+shift,'kind':'rock','node':f'Outcrop_{formations:04d}_{j}',
                    'nodePrefix':f'Outcrop_{formations:04d}_{j}_','names':set(),'collides':False,'walk':False})
        print(f'Continental geology: {formations} related rock formations',flush=True)
        undergrowth=0
        pockets=(h>.8)&(~wet['mask'])&(road>2.2)&(~blocked)&(slope<.5)&(ec['tree_density']>.20)
        for i in np.flatnonzero(pockets & (rng.random(len(x))<.13)):
            region=self.ids[int(self.world.owner_at(x[i],z[i]))]
            source='verdant_stair' if z[i]>980 and x[i]>800 else ('amberwood' if ec['deciduous'][i]>.3 else region)
            pool=[p for p in self.prototypes.get(source,[]) if p[0]['kind'] in ('fern','undergrowth','stump','fallenlog','mushrooms','leafdrift')]
            if not pool:continue
            p,index,low,high=pool[int(rng.integers(len(pool)))];center=(low+high)*.5
            shift=np.array([x[i]-center[0],h[i]-low[1]-.025,z[i]-center[2]])
            undergrowth+=1
            if region in self.authored_regions:continue
            if self.edits.skips_scatter('undergrowth',x[i],z[i]):continue
            if in_structure('undergrowth',x[i],z[i]):continue
            self.objects.append({'region':region,'libraryRegion':source,'index':index,'shift':shift,
                'low':low+shift,'high':high+shift,'kind':'undergrowth','node':f'WoodlandFloor_{undergrowth:04d}',
                'nodePrefix':f'WoodlandFloor_{undergrowth:04d}_','names':set(),'collides':False,'walk':False})
        print(f'Continental woodland floor: {undergrowth} sheltered undergrowth pockets',flush=True)
        report=self.scatter_structure_report
        print(f"Scatter kept out of retained buildings: {refused['tree']} trees, {refused['rock']} outcrop pieces and "
              f"{refused['undergrowth']} undergrowth pockets refused ({report['roots']} roots, {report['triangles']} triangles, "
              f"{report['cells']} cells, {report['seconds']} s)",flush=True)


def scatter_blocking_root(region,name):
    """Is the exported root of a retained node ``name`` (its node prefix included) a building scatter keeps out of?"""
    root=f'{region}_{name}'
    return not (any(token in root for token in SCATTER_OPEN_ROOT_TOKENS)
                or any('_'+prefix in root for prefix in SCATTER_THROUGH_PREFIXES))


def mesh_triangles(document,body,mesh):
    """(n, 3, 3) mesh-local triangles of one glTF mesh: its triangle primitives with readable positions."""
    out=[]
    for primitive in document['meshes'][mesh]['primitives']:
        position=primitive['attributes'].get('POSITION')
        if primitive.get('mode',4)!=4 or position is None or 'bufferView' not in document['accessors'][position]:continue
        points=S.GR.accessor(document,body,position).astype(np.float64)
        order=(S.GR.accessor(document,body,primitive['indices']).reshape(-1).astype(np.int64)
               if 'indices' in primitive else np.arange(len(points)))
        out.append(points[order[:len(order)//3*3]].reshape(-1,3,3))
    return np.concatenate(out) if out else np.zeros((0,3,3))


def structure_cells(triangles,height,x0,z0,cell,rise=STRUCTURE_RISE_METRES,reach=STRUCTURE_REACH_METRES,mask=None,budget=1<<20):
    """Mark the ground cells a structure's triangles stand over; returns a boolean grid shaped like ``height``.

    ``height`` is the ground sampled at grid nodes (x0 + column * cell, z0 + row * cell); cell (row, column) is
    the square from that node to the next, and the ground anywhere in it is at least its lowest corner (the
    composed ground interpolates between them). A triangle marks every cell its x/z projection reaches within
    ``reach`` metres (the cell grown by ``reach`` on every side, tested exactly against the triangle's own
    edges, so a long diagonal wall marks its own strip and not its bounding box) where its highest vertex
    stands more than ``rise`` above that cell's lowest corner. ``mask``, when given, is updated in place.
    Vectorised over (triangle, cell) pairs, ``budget`` pairs at a time.
    """
    height=np.asarray(height,float);rows,cols=height.shape
    mask=np.zeros(height.shape,bool) if mask is None else mask
    tri=np.asarray(triangles,float).reshape(-1,3,3)
    if not len(tri) or rows<2 or cols<2:return mask
    floor=np.minimum(np.minimum(height[:-1,:-1],height[:-1,1:]),np.minimum(height[1:,:-1],height[1:,1:]))
    px,pz,top=tri[:,:,0],tri[:,:,2],tri[:,:,1].max(axis=1)
    lx=np.floor((px.min(axis=1)-reach-x0)/cell);hx=np.floor((px.max(axis=1)+reach-x0)/cell)
    lz=np.floor((pz.min(axis=1)-reach-z0)/cell);hz=np.floor((pz.max(axis=1)+reach-z0)/cell)
    chosen=np.flatnonzero((hx>=0)&(lx<=cols-2)&(hz>=0)&(lz<=rows-2)&(top>floor.min()+rise))
    if not len(chosen):return mask
    ix0=np.clip(lx[chosen],0,cols-2).astype(np.int64);nx=np.clip(hx[chosen],0,cols-2).astype(np.int64)-ix0+1
    iz0=np.clip(lz[chosen],0,rows-2).astype(np.int64);nz=np.clip(hz[chosen],0,rows-2).astype(np.int64)-iz0+1
    count=nx*nz;ends=np.cumsum(count);start=0;half=cell*.5+reach
    while start<len(chosen):
        stop=max(start+1,int(np.searchsorted(ends,(ends[start-1] if start else 0)+budget,side='right')))
        pair=np.repeat(np.arange(start,stop),count[start:stop])
        k=np.arange(len(pair))-np.repeat(ends[start:stop]-count[start:stop]-(ends[start-1] if start else 0),count[start:stop])
        cx=ix0[pair]+k%nx[pair];cz=iz0[pair]+k//nx[pair];t=chosen[pair]
        high=top[t]>floor[cz,cx]+rise
        cx,cz,t=cx[high],cz[high],t[high]
        X,Z=px[t],pz[t];centre_x=x0+(cx+.5)*cell;centre_z=z0+(cz+.5)*cell
        apart=np.zeros(len(t),bool)
        for edge in range(3):
            # Separating axis: this edge's normal. The cell's own axes overlap by construction.
            normal_x=Z[:,edge]-Z[:,(edge+1)%3];normal_z=X[:,(edge+1)%3]-X[:,edge]
            projection=X*normal_x[:,None]+Z*normal_z[:,None]
            middle=centre_x*normal_x+centre_z*normal_z;extent=half*(np.abs(normal_x)+np.abs(normal_z))
            apart|=(projection.max(axis=1)<middle-extent)|(projection.min(axis=1)>middle+extent)
        mask[cz[~apart],cx[~apart]]=True
        start=stop
    return mask


def triangle_road(world,x,z):
    from world_layout import triangle_sample
    distance=np.where(np.isfinite(world.road_distance),world.road_distance,1e6)
    return triangle_sample(distance,x,z,world.x0,world.z0)
