import copy,os,unittest
from pathlib import Path
from types import SimpleNamespace
import publish_interior_staff as P
import test_generate_continent_walk_proof as proof_tests

class StaffSourceTests(unittest.TestCase):
    def test_exact_six_coordinate_edits_preserve_every_other_roster_field_and_repeat(self):
        lines=['# keep exact roster formatting\r\n']
        for name,region,old,new,*_ in P.POSTS:
            lines.append(f'npc | {name} | {region} | {old[0]} | {old[1]} | dialogue | actor_type=313 | Exact dialogue | price=9\r\n')
        lines.append('npc | Unrelated | room | 1 | 2 | shop | retained\r\n')
        original=''.join(lines);result,changes=P.rewrite_roster(original)
        self.assertEqual(len(changes),6)
        for before,after in zip(original.splitlines(),result.splitlines()):
            a,b=before.split('|'),after.split('|')
            if len(a)>5:self.assertEqual(a[:3]+a[5:],b[:3]+b[5:])
            else:self.assertEqual(a,b)
        second,changes=P.rewrite_roster(result)
        self.assertEqual(result,second);self.assertFalse(any(p['changed'] for p in changes))
        with self.assertRaisesRegex(ValueError,'unexpected authored position'):
            P.rewrite_roster(original.replace('| 58 | 58 |','| 59 | 58 |',1))
        with self.assertRaisesRegex(ValueError,'exactly one staff identity'):
            P.rewrite_roster(original+lines[1])

    def test_named_marker_reconciles_without_changing_unrelated_generic_markers(self):
        post=P.POSTS[3];name=post[0]
        generic={'id':'lens-master','label':'Lens Master','space':'lens_vault_grinding_room'}
        manifest={'coordinateTransform':{'serverOrigin':[0,204],'invertServerY':True},
                  'npcMarkers':[generic,{'id':'old-named-marker','name':name,'position':[47.5,6,16.5]}]}
        before=copy.deepcopy(manifest);result,reconciled=P.marker_update(manifest,[post])
        self.assertEqual(before,manifest)
        self.assertEqual(result['npcMarkers'][0],generic)
        self.assertEqual(len(result['npcMarkers']),2)
        self.assertEqual(reconciled,['old-named-marker'])
        self.assertEqual(result['npcMarkers'][1]['position'],[44.5,6.,16.5])
        self.assertEqual(P.marker_update(result,[post])[0],result)

@unittest.skipUnless(os.environ.get('ELORIA_PROOF_SERVER'),'paired production World required')
class StaffAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.R=P.runtime(Path(os.environ['ELORIA_PROOF_SERVER']))

    def test_occupied_arrival_repaired_without_changing_entry_or_return_and_collision_rejected(self):
        fixture=proof_tests.PathProofTests();fixture.R=self.R;w=fixture.world(20,12)
        npc=SimpleNamespace(name='keeper',x=3,y=5)
        w.npcs={1:(npc,'b',0,())}
        portals=[fixture.portal('a',3,5,'b',3,5),fixture.portal('b',3,5,'a',3,5)]
        posts=(('keeper','b',(3,5),(6,5),0.,'side post'),)
        self.assertIsNone(P.WalkAudit(w,portals).arrival_departure('b',(3,5)))
        result=P.validate_posts(w,portals,posts)
        self.assertEqual(len(result[0]['conversation']),4)
        self.assertEqual((npc.x,npc.y),(3,5))  # dry run restored actual input
        w.npcs[2]=(SimpleNamespace(name='other',x=6,y=5),'b',0,())
        with self.assertRaisesRegex(ValueError,'blocked/occupied authored post'):P.validate_posts(w,portals,posts)
        self.assertEqual((npc.x,npc.y),(3,5))

if __name__=='__main__':unittest.main()
