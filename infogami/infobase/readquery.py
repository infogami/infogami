import re

import simplejson
import web

from infogami.infobase import common

def get_thing(store, key, revision=None):
    json = key and store.get(key, revision)
    return json and common.Thing.from_json(store, key, json)

def run_things_query(store, query):
    query = make_query(store, query)
    keys = store.things(query)

    xthings = {}
    def load_things(keys, query):
        _things = simplejson.loads(store.get_many(keys))
        xthings.update(_things)

        for k, v in query.requested.items():
            k = web.lstrips(k, query.prefix)
            if isinstance(v, Query):
                keys2 = common.flatten([d.get(k) for d in _things.values() if d.get(k)])
                keys2 = [k['key'] for k in keys2]
                load_things(set(keys2), v)

    def get_nested_data(value, query):
        if isinstance(value, list):
            return [get_nested_data(v, query) for v in value]
        elif isinstance(value, dict) and 'key' in value:
            thingdata = xthings[value['key']]
            return get_data(thingdata, query)
        else:
            return value

    def get_data(thingdata, query):
        fields = dict((web.lstrips(k, query.prefix), v) for k, v in query.requested.items())

        # special care for '*'
        if '*' in fields:
            f = dict((k, None) for k in thingdata.keys())
            fields.pop('*')
            f.update(fields)
            fields = f

        d = {}
        for k, v in fields.items():
            value = thingdata.get(k)
            if isinstance(v, Query):
                d[k] = get_nested_data(value, v)
            else:
                d[k] = value
        return d

    data = [{'key': key} for key in keys]
    if query.requested.keys() == ['key']:
        return data
    else:
        load_things(keys, query)

        # @@@ Sometimes thing.latest_revision is not same as max(data.revision) due to some data error.
        # @@@ Temporary work-around to handle that case.
        data = [d for d in data if d['key'] in xthings]
        return get_nested_data(data, query)

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
        self.prefix = None
        self.requested = {"key": None}

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
            raise common.BadData(message="missing 'type' in query")

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

def make_query(store, query, prefix=""):
    """Creates a query object from query dict.
        >>> store = common.create_test_store()
        >>> make_query(store, {'type': '/type/page'})
        <query: ['type = ref:/type/page']>
        >>> make_query(store, {'life': 42, 'type': '/type/page', 'title~': 'foo'})
        <query: ['life = int:42', 'type = ref:/type/page', 'title ~ str:foo']>
        >>> make_query(store, {'a:life<': 42, 'type': '/type/page', 'title~': 'foo', "b:life>": 420})
        <query: ['life < int:42', 'type = ref:/type/page', 'title ~ str:foo', 'life > int:420']>
    """
    query = common.parse_query(query)
    q = Query()
    q.prefix = prefix
    q.offset = common.safeint(query.pop('offset', None), 0)
    q.limit = common.safeint(query.pop('limit', 20), 20)
    if q.limit > 1000:
        q.limit = 1000
    sort = query.pop('sort', None)

    nested = (prefix != "")

    for k, v in query.items():
        # key foo can also be written as label:foo
        k = k.split(':')[-1]
        if v is None:
            q.requested[k] = v
        elif isinstance(v, dict):
            # make sure op is ==
            v = dict((k + '.' + key, value) for key, value in v.items())
            q2 = make_query(store, v, prefix=prefix + k + ".")
            #@@ Anand: Quick-fix
            # dbstore.things looks for key to find whether type is required or not.
            q2.key = k
            if q2.conditions:
                q.conditions.append(q2)
            else:
                q.requested[k] = q2
        else:
            k, op = parse_key(k)
            q.add_condition(k, op, None, v)

    if not nested:
        q.assert_type_required()

    type = get_thing(store, q.get_type())
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
        >>> parse_key('foo!=')
        ('foo', '!=')
    """
    operators = ["!=", "=", "<", "<=", ">=", ">", "~"]
    operator = "="
    for op in operators:
        if key.endswith(op):
            key = key[:-len(op)]
            operator = op
            break

    return key, operator

def make_versions_query(store, query):
    """Creates a versions query object from query dict.
    """
    q = Query()

    q.offset = common.safeint(query.pop('offset', None), 0)
    q.limit = common.safeint(query.pop('limit', 20), 20)
    if q.limit > 1000:
        q.limit = 1000
    q.sort = query.pop('sort', '-created')

    columns = ['key', 'type', 'revision', 'author', 'comment', 'machine_comment', 'ip', 'created', 'bot']

    for k, v in query.items():
        if k not in columns:
            raise ValueError(k)
        q.add_condition(k, '=', None, v)

    return q

if __name__ == "__main__":
    import doctest
    doctest.testmod()
