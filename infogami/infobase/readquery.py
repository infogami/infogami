import web
import re

import infobase
from infobase import TYPE_KEY, TYPE_STRING, TYPE_INT, TYPE_FLOAT, TYPE_BOOLEAN, TYPE_URI, TYPE_DATETIME, DATATYPE_REFERENCE, MAX_REVISION

ALL_TYPES = [TYPE_KEY, TYPE_STRING, TYPE_INT, TYPE_FLOAT, TYPE_BOOLEAN, TYPE_URI, TYPE_DATETIME, DATATYPE_REFERENCE]

if not hasattr(__builtins__, 'all'):
    def all(items):
        for item in items:
            if not item: 
                return False
        return True
    
    def any(items):
        for item in items:
            if item: 
                return True
        return False
        
class operator:
    def __init__(self, op, allowed_datatypes, sqlop=None, process=None, compare=None):
        self.op = op
        self.sqlop = sqlop or op
        self.allowed_datatypes = allowed_datatypes
        self.process = process or (lambda x: x)
        self.compare = compare
        
    def query(self, column):
        return "%s %s $value" % (column, self.sqlop)
        
    def __repr__(self):
        return "<op: %s>" % repr(self.op)
    __str__ = __repr__

EQ = operator("=", ALL_TYPES, compare=lambda x, y: x == y)
NE = operator("!=", ALL_TYPES, compare=lambda x, y: x != y)
LT = operator("<", [TYPE_INT, TYPE_FLOAT], compare=lambda x, y: x < y)
LE = operator("<=", [TYPE_INT, TYPE_FLOAT], compare=lambda x, y: x <= y)
GT = operator(">", [TYPE_INT, TYPE_FLOAT], compare=lambda x, y: x > y)
GE = operator(">=", [TYPE_INT, TYPE_FLOAT], compare=lambda x, y: x >= y)
LIKE = operator("~", [TYPE_KEY, TYPE_STRING, TYPE_URI], 'LIKE', 
        lambda value: value.replace('*', '%'), 
        compare=lambda x, y: bool(re.match('^' + x.replace('*', '.*') + '$', y)))
        
operators = [LT, LE, GT, GE, LIKE, NE, EQ] # EQ must be at the end

def _test_ops():
    """
        >>> (2, 2)
        True
        >>> EQ.compare(2, 3)
        False
        >>> NE.compare(2, 2)
        False
        >>> NE.compare(2, 3)
        True
        >>> LIKE.compare('/foo/*', '/foo/bar')
        True
        >>> LIKE.compare('/foo/*', '/bar')
        False
    """
    pass
    
class Things:
    def __init__(self, site, query):
        self.site = site
        
        self.offset = query.pop('offset', None)
        self.limit = query.pop('limit', None)
        self.sort = query.pop('sort', None)
        
        self.type = query.get('type')
        self.type = self.type and self.site.withKey(self.type)
        self.revision = query.pop('revision', MAX_REVISION)
        
        self.query = query
        self.items = self.process_query(query)
        
    def matches(self, thing):
        try:
            return all(item.matches(thing) for item in self.items)
        except:
            import traceback
            traceback.print_exc()
            # if there is any error then in matching better remove it from cache
            return True
    
    def __eq__(self, other):
        return isinstance(other, Things) \
            and self.type == other.type \
            and self.offset == other.offset \
            and self.limit == other.limit \
            and self.sort == other.sort \
            and self.query == other.query
        
    def __ne__(self, other):
        return not (self == other)
        
    def __hash__(self):
        d = (self.type and self.type.key, self.offset, self.limit, self.sort, tuple(self.query.items()))
        return hash(d)
        
    def process_query(self, query):
        items = []
        for key, value in query.items():
            key, op = parse_key(key)
            items.append(ThingItem(self.site, self.type, key, op, value))
        return items
        
    def execute(self):        
        #@@ make sure all keys are valid.
        tables = ['thing']
        what = 'thing.key'
        where = web.reparam('thing.site_id = $self.site.id', locals())
        
        order = self.sort
        if order:
            if order.startswith('-'):
                order = order[1:]
                desc = " desc"
            else:
                desc = ""
                
            # allow sort based on thing columns
            if order in ['id', 'created', 'last_modified', 'key']:
                order = 'thing.' + order + desc
            else:
                datatype = get_datatype(self.type, order)
                tables.append('datum as ds')
                where += web.reparam(" AND ds.thing_id = thing.id"
                    + " AND ds.end_revision = 2147483647"
                    + " AND ds.key = $order AND ds.datatype = $datatype", locals())
                order = "ds.value" + desc
            
        for i, item in enumerate(self.items):
            d = 'd%d' % i
            tables.append('datum as ' + d)
            where += ' AND ' + item.query(d, self.revision)
            
        return [r.key for r in web.select(tables, what=what, where=where, offset=self.offset, limit=self.limit, order=order)]
    
