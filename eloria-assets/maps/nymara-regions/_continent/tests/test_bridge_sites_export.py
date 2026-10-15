"""A bridge deck is its site span plus landings of at most 6 m; piers stand only under the span; designed decks are named."""
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

import numpy as np
from scipy.ndimage import label

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bridge_export as B
import landscape as L
import scene_io as S


def crossing(level=0.):
    """A 12 m river along z at x 18..30 (deep), dry banks at 2 m, one claimed site square across it at z 20."""
    w = SimpleNamespace(x0=0., z0=0., x1=60., z1=40., ids=['west', 'east'], connections=[], plan={})
    w.height_at = lambda x, z: np.where((np.asarray(x) >= 18) & (np.asarray(x) <= 30), -2., 2.) + np.asarray(z) * 0
    w.owner_at = lambda x, z: np.where(np.asarray(x) < 24, 0, 1) + np.asarray(z, dtype=int) * 0
    w.roads = [{'id': 'seam', 'width': 3., 'points': [[2, 2, 20], [58, 2, 20]]}]
    w.crossing_sites = [{'id': 4, 'key': 'main@20', 'river': 'main', 'wetEdges': [[18., 20.], [30., 20.]],
                         'routeLandings': [[9., 20.], [39., 20.]]}]
    w.crossing_site_roads = {4: {'seam'}}
    return w


def water(x, z, *, height, plan):
    wet = (np.asarray(x) >= 18) & (np.asarray(x) <= 30)
    return {'mask': wet, 'depth': np.where(wet, 2., 0.), 'surface': np.zeros(np.shape(height)), 'river_mask': wet}


