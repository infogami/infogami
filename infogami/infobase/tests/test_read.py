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
    def _save(self, docs, author=None, comment="testing", kind="test_save", timestamp=None, data=None):
        timestamp = timestamp=timestamp or datetime.datetime(2010, 01, 02, 03, 04, 05)
        s = SaveImpl(db)
        s.save(docs, 
            timestamp=timestamp,
            comment=comment, 
            ip="1.2.3.4", 
            author=author,
            action=kind,
            data=data
        )
        
    def test_all(self, wildcard):
        docs = [
            {"key": "/foo", "type": {"key": "/type/object"}, "title": "foo"},
            {"key": "/bar", "type": {"key": "/type/object"}, "title": "bar"}
        ]
        timestamp = datetime.datetime(2010, 01, 02, 03, 04, 05)
        self._save(docs, comment="testing recentchanges", timestamp=timestamp)

        engine = RecentChanges(db)
        changes = engine.recentchanges(limit=1)
        
        assert changes == [{
            "id": wildcard,
            "kind": "test_save",
            "timestamp": timestamp.isoformat(), 
            "comment": "testing recentchanges",
            "ip": "1.2.3.4",
            "author": None,
            "data": {}
        }]
        
        engine.get_change(changes[0]['id']) == {
            "id": wildcard,
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
        }     
        
    def test_author(self):
        db.insert("thing", key='/user/one')
        db.insert("thing", key='/user/two')
        
        def doc(key):
            return {"key": key, "type": {"key": "/type/object"}}
        
        self._save([doc("/zero")])
        self._save([doc("/one")], author="/user/one")
        self._save([doc("/two")], author="/user/two")
        
        def changes(author):
            return RecentChanges(db).recentchanges(author=author)
        
        assert len(changes("/user/one")) == 1
        assert len(changes("/user/two")) == 1
        
    def test_bot(self):
        one_id = db.insert("thing", key='/user/one')
        two_id = db.insert("thing", key='/user/two')
        db.insert("account", thing_id=one_id, bot=True, seqname=False)

        def doc(key):
            return {"key": key, "type": {"key": "/type/object"}}
        
        self._save([doc("/zero")])
        self._save([doc("/one")], author="/user/one")
        self._save([doc("/two")], author="/user/two")

        def changes(bot):
            return RecentChanges(db).recentchanges(bot=bot)
        
        assert len(changes(bot=True)) == 1
        assert len(changes(bot=False)) == 2
        assert len(changes(bot=None)) == 3
        
    def test_data(self):
        def doc(key):
            return {"key": key, "type": {"key": "/type/object"}}
            
        self._save([doc("/zero")], data={"foo": "bar"})
        
        def recentchange():
            return RecentChanges(db).recentchanges(limit=1)[0]
            
        assert recentchange()['data'] == {"foo": "bar"}
        
    def test_kind(self):
        def doc(key):
            return {"key": key, "type": {"key": "/type/object"}}
        
        self._save([doc("/zero")], kind="foo")
        self._save([doc("/one")], kind="bar")

        def changes(kind):
            return RecentChanges(db).recentchanges(kind=kind)
            
        assert len(changes(None)) == 2
        assert len(changes("foo")) == 1
        assert len(changes("bar")) == 1
        
    def test_query_by_date(self):
        def doc(key):
            return {"key": key, "type": {"key": "/type/object"}}
            
        def date(datestr):
            y, m, d = datestr.split("-")
            return datetime.datetime(int(y), int(m), int(d))
        
        self._save([doc("/a")], kind="foo", timestamp=date("2010-01-02"), comment="a")
        self._save([doc("/b")], kind="bar", timestamp=date("2010-01-03"), comment="b")
        
        def changes(**kw):
            return [c['comment'] for c in RecentChanges(db).recentchanges(**kw)]

        # begin_date is included in the interval, but end_date is not included.
        assert changes(begin_date=date("2010-01-01")) == ['b', 'a']
        assert changes(begin_date=date("2010-01-02")) == ['b', 'a']
        assert changes(begin_date=date("2010-01-03")) == ['b']
        assert changes(begin_date=date("2010-01-04")) == []

        assert changes(end_date=date("2010-01-01")) == []
        assert changes(end_date=date("2010-01-02")) == []
        assert changes(end_date=date("2010-01-03")) == ['a']
        assert changes(end_date=date("2010-01-04")) == ['b', 'a']
        
        assert changes(begin_date=date("2010-01-01"), end_date=date("2010-01-03")) == ['a']
        assert changes(begin_date=date("2010-01-01"), end_date=date("2010-01-04")) == ['b', 'a']
