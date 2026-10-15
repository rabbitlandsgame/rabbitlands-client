"""Westhaven's compact coordinate contract, independent of rendering imports."""
FACTOR = 396 / 576
SERVER_CELLS = 396
SERVER_ORIGIN = (120, 172)
REVISION = 'inhabited-harbour-396-v1'


def point(x, z):
    """First-pass content migration; authored service/door posts override it."""
    return float(x) * FACTOR, float(z) * FACTOR


def tile(value):
    x, z = point(float(value[0]) - 174, 250 - float(value[1]))
    return [min(395, max(0, round(x + 120))), min(395, max(0, round(172 - z)))]


def configure(g):
    """Recompose named places and route stations; building dimensions stay local."""
    import numpy as np
    a = g['ANCHORS']
    a.update(main_quay=(34, 6), fish_market=(-8, -9), lower_square=(11, -34),
        mid_street=(25, -60), city_gate=(4, -53), arcade=(-7, -90),
        cathedral=(53, -95), cathedral_approach=(53, -77),
        campanile=(-6, -146), brass_dome=(55, -151), crown_terrace=(42, -168),
        high_spire=(109, -109), north_gate=(105, -155),
        upland_farm=(151, -120), farm_door=(151, -108),
        upland_chapel=(222, -127), crossroads=(180, -93),
        east_watch=(235, -99), watch_door=(235, -86),
        hill_estate=(239, -45), estate_door=(239, -34),
        north_exit=(190.5, -213.5), east_exit=(264.5, -37.5),
        mole_root=(-67, 8), mole_bastion=(-56, 31), mole_head=(125, 64),
        west_quay=(-67, 0), custom_house=(-51, -14), custom_house_entry=(-51,-8),
        bonded_entry=(-29,-21),
        cargo_pier=(68, 15), crane_pier=(105, 16),
        chandlery=(86, -3), ropewalk=(135, -15), shipyard=(159, 5),
        shipyard_slip=(169, 23), guild_hall=(65, -35),
        gullstone_watch=(-54, 72), gullstone_door=(-67, 73),
        lighthouse_yard=(215, 80))
    g['SPAWN'] = a['main_quay']; g['SPAWN_MARKET'] = a['fish_market']
    g['SPAWN_CROWN'] = a['crown_terrace']; g['SPAWN_LIGHTHOUSE'] = a['lighthouse_yard']
    route = lambda *names: np.asarray([a[n] for n in names], float)
    roads = g['ROADS']; heights = g['ROAD_HEIGHTS']
    roads.update(quayside=np.asarray([(-68,0),(-35,3),(0,6),(34,6),(86,0),(135,1),(159,5)],float),
        market_climb=np.asarray([(34,6),(12,5),(-19,0),(-23,-13),(-15,-28),(11,-34)],float),
        gate_climb=route('lower_square','city_gate','mid_street'),
        arcade_walk=np.asarray([(25,-60),(25,-72),(-7,-90),(24,-81),(53,-77)],float),
        crown_climb=np.asarray([(53,-77),(78,-91),(77,-121),(65,-134),(42,-168)],float),
        crown_link=route('crown_terrace','north_gate'),
        north_road=np.asarray([(105,-155),(133,-146),(171,-148),(190.5,-160),(190.5,-213.5)],float),
        farm_lane=np.asarray([(171,-148),(170,-130),(162,-108),(151,-108)],float),
        chapel_lane=np.asarray([(190.5,-160),(210,-153),(222,-143),(222,-136)],float),
        east_road=np.asarray([(105,-155),(119,-126),(143,-103),(180,-93),(207,-67),(236,-58),(264.5,-37.5)],float),
        cart_climb=np.asarray([(34,6),(54,4),(69,-14),(110,-26),(136,-52),(161,-71),(180,-93)],float),
        watch_lane=np.asarray([(180,-93),(213,-84),(235,-86)],float),
        coast_descent=np.asarray([(264.5,-37.5),(253,-11),(244,12)],float),
        bay_track=np.asarray([(172,5),(193,18),(215,19),(244,12),(262,24),(264,50),(254,62),(231,73),(215,80)],float),
        bell_lane=np.asarray([(-7,-90),(-28,-114),(-20,-137),(-6,-136)],float),
        lower_lane=np.asarray([(-68,-31),(-34,-31),(11,-34),(85,-34),(105,-34),(110,-26)],float),
        mid_lane=np.asarray([(-65,-63),(-29,-63),(25,-60),(83,-60),(106,-55)],float),
        gullstone_path=np.asarray([(-62,52),(-70,61),(-67,73),(-54,88),(-31,98),(7,107)],float),
        mole_approach=np.asarray([(-67,0),(-67,8)],float))
    heights.update(quayside=[3.4]*7, market_climb=[3.4,3.4,3.4,8.4,8.4,8.4],
        gate_climb=[8.4,14,14], arcade_walk=[14,17,21,21,28],
        crown_climb=[28,28,32,36,36], crown_link=[36,34],
        north_road=[34,33,32,34,34], farm_lane=[32,30,29,29], chapel_lane=[34,32,30,30],
        east_road=[34,32,31,29,26,23,22], cart_climb=[3.4,3.4,6.5,13,19,24,29],
        watch_lane=[29,33,35], coast_descent=[22,9,3.2],
        bay_track=[3.4,3.4,2.6,3.2,4.2,3.4,5.2,11,17],
        bell_lane=[21,25,28,28], lower_lane=[8.4,8.4,8.4,8.4,11,13], mid_lane=[14]*5,
        gullstone_path=[9,13,18,24,26,20], mole_approach=[3.4,5.2])
    for key in roads:
        g['ROAD_WIDTH'][key] = (14 if key=='quayside' else 5.6 if key in ('cart_climb','north_road','east_road') else 4.2) / g['SCALE']
        g['ROAD_SURFACE'].setdefault(key, g['TER'].PAVING if key in ('lower_lane','mid_lane','bell_lane') else g['TER'].PATH)
    g['QUAYSIDE'] = roads['quayside']; g['MOLE'] = route('mole_root','mole_bastion','mole_head')
    g['SHORE_CROSSINGS'] = {
        'quay-mole-ramp': ([(-67,3.55,-2),(-67,3.55,4),(-67,5.2,10),(-62,5.2,15)],6.2),
        'yard-bridge': ([(177,3.58,8),(194,3.58,18),(211,2.78,19)],5.6),
        'lamp-causeway': ([(260,4.35,23),(267,4.25,34),(263,3.55,52),(253,5.35,62)],5.2),
        'gullstone-bridge': ([(-62,5.2,15),(-73,5.8,24),(-76,7.1,37),(-62,9.15,52)],4.6),
    }
    g['FARM_FIELDS'] = [(140,-85,27),(187,-127,30)]
    g['CONTENT_LAYOUT']['services'] = [dict(role=r,position=[x,3.4,z]) for r,x,z in
        [('information',22,0),('storage',34,-2),('crafting_station',45,0),('training',48,8)]]
    g['CONTENT_LAYOUT']['harvest'] = {'Wheat':[[140,-85,6]],'Sage':[[187,-127,6]],
        'Cotton':[[180,-121,13]],'Kelp':[[214,8,10],[241,8,10]],
        'Shell':[[219,1,10],[239,1,10]],'Salt':[[228,6,12]],'Clay':[[209,-1,10]]}
    g['CONTENT_LAYOUT']['wildlife'] = {'rootback_boar':[[181,-114,16],[204,-109,14]],
        'moss_horn_ram':[[167,-126,15],[228,-168,18]],'bronze_tide_crab':[[226,-2,9],[240,-1,9]],
        'coralcrest_heron':[[214,1,9]],'brambleback_boar':[[-32,108,17]],
        'moor_wisp_hound':[[246,-183,15],[69,-201,17]]}

    g['CONTENT_LAYOUT']['primaryArrivalOnly'] = True
    g['CONTENT_LAYOUT']['requireFullWildlife'] = True
    g['CONTENT_LAYOUT']['npcs'] = {
        'Captain Iven':[30,3.4,1], 'Sela Quay':[37,3.4,-5],
        'Harbour Reeve Anselm Coy':[-47,3.4,-6],
        'Crane Foreman Bettis Roke':[101,3.4,4],
        'Fishwife Orla Mudge':[-10,8.4,-7],
        'Yard Master Gervas Tull':[177,3.4,-4],
        'Ropewalk Mistress Sabra Hine':[134,3.4,-6],
        'Guild Notary Elber Wisk':[65,8.4,-46],
        "Astronomers' Hall Porter Nyle":[66,36,-147],
        'Bell-Warden Cathis Orr':[-13,28,-136],
        'Lamp Rock Keeper Fen Tallow':[219,17,84],
        'Gullscar Farmer Rhys Camber':[156,29,-109],
        "Factor's Clerk Ivet Somer":[241,23,-33],
        'Bastion Sergeant Odo Fell':[-67,12,59],
    }
