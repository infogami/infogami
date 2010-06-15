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

class DBTest(unittest.TestCase):
    def setUp(self):
        self.tx = db.transaction()
        db.insert("thing", key='/type/object')
        
    def tearDown(self):
        self.tx.rollback()

class TestStore(DBTest):
    def test_insert(self):
        for i in range(10):
            d = {"name": str(i), "value": i}
            store.put("/" + str(i), d)
            
        for i in range(10):
            d = {"name": str(i), "value": i}
            assert store.get("/" + str(i)) == d

    def test_update(self):
        self.test_insert()
        self.test_insert()
                
    def test_query(self):
        store.put("/one", {"type": "digit", "name": "one"})
        store.put("/two", {"type": "digit", "name": "two"})
        
        store.put("/a", {"type": "char", "name": "a"})
        store.put("/b", {"type": "char", "name": "b"})

        # regular query
        assert store.query("digit", "name", "one") == ["/one"]
        
        # query for type
        assert store.query("digit", None, None) == ["/two", "/one"]
        assert store.query("char", None, None) == ["/b", "/a"]
        
        # query for all
        assert store.query(None, None, None) == ["/b", "/a", "/two", "/one"]

    def test_indexer(self):
        s = Store(db)
        s.indexer = BookIndexer()
        
        s.put("/book", {"title": "The lord of the rings", "lang": "en"})
        assert store.query("", "lang", "en") == []
        assert store.query("", "title,lang", "The lord of the rings--en") == ['/book']

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
        
        s.put("/book", {"type": "book", "title": "The lord of the rings", "lang": "en"})
        s.put("/one", {"type": "digit", "name": "one"})
        s.put("/foo", {"name": "foo"})
        
        assert store.query("", "lang", "en") == []
        assert store.query("book", "title,lang", "The lord of the rings--en") == ['/book']
        
        assert store.query("digit", "name", "one") == ["/one"]
        assert store.query("", "name", "foo") == ["/foo"]
        
class BookIndexer:
    def index(self, doc):
        yield "title,lang", doc['title'] + "--" + doc['lang']
        