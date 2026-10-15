"""Discovery moves preserve identity and rigid prop shape on real graded ground."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import os
import unittest
import numpy as np

REG=Path(__file__).resolve().parents[1]/'maps/nymara-regions'
sys.path[:0]=[str(REG/'mirrorhold/source'),str(REG/'_toolkit')]
import secret_approaches as S
from amberwood import mesh as M
from amberwood.stonework import MeshGroup
from regionbuild import Placement


def fixture():
    build=SimpleNamespace(placements=[],meshes={},interactives=[],terrain_meshes={},landmarks=[])
    for i,(secret,point) in enumerate(S.OLD_POSTS.items()):
        node='Secret_'+secret.replace('-','_')
        mesh=MeshGroup().add(M.box((2.,.18,2.),material='pale_ashlar'))
        build.meshes[node]=mesh
        build.placements.append(Placement(node,node,(point[0],point[1]-.05,point[2]-1.8),rotation_y=.4))
        build.interactives.append(dict(id='secret-'+secret,kind='secret',secret=secret,name=secret,
            label='original discovery',prop='cracked_slab' if i else 'loose_stone',key='Storage Token' if i else '',
            destinationMap='mirrorhold_secrets',destinationSpawn=secret,authority='server',position=list(point)))
    def ground(x,z):return 84. if z>-150 else 91.3536-.267*(x-62.)
    for name,x0,x1,z0,z1 in [('basin',80.,96.,-118.,-99.),('court',55.,73.,-202.,-184.)]:
        build.terrain_meshes['Terrain_'+name]=M.quad([(x,ground(x,z),z) for x,z in [(x0,z0),(x0,z1),(x1,z1),(x1,z0)]],material='rock')
    return build


class SecretApproaches(unittest.TestCase):
    def test_preparation_releases_old_protection_without_changing_identity(self):
        build=fixture();original=deepcopy(build.interactives)
        S.prepare(build)
        for old,entry,prop in zip(original,build.interactives,build.placements):
            for key in S.IDENTITY_FIELDS:self.assertEqual(entry[key],old[key])
            self.assertEqual(tuple(entry['position']),S.POSTS[entry['secret']])
            self.assertGreater(np.linalg.norm(np.array(prop.position)[[0,2]]-np.array(old['position'])[[0,2]]),15.)
            self.assertFalse(prop.collides)
        once=deepcopy(build.secret_approaches);S.prepare(build)
        self.assertEqual(once,build.secret_approaches)

    def test_final_slab_is_rigidly_seated_on_grade_with_uvs_and_topology_exact(self):
        build=fixture();S.prepare(build)
        prop=build.placements[1];old=build.meshes[prop.mesh].parts[0].copy()
        terrain={n:m.positions.copy() for n,m in build.terrain_meshes.items()}
        S.finish(build);new=build.meshes[prop.mesh].parts[0]
        self.assertTrue(np.array_equal(old.indices,new.indices))
        self.assertTrue(np.array_equal(old.uvs,new.uvs))
        self.assertEqual(old.material,new.material)
        self.assertTrue(np.allclose(np.linalg.norm(old.positions[:,None]-old.positions[None,:],axis=2),
                                    np.linalg.norm(new.positions[:,None]-new.positions[None,:],axis=2),atol=1e-10))
        for n,positions in terrain.items():self.assertTrue(np.array_equal(positions,build.terrain_meshes[n].positions))
        rotation=M.rotation_y(prop.rotation_y)[:3,:3]
        world=new.positions@rotation.T+prop.position
        # The complete rigid slab follows the real plane, not a horizontal
        # root seated at one point with a floating downhill edge.
        signed=world[:,1]-(91.3536-.267*(world[:,0]-62.))
        self.assertLess(float(np.ptp(signed)),.19)
        self.assertAlmostEqual(float(signed.min()),-.05-.09*np.sqrt(1+.267**2),places=6)
        once=new.positions.copy();S.finish(build)
        self.assertTrue(np.array_equal(once,build.meshes[prop.mesh].parts[0].positions))

    def test_manifest_rejects_unfinished_and_preserves_room_key_links(self):
        build=fixture();S.prepare(build)
        with self.assertRaisesRegex(ValueError,'Unfinished'):S.manifest(build,{})
        S.finish(build);payload={};S.manifest(build,payload)
        entries=payload['secretApproaches']['entries']
        self.assertEqual(entries[1]['identity']['key'],'Storage Token')
        self.assertEqual(entries[1]['identity']['destinationSpawn'],'mirror-orrery-vault')
        self.assertEqual(entries[0]['nativeServerTile'],[208,205])
        self.assertEqual(entries[1]['nativeServerTile'],[182,289])

    def test_rigid_tilt_is_identity_on_flat_ground(self):
        self.assertTrue(np.array_equal(S._tilt([0.,0.]),np.eye(3)))
        rotation=S._tilt([-.267,.05])
        self.assertTrue(np.allclose(rotation.T@rotation,np.eye(3),atol=1e-12))
        self.assertAlmostEqual(np.linalg.det(rotation),1.,places=12)

    def test_final_verge_poses_keep_the_authoritative_discovery_markers(self):
        build=fixture();S.prepare(build)
        marker_xz=[(e['position'][0],e['position'][2]) for e in build.interactives]
        marker_tiles=[e['serverTile'][:] for e in build.interactives]
        S.finish(build)
        self.assertEqual(marker_xz,[(e['position'][0],e['position'][2]) for e in build.interactives])
        self.assertEqual(marker_tiles,[e['serverTile'] for e in build.interactives])
        self.assertEqual([(p.position[0],p.position[2]) for p in build.placements],[(88.,-111.7),(62.5,-191.)])
        self.assertEqual(build.placements[1].rotation_y,0.)


@unittest.skipUnless(os.environ.get('ELORIA_SECRET_REVIEW_PACKAGE'),
                     'Pass the completed emitted package to check the literal Basin lip regression')
class EmittedBasinFoundation(unittest.TestCase):
    def test_discovery_props_clear_the_literal_trigger_and_lens_edge_regressions(self):
        import glb_reader as G
        package=Path(os.environ['ELORIA_SECRET_REVIEW_PACKAGE'])
        document,body=G.load(package/'world.glb')
        cases={
            'Secret_mirror_basin_spring':((87.625,-109.375),(87.5,-109.5),(86.75,-109.25),(87.25,-109.25)),
            'Secret_mirror_orrery_vault':((62.51478537790619,-193.11055247819513),(60.75,-192.75),(61.25,-192.75)),
        }
        for name,points in cases.items():
            triangles=G.triangles(document,body,G.named(document,name))
            self.assertGreater(len(triangles),0)
            lower=triangles.min((0,1))[[0,2]];upper=triangles.max((0,1))[[0,2]]
            for point in points:
                # The entire projected prop box clears the actor, so this
                # conservative check cannot hide a taller mesh intersection.
                distance=np.linalg.norm(np.maximum(np.maximum(lower-point,np.array(point)-upper),0.))
                with self.subTest(node=name,point=point):self.assertGreater(distance,.45)

    def test_two_literal_western_lip_samples_keep_the_original_structural_support(self):
        import glb_reader as G
        from verify_runtime import VerticalRayIndex
        package=Path(os.environ['ELORIA_SECRET_REVIEW_PACKAGE'])
        document,body=G.load(package/'world.glb')
        nodes=[i for i in G.named(document,'Terrain_') if not any(token in document['nodes'][i].get('name','')
               for token in ('_StreamCollar_','_ContinentBlend_','OuterEscarpment'))]
        earth=VerticalRayIndex(G.triangles(document,body,nodes))
        for x,z,expected in ((76.728799,-87.9464,83.56032544670984),
                             (77.1788,-88.3964,83.79786967666438)):
            with self.subTest(point=(x,z)):
                self.assertAlmostEqual(earth.top_hit(x,z),expected,delta=.003)


if __name__=='__main__':unittest.main()