class ThingItem:
    """An Item in Things query.
    """
    def __init__(self, site, type, key, op, value):
        self.site = site
        self.type = type
        self.key = key
        self.op = op
        self.datatype = get_datatype(type, key, value)
        self.value = self.coerce(self.datatype, value)
        
        if self.datatype not in self.op.allowed_datatypes:
            raise Exception, '%s is not allowed for %s' % (self.op.op, self.datatype)
        
    def matches(self, thing):
        value = thing._get(self.key)
        if not isinstance(value, list):
            value = [value]
        return any(self.op.compare(self.value, self.coerce(self.datatype, v)) for v in value)
        
    def coerce(self, datatype, value):
        if isinstance(value, infobase.Datum):
            value = value.value
            
        if value is None:
            return None

        if datatype in [TYPE_BOOLEAN, TYPE_INT, DATATYPE_REFERENCE]:
            if datatype == DATATYPE_REFERENCE:
                if isinstance(value, basestring):
                    value = self.site.withKey(value).id
                elif isinstance(value, infobase.Thing):
                    value = value.id
                else:
                    raise Exception, 'Bad data: %s %s' % (repr(value), value.__class__)
            elif datatype == TYPE_BOOLEAN:
                value = int(value)
        elif datatype == TYPE_FLOAT:
            value = float(value)
        else:
            value = str(value)
        
        return value
        
    def query(self, table, revision):
        key = self.key
        datatype = self.datatype
        value = self.op.process(self.value)
        q = ['%(table)s.thing_id = thing.id',
            '%(table)s.end_revision = 2147483647',
            '%(table)s.key = $key',
            self.op.query(self.cast(table + '.value')),
            '%(table)s.datatype = $datatype']
        q = ' AND '.join(q) % locals()
        return web.reparam(q, locals())
        
    def cast(self, column):
        if self.datatype in [TYPE_BOOLEAN, TYPE_INT, DATATYPE_REFERENCE]:
            return 'cast(%s as int)' % column
        elif self.datatype == TYPE_FLOAT:
            return 'cast(%s as float)'% column
        else:
            return column
        
def parse_key(key):
    """Parses key and returns key and operator.
    """
    for op in operators:
        if key.endswith(op.op):
            key = key[:-len(op.op)]
            return key, op
    return key, EQ

def join(site, type, table, key, value, revision):
    """Creates join query to join on condition specified by key and value."""
    key, op = parse_key(key)
    if not web.re_compile('[a-zA-Z][a-zA-Z_]*').match(key):
        raise Exception, "invalid key: %s" % key
            
    datatype = get_datatype(type, key)
    if datatype not in op.allowed_datatypes:
        raise Exception, '%s is not allowed for %s' % (op.op, infobase.TYPES.get(datatype, 'references'))
        
    if datatype in [TYPE_BOOLEAN, TYPE_INT, DATATYPE_REFERENCE]:
        value_column = 'cast(%s.value as int)' % table
        
        if datatype == DATATYPE_REFERENCE:
            value = site.withKey(value).id
        elif datatype == TYPE_BOOLEAN:
            value = int(value)
    elif datatype == TYPE_FLOAT:
        value_column = 'cast(%s.value as float)' % table
        value = float(value)
    else:
        value_column = '%s.value' % table
        value = str(value)
    
    value = op.process(value)
    q = ['%(table)s.thing_id = thing.id',
        '%(table)s.begin_revision <= $revision',
        '%(table)s.end_revision > $revision',
        '%(table)s.key = $key',
        op.query(value_column),
        '%(table)s.datatype = $datatype']
        
    q = ' AND '.join(q) % locals()
    return web.reparam(q, locals())

