from infogami.infobase._dbstore.store import Store, TypewiseIndexer
import utils

import unittest
import simplejson

def setup_module(mod):
    utils.setup_db(mod)
    mod.store = Store(db)
    
def teardown_module(mod):
    utils.teardown_db(mod)
    mod.store = None

class DBTest:
    def setup_method(self, method):
        self.tx = db.transaction()
        db.insert("thing", key='/type/object')
        
    def teardown_method(self, method):
        self.tx.rollback()

class TestStore(DBTest):
    def test_insert(self, wildcard):
        for i in range(10):
            d = {"name": str(i), "value": i}
            store.put(str(i), d)
            
        for i in range(10):
            d = {"name": str(i), "value": i, "_key": str(i), "_rev": wildcard}
            assert store.get(str(i)) == d

    def test_update(self, wildcard):
        store.put("foo", {"name": "foo"})
        assert store.get("foo") == dict(name="foo", _key="foo", _rev=wildcard)

        store.put("foo", {"name": "bar"})
        assert store.get("foo") == dict(name="bar", _key="foo", _rev=wildcard)
        
    def test_notfound(self):
        assert store.get("xxx") is None
        assert store.get_json("xxx") is None
        assert store.get_row("xxx") is None
        
    def test_delete(self, wildcard):
        d = {"name": "foo"}
        store.put("foo", d)        
        assert store.get("foo") == dict(d, _key="foo", _rev=wildcard)
        
        store.delete("foo")
        assert store.get("foo") is None
        
        store.put("foo", {"name": "bar"})    
        assert store.get("foo") == {"name": "bar", "_key": "foo", "_rev": wildcard}
                
    def test_query(self):
        store.put("one", {"type": "digit", "name": "one", "value": 1})
        store.put("two", {"type": "digit", "name": "two", "value": 2})
        
        store.put("a", {"type": "char", "name": "a"})
        store.put("b", {"type": "char", "name": "b"})

        # regular query
        assert store.query("digit", "name", "one") == [{'key': "one"}]
        
        # query for type
        assert store.query("digit", None, None) == [{"key": "two"}, {"key": "one"}]
        assert store.query("char", None, None) == [{"key": "b"}, {"key": "a"}]
        
        # query for all
        assert store.query(None, None, None) == [{"key": "b"}, {"key": "a"}, {"key": "two"}, {"key": "one"}]

    def test_query_include_docs(self, wildcard):
        assert store.query(None, None, None, include_docs=True) == []
        
        store.put("one", {"type": "digit", "name": "one", "value": 1})
        store.put("two", {"type": "digit", "name": "two", "value": 2})
        
        assert store.query("digit", "name", "one", include_docs=True) == [
            {'key': "one", "doc": {"type": "digit", "name": "one", "value": 1, "_key": "one", "_rev": wildcard}}
        ]
        assert store.query(None, None, None, include_docs=True) == [
            {'key': "two", "doc": {"type": "digit", "name": "two", "value": 2, "_key": "two", "_rev": wildcard}},
            {'key': "one", "doc": {"type": "digit", "name": "one", "value": 1, "_key": "one", "_rev": wildcard}},
        ]

    def test_indexer(self):
        s = Store(db)
        s.indexer = BookIndexer()
        
        s.put("book", {"title": "The lord of the rings", "lang": "en"})
        assert store.query("", "lang", "en") == []
        assert store.query("", "title,lang", "The lord of the rings--en") == [{'key': 'book'}]

    def test_typewise_indexer(self):                
        t = TypewiseIndexer()
        t.set_indexer("book", BookIndexer())
        
        def f(doc):
            return sorted(t.index(doc))

        assert f({"type": "book", "title": "foo", "lang": "en", "name": "foo"}) == [("title,lang", "foo--en")]
        assert f({"name": "foo"}) == [("name", "foo")]
                        
    def test_typewise_indexer2(self):
        s = Store(db)
        s.indexer = TypewiseIndexer()
        s.indexer.set_indexer("book", BookIndexer())
        
        s.put("book", {"type": "book", "title": "The lord of the rings", "lang": "en"})
        s.put("one", {"type": "digit", "name": "one"})
        s.put("foo", {"name": "foo"})
        
        assert store.query("", "lang", "en") == []
        assert store.query("book", "title,lang", "The lord of the rings--en") == [{"key": "book"}]
        
        assert store.query("digit", "name", "one") == [{"key": "one"}]
        assert store.query("", "name", "foo") == [{"key": "foo"}]
        
    def test_multiput(self):
        store.put("x", {"name": "foo"})
        store.put("x", {"name": "foo"})
        store.put("x", {"name": "foo"})
                
        assert store.query(None, None, None) == [{"key": "x"}]
        assert store.query("", None, None) == [{"key": "x"}]
        assert store.query("", "name", "foo") == [{"key": "x"}]
        
class BookIndexer:
    def index(self, doc):
        yield "title,lang", doc['title'] + "--" + doc['lang']
        