import common
from common import all, any
import web
import re

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
                
    def assert_type_required(self):
        type_required = any(c.key not in common.COMMON_PROPERTIES for c in self.conditions if not isinstance(c, Query))
        if type_required and self.get_type() is None:
            raise common.InfobaseException("missing 'type' in query")

    def add_condition(self, key, op, datatype, value):
        self.conditions.append(web.storage(key=key, op=op, datatype=datatype, value=value))
        
    def __repr__(self):
        def f(c):
            if isinstance(c, Query):
                return repr(c)
            else:
                return "%s %s %s:%s" % (c.key, c.op, c.datatype, c.value)
        conditions = [f(c) for c in self.conditions]
        return "<query: %s>" % repr(conditions)

def make_query(store, query, nested=False):
    """Creates a query object from query dict.
        >>> store = common.create_test_store()
        >>> make_query(store, {'type': '/type/page'})
        <query: ['type = ref:/type/page']>
        >>> make_query(store, {'type': '/type/page', 'title~': 'foo', 'life': 42})
        <query: ['life = int:42', 'type = ref:/type/page', 'title ~ str:foo']>
    """
    query = common.parse_query(query)
    q = Query()
    q.offset = query.pop('offset', None)
    q.limit = query.pop('limit', 1000)
    if q.limit > 1000:
        q.limit = 1000
    sort = query.pop('sort', None)
    
    for k, v in query.items():
        if isinstance(v, dict):
            # make sure op is ==
            v = dict((k + '.' + key, value) for key, value in v.items())
            q.conditions.append(make_query(store, v, nested=True))
        else:
            k, op = parse_key(k)
            q.add_condition(k, op, None, v)
            
    if not nested:
        q.assert_type_required()
        
    type = store.get(q.get_type())
    #assert type is not None, 'Not found: ' + q.get_type()
    for c in q.conditions:
        if not isinstance(c, Query):
            c.datatype = find_datatype(type, c.key, c.value)
            
    if sort:
        parse_key(sort) # to validate key
        q.sort = web.storage(key=sort, datatype=find_datatype(type, sort, None))
    else:
        q.sort = None
            
    return q
    
def find_datatype(type, key, value):
    """
        >>> find_datatype(None, "foo", 1)
        'int'
        >>> find_datatype(None, "foo", True)
        'boolean'
        >>> find_datatype(None, "foo", "hello")
        'str'
    """
    # special properties
    d = dict(
        key="key", 
        type="ref", 
        permission="ref",
        child_permission="ref",
        created="datetime", 
        last_modified="datetime")
    
    if key in d:
        return d[key]
    
    if isinstance(value, bool):
        return "boolean"
    elif isinstance(value, int):
        return "int"
    elif isinstance(value, float):
        return "float"
    elif isinstance(value, common.Reference):
        return 'ref'

    type2datatype = {
        '/type/string': 'str',
        '/type/int': 'int',
        '/type/float': 'float',
        '/type/boolean': 'boolean',
        '/type/datetime': 'datetime'
    }
    
    # if possible, get the datatype from the type schema
    p = type and type.get_property(key)
    return (p and type2datatype.get(p.expected_type.key, 'ref')) or "str"
    
def parse_key(key):
    """Parses key and returns key and operator.
        >>> parse_key('foo')
        ('foo', '=')
        >>> parse_key('foo=')
        ('foo', '=')
        >>> parse_key('foo<')
        ('foo', '<')
        >>> parse_key('foo~')
        ('foo', '~')
    """
    operators = ["=", "!=", "<", "<=", ">=", ">", "~"]
    for op in operators:
        if key.endswith(op):
            key = key[:-len(op)]
            return key, op

    if not re.match('^[a-zA-Z0-9_]*$', key):
        raise common.InfobaseException("Invalid property: %s" % repr(key))

    return key, "="
    
def make_versions_query(store, query):
    """Creates a versions query object from query dict.
    """
    q = Query()
    
    q.offset = query.pop('offset', None)
    q.limit = query.pop('limit', 1000)
    if q.limit > 1000:
        q.limit = 1000
    q.sort = query.pop('sort', None)
    
    columns = ['key', 'type', 'revision', 'author', 'comment', 'machine_comment', 'ip', 'created']
    
    for k, v in query.items():
        assert k in columns
        q.add_condition(k, '=', None, v)
        
    return q
    
if __name__ == "__main__":
    import doctest
    doctest.testmod()
