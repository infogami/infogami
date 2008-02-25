"""
Infobase: structured database.

Infobase contains multiple sites and each site can store any number of objects. 
Each object has a key, that is unique to the site it belongs.
"""
import web
from multiple_insert import multiple_insert

KEYWORDS = ["id", 
    "action", "create", "update", "insert", "delete", 
    "limit", "offset", "index", "sort", 
    "revision", "version", "history", 
    "value", "metadata"
]
    
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
    
class PermissionDenied(InfobaseException):
    pass
    
def loadhook():
    ctx = web.storage()
    ctx.dirty = []
    web.ctx.infobase_ctx = ctx
            
web.loadhooks['infobase_hook'] = loadhook

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
            return Infosite(s.id, s.name, s.secret_key)
        else:
            raise SiteNotFound(name)

    def create_site(self, name, admin_password):
        import bootstrap
        secret_key = self.randomkey()
        try:
            web.transact()
            id = web.insert('site', name=name, secret_key=secret_key)
            site = Infosite(id, name, secret_key)
            bootstrap.bootstrap(site, admin_password)
        except:
            web.rollback()
            raise
        else:
            web.commit()
            return site

    def randomkey(self):
        import string, random
        chars = string.letters + string.digits
        return "".join(random.choice(chars) for i in range(25))

    def delete_site(self, name):
        pass
        
class ThingList(list):
    def get(self, key, default=None):
        for t in self:
            if t.key == key:
                return t
        return default

    def _get_value(self):
        return [t._get_value() for t in self]

class Datum(object):
    __slots__ = ['value', 'datatype']
    def __init__(self, value, datatype):
        self.value = value
        self.datatype = datatype

    def _get_value(self):
        return self.value
    
    def _get_datatype(self):
        return self.datatype
        
    def __repr__(self):
        return repr(self.value)
    __str__ = __repr__
        
class Thing:
    """Thing: an object in infobase."""
    def __init__(self, site, id, key, last_modified=None, latest_revision=None, revision=None):
        self._site = site
        self.id = id
        self.key = key
        self.revision = revision
        self.last_modified = last_modified and last_modified.isoformat()
        self.latest_revision = latest_revision
        self._d = None # data is loaded lazily on demand

    def _get_value(self):
        return self.id

    def _get_datatype(self):
        return DATATYPE_REFERENCE
        
    def _load(self):
        if self._d is None:
            revision = self.revision or MAX_REVISION
            d = web.select('datum', where='thing_id=$self.id AND begin_revision <= $revision AND end_revision > $revision', order='key, ordering', vars=locals())
            d = self._parse_data(d)
            self._d = d
        
    def _get_data(self):
        def unthingify(thing):
            if isinstance(thing, list):
                return [unthingify(x) for x in thing]
            elif isinstance(thing, Datum):
                if thing.datatype == DATATYPE_REFERENCE:
                    return {'key': self._site.withID(thing.value).key}
                else:
                    return thing._get_value()
            else:
                return thing
        
        self._load()
        d = {
            'last_modified': self.last_modified, 
            'latest_revision': self.latest_revision,
            'revision': self.revision or self.latest_revision
        }
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
        value = self._d[key]
        
        def process(value):
            """Return Thing when datatype is reference, Datum object otherwise.
            Properties of a thing are always stored as Datum objects, 
            so that it will not keep reference to any thing, which may interfere with caching.
            """
            if isinstance(value, list):
                return [process(v) for v in value]
            elif value.datatype == DATATYPE_REFERENCE:
                return self._site.withID(value.value)
            else:
                return value
                
        return process(value)
        
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
            if r.datatype in (TYPES['type/string'], TYPES['type/key'], TYPES['type/uri'], TYPES['type/text']):
                value = Datum(r.value, r.datatype)
            elif r.datatype == TYPES['type/int'] or r.datatype == DATATYPE_REFERENCE:
                value = Datum(int(r.value), r.datatype)
            elif r.datatype == TYPES['type/float']:
                value = Datum(float(r.value), r.datatype)
            elif r.datatype == TYPES['type/boolean']:
                value = Datum(bool(int(r.value)), r.datatype)
            else:
                raise Exception, "unknown datatype: %s" % r.datatype

            if r.ordering is not None:
                d.setdefault(r.key, []).append(value)
            else:
                d[r.key] = value

        return d
        
    def __repr__(self):
        return "<Thing: %s at %d>" % (self.key, self.id)
        
    def __str__(self):
        return self.key

    def __eq__(self, other):
        return isinstance(other, Thing) and self.id == other.id

    def __ne__(self, other):
        return not (self == other)

