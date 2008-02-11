"""Module to execute infobase write queries.
"""
import web
import infobase

MAX_INT = 2 ** 31 - 1 

class Value:
    """Datastucture to store value and its type. 
    Execution of every query returns this.
    """
    def __init__(self, value, type):
        assert isinstance(value, (basestring, int, float, bool, infobase.Thing))
        if type:
            assert isinstance(type, basestring)

        self.type = type
        self.datatype = type and infobase.TYPES.get(type, infobase.DATATYPE_REFERENCE)

        if self.type == None:
            if isinstance(value, bool):
                self.type = type = 'type/boolean'
                self.datatype = infobase.TYPES['type/boolean']

        if self.datatype == infobase.DATATYPE_REFERENCE:
            self.value = value.id
            self.key = value
        else:
            self.value = value
            self.key = None
            if type == "type/boolean":
                self.value = int(value)

    def __eq__(self, other):
        return isinstance(other, Value) and self.value == other.value and self.get_datatype() == other.get_datatype()

    def get_datatype(self):
        if self.datatype is None:
            return infobase.TYPES['type/string']
        else:
            return self.datatype

    def coerce(self, ctx, expected_type):
        if isinstance(expected_type, infobase.Thing):
            expected_type = expected_type.key

        def makesure(condition):
            if not condition:
                raise Exception, "%s: expected %s but found %s" % (self.value, expected_type, self.type)

        if self.type is not None:
            makesure(self.type == expected_type)
        else:
            if expected_type not in infobase.TYPES:
                thing = ctx.site.withKey(self.value)
                self.type = expected_type
                self.value = thing.id
                self.datatype = infobase.DATATYPE_REFERENCE
            elif expected_type == 'type/int':
                makesure(isinstance(self.value, int))
                self.datatype = infobase.TYPES['type/int']
            elif expected_type == 'type/boolean':
                self.datatype = infobase.TYPES['type/boolean']
                self.value = int(bool(self.value))
            elif expected_type == 'type/float':
                makesure(isinstance(self.value, (int, float)))
                self.datatype = infobase.TYPES['type/float']
                self.value = float(self.value)
            else: # one of 'type/string', 'type/text', 'type/key', 'type/uri', 'type/datetime'
                self.type = expected_type
                self.datatype = infobase.TYPES[expected_type]
                # validate for type/key, type/uri and type/datetime 
                # (database will anyway do it, but we can give better error messages).
        
    def __str__(self): return str((self.value, self.type))
    __repr__ = __str__

