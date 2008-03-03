import web

import infobase
from infobase import TYPE_KEY, TYPE_STRING, TYPE_INT, TYPE_FLOAT, TYPE_BOOLEAN, TYPE_URI, TYPE_DATETIME, DATATYPE_REFERENCE

ALL_TYPES = [TYPE_KEY, TYPE_STRING, TYPE_INT, TYPE_FLOAT, TYPE_BOOLEAN, TYPE_URI, TYPE_DATETIME, DATATYPE_REFERENCE]

class operator:
    def __init__(self, op, allowed_datatypes, sqlop=None, process=None):
        self.op = op
        self.sqlop = sqlop or op
        self.allowed_datatypes = allowed_datatypes
        self.process = process or (lambda x: x)
        
    def query(self, column):
        return "%s %s $value" % (column, self.sqlop)
        
    def matches(self, key):
        if key.endswith(self.op):
            return 
        
    def __repr__(self):
        return "<op: %s>" % repr(self.op)
    __str__ = __repr__

EQ = operator("=", ALL_TYPES)
NE = operator("!=", ALL_TYPES)
LT = operator("<", [TYPE_INT, TYPE_FLOAT])
LE = operator("<=", [TYPE_INT, TYPE_FLOAT])
GT = operator(">", [TYPE_INT, TYPE_FLOAT])
GE = operator(">=", [TYPE_INT, TYPE_FLOAT])
LIKE = operator("~", [TYPE_KEY, TYPE_STRING, TYPE_URI], 'LIKE', lambda value: value.replace('*', '%'))

operators = [LT, LE, GT, GE, LIKE, NE, EQ] # EQ must be at the end

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

def get_datatype(type, key):
    if key == 'key':
        return infobase.TYPES['/type/key']
    elif key == 'type':
        return DATATYPE_REFERENCE
        
    if type == None:
        return '/type/string'
        
    key = type.key + '/' + key
    p = None
    for pp in type.properties:
        if pp.key == key:
            p = pp
            
    if p:
        expected_type = p.expected_type.key
        if expected_type in infobase.TYPES:
            return infobase.TYPES[expected_type]
        else:
            return DATATYPE_REFERENCE
    else:
        return infobase.TYPES['/type/string']

