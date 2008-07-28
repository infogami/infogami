"""
"""
import common
from common import types, pprint, datatype2type, type2datatype, any, all
import web

def make_query(store, query):
    r"""Compiles query into subqueries.    
    """
    for q in serialize(query):
        action, key, q = compile(store, q)
        if action != 'ignore':
            yield action, key, q
    
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
    def flatten(query, result, path=[]):
        """This does two things. 
	    1. It flattens the query and appends it to result.
        2. It returns its minimal value to use in parent query.
        """
        if isinstance(query, list):
            data = [flatten(q, result, path + [str(i)]) for i, q in enumerate(query)]
            return data
        elif isinstance(query, dict):
            #@@ FIX ME
            q = query.copy()
            for k, v in q.items():
                q[k] = flatten(v, result, path + [k])
                
            if 'key' in q:
                result.append(Query(path, q))
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
        
        type = get_type(thing, d.get('type'))
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
    """
    def __init__(self, path, data):
        if isinstance(path, list):
            path = ".".join(path)
        self.path = path
        
        if not isinstance(data, dict):
            data = dict(value=data)
        
        keys = ['key', 'value', 'type', 'connect', 'create']
        for k in keys:
            setattr(self, k, data.get(k))
            
        # just for easy of use
        if self.key is not None:
            self.value = self.key
        elif self.value is not None:
            self.key = self.value
            
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
        if expected_type is None or self.guess_type() == expected_type:
            return
            
        if self.type is not None:
            raise QueryError(self.path, "Expected %s, but found %s: %s" % (expected_type, self.guess_type(), repr(self.value)))
        elif expected_type not in common.primitive_types:
            thing = store.get(self.key)
            if thing is None:
                msg = "%s is not found" % repr(self.key)
                raise QueryError(self.path, msg)
            elif thing.type.key != expected_type:
                msg = "Expected %s, but found %s: %s" % (repr(expected_type), repr(thing.type.key), repr(self.key))
                raise QueryError(self.path, msg)
                
        # nothing can be converted to ini, float boolean and string
        elif expected_type in ["/type/int", "/type/float", "/type/boolean", "/type/string"]:
            raise QueryError(self.path, "Expected %s, but found %s: %s" % (expected_type, self.guess_type(), repr(self.value)))
            
        # int, float and boolean can not be converted to any other type
        elif self.guess_type() in ["/type/int", "/type/float", "/type/boolean"]:
            raise QueryError(self.path, "Expected %s, but found %s: %s" % (expected_type, self.guess_type(), repr(self.value)))
        
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
        self.value = [QueryValue(path + '.' + str(i), v) for i, v in enumerate(data['value'])]
        self.type = None
    
    def coerce(self, expected_type):
        for v in self.value:
            v.coerce(expected_type)
        self.type = expected_type
        
    def __repr__(self):
        return "<%s of type %s>" % ([v.value for v in self.value], repr(self.type))
        
if __name__ == "__main__":
    import doctest
    doctest.testmod()