class Infosite:
    def __init__(self, id, name, secret_key):
        self.id = id
        self.name = name
        self.secret_key = secret_key
        
    def get(self, key):
        """Same as withKey, but returns None instead of raising exception when object is not found."""
        try:
            return self.withKey(key)
        except NotFound:
            return None

    def withKey(self, key, revision=None, lazy=False):
        try:
            d = web.select('thing', where='site_id = $self.id AND key = $key', vars=locals())[0]
        except IndexError:
            raise NotFound, key
            
        return Thing(self, d.id, d.key, d.last_modified, d.latest_revision, revision=revision)
        
    def withID(self, id, revision=None):
        try:
            d = web.select('thing', where='site_id = $self.id AND id = $id', vars=locals())[0]        
        except IndexError:
            raise NotFound, id
        return Thing(self, d.id, d.key, d.last_modified, d.latest_revision, revision=revision)

    def things(self, query):
        assert isinstance(query, dict)
        
        type = query.get('type')
        type = type and self.withKey(type)
        
        #@@ make sure all keys are valid.
        tables = ['thing']
        what = 'thing.key'
        revision = query.pop('revision', MAX_REVISION)
        
        where = web.reparam('thing.site_id = $self.id', locals())
        
        offset = query.pop('offset', None)
        limit = query.pop('limit', None)
        order = query.pop('sort', None)

        from readquery import join, get_datatype

        if order:
            if order.startswith('-'):
                order = order[1:]
                desc = " desc"
            else:
                desc = ""
            datatype = get_datatype(type, order)            
            tables.append('datum as ds')
            where += web.reparam(" AND ds.thing_id = thing.id"
                + " AND ds.begin_revision <= $revision AND ds.end_revision > $revision"
                + " AND ds.key = $order AND ds.datatype = $datatype", locals())
            order = "ds.value" + desc
            
        for i, (k, v) in enumerate(query.items()):
            d = 'd%d' % i
            tables.append('datum as ' + d)
            where  += ' AND ' + join(self, type, d, k, v, revision)
                
        return [r.key for r in web.select(tables, what=what, where=where, offset=offset, limit=limit, order=order)]
        
    def versions(self, query):
        offset = query.pop('offset', None)
        limit = query.pop('limit', None)
        order = query.pop('sort', None)
        
        query = web.storage(query)
        
        if order and order.startswith('-'):
            order = order[1:]
            desc = " desc"
        else:
            desc = ""
        
        keys = ["key", "revision", "author", "comment", "created"]
        if order:
            assert order in keys
            order = order + desc
        
        what = 'thing.key, version.revision, version.author_id, version.comment, version.comment, version.ip, version.created'
        where = 'thing.id = version.thing_id'
                        
        if 'key' in query:
            key = query['key']
            where += ' AND key=$key'
        if 'revision' in query:
            where += ' AND revision=query.revision'
        if 'author' in query:
            key = query['author']
            author = self.withKey(key)
            where += ' AND author_id=$author.id'
        if 'created' in query:
            where += 'AND created = $created'
            
        result = web.select(['version', 'thing'], what=what, where=where, offset=offset, limit=limit, order=order, vars=locals())
        out = []

        for r in result:
            r.created = r.created.isoformat()
            r.author = r.author_id and self.withID(r.author_id).key
            del r.author_id
            out.append(dict(r))
        return out

    def write(self, query, comment=None):
        web.transact()
        try:
            import writequery2 as writequery
            a = self.get_account_manager()
            ctx = writequery.Context(self, comment, author=a.get_user(), ip=web.ctx.get('ip'))
            result =  ctx.execute(query)
            self.invalidate(result['created'] + result['updated'])
        except:
            web.rollback()
            raise
        else:
            web.commit()
        return result
    
    def invalidate(self, keys):
        """Invalidate the given keys from cache."""
        pass
        
    def get_account_manager(self):
        import account
        return account.AccountManager(self)
        
if __name__ == "__main__":
    import sys
    import os

    web.config.db_parameters = dict(dbn='postgres', db='infobase', user='anand', pw='') 
    web.config.db_printing = True
    web.load()
    infobase = Infobase()
    
    if '--create' in sys.argv:
        os.system('dropdb infobase; createdb infobase; createlang plpgsql infobase; psql infobase < schema.sql')
        site = infobase.create_site('infogami.org')

    site = infobase.get_site('infogami.org')
    for v in  site.versions({'sort': '-created', 'limit':10}):
        print v