class Query:
    def __init__(self, ctx, d, path):
        self.ctx = ctx
        self.d = d
        self.path = path
        self.value = None

    def get_expected_type(self, type, name):
        if name == 'key':
            return 'type/key', True
        elif name == 'type':
            return 'type/type', True
        else:
            for p in type._get('properties', []):
                if p.key.split('/')[-1] == name:
                    return p.expected_type, p.unique.value
        return None, None

    def update(self, thing, key, value):
        assert isinstance(key, basestring)
        assert isinstance(value, (Value, list))
        assert isinstance(thing, infobase.Thing)

        old = thing._get(key, None)

        expected_type, unique = self.get_expected_type(thing.type, key)
        if expected_type:
            if unique:
                if isinstance(value, list):
                    raise Exception, '%s: expected unique value but found list.' % value
            else:
                if not isinstance(value, list):
                    raise Exception, '%s: expected list but found unique value.' % value.value

            if isinstance(value, list):
                for v in value:
                    v.coerce(self.ctx, expected_type)
            else:
                value.coerce(self.ctx, expected_type)

        def datum2value(d):
            if isinstance(d, list):
                return [datum2value(x) for x in d]
            elif isinstance(d, infobase.Thing):
                return Value(d, d.type.key)
            elif isinstance(d, infobase.Datum):
                def get_type(datatype):
                    for k, v in infobase.TYPES.items():
                        if v == datatype: 
                            return k
                type = get_type(d._get_datatype())
                return Value(d.value, type)

        if datum2value(old) == value:
            return
        
        max_rev = MAX_INT
        revision = self.ctx.get_revision(thing)
        web.update('datum', 
            where='thing_id=$thing.id AND key=$key AND end_revision=$max_rev', 
            end_revision=revision, vars=locals())

        if value:
            if isinstance(value, list):
                for i, v in enumerate(value):
                    web.insert('datum', False, thing_id=thing.id, key=key, value=v.value, datatype=v.get_datatype(), begin_revision=revision, ordering=i)
            else:
                web.insert('datum', False, thing_id=thing.id, key=key, value=value.value, datatype=value.get_datatype(), begin_revision=revision)

    def execute(self):
        if self.value:
            return self.value

        def get(key):
            try: 
                return self.ctx.site.withKey(key)
            except infobase.NotFound: 
                return None

        if isinstance(self.d, list):
            self.value = [q.execute() for q in self.d]
        elif isinstance(self.d, dict):
            if 'value' in self.d: # primitive type
                assert 'type' in self.d
                value = self.d['value'].execute().value
                type = self.d['type'].execute().value
                assert isinstance(value, (basestring, int, float, bool))
                assert isinstance(type, basestring)
                self.value = Value(value, type)
            else:
                assert 'key' in self.d
                key = self.d['key'].execute().value
                assert isinstance(key, basestring)
                thing = get(key)

                if not thing:
                    assert 'type' in self.d
                    web.insert('thing', site_id=self.ctx.site.id, key=key)
                    thing = get(key)
                    type = self.d['type'].execute()
                    type.coerce(self.ctx, 'type/type')
                    thing.type = self.ctx.site.withID(type.value)
                    
                for k, v in self.d.items():
                    v = v.execute()
                    self.update(thing, k, v)
                self.value = Value(thing, thing.type.key)
        else:
            self.value = Value(self.d, None)
        return self.value

    def primitive_value(self, value):
        if isinstance(value, int):
            return Value(value, 'type/int')
        elif isinstance(value, bool):
            return Value(int(value), 'type/boolean')
        elif isinstance(value, float):
            return Value(value, 'type/float')
        else:
            return Value(value, 'type/string')

    def __str__(self):
        return "<query: %s>" % repr(self.d)
    __repr__ = __str__

class Context:
    """Query execution context for bookkeeping."""
    def __init__(self, site):
        self.site = site
        self.revisions = {}
        self.updated = set()
        self.created = set()

    def get_revision(self, thing):
        if thing.id not in self.revisions:
            id = web.insert('version', thing_id=thing.id)
            version = web.select('version', where='id=$id', vars=locals())[0]
            self.revisions[thing.id] = version.revision
            if version.revision == 1:
                self.created.add(thing.key)
            else:
                self.updated.add(thing.key)
        return self.revisions[thing.id]

    def make_query(self, q, path=""):
        """Takes nested dictionary as input and returns nested query object."""
        if isinstance(q, list):
            return Query(self, [self.make_query(x, "%s/%d" % (path, i)) for i, x in enumerate(q)], path)
        elif isinstance(q, dict):
            d = dict((k, self.make_query(v, path + "/" + k)) for k, v in q.items())
            return Query(self, d, path)
        else:
            return Query(self, q, path)

    def execute(self, query):
        query = self.make_query(query)
        query.execute()
        return dict(created=list(self.created), updated=list(self.updated))

if __name__ == "__main__":
    import config
    import web
    q = [{
        'key': 'pagelist',
        'type': {'key': 'type/page'},
        'title': 'Page List',
        'body': '{{PageList("")}}'
    },
    {
        'key': 'recentchanges',
        'type': {'key': 'type/page'},
        'title': 'Recent Changes',
        'body': '{{RecentChanges("")}}'
    }]

    q = {
        'key': 'type/type',
        'type': 'type/type',
    }
    
    ctx = Context(config.site)
    print ctx.execute([q, q])

