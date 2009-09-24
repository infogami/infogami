"""
"""
import common
from common import pprint, any, all
import web

def get_thing(store, key, revision=None):
    if isinstance(key, common.Reference):
        key = unicode(key)
    json = store.get(key, revision)
    return json and common.Thing.from_json(store, key, json)

class SaveProcessor:
    def __init__(self, store, author):
        self.store = store
        self.author = author
        
    def process(self, key, data):
        if 'key' not in data:
            data['key'] = key

        assert data['key'] == key

        data = common.parse_query(data)
        self.validate_properties(data)
        
        if not web.ctx.get('disable_permission_check', False) and not has_permission(self.store, self.author, key):
            raise common.PermissionDenied(message='Permission denied to modify %s' % repr(key))
        
        type = data.get('type')
        if type is None:
            raise common.BadData(message="missing type")
        type = self.process_value(type, self.get_property(None, 'type'))
        type = get_thing(self.store, type)
        
        thing = get_thing(self.store, key)
        prev_data = thing and thing._get_data()

        # when type is changed, consider as all object is modified and don't compare with prev data.
        if prev_data and prev_data.get('type') != type.key:
            prev_data = None

        data = self.process_data(data, type, prev_data)

        for k in common.READ_ONLY_PROPERTIES:
            data.pop(k, None)
            prev_data and prev_data.pop(k, None)
            
        if data == prev_data:
            return None
        else:
            return data

    def get_property(self, type, name):
        if name == 'type':
            return web.storage(name='type', expected_type=web.storage(key='/type/type', kind="regular"), unique=True)
        elif name in ['permission', 'child_permission']:
            return web.storage(name=name, expected_type=web.storage(key='/type/permission', kind="regular"), unique=True)
        else:
            for p in type.get('properties', []):
                if p.get('name') == name:
                    return p
                    
    def validate_properties(self, data):
        rx = web.re_compile('^[a-z][a-z0-9_]*$')
        for key in data:
            if not rx.match(key):
                raise common.BadData(message="Bad Property: %s" % repr(key))

    def process_data(self, d, type, old_data=None):
        for k, v in d.items():
            if v is None or v == [] or web.safeunicode(v).strip() == '':
                del d[k]
            else:
                if old_data and old_data.get(k) == v:
                    continue
                p = self.get_property(type, k)
                if p:
                    d[k] = self.process_value(v, p)
                else:
                    d[k] = v
        if type:
            d['type'] = common.Reference(type.key)
            
        return d

    def process_value(self, value, property):
        """
            >>> def property(expected_type, unique=True):
            ...     return web.storage(expected_type=web.storage(key=expected_type, kind='regular'), unique=unique)
            ...
            >>> p = SaveProcessor(common.create_test_store(), None)
            
            >>> p.process_value(1, property('/type/int'))
            1
            >>> p.process_value('1', property('/type/int'))
            1
            >>> p.process_value(['1', '2'], property('/type/int', unique=False))
            [1, 2]
            >>> p.process_value('x', property('/type/int'))
            Traceback (most recent call last):
                ... 
            BadData: {"message": "invalid literal for int() with base 10: 'x'", "error": "bad_data"}
            >>> p.process_value('1', property('/type/int', unique=False))
            Traceback (most recent call last):
                ... 
            BadData: {"message": "expected list, found atom", "error": "bad_data"}
            >>> p.process_value(['1'], property('/type/int'))
            Traceback (most recent call last):
                ... 
            BadData: {"message": "expected atom, found list", "error": "bad_data"}
            >>> p.process_value('/type/string', property('/type/type'))
            <ref: u'/type/string'>
        """
        unique = property.get('unique', True)
        expected_type = property.expected_type.key

        if isinstance(value, list):
            if unique is True:
                raise common.BadData(message='expected atom, found list')
            
            p = web.storage(property.copy())
            p.unique = True
            return [self.process_value(v, p) for v in value]
    
        if unique is False:    
            raise common.BadData(message='expected list, found atom')

        type_found = common.find_type(value)
    
        if expected_type in common.primitive_types:
            # string can be converted to any type and int can be converted to float
            try:
                if type_found == '/type/string' and expected_type != '/type/string':
                    value = common.primitive_types[expected_type](value)
                elif type_found == '/type/int' and expected_type == '/type/float':
                    value = float(value)
            except ValueError, e:
                raise common.BadData(message=str(e))
        elif property.expected_type.kind == 'embeddable':
            if isinstance(value, dict):
                return self.process_data(value, property.expected_type)
            else:
                raise common.TypeMismatch(expected_type, type_found)
        else:
            if type_found == '/type/string':
                value = common.Reference(value)
    
        type_found = common.find_type(value)
    
        if type_found == '/type/object':
            thing = get_thing(self.store, value)
            if thing is None:
                raise common.NotFound(key=value)
            type_found = thing.type.key

        if expected_type != type_found:
            raise common.BadData(message='expected %s, found %s' % (repr(property.expected_type.key), repr(type_found)))
        return value

