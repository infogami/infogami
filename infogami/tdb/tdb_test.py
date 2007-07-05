import random
import web
import tdb as tdb2
import unittest

tdb = tdb2.SimpleTDBImpl()

# root, default type, default parent and default thing
root = None
type = None
parent = None
thing = None

testtype = None

def simplething(name):
    t = tdb.new(name, testtype, testtype, {'title' : name})
    t.save('saving ' + name);
    return t
    
def setup(impl):
    global tdb
    tdb = impl
    
    web.config.db_parameters = dict(dbn='postgres', db='tdbtest', user='postgres', pw='')
    web.db._hasPooling = False
    web.config.db_printing = False
    web.load()
    tdb.setup()
    
    # clear the database
    web.query('delete from datum where version_id > 1')
    web.query('delete from version where thing_id > 1')
    web.query('delete from thing where id > 1')
    
    global testtype, usertype
    
    testtype = tdb.new('test', tdb.root, tdb.root, dict(a=42))
    testtype.save()

    usertype = tdb.new('user', tdb.root, tdb.root)
    usertype.save()
    
    global root, type, parent, thing
    
    root = tdb.root
    type = testtype
    parent = new('parent', root, d=dict(title='default parent'))
    parent.save()
    thing = new('test1', d=dict(title='test1'))
    thing.save()

def new(name, _parent=None, _type=None, d=None):
    if d is None: d = {}    
    return tdb.new(name, _parent or parent, _type or type, d)
        
