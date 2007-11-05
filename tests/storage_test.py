from infogami.utils.storage import *
from infogami.utils.context import context
import unittest

class SiteLocalDictTest(unittest.TestCase):
    def setUp(self):
        self.d = SiteLocalDict()
        self.load(1)

    def load(self, id):
        web.load()
        context.load()
        context.site = web.storage(id=id)

    def testSingle(self):
        self.d['x'] = 1
        self.d['y'] = 2
        self.assertEquals(self.d, dict(x=1, y=2))
        
        self.d.a = 1
        self.d.b = 2
        self.assertEquals(self.d, dict(a=1, b=2, x=1, y=2))
        
    def testMultiple(self):
        self.load(1)
        self.d.a = 0
        self.d.x = 1
        self.d.y = 2
        self.assertEquals(self.d, dict(a=0, x=1, y=2))
        
        self.load(2)
        self.d.x = 11
        self.d.y = 12
        self.d.z = 13
        self.assertEquals(self.d, dict(x=11, y=12, z=13))

        self.load(1)
        self.assertEquals(self.d, dict(a=0, x=1, y=2))
        
        self.load(2)
        self.assertEquals(self.d, dict(x=11, y=12, z=13))
        
    def testDict(self):
        self.d.x = 1
        self.d.y = 2

        self.assertEquals('x' in self.d, True)
        self.assertEquals('z' in self.d, False)

        self.assertEquals(sorted(self.d), ['x', 'y'])    
        self.assertEquals(sorted(self.d.keys()), ['x', 'y'])
        self.assertEquals(sorted(self.d.values()), [1, 2])
        self.assertEquals(sorted(self.d.items()), [('x', 1), ('y', 2)])
        
        self.assertEquals(sorted(self.d.iterkeys()), ['x', 'y'])
        self.assertEquals(sorted(self.d.itervalues()), [1, 2])
        self.assertEquals(sorted(self.d.iteritems()), [('x', 1), ('y', 2)])
        
        self.assertEquals(self.d.get('x'), 1)
        self.assertEquals(self.d.get('z'), None)
        self.assertEquals(self.d.get('z', 42), 42)

        self.assertEquals(getattr(self.d, 'x'), 1)
        self.assertEquals(getattr(self.d, 'z', 42), 42)
        
        del self.d['x']
        del self.d.y
        
