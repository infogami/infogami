import simplejson

from infogami.infobase import client, server
from infogami.infobase.tests import utils


def setup_module(mod):
    utils.setup_conn(mod)
    utils.setup_server(mod)

    mod.site = client.Site(mod.conn, "test")
    mod.s = mod.site.store
    mod.seq = mod.site.seq


def teardown_module(mod):
    utils.teardown_server(mod)
    utils.teardown_conn(mod)


class TestRecentChanges:
    def save_doc(self, key, **kw):
        doc = {"key": key, "type": {"key": "/type/object"}}
        return site.save(doc, **kw)

    def recentchanges(self, **query):
        return [c.dict() for c in site.recentchanges(query)]

    def test_all(self, wildcard):
        self.save_doc("/foo", comment="test recentchanges")

        changes = self.recentchanges(limit=1)
        assert changes == [{
            "id": wildcard,
            "kind": "update",
            "author": None,
            "ip": wildcard,
            "timestamp": wildcard,
            "changes": [{"key": "/foo", "revision": 1}],
            "comment": "test recentchanges",
            "data": {}
        }]

        assert site.get_change(changes[0]["id"]).dict() == {
            "id": wildcard,
            "kind": "update",
            "author": None,
            "ip": wildcard,
            "timestamp": wildcard,
            "comment": "test recentchanges",
            "changes": [{"key": "/foo", "revision": 1}],
            "data": {}
        }

    def test_key(self, wildcard):
        self.save_doc("/foo")
        self.save_doc("/bar")

        changes = self.recentchanges(key="/foo")
        assert len(changes) == 1

    def test_query_by_data(self):
        self.save_doc("/one", data={"x": "one"}, comment="one")
        self.save_doc("/two", data={"x": "two"}, comment="two")

        changes = self.recentchanges(data={"x": "one"})
        assert [c['data'] for c in changes] == [{"x": "one"}]

        changes = self.recentchanges(data={"x": "two"})
        assert [c['data'] for c in changes] == [{"x": "two"}]

class TestStore:
    global site
    global s  # site.store

    def setup_method(self, method):
        s.clear()

    def test_getitem(self, wildcard):
        try:
            s["x"]
        except KeyError:
            pass
        else:
            assert False, "should raise KeyError"

        s["x"] = {"name": "x"}
        assert s["x"] == {"name": "x", "_key": "x", "_rev": wildcard}

        s["x"] = {"name": "xx", "_rev": None}
        assert s["x"] == {"name": "xx", "_key": "x", "_rev": wildcard}

    def test_contains(self):
        assert "x" not in s

        s["x"] = {"name": "x"}
        assert "x" in s

        del s["x"]
        assert "x" not in s

    def test_keys(self):
        assert s.keys() == []

        s["x"] = {"name": "x"}
        assert s.keys() == ["x"]

        s["y"] = {"name": "y"}
        assert s.keys() == ["y", "x"]

        del s["x"]
        assert s.keys() == ["y"]

    def test_keys_unlimited(self):
        for i in range(200):
            s[str(i)] = {"value": i}

        def srange(*args):
            return [str(i) for i in range(*args)]

        assert s.keys() == srange(100, 200)[::-1]
        assert list(s.keys(limit=-1)) == srange(200)[::-1]

    def test_key_value_items(self, wildcard):
        s["x"] = {"type": "foo", "name": "x"}
        s["y"] = {"type": "bar", "name": "y"}
        s["z"] = {"type": "bar", "name": "z"}

        assert s.keys() == ["z", "y", "x"]
        assert s.keys(type='bar') == ["z", "y"]
        assert s.keys(type='bar', name="name", value="y") == ["y"]

        assert s.values() == [
            {"type": "bar", "name": "z", "_key": "z", "_rev": wildcard},
            {"type": "bar", "name": "y", "_key": "y", "_rev": wildcard},
            {"type": "foo", "name": "x", "_key": "x", "_rev": wildcard}
        ]
        assert s.values(type='bar') == [
            {"type": "bar", "name": "z", "_key": "z", "_rev": wildcard},
            {"type": "bar", "name": "y", "_key": "y", "_rev": wildcard}
        ]
        assert s.values(type='bar', name="name", value="y") == [
            {"type": "bar", "name": "y", "_key": "y", "_rev": wildcard}
        ]

        assert s.items() == [
            ("z", {"type": "bar", "name": "z", "_key": "z", "_rev": wildcard}),
            ("y", {"type": "bar", "name": "y", "_key": "y", "_rev": wildcard}),
            ("x", {"type": "foo", "name": "x", "_key": "x", "_rev": wildcard})
        ]
        assert s.items(type='bar') == [
            ("z", {"type": "bar", "name": "z", "_key": "z", "_rev": wildcard}),
            ("y", {"type": "bar", "name": "y", "_key": "y", "_rev": wildcard}),
        ]
        assert s.items(type='bar', name="name", value="y") == [
            ("y", {"type": "bar", "name": "y", "_key": "y", "_rev": wildcard}),
        ]

    def test_update(self):
        docs = {
            "x": {"type": "foo", "name": "x"},
            "y": {"type": "bar", "name": "y"},
            "z": {"type": "bar", "name": "z"},
        }
        s.update(docs)
        assert sorted(s.keys()) == (["x", "y", "z"])

class TestSeq:
    def test_seq(self):
        global seq
        seq.get_value("foo") == 0
        seq.get_value("bar") == 0

        for i in range(10):
            seq.next_value("foo") == i+1

class TestSanity:
    """Simple tests to make sure that queries are working fine via all these layers."""
    def test_reindex(self):
        keys = ['/type/page']
        site._request("/reindex", method="POST", data={"keys": simplejson.dumps(keys)})

class TestAccount:
    """Test account creation, forgot password etc."""
    def test_register(self):
        global site
        email = "joe@example.com"
        response = site.register(username="joe", displayname="Joe", email=email, password="secret")

        assert site.activate_account(username="joe") == {'ok': 'true'}

        # login should succed
        site.login("joe", "secret")

        try:
            site.login("joe", "secret2")
        except client.ClientException:
            pass
        else:
            assert False, "Login should fail when used with wrong password"
