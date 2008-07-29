import _json as simplejson
import web

try:
    from __builtin__ import any, all
except ImportError:
    def any(seq):
        for x in seq:
            if x:
                return True
                
    def all(seq):
        for x in seq:
            if not x:
                return False
        return True
            

primitive_types = [
    "/type/key",
    "/type/string",
    "/type/text",
    "/type/int",
    "/type/float",
    "/type/boolean",
    "/type/datetime"
]

types = web.storage(
    key="key",
    str="str",
    text="text",
    int="int",
    float="float",
    boolean="boolean",
    datetime="datetime",
    ref="ref"
)

_datatypes = {
    "/type/key": types.key,
    "/type/string": types.str,
    "/type/text": types.text,
    "/type/int": types.int,
    "/type/float": types.float,
    "/type/boolean": types.boolean,
    "/type/datetime": types.datetime
}

_types = dict((v, k) for (k, v) in _datatypes.items())

def type2datatype(type):
    """Returns datatype from type name.
    
        >>> type2datatype('/type/int')
        'int'
        >>> type2datatype('/type/page')
        'ref'
    """
    return _datatypes.get(type, types.ref)
    
def datatype2type(datatype):
    return _types.get(datatype)

class InfobaseContext:
	def __init__(self, sitename, user, ip):
		self.sitename = sitename
		self.user = user
		self.ip = ip
		self.superuser = self.user and (self.user.key == '/user/admin')

class Thing:
    def __init__(self, store, key, metadata=None, data=None):
        self._store = store
        self.key = key
        self._metadata = metadata or web.storage()
        self._data = data or {}
        
    def get_value(self, key):
        if key not in self._data:
            return None
        datatype, value = self._data[key]
        if datatype == 'ref':
            if isinstance(value, list):
                value = [self._store.get(v) for v in value]
            else:
                value = self._store.get(value)
        return value

    def get_datatype(self, key):
        datatype, value = self._data[key]
        return datatype
        
    def get(self, name):
        return self._data[name]
        
    def set(self, name, value, datatype):
        def unthing(x):
            if isinstance(x, Thing): return x.key
            else: return x
            
        if datatype == 'ref':
            if isinstance(value, list):
                value = [unthing(v) for v in value]
            else:
                value = value.key
        self._data[name] = (datatype, value)
        
    def __contains__(self, name):
        return name == 'key' or name in self._metadata or name in self._data
        
    def __getitem__(self, name):
        return self.get_value(key)

    def __getattr__(self, key):
        if key.startswith('__'):
            raise AttributeError, key
        return self.get_value(key)
        
    def __delattr__(self, key):
        del self._data[key]
        
    def to_json(self):
        d = {}
        for k, v in self._data.items():
            datatype, v = v
            if datatype == 'ref':
                v = {'key': v}
            elif datatype not in ['int', 'boolean', 'float', 'str', 'key']:
                v = {'type': datatype2type(datatype), 'value': v}
            d[k] = v
        return simplejson.dumps(d)
        
    @staticmethod
    def from_json(store, key, json):
        d = simplejson.loads(json)
        for k, v in d.items():
            if isinstance(v, bool):
                d[k] = 'boolean', v
            elif isinstance(v, int):
                d[k] = 'int', v
            elif isinstance(v, float):
                d[k] = 'float', v
            elif isinstance(v, dict):
                if 'key' in v:
                    d[k] = 'ref', v['key']
                else:
                    d[k] = type2datatype(v['type']), v['value']
            else:
                d[k] = 'str', v
        return Thing(store, key, data=d)
        
    def get_property(self, name):
        """Makes sense only when this object is a type object."""
        for p in self.properties or []:
            if p.name == name:
                return p

    def __repr__(self):
        return "<thing: %s>" % repr(self.key)
        