class WriteQueryProcessor:
    def __init__(self, store, author):
        self.store = store
        self.author = author
        
    def process(self, query):
        p = SaveProcessor(self.store, self.author)
        
        for q in serialize(query):
            q = common.parse_query(q)
            
            if not isinstance(q, dict) or q.get('key') is None:
                continue

            key = q['key']                
            thing = get_thing(self.store, key)
            create = q.pop('create', None)
            
            if thing is None:
                if create:
                    q = self.remove_connects(q)
                else:
                    raise common.NotFound(key=key)
            else:
                q = self.connect_all(thing._data, q)
            
            yield p.process(key, q)
    
    def remove_connects(self, query):
        for k, v in query.items():
            if isinstance(v, dict) and 'connect' in v:
                if 'key' in v:
                    value = v['key'] and common.Reference(v['key'])
                else:
                    value = v['value']
                query[k] = value
        return query
            
    def connect_all(self, data, query):
        """Applys all connects specified in the query to data.
        
            >>> p = WriteQueryProcessor(None, None)
            >>> data = {'a': 'foo', 'b': ['foo', 'bar']}
            
            >>> query = {'a': {'connect': 'update', 'value': 'bar'}, 'b': {'connect': 'insert', 'value': 'foobar'}}
            >>> p.connect_all(data, query)
            {'a': 'bar', 'b': ['foo', 'bar', 'foobar']}
            
            >>> query = {'a': {'connect': 'update', 'value': 'bar'}, 'b': {'connect': 'delete', 'value': 'foo'}}
            >>> p.connect_all(data, query)
            {'a': 'bar', 'b': ['bar']}

            >>> query = {'a': {'connect': 'update', 'value': 'bar'}, 'b': {'connect': 'update_list', 'value': ['foo', 'foobar']}}
            >>> p.connect_all(data, query)
            {'a': 'bar', 'b': ['foo', 'foobar']}
        """
        import copy
        data = copy.deepcopy(data)
        
        for k, v in query.items():
            if isinstance(v, dict):
                if 'connect' in v:
                    if 'key' in v:
                        value = v['key'] and common.Reference(v['key'])
                    else:
                        value = v['value']            
                    self.connect(data, k, v['connect'], value)
        return data
        
    def connect(self, data, name, connect, value):
        """Modifies the data dict by performing the specified connect.
        
            >>> getdata = lambda: {'a': 'foo', 'b': ['foo', 'bar']}
            >>> p = WriteQueryProcessor(None, None)
            
            >>> p.connect(getdata(), 'a', 'update', 'bar')
            {'a': 'bar', 'b': ['foo', 'bar']}
            >>> p.connect(getdata(), 'b', 'update_list', ['foobar'])
            {'a': 'foo', 'b': ['foobar']}
            >>> p.connect(getdata(), 'b', 'insert', 'foobar')
            {'a': 'foo', 'b': ['foo', 'bar', 'foobar']}
            >>> p.connect(getdata(), 'b', 'insert', 'foo')
            {'a': 'foo', 'b': ['foo', 'bar']}
            >>> p.connect(getdata(), 'b', 'delete', 'foobar')
            {'a': 'foo', 'b': ['foo', 'bar']}
        """
        if connect == 'update' or connect == 'update_list':
            data[name] = value
        elif connect == 'insert':
            if value not in data[name]:
                data[name].append(value)
        elif connect == 'delete':
            if value in data[name]:
                data[name].remove(value)
        return data
            
def serialize(query):
    ""
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
                result.append(q)
                
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

def has_permission(store, author, key):
    # admin user can modify everything
    if author and author.key == '/user/admin':
        return True
    
    permission = get_permission(store, key)
    if permission is None:
        return True
    else:
        groups = permission.get('writers') or [] 
        # admin users can edit anything
        groups = groups + [get_thing(store, '/usergroup/admin')]
        for group in groups:
            if group.key == '/usergroup/everyone':
                return True
            elif author is not None:
                members = [m.key for m in group.get('members', [])]
                if group.key == '/usergroup/allusers' or author.key in members:
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
        thing = get_thing(store, key)
        if child_permission:
            permission = thing and (thing.get("child_permission") or thing.get("permission"))
        else:
            permission = thing and thing.get("permission")
        return permission or _get_permission(parent(key), child_permission=True)

    return _get_permission(key)
    
if __name__ == "__main__":
    import doctest
    doctest.testmod()