class SiteDeckTests(unittest.TestCase):
    def test_all_saved_crossings_need_no_procedural_site_fit(self):
        w = crossing()
        w.crossing_sites = []
        w.height = np.array([[2., 3.], [4., 5.]])
        w.authored_terrain_authority = np.ones((2, 2), bool)
        w.water = {"mask": np.zeros((2, 2), bool)}
        original = w.height.copy(); water_authority = w.water
        saved = SimpleNamespace(authored_regions=set(w.ids))
        report = B.fit_claimed_sites(w, content=saved)
        self.assertEqual(report["selectedSiteIds"], [])
        self.assertEqual(report["changedTerrainVertices"], 0)
        self.assertEqual(report["authoredTerrainVertices"], 4)
        np.testing.assert_array_equal(w.height, original)
        self.assertIs(w.water, water_authority)
        self.assertEqual(w.claimed_bridge_protected_nodes.shape, (0, 2))
        with self.assertRaisesRegex(B.BP.ProfileError, "no claimed bridge sites"):
            B.fit_claimed_sites(w, site_ids=[], content=saved)
        with self.assertRaisesRegex(B.BP.ProfileError, "no claimed bridge sites"):
            B.fit_claimed_sites(w, content=SimpleNamespace(authored_regions={"west"}))

    def test_the_deck_is_the_span_plus_landings_of_at_most_six_metres(self):
        w = crossing()
        field = B.common_surface(w, water_fields=water)
        columns = np.flatnonzero(field['mask'].any(axis=0))
        self.assertGreaterEqual(columns.min(), 18 - 6); self.assertLessEqual(columns.max() + 1, 30 + 6)
        self.assertEqual([d['sites'] for d in field['decks']], [[4]])
        self.assertEqual(field['decks'][0]['component'], 5)               # named by its site (id + 1)
        self.assertEqual(field['riverWaterOutsideSites']['cells'], 0)
        self.assertLessEqual(field['decks'][0]['maximumDryLiftMetres'], L.CROSSING_POLICY_DEFAULTS['deck_lift_metres'])

    def test_piers_stand_only_over_the_water(self):
        w = crossing()
        with tempfile.TemporaryDirectory() as temporary:
            parts = B.build_bridges(w, Path(temporary) / 'bridges.glb', water_fields=water)
        piers = [p for p in parts if p['node'].startswith('BridgeUnionPier_')]
        self.assertTrue(piers)
        for pier in piers:
            low, high = pier['bounds']
            x = float((low[0] + high[0]) * .5)
            self.assertTrue(18 <= x <= 30, x)
        floors = {p['node'] for p in parts if p['node'].startswith('Walk_ContinentalBridgeUnion_')}
        self.assertEqual(floors, {'Walk_ContinentalBridgeUnion_005_west', 'Walk_ContinentalBridgeUnion_005_east'})

    def test_a_site_deck_in_two_pieces_emits_one_floor_per_territory(self):
        # Two narrow roads cross the same site 6 m apart: their deck cells never touch, so the site's deck is two
        # components that both take the site's number; the export merges them into one node per territory.
        w = crossing()
        w.roads = [{'id': 'north', 'width': 1., 'points': [[2, 2, 17], [58, 2, 17]]},
                   {'id': 'south', 'width': 1., 'points': [[2, 2, 23], [58, 2, 23]]}]
        field = B.common_surface(w, water_fields=water)
        self.assertEqual([d['component'] for d in field['decks']], [5, 5])
        with tempfile.TemporaryDirectory() as temporary:
            parts = B.build_bridges(w, Path(temporary) / 'bridges.glb', water_fields=water)
        names = [p['node'] for p in parts]
        self.assertEqual(len(names), len(set(names)))
        floors = [p for p in parts if p['node'].startswith('Walk_ContinentalBridgeUnion_')]
        self.assertEqual(sorted(p['node'] for p in floors), ['Walk_ContinentalBridgeUnion_005_east', 'Walk_ContinentalBridgeUnion_005_west'])
        for part in floors:
            low, high = part['bounds']
            self.assertLess(float(low[2]), 18.); self.assertGreater(float(high[2]), 22.)   # both pieces in one node

    def test_a_long_approach_is_ground_not_deck(self):
        # A road that stays on its bank for 20 m past the water gets no deck beyond the six-metre landing.
        w = crossing()
        w.roads = [{'id': 'seam', 'width': 3., 'points': [[2, 2, 20], [58, 2, 20]]},
                   {'id': 'bank', 'width': 2., 'points': [[40, 2, 5], [40, 2, 35]]}]
        field = B.common_surface(w, water_fields=water)
        self.assertFalse(field['mask'][:, 37:].any())

    def test_deep_water_away_from_every_site_gets_the_same_short_deck_and_river_water_is_reported(self):
        w = crossing(); w.crossing_sites = []
        field = B.common_surface(w, water_fields=water)
        columns = np.flatnonzero(field['mask'].any(axis=0))
        self.assertGreaterEqual(columns.min(), 12); self.assertLessEqual(columns.max() + 1, 36)
        self.assertGreaterEqual(field['decks'][0]['component'], 500)
        self.assertGreater(field['riverWaterOutsideSites']['cells'], 0)

    def test_a_landing_trim_never_leaves_a_deck_in_pieces(self):
        # The east bank's first dry metre lies at the water line and the bank then rises 2 m in a metre: the deck,
        # held over the water, lifts about 1.5 m over that metre, so the trim cuts the landing's first dry column
        # across the whole road. The landing cells beyond the cut would be a floor of their own (the Amberwater
        # crossing at the Amberwood hub was split [104, 36] this way): they go with the cut, and the report says
        # where a bank ended a landing.
        w = crossing()
        w.height_at = lambda x, z: np.select([(np.asarray(x) >= 18) & (np.asarray(x) <= 30), (np.asarray(x) > 30) & (np.asarray(x) < 32)],
                                             [-2., 0.], 2.) + np.asarray(z) * 0
        field = B.common_surface(w, water_fields=water)
        self.assertEqual([d['sites'] for d in field['decks']], [[4]])
        _, pieces = label(field['mask'], structure=B.CROSS)
        self.assertEqual(pieces, 1)
        self.assertFalse(field['mask'][:, 31:].any())                  # nothing of the east landing beyond its cut
        self.assertTrue(field['mask'][:, 12:18].any())                 # the west landing, which fits, stays
        self.assertGreater(field['cutOffLandingCells'], 0)
        self.assertTrue(any(abs(x - 31.5) <= 1 and abs(z - 20) <= 2 for x, z in field['cutOffLandingBanks']))

    def test_a_landing_cut_keeps_every_piece_still_joined_to_the_water(self):
        mask = np.ones((3, 6), bool)
        dry = np.zeros((3, 6), bool); dry[:, 2:] = True               # columns 0-1 stand over the water
        cut = np.zeros((3, 6), bool); cut[:, 3] = True                # a full-width cut in the landing
        removed = B.landing_cut(mask, cut, dry)
        self.assertTrue(removed[:, 3:].all()); self.assertFalse(removed[:, :3].any())
        cut[:, 3] = False; cut[0, 3] = True                           # a partial cut parts nothing
        self.assertEqual(B.landing_cut(mask, cut, dry).tolist(), cut.tolist())

    def test_the_retired_apron_keys_are_refused(self):
        for key in ('bridge_approach_aprons', 'bridge_approach_connections'):
            w = crossing(); w.plan = {key: {'west': 96.}}
            with self.assertRaisesRegex(ValueError, 'retired by the roads pass'):
                B.common_surface(w, water_fields=water)


