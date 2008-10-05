import config
from lru import LRU

import _json as simplejson
import web


class InfobaseException(Exception):
    pass
    
class NotFound(InfobaseException):
    pass

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
    "/type/datetime",
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

# properties present for every type of object.
COMMON_PROPERTIES = ['key', 'type', 'created', 'last_modified', 'permission', 'child_permission']

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
    
def record_exception():
    """This function is called whenever there is any exception in Infobase.
    
    Overwrite this function if some action (like logging the exception) needs to be taken on exceptions.
    """
    import traceback
    traceback.print_exc()

class InfobaseContext:
	def __init__(self, sitename, user, ip):
		self.sitename = sitename
		self.user = user
		self.ip = ip
		self.superuser = self.user and (self.user.key == '/user/admin')
		
class Event:
    """Infobase Event.
    
    Events are fired when something important happens (write, new account etc.).
    Some code can listen to the events and do some action (like logging, updating external cache etc.).
    """
    def __init__(self, sitename, name, timestamp, ip, username, data):
        """Creates a new event.
        
        sitename - name of the site where the event is triggered.
        name - name of the event
        timestamp - timestamp of the event
        ip - client's ip address
        username - current user
        data - additional data of the event
        """
        self.sitename = sitename
        self.name = name
        self.timestamp = timestamp
        self.ip = ip
        self.username = username
        self.data = data

class Thing:
    def __init__(self, store, key, metadata=None, data=None):
        self._store = store
        self.key = key
        self._metadata = metadata or web.storage()
        self._data = data or {}
        
    def get_value(self, key, default=None):
        if key not in self._data:
            return default
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
                value = unthing(value)
        self._data[name] = (datatype, value)
        
    def copy(self):
        return Thing(self._store, self.key, self._metadata and self._metadata.copy() or {}, self._data and self._data.copy() or {})
        
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
        
    def __delitem__(self, key):
        del self._data[key]
        
    def to_json(self):
        d = self._get_data()
        return simplejson.dumps(d)
        
    def __json__(self):
        d = self._get_data()
        return simplejson.dumps(d)
        
    def _get_data(self):
        d = {}
        for key, value in self._data.items():
            datatype, value = value
            if datatype == 'ref':
                if isinstance(value, list):
                    value = [{'key': v} for v in value]
                else:
                    value = {'key': value}
            elif datatype not in ['int', 'boolean', 'float', 'str', 'key']:
                type = datatype2type(datatype)
                if isinstance(value, list):
                    value = [{"type": type, "value": v} for v in value]
                else:
                    value = {"type": type, "value": value}
            d[key] = value
        return d
    
    @staticmethod
    def from_json(store, key, json):
        def parse(value):
            if isinstance(value, bool):
                return 'boolean', value
            elif isinstance(value, int):
                return 'int', value
            elif isinstance(value, float):
                return 'float', value
            elif isinstance(value, dict):
                if 'key' in value:
                    return 'ref', value['key']
                else:
                    return type2datatype(value['type']), value['value']
            elif isinstance(value, list):
                value = [parse(v) for v in value]
                if value:
                    return value[0][0], [v[1] for v in value]
                else:
                    return None
            else:
                return 'str', value
                        
        d = simplejson.loads(json)
        data = {}
        for k, v in d.items():
            v = parse(v)
            if v:
                data[k] = v
        return Thing(store, key, data=data)
        
    def get_property(self, name):
        """Makes sense only when this object is a type object."""
        for p in self.properties or []:
            if p.name == name:
                return p

    def __repr__(self):
        return "<thing: %s>" % repr(self.key)
        
class LazyThing:
    def __init__(self, store, key, json):
        self.__dict__['_key'] = key
        self.__dict__['_store'] = store
        self.__dict__['_json'] = json
        self.__dict__['_thing'] = None
        
    def _get(self):
        if self._thing is None:
            self._thing = Thing.from_json(self._store, self._key, self._json)
        return self._thing
        
    def __getattr__(self, key):
        return getattr(self._get(), key)
        
    def __json__(self):
        return self._json
        
    def __repr__(self):
        return "<LazyThing: %s>" % repr(self._key)

class Store:
    """Storage for Infobase.
    
    Store manages one or many SiteStores. 
    """
    def create(self, sitename):
        """Creates a new site with the given name and returns store for it."""
        raise NotImplementedError
        
    def get(self, sitename):
        """Returns store object for the given sitename."""
        raise NotImplementedError
    
    def delete(self, sitename):
        """Deletes the store for the specified sitename."""
        raise NotImplementedError

