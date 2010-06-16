import unittest

from infogami.infobase import client, server

import utils

def setup_module(mod):
    utils.setup_conn(mod)
    
    server._infobase = None # clear earlier reference, if any.
    server.get_site("test") # initialize server._infobase
    server._infobase.create("test") # create a new site
    
    mod.site = client.Site(mod.conn, "test")
    mod.s = mod.site.store
    
def teardown_module(mod):
    utils.teardown_conn(mod)
    
class StoreTest(unittest.TestCase):
    def setUp(self):
        s.clear()
        
    def test_getitem(self):
        try:
            s["x"]
        except KeyError:
            pass
        else:
            assert False, "should raise KeyError"
        
        s["x"] = {"name": "x"}
        assert s["x"] == {"name": "x"}
        
        s["x"] = {"name": "xx"}
        assert s["x"] == {"name": "xx"}
        
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
        for i in range(1000):
            s[str(i)] = {"value": i}
            
        def srange(*args):
            return [str(i) for i in range(*args)]
            
        assert s.keys() == srange(900, 1000)[::-1]
        assert list(s.keys(limit=-1)) == srange(1000)[::-1]
        
    def test_bad_data(self):
        s["x"] = 1
        assert s["x"] == 1
        assert "x" in s

        