def get_datatype(type, key, value=None):
    # "key" and "type" always have the same type
    if key == 'key':
        return infobase.TYPES['/type/key']
    elif key in ['type', 'permission', 'child_permission']:
        return DATATYPE_REFERENCE
        
    # see of you infer the datatype from the type of the object
    if value is None:
        pass
    elif isinstance(value, int):
        return infobase.TYPES['/type/int']
    elif isinstance(value, float):
        return infobase.TYPES['/type/float']
    elif isinstance(value, bool):
        return infobase.TYPES['/type/boolean']
        
    # if possible, get the datatype from the type schema
    if type:
        key = type.key + '/' + key
        p = None
        for pp in type._get('properties', []):
            if pp.key == key:
                p = pp
            
        if p:
            expected_type = p.expected_type.key
            if expected_type in infobase.TYPES:
                return infobase.TYPES[expected_type]
            else:
                return DATATYPE_REFERENCE
    
    # everything is a string, unless specified otherwise.
    return infobase.TYPES['/type/string']
    
class Versions:
    def __init__(self, site, query):
        self.site = site
        
        self.offset = query.pop('offset', None)
        self.limit = query.pop('limit', None)
        self.sort = query.pop('sort', None)
        
        self.query = web.storage(query)
        
        author = self.query.pop('author', None)
        if author:
            self.query.author_id = self.site.withKey(author).id
        
        key = self.query.pop('key', None)
        if key:
            self.query.thing_id = self.site.withKey(key).id
        
        keys = ['thing_id', 'revision', 'author_id', 'comment', 'machine_comment', 'ip', 'created']
        for k in self.query:
            assert k in keys
        
    def get_order(self):
        order = self.sort

        if order:
            if order.startswith('-'):
                order = order[1:]
                desc = " desc"
            else:
                desc = ""
        
            keys = ["key", "revision", "author", "comment", "created"]
            assert order in keys
            order = order + desc
        return order
        
    def execute(self):
        query = self.query
        
        tables = ['thing', 'version']
        what = 'thing.key, version.*'
        where = 'thing.id = version.thing_id'
        
        for k, v in self.query.items():
            where += web.reparam(' AND %s=$v' % (k), locals())
            
        result = web.select(['version', 'thing'], what=what, where=where, offset=self.offset, limit=self.limit, order=self.get_order(), vars=locals())
        out = []

        for r in result:
            r.created = r.created.isoformat()
            r.author = r.author_id and self.site.withID(r.author_id).key
            del r.author_id
            out.append(dict(r))
        return out
        
    def matches(self, version):
        try:
            return all(self.query[k] == version[k] for k in self.query)
        except:
            import traceback
            traceback.print_exc()
            # if there is any error then in matching better remove it from cache
            return True
    
    def __hash__(self):
        d = (self.offset, self.limit, self.sort, tuple(self.query.items()))
        return hash(d)
        
    def __eq__(self, other):
        return self._get_data() == other._get_data()

    def __ne__(self, other):
        return self._get_data() != other._get_data()
        
    def _get_data(self):
        return (self.offset, self.limit, self.sort, tuple(self.query.items()))
        
    def __repr__(self):
        return "<versions: %s at %s>" % (repr(dict(self.query)), hash(self))
    
    __str__ = __repr__

if __name__ == "__main__":
    import doctest
    doctest.testmod()
    
