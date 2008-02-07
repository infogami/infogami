"""
Infobase: structured database.

Infobase contains multiple sites and each site can store any number of objects. 
Each object has a key, that is unique to the site it belongs.
"""
import web
from multiple_insert import multiple_insert

KEYWORDS = "id", "create", "limit", "offset", "index", "sort", "revision", "versions"

TYPES = {}
TYPES['type/key'] = 1
TYPES['type/string'] = 2
TYPES['type/text'] = 3
TYPES['type/uri'] = 4
TYPES['type/boolean'] = 5
TYPES['type/int'] = 6
TYPES['type/float'] = 7
TYPES['type/datetime'] = 8

DATATYPE_REFERENCE = 0
TYPE_REFERENCE = 0
TYPE_KEY = 1
TYPE_STRING = 2
TYPE_TEXT = 3
TYPE_URI = 4
TYPE_BOOLEAN = 5
TYPE_INT = 6
TYPE_FLOAT = 7
TYPE_DATETIME = 8

MAX_INT = (2 ** 31) - 1
MAX_REVISION = MAX_INT - 1

class InfobaseException(Exception):
    pass
    
class SiteNotFound(InfobaseException):
    pass
    
class NotFound(InfobaseException):
    pass

class AlreadyExists(InfobaseException):
    pass

def transactify(f):
    def g(*a, **kw):
        web.transact()
        try:
            result = f(*a, **kw)
        except:
            web.rollback()
            raise
        else:
            web.commit()
        return result
    return g

class Infobase:
    def get_site(self, name):
        d = web.select('site', where='name=$name', vars=locals())
        if d:
            s = d[0]
            return Infosite(s.id, s.name)
        else:
            raise SiteNotFound(name)
    
    def create_site(self, name):
        id = web.insert('site', name=name)
        site = Infosite(id, name)
        import bootstrap
        site.write(bootstrap.types)
        return site
    
    def delete_site(self, name):
        pass
        
class ThingList(list):
    def get(self, key, default=None):
        for t in self:
            if t.key == key:
                return t
        return default
        
class Thing:
    """Thing: an object in infobase."""
    def __init__(self, site, id, key, revision=None):
        self._site = site
        self.id = id
        self.key = key
        self.revision = revision
        self._d = None # data is loaded lazily on demand
        
    def _load(self):
        if self._d is None:
            revision = self.revision or MAX_REVISION
            d = web.select('datum', where='thing_id=$self.id AND begin_revision <= $revision AND end_revision > $revision', vars=locals())
            d = self._parse_data(d)
            self._d = d
        
    def _get_data(self):
        def unthingify(thing):
            if isinstance(thing, list):
                return [unthingify(x) for x in thing]
            elif isinstance(thing, Thing):
                return thing.key
            else:
                return thing
        
        self._load()
        d = {}
        for k, v in self._d.items():
            d[k] = unthingify(v)
        return d
        
    def _get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default
        
    def __getitem__(self, key):
        if self._d is None:
            self._load()
        return self._d[key]
        
    def __getattr__(self, key):
        if key.startswith('__'):
            raise AttributeError, key
            
        try:
            return self[key]
        except KeyError:
            raise AttributeError, key
        
    def _parse_data(self, data):
        d = web.storage()
        for r in data:
            value = r.value
            if r.datatype == DATATYPE_REFERENCE:
                value = self._site.withID(int(value))
            elif r.datatype in (TYPES['type/string'], TYPES['type/key'], TYPES['type/uri']):
                pass # already a string
            elif r.datatype == TYPES['type/int']:
                value = int(value)
            elif r.datatype == TYPES['type/float']:
                value = float(value)
            elif r.datatype == TYPES['type/boolean']:
                value = (str(value).lower() != "false")

            if r.key in d:
                if not isinstance(d[r.key], list):
                    d[r.key] = ThingList([d[r.key]])
                d[r.key].append(value)
            else:
                d[r.key] = value

        return d
        
    def __repr__(self):
        return "<Thing: %s at %d>" % (self.key, self.id)
        
    def __str__(self):
        return self.key
        