def create_test_store():
    """Creates a test implementation with /type/book and /type/author.
    Used is doctests.
    
    >>> store = create_test_store()
    >>> store.get('/type/type')
    <thing: '/type/type'>
    >>> t = store.get('/type/book')
    >>> t
    <thing: '/type/book'>
    >>> t.properties
    [<thing: '/type/book/title'>, <thing: '/type/book/author'>, <thing: '/type/book/pages'>]
    >>> t.properties[1].name
    'author'
    >>> t.properties[1].expected_type
    <thing: '/type/author'>
    """
    store = web.storage()
    
    def add_type(key, *properties):
        t = Thing(store, key)
        store[key] = t
        t.type = store['/type/type']
        t.set('properties', [], 'ref')
                
        for name, expected_type in properties:
            p = Thing(store, key + '/' + name)
            p.type = store['/type/property']
            p.set('name', name, 'str')
            p.set('expected_type', store[expected_type], 'ref')
            t.set('properties', t.properties + [p], 'ref')
            store[p.key] = p
        return t
        
    def add_object(key, type, *values):
        t = Thing(store, key)
        t.type = store[type]
        for name, value, datatype in values:
            if datatype == "ref":
                value = store[value]
            t.set(name, value, datatype)

        store[key] = t
        return t
    
    add_type('/type/type')

    add_type('/type/string')
    add_type('/type/int')

    add_type('/type/property',
        ('name', '/type/string'),
        ('expected_type', '/type/property'),
    )
    
    add_type('/type/author',
        ('name', '/type/string')
    )

    add_type('/type/book',
        ('title', '/type/string'),
        ('author', '/type/author'),
        ('pages', '/type/int')
    )
    
    add_object('/author/test', '/type/author',
        ('name', 'test', 'str')
    )
    
    add_object('/book/test', '/type/book',
        ('title', 'test', 'str'),
        ('author', '/author/test', 'ref'),
        ('pages', 10, 'int')
    )
    
    return store
                        
class WriteQuery:
    """Write query is a list of actions.
        >>> q = WriteQuery('update', "/foo", "/type/page")
    """
    def __init__(self, action, key, type):
        pass
    
class Query:
    """Query is a list of conditions.
    Each condition is a storage object with ("key", "op", "datatype", "value") as keys.
    
        >>> q = Query()
        >>> q
        <query: []>
        >>> q.add_condition("name", "=", "str", "foo")
        >>> q
        <query: ['name = str:foo']>
        >>> q.add_condition('type', '=', 'ref', '/type/page')
        >>> q.get_type()
        '/type/page'
        >>> q
        <query: ['name = str:foo', 'type = ref:/type/page']>
    """
    def __init__(self, conditions=None):
        self.conditions = conditions or []
        self.sort = None
        self.limit = None
        self.offset = None
        
    def get_type(self):
        """Returns the value of the condition for type if there is any.
        """
        for c in self.conditions:
            #@@ also make sure op is =
            if c.key == 'type':
                return c.value
    
    def add_condition(self, key, op, datatype, value):
        self.conditions.append(web.storage(key=key, op=op, datatype=datatype, value=value))
        
    def __repr__(self):
        conditions = ["%s %s %s:%s" % (c.key, c.op, c.datatype, c.value) for c in self.conditions]
        return "<query: %s>" % repr(conditions)

def pprint(obj):
    """Pretty prints given object.
    >>> pprint(1)
    1
    >>> pprint("hello")
    'hello'
    >>> pprint([1, 2, 3])
    [1, 2, 3]
    >>> pprint({'x': 1, 'y': 2})
    {
        'x': 1,
        'y': 2
    }
    >>> pprint([dict(x=1, y=2), dict(c=1, a=2)])
    [{
        'x': 1,
        'y': 2
    }, {
        'a': 2,
        'c': 1
    }]
    >>> pprint({'x': 1, 'y': {'a': 1, 'b': 2}, 'z': 3})
    {
        'x': 1,
        'y': {
            'a': 1,
            'b': 2
        },
        'z': 3
    }
    >>> pprint({})
    {
    }
    """
    print prepr(obj)
    
def prepr(obj, indent=""):
    """Pretty representaion."""
    if isinstance(obj, list):
        return "[" + ", ".join(prepr(x, indent) for x in obj) + "]"
    elif isinstance(obj, tuple):
        return "(" + ", ".join(prepr(x, indent) for x in obj) + ")"
    elif isinstance(obj, dict):
        if hasattr(obj, '__prepr__'):
            return obj.__prepr__()
        else:
            indent = indent + "    "
            items = ["\n" + indent + prepr(k) + ": " + prepr(obj[k], indent) for k in sorted(obj.keys())]
            return '{' + ",".join(items) + "\n" + indent[4:] + "}"
    else:
        return repr(obj)
        
if __name__ == "__main__":
    import doctest
    doctest.testmod()
    