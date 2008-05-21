import webtest
from infogami.infobase import infobase, client
import web

class InfobaseTestCase(webtest.TestCase):
    """Testcase to test infobase."""
    def get_site(self, name):
        try:
            return infobase.Infobase().get_site(name)
        except:
            import traceback
            traceback.print_exc()
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
                
        # clear env
        web.load()
        web.ctx.ip = '127.0.0.1'
        
        # run every test in a transaction, so that we can rollback later in tearDown
        web.transact()
        
    def clear_cache(self):
        self.site.cache_store.clear()

    def create_book_author_types(self):
        def property(type, name, expected_type):
            return dict(
                create='unless_exists', 
                type='/type/property', 
                key=type + '/' + name, 
                name=name, 
                expected_type=expected_type, 
                unique=True)

        def backreference(type, name, expected_type, property_name):
            return dict(
                create='unless_exists', 
                type='/type/backreference', 
                key=type + '/' + name, 
                name=name, 
                expected_type=expected_type, 
                property_name=property_name)
            
        q = {
            'create': 'unless_exists',
            'key': '/type/book',
            'type': '/type/type',
            'properties': [
                property('/type/book', 'title', '/type/string'),
                property('/type/book', 'authors', {
                    'create': 'unless_exists',
                    'key': '/type/author',
                    'type': '/type/type',
                    'properties': [
                        property('/type/author', 'name', '/type/string'),
                    ],
                })
            ]         
        }
        
        self.site.write(q)

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
            if isinstance(v, list):
                q[k] = dict(connect='update_list', value=v)
            else:
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
        
    def assertRevision(self, key, revision):
        self.assertEquals(self.site.get(key).revision, revision)
        
    def assertValue(self, key, property_name, value):
        thing = self.site.get(key)
        value2 = thing._get(property_name, None)
        self.assertEquals(value2, value)
        
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

    def test_write_with_none(self):
        self.new('/foo', '/type/page', title='foo', a=2)
        foo = self.site.get('/foo')
        self.assertEquals(foo.a.value, 2)

        self.update('/foo', title=None)
        self.assertEquals(foo.revision, 2)
        
        self.update('/foo', title=None)
        self.assertEquals(foo.revision, 2)
        
    def test_update_with_nochange(self):
        self.new('/foo', '/type/page', title='foo', a=["x", "y"])
        self.update('/foo', title='foo')
        self.assertRevision('/foo', 1)

        self.update('/foo', title=None)
        self.assertValue('/foo', 'title', None)
        self.assertRevision('/foo', 2)

        self.update('/foo', title=None)
        self.assertValue('/foo', 'title', None)
        self.assertRevision('/foo', 2)
                
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
        
    def disable_test_things_stats(self):
        s = infobase.stats
        self.new('/foo', '/type/page', title='foo')
        
        # no thing queries are executed.
        self.assertEquals((s.t_hits, s.t_misses), (0, 0))
        
        # first things query, this must be a miss
        self.things(type='/type/page', title='foo')
        #self.assertEquals((s.t_hits, s.t_misses), (0, 1))
        
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
        
    def test_things_without_type(self):
        self.new('/foo', '/type/page', title='foo', a='foo')
        # things is failing when sort is spefified and type is not specified
        self.site.things({'a~': 'f*', 'sort': 'a'})
    
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
        changes = self.versions(sort='-created')
        
        self.new('/foo', '/type/page', title='foo')
        self.assertEquals(len(self.versions()), len(changes) + 1)
    
        self.new('/bar', '/type/page', title='foo')
        self.assertEquals(len(self.versions()), len(changes) + 2)
    
    def disable_test_versions_stats(self):
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

class AccountTest(InfobaseTestCase):
    def testAccount(self):
        site = client.Site(client.Client(None, 'test'))
        site.register('test', 'Test', 'test@example.com', 'test123')
        site.login('test', 'test123')        
        self.save_cookie()
        site.update_user('test123', 'test321', 'test@test.com')
        site.login('test', 'test321')
        
    def save_cookie(self):
        cookie = web.ctx.headers[0][1].split(';')[0]        
        web.ctx.env = web.storage(HTTP_COOKIE=cookie) 
        
class CacheTest(InfobaseTestCase):
    def testThingCache(self):
        self.new('/foo', '/type/page', title='foo', body='bar')

        # foo must be available in cache, once we request it
        foo = self.site.withKey('/foo')
        assert (foo.id, None) in self.site.thing_cache

        # foo must be removed from cache after updated it
        self.update('/foo', title='foo2')
        assert (foo.id, None) not in self.site.thing_cache
        
        foo2 = self.site.withKey('/foo')
        self.assertEquals(foo2.title.value, 'foo2')
        self.assertEquals(foo2.revision, 2)
        
    def test_update_with_none(self):
        # create an object with a permission
        self.site.write(dict(create='unless_exists', key='/foo', type='/type/page', permission='/permission/open'))
        # query for all objects controlled by that permission (to poplulate cache)
        things = self.things(permission='/permission/open')
        # try to update permission to None
        self.site.write(dict(key='/foo', permission=dict(connect='update', key=None)))
        
    def test_withKey_revision(self):
        self.new('/foo', '/type/page', title='foo', body='foo')
        self.update('/foo', body='bar')
        foo = self.site.withKey('/foo', revision=1)
        foo2 = self.site.withKey('/foo')
        self.assertEquals(foo2.body.value, 'bar')
        
    def test_cache_bug(self):
        # create 2 objects
        self.new('/foo', '/type/page', title='foo')
        self.new('/foo2', '/type/page', title='foo')
        
        # run  a query which selects these 2 and puts the result in the cache
        self.things(type='/type/page', title='foo')
        
        # update those 2 objects to make it not match the query
        def q(key):
            return dict(key=key, title=dict(connect='update', value='bar'))    
        self.site.write([q('/foo'), q('/foo2')])
    
class BulkUploadTest(InfobaseTest):
    def disable_test_bulkupload(self):
        self.create_book_author_types()
        from infogami.infobase import bulkupload
        bulk = bulkupload.BulkUpload(self.site)

        def f(name):
            return {
                'create': 'unless_exists',
                'key': '/b/' + name,
                'author': {'create': 'unless_exists', 'key': '/a/foo'}
            }

        q = [f('b1'), f('b2')]
        bulk.upload(q)
        self.site.get('/a/foo')
    
    

if __name__ == "__main__":
    webtest.main()