class Infosite:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        
    def get_object(self, key):
        d = web.select('thing', where='site_id = $self.id AND key = $key', vars=locals())
        obj = d and d[0] or None

    def withKey(self, key, lazy=False):
        try:
            d = web.select('thing', where='site_id = $self.id AND key = $key', vars=locals())[0]
        except IndexError:
            raise NotFound, key
            
        return Thing(self, d.id, d.key)
        
    def withID(self, id):
        try:
            d = web.select('thing', where='site_id = $self.id AND id = $id', vars=locals())[0]        
        except IndexError:
            raise NotFound, id
        return Thing(self, d.id, d.key)
        
    def get_datatype(self, type, key):
        if key == 'key':
            return TYPES['type/key']
        elif key == 'type':
            return DATATYPE_REFERENCE
            
        key = type.key + '/' + key
        p = type.properties.get(key)

        if p:
            expected_type = p.expected_type.key
            print >> web.debug, p, expected_type
            if expected_type in TYPES:
                return TYPES[expected_type]
            else:
                return DATATYPE_REFERENCE
        else:
            return TYPES['type/string']

    def things(self, query):
        assert isinstance(query, dict)
        assert 'type' in query
        assert query['type'] is not None
            
        type = self.withKey(query['type'])
        
        #@@ make sure all keys are valid.
        tables = ['thing']
        what = 'thing.key'
        revision = query.pop('revision', MAX_REVISION)
        
        where = '1 = 1'
        
        def cast(v, datatype):
            if datatype == TYPES['type/int'] or TYPES['type/boolean'] or DATATYPE_REFERENCE:
                return 'cast(%s as int)' % v
            else:
                return v
                
        def join(table, key, value, datatype, revision):
            if datatype in [TYPE_BOOLEAN, TYPE_INT, TYPE_REFERENCE]:
                value_column = 'cast(%s.value as int)' % table
                
                if datatype == TYPE_REFERENCE:
                    value = self.withKey(value).id
                elif datatype == TYPE_BOOLEAN:
                    value = int(value)
            elif datatype == TYPE_FLOAT:
                value_column = 'cast(%s.value as float)' % table
                value = float(value)
            else:
                value_column = '%s.value' % table
                value = str(value)
                
            q = ['%(table)s.thing_id = thing.id',
                '%(table)s.begin_revision <= $revision',
                '%(table)s.end_revision > $revision',
                '%(table)s.key = $key',
                '%(value_column)s = $value',
                '%(table)s.datatype = $datatype']
                
            q = ' AND '.join(q) % locals()
            return web.reparam(q, locals())
        
        offset = query.pop('offset', None)
        limit = query.pop('limit', None)
        order = query.pop('sort', None)
        
        if order:
            datatype = self.get_datatype(type, order)            
            tables.append('datum as ds')
            where += web.reparam(" AND ds.thing_id = thing.id"
                + " AND ds.begin_revision <= $revision AND ds.end_revision > $revision"
                + " AND ds.key = $order AND ds.datatype = $datatype", locals())
            order = "ds.value"
                
        for i, (k, v) in enumerate(query.items()):
            d = 'd%d' % i
            tables.append('datum as ' + d)
            where  += ' AND ' + join(d, k, v, self.get_datatype(type, k), revision)
                
        return [r.key for r in web.select(tables, what=what, where=where, offset=offset, limit=limit, order=order)]

    @transactify
    def write(self, query):
        import writequery
        q = writequery.make_query(query, self)
        q.execute()
        return q.dict()
        
if __name__ == "__main__":
    import sys
    import os

    web.config.db_parameters = dict(dbn='postgres', db='infobase', user='anand', pw='') 
    web.config.db_printing = True
    web.load()
    infobase = Infobase()
    
    if '--create' in sys.argv:
        #os.system('dropdb infobase; createdb infobase; createlang plpgsql infobase; psql infobase < schema.sql')
        #site = infobase.create_site('infogami.org')
        site = infobase.create_site('test')

    site = infobase.get_site('infogami.org')
    web.commit()
    print site.create({"type": "type/property", 'sort': 'name'})
    web.rollback()
