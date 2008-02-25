"""Module to execute infobase write queries.
"""
import web
import infobase
import multiple_insert

MAX_INT = 2 ** 31 - 1 

error = infobase.InfobaseException

class Value:
    """Datastucture to store value and its type. 
    Execution of every query returns this.
    """
    def __init__(self, value, type):
        assert value is None or isinstance(value, (basestring, int, float, bool, infobase.Thing))
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
        if self.value is None:
            return self.value
            
        if isinstance(expected_type, infobase.Thing):
            expected_type = expected_type.key

        def makesure(condition):
            if not condition:
                raise Exception, "%s: expected %s but found %s" % (self.value, expected_type, self.type)

        if self.type is not None:
            makesure(self.type == expected_type)
        else:
            if expected_type not in infobase.TYPES:
                thing = ctx.withKey(self.value)
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
    def __init__(self, ctx, d, path, create=None, connect=None):
        self.ctx = ctx
        self.d = d
        self.path = path
        self.value = None
        self._create = create
        self._connect = connect

    def get_expected_type(self, type, name):
        if name == 'key':
            return 'type/key', True
        elif name == 'type':
            return 'type/type', True
        elif name in ['permission', 'child_permission']:
            return 'type/permission', True
        else:
            properties = type._get('properties', [])
            for p in properties:
                if p.key.split('/')[-1] == name:
                    return p.expected_type, p.unique.value
        return None, None
        
    def assert_expected_type(self, thing, key, value):
        """Make sure the value has the type as expected."""
        expected_type, unique = self.get_expected_type(thing.type, key)
        if expected_type:
            if unique:
                if isinstance(value, list):
                    raise error('%s: expected unique value but found list.' % value)
            else:
                if not isinstance(value, list):
                    raise error('%s: expected list but found unique value.' % value.value)

            if isinstance(value, list):
                for v in value:
                    v.coerce(self.ctx, expected_type)
            else:
                value.coerce(self.ctx, expected_type)

    def datum2value(self, d):
        """Converts Datum/Thing object got from thing.foo to Value."""
        if isinstance(d, list):
            return [self.datum2value(x) for x in d]
        elif isinstance(d, infobase.Thing):
            return Value(d, d.type.key)
        elif isinstance(d, infobase.Datum):
            def get_type(datatype):
                for k, v in infobase.TYPES.items():
                    if v == datatype: 
                        return k
            type = get_type(d._get_datatype())
            return Value(d.value, type)
        else:
            raise Exception, 'huh?'

    def execute(self):
        if self.value:
            return self.value
            
        if isinstance(self.d, list):
            self.value = [q.execute() for q in self.d]
        elif isinstance(self.d, dict):
            if self._connect == 'update_list':
                assert 'value' in self.d
                assert isinstance(self.d['value'].d, list)
                self.value = self.d['value'].execute()
            elif 'value' in self.d: # primitive type
                value = self.d['value'].execute().value
                type = self.d.get('type')
                type = type and type.execute().value
                assert isinstance(value, (basestring, int, float, bool))
                assert type is None or isinstance(type, basestring)
                self.value = Value(value, type)
            else:
                assert 'key' in self.d
                key = self.d['key'].execute().value
                assert isinstance(key, basestring)
                
                thing = self.ctx.get(key)
                if thing:
                    for k, v in self.d.items():
                        self.connect(thing, k, v)
                else:
                    if self._create == 'unless_exists':
                        if not self.ctx.can_write(key):
                            raise infobase.PermissionDenied('Permission denied to modify: ' + repr(key))

                        assert 'type' in self.d
                        thing = self.ctx.create(key)
                        type = self.d['type'].execute()
                        type.coerce(self.ctx, 'type/type')
                        thing._d['type'] = infobase.Datum(type.value, 0)
                        self.insert_all(thing, self.d)
                        self._create = 'created'
                    else:
                        raise infobase.InfobaseException('Not found: ' + key)
                        
                self.value = Value(thing, thing.type.key)
        else:
            self.value = Value(self.d, None)
        return self.value
        
    def get_connect(self):
        if self._connect:
            return self._connect
        elif self._create == 'created':
            return 'update'    
        return None
        
    def connect(self, thing, key, query):
        if isinstance(query.d, list):
            for q in query.d:
                self.connect(thing, key, q)
            return
                
        assert isinstance(key, basestring)
        #assert isinstance(value, (Value, list))
        assert isinstance(thing, infobase.Thing)
            
        connect = query.get_connect()
        
        if connect:
            if not self.ctx.can_write(thing.key):
                raise infobase.PermissionDenied('Permission denied to modify: ' + repr(thing.key))        
            value = query.execute()
            if connect == 'update': 
                query._connect = self.update(thing, key, value)
            elif connect == 'update_list': 
                query._connect = self.update_list(thing, key, value)
            elif connect == 'insert':
                query._connect = self.insert(thing, key, value)
            elif connect == 'delete':
                query._connect = self.delete(thing, key, value)
        
    def update(self, thing, key, value):
        self.assert_expected_type(thing, key, value)        
        assert not isinstance(value, list)
        old = thing._get(key, None)
        present = old and self.datum2value(old) == value
        
        if present:
            return "present"
        else:
            self.ctx.update(thing, key, value)        
            return "updated"
        
    def update_list(self, thing, key, value):
        self.assert_expected_type(thing, key, value)        
        assert isinstance(value, list)
        self.ctx.update_list(thing, key, value)
        return 'updated'

    def insert(self, thing, key, value):
        """Inserts a new value to elements of thing[key] if it is not already inserted."""
        old = thing._get(key, None)
        present = old and value in self.datum2value(old)
        
        if present:
            return "present"
        else:
            self.ctx.insert(thing, key, value)        
            return "inserted"
            
    def delete(self, thing, key, value):
        """Deletes value to elements of thing[key]."""
        old = thing._get(key, None)
        present = old and value in self.datum2value(old)
        
        if present:
            self.ctx.delete(thing, key, value)
            return "deleted"
        else:
            return "absent"
        
    def insert_all(self, thing, d):
        """Inserts all values of a new thing."""        
        values = {}
        for key, value in self.d.items():
            value = value.execute()
            self.assert_expected_type(thing, key, value)
            values[key] = value
            
        self.ctx.insert_all(thing, values)
        #multiple_insert.multiple_insert('datum', data, seqname=False)

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
    """Query execution context for bookkeeping.
    This also isolates the query execution from interacting with infobase cache.
    """
    def __init__(self, site, comment, author=None, ip=None):
        self.site = site
        self.comment = comment
        self.author = author
        self.author_id = author and author.id
        self.ip = ip
        self.revisions = {}
        self.updated = set()
        self.created = set()
        self.key2id = {}
        self.cache = {}
        
    def has_permission(self, key, get_groups):
        if web.ctx.get('infobase_bootstrap'):
            return True
            
        permission = self.get_permission(key)
        
        if permission is None:
            return True
        
        for group in get_groups(permission):
            if group.key == 'permission/everyone':
                return True
            elif self.author is not None:    
                if group.key == 'permission/allusers' or self.author in group._get('members', []):
                    return True
                        
        return False
    
    def can_write(self, key):
        return self.has_permission(key, lambda p: p._get('writers', []))
    
    def can_admin(self, key):
        return self.has_permission(key, lambda p: p._get('admins', []))
            
    def get_permission(self, key):
        def parent(key):
            if '/' in key:
                return key.rsplit('/', 1)[0]
        
        if key == None:
            return None
        
        try:
            thing = self.withKey(key)
        except infobase.NotFound:
            thing = None
        
        permission = thing and thing._get('permission')
        return permission or self.get_permission(parent(key))

    def get_revision(self, thing):
        if thing.id not in self.revisions:
            id = web.insert('version', thing_id=thing.id, comment=self.comment, author_id=self.author_id, ip=self.ip)
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
            create = q.pop('create', None)
            connect = q.pop('connect', None)
            d = dict((k, self.make_query(v, path + "/" + k)) for k, v in q.items())
            return Query(self, d, path, create, connect)
        else:
            return Query(self, q, path)

    def execute(self, query):
        query = self.make_query(query)
        query.execute()
        return dict(created=list(self.created), updated=list(self.updated))
    
    def process(self, thing):
        if thing:
            thing = thing.copy()
            thing._load()
            thing._site = self.site
            self.cache[thing.id] = thing
            self.key2id[thing.key] = thing.id
        return thing
        
    def withID(self, id):
        if id in self.cache:
            return self.cache[id]
        else:
            thing = self.site.withID(id)
            return self.process(thing)

    def withKey(self, key):
        if key in self.key2id:
            return self.withID(self.key2id[key])
        else:
            thing = self.site.withKey(key)
            return self.process(thing)
        
    def get(self, key):
        if key in self.key2id:
            return self.withID(self.key2id[key])
        else:
            thing = self.site.get(key)
            return self.process(thing)

    def create(self, key):
        """Creates a new thing with the specified key."""
        id = web.insert('thing', site_id=self.site.id, key=key)
        thing = infobase.Thing(self, id, key)
        thing._d = web.storage(key=key)
        self.key2id[key] = id
        self.cache[id] = thing
        return thing

    def insert_all(self, thing, values):
        # this is called after calling create
        data = []
        def insert(thing_id, revision, key, value, ordering=None):
            if isinstance(value, list):
                return [insert(thing_id, revision, key, v, i) for i, v in enumerate(value)]
            else:
                datatype = value.get_datatype()
                value = value.value
                data.append(dict(thing_id=thing_id, begin_revision=revision, 
                    key=key, value=value, datatype=datatype, ordering=ordering))
                return infobase.Datum(value, datatype)

        revision = self.get_revision(thing)
        for key, value in values.items():
            thing._d[key] = insert(thing.id, revision, key, value)
        multiple_insert.multiple_insert('datum', data, seqname=False)
        
    def update(self, thing, key, value):
        max_rev = MAX_INT
        revision = self.get_revision(thing)
        datatype = value.get_datatype()
        value = value.value
        web.update('datum', 
            where='thing_id=$thing.id AND key=$key AND value=$value AND datatype=$datatype AND end_revision=$max_rev',
            end_revision=revision, vars=locals())

        web.insert('datum', False, thing_id=thing.id, key=key, value=value, datatype=datatype, begin_revision=revision)
        thing._d[key] = infobase.Datum(value, datatype)
        
    def update_list(self, thing, key, value):
        max_rev = MAX_INT
        revision = self.get_revision(thing)
        web.update('datum', 
            where='thing_id=$thing.id AND key=$key AND end_revision=$max_rev', 
            end_revision=revision, vars=locals())

        new_value = []
        #@@ use multi_insert
        for i, v in enumerate(value):
            web.insert('datum', False, thing_id=thing.id, key=key, value=v.value, datatype=v.get_datatype(), begin_revision=revision, ordering=i)
            new_value.append(infobase.Datum(v.value, v.get_datatype()))
        thing._d[key] = new_value
        
    def insert(self, thing, key, value):
        datatype = value.get_datatype()
        value = value.value
        revision = self.get_revision(thing)
        web.insert('datum', False, 
            thing_id=thing.id, begin_revision=revision,
            key=key, value=value, datatype=datatype, ordering=0)
        value = infobase.Datum(value, datatype)
        thing._d[key].append(value)
        
    def delete(self, thing, key, value):
        datatype = value.get_datatype()
        value = value.value
        max_rev = MAX_INT            
        revision = self.get_revision(thing)
        web.update('datum', 
            where='thing_id=$thing.id AND end_revision=$max_rev AND key=$key AND value=$value AND datatype=$datatype',
            end_revision=revision,
            vars=locals())
        value = infobase.Datum(value, datatype)
        thing._d[key].remove(value)
