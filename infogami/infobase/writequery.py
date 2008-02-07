"""Module to execute infobase write queries.
"""
import web
import infobase

PRIMITIVE_TYPES = "type/string", "type/text", "type/key", "type/uri", "type/datetime", "type/int", "type/float", "type/text", "type/boolean"
MAX_INT = 2 ** 31 - 1 

def make_query(q, site, path="", context=None):
    """Takes nested dictionary as input and returns nested query object."""
    context = context or Context(site)
    if isinstance(q, list):
        return QueryList([make_query(x, site, "%s/%d" % (path, i), context) for i, x in enumerate(q)])
    elif isinstance(q, dict):
        d = dict((k, make_query(v, site, path + "/" + k, context)) for k, v in q.items())
        return Query(context, d, path)
    else:
        return SimpleQuery(context, q, path)

class Context:
    """Query execution context for bookkeeping."""
    def __init__(self, site):
        self.site = site
        self.revisions = {}

    def get_revision(self, thing_id):
        if thing_id not in self.revisions:
            id = web.insert('version', thing_id=thing_id)
            version = web.select('version', where='id=$id', vars=locals())[0]
            self.revisions[thing_id] = version.revision
        return self.revisions[thing_id]

    def insert(self, thing_id, key, value):
        if isinstance(value, list):
            for v in value:
                self.insert(thing_id, key, v)
        else:
            revision = self.get_revision(thing_id)
            web.insert('datum', False, thing_id=thing_id, key=key, value=value.value, datatype=value.datatype, begin_revision=revision)

    def delete(self, thing_id, key, value):
        revision = self.get_revision(thing_id)
        max_rev = MAX_INT-1
        count = web.update('datum', where="thing_id=$thing_id AND key=$key AND value=$value.value" +
            " AND datatype=$value.datatype AND end_revision=$max_rev", end_revision=revision, vars=locals())
        assert count <= 1

    def update(self, thing_id, key, value):
        revision = self.get_revision(thing_id)
        max_rev = MAX_INT-1
        count = web.update('datum', where='thing_id=$thing_id AND key=$key AND end_revision=$max_rev', end_revision=revision, vars=locals())
        assert count <= 1
        self.insert(thing_id, key, value)

class Value:
    """Datastucture to store value and its type. 
    Execution of every query returns this.
    """
    def __init__(self, site, value, type):
        self.type = type

        self.datatype = infobase.TYPES.get(type, infobase.DATATYPE_REFERENCE)

        if self.datatype == infobase.DATATYPE_REFERENCE:
            thing = site.withKey(value)
            self.value = thing.id
            self.key = value
        else:
            self.value = value
            self.key = None
            if type == "type/boolean":
                self.value = int(value)

    def __str__(self): return str((self.value, self.type))
    __repr__ = __str__

class WriteException(infobase.InfobaseException):
    def __init__(self, path, message):
        infobase.InfobaseException.__init__(self, message)
        self.path = path
        self.message = message

class QueryList(list):
    def __init__(self, data):
        list.__init__(self, data)
        self.expected_type = None

    def execute(self):
        return [q.execute() for q in self]

    def dict(self):
        return [q.dict() for q in self]

