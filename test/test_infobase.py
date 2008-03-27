import webtest
from infogami.infobase import infobase, client
import web

class InfobaseTestCase(webtest.TestCase):
    """Testcase to test infobase."""
    def get_site(self, name):
        try:
            return infobase.Infobase().get_site(name)
        except:
            site = infobase.Infobase().create_site(name, 'admin123')
            q = dict(
                create='unless_exists', 
                key='/type/page', 
                type='/type/type'
            )
            site.write(q)
            return site
            
    def setUp(self):
        self.site = self.get_site("test")
        # don't let the cache state of one test interfere with another.
        self.clear_cache()

        # reset stats
        for k in infobase.stats:
            infobase.stats[k] = 0
        
        # run every test in a transaction, so that we can rollback later in tearDown
        web.transact()

    def clear_cache(self):
        infobase.thingcache.clear()
        infobase.querycache_things.clear()
        infobase.querycache_versions.clear()
        
    def tearDown(self):
        web.rollback()
        
    def new(self, key, type, **data):
        for k, v in data.items():
            if isinstance(v, int):
                data[k] = dict(type='/type/int', value=v)
            elif isinstance(v, float):
                data[k] = dict(type='/type/float', value=v)
            
        q = dict(create='unless_exists', key=key, type=type, **data)
        self.site.write(q)
        
    def update(self, key, **values):
        q = dict(key=key)

        for k, v in values.items():
            q[k] = dict(connect='update', value=v)
            if isinstance(v, int):
                q[k]['type'] = '/type/int'
            elif isinstance(v, float):
                q[k]['type'] = '/type/float'

        self.site.write(q)

    def things(self, q=None, **query):
        q and query.update(q)
        return self.site.things(query)
        
    def versions(self, **query):
        return self.site.versions(query)
        
class WriteTest(InfobaseTestCase):
    def test_new(self):
        self.new('/foo', '/type/page', title='foo', body='bar', i=1, f=3.14)
        foo = self.site.get('/foo')
        
        self.assertEquals(foo.title.value, 'foo')
        self.assertEquals(foo.body.value, 'bar')
        self.assertEquals(foo.type.key, '/type/page')
        self.assertEquals(foo.i.value, 1)
        self.assertEquals(foo.f.value, 3.14)
        
    def test_update(self):
        self.new('/foo', '/type/page', title='foo', body='bar')
        self.update('/foo', title='foofoo')
        foo = self.site.get('/foo')

        self.assertEquals(foo.title.value, 'foofoo')
        self.assertEquals(foo.body.value, 'bar')
        self.assertEquals(foo.type.key, '/type/page')
        
    def test_update_with_integers(self):
        self.new('/foo', '/type/page', title='foo', body='bar')
        self.update('/foo', title=5)
        
        foo = self.site.get('/foo')
        self.assertEquals(foo.title.value, 5)
        
