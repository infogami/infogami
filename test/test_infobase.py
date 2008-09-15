import webtest
from infogami.infobase import infobase, dbstore
import web

class InfobaseTestCase(webtest.TestCase):
    """Testcase to test infobase."""
    def get_site(self, name):
        store = dbstore.DBStore(dbstore.Schema())
        _infobase = infobase.Infobase(store, 'test')
        site = _infobase.get(name)
        if site is None:
            site = _infobase.create(name)
        return site
            
    def setUp(self):
        if not hasattr(self, 'site'):
            self.site = self.get_site("test")
            self.create_types(self.site)
        
        # clear env
        web.load()
        web.ctx.ip = '127.0.0.1'
        
        # run every test in a transaction, so that we can rollback later in tearDown
        web.transact()
        
    def tearDown(self):
        web.rollback()
        
    def create_types(self, site):
        def property(type, name, expected_type):
            return {
                'create': 'unless_exists',
                'key': type + '/' + name,
                'type': '/type/property',
                'name': name,
                'expected_type': expected_type
            }
        
        site.write({
            'create': 'unless_exists',
            'key': '/type/page',
            'type': '/type/type',
            'properties': [
                property('/type/page', 'title', '/type/string'),
                property('/type/page', 'body', '/type/text'),
            ]
        })
        
    def test_nothing(self):
        pass
        
    def test_create(self):
        self.site.write({
            'create': 'unless_exists',
            'key': '/foo',
            'type': '/type/page',
            'title': 'foo',
            'body': 'foo bar',
        })
        
        foo = self.site.get('/foo')
        assert foo.revision == 1
        assert foo.title == 'foo'
        assert foo.body == 'foo bar'
    
if __name__ == "__main__":
    webtest.main()