class Query:
    """Infobase write query."""
    def __init__(self, ctx, d, path):
        self.create = d.pop('create', None)
        self.connect = d.pop('connect', None)
        if self.create: self.create = self.create.value
        if self.connect: self.connect = self.connect.value

        self.ctx = ctx
        self.site = ctx.site
        self.d = d
        self.path = path

        self.expected_type = None
        self.result = None

    def get_type(self):
        if 'type' in self.d:
            type = self.d['type']
            if isinstance(type, SimpleQuery):
                return type.value
            elif isinstance(type, basestring):
                return type
            else:
                return type.execute().value
        else:
            return None

    def execute(self):
        """Executes the query and returns its value."""
        if self.result:
            return self.result

        if 'key' in self.d:
            self.d['key'].expected_type = 'type/key'
        if 'type' in self.d:
            self.d['type'].expected_type = 'type/type'

        if self.create:
            thing = self.get_thing(validate_type=False)
            if thing:
                self.create = 'present'
            else:
                thing = self.create_thing()
                self.create = 'created'
                
                if 'type' in self.d:
                    self.d['type'].expected_type = 'type/type'

                self.fill_types()
                for k, v in self.d.items():
                    v = v.execute()
                    self.ctx.insert(thing.id, k, v)
            self.result = Value(self.site, thing.key, thing.type.key)
        elif self.is_primitive():
            assert "type" in self.d
            assert "value" in self.d
            self.result = Value(self.site, self.d['value'].value, self.d['type'].value)
        else:
            if 'type' in self.d:
                self.d['type'].expected_type = 'type/type'
            thing = self.get_thing()
            if not thing:
                raise WriteException(self.path, "Not Found")
            self.fill_types(thing.type)
            for k, v in self.d.items():
                v1 = v.execute()
                self.xconnect(thing.id, k, v1, v)
            self.result = Value(self.site, thing.key, thing.type)
        return self.result

    def get_thing(self, validate_type=True):
        """Returns the thing matching the given query.
        If the query has 'type' then type the resulting object be same as the given type.
        """
        assert 'key' in self.d
        key = self.d['key'].execute().value

        try:
            thing = self.site.withKey(key)
            if validate_type and self.expected_type:
                assert thing.type == self.expected_type
            if validate_type and 'type' in self.d:
                assert thing.type.key == self.d['type'].execute().key
            return thing
        except infobase.NotFound:
            return None

    def create_thing(self):
        """Creates a new thing using the query.
        It also make sure that all the given properties are of required type.
        """
        assert 'key' in self.d and 'type' in self.d
        key = self.d['key'].execute().value
        id = web.insert('thing', site_id=self.site.id, key=key)
        self.thing = infobase.Thing(self.site, id, key)
        return self.thing

    def xconnect(self, thing_id, key, value, query):
        if isinstance(value, list):
            for q, v in zip(query, value):
                self.xconnect(thing_id, key, v, q)
        else:
            d = web.select('datum', 
                where='thing_id=$thing_id AND key=$key AND value=$value.value AND datatype=$value.datatype',
                vars=locals())
            d = [row.value for row in d]
            present = value.value in d
            if query.connect == "insert" or query.create:
                if present:
                    query.connect = 'present'
                else:
                    query.connect = 'connected'
                    self.ctx.insert(thing_id, key, value)
            elif query.connect == 'delete':
                if not present:
                    query.connect = 'absent'
                else:
                    query.connect = 'deleted'
                    self.ctx.delete(thing_id, key, value)
            elif query.connect == 'update':
                if present:
                    query.connect = 'present'
                else:
                    query.connect = 'updated'
                    self.ctx.update(thing_id, key, value)

    def is_primitive(self):
        if 'type' in self.d:
            type = self.d['type']
            if isinstance(type, SimpleQuery):
                type = type.value
            else:
                type = type.execute().value
            return type in PRIMITIVE_TYPES
        else:
            return False

    def fill_types(self, type=None):
        """Fill expected types of all the children."""
        if 'key' in self.d:
            self.d['key'].expected_type = 'type/type'
        
        if type == None:
            assert 'type' in self.d
            # improve
            type_id = self.d['type'].execute().value
            type = self.site.withID(type_id)
        elif isinstance(type, basestring):
            type = self.site.withKey(type)

        def get_properties(type):
            return dict((web.lstrips(p.key, type.key + '/'), p) for p in type._get('properties', []))

        for name, p in get_properties(type).items():
            if name in self.d:
                t = p.expected_type
                if isinstance(t, infobase.Thing):
                    t = t.key
                self.d[name].expected_type = t

    def dict(self):
        if not isinstance(self.d, dict):
            return self.d
        d = self.d.copy()
        for k, v in d.items():
            if isinstance(v, Query):
                d[k] = v.dict()
            elif isinstance(v, list):
                d[k] = [x.dict() for x in v]
        if self.create:
            d['create'] = self.create
        elif self.connect:
            d['connect'] = self.connect

        return d

    def __str__(self):
        if self.create: action = 'create '
        elif self.connect: action = 'connect '
        else: action = ""
        return "<%squery: %s>" % (action, repr(self.d))

    __repr__ = __str__


class SimpleQuery:
    """Query class for handling leaf nodes in the query."""
    def __init__(self, ctx, value, path):
        self.ctx = ctx
        self.value = value
        self.path = path
        self.expected_type = None
        self.parent = None
        self.result = None
        self.connect = None
        self.create = None

    def execute(self):
        if not self.result:
            self.result = Value(self.ctx.site, self.value, self.expected_type or "type/string")
        return self.result

    def dict(self):
        return self.value
    
    def __str__(self): return repr(self.value)
    __repr__ = __str__

if __name__ == "__main__":
    import doctest
    doctest.testmod()