class DesignedDeckTests(unittest.TestCase):
    PLAN = {'designed_decks': [
        {'name': 'Walk_Amber_RootRamp', 'module': 'amberwood_access', 'note': 'the ramp onto the Motherroot plateau'},
        {'name': 'Walk_Manymouth_Village_*', 'module': 'manymouth_village_streets', 'note': 'village streets on piles'}]}

    def test_designed_decks_are_named_exactly_or_by_family_and_by_their_module(self):
        self.assertEqual(L.validate_designed_decks(self.PLAN), [])
        self.assertEqual(L.designed_deck_entry(self.PLAN, 'Walk_Manymouth_Village_town')['module'], 'manymouth_village_streets')
        self.assertIsNone(L.designed_deck_entry(self.PLAN, 'Walk_Amber_RootRampExtension'))
        L.require_designed_deck(self.PLAN, 'Walk_Amber_RootRamp', 'amberwood_access')
        with self.assertRaisesRegex(ValueError, 'does not name'):
            L.require_designed_deck(self.PLAN, 'Walk_Amber_CanopyBridge', 'amberwood_access')
        with self.assertRaisesRegex(ValueError, "under 'amberwood_access'"):
            L.require_designed_deck(self.PLAN, 'Walk_Amber_RootRamp', 'manymouth_access')
        # A plan that predates the rule carries no list and refuses nothing.
        self.assertIsNone(L.require_designed_deck({}, 'Walk_Anything', 'any_module'))

    def test_invalid_lists_are_reported(self):
        bad = {'designed_decks': [{'name': 'Walk_*_Deck', 'module': 'x', 'note': 'y'}, {'name': 'Walk_A', 'module': '', 'note': 'y'},
                                  {'name': 'Walk_A', 'module': 'x', 'note': 'y', 'height': 3}]}
        problems = L.validate_designed_decks(bad)
        self.assertTrue(any("ending in one '*'" in p for p in problems))
        self.assertTrue(any("needs a non-empty string 'module'" in p for p in problems))
        self.assertTrue(any('listed twice' in p for p in problems))
        self.assertTrue(any('unknown key' in p for p in problems))

    def test_the_plan_names_every_support_module_deck(self):
        plan = L.load_plan()
        self.assertEqual(L.validate_designed_decks(plan), [])
        self.assertNotIn('bridge_approach_aprons', plan)
        self.assertNotIn('bridge_approach_connections', plan)
        for name, module in (('Walk_Amber_MarketCanopyStair', 'amberwood_access'), ('Walk_Amber_RootRamp', 'amberwood_access'),
                             ('Walk_Manymouth_FishingBoardwalk', 'manymouth_access'), ('Walk_Manymouth_PaddyStreet', 'manymouth_access'),
                             ('Walk_Manymouth_Village_town', 'manymouth_village_streets'), ('Walk_Mirror_BankRamp_Quay', 'mirror_access_geometry'),
                             ('Walk_FerryQuay_westhaven_00', 'ferry_export'), ('Landmark_boardwalk_bog', 'grey_crossings')):
            L.require_designed_deck(plan, name, module)


