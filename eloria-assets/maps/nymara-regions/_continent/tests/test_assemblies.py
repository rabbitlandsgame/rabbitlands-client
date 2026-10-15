"""A connected compound must retain actual spacing, grade and quiet water."""
import sys
from pathlib import Path
import unittest

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assemblies as A


def ground(x,z):
    x,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(z,float))
    return 31.+x*.01+z*.02


class AssembliesTests(unittest.TestCase):
    def test_compressed_anchor_does_not_compress_full_size_components(self):
        p=[{'node':'Plaza_Monument','kind':'landmark','position':[0,31,0]},
           {'node':'Plaza_Fountain_0','kind':'prop','position':[25,31,25]}]
        b={'Plaza_Monument':([-10,31,-10],[10,91,10]),'Plaza_Fountain_0':([23,31,23],[27,34,27])}
        a=A.build_assemblies('four_gates',p,b,ground)['four_gates.civic']
        shift=a.shift_to(lambda q:q*.78+[530,840],lambda x,z:20.)
        actual=np.array([row['position'] for row in p])+shift
        np.testing.assert_allclose(actual[1]-actual[0],[25,0,25])
        self.assertEqual(actual[0,1],20.)
        self.assertEqual(a.reference_y,31.)

    def test_arcade_quarters_and_small_street_details_share_the_civic_group(self):
        for name,kind in [('Plaza_Arcade_0','landmark'),('Plaza_Monument_Crystal','landmark'),
                          ('Goods_four-gates-reedworks','small_dressing'),('City_Wall_02','wall')]:
            self.assertEqual(A.placement_group('four_gates',{'node':name,'kind':kind}), 'four_gates.civic')
        self.assertIsNone(A.placement_group('four_gates',{'node':'Tree_plaza_1','kind':'tree'}))

    def test_water_city_uses_one_sea_datum_and_does_not_fill_spans(self):
        p=[{'node':'Landmark_Pavilion_pavilion_west','kind':'landmark'},
           {'node':'Causeway_ring_west_east','kind':'landmark'},
           {'node':'Landmark_Cathedral','kind':'landmark'}]
        b={p[0]['node']:([0,4,0],[4,10,4]),p[1]['node']:([4,-8,0],[96,5,4]),p[2]['node']:([96,14,0],[100,50,4])}
        a=A.build_assemblies('crownwater',p,b,ground)['crownwater.causeway-city']
        shift=a.shift_to(lambda q:q+[300,1200],lambda x,z:120.,water_level=0.)
        self.assertEqual(shift[1],0.)
        target,weight=a.sample_foundation([302,350,398],[1202]*3,shift,ground)
        np.testing.assert_allclose(weight,[1,0,1])
        self.assertEqual(a.reference_y,0.)
        self.assertEqual(len(a.footprints),2)

    def test_baked_zero_origin_porches_follow_their_house_and_actual_bounds(self):
        p=[{'node':'town_house_00','kind':'building','position':[38,2.2,-25]},
           {'node':'town_porch_00','kind':'structure','position':[0,0,0]}]
        b={p[0]['node']:([35,-1,-28],[41,8,-22]),p[1]['node']:([33,2.15,-29],[38,2.25,-24])}
        a=A.build_assemblies('manymouth_delta',p,b,ground)['manymouth_delta.boardwalk-town']
        np.testing.assert_allclose(a.bounds,[[33,-1,-29],[41,8,-22]])
        self.assertEqual(set(a.nodes),{'town_house_00','town_porch_00'})
        self.assertNotEqual(A.placement_group('manymouth_delta',{'node':'east_hamlet_porch_00'}),a.id)

    def test_fortress_roof_height_is_never_used_as_the_ground_datum(self):
        p=[{'node':'Landmark_Orrery','kind':'landmark','position':[99.7,134.35,-216.6]},
           {'node':'Landmark_CitadelCourt','kind':'landmark','position':[99.7,98,-138.6]}]
        b={p[0]['node']:([90,124,-225],[110,150,-205]),p[1]['node']:([60,97,-170],[140,120,-105])}
        a=A.build_assemblies('mirrorhold',p,b,lambda x,z:98.)['mirrorhold.city']
        shift=a.shift_to(lambda q:q+[740,790],lambda x,z:70.)
        self.assertEqual(shift[1],-28.)
        self.assertEqual(np.diff(np.array([134.35,98])+shift[1])[0],98-134.35)

    def test_regrounding_preserves_existing_mapping_references_and_fails_on_tearing(self):
        objects=[{'shift':np.array([20.,-10,50]),'low':np.zeros(3),'high':np.ones(3),'targetGround':20.} for _ in range(2)]
        mapped=objects[0]['shift'];bounds=objects[0]['low']
        A.apply_group_delta(objects,[0,2,0]);A.assert_rigid(objects)
        np.testing.assert_allclose(mapped,[20,-8,50]);np.testing.assert_allclose(bounds,[0,2,0])
        objects[1]['shift'][1]+=.01
        with self.assertRaisesRegex(ValueError,'independent component'):A.assert_rigid(objects)

    def test_local_foundation_retains_grade_and_leaves_distant_wilderness_untouched(self):
        p=[{'node':'Building_CliffHouse_0','kind':'building'}];b={p[0]['node']:([0,0,0],[8,10,8])}
        a=A.build_assemblies('mirrorhold',p,b,ground)['mirrorhold.city']
        shift=np.array([100.,5,200.])
        y,w=a.sample_foundation([102,106,200],[202,206,300],shift,ground)
        self.assertAlmostEqual(y[1]-y[0],.12)
        np.testing.assert_allclose(w,[1,1,0])

    def test_fortress_harbour_and_cliff_streets_cannot_drift_into_one_another(self):
        members=['Landmark_Orrery','Landmark_Quay','Building_CliffHouse_10','Landmark_Retaining_1','Prop_Signpost_0']
        self.assertEqual({A.placement_group('mirrorhold',{'node':name,'kind':'landmark'}) for name in members},{'mirrorhold.city'})

    def test_canopy_village_keeps_support_trees_without_crown_sized_ground_pads(self):
        for kind,suffix in (('tree','Wood'),('foliage','Canopy')):
            p={'node':'Landmark_Giant_3_'+suffix,'kind':kind}
            self.assertEqual(A.placement_group('amberwood',p),'amberwood.canopy-village')
            self.assertFalse(A.supports_ground(p))
        for name in ('Landmark_CanopyPlatform_4','Landmark_CanopyWalkway_3'):
            self.assertFalse(A.supports_ground({'node':name,'kind':'landmark'}))

    def test_canopy_spiral_stairs_move_with_their_platforms_and_dig_no_ground_of_their_own(self):
        # Library positions of platform 3 and its stair: the stair's top stands 1.65 m under the platform.
        platform={'node':'Landmark_CanopyPlatform_3','kind':'landmark','position':[93.8471,65.8284,-171.0711]}
        stairs=[{'node':'Walk_Prop_SpiralStair_'+str(i),'kind':'prop','walk_surface':True} for i in range(6)]
        stairs[3]['position']=[94.7949,54.8284,-170.8318]
        for stair in stairs:
            self.assertEqual(A.placement_group('amberwood',stair),'amberwood.canopy-village')
            # Like its platform, a stair carries no footing of its own: under the two western platforms, which the
            # continent's relief buries, a stair footing dug a pit through the relief.
            self.assertFalse(A.supports_ground(stair))
        self.assertIsNone(A.placement_group('whitehorn_range',stairs[3]),'only Amberwood carries canopy stairs')
        b={'Landmark_CanopyPlatform_3':([88.,64.,-176.],[100.,67.,-166.]),'Walk_Prop_SpiralStair_3':([92.8,54.8,-172.8],[96.8,64.2,-168.8])}
        village=A.build_assemblies('amberwood',[platform,stairs[3]],b,ground)['amberwood.canopy-village']
        self.assertEqual(set(village.nodes),{'Landmark_CanopyPlatform_3','Walk_Prop_SpiralStair_3'})
        self.assertEqual(len(village.footprints),0,'neither the stair nor the platform supports the ground')
        # One shift carries both, so the stair keeps its place under the platform wherever the village stands.
        shift=village.shift_to(lambda q:np.asarray(q)+[500.,700.],lambda x,z:40.)
        np.testing.assert_allclose((np.array(stairs[3]['position'])+shift)-(np.array(platform['position'])+shift),
                                   np.array(stairs[3]['position'])-np.array(platform['position']))

    def test_the_glacier_temple_and_the_lower_camp_are_whitehorn_compounds_on_their_own_ground(self):
        temple={'node':'Landmark_glacier_temple','kind':'landmark','collides':True}
        camp=[{'node':name,'kind':'landmark' if name=='Landmark_LowerCamp' else 'prop'} for name in A.WHITEHORN_LOWER_CAMP]
        steeple={'node':'Landmark_TemplePinnacle1','kind':'landmark'}
        self.assertEqual(A.placement_group('whitehorn_range',temple),'whitehorn_range.glacier-temple')
        self.assertEqual({A.placement_group('whitehorn_range',p) for p in camp},{'whitehorn_range.lower-camp'})
        # The steeples ride on the temple as attachments, which a compound member cannot be; other huts stay singles.
        for single in (steeple,{'node':'Landmark_BridgeWatch','kind':'landmark'},{'node':'Landmark_TempleRest','kind':'landmark'}):
            self.assertIsNone(A.placement_group('whitehorn_range',single))
        self.assertIsNone(A.placement_group('grey_moors',temple),'the rule is Whitehorn\'s own')
        b={'Landmark_glacier_temple':([86.,40.,-246.2],[113.,89.,-220.8])}
        b.update({p['node']:([64.5+i,25.8,39.4],[66.5+i,27.,41.4]) for i,p in enumerate(camp)})
        groups=A.build_assemblies('whitehorn_range',[temple,*camp],b,ground)
        # The temple's footing covers its whole body; the camp's covers the hut, and its props follow it without one.
        self.assertEqual(len(groups['whitehorn_range.glacier-temple'].footprints),1)
        self.assertEqual(len(groups['whitehorn_range.lower-camp'].footprints),1)
        self.assertEqual(groups['whitehorn_range.glacier-temple'].datum,'terrain')

    def test_city_streets_share_the_building_support_without_exporting_a_rectangle(self):
        p=[{'node':'Building_CliffHouse_'+str(i),'kind':'building'} for i in range(3)]
        b={p[0]['node']:([0,0,0],[8,10,8]),p[1]['node']:([100,0,0],[108,10,8]),
           p[2]['node']:([0,0,100],[8,10,108])}
        a=A.build_assemblies('mirrorhold',p,b,ground)['mirrorhold.city']
        y,w=a.sample_foundation([30,110,250],[30,110,250],np.zeros(3),ground,feather=30.)
        self.assertEqual(w[0],1.,'The empty street between houses needs continuous support')
        self.assertEqual(w[1],0.,'The uninhabited corner of the bounding rectangle is not imported')
        self.assertEqual(w[2],0.)
        self.assertAlmostEqual(y[0],31.9)

    def test_ruin_courts_gate_and_culvert_keep_the_original_temple_spacing(self):
        names=('Temple_Ssarathi','Temple_VaultPortal','Colonnade_ritual_plaza',
               'Colonnade_lily_court','Secret_ruins_culvert_mouth','WaterGate','SerpentColumn_0_1')
        self.assertEqual({A.placement_group('ssarathi_ruins',{'node':name,'kind':'landmark'}) for name in names},
                         {'ssarathi_ruins.ruin-city'})
        self.assertIsNone(A.placement_group('ssarathi_ruins',{'node':'Jungle_0','kind':'tree'}))
        self.assertEqual(A.placement_group('ssarathi_ruins',{'node':'Secret_ruins_temple_focus','kind':'prop'}),
                         'ssarathi_ruins.temple-focus')

    def test_steppe_encampment_preserves_the_lane_between_pavilion_and_hall(self):
        names=('Structure_Palisade','Encampment_Pavilion_00','Encampment_Cart_00',
               'Landmark_sunmane_great_hall','Landmark_sunmane_secret_steppe-hall-vault')
        self.assertEqual({A.placement_group('sunmane_steppe',{'node':n,'kind':'prop'}) for n in names},
                         {'sunmane_steppe.encampment'})
        self.assertIsNone(A.placement_group('sunmane_steppe',{'node':'Landmark_orun_banner_shrine_00','kind':'landmark'}))

    def test_city_apron_does_not_import_the_old_mountain_beyond_actual_support(self):
        p=[{'node':'Building_CliffHouse_'+str(i),'kind':'building'} for i in range(2)]
        b={p[0]['node']:([0,0,0],[8,10,8]),p[1]['node']:([20,0,0],[28,10,8])}
        a=A.build_assemblies('mirrorhold',p,b,ground)['mirrorhold.city']
        # The old mountain outside the western city edge is much higher than
        # the city. Its slope must not become an unrelated exterior mound.
        survey=lambda x,z:50.+np.maximum(-np.asarray(x),0.)*3.
        x=np.array([-50.,-33.5,-17.5,-1.5,10.,20.])
        y,w=a.sample_foundation(x,np.full_like(x,4),np.zeros(3),survey,feather=32.)
        np.testing.assert_allclose(y[:4],54.5)
        np.testing.assert_allclose(w,[0,0,.5,1,1,1])
        self.assertEqual(y[4],50.,'The shared street keeps its actual source survey')

    def test_a_landmark_and_its_named_natural_companions_form_one_compound(self):
        cave='Landmark_sunmane_cave_east_adit'
        p=[{'node':cave,'kind':'landmark'}]+[{'node':f'{cave}_EarthRock_{i}','kind':'rock'} for i in range(3)]
        p+=[{'node':'Rock_0001','kind':'rock'},{'node':'Landmark_gone_EarthRock_0','kind':'rock'},
            {'node':'Landmark_sunmane_cave_east_adit_EarthRockish_0','kind':'rock'}]
        groups={q['node']:A.placement_group('sunmane_steppe',q,p) for q in p}
        self.assertEqual({groups[q['node']] for q in p[:4]},{'sunmane_steppe.'+cave})
        # An unrelated rock, a companion whose structure is not placed and a name that only resembles the rule stay natural.
        self.assertIsNone(groups['Rock_0001']);self.assertIsNone(groups['Landmark_gone_EarthRock_0'])
        self.assertIsNone(groups['Landmark_sunmane_cave_east_adit_EarthRockish_0'])
        # Companions are read from the placements every loader passes; alone, a structure is what its own rules make it.
        self.assertIsNone(A.placement_group('sunmane_steppe',p[0]))
        b={q['node']:([10.+i,14.,-60.],[14.+i,21.,-55.]) for i,q in enumerate(p[:4])}
        compound=A.build_assemblies('sunmane_steppe',p,b,ground)['sunmane_steppe.'+cave]
        self.assertEqual(set(compound.nodes),set(b))
        self.assertEqual(len(compound.footprints),4,'the mouth and each rock carry the legacy slope they stood on')
        self.assertEqual((compound.datum,len(compound.member_boxes)),('terrain',4))
        # A structure already in a compound brings its companions into that compound.
        orrery=[{'node':'Landmark_Orrery','kind':'landmark'},{'node':'Landmark_Orrery_EarthRock_0','kind':'rock'}]
        self.assertEqual({A.placement_group('mirrorhold',q,orrery) for q in orrery},{'mirrorhold.city'})

    def test_the_audits_named_pairs_join_a_structure_that_the_rule_cannot_read(self):
        # The sea arch is left out: measured as a compound it stood further from its legacy ground than as a single.
        p=[{'node':'Landmark_SeaArch','kind':'landmark'},{'node':'RockCluster_2_sea_arch_01','kind':'rock'}]
        self.assertEqual([A.placement_group('amberwood',q,p) for q in p],[None,None])
        grotto=[{'node':'Northern_Grotto_Bridge_Arch','kind':'bridge'},{'node':'Northern_Grotto_Abutment_0_-1','kind':'stone'},
                {'node':'Landmark_GeodeCave_0','kind':'landmark'},{'node':'Landmark_GeodeCave_1','kind':'landmark'}]
        self.assertEqual([A.placement_group('amethyst_barrens',q,grotto) for q in grotto],
                         ['amethyst_barrens.Northern_Grotto_Bridge_Arch']*3+[None])
        # Without its structure a named companion is only a natural placement.
        self.assertIsNone(A.placement_group('amethyst_barrens',grotto[1],grotto[1:2]))
        b={q['node']:([float(i),10.,0.],[i+4.,14.,4.]) for i,q in enumerate(grotto[:3])}
        compound=A.build_assemblies('amethyst_barrens',grotto[:3],b,ground)['amethyst_barrens.Northern_Grotto_Bridge_Arch']
        self.assertEqual(len(compound.footprints),3,'the arch, the cave and the abutment stone each hold their ground')

    def test_pulled_sites_and_the_palisade_gates_are_compounds_placed_by_their_footprints(self):
        members={'amberwood':('Landmark_EastQuarry','Landmark_Tower_far_watch','Landmark_Building_Lodge_29','Prop_Signpost_272','Crate_east_quarry_07'),
                 'verdant_stair':('Landmark_GreatTemple','Landmark_Stair_temple_climb','Rail_TempleCourt_3','Prop_quarry_02'),
                 'amethyst_barrens':('Landmark_GeodeCave_3','Landmark_ResonantCluster_7','Crystal_UplandSpire_1_2')}
        sites={'amberwood':'amberwood.east-quarry','verdant_stair':'verdant_stair.temple-summit','amethyst_barrens':'amethyst_barrens.upland-geode'}
        for region,names in members.items():
            for name in names:
                self.assertEqual(A.placement_group(region,{'node':name,'kind':'landmark'}),sites[region],name)
            self.assertEqual(A.REFERENCE[sites[region]][1],'footprints')
            if region!='verdant_stair':self.assertIsNone(A.REFERENCE[sites[region]][0])
        for name in ('Landmark_Building_Lodge_12','Landmark_CharcoalKiln_0','Secret_amber_charcoal_cache'):
            self.assertIsNone(A.placement_group('amberwood',{'node':name,'kind':'landmark'}),name)
        self.assertEqual({A.placement_group('sunmane_steppe',{'node':'Gate_'+side,'kind':'landmark'}) for side in ('North','South','East','West')},
                         {'sunmane_steppe.encampment'})
        self.assertEqual(A.placement_group('verdant_stair',{'node':'Landmark_UpperCourt','kind':'landmark'}),'verdant_stair.temple-summit')
        self.assertEqual(A.REFERENCE['verdant_stair.temple-summit'],((143.76912019141707,-126.2123795523941),'footprints'))
        self.assertEqual(A.SITE_PULL['amberwood.east-quarry'],(.02,160,False))
        self.assertEqual(A.SITE_PULL['amethyst_barrens.upland-geode'],(.02,160,True))
        self.assertNotIn('four_gates.civic',A.SITE_PULL,'every other compound keeps its 8 % pull')
        # A site with no reference point keeps the centre of its own bounds as its anchor.
        p=[{'node':'Landmark_EastQuarry','kind':'landmark'},{'node':'Landmark_Tower_far_watch','kind':'landmark'}]
        b={'Landmark_EastQuarry':([222.,20.,81.],[243.,37.,102.]),'Landmark_Tower_far_watch':([251.,31.,60.],[263.,49.,72.])}
        site=A.build_assemblies('amberwood',p,b,ground)['amberwood.east-quarry']
        np.testing.assert_allclose(site.reference_xz,[242.5,81.])
        self.assertEqual(site.datum,'footprints')
        # A site's props, signs and crystals stand on their own legacy ground; lamps, boats and levitating shards do not.
        for node,kind,expected in (('Prop_Crate_057','prop',True),('Crystal_UplandSpire_1_0','crystal',True),('Prop_LampPost_1','prop',False),
                                   ('Landmark_LevitatingShards_0','shards',False),('Rock_1','rock',False)):
            self.assertEqual(A.site_supports_ground({'node':node,'kind':kind}),expected,node)
        p.append({'node':'Prop_Crate_057','kind':'prop'});b['Prop_Crate_057']=([230.,28.,70.],[231.,29.,71.])
        self.assertEqual(len(A.build_assemblies('amberwood',p,b,ground)['amberwood.east-quarry'].footprints),3)

    def test_a_footprint_datum_stands_a_compound_on_the_ground_under_all_its_members(self):
        boxes=(np.array([[0.,0.],[10.,10.]]),np.array([[20.,0.],[30.,10.]]),np.array([[40.,0.],[50.,10.]]))
        compound=A.Assembly('grey_moors.site',('a','b','c'),np.array([25.,5.]),0.,'footprints',np.zeros((2,3)),(),boxes)
        source=lambda x,z:np.asarray(x,float)*0.+2.
        # The continent stands 5 m over the legacy ground, except a 25 m dome over the middle member's place.
        shift=np.array([100.,0.,300.])
        def continent(x,z):
            x=np.asarray(x,float);return np.where((x>=119.)&(x<=131.),27.,7.)
        self.assertAlmostEqual(compound.footprint_lift(continent,source,shift),5.)
        self.assertEqual(float(continent(*(compound.reference_xz+shift[[0,2]])))-2.,25.,'the reference point alone would lift it 25 m')
        # Under a turned layout the legacy ground is read where the unmapping leads.
        legacy=lambda x,z:np.where(np.asarray(z,float)>1000.,9.,2.)
        self.assertAlmostEqual(compound.footprint_lift(continent,legacy,shift,unmap=lambda x,z:(x,np.asarray(z)+1000.)),-2.)
        with self.assertRaisesRegex(ValueError,'needs member bounds'):
            A.Assembly('grey_moors.site',(),np.zeros(2),0.,'footprints',np.zeros((2,3)),()).footprint_lift(continent,source,shift)
        # The canopy village keeps its reference point: a footprint lift would raise the market stair's deck past its run.
        self.assertEqual(A.REFERENCE['amberwood.canopy-village'],((61.2229,-141.8745),'terrain'))

    def test_city_apron_uses_euclidean_corner_distance_and_a_smooth_boundary(self):
        p=[{'node':'Building_CliffHouse_'+str(i),'kind':'building'} for i in range(2)]
        b={p[0]['node']:([0,0,0],[8,10,8]),p[1]['node']:([20,0,0],[28,10,8])}
        a=A.build_assemblies('mirrorhold',p,b,ground)['mirrorhold.city']
        _,w=a.sample_foundation([-25.5,-1.5,-1.5001],[33.5,4,4],np.zeros(3),ground,feather=32.)
        self.assertEqual(w[0],0.,'A square 24m corner offset is more than32m from the actual city')
        self.assertEqual(w[1],1.)
        self.assertLess(abs(w[2]-w[1]),1e-9)


if __name__=='__main__':unittest.main()
