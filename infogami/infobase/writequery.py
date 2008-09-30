"""
"""
import common
from common import types, pprint, datatype2type, type2datatype, any, all
import web

def make_query(store, author, query):
    r"""Compiles query into subqueries.    
    """
    for q in serialize(query):
        action, key, q = compile(store, q)
        if action == 'update':
            q = optimize(store, key, q)
            if not q:
                continue
        elif action == 'create':
            # strip None values
            for k, v in q.items():
                if v.value == None:
                    del q[k]
            
        if action != 'ignore':
            if not has_permission(store, author, key):
                raise Exception('Permission denied to modify %s' % repr(key))
            yield action, key, q
            
def has_permission(store, author, key):
    # admin user can modify everything
    if author and author.key == '/user/admin':
        return True
    
    permission = get_permission(store, key)
    if permission is None:
        return True
    else:
        groups = permission.get_value('writers') or []
        for group in groups:
            if group.key == '/usergroup/everyone':
                return True
            elif author is not None:
                if group.key == '/usergroup/allusers' or author in group.get_value('members', []):
                    return True
            else:
                return False        
        
def get_permission(store, key):
    """Returns permission for the specified key."""
    def parent(key):
        if key == "/":
            return None
        else:
            return key.rsplit('/', 1)[0] or "/"

    def _get_permission(key, child_permission=False):
        if key is None:
            return None
        thing = store.get(key)
        if child_permission:
            permission = thing and (thing.get_value("child_permission") or thing.get_value("permission"))
        else:
            permission = thing and thing.get_value("permission")
        return permission or _get_permission(parent(key), child_permission=True)

    return _get_permission(key)

    
    
def serialize(query):
    r"""Serializes a nested query such that each subquery acts on a single object.

        >>> q = {
        ...     'create': 'unless_exists',
        ...     'key': '/foo',
        ...     'type': '/type/book',
        ...     'author': {
        ...        'create': 'unless_exists',
        ...        'key': '/bar',
        ...     },
        ...     'descption': {'value': 'foo', 'type': '/type/text'}
        ... }
        >>> serialize(q)
        [{
            'create': 'unless_exists',
            'key': '/bar'
        }, {
            'author': {
                'key': '/bar'
            },
            'create': 'unless_exists',
            'descption': {
                'type': '/type/text',
                'value': 'foo'
            },
            'key': '/foo',
            'type': '/type/book'
        }]
        >>> q = {
        ...     'create': 'unless_exists',
        ...     'key': '/foo',
        ...     'authors': {
        ...         'connect': 'update_list',
        ...         'value': [{
        ...             'create': 'unless_exists',
        ...             'key': '/a/1'
        ...         }, {
        ...             'create': 'unless_exists',
        ...             'key': 'a/2'
        ...         }]
        ...     }
        ... }
        >>> serialize(q)
        [{
            'create': 'unless_exists',
            'key': '/a/1'
        }, {
            'create': 'unless_exists',
            'key': 'a/2'
        }, {
            'authors': {
                'connect': 'update_list',
                'value': [{
                    'key': '/a/1'
                }, {
                    'key': 'a/2'
                }]
            },
            'create': 'unless_exists',
            'key': '/foo'
        }]
    """
    def flatten(query, result, path=[], from_list=False):
        """This does two things. 
	    1. It flattens the query and appends it to result.
        2. It returns its minimal value to use in parent query.
        """
        if isinstance(query, list):
            data = [flatten(q, result, path + [str(i)], from_list=True) for i, q in enumerate(query)]
            return data
        elif isinstance(query, dict):
            #@@ FIX ME
            q = query.copy()
            for k, v in q.items():
                q[k] = flatten(v, result, path + [k])
                
            if 'key' in q:
                result.append(Query(path, q))
                
            if from_list:
                #@@ quick fix
                if 'key' in q:
                    data = {'key': q['key']}
                else:
                    # take keys (connect, key, type, value) from q
                    data = dict((k, v) for k, v in q.items() if k in ("connect", "key", "type", "value"))
            else:
                # take keys (connect, key, type, value) from q
                data = dict((k, v) for k, v in q.items() if k in ("connect", "key", "type", "value"))
            return data
        else:
            return query
            
    result = []
    flatten(query, result)                         
    return result

class QueryError(Exception):
    def __init__(self, path, msg):
        Exception.__init__(self, "%s (at %s)" % (msg, repr(path)))
        self.msg = msg
        self.path = path
        