def prepared_crossing(oblique=False):
    """Small current-hydrology world for the coupled profile and terrain fit."""
    if oblique:
        axis=np.array([.6,.8]);across=np.array([-axis[1],axis[0]])
        left=np.array([24.,24.]);right=left+12.*axis;middle=(left+right)*.5
        world=SimpleNamespace(x0=0.,z0=0.,x1=80.,z1=80.,ids=['west','east'],connections=[])
        world.x=np.arange(0.,81.,2.);world.z=np.arange(0.,81.,2.)
        world.gx,world.gz=np.meshgrid(world.x,world.z)
        station=(np.stack((world.gx,world.gz),axis=-1)-left)@axis
        world.height=np.where((station>=0.)&(station<=12.),-2.,2.)
        world.owner_at=lambda x,z:np.zeros(np.broadcast(np.asarray(x),np.asarray(z)).shape,dtype=int)
        road_id='oblique'
        world.roads=[{'id':road_id,'width':3.,
            'points':[[*(left-axis*18.)[:1],2.,(left-axis*18.)[1]],
                      [*(right+axis*18.)[:1],2.,(right+axis*18.)[1]]]}]
        world.crossing_sites=[{'id':7,'key':'oblique@12','river':'oblique-river',
            'wetEdges':[left.tolist(),right.tolist()],
            'routeLandings':[(left-axis*12.).tolist(),(right+axis*12.).tolist()]}]
        world.crossing_site_roads={7:{road_id}}
        river_a=middle-across*50.;river_b=middle+across*50.
        rivers=[{'id':'oblique-river','width':6.,
                 'points':[[river_a[0],river_a[1],0.],[river_b[0],river_b[1],0.]]}]
    else:
        world=crossing();world.x=np.arange(world.x0,world.x1+1.,2.)
        world.z=np.arange(world.z0,world.z1+1.,2.);world.gx,world.gz=np.meshgrid(world.x,world.z)
        world.height=np.where((world.gx>=18.)&(world.gx<=30.),-2.,2.)
        world.height[:,world.x>=38.]=4.
        rivers=[{'id':'main','width':6.,'points':[[24.,0.,0.],[24.,40.,0.]]}]
    world.original_height=world.height.copy();world.solids=np.zeros(world.height.shape,bool)
    world.height_at=lambda x,z:B.triangle_sample(world.height,x,z,world.x0,world.z0,B.TERRAIN_CELL)
    world.plan={'sea_level':-100.,'lakes':[],'rivers':rivers,
        'crossing_policy':{'deck_landing_metres':6.,'deck_lift_metres':.3,
                           'deck_clearance_metres':.85}}
    world.water=L.water_fields(world.gx,world.gz,height=world.height,plan=world.plan)
    return world


