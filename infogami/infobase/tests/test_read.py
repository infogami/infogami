from infogami.infobase import dbstore
from infogami.infobase._dbstore.save import SaveImpl
from infogami.infobase._dbstore.read import RecentChanges

import utils

import datetime

def setup_module(mod):
    utils.setup_db(mod)
    
def teardown_module(mod):
    utils.teardown_db(mod)

class DBTest:
    def setup_method(self, method):
        self.tx = db.transaction()
        db.insert("thing", key='/type/object')

    def teardown_method(self, method):
        self.tx.rollback()

class TestRecentChanges(DBTest):
    def test_all(self):
        docs = [
            {"key": "/foo", "type": {"key": "/type/object"}, "title": "foo"},
            {"key": "/bar", "type": {"key": "/type/object"}, "title": "bar"}
        ]
        timestamp = datetime.datetime(2010, 01, 02, 03, 04, 05)
        s = SaveImpl(db)
        s.save(docs, 
            timestamp=timestamp,
            comment="testing recentchanges", 
            ip="1.2.3.4", 
            author=None,
            action="test_save"
        )

        changes = RecentChanges(db).recentchanges(limit=1)
        for c in changes:
            del c['id']
        
        assert changes == [{
            "kind": "test_save",
            "timestamp": timestamp.isoformat(), 
            "comment": "testing recentchanges",
            "ip": "1.2.3.4",
            "author": None,
            "changes": [
                {"key": "/foo", "revision": 1},
                {"key": "/bar", "revision": 1},
            ],
            "data": {}
        }]
    