class SiteStore:
    """Interface for Infobase data storage"""
    def get(self, key, revision=None):
        raise NotImplementedError
        
    def new_key(self, type, kw):
        """Generates a new key to create a object of specified type. 
        The store guarentees that it never returns the same key again.
        Optional keyword arguments can be specified to give more hints 
        to the store in generating the new key.
        """
        import uuid
        return '/' + str(uuid.uuid1())
        
    def get_many(self, keys):
        return [self.get(key) for key in keys]
    
    def write(self, query, timestamp=None, comment=None, machine_comment=None, ip=None, author=None):
        raise NotImplementedError
        
    def things(self, query):
        raise NotImplementedError
        
    def versions(self, query):
        raise NotImplementedError
        
    def get_user_details(self, key):
        """Returns a storage object with user email and encrypted password."""
        raise NotImplementedError
        
    def update_user_details(self, key, email, enc_password):
        """Update user's email and/or encrypted password.
        """
        raise NotImplementedError
            
    def find_user(self, email):
        """Returns the key of the user with the specified email."""
        raise NotImplementedError
        
    def register(self, key, email, encrypted):
        """Registers a new user.
        """
        raise NotImplementedError
        
    def transact(self, f):
        """Executes function f in a transaction."""
        raise NotImplementedError
        
    def initialze(self):
        """Initialzes the store for the first time.
        This is called before doing the bootstrap.
        """
        pass
        
    def set_cache(self, cache):
        pass
        
class Cache:
    """
    Cache for Infobase has peculiar requirement.
    
    Since the writequery is executed in a transaction, the cache state can not be changed until the transcation is complete.
    To allow caching even within a writequery, a separate thread-local cache is used other than the global cache.
    The local cache is added to the global cache only if the transaction is successful.
    
    
    >>> cache = Cache()
    >>> cache['x'] = 1
    >>> cache['x']
    1
    >>> cache.transact()
    >>> cache['x'] = 2
    >>> cache['x']
    2
    >>> cache.rollback()
    >>> cache['x']
    1
    >>> cache.transact()
    >>> cache['y'] = 3
    >>> cache['y']
    3
    >>> cache.commit()
    >>> cache['y']
    3
    """
    def __init__(self, dict_cls=None):
        if dict_cls is None:
            dict_cls = lambda: LRU(config.cache_size)
            
        self._global = dict_cls()
        
        import threading
        self._local = threading.local().__dict__
        self._transaction = threading.local().__dict__
        
    def transact(self):
        self._transaction[1] = 1 # just to make it non-empty
        
    def commit(self):
        self._global.update(self._local)
        self._local.clear()
        self._transaction.clear()
        
    def rollback(self):
        self._local.clear()
        self._transaction.clear()
        
    def keys(self):
        return self._global.keys() + self._local.keys()
        
    def __contains__(self, key):
        if self._transaction:
            return key in self._local or self._global.get(key) is not None
        else:
            return key in self._global
        
    def __getitem__(self, key):
        try:
            return self._local[key]
        except KeyError:
            return self._global[key]
        
    def __setitem__(self, key, value):
        if self._transaction:
            self._local[key] = value
        else:
            self._global[key] = value
            
    def __delitem__(self, key):
        if self._transaction:
            del self._local[key]
        else:
            del self._global[key]
            
class CachedSiteStore:
    def __init__(self, store):
        self.store = store
        self.cache = Cache()
        self.store.set_cache(self.cache)

    def get(self, key, revision=None):
        if revision is not None:
            return self.store.get(key, revision)
        else:
            if key not in self.cache:
                thing = self.store.get(key)
                self.cache[key] = thing
            else:
                thing = self.cache[key]
            return thing
    
    def write(self, query, *a, **kw):
        self.cache.transact()
        try:
            result = self.store.write(self.iterquery(query), *a, **kw)
        except:
            self.cache.rollback()
            raise
        else:
            self.cache.commit()
            for key in result.created + result.updated:
                if key in self.cache:
                    del self.cache[key]
            return result
        
    def iterquery(self, query):
        for action, key, q in query:
            yield action, key, q
            if key in self.cache._local:
                del self.cache[key]
                        
    def __getattr__(self, name):
        return getattr(self.store, name)
        
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
    