class InfobaseTest(InfobaseTestCase):        
    def test_get(self):
        t = self.site.get('/type/type')
        assert t.key == '/type/type'

    def testObjectCache(self):
        q = dict(create='unless_exists', key='/foo', type='/type/page', title='foo', body='bar')
        self.site.write(q)
        foo = self.site.get('/foo')
        self.assertEquals(foo.title.value, 'foo')
        
        # make sure cache is invalidated when an object is modifed.
        q = dict(key='/foo', title=dict(connect='update', value='foofoo'))
        self.site.write(q)
        foo = self.site.get('/foo')

        self.assertEquals(foo.title.value, 'foofoo')
        
    def test_things(self):
        self.new('/foo', '/type/page', title='foo', body='foo')
        self.new('/bar', '/type/page', title='bar', body='bar')
        
        self.assertEquals(sorted(self.things(type='/type/page')), ['/bar', '/foo'])
        self.assertEquals(self.things(type='/type/page', sort='key'), ['/bar', '/foo'])
        self.assertEquals(self.things(type='/type/page', sort='-key'), ['/foo', '/bar'])
        
    def test_things_with_numbers(self):        
        def test_range(name, a, b):
            key_a = '/a/' + name
            key_b = '/b/' + name
            
            self.new(key_a, '/type/page', **{name: a})
            self.new(key_b, '/type/page', **{name: b})
            
            self.assertEquals(self.things({'type': '/type/page', name + "<": a, 'sort': 'key'}), [])
            self.assertEquals(self.things({'type': '/type/page', name + "<=": a, 'sort': 'key'}), [key_a])
            self.assertEquals(self.things({'type': '/type/page', name: a, 'sort': 'key'}), [key_a])
            self.assertEquals(self.things({'type': '/type/page', name + ">=": a, 'sort': 'key'}), [key_a, key_b])
            self.assertEquals(self.things({'type': '/type/page', name + ">": a, 'sort': 'key'}), [key_b])

            self.assertEquals(self.things({'type': '/type/page', name + "<": b, 'sort': 'key'}), [key_a])
            self.assertEquals(self.things({'type': '/type/page', name + "<=": b, 'sort': 'key'}), [key_a, key_b])
            self.assertEquals(self.things({'type': '/type/page', name: b, 'sort': 'key'}), [key_b])
            self.assertEquals(self.things({'type': '/type/page', name + ">=": b, 'sort': 'key'}), [key_b])
            self.assertEquals(self.things({'type': '/type/page', name + ">": b, 'sort': 'key'}), [])

        test_range('i', 10, 100)
        test_range('f', 3.1416, 31.416)
        
    def test_things_stats(self):
        s = infobase.stats
        self.new('/foo', '/type/page', title='foo')
        
        # no thing queries are executed.
        self.assertEquals((s.t_hits, s.t_misses), (0, 0))
        
        # first things query, this must be a miss
        self.things(type='/type/page', title='foo')
        self.assertEquals((s.t_hits, s.t_misses), (0, 1))
        
        # same query again; this must be a hit
        self.things(type='/type/page', title='foo')
        assert (s.t_hits, s.t_misses) == (1, 1)
    
    def test_things_cache_with_update(self):
        # make sure things cache is invalidated when an object is modified.
        self.new('/foo', '/type/page', title='foo')
        self.things(type='/type/page', title='foo') # populate cache
                
        self.update('/foo', title='foofoo')        
        self.assertEquals(self.things(type='/type/page', title='foo'), [])

    def test_things_cache_with_new(self):
        # make sure things cache is invalidated when a new object is created.
        self.new('/foo', '/type/page', title='foo')
        self.things(type='/type/page', title='foo') # populate cache
        
        self.new('/foo2', '/type/page', title='foo')
        #@@ need to specify sort order?
        self.assertEquals(self.things(type='/type/page', title='foo', sort='key'), ['/foo', '/foo2'])

class WriteTest(InfobaseTestCase):
    def test_write_with_none(self):
        self.new('/foo', '/type/page', title='foo', a=2)
        foo = self.site.get('/foo')
        self.assertEquals(foo.a.value, 2)
        
        self.update('/foo', a=None)
    
class VersionsTest(InfobaseTestCase):
    def test_versions(self):
        # new object should have only one version
        self.new('/foo', '/type/page', title='foo')        
        versions = self.versions(key='/foo')
        self.assertEquals(len(versions), 1)
        
        # if the object is modified, then a new version should be created.
        self.update('/foo', title='foofoo')
        versions = self.versions(key='/foo')
        self.assertEquals(len(versions), 2)
        
        # if there is no changes, then update should not create any versions
        self.update('/foo', title='foofoo')
        versions = self.versions(key='/foo')
        self.assertEquals(len(versions), 2)
        
    def test_versions_cache_with_new(self):
        import datetime
        timestamp = datetime.datetime.utcnow()

        changes = self.versions(sort='-created')
        
        self.new('/foo', '/type/page', title='foo')
        self.assertEquals(len(self.versions()), len(changes) + 1)
    
        self.new('/bar', '/type/page', title='foo')
        self.assertEquals(len(self.versions()), len(changes) + 2)
    
    def test_versions_stats(self):
        s = infobase.stats
        self.new('/foo', '/type/page', title='foo')
        
        # no thing queries are executed.
        self.assertEquals((s.v_hits, s.v_misses), (0, 0))
        
        changes = self.versions(sort='-created')
        self.assertEquals((s.v_hits, s.v_misses), (0, 1))

        changes = self.versions(sort='-created')
        self.assertEquals((s.v_hits, s.v_misses), (1, 1))

class UnicodeTest(InfobaseTestCase):
    def testUnicode(self):
        u = u'/\u1234'
        self.new(u, '/type/page', title=u)

        t = self.site.withKey(u)
        self.assertEquals(t.key, u)
        self.assertEquals(t.title.value, u)

        self.clear_cache()
        t = self.site.withKey(u)
        self.assertEquals(t.key, u)
        self.assertEquals(t.title.value, u)

class ClientTest(InfobaseTestCase):
    def testWrite(self):
        site = client.Site(client.Client(None, 'test'))
        site.write(dict(create='unless_exists', key='/foo', type='/type/page', title='foo'))
        foo = site.get('/foo')
        self.assertEquals(foo.key, '/foo')
        self.assertEquals(foo.title, 'foo')
        import web

        x = u'/\iu1234'
        u = web.utf8(x)
        
        site.write(dict(create='unless_exists', key=u, type='/type/page', title=u))
        foo = site.get(x)
        self.assertEquals(foo.key, x)
        self.assertEquals(foo.title, x)
                        
if __name__ == "__main__":
    webtest.main()
