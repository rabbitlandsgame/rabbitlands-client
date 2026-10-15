"""Rigid placement of authored compounds, with local terrain support patches.

Call placement_group before discarding small_dressing: signs, lamps and rails
belong to their streets. Build each group's bounds from actual library GLB
subtrees. Apply ONE translation to every member, its metadata, and walk meshes;
never compress member pivots while retaining full-size geometry. A later
reground pass may move the whole assembly, never its individual pieces.

This module supplies geometry-independent placement contracts and bounded
foundation fields. It does not edit content, terrain, meshes or publications.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Callable, Mapping

import numpy as np
from scipy.spatial import ConvexHull
import westhaven_support as W
import manymouth_support as D


NATURE = {'tree','foliage','rock','undergrowth','stone','scatter','stump',
          'fallenlog','leafdrift','mushrooms','fern','vine','scrub'}
HAMLETS = ('paddy_hamlet','east_hamlet','south_hamlet','west_hamlet','north_fishing',
           'boat_yard','far_bar','sea_landing','temple_quay','deep_grove')
TOWN_LINKS = {'Survey_stilt_town__town_hall','Survey_stilt_town__town_quay',
              'Survey_stilt_town__market_hall','Survey_market_hall__floating_market'}
TOWN_NODES = {'Landmark_MootHall','Landmark_MarketHall','Landing_stilt_town',
              'Landing_floating_market','PacketLateen','Secret_delta_moot_vault'}
WHITEHORN_LOWER_CAMP = ('Landmark_LowerCamp','Prop_camp_crate_00_0','Prop_camp_crate_00_1','Prop_camp_crate_00_2',
                        'Prop_camp_brazier_00','Prop_RefugeFuel2','Prop_RefugeFire2')
MIRROR_FORTRESS = ('Landmark_Orrery','Landmark_Citadel','Landmark_Basin_',
    'Landmark_Gate','Landmark_Gallery','Landmark_RoseWindow','Landmark_lens_tower_',
    'Landmark_north-post','Landmark_upper-shrine','Building_VaultEntry_lens-',
    'Prop_Brazier_0_','Prop_Brazier_2_','Secret_mirror_orrery_','Secret_mirror_rose_',
    'Secret_mirror_basin_','Secret_mirror_citadel_','Secret_mirror_lens_focus',
    'Secret_mirror_icebore_')
# Natural placements a retained structure keeps as parts of itself. content.load drops natural placements that are
# neither landmarks nor compound members, so a landmark built with rocks at its flanks lost them and stood free on
# the continent (the Sunmane cave mouths, asset audit example 1). The rule: a natural placement named
# <structure node>_<word>_<n>, for a word of COMPANION_WORDS, belongs to that structure (the four Sunmane cave mouths
# and their EarthRock_0..2). COMPANION_PAIRS names the pairs the rule cannot read, per territory: structure node ->
# (exact companion names, companion name prefixes). A structure with companions is a compound with them (its own
# compound when it already belongs to one), named '<territory>.<structure node>'; its footprint and each companion's
# then carry the legacy slope the structure was built against instead of a flat round footing.
COMPANION_WORDS = ('EarthRock',)
COMPANION_PAIRS = {
    # The Northern Grotto arch, its four abutment stones and the geode cave whose mouth it spans. (The Amberwood sea arch
    # and its RockCluster_2_sea_arch_* rocks read the same way, but as a compound the arch stood 26 % hidden against 7 %
    # in the legacy frame and 3 % as a single, measured on the O5 plan: a later stage raises its footprint.)
    'amethyst_barrens': {'Northern_Grotto_Bridge_Arch': (('Landmark_GeodeCave_0',), ('Northern_Grotto_Abutment_',))}}
_COMPANION_PATTERN = re.compile(r'(.+)_(?:%s)_\d+' % '|'.join(map(re.escape, COMPANION_WORDS)))
# Legacy sites content.load pulled into their territory one placement at a time (a single moves 10 % of the way to the
# hub until it is owned and dry), so their pieces converged and interpenetrated (asset audit family D, example 4). As
# compounds they move as one body and keep their legacy spacing. Per territory: compound id -> (exact member names,
# member name prefixes). A plan assembly_sites center places a site whose pull would land it on other content.
PULLED_SITES = {
    # The east quarry, its two watch towers, the three lodges east of the timber yard and all their dressing: legacy
    # x 186..265, z 12..108 of the Amberwood library, mapped into Mirrorhold's ground and pulled 19-62 m piece by piece.
    'amberwood': {'amberwood.east-quarry': ((
        'Landmark_EastQuarry', 'Landmark_Tower_far_watch', 'Landmark_Watchtower_5', 'Landmark_Building_Lodge_10',
        'Landmark_Building_Lodge_11', 'Landmark_Building_Lodge_29', 'Prop_Barrel_005', 'Prop_Barrel_020', 'Prop_Barrel_021',
        'Prop_Barrel_031', 'Prop_BasketAmber_106', 'Prop_BasketAmber_116', 'Prop_BasketAmber_118', 'Prop_BasketAmber_119',
        'Prop_Brazier_233', 'Prop_Brazier_235', 'Prop_Brazier_239', 'Prop_BurntBrazier_2', 'Prop_BurntBrazier_6',
        'Prop_BurntBrazier_7', 'Prop_BurntCamp_2', 'Prop_BurntCamp_6', 'Prop_BurntCamp_7', 'Prop_Cart_181', 'Prop_Cart_194',
        'Prop_Crate_057', 'Prop_Crate_073', 'Prop_Crate_083', 'Prop_Crate_087', 'Prop_Crate_094', 'Prop_Firewood_172',
        'Prop_LogPile_224', 'Prop_LogPile_228', 'Prop_RetainingWall_5', 'Prop_Ruin_038', 'Prop_Ruin_043', 'Prop_Ruin_046',
        'Prop_Sack_130', 'Prop_Signpost_272'), ('Cart_east_quarry_', 'Crate_east_quarry_'))},
    # The temple summit: the Great Temple and its climbing stair (compacted 36 -> 28 m apart, the stair through the
    # temple), the sun pavilion and its arcade, the court rails, the high camp, the summit stair, the kiln yard and the
    # quarry huts with their discoveries.
    'verdant_stair': {'verdant_stair.temple-summit': ((
        'Landmark_GreatTemple', 'Landmark_Stair_temple_climb', 'Arcade_SunPavilion', 'Landmark_SunPavilion',
        'Signpost_TempleCourt', 'Secret_stair_sun_focus', 'Secret_stair_temple_vault', 'Landmark_Stair_summit_climb',
        'Secret_stair_quarry_pit', 'Hut_kiln_yard_00', 'Prop_kiln_yard_00',
        # The upper court the climbing stair starts from, with its arcade, signpost and waystone.
        'Landmark_UpperCourt', 'Arcade_UpperCourt', 'Signpost_UpperCourt', 'Secret_stair_waystone'),
        ('Rail_SunPavilion_', 'Rail_TempleCourt_', 'Wall_temple_court_', 'Hut_high_camp_', 'Prop_high_camp_', 'Hut_quarry_',
         'Prop_quarry_'))},
    # The upland geode cave with its crystal field: the cave and the spires were pulled 20-43 m off the wet coast onto
    # the resonant cluster they had stood 27-54 m from.
    'amethyst_barrens': {'amethyst_barrens.upland-geode': ((
        'Landmark_GeodeCave_3', 'Landmark_ResonantCluster_7', 'Crystal_UplandSpire_1_0', 'Crystal_UplandSpire_1_1',
        'Crystal_UplandSpire_1_2'), ())}}
# How content.load pulls a compound into its territory: (step, steps, dry). Every other compound steps 8 % of the way to
# the territory hub up to 32 times until every member corner is owned. A pulled site steps 2 % (up to 160 times), so it
# stops at the first owned place instead of up to 16 m beyond it, and a site whose pieces were pulled off wet ground
# also needs every member centre dry (above 0.8 m and out of water deeper than 0.35 m, the rule for a single).
PULL = (.08, 32, False)
SITE_PULL = {identity: (.02, 160, identity == 'amethyst_barrens.upland-geode')
             for sites in PULLED_SITES.values() for identity in sites}
REFERENCE = {'four_gates.civic':((0.,0.),'terrain'),
    'four_gates.sanctuary':((-115.,-162.),'terrain'),
    'four_gates.south-gate':((.5,172.),'terrain'),
    'crownwater.causeway-city':((23.,8.),'water'),
    'mirrorhold.fortress':((99.6788,-138.6464),'terrain'),
    'mirrorhold.plaza':((69.6788,-39.6464),'terrain'),
    'mirrorhold.lake-harbour':((93.6788,42.4641),'water'),
    # The canopy village keeps its reference-point datum. Its western giants, platforms and walkways stand 31-35 m
    # under the continent's northern dome (Landmark_Giant_6_Wood 93 % underground in the O5 composition), but the
    # 'footprints' datum (Assembly.footprint_lift) lifts the whole village about 11.5 m with the Great Tree, and the
    # market stair from platform 0 then needs more than its 45 m at 0.58 (build_amberwood_access refuses it): see
    # C:/Temp/el-ca-out/ASSET-FIXES.md, item 5. Burying giants need terrain work under the dome, not a datum.
    'amberwood.canopy-village':((61.2229,-141.8745),'terrain'),
    'amberwood.great-arch':((132.9427,-49.1381),'terrain'),
    'amberwood.garden':((122.2803,29.841),'terrain'),
    'sunmane_steppe.encampment':((0.,0.),'terrain'),
    'amberwood.ridge-camp':((161.3758,-224.9205),'terrain'),
    'manymouth_delta.boardwalk-town':((39.3459,-55.3715),'water'),
    'manymouth_delta.east_hamlet':((292.06279895504485,-120.97237631493502),'terrain')}
REFERENCE.update(W.REFERENCES)
REFERENCE.update(D.REFERENCES)
# The pulled sites are placed by their footprints: a site moved across its territory has no meaningful single point, so
# it is mapped by the centre of its own bounds. The temple summit keeps the anchor it had before its upper court joined
# (a later centre would move the whole site against its compacted neighbours).
REFERENCE.update({identity: (None, 'footprints') for sites in PULLED_SITES.values() for identity in sites})
REFERENCE['verdant_stair.temple-summit'] = ((143.76912019141707, -126.2123795523941), 'footprints')
DATUMS = ('terrain', 'water', 'footprints')
# The upper-bank hamlet retains the old tidal architectural datum. Sampling
# its obsolete excavated seabed (-4m) would lift every stilt floor needlessly.
REFERENCE_HEIGHTS={'manymouth_delta.east_hamlet':0.}


_COMPANIONS_CACHE = {}


def companions(region, allplacements=()):
    """{node: its structure's placement} for every structure with companions and for each companion (itself included).

    The COMPANION_WORDS rule and COMPANION_PAIRS over one territory's placements: a companion counts only while its
    structure is among them (an object edit may have removed the structure), and a structure only while it keeps one.
    Remembered for the placement list last asked about (content.load asks once per placement)."""
    key = (region, id(allplacements), len(allplacements))
    cached = _COMPANIONS_CACHE.get('last')
    if cached is not None and cached[0] == key and cached[1] is allplacements:
        return cached[2]
    by_name = {p['node']: p for p in allplacements}
    found = {}
    for name in by_name:
        match = _COMPANION_PATTERN.fullmatch(name)
        if match and match.group(1) in by_name:
            found.setdefault(match.group(1), set()).add(name)
    for host, (names, prefixes) in COMPANION_PAIRS.get(region, {}).items():
        if host in by_name:
            members = {name for name in by_name if name != host and (name in names or name.startswith(prefixes))}
            if members:
                found.setdefault(host, set()).update(members)
    result = {}
    for host, members in found.items():
        for name in (host, *members):
            result[name] = by_name[host]
    _COMPANIONS_CACHE['last'] = (key, allplacements, result)
    return result


def placement_group(region, placement, allplacements=()):
    """Stable assembly ID, or None for a separate wilderness object.

    Explicit source assembly metadata takes precedence. Legacy recipes have
    meaningful component names, including zero-origin baked walk meshes;
    membership therefore must not be inferred from placement-position alone.
    A structure's natural companions (COMPANION_WORDS, COMPANION_PAIRS) share
    its compound, or form '<territory>.<structure node>' with it; companions
    are known only from ``allplacements``, which every loader passes.
    """
    explicit=placement.get('assembly') or placement.get('assembly_id')
    if explicit:return region+'.'+str(explicit)
    host=companions(region,allplacements).get(placement['node']) if allplacements else None
    if host is not None:
        return _territory_group(region,host) or region+'.'+host['node']
    return _territory_group(region,placement)


def _territory_group(region, placement):
    """The compound a placement belongs to by its territory's naming rules and site tables, or None."""
    name=placement['node'];kind=placement.get('kind','prop')
    for identity,(names,prefixes) in PULLED_SITES.get(region,{}).items():
        if name in names or name.startswith(prefixes):return identity
    if region=='westhaven':return W.placement_group(placement)
    if region=='amberwood' and name.startswith('Landmark_Giant_'):return 'amberwood.canopy-village'
    if kind in NATURE:return None
    if any(token in name for token in ('_Stream','StreamView_','Backdrop_')) or name.startswith(('March_','MarchGate_','Walk_Survey_')):
        return None
    if region=='mirrorhold' and kind not in ('road','path','ground','terrain'):
        return 'mirrorhold.city'
    if region=='four_gates':
        if name.startswith(('Northern_Sanctuary','Sanctuary_','Walk_Sanctuary_')) or name=='Secret_gates_sanctuary_reliquary':
            return region+'.sanctuary'
        if name.startswith(('Gate_South_Outer','SouthOuter_')):return region+'.south-gate'
        if name.startswith(('Plaza_','Shopfront_','District_House_','City_Wall_',
            'Gate_','Market_','Avenue_','Sign_four-gates-','Goods_four-gates-')):
            return region+'.civic'
        if name.startswith(('Secret_gates_','Garden_Rail_')):
            point=placement.get('position',[math.inf,0,math.inf])
            if math.hypot(point[0],point[2])<=125:return region+'.civic'
    elif region=='crownwater':
        # The complete radial causeway network, islands, quays and their
        # architectural dressing share one sea-level datum. This includes
        # baked Causeway roots whose placement Y is deliberately zero.
        if name=='Walk_FourGatesNativeLanding':return None
        if kind not in ('road','path','ground','terrain'):return region+'.causeway-city'
    elif region=='mirrorhold':
        if name.startswith(MIRROR_FORTRESS):return region+'.fortress'
        if name.startswith(('Landmark_Fountain','Landmark_PlazaStatue_','Prop_PlazaLamp_',
                            'Building_VaultEntry_cistern-','Secret_mirror_waystone','Prop_Brazier_1_')):
            return region+'.plaza'
        if name.startswith(('Landmark_Ring','Landmark_LakeLink_','Landmark_Quay','Landmark_Dock_',
                            'Prop_Boat_','Prop_Pier','Prop_HarbourGoods_')):
            return region+'.lake-harbour'
        if name.startswith('Building_CliffHouse_'):
            return region+'.cliff-row-'+str(int(name.rsplit('_',1)[1])//5)
    elif region=='amberwood':
        if name=='Landmark_Watchtower_1' or name.startswith(('Prop_Tent_ridge_camp_','Brazier_ridge_camp_')):
            return region+'.ridge-camp'
        # The spiral stairs climb to the canopy platforms: as singles each was pulled and grounded on its
        # own and stood 33-58 m from its platform (the legacy stair tops sit 1.65 m under them).
        if name.startswith(('Landmark_Canopy','Landmark_GreatTree_','Walk_Prop_SpiralStair_')):return region+'.canopy-village'
        if name.startswith(('Landmark_GreatArch','Landmark_ArchColumn_')):return region+'.great-arch'
        if name.startswith('Landmark_Garden'):return region+'.garden'
    elif region=='whitehorn_range':
        # Retained singles are regrounded on whatever ground the roads leave them, and settle_roads fixes no
        # single's ground. The temple road ends at the glacier temple's stair foot, where corridor_grade caps
        # the road near 196 m (its upper envelope rises 0.318 m per metre from the network's low cells), so the
        # temple, as a single, sank 14-15 m with its terrace in two offline compositions; the lower camp's spur is
        # rounded 20-26 m off by the Amberwood seam road at 155-157 m, whose shoulders cut the pad under the camp.
        # As compounds their footings hold the legacy ground under them (both legacy sites are level) against the
        # roads, road cells inside them are fitted to that ground, and nothing regrounds them.
        if name=='Landmark_glacier_temple':return region+'.glacier-temple'
        if name in WHITEHORN_LOWER_CAMP:return region+'.lower-camp'
    elif region=='manymouth_delta':
        if name=='Landing_shore_south_hamlet':return region+'.south_hamlet'
        if name in ('Lore_stelae_court','Landing_lore_court','Landing_shore_lore_court'):
            return region+'.east_hamlet'
        compound=D.placement_group(name)
        if compound:return compound
        if name.startswith(('town_','market_stall_','MooredMarketBoat_')) or name in TOWN_NODES|TOWN_LINKS:
            return region+'.boardwalk-town'
        for hamlet in HAMLETS:
            if name.startswith(hamlet+'_') or name=='Landing_'+hamlet:return region+'.'+hamlet
        # Exterior standing stones follow the final bank, not the temple's
        # raised floor datum; they do not carry connected walk geometry.
    elif region=='sunmane_steppe':
        # The palisade's four gates stand in its walls: as singles, compacted to 0.78 of their 25 m, they stood inside
        # the full-size ring, through the great hall and the pavilions (asset audit family D).
        if name.startswith('Encampment_') or name in (
            'Structure_Palisade','Landmark_sunmane_great_hall','Landmark_sunmane_well_00',
            'Landmark_sunmane_secret_steppe-hall-vault','Gate_North','Gate_South','Gate_East','Gate_West',
            *('Landmark_orun_banner_shrine_'+str(i).zfill(2) for i in range(4,8))):
            return region+'.encampment'
    elif region=='ssarathi_ruins':
        if name=='Secret_ruins_temple_focus':return region+'.temple-focus'
        # The pyramid, canal courts, outer shrines and water gate share a
        # surveyed plan. Separate compacted pivots put the lily court inside
        # the pyramid and the culvert beneath its stairs.
        if kind not in ('road','path','ground','terrain'):return region+'.ruin-city'
    return None


# Name words of the pulled-site members that stand in water or in the air and carry no footing.
SITE_OPEN_WORDS = ('boat', 'skiff', 'lateen', 'causeway', 'pier', 'quay', 'water', 'sunken', 'lamp', 'banner', 'flame',
                   'portcullis', 'levitating', 'shard', 'wisp')


def site_supports_ground(placement):
    """Does a member of a pulled site keep its legacy ground under it? Every member but natural ones and those standing
    in water or in the air (SITE_OPEN_WORDS), props, signs, discoveries and crystals included: as singles each had a
    round footing of its own, and a site moved onto other ground leaves a prop without one floating or buried."""
    name = placement['node'].lower()
    return placement.get('kind') not in NATURE and not any(word in name for word in SITE_OPEN_WORDS)


def supports_ground(placement):
    """A bridge deck or water surface is not an island-shaped foundation."""
    name=placement['node'].lower()
    if placement.get('kind') in NATURE:return False
    # A spiral stair stands under its canopy platform, which supports no ground either: the two western
    # platforms stand 17-25 m under the continent's relief, and a stair footprint carrying the legacy ground
    # there dug a 29 m pit that moved the Amberwood-Grey Moors crossing 28.6 m (an offline composition).
    if name.startswith(('landmark_canopyplatform','landmark_canopywalkway','walk_prop_spiralstair')):return False
    if any(word in name for word in ('boat','skiff','lateen','causeway','pier','quay','survey_',
        'water','sunken','lamp','bollard','banner','crystal','flame','portcullis')):return False
    return not name.startswith(('prop_','secret_','sign_','goods_','plaza_bench','plaza_fountain','plaza_arcade'))


@dataclass
class Assembly:
    id: str
    nodes: tuple[str,...]
    reference_xz: np.ndarray
    reference_y: float
    datum: str
    bounds: np.ndarray
    footprints: tuple[np.ndarray,...]
    # Every member's xz bounds [[low x, low z], [high x, high z]] in the source frame, supporting the ground or not.
    member_boxes: tuple[np.ndarray,...] = ()

    def shift_to(self, map_xz: Callable, target_height: Callable, *, water_level=0., target_xz=None):
        """Map the assembly anchor once; preserve metre-for-metre structure."""
        target=np.asarray(map_xz(self.reference_xz) if target_xz is None else target_xz,float)
        y=float(water_level if self.datum=='water' else target_height(*target))
        return np.array([target[0]-self.reference_xz[0],y-self.reference_y,target[1]-self.reference_xz[1]])

    def footprint_lift(self, target_height: Callable, source_height: Callable, shift, *, spacing=2., unmap=None):
        """The vertical shift that stands the compound on the ground under all its members (datum 'footprints').

        Each member's source xz bounds (``member_boxes``) are sampled on a grid ``spacing`` metres apart (at least its
        centre), carried by ``shift`` in x/z onto the continent, and the continent ground there (``target_height``) is
        compared with the source ground at the same legacy point (``source_height``; through ``unmap``, a turned
        layout's inverse mapping, when given). The shift is the median of those differences over every sample, so the
        compound sits on the continent as a whole instead of at its reference point, and a member standing where the
        continent is much higher or lower than its legacy ground no longer decides the datum on its own."""
        if not math.isfinite(spacing) or spacing<=0:raise ValueError('Footprint datum spacing must be positive')
        shift=np.asarray(shift,float)
        xs,zs=[],[]
        for low,high in self.member_boxes:
            low,high=np.asarray(low,float),np.asarray(high,float)
            x=np.arange(low[0],high[0]+1e-9,spacing) if high[0]-low[0]>=spacing else np.array([(low[0]+high[0])*.5])
            z=np.arange(low[1],high[1]+1e-9,spacing) if high[1]-low[1]>=spacing else np.array([(low[1]+high[1])*.5])
            gx,gz=np.meshgrid(x,z)
            xs.append(gx.ravel());zs.append(gz.ravel())
        if not xs:raise ValueError(self.id+': a footprint datum needs member bounds')
        sx,sz=np.concatenate(xs),np.concatenate(zs)
        wx,wz=sx+shift[0],sz+shift[2]
        lx,lz=unmap(wx,wz) if unmap is not None else (sx,sz)
        difference=np.asarray(target_height(wx,wz),float)-np.asarray(source_height(lx,lz),float)
        if not np.isfinite(difference).all():raise ValueError(self.id+': footprint datum samples leave the ground')
        return float(np.median(difference))

    def sample_foundation(self, x, z, shift, source_height, *, feather=12., unmap=None):
        """Return target Y and influence for footprint-local original grades.

        Query with world XZ arrays on the new global terrain lattice. Source
        height takes source X,Z arrays. Blend once using maximum influence,
        not one additive raising pass per component. Open water and bridge
        spans stay outside the support mask. The original region's terrain is
        sampled only underneath buildings/yards, never copied as a rectangle.
        ``unmap`` (a turned layout's inverse mapping) carries the sample point back to the legacy
        frame, which the shift alone cannot do once the layout turns; without it the shift leads
        back, as it does for every territory that is only translated.
        """
        if not math.isfinite(feather) or feather<=0:raise ValueError('Foundation feather must be positive')
        x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
        sx,sz=x-shift[0],z-shift[2]
        influence=np.zeros(x.shape,float)
        for footprint in self.footprints:
            low,high=footprint
            dx=np.maximum(np.maximum(low[0]-sx,sx-high[0]),0)
            dz=np.maximum(np.maximum(low[1]-sz,sz-high[1]),0)
            t=np.clip(1-np.hypot(dx,dz)/feather,0,1)
            influence=np.maximum(influence,t*t*(3-2*t))
        sample_x,sample_z=sx,sz
        if self.id=='mirrorhold.city' and len(self.footprints)>1:
            # The fortress, cliff streets and harbour occupy one inhabited
            # hillside. Preserve the surveyed streets BETWEEN their buildings
            # too; isolated footprint patches create pits and bury the quays.
            # The old survey is authoritative inside this inhabited envelope.
            # Beyond it, extend its boundary elevation only through the local
            # apron. Sampling the distant old mountain here used to raise an
            # empty Four Gates hillside by 70 m.
            corners=np.array([[a,b] for low,high in self.footprints
                for a in (low[0],high[0]) for b in (low[1],high[1])])
            hull=ConvexHull(corners)
            signed=np.full(x.shape,-np.inf)
            for nx,nz,offset in hull.equations:
                signed=np.maximum(signed,nx*sx+nz*sz+offset)
            distance=np.full(x.shape,np.inf)
            nearest_x=sx.copy();nearest_z=sz.copy()
            vertices=corners[hull.vertices]
            for a,b in zip(vertices,np.roll(vertices,-1,axis=0)):
                delta=b-a
                t=np.clip(((sx-a[0])*delta[0]+(sz-a[1])*delta[1])/np.dot(delta,delta),0,1)
                px,pz=a[0]+t*delta[0],a[1]+t*delta[1]
                d=np.hypot(sx-px,sz-pz);closer=d<distance
                nearest_x=np.where(closer,px,nearest_x);nearest_z=np.where(closer,pz,nearest_z)
                distance=np.minimum(distance,d)
            outside=signed>1e-8
            distance=np.where(outside,distance,0.)
            t=np.clip(1-distance/feather,0,1)
            influence=t*t*(3-2*t)
            sample_x=np.where(outside,nearest_x,sx);sample_z=np.where(outside,nearest_z,sz)
        if unmap is not None:
            # A turned layout: the legacy ground under this footing is the continent point carried back
            # through the layout's own mapping, not the point the shift alone reaches.
            sample_x,sample_z=unmap(sample_x+shift[0],sample_z+shift[2])
        target=np.asarray(source_height(sample_x,sample_z),float)+shift[1]
        return target,influence


def build_assemblies(region, placements, bounds_by_name: Mapping, source_height: Callable, references=None):
    """Build groups from actual source-space GLB bounds; return ID -> Assembly.

    bounds_by_name[node] is (minimumXYZ, maximumXYZ). source_height(x,z)
    supports scalar or broadcast NumPy input. Regions are never mutated here.
    ``references`` pins a compound's anchor to the point it stood on before its layout was turned, so
    turning the compound about that anchor cannot move the compound itself.
    """
    groups={}
    for p in placements:
        identity=placement_group(region,p,placements)
        if identity and p['node'] in bounds_by_name:groups.setdefault(identity,[]).append(p)
    result={}
    for identity,members in groups.items():
        bounds=np.array([bounds_by_name[p['node']] for p in members],float)
        if not np.isfinite(bounds).all() or np.any(bounds[:,1]<bounds[:,0]):raise ValueError(identity+': invalid actual assembly bounds')
        full=np.array([bounds[:,0].min(axis=0),bounds[:,1].max(axis=0)])
        fallback=tuple(((full[0]+full[1])*.5)[[0,2]])
        reference,datum=REFERENCE.get(identity,(fallback,'water' if region=='manymouth_delta' and identity.rsplit('.',1)[1] in HAMLETS else 'terrain'))
        if datum not in DATUMS:raise ValueError(f'{identity}: datum {datum!r} is none of {DATUMS}')
        # A site placed by its footprints keeps the centre of its own bounds as the point it is mapped and pulled by.
        reference=fallback if reference is None else reference
        reference=np.asarray((references or {}).get(identity,reference),float)
        y=REFERENCE_HEIGHTS.get(identity,0. if datum=='water' else float(source_height(*reference)))
        footprints=[]
        if identity=='four_gates.civic':
            # Civic paving and the inhabited inner streets are one broad
            # terrace. Octagonal strips avoid a square imported terrain base.
            for z in range(-112,112,8):
                half=math.sqrt(max(0,112**2-(z+4)**2))
                footprints.append(np.array([[-half,z],[half,z+8]],float))
        # A structure's natural companions and a pulled site's members stand on their own legacy ground.
        companion_of=companions(region,placements)
        site=identity in SITE_PULL
        for p,b in zip(members,bounds):
            # These three Manymouth banks are fitted to their actual upper
            # floors by manymouth_support. The old survey's rectangular
            # footing masks would restore trenches around the new bank edge.
            camp_member=identity=='amberwood.ridge-camp' and p['node'].startswith(('Prop_Tent_ridge_camp_','Brazier_ridge_camp_'))
            companion=p['node'] in companion_of and companion_of[p['node']]['node']!=p['node']
            if (supports_ground(p) or camp_member or companion or (site and site_supports_ground(p))) and identity not in D.REFERENCES:
                footprints.append(b[:,[0,2]]+np.array([[-1.5,-1.5],[1.5,1.5]]))
        result[identity]=Assembly(identity,tuple(p['node'] for p in members),reference,y,datum,full,tuple(footprints),
                                  tuple(b[:,[0,2]] for b in bounds))
    return result


def apply_group_delta(objects, delta):
    """Reground an already placed assembly atomically, including its bounds."""
    delta=np.asarray(delta,float)
    if delta.shape!=(3,) or not np.isfinite(delta).all():raise ValueError('Assembly displacement must be finite XYZ')
    for obj in objects:
        for key in ('shift','low','high'):
            value=np.asarray(obj[key],float)
            value+=delta  # Preserve existing mapping/bounds array references.
            obj[key]=value
        if 'targetGround' in obj:obj['targetGround']+=float(delta[1])


def assert_rigid(objects, *, tolerance=1e-7):
    """Fail if a later placement/grounding pass tears an assembly apart."""
    shifts=np.array([obj['shift'] for obj in objects],float)
    if not np.isfinite(shifts).all():raise ValueError('Assembly displacement is not finite')
    if len(shifts) and np.max(np.abs(shifts-shifts[0]))>tolerance:
        raise ValueError('Connected assembly received independent component transforms')


def report(assembly):
    return {'id':assembly.id,'members':len(assembly.nodes),'nodes':list(assembly.nodes),
            'referenceXZ':assembly.reference_xz.tolist(),'referenceY':assembly.reference_y,
            'datum':assembly.datum,'sourceBounds':assembly.bounds.tolist(),
            'foundationFootprints':len(assembly.footprints),'geometryScale':1.,
            'placementPolicy':'One common translation; preserve all relative XYZ offsets and metadata.'}