class SimpleTDBImplTest(unittest.TestCase):
    initialized = False
    impl = tdb2.SimpleTDBImpl()
    count = 0
    
    def setUp(self):
        if not self.initialized:
            self.initialized = True
            setup(self.impl)

    def uniqueName(self):
        self.count += 1
        return 'thing.%d' % self.count
    
    def new(self, name=None, _parent=None, _type=None, d=None):
        name = name or self.uniqueName()
        _parent = _parent or parent
        _type = _type or type
        d = d or dict(title='title-' + name)
        t = tdb.new(name, _parent, _type, d=d)
        t.save()
        return t

    def testThing(self):
        self.assertEquals(thing, thing)
        self.assertEquals(thing._dirty, False)
        
        t = self.new('newthing')
        self.assertEquals(t.name, 'newthing')
        self.assertEquals(t.latest_revision, 1)
        
    def testCopy(self):
        t = thing.copy()
        self.assertEquals(t, thing)
        t.title = 'new title'
        self.assertEquals(t._dirty, True)
        self.assertEquals(thing._dirty, False)
        
    def testNew(self):
        name = self.uniqueName()
        d = dict(i=1, s="hello", l=range(10), ss=["foo"]*10)
        t = tdb.new(name, parent, type, d=d)
        self.assertEquals(t.name, name)
        self.assertEquals(t.parent, parent)
        self.assertEquals(t.type, type)
        self.assertEquals(dict(t.d), d)
        self.assertEquals(t._dirty, True)
        
        t.save()
        self.assertEquals(t.name, name)
        self.assertEquals(t.parent, parent)
        self.assertEquals(t.type, type)
        self.assertEquals(dict(t.d), d)
        self.assertEquals(t._dirty, False)
        assert t.v is not None
        assert t.v.created is not None
        
        self.assertEquals(t.latest_revision, 1)
        t.x = 1
        t.save()
        self.assertEquals(t.latest_revision, 2)
        self.assertEquals(t.x, 1)

    def testWithID(self):
        self.assertEquals(thing, tdb.withID(thing.id))
        self.assertEquals(thing, tdb.withID(thing.id, lazy=True))
        self.assertEquals(thing, tdb.withID(thing.id, revision=thing.latest_revision))
        self.assertEquals(thing, tdb.withID(thing.id, revision=thing.latest_revision, lazy=True))

    def testWithName(self):
        self.assertEquals(thing, tdb.withName(thing.name, thing.parent))
        self.assertEquals(thing, tdb.withName(thing.name, thing.parent, lazy=True))
        self.assertEquals(thing, tdb.withName(thing.name, thing.parent, revision=thing.latest_revision))
        self.assertEquals(thing, tdb.withName(thing.name, thing.parent, revision=thing.latest_revision, lazy=True))
        
    def testRevisions(self):
        t = self.new()
        self.assertEquals(t, tdb.withID(t.id))
        
        t2 = t.copy()
        t2.x = 1
        t2.save()

        self.assertEquals(t2, tdb.withID(t.id))
        self.assertEquals(t, tdb.withID(t.id, revision=1))
        self.assertEquals(t, tdb.withID(t.id, revision=1, lazy=True))
        self.assertEquals(t, tdb.withName(t.name, t.parent, revision=1))
        self.assertEquals(t, tdb.withName(t.name, t.parent, revision=1, lazy=True))
        
    def testHistory(self):
        def test_revision(h, n):
            for i in range(n):
                assert h[i].revision == n-i
                
        t = self.new()
        test_revision(t.h, 1)
        test_revision(tdb.withID(t.id).h, 1)

        t.title = 'v2'
        t.save()
        test_revision(t.h, 2)
        test_revision(tdb.withID(t.id).h, 2)

        t.title = 'v3'
        t.save()
        test_revision(t.h, 3)
        test_revision(tdb.withID(t.id).h, 3)
        
        assert t.h == tdb.withID(t.id).h

    def testWithIDs(self):
        things = [self.new() for i in range(10)]
        ids = [t.id for t in things]
        assert tdb.withIDs(ids) == things

    def testWithNames(self):
        things = [self.new() for i in range(10)]
        names = [t.name for t in things]
        assert tdb.withNames(names, parent) == things

    def assertException(self, exc, f, *a, **kw):
        try:
            f(*a, **kw)
        except exc:
            pass
        else:
            raise Exception, "%s should be raised" % (exc)

    def testExceptions(self):
        # NotFound is raised when thing is not found
        self.assertException(tdb2.NotFound, tdb.withID, thing.id+10000)
        self.assertException(tdb2.NotFound, tdb.withName, 'nothing', parent)

        # AttributeError is raised when attr is not available
        self.assertException(AttributeError, getattr, thing, 'nothing')

        # database exception is raised when you try to create a thing with duplicate name
        self.assertException(Exception, new(thing.name).save)

    def testThings(self):
        x = self.new('x', d=dict(title='testThings'))
        tl = tdb.Things(title='testThings').list()
        assert tl == [x]

        y = self.new('y', d=dict(title='testThings', body='a'))
        z = self.new('z', d=dict(title='testThings', body='a'))
        
        tl = tdb.Things(title='testThings').list()   
        assert tl == [x, y, z]

        tl = tdb.Things(title='testThings', body='a').list()
        assert tl == [y, z]

        tl = tdb.Things(title='notitle').list()
        assert tl == []        
                
class BetterTDBImplTest(SimpleTDBImplTest):
    impl = tdb2.BetterTDBImpl()

class CachedSimpleTDBImplTest(SimpleTDBImplTest):
    impl = tdb2.CachedTDBImpl(tdb2.SimpleTDBImpl())

class CachedBetterTDBImplTest(SimpleTDBImplTest):
    impl = tdb2.CachedTDBImpl(tdb2.BetterTDBImpl())

#del SimpleTDBImplTest
#del BetterTDBImplTest
#del CachedSimpleTDBImplTest
#del CachedBetterTDBImplTest

class ThingCacheTest(unittest.TestCase):
    def testInsert(self):
        c = tdb2.ThingCache()
        c[thing.id] = thing
        self.assertEquals(c[thing.name, thing.parent.id], thing)

class SaveTest(unittest.TestCase):
    def testSave(self):
        impl = tdb2.CachedTDBImpl(tdb2.SimpleTDBImpl())
        setup(impl)
        impl.querycache.clear()

        def test_revision(h, n):
            assert len(h) == n
            for i in range(n):
                assert h[i].revision == n-i
                
        t = new('hello')
        t.save()
        test_revision(t.h, 1)
        
        t.title = 'v2'
        t.save()
        test_revision(t.h, 2)

        t.title = 'v3'
        t.save()
        test_revision(t.h, 3)
        
if __name__ == "__main__":
    unittest.main()
