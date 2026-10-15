"""Prepare the disposable local account used by test-magic-tutorial.bat."""
from pathlib import Path
import argparse
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('server', type=Path)
parser.add_argument('database', type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.server.resolve()))
from eloria.database import Database
from eloria.sky import RING_CAPABILITY
from eloria.items import configure_items

assert RING_CAPABILITY == 'spell_ring_v1', 'This launcher needs the matching ring tutorial server branch.'
configure_items(args.server / 'config/eloria/items.txt')
db = Database(str(args.database))
try:
    if not db.db.execute('SELECT 1 FROM characters WHERE username=?', ('RingStudent',)).fetchone():
        db.create('RingStudent', 'ringpractice')
        character = db.load('RingStudent', 1)
        character.quest_state['last_lantern'] = 99
        db.save(character)
        db.claim_first_login('RingStudent')
finally:
    db.db.close()
