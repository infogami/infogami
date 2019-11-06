import datetime

from infogami.infobase import dbstore
from infogami.infobase._dbstore.save import SaveImpl
from infogami.infobase._dbstore.store import Store
from infogami.infobase._dbstore.read import RecentChanges
from infogami.infobase.tests import utils
from infogami.infobase.tests.pytest_wildcard import wildcard


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
    def _save(self, docs, author=None, ip="1.2.3.4", comment="testing", kind="test_save", timestamp=None, data=None):
        timestamp = timestamp=timestamp or datetime.datetime(2010, 1, 2, 3, 4, 5)
        s = SaveImpl(db)
        s.save(docs,
            timestamp=timestamp,
            comment=comment,
            ip=ip,
            author=author,
            action=kind,
            data=data
        )

    def recentchanges(self, **kw):
        return RecentChanges(db).recentchanges(**kw)

    def doc(self, key, **kw):
        doc = {
            "key": key,
            "type": {"key": "/type/object"}
        }
        doc.update(kw)
        return doc

    def save_doc(self, key, **kw):
        docs = [self.doc(key)]
        return self._save(docs, **kw)

    def test_all(self, wildcard):
        docs = [
            {"key": "/foo", "type": {"key": "/type/object"}, "title": "foo"},
            {"key": "/bar", "type": {"key": "/type/object"}, "title": "bar"}
        ]
        timestamp = datetime.datetime(2010, 1, 2, 3, 4, 5)
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
            "changes": [
                {"key": "/foo", "revision": 1},
                {"key": "/bar", "revision": 1},
            ],
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

        self.save_doc('/zero')
        self.save_doc("/one", author="/user/one")
        self.save_doc("/two", author="/user/two")

        assert len(self.recentchanges(author="/user/one")) == 1
        assert len(self.recentchanges(author="/user/two")) == 1

    def test_ip(self):
        db.insert("thing", key='/user/foo')

        self.save_doc("/zero")
        self.save_doc("/one", ip="1.1.1.1")
        self.save_doc("/two", ip="2.2.2.2")

        assert len(self.recentchanges(ip="1.1.1.1")) == 1
        assert len(self.recentchanges(ip="2.2.2.2")) == 1

        self.save_doc("/three", author="/user/foo", ip="1.1.1.1")

        # srecentchanges by logged in users should be ignored in ip queries
        assert len(self.recentchanges(ip="1.1.1.1")) == 1

        # query with bad ip should not fail.
        assert len(self.recentchanges(ip="bad.ip")) == 0
        assert len(self.recentchanges(ip="1.1.1.345")) == 0
        assert len(self.recentchanges(ip="1.1.1.-1")) == 0
        assert len(self.recentchanges(ip="1.2.3.4.5")) == 0
        assert len(self.recentchanges(ip="1.2.3")) == 0

    def new_account(self, username, **kw):
        # backdoor to create new account

        db.insert("thing", key='/user/' + username)

        store = Store(db)
        store.put("account/" + username, dict(kw,
            type="account",
            status="active"
        ))

    def test_bot(self):
        self.new_account("one", bot=False)
        self.new_account("two", bot=True)

        self.save_doc("/zero")
        self.save_doc("/one", author="/user/one")
        self.save_doc("/two", author="/user/two")

        assert len(self.recentchanges(bot=True)) == 1
        assert len(self.recentchanges(bot=False)) == 2
        assert len(self.recentchanges(bot=None)) == 3

    def test_key(self):
        assert self.recentchanges(key='/foo') == []

        self.save_doc("/foo")
        self.save_doc("/bar")

        assert len(self.recentchanges(key='/foo')) == 1

    def test_data(self):
        self.save_doc("/zero", data={"foo": "bar"})
        assert self.recentchanges(limit=1)[0]['data'] == {"foo": "bar"}

    def test_query_by_data(self):
        self.save_doc("/one", data={"x": "one"})
        self.save_doc("/two", data={"x": "two"})

        assert self.recentchanges(limit=1, data={"x": "one"})[0]['changes'] == [{"key": "/one", "revision": 1}]
        assert self.recentchanges(limit=1, data={"x": "two"})[0]['changes'] == [{"key": "/two", "revision": 1}]

    def test_kind(self):
        self.save_doc("/zero", kind="foo")
        self.save_doc("/one", kind="bar")

        assert len(self.recentchanges(kind=None)) == 2
        assert len(self.recentchanges(kind="foo")) == 1
        assert len(self.recentchanges(kind="bar")) == 1

    def test_query_by_date(self):
        def doc(key):
            return {"key": key, "type": {"key": "/type/object"}}

        def date(datestr):
            y, m, d = datestr.split("-")
            return datetime.datetime(int(y), int(m), int(d))

        self.save_doc("/a", kind="foo", timestamp=date("2010-01-02"), comment="a")
        self.save_doc("/b", kind="bar", timestamp=date("2010-01-03"), comment="b")

        def changes(**kw):
            global db
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