class PreparedProfileTests(unittest.TestCase):
    def test_axis_aligned_joint_fit_preserves_hydrology_and_declared_stencil(self):
        world=prepared_crossing();before=world.height.copy();sites=list(world.crossing_sites)
        report=B.fit_claimed_sites(world,site_ids=[4])
        self.assertEqual(world.crossing_sites,sites)
        self.assertTrue(report['waterAuthority'][4]['unchanged'])
        self.assertEqual(report['outsideDeclaredStencilChangedVertices'],0)
        self.assertGreater(report['changedTerrainVertices'],0)
        self.assertLessEqual(float(np.max(before-world.height)),B.ROAD_CUT_METRES)
        self.assertLessEqual(float(np.max(world.height-before)),B.ROAD_FILL_METRES)
        actual=report['sites'][0]['actualGeometry']
        self.assertFalse(actual['waterClearanceIsSampledNotContinuous'])
        self.assertGreaterEqual(actual['minimumDeepWaterClearanceMetres'],.85)
        self.assertLessEqual(actual['maximumEncodedDeckGrade'],B.GRADE)
        self.assertLessEqual(actual['maximumEncodedApproachGrade'],B.GRADE)
        self.assertEqual(actual['joinCoverage']['left']['analyticIntervals'],[[-3.,3.]])
        self.assertEqual(actual['joinCoverage']['right']['analyticIntervals'],[[-3.,3.]])
        geometry=report['sites'][0]['representationV7']['geometry']
        self.assertLessEqual(geometry['numericJoinExpansionMetres'],
                             geometry['numericJoinExpansionGuardMetres'])

    def test_joint_fit_never_mutates_authored_terrain_vertices(self):
        baseline=prepared_crossing();first=B.fit_claimed_sites(baseline,site_ids=[4])
        changed=first['sites'][0]['changedTerrain']
        self.assertTrue(changed)
        # Pin the least-displaced fitted vertex, leaving the remaining dry
        # approach available to the solver.
        node=tuple(min(changed,key=lambda row:abs(row['deltaMetres']))['node'])
        world=prepared_crossing();before=world.height.copy()
        world.authored_terrain_authority=np.zeros_like(world.height,bool)
        world.authored_terrain_authority[node]=True
        with self.assertRaises(B.BP.ProfileError):
            B.fit_claimed_sites(world,site_ids=[4])
        # A bridge that needs an authored vertex fails atomically rather than
        # changing the editor's final terrain authority.
        np.testing.assert_array_equal(world.height,before)

    def test_oblique_joint_fit_keeps_flat_width_and_encoded_join_identity(self):
        world=prepared_crossing(oblique=True);report=B.fit_claimed_sites(world,site_ids=[7])
        site=world.crossing_sites[0];left,right=np.asarray(site['wetEdges'])
        axis=(right-left)/np.linalg.norm(right-left);across=np.array([-axis[1],axis[0]])
        profile=world.claimed_bridge_profiles[7]
        station=float(np.linalg.norm(right-left))*.5
        points=left+station*axis+np.linspace(-1.4,1.4,9)[:,None]*across
        field=B.common_surface(world)
        values=B.surface_at(world,points[:,0],points[:,1],field)
        np.testing.assert_allclose(values,profile.at(station),atol=2e-5)
        actual=report['sites'][0]['actualGeometry']
        for side in ('left','right'):
            join=actual['joinCoverage'][side]
            self.assertEqual(join['constraintMode'],'uniform-equality')
            self.assertTrue(join['canonicalContactRowProvenanceMatched'])
            self.assertLessEqual(join['maximumContactConstraintResidualMetres'],
                                 join['maximumEncodingBoundMetres'])
            self.assertLessEqual(join['maximumGroundGapMetres'],.3)

    def test_site11_captured_retraced_clip_emits_every_positive_piece(self):
        raw=np.array([[473.,0.,1045.4886454],[473.,0.,1046.],
                      [473.1147254,0.,1045.8852746],[473.1517774,0.,1045.8482226],
                      [473.0160586,0.,1045.52669]])
        left=np.array([469.61743848007154,1047.7610394719027])
        right=np.array([462.2287937688258,1030.2565277868832])
        axis=right-left;length=float(np.linalg.norm(axis));axis/=length
        profile=SimpleNamespace(stations=np.array([.5]),at=lambda value:np.zeros_like(value))
        span=B.SpanOutline(SimpleNamespace(clip=lambda triangle:[raw.copy()]),
                           left,axis,-6.,length+6.,4.)
        triangle=np.array([[473.,0.,1045.],[473.,0.,1046.],[474.,0.,1045.]])
        pieces=span.clip(triangle)
        faces=[face for piece in pieces for band in B.arch_station_slices(
            piece,{'origin':left,'axis':axis,'profile':profile}) for face in B.triangulate_floor(band)]
        self.assertTrue(faces)
        self.assertGreater(sum(abs(B._area_xz(face)) for face in faces),0.)

    def test_continuous_encoded_clearance_finds_minimum_between_old_samples(self):
        deck=np.array([[[0.,1.,0.],[2.,1.,0.],[0.,1.,2.]]])
        water_faces=np.array([[[.121,.2,.121],[.139,.2,.121],[.121,.2,.139]]])
        with self.assertRaisesRegex(B.BP.ProfileError,'continuous water clearance'):
            B._continuous_emitted_water_check(deck,water_faces,.85)
        deck[:,:,1]=1.05
        result=B._continuous_emitted_water_check(deck,water_faces,.85)
        self.assertEqual(result['positiveOverlapPieces'],1)
        self.assertGreaterEqual(result['minimumClearanceMetres'],.85)

    def test_complete_final_water_union_cannot_cross_a_full_width_join(self):
        world=crossing();site=world.crossing_sites[0]
        geometry=B._claimed_geometry_v7(world,site,6.,B._serving_roads(world,site))
        water_faces=np.array([[[11.5,0.,21.],[12.5,0.,21.],[12.,0.,22.]]])
        with self.assertRaisesRegex(B.BP.ProfileError,'full-width join'):
            B._join_misses_water(world,site,np.empty((0,3,3)),water_faces,geometry)

    def test_local_authority_detects_dry_terrain_that_moves_the_shoreline(self):
        world=prepared_crossing();ix=int(np.flatnonzero(world.x==20.)[0])
        world.height[:,ix]=2.;world.water=L.water_fields(
            world.gx,world.gz,height=world.height,plan=world.plan)
        bounds=B._site_local_bounds(world,world.crossing_sites[0],6.)
        before=B._encoded_water_authority(world,bounds)
        self.assertFalse(world.water['mask'][:,ix].any())
        world.height[:,ix]=-2.;world.water=L.water_fields(
            world.gx,world.gz,height=world.height,plan=world.plan)
        after=B._encoded_water_authority(world,bounds)
        same,fields=B._same_water_authority(before,after)
        self.assertFalse(same)
        self.assertTrue(any(not value for value in fields.values()))

    def test_immutable_dry_sample_inside_encoding_guard_adds_no_false_lp_row(self):
        rows=[];limits=[];guard=6e-7
        added=B._append_mutable_dry_constraint(
            rows,limits,np.zeros(3),0.,.01501,guard)
        self.assertFalse(added);self.assertEqual(rows,[]);self.assertEqual(limits,[])
        added=B._append_mutable_dry_constraint(
            rows,limits,np.array([0.,.5,.5]),0.,.01501,guard)
        self.assertTrue(added)
        np.testing.assert_array_equal(rows[0],[0.,-.5,-.5])
        self.assertLess(limits[0],0.)

    def test_nominal_line_merges_only_a_derived_arithmetic_shared_seam(self):
        faces=np.array([[[1000.,0.],[1001.,0.],[1000.,1.]],
                        [[1001.,0.],[1001.,1.],[1000.,1.]]])
        bound=B._line_interval_arithmetic_bound(faces,np.array([1000.5,0.]),np.array([0.,1.]))
        seam=1.;next_seam=float(np.nextafter(seam,np.inf))
        self.assertGreaterEqual(bound,next_seam-seam)
        self.assertEqual(B._merge_intervals([[-4.,seam],[next_seam,4.]],epsilon=bound),[[-4.,4.]])
        self.assertEqual(len(B._merge_intervals([[-4.,seam],[seam+2*bound,4.]],epsilon=bound)),2)

    def test_join_coverage_accepts_only_guarded_expansion_and_never_a_missing_edge(self):
        B._require_join_coverage([[-4.,4.]],[[-4.00012,4.00008]],8e-5,'left',
                                 maximum_expansion=1.5e-4)
        with self.assertRaisesRegex(B.BP.ProfileError,'does not cover'):
            B._require_join_coverage([[-4.,4.]],[[-3.9998,4.00008]],8e-5,'left',
                                     maximum_expansion=1.5e-4)
        with self.assertRaisesRegex(B.BP.ProfileError,'expansion guard'):
            B._require_join_coverage([[-4.,4.]],[[-4.0002,4.00008]],8e-5,'left',
                                     maximum_expansion=1.5e-4)

    def test_positive_f64_corner_is_not_removed_after_f32_product_cancellation(self):
        points=np.array([[0.,0.],[9.43625545501709,9.764812469482422],
                         [14.424707412719727,14.926955223083496]],dtype=np.float32)
        ab=points[1]-points[0];bc=points[2]-points[1]
        self.assertEqual(np.float32(ab[0]*bc[1]-ab[1]*bc[0]),0.)
        self.assertFalse(B._encoded_collinear_forward(*points))

    def test_selected_span_cells_exclude_a_disconnected_attributed_road(self):
        main={'id':'main','width':.5,'points':[[0.,0.,5.],[10.,0.,5.]]}
        detached={'id':'detached','width':.5,'points':[[3.,0.,6.3],[7.,0.,6.3]]}
        world=SimpleNamespace(x0=0.,z0=0.,x1=10.,z1=10.,roads=[main,detached])
        site={'wetEdges':[[3.,5.],[7.,5.]]}
        geometry={'roadCapsuleGuardMetres':0.,'servingSegmentIndices':[0],
                  'servingSegmentXZ':[[0.,5.,10.,5.]],'constructionStart':-2.,
                  'constructionEnd':6.,'constructionHalf':2.,'maximumLandingMetres':2.}
        span=B._selected_span_outline(world.roads,geometry,np.array([3.,5.]),np.array([1.,0.]))
        cells=B._selected_span_cells(world,site,geometry,span)
        self.assertTrue(cells[4,4])
        self.assertFalse(cells[6,4])
        self.assertEqual(label(cells,structure=np.ones((3,3)))[1],1)

    def test_actor_center_approach_uses_current_collision_half_width(self):
        road={'id':'main','width':4.,'points':[[0.,0.,0.],[10.,0.,0.]]}
        outline=B.RoadOutline(SimpleNamespace(roads=[road]))
        geometry={'servingSegmentIndices':[0],
                  'servingSegmentXZ':outline.segments[:,:4].tolist()}
        actor=B._actor_center_outline([road],geometry)
        self.assertEqual(B.ACTOR_HALF_WIDTH_METRES,.5)
        self.assertEqual(actor.segments[0,4],3.5)

    def test_retained_assembly_and_solid_footprints_are_pinned_by_area(self):
        content=SimpleNamespace(objects=[
            {'low':[10.,0.,10.],'high':[14.,5.,14.],'assembly':'village'},
            {'low':[20.,0.,20.],'high':[22.,3.,22.],'collides':True}])
        support,colliding=B._retained_footprints(content)
        self.assertEqual(len(support),2);self.assertEqual(len(colliding),1)
        triangle=np.array([[9.,0.,9.],[15.,0.,9.],[9.,0.,15.]])
        self.assertTrue(B._footprint_intersects_triangle(support[0],triangle))

    def test_site8_releases_only_the_three_proved_solid_margin_nodes(self):
        shape=(422,422)
        world=SimpleNamespace(x0=0.,z0=0.,x=np.arange(shape[1])*2.,z=np.arange(shape[0])*2.,
            height=np.zeros(shape),solids=np.zeros(shape,bool),solid_ids=np.zeros(shape,np.int32),
            plan={'sea_level':-100.,'lakes':[],'rivers':[]},
            regions={'amberwood':{'center':[510.,540.]}})
        expected={(416,414),(416,415),(417,414)}
        for node in expected:world.solids[node]=True;world.solid_ids[node]=552
        crate={'region':'mirrorhold','node':'Prop_PierCrate_0','collides':True,
            'low':[833.6202436103217,0.,829.8254436103217],
            'high':[834.7373563896783,1.,830.9425563896783]}
        skiff={'region':'mirrorhold','node':'Prop_PierSkiff_0','collides':True,
            'low':[831.8788000476837,0.,833.5318],
            'high':[836.4787999523163,1.,835.0318]}
        content=SimpleNamespace(objects=[crate,skiff],assembly_records={},metadata={},
            world=SimpleNamespace(plan={}),placement_by_name={})
        self.assertEqual(B._site8_known_solid_margin_nodes(world,content),expected)
        world.claimed_bridge_solid_margin_source_nodes=expected
        support,_=B._retained_footprints(content);before=world.solids.copy()
        crossing={'id':7,'key':B.MIRROR_OUTLET_SOLID_RELEASE_KEY}
        released=B._site_solid_margin_release_nodes(
            world,crossing,support,set(),world.height)
        self.assertEqual(released,expected);np.testing.assert_array_equal(world.solids,before)
        self.assertEqual(B._site_solid_margin_release_nodes(
            world,{'id':8,'key':'another_river@16'},support,set(),world.height),set())
        polygon=np.array([[827.1,0.,831.1],[827.4,0.,831.1],[827.1,0.,831.4]])
        world.claimed_bridge_colliding_boxes=()
        self.assertTrue(B._solid_overlap(world,polygon))
        self.assertFalse(B._solid_overlap(world,polygon,released))
        world.claimed_bridge_colliding_boxes=((np.array([827.,831.]),np.array([827.5,831.5])),)
        self.assertTrue(B._solid_overlap(world,polygon,released))
        face=np.array([[827.1,10.,831.1],[827.4,10.,831.1],[827.1,10.,831.4]])
        below=('known',np.array([827.15,0.,831.15]),np.array([827.35,1.,831.35]))
        world.claimed_bridge_solid_clearance_sources={(416,414):(below,)}
        world.claimed_bridge_colliding_objects=(below,)
        self.assertFalse(B._solid_overlap(world,face,(),face))
        intersecting=('known',np.array([827.15,9.8,831.15]),np.array([827.35,10.2,831.35]))
        world.claimed_bridge_solid_clearance_sources={(416,414):(intersecting,)}
        world.claimed_bridge_colliding_objects=(intersecting,)
        self.assertTrue(B._solid_overlap(world,face,(),face))
        actor=('known',np.array([827.15,10.5,831.15]),np.array([827.35,11.,831.35]))
        world.claimed_bridge_solid_clearance_sources={(416,414):(actor,)}
        world.claimed_bridge_colliding_objects=(actor,)
        self.assertTrue(B._solid_overlap(world,face,(),face))
        flat=('known-flat',np.array([827.15,10.,831.15]),np.array([827.35,10.,831.35]))
        world.claimed_bridge_solid_clearance_sources={(416,414):(flat,)}
        world.claimed_bridge_colliding_objects=(flat,)
        self.assertTrue(B._solid_overlap(world,face,(),face))
        world.claimed_bridge_solid_clearance_sources={}
        self.assertTrue(B._solid_overlap(world,face,(),face))
        actual_overlap={'kind':'box','low':np.array([827.,831.]),
                        'high':np.array([829.,833.]),'source':'test'}
        blocked=B._site_solid_margin_release_nodes(
            world,crossing,support+[actual_overlap],set(),world.height)
        self.assertNotIn((416,414),blocked)
        self.assertNotIn((416,414),B._site_solid_margin_release_nodes(
            world,crossing,support,{(416,414)},world.height))
        unknown={'region':'mirrorhold','node':'Unknown_Solid','collides':True,
                 'low':[827.,0.,831.],'high':[829.,1.,833.]}
        content.objects.append(unknown)
        self.assertEqual(B._site8_known_solid_margin_nodes(world,content),set())
        self.assertNotIn((416,414),B._site8_solid_clearance_sources(world,content))

    def test_assembly_extension_and_standalone_authored_footing_are_protected(self):
        placement={'node':'Building_Test','kind':'building'}
        member={'low':[10.,0.,10.],'high':[12.,4.,12.],'assembly':'test.group',
                'region':'test','source':placement}
        footing={'low':[20.,0.,20.],'high':[21.,2.,21.],'region':'test','node':'Footing_Test',
                 'sourcePivot':[20.,0.,20.],'shift':[1.,0.,2.]}
        world=SimpleNamespace(plan={'retained_footings':{'test':[{'node':'Footing_Test','radius':3.}]}})
        content=SimpleNamespace(objects=[member,footing],world=world,
            metadata={'test':{'placements':[placement]}},
            assembly_records={'test.group':{'translation':[0.,0.,0.],'foundationFootprints':1}},
            placement_by_name={('test','Footing_Test'):footing})
        support,_=B._retained_footprints(content)
        exact=[item for item in support if item['source']=='assembly-footprint']
        circles=[item for item in support if item['source']=='retained-footing']
        self.assertEqual(len(exact),1);self.assertEqual(len(circles),1)
        self.assertEqual(exact[0]['low'].tolist(),[8.5,8.5])
        self.assertEqual(exact[0]['high'].tolist(),[13.5,13.5])
        self.assertEqual(circles[0]['center'].tolist(),[21.,22.])
        tangent=np.array([[24.,0.,22.],[25.,0.,21.],[25.,0.,23.]])
        overlap=np.array([[23.9,0.,22.],[25.,0.,21.],[25.,0.,23.]])
        self.assertFalse(B._footprint_intersects_triangle(circles[0],tangent))
        self.assertTrue(B._footprint_intersects_triangle(circles[0],overlap))

    def test_prepared_surface_queries_only_the_actual_encoded_triangles(self):
        positions=np.array([[0.,1.,0.],[0.,2.,1.],[1.,3.,0.],[1.,4.,1.]],float)
        mesh=B.M.Mesh(positions=positions,normals=np.tile([0.,1.,0.],(4,1)),
                      uvs=np.zeros((4,2)),indices=np.array([0,1,2,2,1,3]),material='bridge_timber')
        component={'slice':np.s_[0:1,0:1],'cells':np.ones((1,1),bool),
                   'arch':{'prepared':True},'_preparedMeshCache':(mesh,np.array([0]))}
        field={'x0':0.,'z0':0.,'mask':np.ones((1,1),bool),'height':np.zeros((2,2)),
               'components':[component]}
        world=SimpleNamespace(height_at=lambda x,z:np.zeros(np.broadcast(x,z).shape),bridge_field=field)
        actual=B.surface_at(world,np.array([.25,-1e-12,.5,1.]),np.array([.25,.25,.5,1.]))
        self.assertEqual(actual[0],1.75)
        self.assertEqual(actual[1],0.)
        self.assertEqual(actual[2],2.5)
        self.assertEqual(actual[3],4.)


if __name__ == '__main__':
    unittest.main()