def optimize(store, key, query):
    """Optimizes the query by removing unnecessary actions.
    """
    thing = store.get(key)
    
    def equal(name):
        q = query[name]
        
        if name in thing:
            datatype, value = thing.get(name)
        else:
            if q.connect == 'update':
                datatype, value = None, None
            else:
                datatype, value = None, []
            
        if q.connect == 'update':
            return (q.value == None and value == None) or (q.datatype == datatype and q.value == value)
        elif q.connect == 'update_list':
            return (q.value == [] and value == []) or (q.datatype == datatype and q.value == value)
        elif q.connect == 'insert':
            return isinstance(value, list) and q.value in value
        elif q.connect == 'delete':
            return isinstance(value, list) and q.value not in value
        else:
            # not possible case.
            return False
    
    # don't try to optimize if there is change in type
    # The store might keep values for each type in different tables.
    if 'type' in query and not equal('type'):
        return query
        
    for k in query.keys():
        if equal(k):
            del query[k]
    
    return query
        
def compile(store, query):
    """Compiles the given query.
    
        >>> store = common.create_test_store()
        >>> q = {
        ...     'create': 'unless_exists',
        ...     'key': '/foo',
        ...     'type': '/type/book',
        ...     'author': {
        ...        'key': '/author/test',
        ...     },
        ...     'descption': {'value': 'foo', 'type': '/type/text'}
        ... }
        >>> pprint(compile(store, Query('', q)))
        ('create', '/foo', {
            'author': <'/author/test' of type '/type/author'>,
            'descption': <'foo' of type '/type/text'>,
            'type': <'/type/book' of type '/type/type'>
        })
        >>> q = {
        ...     'key': '/book/test',
        ...     'type': '/type/book',
        ...     'author': {
        ...         'connect': 'update',
        ...         'key': '/author/test',
        ...     },
        ...     'descption': {'value': 'foo', 'type': '/type/text', 'connect': 'update'}
        ... }
        >>> pprint(compile(store, Query('', q)))
        ('update', '/book/test', {
            'author': <'/author/test' of type '/type/author' connect=update>,
            'descption': <'foo' of type '/type/text' connect=update>
        })
    """
    def query_value(path, v):
        if isinstance(v, dict):
            if 'value' in v and isinstance(v['value'], list):
                return ListQueryValue(path, v)
            else:
                return QueryValue(path, v)
        elif isinstance(v, list):
            return ListQueryValue(path, dict(value=v))
        else:
            return QueryValue(path, dict(value=v))

    def get_expected_type(type, name):
        if name == 'key':
            return '/type/key'
        elif name == 'type':
            return '/type/type'
        else:
            p = type.get_property(name)
            return p and p.expected_type and p.expected_type.key
    
    def coerce_all(d, type):
        for k, v in d.items():
            v.coerce(store, get_expected_type(type, k))
            
    def get_type(thing, type_key):
        if type_key:
            #@@ what if there is no such type?
            type = store.get(type_key)
            assert type is not None
            return type
        else:
            return thing.type
        
    def process(path, d):
        """convert all values to QueryValues."""
        result = {}
        for k, v in d.items():
            result[k] = query_value(path + '.' + k, v)
        return result

    d = query.query

    if 'key' not in d:
        raise QueryError(query.path, 'Missing key')

    key = d.pop('key')
    thing = store.get(key)
    
    create = d.pop('create', None)
    d = process(query.path, d)
    has_connects = any(v.connect for v in d.values())
    
    if create and thing is None:
        if 'type' not in d:
            raise QueryError(query.path, 'Missing type')
        
        type = get_type(None, d['type'].value)
        coerce_all(d, type)
        return 'create', key, d
    elif has_connects:
        if not thing:
            raise QueryError(query.path, 'Not found: ' + repr(key))
            
        d = dict((k, v) for k, v in d.items() if v.connect)
        type_key = d.get('type')
        type = type_key and get_type(thing, type_key.value) or thing.type
        coerce_all(d, type)
        return 'update', key, d
    else:
        return 'ignore', key, None

class Query(web.storage):
    def __init__(self, path, query):
        if isinstance(path, list):
            path = ".".join(path)
        
        self.path = path
        self.query = query
    
    def __repr__(self):
        return common.prepr(self.query)

class QueryValue:
    """Representation of a value in the query dict.
    Each query value contains a `value` and a `type`.
    It also contains fields `connect` and `create` to know to how use this value in query execution.
    
        >>> QueryValue('', dict(value=1))
        <1 of type '/type/int'>
        >>> QueryValue('', dict(value="foo", type='/type/text'))
        <'foo' of type '/type/text'>
        >>> QueryValue('', dict(key="/foo"))
        <'/foo' of type '/type/object'>
    """
    def __init__(self, path, data):
        if isinstance(path, list):
            path = ".".join(path)
        self.path = path
        
        if not isinstance(data, dict):
            data = dict(value=data)
            
        self._data = data
        
        keys = ['key', 'value', 'type', 'connect', 'create']
        for k in keys:
            setattr(self, k, data.get(k))
        
        # just for easy of use
        if self.key is not None:
            self.value = self.key
            self._key_specified = True
        elif self.value is not None:
            self._key_specified = False
            self.key = self.value
        else:
            self._key_specified = False
            
    def get_datatype(self):
        return type2datatype(self.guess_type())
        
    datatype = property(get_datatype)
            
    def guess_type(self):
        """Guess type of this QueryValue.
        
            >>> QueryValue('', dict(value=1)).guess_type()
            '/type/int'
            >>> QueryValue('', dict(value='foo')).guess_type()
            '/type/string'
            >>> QueryValue('', dict(value='foo', type='/type/text')).guess_type()
            '/type/text'
        """
        if self.type:
            return self.type
        elif isinstance(self.value, bool):
            return '/type/boolean'
        elif isinstance(self.value, int):
            return '/type/int'
        elif isinstance(self.value, float):
            return '/type/float'
        elif self._key_specified:
            return '/type/object'
        else:
            return '/type/string'
            
    def assert_unique(self, unique):
        pass
    
    def coerce(self, store, expected_type):
        r"""Coerces this QueryValue to the expected type.
        
            >>> v = QueryValue('page.body', dict(value='foo'))
            >>> v.coerce(None, '/type/text')
            >>> v.type
            '/type/text'

            >>> store = common.create_test_store()
            >>> v = QueryValue('book.type', dict(key='/type/book'))
            >>> v.coerce(store, '/type/type')
            >>> v.type
            '/type/type'
    
        When the coercion is not possible, it raises Exception.
        
            >>> v = QueryValue('book.pages', dict(value=23))
            >>> v.coerce(None, '/type/string')
            Traceback (most recent call last):
                ...
            QueryError: Expected /type/string, but found /type/int: 23 (at 'book.pages')
        """
        if expected_type is None or self.guess_type() == expected_type or self.value is None:
            return
            
        if self.type is not None:
            raise QueryError(self.path, "Expected %s, but found %s: %s" % (expected_type, self.guess_type(), repr(self.value)))
        elif expected_type not in common.primitive_types:
            thing = store.get(self.key)
            if thing is None:
                msg = "%s is not found" % repr(self.key)
                raise QueryError(self.path, msg)
            elif thing.type.key != expected_type and expected_type != '/type/object': # /type/object means any type
                msg = "Expected %s, but found %s: %s" % (repr(expected_type), repr(thing.type.key), repr(self.key))
                raise QueryError(self.path, msg)
        
        # string can be converted to int or float
        elif expected_type in ["/type/int", "/type/float"]:
            if self.guess_type() != '/type/string':
                raise QueryError(self.path, "Expected %s, but found %s: %s" % (expected_type, self.guess_type(), repr(self.value)))
                
            d = {'/type/int': int, '/type/float': float}
            try:
                self.value = d[expected_type](self.value)
            except ValueError:
                raise QueryError(self.path, "Expected %s, but found %s: %s" % (expected_type, self.guess_type(), repr(self.value)))
                
        # nothing can be converted to string
        elif expected_type == '/type/string':
            raise QueryError(self.path, "Expected %s, but found %s: %s" % (expected_type, self.guess_type(), repr(self.value)))
            
        # int, float and boolean can not be converted to any other type
        elif self.guess_type() in ["/type/int", "/type/float", "/type/boolean"]:
            raise QueryError(self.path, "Expected %s, but found %s: %s" % (expected_type, self.guess_type(), repr(self.value)))
        elif expected_type == '/type/boolean':
            if self.guess_type() == '/type/string':
                self.value = self.value.lower() != 'false' and self.value.lower() != ''
        
        #@@ validate conversion to datetime, url etc
        self.type = expected_type

    def __repr__(self):
        if self.connect:
            connect = ' connect=' + self.connect
        else:
            connect = ''
        return "<%s of type %s%s>" % (repr(self.value), repr(self.guess_type()), connect)

class ListQueryValue:
    """
        >>> ListQueryValue('', [1, 2, 3])
        <[1, 2, 3] of type None>
    """
    def __init__(self, path, data):
        if isinstance(path, list):
            path = ".".join(path)
            
        if not isinstance(data, dict):
            data = dict(value=data)            
            
        self.connect = data.get('connect')
        self.values = [QueryValue(path + '.' + str(i), v) for i, v in enumerate(data['value'])]
        self.type = None
        
    def get_value(self):
        return [v.value for v in self.values]
        
    value = property(get_value)
    
    def coerce(self, store, expected_type):
        if expected_type is None:
            if self.values:
                expected_type = self.values[0].guess_type()
            else:
                # values is empty list. Any type with do.
                expected_type = '/type/string'
                
        for v in self.values:
            v.coerce(store, expected_type)
        self.type = expected_type

    def get_datatype(self):
        return type2datatype(self.type)

    datatype = property(get_datatype)
        
    def __repr__(self):
        return "<%s of type %s>" % (self.value, repr(self.type))
        
if __name__ == "__main__":
    import doctest
    doctest.testmod()